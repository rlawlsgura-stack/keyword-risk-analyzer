-- Assign one permanent receipt number per request, in Korean calendar days.
-- The counter row is locked by ON CONFLICT UPDATE, including concurrent inserts.
create table if not exists private.kra_keyword_request_receipt_counters (
    receipt_date date primary key,
    last_sequence integer not null check (last_sequence > 0)
);
alter table private.kra_keyword_request_receipt_counters enable row level security;
revoke all on private.kra_keyword_request_receipt_counters from public, anon, authenticated;

alter table public.kra_keyword_requests add column if not exists receipt_no text;

-- Give existing requests stable numbers in their original receipt order.
with numbered as (
    select id, (created_at at time zone 'Asia/Seoul')::date as receipt_date,
           row_number() over (
               partition by (created_at at time zone 'Asia/Seoul')::date
               order by created_at, id
           ) as sequence_no
    from public.kra_keyword_requests
)
update public.kra_keyword_requests r
set receipt_no = to_char(n.receipt_date, 'YYYYMMDD') || '_' ||
                 lpad(n.sequence_no::text, greatest(3, length(n.sequence_no::text)), '0')
from numbered n
where r.id = n.id and r.receipt_no is null;

insert into private.kra_keyword_request_receipt_counters (receipt_date, last_sequence)
select (created_at at time zone 'Asia/Seoul')::date,
       max(split_part(receipt_no, '_', 2)::integer)
from public.kra_keyword_requests
group by (created_at at time zone 'Asia/Seoul')::date
on conflict (receipt_date) do update
set last_sequence = greatest(
    private.kra_keyword_request_receipt_counters.last_sequence,
    excluded.last_sequence
);

alter table public.kra_keyword_requests alter column receipt_no set not null;
create unique index if not exists kra_keyword_requests_receipt_no_key
    on public.kra_keyword_requests (receipt_no);

create or replace function private.kra_assign_keyword_request_receipt()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    v_date date;
    v_sequence integer;
begin
    v_date := (new.created_at at time zone 'Asia/Seoul')::date;
    insert into private.kra_keyword_request_receipt_counters (receipt_date, last_sequence)
    values (v_date, 1)
    on conflict (receipt_date) do update
    set last_sequence = private.kra_keyword_request_receipt_counters.last_sequence + 1
    returning last_sequence into v_sequence;
    new.receipt_no := to_char(v_date, 'YYYYMMDD') || '_' ||
                      lpad(v_sequence::text, greatest(3, length(v_sequence::text)), '0');
    return new;
end;
$$;
revoke all on function private.kra_assign_keyword_request_receipt()
    from public, anon, authenticated;

drop trigger if exists kra_keyword_requests_assign_receipt on public.kra_keyword_requests;
create trigger kra_keyword_requests_assign_receipt
before insert on public.kra_keyword_requests
for each row execute function private.kra_assign_keyword_request_receipt();
