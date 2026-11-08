-- Add the new keyword registration request type without changing existing rows.
alter table public.kra_keyword_requests
    drop constraint if exists kra_keyword_requests_request_type_check;

alter table public.kra_keyword_requests
    add constraint kra_keyword_requests_request_type_check
    check (request_type in (
        'risk_grade_adjustment',
        'review_criteria_change',
        'new_keyword_registration'
    ));
