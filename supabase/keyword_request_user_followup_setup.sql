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
