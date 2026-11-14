-- Run after keyword_request_daily_receipts. All fixture rows are rolled back.
begin;
do $$
declare
    v_owner uuid;
    v_first text;
    v_second text;
    v_third text;
    v_next_day text;
begin
    select id into v_owner from auth.users limit 1;
    if v_owner is null then
        raise exception 'An existing account is required for this test';
    end if;

    insert into public.kra_keyword_requests
        (requester_id, requester_email, kwd_no, keyword_name,
         request_type, request_detail, created_at)
    values (v_owner, 'receipt-test@example.invalid', '', 'receipt test',
            'new_keyword_registration', 'first', '2099-12-31 14:59:58+00')
    returning receipt_no into v_first;

    insert into public.kra_keyword_requests
        (requester_id, requester_email, kwd_no, keyword_name,
         request_type, request_detail, created_at)
    values (v_owner, 'receipt-test@example.invalid', '', 'receipt test',
            'new_keyword_registration', 'second', '2099-12-31 14:59:59+00')
    returning receipt_no into v_second;

    delete from public.kra_keyword_requests where receipt_no = v_second;

    insert into public.kra_keyword_requests
        (requester_id, requester_email, kwd_no, keyword_name,
         request_type, request_detail, created_at)
    values (v_owner, 'receipt-test@example.invalid', '', 'receipt test',
            'new_keyword_registration', 'third', '2099-12-31 14:59:59+00')
    returning receipt_no into v_third;

    insert into public.kra_keyword_requests
        (requester_id, requester_email, kwd_no, keyword_name,
         request_type, request_detail, created_at)
    values (v_owner, 'receipt-test@example.invalid', '', 'receipt test',
            'new_keyword_registration', 'next day', '2099-12-31 15:00:00+00')
    returning receipt_no into v_next_day;

    if (v_first, v_second, v_third, v_next_day) is distinct from
       ('20991231_001', '20991231_002', '20991231_003', '21000101_001') then
        raise exception 'Unexpected receipt sequence: %, %, %, %',
            v_first, v_second, v_third, v_next_day;
    end if;
end;
$$;
rollback;
