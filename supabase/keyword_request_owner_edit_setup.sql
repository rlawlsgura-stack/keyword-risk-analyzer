-- Apply after keyword_request_feedback_status_setup.sql. Safe to run again.
-- Keep direct UPDATE privileges administrator-only. The private operation below
-- grants only an owner's content edit and atomically updates its initial message.

create or replace function private.kra_edit_own_keyword_request(
    p_request_id uuid,
    p_request_type text,
    p_request_detail text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
    v_user_id uuid := (select auth.uid());
    v_detail text := btrim(coalesce(p_request_detail, ''));
    v_request public.kra_keyword_requests%rowtype;
begin
    if v_user_id is null then
        raise exception 'authentication required' using errcode = '42501';
    end if;
    if p_request_type is null or p_request_type not in (
        'risk_grade_adjustment', 'review_criteria_change', 'new_keyword_registration'
    ) or char_length(v_detail) > 4000 then
        raise exception 'invalid request content' using errcode = '22023';
    end if;

    update public.kra_keyword_requests
    set request_type = p_request_type, request_detail = v_detail
    where id = p_request_id and requester_id = v_user_id
    returning * into v_request;
    if not found then
        raise exception 'own request not found' using errcode = '42501';
    end if;

    insert into public.kra_keyword_request_messages as initial
        (request_id, author_id, author_email, author_role, is_initial,
         body, status, created_at)
    values (
        v_request.id, v_user_id, v_request.requester_email, 'user', true,
        coalesce(nullif(v_detail, ''), '최초 문의 등록'),
        v_request.status, v_request.created_at
    )
    on conflict (request_id) where is_initial
    do update set body = excluded.body
    where initial.author_id = v_user_id and initial.author_role = 'user';
    if not found then
        raise exception 'initial inquiry owner mismatch' using errcode = '42501';
    end if;

    return to_jsonb(v_request);
end;
$function$;

revoke all on function private.kra_edit_own_keyword_request(uuid, text, text)
    from public, anon, authenticated;
grant execute on function private.kra_edit_own_keyword_request(uuid, text, text)
    to authenticated;

create or replace function public.kra_edit_own_keyword_request(
    p_request_id uuid,
    p_request_type text,
    p_request_detail text
)
returns jsonb
language sql
security invoker
set search_path = ''
as $function$
    select private.kra_edit_own_keyword_request(
        p_request_id, p_request_type, p_request_detail
    );
$function$;

revoke all on function public.kra_edit_own_keyword_request(uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.kra_edit_own_keyword_request(uuid, text, text)
    to authenticated;

drop policy if exists kra_keyword_requests_delete_owner
    on public.kra_keyword_requests;
create policy kra_keyword_requests_delete_owner
    on public.kra_keyword_requests for delete to authenticated
    using (requester_id = (select auth.uid()));
