-- Restrict the legacy table for this application without changing its contents.
alter table public.keywords enable row level security;
revoke all privileges on table public.keywords from anon, authenticated;
