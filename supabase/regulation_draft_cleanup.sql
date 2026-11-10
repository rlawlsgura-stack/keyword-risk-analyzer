-- Allow administrators to remove unapproved uploads.
create or replace function public.kra_delete_regulation_draft(p_id uuid)
returns boolean language plpgsql security invoker set search_path = '' as $$
begin
    delete from public.kra_regulation_documents where id = p_id and status = 'draft';
    return found;
end;
$$;
revoke all on function public.kra_delete_regulation_draft(uuid) from public, anon, authenticated;
grant execute on function public.kra_delete_regulation_draft(uuid) to service_role;
