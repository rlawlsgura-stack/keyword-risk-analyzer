-- Additive Kiwi unmatched-term aggregation. No source text is stored.
create table public.kra_unmatched_term_candidates (
    term_norm text primary key check (char_length(btrim(term_norm)) between 1 and 100),
    display_term text not null check (char_length(btrim(display_term)) between 1 and 150),
    total_occurrences bigint not null default 0 check (total_occurrences >= 0),
    analysis_count bigint not null default 0 check (analysis_count >= 0),
    first_seen timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    review_status text not null default 'pending'
        check (review_status in ('pending', 'approved', 'ignored'))
);

create table public.kra_unmatched_term_observations (
    analysis_id uuid not null,
    term_norm text not null,
    occurrences integer not null check (occurrences between 1 and 10000),
    created_at timestamptz not null default now(),
    primary key (analysis_id, term_norm)
);
create index kra_unmatched_candidates_frequency_idx
    on public.kra_unmatched_term_candidates(total_occurrences desc, analysis_count desc);

alter table public.kra_unmatched_term_candidates enable row level security;
alter table public.kra_unmatched_term_observations enable row level security;
revoke all on public.kra_unmatched_term_candidates,
    public.kra_unmatched_term_observations from public, anon, authenticated;
grant all on public.kra_unmatched_term_candidates,
    public.kra_unmatched_term_observations to service_role;

create function public.kra_collect_unmatched_terms(p_id uuid, p_terms jsonb)
returns integer
language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    if p_id is null or p_terms is null or jsonb_typeof(p_terms) <> 'array'
       or jsonb_array_length(p_terms) > 1000 then
        raise exception 'Invalid unmatched-term payload' using errcode = '22023';
    end if;
    if exists (
        select 1 from jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
        where item.term_norm is null or char_length(btrim(item.term_norm)) not between 1 and 100
           or item.display_term is null or char_length(btrim(item.display_term)) not between 1 and 150
           or item.occurrences is null or item.occurrences not between 1 and 10000
    ) then
        raise exception 'Invalid unmatched-term item' using errcode = '22023';
    end if;

    with inserted as (
        insert into public.kra_unmatched_term_observations(analysis_id, term_norm, occurrences)
        select p_id, item.term_norm, item.occurrences
        from (
            select term_norm, min(display_term) as display_term,
                   sum(occurrences)::integer as occurrences
            from jsonb_to_recordset(p_terms)
                as source(term_norm text, display_term text, occurrences integer)
            group by term_norm
        ) item
        on conflict (analysis_id, term_norm) do nothing
        returning term_norm, occurrences, created_at
    ), grouped as (
        select term_norm, sum(occurrences)::bigint as total_occurrences,
               count(*)::bigint as analysis_count, min(created_at) as first_seen,
               max(created_at) as last_seen
        from inserted group by term_norm
    ), upserted as (
        insert into public.kra_unmatched_term_candidates as candidate
            (term_norm, display_term, total_occurrences, analysis_count, first_seen, last_seen)
        select grouped.term_norm,
               min(item.display_term), grouped.total_occurrences, grouped.analysis_count,
               grouped.first_seen, grouped.last_seen
        from grouped
        join jsonb_to_recordset(p_terms)
            as item(term_norm text, display_term text, occurrences integer)
          on item.term_norm = grouped.term_norm
        group by grouped.term_norm, grouped.total_occurrences, grouped.analysis_count,
                 grouped.first_seen, grouped.last_seen
        on conflict (term_norm) do update set
            total_occurrences = candidate.total_occurrences + excluded.total_occurrences,
            analysis_count = candidate.analysis_count + excluded.analysis_count,
            first_seen = least(candidate.first_seen, excluded.first_seen),
            last_seen = greatest(candidate.last_seen, excluded.last_seen)
        returning 1
    )
    select count(*)::integer into v_count from upserted;
    return coalesce(v_count, 0);
end;
$$;

create function public.kra_unmatched_term_candidates(p_status text default null,
                                                       p_limit integer default 500)
returns jsonb
language plpgsql stable security invoker set search_path = '' as $$
begin
    if p_status is not null and p_status not in ('pending', 'approved', 'ignored') then
        raise exception 'Invalid review status' using errcode = '22023';
    end if;
    return coalesce((
        select jsonb_agg(to_jsonb(candidate)
                         order by candidate.total_occurrences desc,
                                  candidate.analysis_count desc, candidate.term_norm)
        from (
            select term_norm, display_term, total_occurrences, analysis_count,
                   first_seen, last_seen, review_status
            from public.kra_unmatched_term_candidates
            where p_status is null or review_status = p_status
            order by total_occurrences desc, analysis_count desc, term_norm
            limit least(greatest(coalesce(p_limit, 500), 1), 1000)
        ) candidate
    ), '[]'::jsonb);
end;
$$;

create function public.kra_set_unmatched_term_status(p_term_norm text, p_status text)
returns boolean
language plpgsql security invoker set search_path = '' as $$
begin
    if p_status not in ('pending', 'approved', 'ignored') then
        raise exception 'Invalid review status' using errcode = '22023';
    end if;
    update public.kra_unmatched_term_candidates
       set review_status = p_status
     where term_norm = p_term_norm;
    return found;
end;
$$;

revoke all on function public.kra_collect_unmatched_terms(uuid, jsonb) from public, anon, authenticated;
revoke all on function public.kra_unmatched_term_candidates(text, integer) from public, anon, authenticated;
revoke all on function public.kra_set_unmatched_term_status(text, text) from public, anon, authenticated;
grant execute on function public.kra_collect_unmatched_terms(uuid, jsonb) to service_role;
grant execute on function public.kra_unmatched_term_candidates(text, integer) to service_role;
grant execute on function public.kra_set_unmatched_term_status(text, text) to service_role;
