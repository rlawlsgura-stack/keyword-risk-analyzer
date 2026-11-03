-- Additive report function for React custom date ranges.
create function public.kra_top_keywords_range(
    p_start_date date, p_end_date date, p_limit integer default 10
) returns jsonb language plpgsql stable security invoker set search_path = '' as $$
begin
    if p_start_date is null or p_end_date is null or p_end_date < p_start_date then
        raise exception 'Invalid report date range' using errcode = '22023';
    end if;
    return (
        select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) from (
            select h.kwd_no, count(*) as hit_count, k.data->>'키워드명' as term
            from public.kra_hits h left join public.kra_keywords k using(kwd_no)
            where h.visible
              and h.ts >= (p_start_date::timestamp at time zone 'Asia/Seoul')
              and h.ts < ((p_end_date + 1)::timestamp at time zone 'Asia/Seoul')
            group by h.kwd_no, k.data order by count(*) desc, h.kwd_no
            limit least(greatest(coalesce(p_limit, 10), 1), 100)
        ) t
    );
end;
$$;
revoke all on function public.kra_top_keywords_range(date, date, integer)
    from public, anon, authenticated;
grant execute on function public.kra_top_keywords_range(date, date, integer)
    to service_role;
