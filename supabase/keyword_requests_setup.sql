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
    created_at timestamptz not null default now()
);

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
