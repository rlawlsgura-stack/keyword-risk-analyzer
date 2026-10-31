-- Add registered-order sorting to the shared unmatched-candidate page RPC.
drop function if exists public.kra_unmatched_term_page(integer, integer, text);

create or replace function public.kra_unmatched_term_page(
    p_offset integer default 0,
    p_limit integer default 100,
    p_search text default '',
    p_sort text default 'registered'
)
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

revoke all on function public.kra_unmatched_term_page(integer, integer, text, text)
    from public, anon, authenticated;
grant execute on function public.kra_unmatched_term_page(integer, integer, text, text)
    to service_role;
