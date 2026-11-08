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
