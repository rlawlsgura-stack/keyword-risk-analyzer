-- Verify on the configured project after keyword_request_owner_edit_setup.sql.
-- Uses two existing account IDs, isolated temporary requests, and rolls back all data.
begin;
create temporary table kra_owner_test as
select
    (select id from auth.users order by id limit 1) as owner_id,
    (select id from auth.users order by id offset 1 limit 1) as other_id,
    gen_random_uuid() as own_request,
    gen_random_uuid() as other_request,
    gen_random_uuid() as missing_initial_request,
    gen_random_uuid() as broken_request;
grant select on kra_owner_test to authenticated;

do $$ begin
    assert (select owner_id is not null and other_id is not null from kra_owner_test),
        'verification requires two existing accounts';
end $$;

insert into public.kra_keyword_requests
    (id, requester_id, requester_email, kwd_no, keyword_name, request_type,
     request_detail, status, admin_reply)
select request_id, user_id, 'owner-test@example.test', 'B101', 'verification',
    'risk_grade_adjustment', 'original', '검토중', 'existing answer'
from kra_owner_test t cross join lateral (values
    (t.own_request, t.owner_id), (t.other_request, t.other_id),
    (t.missing_initial_request, t.owner_id), (t.broken_request, t.owner_id)
) fixture(request_id, user_id);

-- The current registration trigger creates initial inquiries; keep one absent
-- to verify compatibility with historical requests that predate that trigger.
delete from public.kra_keyword_request_messages
where request_id = (select missing_initial_request from kra_owner_test);

insert into public.kra_keyword_request_messages
    (request_id, author_id, author_email, author_role, is_initial, body, status)
select request_id, user_id, 'owner-test@example.test', 'user', true, 'original', '검토중'
from kra_owner_test t cross join lateral (values
    (t.own_request, t.owner_id), (t.other_request, t.other_id),
    (t.broken_request, t.other_id)
) fixture(request_id, user_id)
on conflict (request_id) where is_initial
do update set author_id = excluded.author_id, body = excluded.body, status = excluded.status;

insert into public.kra_keyword_request_messages
    (request_id, author_id, author_email, author_role, reply_to_id, body)
select t.own_request, t.other_id, 'admin-test@example.test', 'admin', m.id, 'existing answer'
from kra_owner_test t join public.kra_keyword_request_messages m
    on m.request_id = t.own_request and m.is_initial;

select set_config('request.jwt.claims', jsonb_build_object(
    'sub', owner_id, 'email', 'owner-test@example.test',
    'role', 'authenticated', 'app_metadata', jsonb_build_object('role', 'member')
)::text, true) from kra_owner_test;
set local role authenticated;

do $$
declare
    fixture record;
    saved jsonb;
    affected integer;
begin
    select * into fixture from kra_owner_test;
    saved := public.kra_edit_own_keyword_request(
        fixture.own_request, 'review_criteria_change', '  edited request  '
    );
    assert saved->>'request_detail' = 'edited request', 'owner edit failed';
    assert saved->>'request_type' = 'review_criteria_change', 'type edit failed';
    assert saved->>'status' = '검토중' and saved->>'admin_reply' = 'existing answer',
        'editing changed administrator workflow';
    assert saved->>'requester_id' = fixture.owner_id::text and saved->>'kwd_no' = 'B101',
        'editing changed ownership or keyword';
    assert (select body = 'edited request' and status = '검토중'
        from public.kra_keyword_request_messages where request_id = fixture.own_request and is_initial),
        'initial inquiry was not synchronized';
    assert (select body = 'existing answer' from public.kra_keyword_request_messages
        where request_id = fixture.own_request and author_role = 'admin'), 'answer was changed';

    perform public.kra_edit_own_keyword_request(
        fixture.missing_initial_request, 'new_keyword_registration', ''
    );
    assert (select body = '최초 문의 등록' and status = '검토중'
        from public.kra_keyword_request_messages
        where request_id = fixture.missing_initial_request and is_initial),
        'missing initial inquiry was not created';

    begin
        perform public.kra_edit_own_keyword_request(fixture.other_request, 'review_criteria_change', 'attack');
        raise exception 'another account request was editable';
    exception when insufficient_privilege then null;
    end;
    begin
        perform public.kra_edit_own_keyword_request(fixture.own_request, 'invalid', 'attack');
        raise exception 'invalid request type was accepted';
    exception when invalid_parameter_value then null;
    end;
    begin
        perform public.kra_edit_own_keyword_request(fixture.own_request, 'review_criteria_change', repeat('x', 4001));
        raise exception 'oversized detail was accepted';
    exception when invalid_parameter_value then null;
    end;
    begin
        perform public.kra_edit_own_keyword_request(fixture.broken_request, 'review_criteria_change', 'attack');
        raise exception 'mismatched initial message owner was accepted';
    exception when insufficient_privilege then null;
    end;
    assert (select request_detail = 'original' from public.kra_keyword_requests
        where id = fixture.broken_request), 'partial edit was not rolled back';

    update public.kra_keyword_requests set status = '처리완료', admin_reply = 'forged'
        where id = fixture.own_request;
    get diagnostics affected = row_count;
    assert affected = 0, 'owner changed administrator workflow';
    begin
        update public.kra_keyword_request_messages set body = 'forged'
            where request_id = fixture.own_request and author_role = 'admin';
        raise exception 'owner changed an administrator message';
    exception when insufficient_privilege then null;
    end;
    delete from public.kra_keyword_requests where id = fixture.other_request;
    get diagnostics affected = row_count;
    assert affected = 0, 'another account request was deleted';
    delete from public.kra_keyword_requests where id = fixture.own_request;
    get diagnostics affected = row_count;
    assert affected = 1, 'owner request deletion failed';
end $$;
reset role;

do $$ begin
    assert not exists (select 1 from public.kra_keyword_request_messages
        where request_id = (select own_request from kra_owner_test)), 'linked conversation survived deletion';
    assert (select request_detail = 'original' from public.kra_keyword_requests
        where id = (select other_request from kra_owner_test)), 'other request was changed';
    assert not has_function_privilege('anon',
        'public.kra_edit_own_keyword_request(uuid,text,text)', 'EXECUTE'), 'anonymous RPC access granted';
    assert not has_function_privilege('anon',
        'private.kra_edit_own_keyword_request(uuid,text,text)', 'EXECUTE'), 'anonymous helper access granted';
    assert not has_column_privilege('authenticated',
        'public.kra_keyword_requests', 'request_detail', 'UPDATE'), 'direct content writes granted';
end $$;

select set_config('request.jwt.claims', jsonb_build_object(
    'sub', owner_id, 'email', 'admin-test@example.test',
    'role', 'authenticated', 'app_metadata', jsonb_build_object('role', 'admin')
)::text, true) from kra_owner_test;
set local role authenticated;
do $$
declare fixture record; affected integer;
begin
    select * into fixture from kra_owner_test;
    begin
        perform public.kra_edit_own_keyword_request(fixture.other_request, 'review_criteria_change', 'attack');
        raise exception 'administrator edited another author request content';
    exception when insufficient_privilege then null;
    end;
    update public.kra_keyword_requests set status = '처리완료', admin_reply = 'admin update'
        where id = fixture.other_request;
    get diagnostics affected = row_count;
    assert affected = 1, 'administrator workflow update regressed';
    delete from public.kra_keyword_requests where id = fixture.other_request;
    get diagnostics affected = row_count;
    assert affected = 1, 'administrator deletion regressed';
end $$;
reset role;
rollback;
select 'owner edit/delete verification passed; all test data rolled back' as result;
