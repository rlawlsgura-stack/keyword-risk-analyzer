-- Run on the configured database after persistent_unmatched_setup.sql.
-- All verification data is rolled back, including the anonymous event ledger.
begin;
set local role service_role;
do $$
declare
    event_one uuid := gen_random_uuid();
    event_two uuid := gen_random_uuid();
    batch_event uuid := gen_random_uuid();
    invalid_event uuid := gen_random_uuid();
    prefix text := 'kra-verification-' || gen_random_uuid()::text;
    term text;
    payload jsonb;
    page jsonb;
    n integer;
begin
    term := prefix || '-single';
    payload := jsonb_build_array(jsonb_build_object(
        'term_norm', term, 'display_term', term, 'occurrences', 3));
    n := public.kra_collect_unmatched_terms(event_one, payload);
    assert n = 1, 'first collection failed';
    n := public.kra_collect_unmatched_terms(event_one, payload);
    assert n = 0, 'save retry was counted twice';
    assert (select total_occurrences = 3 and analysis_count = 1
        from public.kra_unmatched_term_candidates where term_norm = term), 'wrong aggregate';

    n := public.kra_delete_unmatched_terms(array[term]);
    assert n = 1, 'delete failed';
    assert not exists (select 1 from public.kra_unmatched_term_observations
                        where term_norm = term), 'observation retained after delete';
    n := public.kra_collect_unmatched_terms(event_one, payload);
    assert n = 0, 'old retry recreated a permanently deleted expression';
    assert not exists (select 1 from public.kra_unmatched_term_candidates
                        where term_norm = term), 'deleted expression reappeared';
    n := public.kra_collect_unmatched_terms(event_two, payload);
    assert n = 1, 'a genuinely new analysis should collect again';

    select jsonb_agg(jsonb_build_object('term_norm', prefix || '-' || i,
        'display_term', prefix || '-' || i, 'occurrences', 2))
        into payload from generate_series(1, 1005) i;
    n := public.kra_collect_unmatched_terms(batch_event, payload);
    assert n = 1005, 'collection truncated at 1000 terms';
    page := public.kra_unmatched_term_page(1000, 100, prefix);
    assert (page->>'total')::integer = 1006, 'wrong total count';
    assert jsonb_array_length(page->'rows') = 6, 'pagination truncated';
    assert (select count(*) from jsonb_array_elements(public.kra_unmatched_term_export()) item
            where item->>'term_norm' like prefix || '%') = 1006, 'export truncated';

    begin
        perform public.kra_collect_unmatched_terms(invalid_event,
            jsonb_build_array(jsonb_build_object('term_norm', term,
                'display_term', term, 'occurrences', -1)));
        raise exception 'invalid counts were accepted';
    exception when invalid_parameter_value then null;
    end;
    assert not exists (select 1 from public.kra_unmatched_collection_events
                        where analysis_id = invalid_event), 'invalid request consumed retry ID';
    assert not has_function_privilege('anon', 'public.kra_delete_unmatched_terms(text[])', 'EXECUTE');
    assert not has_function_privilege('authenticated', 'public.kra_collect_unmatched_terms(uuid,jsonb)', 'EXECUTE');
    assert not has_table_privilege('service_role', 'public.kra_unmatched_collection_events', 'DELETE');
end;
$$;
rollback;
select 'unmatched persistence verification passed; test data rolled back' as result;
