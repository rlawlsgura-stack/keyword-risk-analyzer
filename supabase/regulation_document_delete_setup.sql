create or replace function public.kra_delete_regulation_document(p_id uuid)
returns boolean
language plpgsql security invoker set search_path = '' as $$
begin
    delete from public.kra_regulation_documents where id = p_id;
    return found;
end;
$$;
revoke all on function public.kra_delete_regulation_document(uuid) from public, anon, authenticated;
grant execute on function public.kra_delete_regulation_document(uuid) to service_role;
