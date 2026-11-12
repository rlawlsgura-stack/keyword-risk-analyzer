create policy kra_openai_usage_service_role_only
on public.kra_openai_usage_monthly
for all to service_role
using (true)
with check (true);
