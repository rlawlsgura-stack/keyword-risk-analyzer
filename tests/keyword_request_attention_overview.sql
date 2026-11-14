-- Run after keyword_request_attention_overview. All fixture rows are rolled back.
begin;
do $$
declare
    v_owner uuid;
    v_request uuid;
    v_initial uuid;
    v_followup uuid;
    v_attention boolean;
begin
    select id into v_owner from auth.users limit 1;
    if v_owner is null then
        raise exception 'An existing account is required for this test';
    end if;

    insert into public.kra_keyword_requests
        (requester_id, requester_email, kwd_no, keyword_name,
         request_type, request_detail)
    values (v_owner, 'attention-test@example.invalid', '', 'attention test',
            'new_keyword_registration', 'initial question')
    returning id into v_request;

    select id into v_initial from public.kra_keyword_request_messages
    where request_id = v_request and is_initial;
    select needs_attention into v_attention from public.kra_keyword_request_overview
    where id = v_request;
    if v_attention is distinct from true then
        raise exception 'An unanswered initial question must need attention';
    end if;

    update public.kra_keyword_request_messages set status = '처리완료'
    where id = v_initial;
    insert into public.kra_keyword_request_messages
        (request_id, author_id, author_email, author_role, reply_to_id, body)
    values (v_request, v_owner, 'attention-test@example.invalid', 'admin',
            v_initial, 'initial answer');
    select needs_attention into v_attention from public.kra_keyword_request_overview
    where id = v_request;
    if v_attention is distinct from false then
        raise exception 'A completed and answered question must not need attention';
    end if;

    insert into public.kra_keyword_request_messages
        (request_id, author_id, author_email, author_role, body)
    values (v_request, v_owner, 'attention-test@example.invalid', 'user',
            'follow-up question')
    returning id into v_followup;
    select needs_attention into v_attention from public.kra_keyword_request_overview
    where id = v_request;
    if v_attention is distinct from true then
        raise exception 'An unanswered follow-up must need attention';
    end if;

    update public.kra_keyword_request_messages set status = '검토중'
    where id = v_followup;
    insert into public.kra_keyword_request_messages
        (request_id, author_id, author_email, author_role, reply_to_id, body)
    values (v_request, v_owner, 'attention-test@example.invalid', 'admin',
            v_followup, 'interim answer');
    select needs_attention into v_attention from public.kra_keyword_request_overview
    where id = v_request;
    if v_attention is distinct from true then
        raise exception 'An answered question under review must need attention';
    end if;

    update public.kra_keyword_request_messages set status = '처리완료'
    where id = v_followup;
    select needs_attention into v_attention from public.kra_keyword_request_overview
    where id = v_request;
    if v_attention is distinct from false then
        raise exception 'All completed questions must clear attention';
    end if;
end;
$$;
rollback;
