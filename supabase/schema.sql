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
    kwd_no text not null,
    keyword_name text not null check (length(btrim(keyword_name)) > 0),
    request_type text not null check (request_type in (
        'risk_grade_adjustment', 'review_criteria_change', 'new_keyword_registration'
    )),
    request_detail text not null default '' check (char_length(request_detail) <= 4000),
    status text not null default '대기',
    admin_reply text not null default '',
    created_at timestamptz not null default now()
);

alter table public.kra_keyword_requests
    drop constraint if exists kra_keyword_requests_request_type_check;
alter table public.kra_keyword_requests
    add constraint kra_keyword_requests_request_type_check
    check (request_type in (
        'risk_grade_adjustment', 'review_criteria_change', 'new_keyword_registration'
    ));
alter table public.kra_keyword_requests
    drop constraint if exists kra_keyword_requests_kwd_no_check;
alter table public.kra_keyword_requests
    add constraint kra_keyword_requests_kwd_no_check
    check (
        request_type = 'new_keyword_registration'
        or length(btrim(kwd_no)) > 0
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
-- Add an append-only conversation history for existing keyword requests.
-- Safe to run repeatedly on an existing project.

create table if not exists public.kra_keyword_request_messages (
    id uuid primary key default gen_random_uuid(),
    request_id uuid not null references public.kra_keyword_requests(id) on delete cascade,
    author_id uuid not null references auth.users(id),
    author_email text not null check (length(btrim(author_email)) > 0),
    body text not null check (char_length(btrim(body)) between 1 and 4000),
    created_at timestamptz not null default now()
);

create index if not exists kra_keyword_request_messages_request_created_idx
    on public.kra_keyword_request_messages (request_id, created_at, id);

alter table public.kra_keyword_request_messages enable row level security;
revoke all on public.kra_keyword_request_messages from anon, authenticated;
grant select, insert on public.kra_keyword_request_messages to authenticated;

drop policy if exists kra_keyword_request_messages_read_owner_or_admin
    on public.kra_keyword_request_messages;
create policy kra_keyword_request_messages_read_owner_or_admin
    on public.kra_keyword_request_messages for select to authenticated
    using (
        exists (
            select 1
            from public.kra_keyword_requests r
            where r.id = kra_keyword_request_messages.request_id
              and (
                  r.requester_id = (select auth.uid())
                  or (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
              )
        )
    );

drop policy if exists kra_keyword_request_messages_insert_owner_or_admin
    on public.kra_keyword_request_messages;
create policy kra_keyword_request_messages_insert_owner_or_admin
    on public.kra_keyword_request_messages for insert to authenticated
    with check (
        author_id = (select auth.uid())
        and lower(author_email) = lower((select auth.jwt() ->> 'email'))
        and exists (
            select 1
            from public.kra_keyword_requests r
            where r.id = kra_keyword_request_messages.request_id
              and (
                  r.requester_id = (select auth.uid())
                  or (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
              )
        )
    );\n\n\n-- Bind each administrator reply to exactly one user inquiry message.
-- Safe to run repeatedly on a project with the message-history table installed.

alter table public.kra_keyword_request_messages
    add column if not exists author_role text not null default 'user';
alter table public.kra_keyword_request_messages
    add column if not exists is_initial boolean not null default false;
alter table public.kra_keyword_request_messages
    add column if not exists reply_to_id uuid;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'kra_keyword_request_messages_author_role_check'
          and conrelid = 'public.kra_keyword_request_messages'::regclass
    ) then
        alter table public.kra_keyword_request_messages
            add constraint kra_keyword_request_messages_author_role_check
            check (author_role in ('user', 'admin'));
    end if;
    if not exists (
        select 1 from pg_constraint
        where conname = 'kra_keyword_request_messages_reply_to_fkey'
          and conrelid = 'public.kra_keyword_request_messages'::regclass
    ) then
        alter table public.kra_keyword_request_messages
            add constraint kra_keyword_request_messages_reply_to_fkey
            foreign key (reply_to_id)
            references public.kra_keyword_request_messages(id) on delete cascade;
    end if;
end $$;

update public.kra_keyword_request_messages m
set author_role = 'admin'
from public.kra_keyword_requests r
where r.id = m.request_id
  and m.author_role = 'user'
  and m.author_id <> r.requester_id;

create unique index if not exists kra_keyword_request_messages_one_reply_per_inquiry_idx
    on public.kra_keyword_request_messages (reply_to_id)
    where reply_to_id is not null;
create unique index if not exists kra_keyword_request_messages_one_initial_per_request_idx
    on public.kra_keyword_request_messages (request_id)
    where is_initial;

insert into public.kra_keyword_request_messages
    (request_id, author_id, author_email, body, created_at, author_role, is_initial)
select r.id, r.requester_id, r.requester_email,
       coalesce(nullif(btrim(r.request_detail), ''), '최초 문의 등록'),
       r.created_at, 'user', true
from public.kra_keyword_requests r
where not exists (
    select 1 from public.kra_keyword_request_messages m
    where m.request_id = r.id and m.is_initial
);

-- Pair any existing admin messages with the nearest earlier unanswered user message.
do $$
declare
    admin_message record;
    inquiry_message_id uuid;
begin
    for admin_message in
        select id, request_id, created_at
        from public.kra_keyword_request_messages
        where author_role = 'admin' and reply_to_id is null
        order by created_at, id
    loop
        select u.id into inquiry_message_id
        from public.kra_keyword_request_messages u
        where u.request_id = admin_message.request_id
          and u.author_role = 'user'
          and u.reply_to_id is null
          and u.created_at <= admin_message.created_at
          and not exists (
              select 1 from public.kra_keyword_request_messages a
              where a.reply_to_id = u.id
          )
        order by u.created_at desc, u.id desc
        limit 1;

        if inquiry_message_id is not null then
            update public.kra_keyword_request_messages
            set reply_to_id = inquiry_message_id
            where id = admin_message.id;
        end if;
        inquiry_message_id := null;
    end loop;
end $$;

drop policy if exists kra_keyword_request_messages_insert_owner_or_admin
    on public.kra_keyword_request_messages;
create policy kra_keyword_request_messages_insert_owner_or_admin
    on public.kra_keyword_request_messages for insert to authenticated
    with check (
        author_id = (select auth.uid())
        and lower(author_email) = lower((select auth.jwt() ->> 'email'))
        and (
            (
                author_role = 'user'
                and reply_to_id is null
                and exists (
                    select 1 from public.kra_keyword_requests r
                    where r.id = kra_keyword_request_messages.request_id
                      and r.requester_id = (select auth.uid())
                )
            )
            or
            (
                author_role = 'admin'
                and reply_to_id is not null
                and (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
                and (select private.kra_can_reply_to_keyword_inquiry(
                    kra_keyword_request_messages.request_id,
                    kra_keyword_request_messages.reply_to_id
                ))
            )
        )
    );

-- Latest conversation follow-up and legacy answer migration.
-- Allow a requester to continue the same numbered inquiry after an admin reply.
-- Safe to apply repeatedly after the request message history setup.

alter table public.kra_keyword_request_messages
    alter column author_id drop not null;

alter table public.kra_keyword_request_messages
    add column if not exists is_legacy boolean not null default false;

create unique index if not exists kra_keyword_request_messages_one_reply_per_inquiry_idx
    on public.kra_keyword_request_messages (reply_to_id)
    where reply_to_id is not null;

-- Preserve answers stored in the original request row as replyable history entries.
-- The old column did not store an author or timestamp, so the UI labels these as legacy.
insert into public.kra_keyword_request_messages
    (request_id, author_id, author_email, body, created_at, author_role,
     is_initial, is_legacy, reply_to_id)
select r.id, null, 'legacy-admin', btrim(r.admin_reply), r.created_at,
       'admin', false, true, initial.id
from public.kra_keyword_requests r
join public.kra_keyword_request_messages initial
  on initial.request_id = r.id
 and initial.author_role = 'user'
 and initial.is_initial
where nullif(btrim(r.admin_reply), '') is not null
  and not exists (
      select 1
      from public.kra_keyword_request_messages response
      where response.reply_to_id = initial.id
  );

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

create or replace function private.kra_can_reply_to_keyword_inquiry(
    p_request_id uuid,
    p_inquiry_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
    select case
        when (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin' then
            exists (
                select 1
                from public.kra_keyword_request_messages parent
                where parent.id = p_inquiry_id
                  and parent.request_id = p_request_id
                  and parent.author_role = 'user'
                  and not exists (
                      select 1
                      from public.kra_keyword_request_messages response
                      where response.reply_to_id = parent.id
                  )
            )
        else
            exists (
                select 1
                from public.kra_keyword_requests r
                join public.kra_keyword_request_messages parent
                  on parent.request_id = r.id
                where r.id = p_request_id
                  and r.requester_id = (select auth.uid())
                  and parent.id = p_inquiry_id
                  and parent.author_role = 'admin'
                  and not exists (
                      select 1
                      from public.kra_keyword_request_messages response
                      where response.reply_to_id = parent.id
                  )
            )
    end;
$function$;

revoke all on function private.kra_can_reply_to_keyword_inquiry(uuid, uuid)
    from public, anon, authenticated;
grant execute on function private.kra_can_reply_to_keyword_inquiry(uuid, uuid)
    to authenticated;

drop policy if exists kra_keyword_request_messages_insert_owner_or_admin
    on public.kra_keyword_request_messages;
create policy kra_keyword_request_messages_insert_owner_or_admin
    on public.kra_keyword_request_messages for insert to authenticated
    with check (
        author_id = (select auth.uid())
        and lower(author_email) = lower((select auth.jwt() ->> 'email'))
        and (
            (
                author_role = 'user'
                and (
                    (reply_to_id is null and exists (
                        select 1
                        from public.kra_keyword_requests r
                        where r.id = kra_keyword_request_messages.request_id
                          and r.requester_id = (select auth.uid())
                    ))
                    or
                    (reply_to_id is not null and (select
                        private.kra_can_reply_to_keyword_inquiry(
                            kra_keyword_request_messages.request_id,
                            kra_keyword_request_messages.reply_to_id
                        )
                    ))
                )
            )
            or
            (
                author_role = 'admin'
                and reply_to_id is not null
                and (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
                and (select private.kra_can_reply_to_keyword_inquiry(
                    kra_keyword_request_messages.request_id,
                    kra_keyword_request_messages.reply_to_id
                ))
            )
        )
    );

-- Per-inquiry status and atomic administrator feedback workflow.
-- Save an administrator reply and the selected inquiry's status as one unit.
-- Apply after keyword_request_user_followup_setup.sql.

do $migration$
begin
    if not exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'kra_keyword_request_messages'
          and column_name = 'status'
    ) then
        alter table public.kra_keyword_request_messages
            add column status text not null default '대기';

        -- Carry the previous request-wide status into its original question once.
        update public.kra_keyword_request_messages m
        set status = r.status
        from public.kra_keyword_requests r
        where r.id = m.request_id
          and m.author_role = 'user'
          and m.is_initial
          and r.status in ('대기', '검토중', '처리완료');
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'kra_keyword_request_messages_status_check'
          and conrelid = 'public.kra_keyword_request_messages'::regclass
    ) then
        alter table public.kra_keyword_request_messages
            add constraint kra_keyword_request_messages_status_check
            check (status in ('대기', '검토중', '처리완료'));
    end if;
end
$migration$;

grant update (status) on public.kra_keyword_request_messages to authenticated;

drop policy if exists kra_keyword_request_messages_update_admin_status
    on public.kra_keyword_request_messages;
create policy kra_keyword_request_messages_update_admin_status
    on public.kra_keyword_request_messages for update to authenticated
    using (
        (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
        and author_role = 'user'
    )
    with check (
        (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
        and author_role = 'user'
        and status in ('대기', '검토중', '처리완료')
    );

create or replace function public.kra_admin_respond_to_keyword_inquiry(
    p_request_id uuid,
    p_inquiry_id uuid,
    p_body text,
    p_status text
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $function$
declare
    v_reply_id uuid;
    v_body text := btrim(p_body);
begin
    if (select auth.jwt() -> 'app_metadata' ->> 'role') is distinct from 'admin'
       or (select auth.uid()) is null then
        raise exception 'administrator access required' using errcode = '42501';
    end if;
    if v_body is null or char_length(v_body) not between 1 and 4000 then
        raise exception 'feedback must contain 1 to 4000 characters' using errcode = '22023';
    end if;
    if p_status is null or p_status not in ('대기', '검토중', '처리완료') then
        raise exception 'invalid inquiry status' using errcode = '22023';
    end if;

    update public.kra_keyword_request_messages
    set status = p_status
    where id = p_inquiry_id
      and request_id = p_request_id
      and author_role = 'user';
    if not found then
        raise exception 'inquiry was not found or is not editable' using errcode = 'P0002';
    end if;

    update public.kra_keyword_requests
    set status = p_status, admin_reply = v_body
    where id = p_request_id;
    if not found then
        raise exception 'request was not found' using errcode = 'P0002';
    end if;

    insert into public.kra_keyword_request_messages
        (request_id, author_id, author_email, author_role, reply_to_id, body)
    values (
        p_request_id,
        (select auth.uid()),
        (select auth.jwt() ->> 'email'),
        'admin',
        p_inquiry_id,
        v_body
    )
    returning id into v_reply_id;

    return v_reply_id;
end;
$function$;

revoke all on function public.kra_admin_respond_to_keyword_inquiry(uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.kra_admin_respond_to_keyword_inquiry(uuid, uuid, text, text)
    to authenticated;

-- Additive Kiwi unmatched-term aggregation. No source text is stored.
create table public.kra_unmatched_term_candidates (
    term_norm text primary key check (char_length(btrim(term_norm)) between 1 and 100),
    display_term text not null check (char_length(btrim(display_term)) between 1 and 150),
    total_occurrences bigint not null default 0 check (total_occurrences >= 0),
    analysis_count bigint not null default 0 check (analysis_count >= 0),
    first_seen timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    review_status text not null default 'pending'
        check (review_status in ('pending', 'approved', 'ignored'))
);

create table public.kra_unmatched_term_observations (
    analysis_id uuid not null,
    term_norm text not null,
    occurrences integer not null check (occurrences between 1 and 10000),
    created_at timestamptz not null default now(),
    primary key (analysis_id, term_norm)
);
create index kra_unmatched_candidates_frequency_idx
    on public.kra_unmatched_term_candidates(total_occurrences desc, analysis_count desc);

alter table public.kra_unmatched_term_candidates enable row level security;
alter table public.kra_unmatched_term_observations enable row level security;
revoke all on public.kra_unmatched_term_candidates,
    public.kra_unmatched_term_observations from public, anon, authenticated;
grant all on public.kra_unmatched_term_candidates,
    public.kra_unmatched_term_observations to service_role;

create function public.kra_collect_unmatched_terms(p_id uuid, p_terms jsonb)
returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    if p_id is null or p_terms is null or jsonb_typeof(p_terms) <> 'array'
       or jsonb_array_length(p_terms) > 1000 then
        raise exception 'Invalid unmatched-term payload' using errcode = '22023';
    end if;
    if exists (
        select 1 from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        where item.term_norm is null or char_length(btrim(item.term_norm)) not between 1 and 100
           or item.display_term is null or char_length(btrim(item.display_term)) not between 1 and 150
           or item.occurrences is null or item.occurrences not between 1 and 10000
    ) then
        raise exception 'Invalid unmatched-term item' using errcode = '22023';
    end if;

    with inserted as (
        insert into public.kra_unmatched_term_observations(analysis_id, term_norm, occurrences)
        select p_id, item.term_norm, item.occurrences
        from (
            select term_norm, min(display_term) as display_term,
                   sum(occurrences)::integer as occurrences
            from jsonb_to_recordset(p_terms)
                as source(term_norm text, display_term text, occurrences integer)
            group by term_norm
        ) item
        on conflict (analysis_id, term_norm) do nothing
        returning term_norm, occurrences, created_at
    ), grouped as (
        select term_norm, sum(occurrences)::bigint as total_occurrences,
               count(*)::bigint as analysis_count, min(created_at) as first_seen,
               max(created_at) as last_seen
        from inserted group by term_norm
    ), upserted as (
        insert into public.kra_unmatched_term_candidates as candidate
            (term_norm, display_term, total_occurrences, analysis_count, first_seen, last_seen)
        select grouped.term_norm,
               min(item.display_term), grouped.total_occurrences, grouped.analysis_count,
               grouped.first_seen, grouped.last_seen
        from grouped
        join jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
          on item.term_norm = grouped.term_norm
        group by grouped.term_norm, grouped.total_occurrences, grouped.analysis_count,
                 grouped.first_seen, grouped.last_seen
        on conflict (term_norm) do update set
            total_occurrences = candidate.total_occurrences + excluded.total_occurrences,
            analysis_count = candidate.analysis_count + excluded.analysis_count,
            first_seen = least(candidate.first_seen, excluded.first_seen),
            last_seen = greatest(candidate.last_seen, excluded.last_seen)
        returning 1
    )
    select count(*)::integer into v_count from upserted;
    return coalesce(v_count, 0);
end;
$$;

create function public.kra_unmatched_term_candidates(p_status text default null,
                                                       p_limit integer default 500)
returns jsonb
language plpgsql stable security invoker set search_path = '' as $$
begin
    if p_status is not null and p_status not in ('pending', 'approved', 'ignored') then
        raise exception 'Invalid review status' using errcode = '22023';
    end if;
    return coalesce((
        select jsonb_agg(to_jsonb(candidate)
                         order by candidate.total_occurrences desc,
                                  candidate.analysis_count desc, candidate.term_norm)
        from (
            select term_norm, display_term, total_occurrences, analysis_count,
                   first_seen, last_seen, review_status
            from public.kra_unmatched_term_candidates
            where p_status is null or review_status = p_status
            order by total_occurrences desc, analysis_count desc, term_norm
            limit least(greatest(coalesce(p_limit, 500), 1), 1000)
        ) candidate
    ), '[]'::jsonb);
end;
$$;

create function public.kra_set_unmatched_term_status(p_term_norm text, p_status text)
returns boolean
language plpgsql security invoker set search_path = '' as $$
begin
    if p_status not in ('pending', 'approved', 'ignored') then
        raise exception 'Invalid review status' using errcode = '22023';
    end if;
    update public.kra_unmatched_term_candidates
       set review_status = p_status
     where term_norm = p_term_norm;
    return found;
end;
$$;

revoke all on function public.kra_collect_unmatched_terms(uuid, jsonb) from public, anon, authenticated;
revoke all on function public.kra_unmatched_term_candidates(text, integer) from public, anon, authenticated;
revoke all on function public.kra_set_unmatched_term_status(text, text) from public, anon, authenticated;
grant execute on function public.kra_collect_unmatched_terms(uuid, jsonb) to service_role;
grant execute on function public.kra_unmatched_term_candidates(text, integer) to service_role;
grant execute on function public.kra_set_unmatched_term_status(text, text) to service_role;


-- Persistent shared unmatched collection (FIXED291.4).
-- Run after unmatched_term_pool_setup.sql. No account, source text or image is stored.
create table public.kra_unmatched_collection_events (
    analysis_id uuid primary key,
    created_at timestamptz not null default now()
);
alter table public.kra_unmatched_collection_events enable row level security;
revoke all on public.kra_unmatched_collection_events from public, anon, authenticated;
grant select, insert on public.kra_unmatched_collection_events to service_role;
revoke update, delete, truncate, references, trigger on public.kra_unmatched_collection_events from service_role;
insert into public.kra_unmatched_collection_events(analysis_id)
    select distinct analysis_id from public.kra_unmatched_term_observations
    on conflict do nothing;

create or replace function public.kra_collect_unmatched_terms(p_id uuid, p_terms jsonb)
returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    if p_id is null or p_terms is null or jsonb_typeof(p_terms) <> 'array'
       or jsonb_array_length(p_terms) > 50000 then
        raise exception 'Invalid unmatched-term payload' using errcode = '22023';
    end if;
    if exists (
        select 1 from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        where item.term_norm is null or char_length(btrim(item.term_norm)) not between 1 and 100
           or item.display_term is null or char_length(btrim(item.display_term)) not between 1 and 150
           or item.occurrences is null or item.occurrences not between 1 and 1000000000
    ) then
        raise exception 'Invalid unmatched-term item' using errcode = '22023';
    end if;

    -- ponytail: serialize pool writes/deletes; use per-term locks if throughput requires it.
    perform pg_catalog.pg_advisory_xact_lock(193728174, 1);
    insert into public.kra_unmatched_collection_events(analysis_id) values (p_id)
        on conflict do nothing;
    get diagnostics v_count = row_count;
    if v_count = 0 then return 0; end if;

    insert into public.kra_unmatched_term_observations(analysis_id, term_norm, occurrences)
        select p_id, term_norm, sum(occurrences)::integer
        from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        group by term_norm;

    insert into public.kra_unmatched_term_candidates as candidate
        (term_norm, display_term, total_occurrences, analysis_count)
        select term_norm, min(display_term), sum(occurrences)::bigint, 1
        from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        group by term_norm order by term_norm
        on conflict (term_norm) do update set
            total_occurrences = candidate.total_occurrences + excluded.total_occurrences,
            analysis_count = candidate.analysis_count + 1,
            last_seen = greatest(candidate.last_seen, excluded.last_seen);
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

create function public.kra_unmatched_term_page(
    p_offset integer default 0, p_limit integer default 100, p_search text default '')
returns jsonb
language sql stable security invoker set search_path = '' as $$
    with filtered as (
        select term_norm, display_term, total_occurrences, analysis_count,
               first_seen, last_seen, review_status
        from public.kra_unmatched_term_candidates
        where coalesce(p_search, '') = ''
           or term_norm ilike '%' || p_search || '%'
           or display_term ilike '%' || p_search || '%'
    )
    select jsonb_build_object(
        'total', (select count(*) from filtered),
        'rows', coalesce((select jsonb_agg(to_jsonb(page)
                    order by page.total_occurrences desc, page.analysis_count desc, page.term_norm)
            from (select * from filtered
                  order by total_occurrences desc, analysis_count desc, term_norm
                  limit least(greatest(coalesce(p_limit, 100), 1), 1000)
                  offset greatest(coalesce(p_offset, 0), 0)) page), '[]'::jsonb));
$$;

create function public.kra_unmatched_term_export()
returns jsonb
language sql stable security invoker set search_path = '' as $$
    select coalesce(jsonb_agg(jsonb_build_object(
        'term_norm', term_norm, 'display_term', display_term,
        'total_occurrences', total_occurrences, 'analysis_count', analysis_count,
        'first_seen', first_seen, 'last_seen', last_seen)
        order by total_occurrences desc, analysis_count desc, term_norm), '[]'::jsonb)
    from public.kra_unmatched_term_candidates;
$$;

-- Called only by the server after validating the current administrator's token.
create function public.kra_delete_unmatched_terms(p_terms text[])
returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    if p_terms is null or coalesce(array_length(p_terms, 1), 0) not between 1 and 1000
       or exists (select 1 from unnest(p_terms) term
                  where term is null or char_length(btrim(term)) not between 1 and 100) then
        raise exception 'Invalid unmatched-term selection' using errcode = '22023';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(193728174, 1);
    delete from public.kra_unmatched_term_observations where term_norm = any(p_terms);
    delete from public.kra_unmatched_term_candidates where term_norm = any(p_terms);
    get diagnostics v_count = row_count;
    -- Keep anonymous event IDs: an old save retry must not recreate deleted terms.
    return v_count;
end;
$$;

revoke all on function public.kra_collect_unmatched_terms(uuid, jsonb) from public, anon, authenticated;
revoke all on function public.kra_unmatched_term_page(integer, integer, text) from public, anon, authenticated;
revoke all on function public.kra_unmatched_term_export() from public, anon, authenticated;
revoke all on function public.kra_delete_unmatched_terms(text[]) from public, anon, authenticated;
grant execute on function public.kra_collect_unmatched_terms(uuid, jsonb) to service_role;
grant execute on function public.kra_unmatched_term_page(integer, integer, text) to service_role;
grant execute on function public.kra_unmatched_term_export() to service_role;
grant execute on function public.kra_delete_unmatched_terms(text[]) to service_role;

-- Apply after keyword_request_feedback_status_setup.sql. Safe to run again.
-- Keep direct UPDATE privileges administrator-only. The private operation below
-- grants only an owner's content edit and atomically updates its initial message.

create or replace function private.kra_edit_own_keyword_request(
    p_request_id uuid,
    p_request_type text,
    p_request_detail text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
    v_user_id uuid := (select auth.uid());
    v_detail text := btrim(coalesce(p_request_detail, ''));
    v_request public.kra_keyword_requests%rowtype;
begin
    if v_user_id is null then
        raise exception 'authentication required' using errcode = '42501';
    end if;
    if p_request_type is null or p_request_type not in (
        'risk_grade_adjustment', 'review_criteria_change', 'new_keyword_registration'
    ) or char_length(v_detail) > 4000 then
        raise exception 'invalid request content' using errcode = '22023';
    end if;

    update public.kra_keyword_requests
    set request_type = p_request_type, request_detail = v_detail
    where id = p_request_id and requester_id = v_user_id
    returning * into v_request;
    if not found then
        raise exception 'own request not found' using errcode = '42501';
    end if;

    insert into public.kra_keyword_request_messages as initial
        (request_id, author_id, author_email, author_role, is_initial,
         body, status, created_at)
    values (
        v_request.id, v_user_id, v_request.requester_email, 'user', true,
        coalesce(nullif(v_detail, ''), '최초 문의 등록'),
        v_request.status, v_request.created_at
    )
    on conflict (request_id) where is_initial
    do update set body = excluded.body
    where initial.author_id = v_user_id and initial.author_role = 'user';
    if not found then
        raise exception 'initial inquiry owner mismatch' using errcode = '42501';
    end if;

    return to_jsonb(v_request);
end;
$function$;

revoke all on function private.kra_edit_own_keyword_request(uuid, text, text)
    from public, anon, authenticated;
grant execute on function private.kra_edit_own_keyword_request(uuid, text, text)
    to authenticated;

create or replace function public.kra_edit_own_keyword_request(
    p_request_id uuid,
    p_request_type text,
    p_request_detail text
)
returns jsonb
language sql
security invoker
set search_path = ''
as $function$
    select private.kra_edit_own_keyword_request(
        p_request_id, p_request_type, p_request_detail
    );
$function$;

revoke all on function public.kra_edit_own_keyword_request(uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.kra_edit_own_keyword_request(uuid, text, text)
    to authenticated;

drop policy if exists kra_keyword_requests_delete_owner
    on public.kra_keyword_requests;
create policy kra_keyword_requests_delete_owner
    on public.kra_keyword_requests for delete to authenticated
    using (requester_id = (select auth.uid()));

-- Apply after keyword_request_owner_edit_setup.sql. Safe to run again.
-- Only the author can edit/delete an inquiry in a request they own.
create or replace function private.kra_mutate_own_keyword_inquiry(
    p_request_id uuid,
    p_inquiry_id uuid,
    p_action text,
    p_body text default null,
    p_request_type text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
    v_user_id uuid := (select auth.uid());
    v_body text := btrim(coalesce(p_body, ''));
    v_inquiry public.kra_keyword_request_messages%rowtype;
    v_latest_reply_id uuid;
    v_reply text;
    v_status text;
begin
    if v_user_id is null then
        raise exception 'authentication required' using errcode = '42501';
    end if;
    if p_action is null or p_action not in ('edit', 'delete') then
        raise exception 'invalid inquiry action' using errcode = '22023';
    end if;
    perform 1 from public.kra_keyword_requests
    where id = p_request_id and requester_id = v_user_id for update;
    if not found then
        raise exception 'own request not found' using errcode = '42501';
    end if;
    select * into v_inquiry from public.kra_keyword_request_messages
    where id = p_inquiry_id and request_id = p_request_id
      and author_id = v_user_id and author_role = 'user'
    for update;
    if not found then
        raise exception 'own inquiry not found' using errcode = '42501';
    end if;

    if p_action = 'edit' then
        if char_length(v_body) > 4000 or (v_body = '' and not v_inquiry.is_initial)
           or (p_request_type is not null and (
               not v_inquiry.is_initial or p_request_type not in (
                   'risk_grade_adjustment', 'review_criteria_change', 'new_keyword_registration'
               )
           )) then
            raise exception 'invalid inquiry content' using errcode = '22023';
        end if;
        if v_inquiry.is_initial then
            update public.kra_keyword_requests
            set request_detail = v_body, request_type = coalesce(p_request_type, request_type)
            where id = p_request_id;
        end if;
        update public.kra_keyword_request_messages
        set body = coalesce(nullif(v_body, ''), '최초 문의 등록')
        where id = p_inquiry_id;
    else
        select id into v_latest_reply_id from public.kra_keyword_request_messages
        where request_id = p_request_id and author_role = 'admin'
        order by created_at desc, id desc limit 1;

        -- The reply_to_id FK cascades only down this inquiry's reply chain.
        delete from public.kra_keyword_request_messages where id = p_inquiry_id;
        if v_inquiry.is_initial then
            update public.kra_keyword_requests set request_detail = '' where id = p_request_id;
        end if;
        if (v_latest_reply_id is not null and not exists (
                select 1 from public.kra_keyword_request_messages where id = v_latest_reply_id
            )) or (v_inquiry.is_initial and v_latest_reply_id is null) then
            select answer.body, inquiry.status into v_reply, v_status
            from public.kra_keyword_request_messages answer
            left join public.kra_keyword_request_messages inquiry on inquiry.id = answer.reply_to_id
            where answer.request_id = p_request_id and answer.author_role = 'admin'
            order by answer.created_at desc, answer.id desc limit 1;
            update public.kra_keyword_requests
            set admin_reply = coalesce(v_reply, ''), status = coalesce(v_status, '대기')
            where id = p_request_id;
        end if;
    end if;
    return jsonb_build_object('id', p_inquiry_id, 'action', p_action);
end;
$function$;

revoke all on function private.kra_mutate_own_keyword_inquiry(uuid, uuid, text, text, text)
    from public, anon, authenticated;
grant execute on function private.kra_mutate_own_keyword_inquiry(uuid, uuid, text, text, text)
    to authenticated;

create or replace function public.kra_mutate_own_keyword_inquiry(
    p_request_id uuid,
    p_inquiry_id uuid,
    p_action text,
    p_body text default null,
    p_request_type text default null
)
returns jsonb
language sql
security invoker
set search_path = ''
as $function$
    select private.kra_mutate_own_keyword_inquiry(
        p_request_id, p_inquiry_id, p_action, p_body, p_request_type
    );
$function$;

revoke all on function public.kra_mutate_own_keyword_inquiry(uuid, uuid, text, text, text)
    from public, anon, authenticated;
grant execute on function public.kra_mutate_own_keyword_inquiry(uuid, uuid, text, text, text)
    to authenticated;

-- Every new request must have its original inquiry represented in the same
-- conversation table as Q02/Q03. The caller's existing insert RLS still applies.
create or replace function private.kra_seed_keyword_request_inquiry()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
    insert into public.kra_keyword_request_messages
        (request_id, author_id, author_email, author_role, is_initial, body, status, created_at)
    values (
        new.id, new.requester_id, new.requester_email, 'user', true,
        coalesce(nullif(btrim(new.request_detail), ''), '최초 문의 등록'), new.status, new.created_at
    );
    return new;
end;
$function$;
revoke all on function private.kra_seed_keyword_request_inquiry() from public, anon, authenticated;

drop trigger if exists kra_keyword_requests_initial_inquiry on public.kra_keyword_requests;
create trigger kra_keyword_requests_initial_inquiry
    after insert on public.kra_keyword_requests
    for each row execute function private.kra_seed_keyword_request_inquiry();

-- Preserve existing message bodies. A deleted initial inquiry clears request_detail,
-- so rerunning setup must not recreate it.
insert into public.kra_keyword_request_messages
    (request_id, author_id, author_email, author_role, is_initial, body, status, created_at)
select r.id, u.id, r.requester_email, 'user', true,
       coalesce(nullif(btrim(r.request_detail), ''), '최초 문의 등록'), r.status, r.created_at
from public.kra_keyword_requests r
left join auth.users u on u.id = r.requester_id
where btrim(r.request_detail) <> '' and not exists (
    select 1 from public.kra_keyword_request_messages m where m.request_id = r.id and m.is_initial
);
