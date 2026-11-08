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
