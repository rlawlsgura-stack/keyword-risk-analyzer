-- Pending keyword registrations from unmatched-term normalization requests.
create table if not exists public.kra_unmatched_registration_requests (
    id uuid primary key default gen_random_uuid(),
    term text not null check (char_length(btrim(term)) between 1 and 150),
    source_terms text not null default '' check (char_length(source_terms) <= 500),
    occurrences bigint not null default 0 check (occurrences between 0 and 1000000000),
    category text not null default '',
    risk text not null default '',
    criteria text not null default '',
    evidence_type text not null default '',
    alternative text not null default '-',
    created_at timestamptz not null default now()
);

alter table public.kra_unmatched_registration_requests
    add column if not exists category text not null default '',
    add column if not exists risk text not null default '',
    add column if not exists criteria text not null default '',
    add column if not exists evidence_type text not null default '',
    add column if not exists alternative text not null default '-';

create index if not exists kra_unmatched_registration_requests_created_idx
    on public.kra_unmatched_registration_requests(created_at, id);

alter table public.kra_unmatched_registration_requests enable row level security;
revoke all on public.kra_unmatched_registration_requests from public, anon, authenticated;
grant all on public.kra_unmatched_registration_requests to service_role;
