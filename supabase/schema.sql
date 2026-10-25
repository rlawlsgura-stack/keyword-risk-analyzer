-- Server-only schema. Apply once in the selected Supabase project's SQL Editor.
-- Existing public.keywords and its permissions are intentionally untouched.
create table public.kra_state (
    id boolean primary key default true check (id),
    revision bigint not null default 0,
    columns jsonb not null default '[]'::jsonb
);
insert into public.kra_state(id) values (true);

-- JSONB preserves the existing CSV's extra columns and Korean column names.
create table public.kra_keywords (
    kwd_no text primary key check (btrim(kwd_no) <> ''),
    data jsonb not null check (jsonb_typeof(data) = 'object'),
    hit_count bigint not null default 0 check (hit_count >= 0),
    last_hit text not null default ''
);
create table public.kra_settings (
    name text primary key,
    value jsonb not null
);
create table public.kra_runs (
    id uuid primary key,
    actor text not null,
    fingerprint text not null,
    result jsonb not null,
    created_at timestamptz not null default now()
);
create table public.kra_hits (
    id bigint generated always as identity primary key,
    analysis_id uuid references public.kra_runs(id),
    kwd_no text not null,
    ts timestamptz not null default now(),
    visible boolean not null default true,
    import_key text unique,
    unique(analysis_id, kwd_no)
);
create index kra_hits_ts_idx on public.kra_hits(ts) where visible;
create index kra_hits_kwd_idx on public.kra_hits(kwd_no);
create index kra_runs_actor_idx on public.kra_runs(actor);

alter table public.kra_state enable row level security;
alter table public.kra_keywords enable row level security;
alter table public.kra_settings enable row level security;
alter table public.kra_runs enable row level security;
alter table public.kra_hits enable row level security;
revoke all on public.kra_state, public.kra_keywords, public.kra_settings,
    public.kra_runs, public.kra_hits from anon, authenticated;
grant select, insert, update, delete on public.kra_state, public.kra_keywords,
    public.kra_settings, public.kra_runs, public.kra_hits to service_role;
grant usage, select on sequence public.kra_hits_id_seq to service_role;

create function public.kra_snapshot() returns jsonb
language sql stable security invoker set search_path = '' as $$
    select jsonb_build_object('revision', s.revision, 'columns', s.columns,
        'rows', coalesce((select jsonb_agg(k.data || jsonb_build_object(
            'kwd_no', k.kwd_no, '키워드 조회 수(누적카운트)', k.hit_count::text,
            '마지막 출력일자', k.last_hit) order by k.kwd_no)
            from public.kra_keywords k), '[]'::jsonb))
    from public.kra_state s where s.id;
$$;

create function public.kra_save_keywords(p_rows jsonb, p_columns jsonb, p_revision bigint)
returns bigint language plpgsql security invoker set search_path = '' as $$
declare v_revision bigint;
begin
    select revision into v_revision from public.kra_state where id for update;
    if v_revision <> p_revision or p_revision is null then
        raise exception 'Keyword revision conflict' using errcode = '40001';
    end if;
    if jsonb_typeof(p_rows) <> 'array' or jsonb_typeof(p_columns) <> 'array' then
        raise exception 'Invalid payload';
    end if;
    if exists(select 1 from jsonb_array_elements(p_rows) r
              where coalesce(btrim(r->>'kwd_no'), '') = '') or
       (select count(*) <> count(distinct btrim(r->>'kwd_no'))
        from jsonb_array_elements(p_rows) r) then
        raise exception 'Missing or duplicate kwd_no';
    end if;
    delete from public.kra_keywords k where not exists
        (select 1 from jsonb_array_elements(p_rows) r where btrim(r->>'kwd_no') = k.kwd_no);
    insert into public.kra_keywords as k(kwd_no, data, hit_count, last_hit)
    select btrim(r->>'kwd_no'), r - '키워드 조회 수(누적카운트)' - '마지막 출력일자',
        coalesce(nullif(r->>'키워드 조회 수(누적카운트)', ''), '0')::bigint,
        coalesce(r->>'마지막 출력일자', '') from jsonb_array_elements(p_rows) r
    on conflict (kwd_no) do update set data = excluded.data;
    -- Existing counters are never overwritten by an editor's stale snapshot.
    update public.kra_state set revision = revision + 1, columns = p_columns
        where id returning revision into v_revision;
    return v_revision;
end;
$$;

create function public.kra_get_setting(p_name text) returns jsonb
language sql stable security invoker set search_path = '' as $$
    select value from public.kra_settings where name = p_name;
$$;
create function public.kra_set_setting(p_name text, p_value jsonb) returns void
language plpgsql security invoker set search_path = '' as $$
begin
    -- Serialize setting changes with keyword saves and analysis recording.
    perform 1 from public.kra_state where id for update;
    insert into public.kra_settings(name, value) values (p_name, p_value)
        on conflict(name) do update set value = excluded.value;
    update public.kra_state set revision = revision + 1 where id;
end;
$$;

create function public.kra_get_analysis(p_id uuid, p_actor text, p_fingerprint text default null)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare v_run public.kra_runs;
begin
    select * into v_run from public.kra_runs where id = p_id;
    if not found then return null; end if;
    if v_run.actor <> p_actor or
       (p_fingerprint is not null and v_run.fingerprint <> p_fingerprint) then
        raise exception 'Analysis ID conflict' using errcode = '40001';
    end if;
    return v_run.result;
end;
$$;

create function public.kra_record_analysis(p_id uuid, p_fingerprint text, p_actor text,
    p_revision bigint, p_result jsonb) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare v_revision bigint; v_result jsonb;
begin
    -- ponytail: serializes short writes; use finer row locks if measured traffic requires it.
    select revision into v_revision from public.kra_state where id for update;
    v_result := public.kra_get_analysis(p_id, p_actor, p_fingerprint);
    if v_result is not null then return v_result; end if;
    if p_revision is null or v_revision <> p_revision then
        raise exception 'Keyword revision conflict' using errcode = '40001';
    end if;
    insert into public.kra_runs(id, actor, fingerprint, result)
        values (p_id, p_actor, p_fingerprint, p_result);
    insert into public.kra_hits(analysis_id, kwd_no)
        select p_id, k.kwd_no from public.kra_keywords k
        where k.kwd_no in (select jsonb_array_elements_text(p_result->'unique_keywords'));
    update public.kra_keywords k set hit_count = hit_count + 1,
        last_hit = to_char(now() at time zone 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS')
        where exists (select 1 from public.kra_hits h
                      where h.analysis_id = p_id and h.kwd_no = k.kwd_no);
    return p_result;
end;
$$;

create function public.kra_recent_hits(p_days integer default 7) returns jsonb
language sql stable security invoker set search_path = '' as $$
    select coalesce(jsonb_agg(jsonb_build_object('ts',
        to_char(ts at time zone 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS'),
        'kwd_no', kwd_no) order by ts, id), '[]'::jsonb)
    from public.kra_hits where visible and ts between
        now() - make_interval(days => least(greatest(p_days, 1), 366)) and now();
$$;
create function public.kra_top_keywords(p_days integer default 7, p_limit integer default 10)
returns jsonb language sql stable security invoker set search_path = '' as $$
    select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) from (
        select h.kwd_no, count(*) as hit_count, k.data->>'키워드명' as term
        from public.kra_hits h left join public.kra_keywords k using(kwd_no)
        where h.visible and h.ts between
            now() - make_interval(days => least(greatest(p_days, 1), 366)) and now()
        group by h.kwd_no, k.data order by count(*) desc, h.kwd_no
        limit least(greatest(p_limit, 1), 100)
    ) t;
$$;
create function public.kra_reset_counts() returns void
language plpgsql security invoker set search_path = '' as $$
begin
    perform 1 from public.kra_state where id for update;
    update public.kra_keywords set hit_count = 0, last_hit = ''
        where hit_count <> 0 or last_hit <> '';
end;
$$;
create function public.kra_reset_week() returns bigint
language plpgsql security invoker set search_path = '' as $$
declare v_count bigint;
begin
    perform 1 from public.kra_state where id for update;
    -- Keep events for idempotency; hide them from reports rather than delete.
    update public.kra_hits set visible = false where visible
        and ts between now() - interval '7 days' and now();
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

-- No SECURITY DEFINER functions, public function grants or direct client writes.
do $$
declare f record;
begin
    for f in select p.oid::regprocedure as signature from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname like 'kra\_%' escape '\'
    loop
        execute format('revoke all on function %s from public, anon, authenticated', f.signature);
        execute format('grant execute on function %s to service_role', f.signature);
    end loop;
end;
$$;

-- Keyword inquiry tables and RLS policies are defined in keyword_requests_setup.sql.
-- Additive setup for existing projects. Safe to run again.
-- Request rows are written/read with the signed-in user's access token so RLS applies.

create table if not exists public.kra_keyword_requests (
    id uuid primary key default gen_random_uuid(),
    requester_id uuid not null,
    requester_email text not null check (length(btrim(requester_email)) > 0),
    kwd_no text not null check (length(btrim(kwd_no)) > 0),
    keyword_name text not null check (length(btrim(keyword_name)) > 0),
    request_type text not null check (request_type in (
        'risk_grade_adjustment', 'review_criteria_change'
    )),
    request_detail text not null default '' check (char_length(request_detail) <= 4000),
    status text not null default '대기',
    admin_reply text not null default '',
    created_at timestamptz not null default now()
);

alter table public.kra_keyword_requests
    add column if not exists status text not null default '대기';
alter table public.kra_keyword_requests
    add column if not exists admin_reply text not null default '';
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'kra_keyword_requests_status_check'
          and conrelid = 'public.kra_keyword_requests'::regclass
    ) then
        alter table public.kra_keyword_requests
            add constraint kra_keyword_requests_status_check
            check (status in ('대기', '검토중', '처리완료'));
    end if;
    if not exists (
        select 1 from pg_constraint
        where conname = 'kra_keyword_requests_admin_reply_length_check'
          and conrelid = 'public.kra_keyword_requests'::regclass
    ) then
        alter table public.kra_keyword_requests
            add constraint kra_keyword_requests_admin_reply_length_check
            check (char_length(admin_reply) <= 4000);
    end if;
end $$;

create index if not exists kra_keyword_requests_owner_created_idx
    on public.kra_keyword_requests (requester_id, created_at desc);
create index if not exists kra_keyword_requests_created_idx
    on public.kra_keyword_requests (created_at desc);

create table if not exists public.kra_keyword_request_config (
    id text primary key default 'singleton' check (id = 'singleton'),
    email_notifications_enabled boolean not null default false
);
insert into public.kra_keyword_request_config(id, email_notifications_enabled)
values ('singleton', false)
on conflict (id) do nothing;

alter table public.kra_keyword_requests enable row level security;
alter table public.kra_keyword_request_config enable row level security;

revoke all on public.kra_keyword_requests, public.kra_keyword_request_config
    from anon, authenticated;
grant select on public.kra_keyword_requests to authenticated;
grant insert (requester_id, requester_email, kwd_no, keyword_name,
              request_type, request_detail)
    on public.kra_keyword_requests to authenticated;
grant update (status, admin_reply)
    on public.kra_keyword_requests to authenticated;
grant delete on public.kra_keyword_requests to authenticated;
grant select on public.kra_keyword_request_config to authenticated;
grant update (email_notifications_enabled)
    on public.kra_keyword_request_config to authenticated;

drop policy if exists kra_keyword_requests_read_owner_or_admin
    on public.kra_keyword_requests;
create policy kra_keyword_requests_read_owner_or_admin
    on public.kra_keyword_requests for select to authenticated
    using (
        requester_id = (select auth.uid())
        or (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
    );

drop policy if exists kra_keyword_requests_insert_own
    on public.kra_keyword_requests;
create policy kra_keyword_requests_insert_own
    on public.kra_keyword_requests for insert to authenticated
    with check (
        requester_id = (select auth.uid())
        and lower(requester_email) = lower((select auth.jwt() ->> 'email'))
    );

drop policy if exists kra_keyword_requests_update_admin
    on public.kra_keyword_requests;
create policy kra_keyword_requests_update_admin
    on public.kra_keyword_requests for update to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin')
    with check ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');

drop policy if exists kra_keyword_requests_delete_admin
    on public.kra_keyword_requests;
create policy kra_keyword_requests_delete_admin
    on public.kra_keyword_requests for delete to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');

drop policy if exists kra_keyword_request_config_admin_read
    on public.kra_keyword_request_config;
create policy kra_keyword_request_config_admin_read
    on public.kra_keyword_request_config for select to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');

drop policy if exists kra_keyword_request_config_admin_update
    on public.kra_keyword_request_config;
create policy kra_keyword_request_config_admin_update
    on public.kra_keyword_request_config for update to authenticated
    using ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin')
    with check ((select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');
