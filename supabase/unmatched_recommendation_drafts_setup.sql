-- Keep in-progress normalization recommendations private to each signed-in user.
create table if not exists public.kra_unmatched_recommendation_drafts (
    user_id uuid primary key references auth.users(id) on delete cascade,
    payload jsonb not null check (jsonb_typeof(payload) = 'object'),
    updated_at timestamptz not null default now()
);

alter table public.kra_unmatched_recommendation_drafts enable row level security;
revoke all on public.kra_unmatched_recommendation_drafts
    from public, anon, authenticated;
grant all on public.kra_unmatched_recommendation_drafts to service_role;
drop policy if exists unmatched_recommendation_drafts_server_only
    on public.kra_unmatched_recommendation_drafts;
create policy unmatched_recommendation_drafts_server_only
    on public.kra_unmatched_recommendation_drafts
    for all to service_role using (true) with check (true);
