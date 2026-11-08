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
