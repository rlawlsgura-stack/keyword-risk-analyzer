-- Store source files in private Supabase Storage; keep searchable text in Postgres.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('regulation-documents', 'regulation-documents', false, 52428800,
        array['text/plain', 'text/markdown',
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              'application/pdf'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

alter table public.kra_regulation_documents alter column original_bytes drop not null;
alter table public.kra_regulation_documents add column if not exists storage_path text unique;
alter table public.kra_regulation_documents drop constraint if exists kra_regulation_original_location;
alter table public.kra_regulation_documents add constraint kra_regulation_original_location
    check ((original_bytes is null) <> (storage_path is null));

create table if not exists public.kra_regulation_storage_deletions (
    storage_path text primary key,
    created_at timestamptz not null default now()
);
alter table public.kra_regulation_storage_deletions enable row level security;
revoke all on public.kra_regulation_storage_deletions from public, anon, authenticated;
grant select, insert, delete on public.kra_regulation_storage_deletions to service_role;

create or replace function public.kra_create_regulation_document_in_storage(
    p_source_key text, p_version text, p_title text, p_category text,
    p_effective_from date, p_effective_to date, p_content_sha256 text,
    p_original_name text, p_storage_path text, p_mime_type text,
    p_created_by uuid, p_chunks jsonb
) returns uuid
language plpgsql security invoker set search_path = '' as $$
declare v_doc public.kra_regulation_documents; v_chunk jsonb;
begin
    if p_storage_path !~ '^originals/[a-f0-9]{48}$' then
        raise exception 'Invalid regulation file path';
    end if;
    if jsonb_typeof(p_chunks) <> 'array' or jsonb_array_length(p_chunks) = 0
       or jsonb_array_length(p_chunks) > 300 then
        raise exception 'Document must contain 1 to 300 chunks';
    end if;
    insert into public.kra_regulation_storage_deletions(storage_path)
    select storage_path from public.kra_regulation_documents
     where source_key = p_source_key and status = 'draft' and storage_path is not null
    on conflict do nothing;
    delete from public.kra_regulation_documents
     where source_key = p_source_key and status = 'draft';
    insert into public.kra_regulation_documents(
        source_key, version, title, category, effective_from, effective_to,
        content_sha256, original_name, original_bytes, storage_path, mime_type, created_by)
    values (p_source_key, p_version, p_title, p_category, p_effective_from,
            p_effective_to, p_content_sha256, p_original_name, null,
            p_storage_path, p_mime_type, p_created_by)
    returning * into v_doc;
    for v_chunk in select value from jsonb_array_elements(p_chunks) loop
        insert into public.kra_regulation_chunks(
            document_id, ordinal, content, search_tokens, embedding, embedding_model)
        values (v_doc.id, (v_chunk->>'ordinal')::integer,
                v_chunk->>'content', v_chunk->>'search_tokens',
                (v_chunk->>'embedding')::extensions.vector,
                v_chunk->>'embedding_model');
    end loop;
    return v_doc.id;
end;
$$;

create or replace function public.kra_delete_regulation_document_with_storage(p_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_path text; v_id uuid;
begin
    select storage_path into v_path from public.kra_regulation_documents where id = p_id for update;
    if not found then return jsonb_build_object('deleted', false); end if;
    if v_path is not null then
        insert into public.kra_regulation_storage_deletions(storage_path) values (v_path)
        on conflict do nothing;
    end if;
    delete from public.kra_regulation_documents where id = p_id returning id into v_id;
    return jsonb_build_object('deleted', true);
end;
$$;

create or replace function public.kra_list_regulation_document_originals(p_limit integer default 1)
returns table(id uuid, content_sha256 text, original_name text, mime_type text, original_base64 text)
language sql stable security invoker set search_path = '' as $$
    select d.id, d.content_sha256, d.original_name, d.mime_type,
           encode(d.original_bytes, 'base64')
      from public.kra_regulation_documents d
     where d.original_bytes is not null and d.storage_path is null
     order by d.created_at, d.id
     limit least(greatest(p_limit, 1), 5);
$$;

create or replace function public.kra_finish_regulation_document_original_migration(
    p_id uuid, p_storage_path text, p_content_sha256 text)
returns boolean language plpgsql security invoker set search_path = '' as $$
begin
    update public.kra_regulation_documents
       set storage_path = p_storage_path, original_bytes = null
     where id = p_id and content_sha256 = p_content_sha256
       and original_bytes is not null and storage_path is null;
    return found;
end;
$$;

revoke all on function public.kra_create_regulation_document_in_storage(text,text,text,text,date,date,text,text,text,text,uuid,jsonb) from public, anon, authenticated;
revoke all on function public.kra_delete_regulation_document_with_storage(uuid) from public, anon, authenticated;
revoke all on function public.kra_list_regulation_document_originals(integer) from public, anon, authenticated;
revoke all on function public.kra_finish_regulation_document_original_migration(uuid,text,text) from public, anon, authenticated;
grant execute on function public.kra_create_regulation_document_in_storage(text,text,text,text,date,date,text,text,text,text,uuid,jsonb) to service_role;
grant execute on function public.kra_delete_regulation_document_with_storage(uuid) to service_role;
grant execute on function public.kra_list_regulation_document_originals(integer) to service_role;
grant execute on function public.kra_finish_regulation_document_original_migration(uuid,text,text) to service_role;
