-- Run after keyword_inquiry_status_after_feedback. All fixture rows are rolled back.
begin;
create temporary table inquiry_status_fixture as
select id as owner_id, gen_random_uuid() as request_id,
       gen_random_uuid() as unanswered_id
from auth.users limit 1;
grant select on inquiry_status_fixture to authenticated;

insert into public.kra_keyword_requests
    (id, requester_id, requester_email, kwd_no, keyword_name,
     request_type, request_detail)
select request_id, owner_id, 'status-test@example.invalid', '',
       'status test', 'new_keyword_registration', 'initial question'
from inquiry_status_fixture;

-- The initial question has one administrator answer but remains pending.
insert into public.kra_keyword_request_messages
    (request_id, author_id, author_email, author_role, reply_to_id, body)
select f.request_id, f.owner_id, 'status-test@example.invalid', 'admin',
       m.id, 'saved feedback'
from inquiry_status_fixture f
join public.kra_keyword_request_messages m
  on m.request_id = f.request_id and m.is_initial;

insert into public.kra_keyword_request_messages
    (id, request_id, author_id, author_email, author_role, body)
select unanswered_id, request_id, owner_id, 'status-test@example.invalid',
       'user', 'follow-up question'
from inquiry_status_fixture;

select set_config('request.jwt.claims', jsonb_build_object(
    'sub', owner_id, 'role', 'authenticated', 'email', 'status-test@example.invalid',
    'app_metadata', jsonb_build_object('role', 'admin'))::text, true)
from inquiry_status_fixture;
set local role authenticated;

do $$
declare
    v_request uuid;
    v_initial uuid;
    v_unanswered uuid;
    v_status text;
begin
    select request_id, unanswered_id into v_request, v_unanswered
    from inquiry_status_fixture;
    select id into v_initial from public.kra_keyword_request_messages
    where request_id = v_request and is_initial;

    perform public.kra_admin_set_keyword_inquiry_status(
        v_request, v_initial, '처리완료');
    select status into v_status from public.kra_keyword_request_overview
    where id = v_request;
    if v_status <> '대기' then
        raise exception 'An unanswered follow-up must keep the request pending';
    end if;

    begin
        perform public.kra_admin_set_keyword_inquiry_status(
            v_request, v_unanswered, '처리완료');
        raise exception 'Unanswered inquiry was closed';
    exception when sqlstate '22023' then
        null;
    end;

    if (select count(*) from public.kra_keyword_request_messages
        where request_id = v_request and author_role = 'admin') <> 1 then
        raise exception 'Changing status created another feedback message';
    end if;

    insert into public.kra_keyword_request_messages
        (request_id, author_id, author_email, author_role, reply_to_id, body)
    values (v_request, (select owner_id from inquiry_status_fixture),
            'status-test@example.invalid', 'admin', v_unanswered, 'follow-up answer');
    perform public.kra_admin_set_keyword_inquiry_status(
        v_request, v_unanswered, '처리완료');
    if (select status from public.kra_keyword_request_overview where id = v_request)
       <> '처리완료' or
       (select status from public.kra_keyword_requests where id = v_request)
       <> '처리완료' then
        raise exception 'All answered inquiries did not complete the request';
    end if;

    select set_config('request.jwt.claims', jsonb_build_object(
        'sub', (select owner_id from inquiry_status_fixture),
        'role', 'authenticated', 'app_metadata', jsonb_build_object('role', 'member'))::text,
        true) into v_status;
    begin
        perform public.kra_admin_set_keyword_inquiry_status(
            v_request, v_initial, '대기');
        raise exception 'Member changed an inquiry status';
    exception when insufficient_privilege then
        null;
    end;
end;
$$;
rollback;
