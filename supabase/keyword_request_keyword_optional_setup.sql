-- Allow keyword-less submissions only for new keyword registration requests.
alter table public.kra_keyword_requests
    drop constraint if exists kra_keyword_requests_kwd_no_check;
alter table public.kra_keyword_requests
    add constraint kra_keyword_requests_kwd_no_check
    check (
        request_type = 'new_keyword_registration'
        or length(btrim(kwd_no)) > 0
    );
