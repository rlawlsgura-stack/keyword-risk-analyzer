-- Run after unmatched_registration_requests_setup.sql.
-- Add sidebar keyword-registration requests to the shared pool without
-- incrementing either analysis or occurrence statistics.
alter table public.kra_unmatched_term_candidates
    drop constraint if exists kra_unmatched_term_candidates_review_status_check;
alter table public.kra_unmatched_term_candidates
    add constraint kra_unmatched_term_candidates_review_status_check
    check (review_status in ('pending', 'approved', 'ignored', 'registration_requested'));

alter table public.kra_unmatched_registration_requests
    add column if not exists term_norm text;
update public.kra_unmatched_registration_requests
   set term_norm = lower(btrim(term))
 where term_norm is null;
alter table public.kra_unmatched_registration_requests
    alter column term_norm set not null;
alter table public.kra_unmatched_registration_requests
    drop constraint if exists kra_unmatched_registration_requests_term_norm_check;
alter table public.kra_unmatched_registration_requests
    add constraint kra_unmatched_registration_requests_term_norm_check
    check (char_length(btrim(term_norm)) between 1 and 100);

create or replace function public.kra_submit_new_keyword_registration_requests(p_terms jsonb)
returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    if p_terms is null or jsonb_typeof(p_terms) <> 'array'
       or jsonb_array_length(p_terms) not between 1 and 1000 then
        raise exception 'Invalid keyword-registration request' using errcode = '22023';
    end if;
    if exists (
        select 1 from jsonb_to_recordset(p_terms) as item(term text, term_norm text)
        where item.term is null or char_length(btrim(item.term)) not between 1 and 150
           or item.term_norm is null or char_length(btrim(item.term_norm)) not between 1 and 100
    ) then
        raise exception 'Invalid keyword-registration term' using errcode = '22023';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(193728174, 1);
    insert into public.kra_unmatched_term_candidates as candidate
        (term_norm, display_term, review_status)
    select term_norm, min(term), 'registration_requested'
      from jsonb_to_recordset(p_terms) as item(term text, term_norm text)
     group by term_norm
    on conflict (term_norm) do update
       set review_status = 'registration_requested';

    insert into public.kra_unmatched_registration_requests
        (term_norm, term, source_terms, occurrences)
    select term_norm, term, term, 0
      from jsonb_to_recordset(p_terms) as item(term text, term_norm text);
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

revoke all on function public.kra_submit_new_keyword_registration_requests(jsonb)
    from public, anon, authenticated;
grant execute on function public.kra_submit_new_keyword_registration_requests(jsonb)
    to service_role;

create or replace function public.kra_unmatched_term_export()
returns jsonb
language sql stable security invoker set search_path = '' as $$
    select coalesce(jsonb_agg(jsonb_build_object(
        'term_norm', term_norm, 'display_term', display_term,
        'total_occurrences', total_occurrences, 'analysis_count', analysis_count,
        'review_status', review_status, 'first_seen', first_seen, 'last_seen', last_seen)
        order by total_occurrences desc, analysis_count desc, term_norm), '[]'::jsonb)
    from public.kra_unmatched_term_candidates;
$$;
revoke all on function public.kra_unmatched_term_export() from public, anon, authenticated;
grant execute on function public.kra_unmatched_term_export() to service_role;
