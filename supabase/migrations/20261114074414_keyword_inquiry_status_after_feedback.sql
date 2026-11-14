-- Show the overall status from every user question, including follow-ups.
create or replace view public.kra_keyword_request_overview
with (security_invoker = true) as
select r.id, r.receipt_no, r.requester_id, r.requester_email,
       r.kwd_no, r.keyword_name, r.request_type, r.request_detail,
       case
           when questions.question_count = 0 then r.status
           when questions.needs_attention then
               case when questions.has_review then '검토중' else '대기' end
           else '처리완료'
       end as status,
       r.admin_reply, r.created_at,
       coalesce(questions.needs_attention, false) as needs_attention
from public.kra_keyword_requests r
left join lateral (
    select count(*) as question_count,
           bool_or(question.status = '검토중') as has_review,
           bool_or(question.needs_attention) as needs_attention
    from (
        select inquiry.status,
               inquiry.status is distinct from '처리완료'
               or not exists (
                   select 1 from public.kra_keyword_request_messages answer
                   where answer.reply_to_id = inquiry.id
                     and answer.author_role = 'admin'
               ) as needs_attention
        from public.kra_keyword_request_messages inquiry
        where inquiry.request_id = r.id and inquiry.author_role = 'user'
    ) question
) questions on true;

-- A reply is required before an administrator can close an inquiry.
-- Changing the state does not create another feedback message.
create or replace function public.kra_admin_set_keyword_inquiry_status(
    p_request_id uuid, p_inquiry_id uuid, p_status text
) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare
    v_request_status text;
begin
    if (select auth.jwt() -> 'app_metadata' ->> 'role') is distinct from 'admin'
       or (select auth.uid()) is null then
        raise exception 'administrator access required' using errcode = '42501';
    end if;
    if p_status not in ('대기', '검토중', '처리완료') or p_status is null then
        raise exception 'invalid inquiry status' using errcode = '22023';
    end if;
    perform 1 from public.kra_keyword_requests where id = p_request_id for update;
    if not found then
        raise exception 'request was not found' using errcode = 'P0002';
    end if;
    if not exists (
        select 1 from public.kra_keyword_request_messages answer
        where answer.request_id = p_request_id
          and answer.reply_to_id = p_inquiry_id
          and answer.author_role = 'admin'
    ) then
        raise exception 'feedback is required before changing status' using errcode = '22023';
    end if;
    update public.kra_keyword_request_messages
       set status = p_status
     where id = p_inquiry_id and request_id = p_request_id
       and author_role = 'user';
    if not found then
        raise exception 'inquiry was not found' using errcode = 'P0002';
    end if;
    select status into v_request_status
    from public.kra_keyword_request_overview where id = p_request_id;
    update public.kra_keyword_requests
       set status = v_request_status
     where id = p_request_id;
    return jsonb_build_object('id', p_inquiry_id, 'status', p_status,
                              'request_status', v_request_status);
end;
$$;

revoke all on function public.kra_admin_set_keyword_inquiry_status(uuid, uuid, text)
    from public, anon, authenticated;
grant execute on function public.kra_admin_set_keyword_inquiry_status(uuid, uuid, text)
    to authenticated;
