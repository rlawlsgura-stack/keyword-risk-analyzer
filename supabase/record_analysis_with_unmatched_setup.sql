-- Apply to existing projects before deploying the React v2 analysis endpoint.
-- Both existing idempotent operations share the transaction of this RPC.
create function public.kra_record_analysis_with_unmatched(
    p_id uuid, p_fingerprint text, p_actor text, p_revision bigint,
    p_result jsonb, p_terms jsonb
) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare v_result jsonb;
begin
    v_result := public.kra_record_analysis(
        p_id, p_fingerprint, p_actor, p_revision, p_result);
    perform public.kra_collect_unmatched_terms(p_id, p_terms);
    return v_result;
end;
$$;

revoke all on function public.kra_record_analysis_with_unmatched(
    uuid, text, text, bigint, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.kra_record_analysis_with_unmatched(
    uuid, text, text, bigint, jsonb, jsonb) to service_role;
