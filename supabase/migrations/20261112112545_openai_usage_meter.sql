create table public.kra_openai_usage_monthly (
    month_start date primary key,
    request_count bigint not null default 0 check (request_count >= 0),
    input_tokens bigint not null default 0 check (input_tokens >= 0),
    output_tokens bigint not null default 0 check (output_tokens >= 0),
    cached_input_tokens bigint not null default 0 check (cached_input_tokens >= 0),
    estimated_cost_usd numeric(16, 8) not null default 0 check (estimated_cost_usd >= 0),
    cost_complete boolean not null default true,
    updated_at timestamptz not null default now()
);

alter table public.kra_openai_usage_monthly enable row level security;
revoke all on public.kra_openai_usage_monthly from anon, authenticated;
grant select, insert, update on public.kra_openai_usage_monthly to service_role;

create function public.kra_record_openai_usage(
    p_month_start date, p_request_count bigint, p_input_tokens bigint,
    p_output_tokens bigint, p_cached_input_tokens bigint,
    p_estimated_cost_usd numeric, p_cost_complete boolean
) returns void
language plpgsql security invoker set search_path = '' as $$
begin
    insert into public.kra_openai_usage_monthly as current_usage
        (month_start, request_count, input_tokens, output_tokens,
         cached_input_tokens, estimated_cost_usd, cost_complete)
    values
        (p_month_start, p_request_count, p_input_tokens, p_output_tokens,
         p_cached_input_tokens, coalesce(p_estimated_cost_usd, 0), p_cost_complete)
    on conflict (month_start) do update set
        request_count = current_usage.request_count + excluded.request_count,
        input_tokens = current_usage.input_tokens + excluded.input_tokens,
        output_tokens = current_usage.output_tokens + excluded.output_tokens,
        cached_input_tokens = current_usage.cached_input_tokens + excluded.cached_input_tokens,
        estimated_cost_usd = current_usage.estimated_cost_usd + excluded.estimated_cost_usd,
        cost_complete = current_usage.cost_complete and excluded.cost_complete,
        updated_at = now();
end;
$$;

revoke all on function public.kra_record_openai_usage(
    date, bigint, bigint, bigint, bigint, numeric, boolean
) from public, anon, authenticated;
grant execute on function public.kra_record_openai_usage(
    date, bigint, bigint, bigint, bigint, numeric, boolean
) to service_role;
