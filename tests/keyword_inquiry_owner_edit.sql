-- Run after keyword_inquiry_owner_edit_setup.sql. All fixtures are rolled back.
begin;
create temporary table kra_inquiry_test as
select
    (select id from auth.users order by id limit 1) as owner_id,
    (select id from auth.users order by id offset 1 limit 1) as other_id,
    gen_random_uuid() as request_id,
    gen_random_uuid() as other_request_id,
    gen_random_uuid() as q2_id,
    gen_random_uuid() as q3_id,
    gen_random_uuid() as answer1_id,
    gen_random_uuid() as answer2_id,
    gen_random_uuid() as followup_id,
    gen_random_uuid() as followup_answer_id;
grant select on kra_inquiry_test to authenticated;
do $$ begin
    assert (select owner_id is not null and other_id is not null from kra_inquiry_test),
        'two existing accounts are required';
end $$;

insert into public.kra_keyword_requests
    (id, requester_id, requester_email, kwd_no, keyword_name, request_type,
     request_detail, status, admin_reply)
select request_id, owner_id, 'inquiry-test@example.test', 'B101', 'verification',
    'risk_grade_adjustment', 'initial', '처리완료', 'followup answer'
from kra_inquiry_test
union all
select other_request_id, other_id, 'other-test@example.test', 'B102', 'verification',
    'risk_grade_adjustment', 'other initial', '대기', '' from kra_inquiry_test;

alter table kra_inquiry_test add column q1_id uuid;
update kra_inquiry_test t set q1_id = (
    select id from public.kra_keyword_request_messages m
    where m.request_id = t.request_id and m.is_initial
);
update public.kra_keyword_request_messages set status = '검토중'
where id = (select q1_id from kra_inquiry_test);

insert into public.kra_keyword_request_messages
    (id, request_id, author_id, author_email, author_role, reply_to_id, body, status, created_at)
select message_id, t.request_id, user_id, 'inquiry-test@example.test', role_name,
    parent_id, message_body, message_status, now() + delay * interval '1 second'
from kra_inquiry_test t cross join lateral (values
    (t.q2_id, t.owner_id, 'user', null::uuid, 'second', '처리완료', 1),
    (t.q3_id, t.owner_id, 'user', null::uuid, 'third', '대기', 2),
    (t.answer1_id, t.other_id, 'admin', t.q1_id, 'first answer', '대기', 3),
    (t.answer2_id, t.other_id, 'admin', t.q2_id, 'second answer', '대기', 4),
    (t.followup_id, t.owner_id, 'user', t.answer2_id, 'followup', '처리완료', 5),
    (t.followup_answer_id, t.other_id, 'admin', t.followup_id, 'followup answer', '대기', 6)
) m(message_id, user_id, role_name, parent_id, message_body, message_status, delay);

select set_config('request.jwt.claims', jsonb_build_object(
    'sub', owner_id, 'email', 'inquiry-test@example.test', 'role', 'authenticated',
    'app_metadata', jsonb_build_object('role', 'member')
)::text, true) from kra_inquiry_test;
set local role authenticated;

do $$
declare
    fixture record;
    message_id uuid;
    new_request_id uuid;
begin
    select * into fixture from kra_inquiry_test;
    -- Normal member registration must atomically create its own initial inquiry.
    insert into public.kra_keyword_requests
        (requester_id, requester_email, kwd_no, keyword_name, request_type, request_detail)
    values (fixture.owner_id, 'inquiry-test@example.test', 'B101', 'verification',
        'risk_grade_adjustment', 'new registration') returning id into new_request_id;
    assert (select count(*) = 1 from public.kra_keyword_request_messages
        where request_id = new_request_id and is_initial and author_id = fixture.owner_id),
        'member registration failed to create its initial inquiry';

    foreach message_id in array array[fixture.q2_id, fixture.q3_id, fixture.followup_id] loop
        perform public.kra_mutate_own_keyword_inquiry(
            fixture.request_id, message_id, 'edit', '  edited  '
        );
        assert (select body = 'edited' from public.kra_keyword_request_messages where id = message_id),
            'a later inquiry/followup was not edited';
    end loop;
    assert (select request_detail = 'initial' and admin_reply = 'followup answer' and status = '처리완료'
        from public.kra_keyword_requests where id = fixture.request_id),
        'later inquiry edits changed receipt details or workflow';
    assert (select body = 'first answer' from public.kra_keyword_request_messages where id = fixture.answer1_id),
        'editing changed an administrator answer';
    assert (select body = 'initial' from public.kra_keyword_request_messages where id = fixture.q1_id),
        'later inquiry edits changed Q01';

    perform public.kra_mutate_own_keyword_inquiry(
        fixture.request_id, fixture.q1_id, 'edit', 'edited initial', 'review_criteria_change'
    );
    assert (select request_detail = 'edited initial' and request_type = 'review_criteria_change'
        from public.kra_keyword_requests where id = fixture.request_id), 'Q01 summary was not synchronized';

    begin
        perform public.kra_mutate_own_keyword_inquiry(fixture.other_request_id, fixture.q2_id, 'edit', 'attack');
        raise exception 'another account request was editable';
    exception when insufficient_privilege then null;
    end;
    begin
        perform public.kra_mutate_own_keyword_inquiry(fixture.request_id, fixture.q2_id, 'edit', '');
        raise exception 'empty later inquiry was accepted';
    exception when invalid_parameter_value then null;
    end;
    begin
        perform public.kra_mutate_own_keyword_inquiry(fixture.request_id, fixture.q2_id, 'edit', repeat('x', 4001));
        raise exception 'oversized inquiry was accepted';
    exception when invalid_parameter_value then null;
    end;
    begin
        perform public.kra_mutate_own_keyword_inquiry(
            fixture.request_id, fixture.q2_id, 'edit', 'body', 'review_criteria_change'
        );
        raise exception 'Q02 changed the receipt-level inquiry type';
    exception when invalid_parameter_value then null;
    end;
    begin
        perform public.kra_mutate_own_keyword_inquiry(fixture.request_id, fixture.answer1_id, 'delete');
        raise exception 'owner directly deleted an administrator answer';
    exception when insufficient_privilege then null;
    end;

    perform public.kra_mutate_own_keyword_inquiry(fixture.request_id, fixture.q2_id, 'delete');
    assert not exists (select 1 from public.kra_keyword_request_messages
        where id in (fixture.q2_id, fixture.answer2_id, fixture.followup_id, fixture.followup_answer_id)),
        'Q02 connected replies survived deletion';
    assert (select count(*) = 3 from public.kra_keyword_request_messages
        where id in (fixture.q1_id, fixture.q3_id, fixture.answer1_id)), 'Q02 deletion changed other inquiries';
    assert (select request_detail = 'edited initial' and admin_reply = 'first answer' and status = '검토중'
        from public.kra_keyword_requests where id = fixture.request_id),
        'receipt summary still points to a deleted reply';

    perform public.kra_mutate_own_keyword_inquiry(fixture.request_id, fixture.q1_id, 'delete');
    assert not exists (select 1 from public.kra_keyword_request_messages where id in (fixture.q1_id, fixture.answer1_id)),
        'Q01 reply chain survived deletion';
    assert exists (select 1 from public.kra_keyword_request_messages where id = fixture.q3_id),
        'Q01 deletion removed Q03';
    assert (select request_detail = '' and admin_reply = '' and status = '대기'
        from public.kra_keyword_requests where id = fixture.request_id),
        'Q01 deletion removed receipt or retained deleted summary';
end $$;
reset role;

-- Try a different authenticated identity against the surviving Q03.
select set_config('request.jwt.claims', jsonb_build_object(
    'sub', other_id, 'email', 'other-test@example.test', 'role', 'authenticated',
    'app_metadata', jsonb_build_object('role', 'member')
)::text, true) from kra_inquiry_test;
set local role authenticated;
do $$ declare fixture record; begin
    select * into fixture from kra_inquiry_test;
    begin
        perform public.kra_mutate_own_keyword_inquiry(fixture.request_id, fixture.q3_id, 'delete');
        raise exception 'another account deleted Q03';
    exception when insufficient_privilege then null;
    end;
    assert not has_function_privilege('anon',
        'public.kra_mutate_own_keyword_inquiry(uuid,uuid,text,text,text)', 'EXECUTE'), 'anonymous RPC execution granted';
    assert not has_function_privilege('anon',
        'private.kra_mutate_own_keyword_inquiry(uuid,uuid,text,text,text)', 'EXECUTE'), 'anonymous helper execution granted';
    assert not has_column_privilege('authenticated', 'public.kra_keyword_request_messages', 'body', 'UPDATE'),
        'direct message modification granted';
    assert not has_table_privilege('authenticated', 'public.kra_keyword_request_messages', 'DELETE'),
        'unscoped message deletion granted';
end $$;
reset role;
rollback;
select 'per-inquiry edits, scoped cascade deletion, ownership and registration passed; fixtures rolled back' as result;
