-- Existing installations: keep safeupdate enabled and reset only changed rows.
create or replace function public.kra_reset_counts() returns void
language plpgsql security invoker set search_path = '' as $$
begin
    perform 1 from public.kra_state where id for update;
    update public.kra_keywords set hit_count = 0, last_hit = ''
        where hit_count <> 0 or last_hit <> '';
end;
$$;
