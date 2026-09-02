-- Aurum Console Milestone 2: sanitized MT5 observations and reconciliation.
-- This migration adds reporting only. It creates no broker, execution,
-- command-transition, Order, or Position mutation function.

create table public.mt5_account_observations (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete restrict,
  worker_id text not null,
  account_fingerprint text not null,
  server_fingerprint text not null,
  masked_login text not null,
  masked_server text not null,
  trade_mode text not null check (trade_mode in ('demo', 'contest', 'real', 'unknown')),
  verification_state text not null check (verification_state in (
    'verified_demo_bound', 'verified_demo_unbound', 'trade_mode_unknown',
    'contest_account_blocked', 'real_account_blocked', 'account_binding_mismatch'
  )),
  currency text,
  leverage integer check (leverage is null or leverage > 0),
  observed_at timestamptz not null,
  source text not null check (source in ('mt5', 'fake_mt5')),
  adapter_version text not null,
  trace_id text not null,
  schema_version text not null check (schema_version = '1'),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (account_fingerprint ~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$'),
  check (server_fingerprint ~ '^mt5-server-v1:[A-Za-z0-9:_-]{4,128}$'),
  check (masked_login ~ '^••••[0-9]{0,4}$'),
  check (pg_catalog.length(masked_server) between 5 and 32),
  check (pg_catalog.length(worker_id) between 1 and 160),
  check (pg_catalog.length(adapter_version) between 1 and 160),
  check (pg_catalog.length(trace_id) between 1 and 160),
  unique (id, owner_id),
  unique (owner_id, trace_id, observed_at)
);

create index mt5_account_observations_owner_time_idx
  on public.mt5_account_observations (owner_id, observed_at desc);

create table public.mt5_symbol_observations (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete restrict,
  worker_id text not null,
  account_fingerprint text not null,
  canonical_symbol text not null check (canonical_symbol = 'XAUUSD'),
  broker_symbol text not null,
  specification_fingerprint text not null,
  normalized_specification jsonb not null,
  usability_state text not null check (
    usability_state in ('usable', 'not_visible', 'incomplete', 'invalid')
  ),
  unusable_reason text,
  observed_at timestamptz not null,
  source text not null check (source in ('mt5', 'fake_mt5')),
  adapter_version text not null,
  trace_id text not null,
  schema_version text not null check (schema_version = '1'),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (account_fingerprint ~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$'),
  check (specification_fingerprint ~ '^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$'),
  check (pg_catalog.length(worker_id) between 1 and 160),
  check (pg_catalog.length(broker_symbol) between 1 and 160),
  check (pg_catalog.length(adapter_version) between 1 and 160),
  check (pg_catalog.length(trace_id) between 1 and 160),
  check (unusable_reason is null or unusable_reason ~ '^[A-Z][A-Z0-9_]{0,159}$'),
  unique (id, owner_id),
  unique (owner_id, account_fingerprint, broker_symbol, specification_fingerprint)
);

create index mt5_symbol_observations_owner_time_idx
  on public.mt5_symbol_observations (owner_id, observed_at desc);

create table public.mt5_latest_tick_observations (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete restrict,
  worker_id text not null,
  account_fingerprint text not null,
  broker_symbol text not null,
  bid numeric not null check (bid > 0),
  ask numeric not null check (ask > 0 and ask >= bid),
  spread_price numeric not null check (spread_price >= 0 and spread_price = ask - bid),
  spread_points numeric not null check (spread_points >= 0),
  tick_at timestamptz not null,
  observed_at timestamptz not null,
  age_seconds numeric not null check (age_seconds >= 0),
  freshness text not null check (
    freshness in ('live', 'delayed', 'stale', 'future_invalid', 'unavailable')
  ),
  source text not null check (source in ('mt5', 'fake_mt5')),
  adapter_version text not null,
  trace_id text not null,
  schema_version text not null check (schema_version = '1'),
  version integer not null default 1 check (version > 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (account_fingerprint ~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$'),
  check (pg_catalog.length(worker_id) between 1 and 160),
  check (pg_catalog.length(broker_symbol) between 1 and 160),
  unique (id, owner_id),
  unique (owner_id, account_fingerprint, broker_symbol)
);

create table public.mt5_reconciliation_runs (
  id uuid primary key,
  owner_id uuid not null references public.profiles (id) on delete restrict,
  worker_id text not null,
  status text not null check (status in ('running', 'completed')),
  outcome text check (outcome is null or outcome in ('matched', 'mismatch', 'incomplete')),
  reason_code text not null,
  account_fingerprint text,
  server_fingerprint text,
  broker_symbol text,
  symbol_specification_fingerprint text,
  open_position_count integer not null default 0 check (open_position_count >= 0),
  active_order_count integer not null default 0 check (active_order_count >= 0),
  order_history_count integer not null default 0 check (order_history_count >= 0),
  deal_history_count integer not null default 0 check (deal_history_count >= 0),
  mismatch_count integer not null default 0 check (mismatch_count >= 0),
  report_hash text not null check (report_hash ~ '^[a-f0-9]{32}$'),
  trace_id text not null,
  started_at timestamptz not null,
  completed_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (reason_code ~ '^[A-Z][A-Z0-9_]{0,159}$'),
  check (pg_catalog.length(worker_id) between 1 and 160),
  check (pg_catalog.length(trace_id) between 1 and 160),
  check (
    (status = 'running' and outcome is null and completed_at is null)
    or (status = 'completed' and outcome is not null and completed_at is not null)
  ),
  check (completed_at is null or completed_at >= started_at),
  unique (id, owner_id)
);

create index mt5_reconciliation_runs_owner_time_idx
  on public.mt5_reconciliation_runs (owner_id, started_at desc);

create table public.mt5_reconciliation_mismatches (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  reconciliation_id uuid not null,
  worker_id text not null,
  category text not null check (category in (
    'UNEXPECTED_BROKER_POSITION', 'DATABASE_POSITION_MISSING_AT_BROKER',
    'UNEXPECTED_ACTIVE_ORDER', 'DATABASE_ORDER_MISSING_AT_BROKER',
    'EXECUTION_RESULT_UNCERTAIN', 'ACCOUNT_CHANGED', 'SERVER_CHANGED',
    'SYMBOL_SPEC_CHANGED', 'HISTORY_WINDOW_INCOMPLETE', 'CLOCK_INCONSISTENCY'
  )),
  severity text not null check (severity in ('warning', 'critical')),
  resource_type text not null,
  resource_reference text not null,
  reason_code text,
  resolution_state text not null default 'unresolved' check (
    resolution_state = 'unresolved'
  ),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.length(worker_id) between 1 and 160),
  check (pg_catalog.length(resource_type) between 1 and 160),
  check (pg_catalog.length(resource_reference) between 1 and 160),
  check (reason_code is null or reason_code ~ '^[A-Z][A-Z0-9_]{0,159}$'),
  unique (id, owner_id),
  constraint mt5_reconciliation_mismatch_identity_unique
    unique (owner_id, reconciliation_id, category, resource_reference),
  foreign key (reconciliation_id, owner_id)
    references public.mt5_reconciliation_runs (id, owner_id) on delete restrict
);

create or replace function private.m2_reject_append_only_mutation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  raise exception using errcode = '55000', message = 'AURUM_APPEND_ONLY_RECORD';
end
$function$;

create trigger mt5_account_observations_append_only
before update or delete on public.mt5_account_observations
for each row execute function private.m2_reject_append_only_mutation();
create trigger mt5_symbol_observations_append_only
before update or delete on public.mt5_symbol_observations
for each row execute function private.m2_reject_append_only_mutation();
create trigger mt5_reconciliation_mismatches_append_only
before update or delete on public.mt5_reconciliation_mismatches
for each row execute function private.m2_reject_append_only_mutation();

grant create on schema private to aurum_function_owner;
alter function private.m2_reject_append_only_mutation()
  owner to aurum_function_owner;
revoke all on function private.m2_reject_append_only_mutation() from public;

alter table public.mt5_account_observations enable row level security;
alter table public.mt5_account_observations force row level security;
alter table public.mt5_symbol_observations enable row level security;
alter table public.mt5_symbol_observations force row level security;
alter table public.mt5_latest_tick_observations enable row level security;
alter table public.mt5_latest_tick_observations force row level security;
alter table public.mt5_reconciliation_runs enable row level security;
alter table public.mt5_reconciliation_runs force row level security;
alter table public.mt5_reconciliation_mismatches enable row level security;
alter table public.mt5_reconciliation_mismatches force row level security;

create policy mt5_account_observations_owner_select
on public.mt5_account_observations for select to authenticated
using (owner_id = (select auth.uid()));
create policy mt5_symbol_observations_owner_select
on public.mt5_symbol_observations for select to authenticated
using (owner_id = (select auth.uid()));
create policy mt5_latest_tick_observations_owner_select
on public.mt5_latest_tick_observations for select to authenticated
using (owner_id = (select auth.uid()));
create policy mt5_reconciliation_runs_owner_select
on public.mt5_reconciliation_runs for select to authenticated
using (owner_id = (select auth.uid()));
create policy mt5_reconciliation_mismatches_owner_select
on public.mt5_reconciliation_mismatches for select to authenticated
using (owner_id = (select auth.uid()));

create policy mt5_account_observations_function_select
on public.mt5_account_observations for select to aurum_function_owner using (true);
create policy mt5_account_observations_function_insert
on public.mt5_account_observations for insert to aurum_function_owner with check (true);
create policy mt5_symbol_observations_function_select
on public.mt5_symbol_observations for select to aurum_function_owner using (true);
create policy mt5_symbol_observations_function_insert
on public.mt5_symbol_observations for insert to aurum_function_owner with check (true);
create policy mt5_latest_tick_observations_function_select
on public.mt5_latest_tick_observations for select to aurum_function_owner using (true);
create policy mt5_latest_tick_observations_function_insert
on public.mt5_latest_tick_observations for insert to aurum_function_owner with check (true);
create policy mt5_latest_tick_observations_function_update
on public.mt5_latest_tick_observations for update to aurum_function_owner
using (true) with check (true);
create policy mt5_reconciliation_runs_function_select
on public.mt5_reconciliation_runs for select to aurum_function_owner using (true);
create policy mt5_reconciliation_runs_function_insert
on public.mt5_reconciliation_runs for insert to aurum_function_owner with check (true);
create policy mt5_reconciliation_runs_function_update
on public.mt5_reconciliation_runs for update to aurum_function_owner
using (true) with check (true);
create policy mt5_reconciliation_mismatches_function_select
on public.mt5_reconciliation_mismatches for select to aurum_function_owner using (true);
create policy mt5_reconciliation_mismatches_function_insert
on public.mt5_reconciliation_mismatches for insert to aurum_function_owner with check (true);
create policy broker_orders_function_select_m2 on public.broker_orders
for select to aurum_function_owner using (true);

revoke all on
  public.mt5_account_observations,
  public.mt5_symbol_observations,
  public.mt5_latest_tick_observations,
  public.mt5_reconciliation_runs,
  public.mt5_reconciliation_mismatches
from public, anon, authenticated, aurum_worker, aurum_function_owner;
grant select on
  public.mt5_account_observations,
  public.mt5_symbol_observations,
  public.mt5_latest_tick_observations,
  public.mt5_reconciliation_runs,
  public.mt5_reconciliation_mismatches
to authenticated;
grant select, insert on public.mt5_account_observations to aurum_function_owner;
grant select, insert on public.mt5_symbol_observations to aurum_function_owner;
grant select, insert, update on public.mt5_latest_tick_observations to aurum_function_owner;
grant select, insert, update on public.mt5_reconciliation_runs to aurum_function_owner;
grant select, insert on public.mt5_reconciliation_mismatches to aurum_function_owner;
grant select on public.broker_orders to aurum_function_owner;

create or replace function private.m2_worker_authorized()
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select private.worker_owner_id() is not null
    and private.worker_identifier() is not null
    and private.safe_worker_text(private.worker_identifier())
    and private.worker_identifier() ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$'
$function$;

create or replace function private.jsonb_exact_keys(payload jsonb, expected text[])
returns boolean
language sql
immutable
security definer
set search_path = ''
as $function$
  select payload is not null
    and pg_catalog.jsonb_typeof(payload) = 'object'
    and (
      select coalesce(pg_catalog.array_agg(key order by key), '{}'::text[])
      from pg_catalog.jsonb_object_keys(payload) as key
    ) = (
      select pg_catalog.array_agg(value order by value)
      from pg_catalog.unnest(expected) as value
    )
$function$;

create or replace function private.json_decimal_string(payload jsonb, key_name text)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $function$
declare
  parsed numeric;
begin
  if pg_catalog.jsonb_typeof(payload -> key_name) <> 'string'
    or payload ->> key_name !~ '^-?(0|[1-9][0-9]*)([.][0-9]+)?$' then
    return false;
  end if;
  parsed := (payload ->> key_name)::numeric;
  return private.numeric_is_finite(parsed);
exception when others then
  return false;
end
$function$;

alter function private.m2_worker_authorized() owner to aurum_function_owner;
alter function private.jsonb_exact_keys(jsonb, text[]) owner to aurum_function_owner;
alter function private.json_decimal_string(jsonb, text) owner to aurum_function_owner;
revoke create on schema private from aurum_function_owner;
revoke all on function private.m2_worker_authorized() from public, anon, authenticated, aurum_worker;
revoke all on function private.jsonb_exact_keys(jsonb, text[]) from public, anon, authenticated, aurum_worker;
revoke all on function private.json_decimal_string(jsonb, text) from public, anon, authenticated, aurum_worker;

create or replace function public.worker_record_mt5_account_observation(observation jsonb)
returns text
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  observation_id uuid;
begin
  if not private.m2_worker_authorized() then return 'WORKER_UNAUTHORIZED'; end if;
  if not private.jsonb_exact_keys(observation, array[
      'account_fingerprint', 'adapter_version', 'currency', 'leverage',
      'masked_login', 'masked_server', 'observed_at', 'schema_version',
      'server_fingerprint', 'source', 'trace_id', 'trade_mode',
      'verification_state'
    ])
    or observation ->> 'account_fingerprint' !~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$'
    or observation ->> 'server_fingerprint' !~ '^mt5-server-v1:[A-Za-z0-9:_-]{4,128}$'
    or observation ->> 'masked_login' !~ '^••••[0-9]{0,4}$'
    or observation ->> 'masked_server' !~ '^[A-Za-z0-9]{1,16}…[a-f0-9]{4}$'
    or not private.safe_worker_text(observation ->> 'masked_server')
    or not private.safe_worker_text(observation ->> 'trace_id')
    or observation ->> 'trade_mode' not in ('demo', 'contest', 'real', 'unknown')
    or observation ->> 'verification_state' not in (
      'verified_demo_bound', 'verified_demo_unbound', 'trade_mode_unknown',
      'contest_account_blocked', 'real_account_blocked', 'account_binding_mismatch'
    )
    or (observation ->> 'trade_mode' = 'demo'
      and observation ->> 'verification_state' not in (
        'verified_demo_bound', 'verified_demo_unbound', 'account_binding_mismatch'
      ))
    or (observation ->> 'trade_mode' = 'contest'
      and observation ->> 'verification_state' <> 'contest_account_blocked')
    or (observation ->> 'trade_mode' = 'real'
      and observation ->> 'verification_state' <> 'real_account_blocked')
    or (observation ->> 'trade_mode' = 'unknown'
      and observation ->> 'verification_state' <> 'trade_mode_unknown')
    or observation ->> 'source' not in ('mt5', 'fake_mt5')
    or observation ->> 'schema_version' <> '1' then
    return 'INVALID_ACCOUNT_OBSERVATION';
  end if;
  begin
    insert into public.mt5_account_observations (
      owner_id, worker_id, account_fingerprint, server_fingerprint,
      masked_login, masked_server, trade_mode, verification_state,
      currency, leverage, observed_at, source, adapter_version, trace_id,
      schema_version
    ) values (
      v_owner_id, v_worker_id, observation ->> 'account_fingerprint',
      observation ->> 'server_fingerprint', observation ->> 'masked_login',
      observation ->> 'masked_server', observation ->> 'trade_mode',
      observation ->> 'verification_state', observation ->> 'currency',
      nullif(observation ->> 'leverage', '')::integer,
      (observation ->> 'observed_at')::timestamptz,
      observation ->> 'source', observation ->> 'adapter_version',
      observation ->> 'trace_id', observation ->> 'schema_version'
    )
    on conflict (owner_id, trace_id, observed_at) do nothing
    returning id into observation_id;
  exception when others then
    return 'INVALID_ACCOUNT_OBSERVATION';
  end;
  if observation_id is null then return 'IDEMPOTENT_REPLAY'; end if;
  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id, 'mt5_account_observation_recorded',
    'mt5_account_observation', observation_id, observation_id, null, 1,
    pg_catalog.jsonb_build_object('traceId', observation ->> 'trace_id')
  );
  return 'OBSERVATION_RECORDED';
end
$function$;

create or replace function public.worker_record_mt5_symbol_observation(observation jsonb)
returns text
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  observation_id uuid;
begin
  if not private.m2_worker_authorized() then return 'WORKER_UNAUTHORIZED'; end if;
  if not private.jsonb_exact_keys(observation, array[
      'account_fingerprint', 'adapter_version', 'base_currency',
      'broker_symbol', 'canonical_symbol', 'contract_size', 'description',
      'digits', 'expiration_mode', 'filling_mode', 'freeze_level',
      'margin_currency', 'maximum_volume', 'minimum_volume', 'observed_at',
      'order_mode', 'point', 'profit_currency', 'raw_diagnostic_codes',
      'schema_version', 'source', 'specification_fingerprint', 'stops_level',
      'symbol_path', 'tick_size', 'tick_value', 'tick_value_loss',
      'tick_value_profit', 'trace_id', 'trade_calculation_mode', 'trade_mode',
      'unusable_reason', 'usability_state', 'volume_step'
    ])
    or observation ->> 'canonical_symbol' <> 'XAUUSD'
    or observation ->> 'account_fingerprint' !~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$'
    or observation ->> 'specification_fingerprint' !~ '^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$'
    or not private.safe_worker_text(observation ->> 'broker_symbol')
    or not private.safe_worker_text(observation ->> 'trace_id')
    or observation ->> 'base_currency' !~ '^[A-Z]{3}$'
    or observation ->> 'profit_currency' !~ '^[A-Z]{3}$'
    or observation ->> 'margin_currency' !~ '^[A-Z]{3}$'
    or not private.json_decimal_string(observation, 'point')
    or not private.json_decimal_string(observation, 'tick_size')
    or not private.json_decimal_string(observation, 'tick_value')
    or not private.json_decimal_string(observation, 'tick_value_profit')
    or not private.json_decimal_string(observation, 'tick_value_loss')
    or not private.json_decimal_string(observation, 'contract_size')
    or not private.json_decimal_string(observation, 'minimum_volume')
    or not private.json_decimal_string(observation, 'maximum_volume')
    or not private.json_decimal_string(observation, 'volume_step')
    or (observation ->> 'point')::numeric <= 0
    or (observation ->> 'tick_size')::numeric <= 0
    or (observation ->> 'contract_size')::numeric <= 0
    or (observation ->> 'minimum_volume')::numeric <= 0
    or (observation ->> 'maximum_volume')::numeric
      < (observation ->> 'minimum_volume')::numeric
    or (observation ->> 'volume_step')::numeric <= 0
    or observation ->> 'usability_state' not in ('usable', 'not_visible', 'incomplete', 'invalid')
    or observation ->> 'schema_version' <> '1' then
    return 'INVALID_SYMBOL_OBSERVATION';
  end if;
  begin
    insert into public.mt5_symbol_observations (
      owner_id, worker_id, account_fingerprint, canonical_symbol,
      broker_symbol, specification_fingerprint, normalized_specification,
      usability_state, unusable_reason, observed_at, source,
      adapter_version, trace_id, schema_version
    ) values (
      v_owner_id, v_worker_id, observation ->> 'account_fingerprint',
      'XAUUSD', observation ->> 'broker_symbol',
      observation ->> 'specification_fingerprint', observation,
      observation ->> 'usability_state', observation ->> 'unusable_reason',
      (observation ->> 'observed_at')::timestamptz,
      observation ->> 'source', observation ->> 'adapter_version',
      observation ->> 'trace_id', observation ->> 'schema_version'
    )
    on conflict (
      owner_id, account_fingerprint, broker_symbol, specification_fingerprint
    ) do nothing returning id into observation_id;
  exception when others then
    return 'INVALID_SYMBOL_OBSERVATION';
  end;
  if observation_id is null then return 'IDEMPOTENT_REPLAY'; end if;
  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id, 'mt5_symbol_observation_recorded',
    'mt5_symbol_observation', observation_id, observation_id, null, 1,
    pg_catalog.jsonb_build_object(
      'brokerSymbol', observation ->> 'broker_symbol',
      'specificationFingerprint', observation ->> 'specification_fingerprint'
    )
  );
  return 'OBSERVATION_RECORDED';
end
$function$;

create or replace function public.worker_upsert_mt5_latest_tick(observation jsonb)
returns text
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  tick_id uuid;
  tick_version integer;
begin
  if not private.m2_worker_authorized() then return 'WORKER_UNAUTHORIZED'; end if;
  if not private.jsonb_exact_keys(observation, array[
      'account_fingerprint', 'adapter_version', 'age_seconds', 'ask', 'bid',
      'freshness', 'observed_at', 'schema_version', 'source', 'spread_points',
      'spread_price', 'symbol', 'tick_at', 'trace_id'
    ])
    or not private.json_decimal_string(observation, 'bid')
    or not private.json_decimal_string(observation, 'ask')
    or not private.json_decimal_string(observation, 'spread_price')
    or not private.json_decimal_string(observation, 'spread_points')
    or not private.json_decimal_string(observation, 'age_seconds')
    or (observation ->> 'bid')::numeric <= 0
    or (observation ->> 'ask')::numeric < (observation ->> 'bid')::numeric
    or (observation ->> 'spread_price')::numeric
      <> (observation ->> 'ask')::numeric - (observation ->> 'bid')::numeric
    or observation ->> 'freshness' not in (
      'live', 'delayed', 'stale', 'future_invalid', 'unavailable'
    )
    or not private.safe_worker_text(observation ->> 'symbol') then
    return 'INVALID_TICK_OBSERVATION';
  end if;
  begin
    insert into public.mt5_latest_tick_observations as tick_target (
      owner_id, worker_id, account_fingerprint, broker_symbol,
      bid, ask, spread_price, spread_points, tick_at, observed_at,
      age_seconds, freshness, source, adapter_version, trace_id, schema_version
    ) values (
      v_owner_id, v_worker_id, observation ->> 'account_fingerprint',
      observation ->> 'symbol', (observation ->> 'bid')::numeric,
      (observation ->> 'ask')::numeric,
      (observation ->> 'spread_price')::numeric,
      (observation ->> 'spread_points')::numeric,
      (observation ->> 'tick_at')::timestamptz,
      (observation ->> 'observed_at')::timestamptz,
      (observation ->> 'age_seconds')::numeric,
      observation ->> 'freshness', observation ->> 'source',
      observation ->> 'adapter_version', observation ->> 'trace_id',
      observation ->> 'schema_version'
    )
    on conflict (owner_id, account_fingerprint, broker_symbol) do update set
      worker_id = excluded.worker_id,
      bid = excluded.bid, ask = excluded.ask,
      spread_price = excluded.spread_price,
      spread_points = excluded.spread_points,
      tick_at = excluded.tick_at, observed_at = excluded.observed_at,
      age_seconds = excluded.age_seconds, freshness = excluded.freshness,
      source = excluded.source, adapter_version = excluded.adapter_version,
      trace_id = excluded.trace_id, schema_version = excluded.schema_version,
      version = tick_target.version + 1,
      updated_at = pg_catalog.clock_timestamp()
    where excluded.observed_at >= tick_target.observed_at
    returning id, version into tick_id, tick_version;
  exception when others then
    return 'INVALID_TICK_OBSERVATION';
  end;
  if tick_id is null then return 'STALE_TICK_IGNORED'; end if;
  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id, 'mt5_latest_tick_recorded',
    'mt5_latest_tick_observation', tick_id, tick_id,
    case tick_version when 1 then null else tick_version - 1 end,
    tick_version,
    pg_catalog.jsonb_build_object(
      'symbol', observation ->> 'symbol', 'freshness', observation ->> 'freshness'
    )
  );
  return 'TICK_RECORDED';
end
$function$;

create or replace function public.worker_read_mt5_reconciliation_state()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
begin
  if not private.m2_worker_authorized() then
    return pg_catalog.jsonb_build_object('result_code', 'WORKER_UNAUTHORIZED');
  end if;
  return pg_catalog.jsonb_build_object(
    'position_tickets', coalesce((
      select pg_catalog.jsonb_agg(position_row.broker_position_reference order by position_row.broker_position_reference)
      from public.positions as position_row
      where position_row.owner_id = v_owner_id and position_row.status <> 'closed'
    ), '[]'::jsonb),
    'active_order_tickets', coalesce((
      select pg_catalog.jsonb_agg(order_row.broker_order_reference order by order_row.broker_order_reference)
      from public.broker_orders as order_row
      where order_row.owner_id = v_owner_id
        and order_row.broker_order_reference is not null
        and order_row.status in ('recorded', 'submitted', 'accepted')
    ), '[]'::jsonb),
    'executing_command_ids', coalesce((
      select pg_catalog.jsonb_agg(command_row.id::text order by command_row.id::text)
      from public.system_commands as command_row
      where command_row.owner_id = v_owner_id and command_row.status = 'executing'
    ), '[]'::jsonb),
    'account_fingerprint', (
      select account_row.account_fingerprint
      from public.mt5_account_observations as account_row
      where account_row.owner_id = v_owner_id
      order by account_row.observed_at desc, account_row.id desc limit 1
    ),
    'server_fingerprint', (
      select account_row.server_fingerprint
      from public.mt5_account_observations as account_row
      where account_row.owner_id = v_owner_id
      order by account_row.observed_at desc, account_row.id desc limit 1
    ),
    'broker_symbol', (
      select symbol_row.broker_symbol
      from public.mt5_symbol_observations as symbol_row
      where symbol_row.owner_id = v_owner_id
      order by symbol_row.observed_at desc, symbol_row.id desc limit 1
    ),
    'symbol_specification_fingerprint', (
      select symbol_row.specification_fingerprint
      from public.mt5_symbol_observations as symbol_row
      where symbol_row.owner_id = v_owner_id
      order by symbol_row.observed_at desc, symbol_row.id desc limit 1
    ),
    'history_window_complete', true
  );
end
$function$;

create or replace function public.worker_begin_reconciliation(report jsonb)
returns text
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  run_id uuid;
  v_report_hash text := pg_catalog.md5(report::text);
begin
  if not private.m2_worker_authorized() then return 'WORKER_UNAUTHORIZED'; end if;
  if not private.jsonb_exact_keys(report, array[
      'account_fingerprint', 'active_order_count', 'adapter_version',
      'completed_at', 'deal_history_count', 'mismatches', 'observed_at',
      'open_position_count', 'order_history_count', 'outcome', 'reason_code',
      'reconciliation_id', 'schema_version', 'server_fingerprint', 'source',
      'started_at', 'symbol_specification_fingerprint', 'trace_id'
    ])
    or not private.is_uuid(report ->> 'reconciliation_id')
    or not private.safe_worker_text(report ->> 'trace_id')
    or not private.safe_worker_text(report ->> 'adapter_version')
    or report ->> 'source' <> 'mt5'
    or report ->> 'schema_version' <> '1'
    or pg_catalog.jsonb_typeof(report -> 'mismatches') <> 'array'
    or report ->> 'open_position_count' !~ '^[0-9]+$'
    or report ->> 'active_order_count' !~ '^[0-9]+$'
    or report ->> 'order_history_count' !~ '^[0-9]+$'
    or report ->> 'deal_history_count' !~ '^[0-9]+$'
    or (report ->> 'account_fingerprint' is not null
      and report ->> 'account_fingerprint' !~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$')
    or (report ->> 'server_fingerprint' is not null
      and report ->> 'server_fingerprint' !~ '^mt5-server-v1:[A-Za-z0-9:_-]{4,128}$')
    or (report ->> 'symbol_specification_fingerprint' is not null
      and report ->> 'symbol_specification_fingerprint' !~ '^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$')
    or report ->> 'reason_code' !~ '^[A-Z][A-Z0-9_]{0,159}$' then
    return 'INVALID_RECONCILIATION';
  end if;
  begin
    insert into public.mt5_reconciliation_runs (
      id, owner_id, worker_id, status, reason_code, account_fingerprint,
      server_fingerprint, symbol_specification_fingerprint, trace_id, started_at,
      report_hash
    ) values (
      (report ->> 'reconciliation_id')::uuid, v_owner_id, v_worker_id,
      'running', report ->> 'reason_code', report ->> 'account_fingerprint',
      report ->> 'server_fingerprint',
      report ->> 'symbol_specification_fingerprint', report ->> 'trace_id',
      (report ->> 'started_at')::timestamptz, v_report_hash
    ) on conflict (id) do nothing returning id into run_id;
  exception when others then
    return 'INVALID_RECONCILIATION';
  end;
  if run_id is null then
    if exists (
      select 1 from public.mt5_reconciliation_runs existing
      where existing.id = (report ->> 'reconciliation_id')::uuid
        and existing.owner_id = v_owner_id
        and existing.trace_id = report ->> 'trace_id'
        and existing.report_hash = v_report_hash
    ) then return 'IDEMPOTENT_REPLAY'; end if;
    return 'IDEMPOTENCY_CONFLICT';
  end if;
  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id, 'mt5_reconciliation_started',
    'mt5_reconciliation_run', run_id, run_id, null, 1,
    pg_catalog.jsonb_build_object('traceId', report ->> 'trace_id')
  );
  return 'RECONCILIATION_STARTED';
end
$function$;

create or replace function public.worker_record_reconciliation_mismatch(
  reconciliation_id uuid,
  mismatch jsonb
)
returns text
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  mismatch_id uuid;
begin
  if not private.m2_worker_authorized() then return 'WORKER_UNAUTHORIZED'; end if;
  if reconciliation_id is null
    or not private.jsonb_exact_keys(mismatch, array[
      'category', 'reason_code', 'resource_reference', 'resource_type', 'severity'
    ])
    or mismatch ->> 'category' not in (
      'UNEXPECTED_BROKER_POSITION', 'DATABASE_POSITION_MISSING_AT_BROKER',
      'UNEXPECTED_ACTIVE_ORDER', 'DATABASE_ORDER_MISSING_AT_BROKER',
      'EXECUTION_RESULT_UNCERTAIN', 'ACCOUNT_CHANGED', 'SERVER_CHANGED',
      'SYMBOL_SPEC_CHANGED', 'HISTORY_WINDOW_INCOMPLETE', 'CLOCK_INCONSISTENCY'
    )
    or mismatch ->> 'severity' not in ('warning', 'critical')
    or not private.safe_worker_text(mismatch ->> 'resource_type')
    or not private.safe_worker_text(mismatch ->> 'resource_reference')
    or (mismatch ->> 'reason_code' is not null
      and mismatch ->> 'reason_code' !~ '^[A-Z][A-Z0-9_]{0,159}$') then
    return 'INVALID_RECONCILIATION_MISMATCH';
  end if;
  insert into public.mt5_reconciliation_mismatches (
    owner_id, reconciliation_id, worker_id, category, severity,
    resource_type, resource_reference, reason_code
  ) values (
    v_owner_id, reconciliation_id, v_worker_id, mismatch ->> 'category',
    mismatch ->> 'severity', mismatch ->> 'resource_type',
    mismatch ->> 'resource_reference', mismatch ->> 'reason_code'
  ) on conflict on constraint mt5_reconciliation_mismatch_identity_unique
  do nothing returning id into mismatch_id;
  if mismatch_id is null then return 'IDEMPOTENT_REPLAY'; end if;
  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id, 'mt5_reconciliation_mismatch_recorded',
    'mt5_reconciliation_mismatch', mismatch_id, reconciliation_id,
    null, 1,
    pg_catalog.jsonb_build_object('category', mismatch ->> 'category')
  );
  return 'MISMATCH_RECORDED';
exception when foreign_key_violation then
  return 'RECONCILIATION_NOT_FOUND';
end
$function$;

create or replace function public.worker_complete_reconciliation(report jsonb)
returns text
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  run_id uuid;
  existing public.mt5_reconciliation_runs%rowtype;
  v_report_hash text := pg_catalog.md5(report::text);
begin
  if not private.m2_worker_authorized() then return 'WORKER_UNAUTHORIZED'; end if;
  if not private.jsonb_exact_keys(report, array[
      'account_fingerprint', 'active_order_count', 'adapter_version',
      'completed_at', 'deal_history_count', 'mismatches', 'observed_at',
      'open_position_count', 'order_history_count', 'outcome', 'reason_code',
      'reconciliation_id', 'schema_version', 'server_fingerprint', 'source',
      'started_at', 'symbol_specification_fingerprint', 'trace_id'
    ])
    or not private.is_uuid(report ->> 'reconciliation_id')
    or not private.safe_worker_text(report ->> 'trace_id')
    or not private.safe_worker_text(report ->> 'adapter_version')
    or report ->> 'source' <> 'mt5'
    or report ->> 'schema_version' <> '1'
    or pg_catalog.jsonb_typeof(report -> 'mismatches') <> 'array'
    or report ->> 'open_position_count' !~ '^[0-9]+$'
    or report ->> 'active_order_count' !~ '^[0-9]+$'
    or report ->> 'order_history_count' !~ '^[0-9]+$'
    or report ->> 'deal_history_count' !~ '^[0-9]+$'
    or (report ->> 'account_fingerprint' is not null
      and report ->> 'account_fingerprint' !~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$')
    or (report ->> 'server_fingerprint' is not null
      and report ->> 'server_fingerprint' !~ '^mt5-server-v1:[A-Za-z0-9:_-]{4,128}$')
    or (report ->> 'symbol_specification_fingerprint' is not null
      and report ->> 'symbol_specification_fingerprint' !~ '^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$')
    or report ->> 'outcome' not in ('matched', 'mismatch', 'incomplete')
    or report ->> 'reason_code' !~ '^[A-Z][A-Z0-9_]{0,159}$' then
    return 'INVALID_RECONCILIATION';
  end if;
  select * into existing from public.mt5_reconciliation_runs run
  where run.id = (report ->> 'reconciliation_id')::uuid
    and run.owner_id = v_owner_id for update;
  if not found then return 'RECONCILIATION_NOT_FOUND'; end if;
  if existing.report_hash <> v_report_hash then
    return 'IDEMPOTENCY_CONFLICT';
  end if;
  if existing.status = 'completed' then
    return 'IDEMPOTENT_REPLAY';
  end if;
  update public.mt5_reconciliation_runs run set
    status = 'completed', outcome = report ->> 'outcome',
    reason_code = report ->> 'reason_code',
    account_fingerprint = report ->> 'account_fingerprint',
    server_fingerprint = report ->> 'server_fingerprint',
    symbol_specification_fingerprint = report ->> 'symbol_specification_fingerprint',
    open_position_count = (report ->> 'open_position_count')::integer,
    active_order_count = (report ->> 'active_order_count')::integer,
    order_history_count = (report ->> 'order_history_count')::integer,
    deal_history_count = (report ->> 'deal_history_count')::integer,
    mismatch_count = pg_catalog.jsonb_array_length(report -> 'mismatches'),
    completed_at = (report ->> 'completed_at')::timestamptz,
    updated_at = pg_catalog.clock_timestamp()
  where run.id = existing.id returning run.id into run_id;
  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id, 'mt5_reconciliation_completed',
    'mt5_reconciliation_run', run_id, run_id, 1, 2,
    pg_catalog.jsonb_build_object(
      'outcome', report ->> 'outcome',
      'mismatchCount', pg_catalog.jsonb_array_length(report -> 'mismatches')
    )
  );
  return 'RECONCILIATION_COMPLETED';
exception when others then
  return 'INVALID_RECONCILIATION';
end
$function$;

grant create on schema public to aurum_function_owner;
alter function public.worker_record_mt5_account_observation(jsonb)
  owner to aurum_function_owner;
alter function public.worker_record_mt5_symbol_observation(jsonb)
  owner to aurum_function_owner;
alter function public.worker_upsert_mt5_latest_tick(jsonb)
  owner to aurum_function_owner;
alter function public.worker_read_mt5_reconciliation_state()
  owner to aurum_function_owner;
alter function public.worker_begin_reconciliation(jsonb)
  owner to aurum_function_owner;
alter function public.worker_record_reconciliation_mismatch(uuid, jsonb)
  owner to aurum_function_owner;
alter function public.worker_complete_reconciliation(jsonb)
  owner to aurum_function_owner;
revoke create on schema public from aurum_function_owner;

revoke all on function public.worker_record_mt5_account_observation(jsonb)
  from public, anon, authenticated;
revoke all on function public.worker_record_mt5_symbol_observation(jsonb)
  from public, anon, authenticated;
revoke all on function public.worker_upsert_mt5_latest_tick(jsonb)
  from public, anon, authenticated;
revoke all on function public.worker_read_mt5_reconciliation_state()
  from public, anon, authenticated;
revoke all on function public.worker_begin_reconciliation(jsonb)
  from public, anon, authenticated;
revoke all on function public.worker_record_reconciliation_mismatch(uuid, jsonb)
  from public, anon, authenticated;
revoke all on function public.worker_complete_reconciliation(jsonb)
  from public, anon, authenticated;

grant execute on function public.worker_record_mt5_account_observation(jsonb)
  to aurum_worker;
grant execute on function public.worker_record_mt5_symbol_observation(jsonb)
  to aurum_worker;
grant execute on function public.worker_upsert_mt5_latest_tick(jsonb)
  to aurum_worker;
grant execute on function public.worker_read_mt5_reconciliation_state()
  to aurum_worker;
grant execute on function public.worker_begin_reconciliation(jsonb)
  to aurum_worker;
grant execute on function public.worker_record_reconciliation_mismatch(uuid, jsonb)
  to aurum_worker;
grant execute on function public.worker_complete_reconciliation(jsonb)
  to aurum_worker;

-- Normalize ACLs as the function owner. A newly created PostgreSQL function
-- otherwise has an effective default that includes PUBLIC EXECUTE.
set local role aurum_function_owner;
revoke execute on function private.m2_reject_append_only_mutation()
  from public, anon, authenticated, aurum_worker;
revoke execute on function private.m2_worker_authorized()
  from public, anon, authenticated, aurum_worker;
revoke execute on function private.jsonb_exact_keys(jsonb, text[])
  from public, anon, authenticated, aurum_worker;
revoke execute on function private.json_decimal_string(jsonb, text)
  from public, anon, authenticated, aurum_worker;
revoke execute on function public.worker_record_mt5_account_observation(jsonb),
  public.worker_record_mt5_symbol_observation(jsonb),
  public.worker_upsert_mt5_latest_tick(jsonb),
  public.worker_read_mt5_reconciliation_state(),
  public.worker_begin_reconciliation(jsonb),
  public.worker_record_reconciliation_mismatch(uuid, jsonb),
  public.worker_complete_reconciliation(jsonb)
  from public, anon, authenticated, aurum_worker;
grant execute on function public.worker_record_mt5_account_observation(jsonb),
  public.worker_record_mt5_symbol_observation(jsonb),
  public.worker_upsert_mt5_latest_tick(jsonb),
  public.worker_read_mt5_reconciliation_state(),
  public.worker_begin_reconciliation(jsonb),
  public.worker_record_reconciliation_mismatch(uuid, jsonb),
  public.worker_complete_reconciliation(jsonb)
  to aurum_worker;
reset role;
