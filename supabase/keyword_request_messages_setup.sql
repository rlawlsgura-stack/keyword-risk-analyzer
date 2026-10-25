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
    );
