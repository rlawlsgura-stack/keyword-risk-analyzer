-- Deleted candidates can be collected again by a new OCR or text analysis.
-- The event ledger still prevents old analysis retries from restoring deleted data.
create or replace function public.kra_collect_unmatched_terms(p_id uuid, p_terms jsonb)
returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    if p_id is null or p_terms is null or jsonb_typeof(p_terms) <> 'array'
       or jsonb_array_length(p_terms) > 50000 then
        raise exception 'Invalid unmatched-term payload' using errcode = '22023';
    end if;
    if exists (
        select 1 from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        where item.term_norm is null or char_length(btrim(item.term_norm)) not between 1 and 100
           or item.display_term is null or char_length(btrim(item.display_term)) not between 1 and 150
           or item.occurrences is null or item.occurrences not between 1 and 1000000000
    ) then
        raise exception 'Invalid unmatched-term item' using errcode = '22023';
    end if;

    -- ponytail: serialize pool writes/deletes; use per-term locks if throughput requires it.
    perform pg_catalog.pg_advisory_xact_lock(193728174, 1);
    insert into public.kra_unmatched_collection_events(analysis_id) values (p_id)
        on conflict do nothing;
    get diagnostics v_count = row_count;
    if v_count = 0 then return 0; end if;

    insert into public.kra_unmatched_term_observations(analysis_id, term_norm, occurrences)
        select p_id, item.term_norm, sum(item.occurrences)::integer
        from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        group by item.term_norm;

    insert into public.kra_unmatched_term_candidates as candidate
        (term_norm, display_term, total_occurrences, analysis_count)
        select item.term_norm, min(item.display_term), sum(item.occurrences)::bigint, 1
        from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        group by item.term_norm order by item.term_norm
        on conflict (term_norm) do update set
            total_occurrences = candidate.total_occurrences + excluded.total_occurrences,
            analysis_count = candidate.analysis_count + 1,
            last_seen = greatest(candidate.last_seen, excluded.last_seen);
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

create or replace function public.kra_delete_unmatched_terms(p_terms text[])
returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    if p_terms is null or coalesce(array_length(p_terms, 1), 0) not between 1 and 1000
       or exists (select 1 from unnest(p_terms) term
                  where term is null or char_length(btrim(term)) not between 1 and 100) then
        raise exception 'Invalid unmatched-term selection' using errcode = '22023';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(193728174, 1);
    delete from public.kra_unmatched_term_observations where term_norm = any(p_terms);
    delete from public.kra_unmatched_term_candidates where term_norm = any(p_terms);
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

drop table if exists public.kra_unmatched_term_suppressions;

revoke all on function public.kra_collect_unmatched_terms(uuid, jsonb) from public, anon, authenticated;
revoke all on function public.kra_delete_unmatched_terms(text[]) from public, anon, authenticated;
grant execute on function public.kra_collect_unmatched_terms(uuid, jsonb) to service_role;
grant execute on function public.kra_delete_unmatched_terms(text[]) to service_role;
