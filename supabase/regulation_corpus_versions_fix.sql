-- Preserve historical versions by effective date.
create or replace function public.kra_approve_regulation_document(p_id uuid, p_approver uuid)
returns uuid
language plpgsql security invoker set search_path = '' as $$
declare v_doc public.kra_regulation_documents;
begin
    select * into v_doc from public.kra_regulation_documents where id = p_id for update;
    if not found or v_doc.status <> 'draft' then
        raise exception 'Document is no longer a draft' using errcode = '40001';
    end if;
    if not exists (select 1 from public.kra_regulation_chunks where document_id = p_id) then
        raise exception 'Document has no searchable content';
    end if;
    if exists (select 1 from public.kra_regulation_documents
               where source_key = v_doc.source_key and status = 'approved'
                 and effective_from >= v_doc.effective_from) then
        raise exception 'New version must start after the previous approved version'
            using errcode = '40001';
    end if;
    update public.kra_regulation_documents
       set status = 'superseded',
           effective_to = case when effective_to is null or effective_to >= v_doc.effective_from
                               then v_doc.effective_from - 1 else effective_to end
      where source_key = v_doc.source_key and status = 'approved';
    update public.kra_regulation_documents set status = 'approved',
        approved_by = p_approver, approved_at = now()
      where id = p_id returning * into v_doc;
    return v_doc.id;
end;
$$;
create or replace function public.kra_search_regulation_chunks(
    p_tokens text, p_embedding text, p_category text, p_as_of date,
    p_limit integer default 5, p_strategy text default 'hybrid'
) returns table(chunk_id uuid, document_id uuid, title text, version text,
                content text, ordinal integer, content_sha256 text, score double precision,
                lexical_rank bigint, semantic_rank bigint, fuzzy_rank bigint)
language sql stable security invoker set search_path = '' as $$
    with eligible as (
        select c.id, c.document_id, d.title, d.version, c.content, c.ordinal,
               d.content_sha256, c.fts, c.embedding
        from public.kra_regulation_chunks c
        join public.kra_regulation_documents d on d.id = c.document_id
        where d.status in ('approved', 'superseded') and d.effective_from <= p_as_of
          and (d.effective_to is null or d.effective_to >= p_as_of)
          and (d.category = '' or p_category = '' or d.category = p_category)
    ),
    lexical as (
        select id, row_number() over (order by ts_rank(fts, plainto_tsquery('simple', p_tokens)) desc, id) as rank
        from eligible where fts @@ plainto_tsquery('simple', p_tokens)
        order by rank limit 20
    ),
    semantic as (
        select id, row_number() over (order by embedding OPERATOR(extensions.<=>) p_embedding::extensions.vector, id) as rank
        from eligible
        where p_embedding is not null and embedding is not null
        order by rank limit 20
    ),
    fuzzy as (
        select c.id, row_number() over (order by extensions.word_similarity(p_tokens, c.search_tokens) desc, c.id) as rank
        from public.kra_regulation_chunks c
        join eligible e on e.id = c.id
        where extensions.word_similarity(p_tokens, c.search_tokens) >= 0.25
        order by rank limit 20
    )
    select e.id, e.document_id, e.title, e.version, e.content, e.ordinal,
           e.content_sha256,
           (case when l.rank is null or p_strategy not in ('lexical', 'hybrid') then 0 else 1.0 / (60 + l.rank) end
            + case when s.rank is null or p_strategy not in ('semantic', 'hybrid') then 0 else 1.0 / (60 + s.rank) end
            + case when f.rank is null or p_strategy not in ('fuzzy', 'hybrid') then 0 else 1.0 / (60 + f.rank) end)::double precision,
           l.rank, s.rank, f.rank
    from eligible e
    left join lexical l on l.id = e.id
    left join semantic s on s.id = e.id
    left join fuzzy f on f.id = e.id
    where (p_strategy in ('lexical', 'hybrid') and l.id is not null)
       or (p_strategy in ('semantic', 'hybrid') and s.id is not null)
       or (p_strategy in ('fuzzy', 'hybrid') and f.id is not null)
    order by 8 desc, e.id limit least(greatest(p_limit, 1), 10);
$$;
