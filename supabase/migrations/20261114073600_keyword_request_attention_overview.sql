-- Preserve the existing request RLS when displaying administrator work queues.
create or replace view public.kra_keyword_request_overview
with (security_invoker = true) as
select r.id, r.receipt_no, r.requester_id, r.requester_email,
       r.kwd_no, r.keyword_name, r.request_type, r.request_detail,
       r.status, r.admin_reply, r.created_at,
       exists (
           select 1
           from public.kra_keyword_request_messages inquiry
           where inquiry.request_id = r.id
             and inquiry.author_role = 'user'
             and (
                 inquiry.status is distinct from '처리완료'
                 or not exists (
                     select 1
                     from public.kra_keyword_request_messages answer
                     where answer.reply_to_id = inquiry.id
                       and answer.author_role = 'admin'
                 )
             )
       ) as needs_attention
from public.kra_keyword_requests r;

revoke all on public.kra_keyword_request_overview from public, anon, authenticated;
grant select on public.kra_keyword_request_overview to authenticated;
