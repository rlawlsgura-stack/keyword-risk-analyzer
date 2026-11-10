-- Add atomic embedding backfill for existing approved documents.
create or replace function public.kra_set_regulation_embeddings(
    p_document_id uuid, p_model text, p_vectors jsonb
) returns integer language plpgsql security invoker set search_path = '' as $$
declare v_item jsonb; v_count integer := 0;
begin
    if jsonb_typeof(p_vectors) <> 'array' or
       jsonb_array_length(p_vectors) <> (select count(*) from public.kra_regulation_chunks
                                         where document_id = p_document_id) then
        raise exception 'Embedding count does not match document chunks';
    end if;
    for v_item in select value from jsonb_array_elements(p_vectors) loop
        update public.kra_regulation_chunks
           set embedding = (v_item->>'embedding')::extensions.vector,
               embedding_model = p_model
         where document_id = p_document_id and ordinal = (v_item->>'ordinal')::integer;
        if not found then raise exception 'Embedding ordinal not found'; end if;
        v_count := v_count + 1;
    end loop;
    return v_count;
end;
$$;
revoke all on function public.kra_set_regulation_embeddings(uuid, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.kra_set_regulation_embeddings(uuid, text, jsonb)
    to service_role;
