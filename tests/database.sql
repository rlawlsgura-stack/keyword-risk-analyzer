-- Run inside a transaction containing schema.sql, then ROLLBACK.
do $$
declare v_result jsonb; v_revision bigint;
begin
    if has_table_privilege('anon', 'public.kra_keywords', 'select') or
       has_table_privilege('authenticated', 'public.kra_keywords', 'update') or
       has_function_privilege('anon', 'public.kra_snapshot()', 'execute') or
       has_function_privilege('authenticated', 'public.kra_record_analysis(uuid,text,text,bigint,jsonb)', 'execute') then
        raise exception 'Client roles unexpectedly have access';
    end if;
    v_revision := public.kra_save_keywords(
        '[{"kwd_no":"A001","키워드명":"필러","비고":"keep","키워드 조회 수(누적카운트)":"4"}]',
        '["kwd_no","키워드명","비고","키워드 조회 수(누적카운트)","마지막 출력일자"]', 0);
    v_result := '{"analysis_id":"00000000-0000-0000-0000-000000000001","unique_keywords":["A001","A001"],"matches":[]}';
    perform public.kra_record_analysis('00000000-0000-0000-0000-000000000001',
        'fingerprint', 'user-1', v_revision, v_result);
    perform public.kra_record_analysis('00000000-0000-0000-0000-000000000001',
        'fingerprint', 'user-1', v_revision, v_result);
    if (select hit_count from public.kra_keywords where kwd_no = 'A001') <> 5 or
       (select count(*) from public.kra_hits) <> 1 then
        raise exception 'Idempotency or distinct counting failed';
    end if;
    begin
        perform public.kra_get_analysis('00000000-0000-0000-0000-000000000001', 'other');
        raise exception 'Ownership check failed';
    exception when serialization_failure then null;
    end;
    v_revision := public.kra_save_keywords(
        '[{"kwd_no":"A001","키워드명":"edited","비고":"keep","키워드 조회 수(누적카운트)":"4"}]',
        '["kwd_no","키워드명","비고","키워드 조회 수(누적카운트)","마지막 출력일자"]', v_revision);
    if (select hit_count from public.kra_keywords where kwd_no = 'A001') <> 5 then
        raise exception 'Stale editor overwrote counter';
    end if;
    begin
        perform public.kra_save_keywords('[]', '[]', 0);
        raise exception 'Revision check failed';
    exception when serialization_failure then null;
    end;
    perform public.kra_reset_counts();
    if (select count(*) from public.kra_hits) <> 1 then raise exception 'Reset deleted logs'; end if;
    perform public.kra_reset_week();
    if jsonb_array_length(public.kra_recent_hits()) <> 0 then raise exception 'Weekly reset failed'; end if;
    perform public.kra_record_analysis('00000000-0000-0000-0000-000000000001',
        'fingerprint', 'user-1', v_revision, v_result);
    if (select hit_count from public.kra_keywords where kwd_no = 'A001') <> 0 then
        raise exception 'Retry after reset recounted';
    end if;
    insert into public.kra_keywords(kwd_no,data)
        select 'TEST' || n, jsonb_build_object('kwd_no','TEST' || n) from generate_series(1,1100) n;
    if jsonb_array_length(public.kra_snapshot()->'rows') <> 1101 then
        raise exception 'Snapshot was truncated';
    end if;
end;
$$;
select 'database assertions passed' as result;
