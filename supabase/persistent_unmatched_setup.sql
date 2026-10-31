-- Run after unmatched_term_pool_setup.sql. No account, source text or image is stored.
create table public.kra_unmatched_collection_events (
    analysis_id uuid primary key,
    created_at timestamptz not null default now()
);
alter table public.kra_unmatched_collection_events enable row level security;
revoke all on public.kra_unmatched_collection_events from public, anon, authenticated;
grant select, insert on public.kra_unmatched_collection_events to service_role;
revoke update, delete, truncate, references, trigger on public.kra_unmatched_collection_events from service_role;
insert into public.kra_unmatched_collection_events(analysis_id)
    select distinct analysis_id from public.kra_unmatched_term_observations
    on conflict do nothing;

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
        select p_id, term_norm, sum(occurrences)::integer
        from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        group by term_norm;

    insert into public.kra_unmatched_term_candidates as candidate
        (term_norm, display_term, total_occurrences, analysis_count)
        select term_norm, min(display_term), sum(occurrences)::bigint, 1
        from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        group by term_norm order by term_norm
        on conflict (term_norm) do update set
            total_occurrences = candidate.total_occurrences + excluded.total_occurrences,
            analysis_count = candidate.analysis_count + 1,
            last_seen = greatest(candidate.last_seen, excluded.last_seen);
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

drop function if exists public.kra_unmatched_term_page(integer, integer, text);
create or replace function public.kra_unmatched_term_page(
    p_offset integer default 0, p_limit integer default 100, p_search text default '',
    p_sort text default 'registered')
returns jsonb
language sql stable security invoker set search_path = '' as $$
    with filtered as (
        select term_norm, display_term, total_occurrences, analysis_count,
               first_seen, last_seen, review_status
        from public.kra_unmatched_term_candidates
        where coalesce(p_search, '') = ''
           or term_norm ilike '%' || p_search || '%'
           or display_term ilike '%' || p_search || '%'
    )
    select jsonb_build_object(
        'total', (select count(*) from filtered),
        'rows', coalesce((select jsonb_agg(to_jsonb(page)
                    order by case when p_sort = 'registered' then page.first_seen end desc,
                             case when coalesce(p_sort, 'occurrences') <> 'registered' then page.total_occurrences end desc,
                             case when coalesce(p_sort, 'occurrences') <> 'registered' then page.analysis_count end desc,
                             page.term_norm)
            from (select * from filtered
                  order by case when p_sort = 'registered' then first_seen end desc,
                           case when coalesce(p_sort, 'occurrences') <> 'registered' then total_occurrences end desc,
                           case when coalesce(p_sort, 'occurrences') <> 'registered' then analysis_count end desc,
                           term_norm
                  limit least(greatest(coalesce(p_limit, 100), 1), 1000)
                  offset greatest(coalesce(p_offset, 0), 0)) page), '[]'::jsonb));
$$;

create function public.kra_unmatched_term_export()
returns jsonb
language sql stable security invoker set search_path = '' as $$
    select coalesce(jsonb_agg(jsonb_build_object(
        'term_norm', term_norm, 'display_term', display_term,
        'total_occurrences', total_occurrences, 'analysis_count', analysis_count,
        'review_status', review_status,
        'first_seen', first_seen, 'last_seen', last_seen)
        order by total_occurrences desc, analysis_count desc, term_norm), '[]'::jsonb)
    from public.kra_unmatched_term_candidates;
$$;

-- Called only by the server after validating the current administrator's token.
create function public.kra_delete_unmatched_terms(p_terms text[])
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
    -- Keep anonymous event IDs: an old save retry must not recreate deleted terms.
    return v_count;
end;
$$;

revoke all on function public.kra_collect_unmatched_terms(uuid, jsonb) from public, anon, authenticated;
revoke all on function public.kra_unmatched_term_page(integer, integer, text, text) from public, anon, authenticated;
revoke all on function public.kra_unmatched_term_export() from public, anon, authenticated;
revoke all on function public.kra_delete_unmatched_terms(text[]) from public, anon, authenticated;
grant execute on function public.kra_collect_unmatched_terms(uuid, jsonb) to service_role;
grant execute on function public.kra_unmatched_term_page(integer, integer, text, text) to service_role;
grant execute on function public.kra_unmatched_term_export() to service_role;
grant execute on function public.kra_delete_unmatched_terms(text[]) to service_role;
