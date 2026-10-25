-- Bind each administrator reply to exactly one user inquiry message.
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