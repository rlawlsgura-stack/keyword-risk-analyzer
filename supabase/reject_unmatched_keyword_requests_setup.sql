-- Run after new_keyword_registration_pool_setup.sql.
-- Reject selected requests while preserving real unmatched analysis history.
create or replace function public.kra_reject_unmatched_registration_requests(p_ids uuid[])
returns integer
language plpgsql security invoker set search_path = '' as $$
declare
    v_count integer;
    v_terms text[];
begin
    if p_ids is null or coalesce(array_length(p_ids, 1), 0) not between 1 and 1000
       or exists (select 1 from unnest(p_ids) request_id where request_id is null) then
        raise exception 'Invalid registration request selection' using errcode = '22023';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(193728174, 1);
    with rejected as (
        delete from public.kra_unmatched_registration_requests
         where id = any(p_ids)
         returning term_norm
    )
    select count(*)::integer, array_agg(distinct term_norm)
      into v_count, v_terms
      from rejected;
    if v_count = 0 then return 0; end if;

    update public.kra_unmatched_term_candidates as candidate
       set review_status = 'ignored'
     where candidate.term_norm = any(v_terms)
       and (candidate.total_occurrences > 0 or candidate.analysis_count > 0)
       and not exists (
           select 1 from public.kra_unmatched_registration_requests as request
            where request.term_norm = candidate.term_norm
       );

    delete from public.kra_unmatched_term_observations as observation
     using public.kra_unmatched_term_candidates as candidate
     where observation.term_norm = candidate.term_norm
       and candidate.term_norm = any(v_terms)
       and candidate.total_occurrences = 0 and candidate.analysis_count = 0
       and not exists (
           select 1 from public.kra_unmatched_registration_requests as request
            where request.term_norm = candidate.term_norm
       );

    delete from public.kra_unmatched_term_candidates as candidate
     where candidate.term_norm = any(v_terms)
       and candidate.total_occurrences = 0 and candidate.analysis_count = 0
       and not exists (
           select 1 from public.kra_unmatched_registration_requests as request
            where request.term_norm = candidate.term_norm
       );
    return v_count;
end;
$$;

revoke all on function public.kra_reject_unmatched_registration_requests(uuid[])
    from public, anon, authenticated;
grant execute on function public.kra_reject_unmatched_registration_requests(uuid[])
    to service_role;
