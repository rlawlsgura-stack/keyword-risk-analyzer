-- Avoid RLS recursion when validating an administrator reply target.
-- The helper is private, callable only by authenticated users, and returns true
-- only for administrators selecting an unanswered user inquiry.

create schema if not exists private;
revoke all on schema private from public;
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
    select coalesce(
        (select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin',
        false
    )
    and exists (
        select 1
        from public.kra_keyword_request_messages inquiry
        where inquiry.id = p_inquiry_id
          and inquiry.request_id = p_request_id
          and inquiry.author_role = 'user'
          and inquiry.reply_to_id is null
          and not exists (
              select 1
              from public.kra_keyword_request_messages response
              where response.reply_to_id = inquiry.id
          )
    );
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
