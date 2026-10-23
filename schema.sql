create extension if not exists pgcrypto;

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  filters jsonb not null,
  status text not null default 'pending' check (status in ('pending','active','unsubscribed')),
  confirm_token_hash text,
  manage_token_hash text,
  confirmation_sent_at timestamptz,
  verified_at timestamptz,
  last_scanned_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists subscriptions_status_idx on public.subscriptions(status);
create index if not exists subscriptions_confirmation_idx on public.subscriptions(confirmation_sent_at) where status='pending';

create table if not exists public.deliveries (
  id bigint generated always as identity primary key,
  subscription_id uuid not null references public.subscriptions(id) on delete cascade,
  offer_hash text not null,
  source_url text not null,
  sent_at timestamptz not null default now(),
  unique(subscription_id,offer_hash)
);
create index if not exists deliveries_subscription_idx on public.deliveries(subscription_id,sent_at desc);

-- Store only a salted hash of the network address, never the raw address.
create table if not exists public.signup_rate_limits (
  ip_hash text not null,
  bucket_start timestamptz not null,
  attempts integer not null default 0,
  primary key(ip_hash,bucket_start)
);
create or replace function public.consume_signup_rate_limit(p_ip_hash text)
returns boolean language plpgsql security definer set search_path=public as $$
declare current_bucket timestamptz;
declare attempt_count integer;
begin
  current_bucket := to_timestamp(floor(extract(epoch from now())/600)*600);
  insert into public.signup_rate_limits(ip_hash,bucket_start,attempts) values(p_ip_hash,current_bucket,1)
  on conflict(ip_hash,bucket_start) do update set attempts=public.signup_rate_limits.attempts+1
  returning attempts into attempt_count;
  delete from public.signup_rate_limits where bucket_start < now()-interval '1 day';
  return attempt_count <= 5;
end; $$;

alter table public.subscriptions enable row level security;
alter table public.deliveries enable row level security;
alter table public.signup_rate_limits enable row level security;
revoke all on public.subscriptions from anon,authenticated;
revoke all on public.deliveries from anon,authenticated;
revoke all on public.signup_rate_limits from anon,authenticated;
revoke all on function public.consume_signup_rate_limit(text) from public,anon,authenticated;
grant execute on function public.consume_signup_rate_limit(text) to service_role;
