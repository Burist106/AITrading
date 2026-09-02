-- Aurum Console Milestone 2 source-review patch.
--
-- This migration preserves the read-only broker boundary. It adds no broker,
-- execution, Position, command-lifecycle, or confirmation mutation RPC.

alter table public.broker_symbols
  add column base_currency text,
  add column profit_currency text,
  add column confirmed_specification_fingerprint text,
  add column confirmation_status text not null default 'unconfirmed',
  add column confirmed_at timestamptz,
  add column confirmed_by uuid,
  add column confirmation_version integer;

alter table public.broker_symbols
  add constraint broker_symbols_base_currency_format_check
    check (base_currency is null or base_currency ~ '^[A-Z]{3}$'),
  add constraint broker_symbols_profit_currency_format_check
    check (profit_currency is null or profit_currency ~ '^[A-Z]{3}$'),
  add constraint broker_symbols_confirmation_status_check
    check (confirmation_status in ('unconfirmed', 'confirmed')),
  add constraint broker_symbols_confirmation_state_check
    check (
      (
        confirmation_status = 'unconfirmed'
        and confirmed_specification_fingerprint is null
        and confirmed_at is null
        and confirmed_by is null
        and confirmation_version is null
      )
      or (
        confirmation_status = 'confirmed'
        and canonical_symbol = 'XAUUSD'
        and base_currency = 'XAU'
        and profit_currency = 'USD'
        and confirmed_specification_fingerprint
          ~ '^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$'
        and specification_version = confirmed_specification_fingerprint
        and confirmed_at is not null
        and confirmed_by = owner_id
        and confirmation_version > 0
      )
    ),
  add constraint broker_symbols_confirmed_by_fkey
    foreign key (confirmed_by) references public.profiles (id) on delete restrict;

create unique index broker_symbols_confirmation_version_unique
  on public.broker_symbols (
    owner_id, trading_account_id, canonical_symbol, confirmation_version
  )
  where confirmation_status = 'confirmed';

alter table public.mt5_symbol_observations
  add constraint mt5_symbol_observations_canonical_xauusd_check
    check (
      canonical_symbol = 'XAUUSD'
      and normalized_specification ->> 'canonical_symbol' = 'XAUUSD'
      and normalized_specification ->> 'base_currency' = 'XAU'
      and normalized_specification ->> 'profit_currency' = 'USD'
    );

alter table public.mt5_symbol_observations
  drop constraint mt5_symbol_observations_owner_id_account_fingerprint_broker_key;

create index mt5_symbol_observations_latest_material_state_idx
  on public.mt5_symbol_observations (
    owner_id, account_fingerprint, broker_symbol, created_at desc, id desc
  );

alter table public.mt5_reconciliation_mismatches
  drop constraint mt5_reconciliation_mismatches_category_check;

alter table public.mt5_reconciliation_mismatches
  add constraint mt5_reconciliation_mismatches_category_check check (category in (
    'UNEXPECTED_BROKER_POSITION', 'DATABASE_POSITION_MISSING_AT_BROKER',
    'UNEXPECTED_ACTIVE_ORDER', 'DATABASE_ORDER_MISSING_AT_BROKER',
    'EXECUTION_RESULT_UNCERTAIN', 'ACCOUNT_CHANGED', 'SERVER_CHANGED',
    'SYMBOL_SPEC_CONFIRMATION_REQUIRED', 'SYMBOL_SPEC_CHANGED',
    'HISTORY_QUERY_FAILED', 'HISTORY_WINDOW_INCOMPLETE',
    'CLOCK_INCONSISTENCY'
  ));

create table public.mt5_history_query_evidence (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  reconciliation_id uuid not null,
  history_kind text not null check (history_kind in ('orders', 'deals')),
  requested_start_at timestamptz not null,
  requested_end_at timestamptz not null,
  query_completed_at timestamptz,
  returned_count integer not null check (returned_count >= 0),
  earliest_returned_at timestamptz,
  latest_returned_at timestamptz,
  result_state text not null check (result_state in (
    'query_succeeded', 'empty_valid_result', 'query_failed',
    'window_incomplete', 'window_unknown'
  )),
  reason_code text not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (requested_start_at < requested_end_at),
  check (query_completed_at is null or query_completed_at >= requested_end_at),
  check (
    (earliest_returned_at is null and latest_returned_at is null)
    or (
      earliest_returned_at is not null
      and latest_returned_at is not null
      and earliest_returned_at <= latest_returned_at
    )
  ),
  check (
    result_state <> 'query_succeeded'
    or (
      query_completed_at is not null
      and
      returned_count > 0
      and earliest_returned_at is not null
      and latest_returned_at is not null
    )
  ),
  check (
    result_state <> 'empty_valid_result'
    or (
      query_completed_at is not null
      and returned_count = 0
      and earliest_returned_at is null
      and latest_returned_at is null
    )
  ),
  check (
    result_state <> 'query_failed'
    or (
      query_completed_at is not null
      and returned_count = 0
      and earliest_returned_at is null
      and latest_returned_at is null
    )
  ),
  check (
    result_state <> 'window_unknown'
    or (
      query_completed_at is null
      and returned_count = 0
      and earliest_returned_at is null
      and latest_returned_at is null
    )
  ),
  check (
    (result_state = 'query_succeeded' and reason_code = 'HEALTHY')
    or (result_state = 'empty_valid_result'
      and reason_code = 'HISTORY_EMPTY_VALID_RESULT')
    or (result_state = 'query_failed'
      and reason_code = 'HISTORY_QUERY_FAILED')
    or (result_state in ('window_incomplete', 'window_unknown')
      and reason_code = 'HISTORY_WINDOW_INCOMPLETE')
  ),
  check (reason_code ~ '^[A-Z][A-Z0-9_]{0,159}$'),
  unique (id, owner_id),
  constraint mt5_history_query_evidence_run_kind_unique
    unique (owner_id, reconciliation_id, history_kind),
  foreign key (reconciliation_id, owner_id)
    references public.mt5_reconciliation_runs (id, owner_id) on delete restrict
);

create index mt5_history_query_evidence_owner_time_idx
  on public.mt5_history_query_evidence (owner_id, query_completed_at desc);

create or replace function private.m2_patch_reject_append_only_mutation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  raise exception using errcode = '55000', message = 'AURUM_APPEND_ONLY_RECORD';
end
$function$;

create trigger mt5_history_query_evidence_append_only
before update or delete on public.mt5_history_query_evidence
for each row execute function private.m2_patch_reject_append_only_mutation();

alter table public.mt5_history_query_evidence enable row level security;
alter table public.mt5_history_query_evidence force row level security;

create policy mt5_history_query_evidence_owner_select
on public.mt5_history_query_evidence for select to authenticated
using (owner_id = (select auth.uid()));

create policy mt5_history_query_evidence_function_select
on public.mt5_history_query_evidence for select to aurum_function_owner using (true);
create policy mt5_history_query_evidence_function_insert
on public.mt5_history_query_evidence for insert to aurum_function_owner
with check (true);
create policy broker_symbols_function_select_m2_patch
on public.broker_symbols for select to aurum_function_owner using (true);

revoke all on public.mt5_history_query_evidence
from public, anon, authenticated, aurum_worker, aurum_function_owner;
grant select on public.mt5_history_query_evidence to authenticated;
grant select, insert on public.mt5_history_query_evidence to aurum_function_owner;
grant select on public.broker_symbols to aurum_function_owner;

create or replace function private.m2_history_evidence_valid(
  evidence jsonb,
  expected_kind text
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $function$
declare
  requested_start timestamptz;
  requested_end timestamptz;
  query_completed timestamptz;
  earliest_returned timestamptz;
  latest_returned timestamptz;
  result_count integer;
  result_name text;
begin
  if expected_kind not in ('orders', 'deals')
    or not private.jsonb_exact_keys(evidence, array[
      'earliest_returned_at', 'history_kind', 'latest_returned_at',
      'query_completed_at', 'reason_code', 'requested_end_at',
      'requested_start_at', 'result_state', 'returned_count'
    ])
    or evidence ->> 'history_kind' <> expected_kind
    or evidence ->> 'returned_count' !~ '^[0-9]+$'
    or evidence ->> 'result_state' not in (
      'query_succeeded', 'empty_valid_result', 'query_failed',
      'window_incomplete', 'window_unknown'
    )
    or evidence ->> 'reason_code' !~ '^[A-Z][A-Z0-9_]{0,159}$' then
    return false;
  end if;

  requested_start := (evidence ->> 'requested_start_at')::timestamptz;
  requested_end := (evidence ->> 'requested_end_at')::timestamptz;
  query_completed := (evidence ->> 'query_completed_at')::timestamptz;
  earliest_returned := (evidence ->> 'earliest_returned_at')::timestamptz;
  latest_returned := (evidence ->> 'latest_returned_at')::timestamptz;
  result_count := (evidence ->> 'returned_count')::integer;
  result_name := evidence ->> 'result_state';

  if requested_start >= requested_end
    or (query_completed is not null and query_completed < requested_end) then
    return false;
  end if;
  if (earliest_returned is null) <> (latest_returned is null)
    or (earliest_returned is not null and earliest_returned > latest_returned) then
    return false;
  end if;
  if (result_name = 'query_succeeded'
    and evidence ->> 'reason_code' <> 'HEALTHY') or (
    result_name = 'empty_valid_result'
    and evidence ->> 'reason_code' <> 'HISTORY_EMPTY_VALID_RESULT'
  ) or (
    result_name = 'query_failed'
    and evidence ->> 'reason_code' <> 'HISTORY_QUERY_FAILED'
  ) or (
    result_name in ('window_incomplete', 'window_unknown')
    and evidence ->> 'reason_code' <> 'HISTORY_WINDOW_INCOMPLETE'
  ) then
    return false;
  end if;
  if result_name = 'query_succeeded' and (
    query_completed is null
    or result_count = 0
    or earliest_returned is null
  ) then
    return false;
  end if;
  if result_name = 'empty_valid_result' and (
    query_completed is null
    or result_count <> 0
    or earliest_returned is not null
  ) then
    return false;
  end if;
  if result_name = 'query_failed' and (
    query_completed is null
    or result_count <> 0
    or earliest_returned is not null
  ) then
    return false;
  end if;
  if result_name = 'window_unknown' and (
    query_completed is not null
    or result_count <> 0
    or earliest_returned is not null
  ) then
    return false;
  end if;
  return true;
exception when others then
  return false;
end
$function$;

create or replace function private.m2_reconciliation_mismatches_valid(
  mismatches jsonb
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $function$
declare
  entry jsonb;
begin
  if pg_catalog.jsonb_typeof(mismatches) <> 'array' then return false; end if;
  for entry in
    select item.value from pg_catalog.jsonb_array_elements(mismatches) as item
  loop
    if not private.jsonb_exact_keys(entry, array[
        'category', 'reason_code', 'resource_reference', 'resource_type',
        'severity'
      ])
      or entry ->> 'category' not in (
        'UNEXPECTED_BROKER_POSITION', 'DATABASE_POSITION_MISSING_AT_BROKER',
        'UNEXPECTED_ACTIVE_ORDER', 'DATABASE_ORDER_MISSING_AT_BROKER',
        'EXECUTION_RESULT_UNCERTAIN', 'ACCOUNT_CHANGED', 'SERVER_CHANGED',
        'SYMBOL_SPEC_CONFIRMATION_REQUIRED', 'SYMBOL_SPEC_CHANGED',
        'HISTORY_QUERY_FAILED', 'HISTORY_WINDOW_INCOMPLETE',
        'CLOCK_INCONSISTENCY'
      )
      or entry ->> 'severity' not in ('warning', 'critical')
      or not private.safe_worker_text(entry ->> 'resource_type')
      or not private.safe_worker_text(entry ->> 'resource_reference')
      or (entry ->> 'reason_code' is not null
        and entry ->> 'reason_code' !~ '^[A-Z][A-Z0-9_]{0,159}$') then
      return false;
    end if;
  end loop;
  return true;
exception when others then
  return false;
end
$function$;

create or replace function private.m2_audit_confirmed_broker_symbol()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if new.confirmation_status = 'confirmed' then
    perform private.append_audit(
      new.owner_id,
      'user',
      new.confirmed_by::text,
      'mt5_symbol_binding_confirmed',
      'broker_symbol_confirmation',
      new.id,
      new.id,
      null,
      new.confirmation_version,
      pg_catalog.jsonb_build_object(
        'brokerSymbol', new.broker_symbol,
        'canonicalSymbol', new.canonical_symbol,
        'specificationFingerprint', new.confirmed_specification_fingerprint
      )
    );
  end if;
  return new;
end
$function$;

create trigger broker_symbols_confirmation_audit
after insert on public.broker_symbols
for each row execute function private.m2_audit_confirmed_broker_symbol();

grant create on schema private to aurum_function_owner;
alter function private.m2_history_evidence_valid(jsonb, text)
  owner to aurum_function_owner;
alter function private.m2_reconciliation_mismatches_valid(jsonb)
  owner to aurum_function_owner;
alter function private.m2_audit_confirmed_broker_symbol()
  owner to aurum_function_owner;
alter function private.m2_patch_reject_append_only_mutation()
  owner to aurum_function_owner;
revoke create on schema private from aurum_function_owner;

revoke all on function private.m2_history_evidence_valid(jsonb, text)
  from public, anon, authenticated, aurum_worker;
revoke all on function private.m2_reconciliation_mismatches_valid(jsonb)
  from public, anon, authenticated, aurum_worker;
revoke all on function private.m2_audit_confirmed_broker_symbol()
  from public, anon, authenticated, aurum_worker;
revoke all on function private.m2_patch_reject_append_only_mutation()
  from public, anon, authenticated, aurum_worker;

grant create on schema public to aurum_function_owner;
set local role aurum_function_owner;

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
  latest_observation public.mt5_symbol_observations%rowtype;
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
    ]) then
    return 'INVALID_SYMBOL_OBSERVATION';
  end if;
  if observation ->> 'canonical_symbol' <> 'XAUUSD'
    or observation ->> 'base_currency' <> 'XAU'
    or observation ->> 'profit_currency' <> 'USD' then
    return 'SYMBOL_CANONICAL_MISMATCH';
  end if;
  if observation ->> 'account_fingerprint' !~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$'
    or observation ->> 'specification_fingerprint' !~ '^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$'
    or not private.safe_worker_text(observation ->> 'broker_symbol')
    or not private.safe_worker_text(observation ->> 'trace_id')
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
    or (observation ->> 'usability_state' = 'usable'
      and observation ->> 'unusable_reason' is not null)
    or observation ->> 'schema_version' <> '1' then
    return 'INVALID_SYMBOL_OBSERVATION';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      v_owner_id::text || ':' || (observation ->> 'account_fingerprint')
        || ':' || (observation ->> 'broker_symbol'),
      0
    )
  );
  select * into latest_observation
  from public.mt5_symbol_observations as prior
  where prior.owner_id = v_owner_id
    and prior.account_fingerprint = observation ->> 'account_fingerprint'
    and prior.broker_symbol = observation ->> 'broker_symbol'
  order by prior.created_at desc, prior.id desc
  limit 1;
  if found
    and latest_observation.specification_fingerprint
      = observation ->> 'specification_fingerprint'
    and latest_observation.usability_state = observation ->> 'usability_state'
    and latest_observation.unusable_reason is not distinct from
      observation ->> 'unusable_reason' then
    return 'IDEMPOTENT_REPLAY';
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
    ) returning id into observation_id;
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
    returning id into tick_id;
  exception when others then
    return 'INVALID_TICK_OBSERVATION';
  end;
  if tick_id is null then return 'STALE_TICK_IGNORED'; end if;
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
    'confirmed_symbol_binding', (
      select pg_catalog.jsonb_build_object(
        'owner_id', binding.owner_id,
        'trading_account_id', binding.trading_account_id,
        'canonical_symbol', binding.canonical_symbol,
        'broker_symbol', binding.broker_symbol,
        'confirmed_specification_fingerprint',
          binding.confirmed_specification_fingerprint,
        'confirmation_status', binding.confirmation_status,
        'confirmed_at', binding.confirmed_at,
        'confirmed_by', binding.confirmed_by,
        'version', binding.confirmation_version
      )
      from public.broker_symbols as binding
      where binding.owner_id = v_owner_id
        and binding.confirmation_status = 'confirmed'
      order by binding.confirmation_version desc, binding.confirmed_at desc,
        binding.id desc
      limit 1
    )
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
      'broker_symbol', 'completed_at', 'deal_history_count',
      'deal_history_evidence',
      'mismatches', 'observed_at', 'open_position_count',
      'order_history_count', 'order_history_evidence', 'outcome',
      'reason_code', 'reconciliation_id', 'schema_version',
      'server_fingerprint', 'source', 'started_at',
      'symbol_specification_fingerprint', 'trace_id'
    ])
    or not private.is_uuid(report ->> 'reconciliation_id')
    or not private.safe_worker_text(report ->> 'trace_id')
    or not private.safe_worker_text(report ->> 'adapter_version')
    or report ->> 'source' <> 'mt5'
    or report ->> 'schema_version' <> '1'
    or not private.m2_reconciliation_mismatches_valid(report -> 'mismatches')
    or report ->> 'open_position_count' !~ '^[0-9]+$'
    or report ->> 'active_order_count' !~ '^[0-9]+$'
    or report ->> 'order_history_count' !~ '^[0-9]+$'
    or report ->> 'deal_history_count' !~ '^[0-9]+$'
    or (report ->> 'account_fingerprint' is not null
      and report ->> 'account_fingerprint' !~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$')
    or (report ->> 'server_fingerprint' is not null
      and report ->> 'server_fingerprint' !~ '^mt5-server-v1:[A-Za-z0-9:_-]{4,128}$')
    or (report ->> 'broker_symbol' is not null
      and not private.safe_worker_text(report ->> 'broker_symbol'))
    or (report ->> 'symbol_specification_fingerprint' is not null
      and report ->> 'symbol_specification_fingerprint' !~ '^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$')
    or report ->> 'reason_code' !~ '^[A-Z][A-Z0-9_]{0,159}$'
    or not private.m2_history_evidence_valid(
      report -> 'order_history_evidence', 'orders'
    )
    or not private.m2_history_evidence_valid(
      report -> 'deal_history_evidence', 'deals'
    ) then
    return 'INVALID_RECONCILIATION';
  end if;
  begin
    if (report ->> 'order_history_count')::integer
        <> (report -> 'order_history_evidence' ->> 'returned_count')::integer
      or (report ->> 'deal_history_count')::integer
        <> (report -> 'deal_history_evidence' ->> 'returned_count')::integer then
      return 'INVALID_RECONCILIATION';
    end if;
    insert into public.mt5_reconciliation_runs (
      id, owner_id, worker_id, status, reason_code, account_fingerprint,
      server_fingerprint, broker_symbol, symbol_specification_fingerprint,
      trace_id, started_at, report_hash
    ) values (
      (report ->> 'reconciliation_id')::uuid, v_owner_id, v_worker_id,
      'running', report ->> 'reason_code', report ->> 'account_fingerprint',
      report ->> 'server_fingerprint', report ->> 'broker_symbol',
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
  reconciliation_status text;
begin
  if not private.m2_worker_authorized() then return 'WORKER_UNAUTHORIZED'; end if;
  if reconciliation_id is null
    or not private.m2_reconciliation_mismatches_valid(
      pg_catalog.jsonb_build_array(mismatch)
    ) then
    return 'INVALID_RECONCILIATION_MISMATCH';
  end if;
  select run.status into reconciliation_status
  from public.mt5_reconciliation_runs as run
  where run.id = reconciliation_id and run.owner_id = v_owner_id
  for update;
  if not found then return 'RECONCILIATION_NOT_FOUND'; end if;
  if reconciliation_status <> 'running' then
    if exists (
      select 1
      from public.mt5_reconciliation_mismatches as existing
      where existing.owner_id = v_owner_id
        and existing.reconciliation_id = $1
        and existing.category = mismatch ->> 'category'
        and existing.resource_reference = mismatch ->> 'resource_reference'
    ) then
      return 'IDEMPOTENT_REPLAY';
    end if;
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
  order_evidence jsonb := report -> 'order_history_evidence';
  deal_evidence jsonb := report -> 'deal_history_evidence';
  v_report_hash text := pg_catalog.md5(report::text);
  child_mismatch_count integer;
  payload_mismatches_normalized jsonb;
  child_mismatches_normalized jsonb;
begin
  if not private.m2_worker_authorized() then return 'WORKER_UNAUTHORIZED'; end if;
  if not private.jsonb_exact_keys(report, array[
      'account_fingerprint', 'active_order_count', 'adapter_version',
      'broker_symbol', 'completed_at', 'deal_history_count',
      'deal_history_evidence',
      'mismatches', 'observed_at', 'open_position_count',
      'order_history_count', 'order_history_evidence', 'outcome',
      'reason_code', 'reconciliation_id', 'schema_version',
      'server_fingerprint', 'source', 'started_at',
      'symbol_specification_fingerprint', 'trace_id'
    ])
    or not private.is_uuid(report ->> 'reconciliation_id')
    or not private.safe_worker_text(report ->> 'trace_id')
    or not private.safe_worker_text(report ->> 'adapter_version')
    or report ->> 'source' <> 'mt5'
    or report ->> 'schema_version' <> '1'
    or not private.m2_reconciliation_mismatches_valid(report -> 'mismatches')
    or report ->> 'open_position_count' !~ '^[0-9]+$'
    or report ->> 'active_order_count' !~ '^[0-9]+$'
    or report ->> 'order_history_count' !~ '^[0-9]+$'
    or report ->> 'deal_history_count' !~ '^[0-9]+$'
    or (report ->> 'account_fingerprint' is not null
      and report ->> 'account_fingerprint' !~ '^mt5-account-v1:[A-Za-z0-9:_-]{4,128}$')
    or (report ->> 'server_fingerprint' is not null
      and report ->> 'server_fingerprint' !~ '^mt5-server-v1:[A-Za-z0-9:_-]{4,128}$')
    or (report ->> 'broker_symbol' is not null
      and not private.safe_worker_text(report ->> 'broker_symbol'))
    or (report ->> 'symbol_specification_fingerprint' is not null
      and report ->> 'symbol_specification_fingerprint' !~ '^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$')
    or report ->> 'outcome' not in ('matched', 'mismatch', 'incomplete')
    or report ->> 'reason_code' !~ '^[A-Z][A-Z0-9_]{0,159}$'
    or not private.m2_history_evidence_valid(order_evidence, 'orders')
    or not private.m2_history_evidence_valid(deal_evidence, 'deals') then
    return 'INVALID_RECONCILIATION';
  end if;
  begin
    if (report ->> 'order_history_count')::integer
        <> (order_evidence ->> 'returned_count')::integer
      or (report ->> 'deal_history_count')::integer
        <> (deal_evidence ->> 'returned_count')::integer
      or (
        report ->> 'outcome' = 'matched'
        and (
          report ->> 'reason_code' <> 'HEALTHY'
          or pg_catalog.jsonb_array_length(report -> 'mismatches') <> 0
          or report ->> 'account_fingerprint' is null
          or report ->> 'server_fingerprint' is null
          or report ->> 'broker_symbol' is null
          or report ->> 'symbol_specification_fingerprint' is null
          or order_evidence ->> 'result_state' not in (
            'query_succeeded', 'empty_valid_result'
          )
          or deal_evidence ->> 'result_state' not in (
            'query_succeeded', 'empty_valid_result'
          )
        )
      ) then
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

    select coalesce(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'category', payload.value ->> 'category',
          'severity', payload.value ->> 'severity',
          'resource_type', payload.value ->> 'resource_type',
          'resource_reference', payload.value ->> 'resource_reference',
          'reason_code', payload.value ->> 'reason_code'
        ) order by
          payload.value ->> 'category',
          payload.value ->> 'resource_reference',
          payload.value ->> 'severity',
          payload.value ->> 'resource_type',
          coalesce(payload.value ->> 'reason_code', '')
      ),
      '[]'::jsonb
    ) into payload_mismatches_normalized
    from pg_catalog.jsonb_array_elements(report -> 'mismatches') as payload;

    select pg_catalog.count(*)::integer, coalesce(
      pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
          'category', child.category,
          'severity', child.severity,
          'resource_type', child.resource_type,
          'resource_reference', child.resource_reference,
          'reason_code', child.reason_code
        ) order by
          child.category, child.resource_reference, child.severity,
          child.resource_type, coalesce(child.reason_code, '')
      ),
      '[]'::jsonb
    ) into child_mismatch_count, child_mismatches_normalized
    from public.mt5_reconciliation_mismatches as child
    where child.owner_id = v_owner_id
      and child.reconciliation_id = existing.id;
    if child_mismatch_count <>
        pg_catalog.jsonb_array_length(report -> 'mismatches')
      or child_mismatches_normalized <> payload_mismatches_normalized then
      return 'INVALID_RECONCILIATION';
    end if;

    insert into public.mt5_history_query_evidence (
      owner_id, reconciliation_id, history_kind, requested_start_at,
      requested_end_at, query_completed_at, returned_count,
      earliest_returned_at, latest_returned_at, result_state, reason_code
    ) values
    (
      v_owner_id, existing.id, order_evidence ->> 'history_kind',
      (order_evidence ->> 'requested_start_at')::timestamptz,
      (order_evidence ->> 'requested_end_at')::timestamptz,
      (order_evidence ->> 'query_completed_at')::timestamptz,
      (order_evidence ->> 'returned_count')::integer,
      (order_evidence ->> 'earliest_returned_at')::timestamptz,
      (order_evidence ->> 'latest_returned_at')::timestamptz,
      order_evidence ->> 'result_state', order_evidence ->> 'reason_code'
    ),
    (
      v_owner_id, existing.id, deal_evidence ->> 'history_kind',
      (deal_evidence ->> 'requested_start_at')::timestamptz,
      (deal_evidence ->> 'requested_end_at')::timestamptz,
      (deal_evidence ->> 'query_completed_at')::timestamptz,
      (deal_evidence ->> 'returned_count')::integer,
      (deal_evidence ->> 'earliest_returned_at')::timestamptz,
      (deal_evidence ->> 'latest_returned_at')::timestamptz,
      deal_evidence ->> 'result_state', deal_evidence ->> 'reason_code'
    );

    update public.mt5_reconciliation_runs run set
      status = 'completed', outcome = report ->> 'outcome',
      reason_code = report ->> 'reason_code',
      account_fingerprint = report ->> 'account_fingerprint',
      server_fingerprint = report ->> 'server_fingerprint',
      broker_symbol = report ->> 'broker_symbol',
      symbol_specification_fingerprint = report ->> 'symbol_specification_fingerprint',
      open_position_count = (report ->> 'open_position_count')::integer,
      active_order_count = (report ->> 'active_order_count')::integer,
      order_history_count = (report ->> 'order_history_count')::integer,
      deal_history_count = (report ->> 'deal_history_count')::integer,
      mismatch_count = pg_catalog.jsonb_array_length(report -> 'mismatches'),
      completed_at = (report ->> 'completed_at')::timestamptz,
      updated_at = pg_catalog.clock_timestamp()
    where run.id = existing.id returning run.id into run_id;
  exception when others then
    return 'INVALID_RECONCILIATION';
  end;

  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id, 'mt5_reconciliation_completed',
    'mt5_reconciliation_run', run_id, run_id, 1, 2,
    pg_catalog.jsonb_build_object(
      'outcome', report ->> 'outcome',
      'mismatchCount', pg_catalog.jsonb_array_length(report -> 'mismatches'),
      'orderHistoryState', order_evidence ->> 'result_state',
      'dealHistoryState', deal_evidence ->> 'result_state'
    )
  );
  return 'RECONCILIATION_COMPLETED';
end
$function$;

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
reset role;
revoke create on schema public from aurum_function_owner;

set local role aurum_function_owner;
revoke all on function public.worker_record_mt5_symbol_observation(jsonb),
  public.worker_upsert_mt5_latest_tick(jsonb),
  public.worker_read_mt5_reconciliation_state(),
  public.worker_begin_reconciliation(jsonb),
  public.worker_record_reconciliation_mismatch(uuid, jsonb),
  public.worker_complete_reconciliation(jsonb)
  from public, anon, authenticated, aurum_worker;
grant execute on function public.worker_record_mt5_symbol_observation(jsonb),
  public.worker_upsert_mt5_latest_tick(jsonb),
  public.worker_read_mt5_reconciliation_state(),
  public.worker_begin_reconciliation(jsonb),
  public.worker_record_reconciliation_mismatch(uuid, jsonb),
  public.worker_complete_reconciliation(jsonb)
  to aurum_worker;

revoke execute on function private.m2_history_evidence_valid(jsonb, text),
  private.m2_reconciliation_mismatches_valid(jsonb),
  private.m2_audit_confirmed_broker_symbol(),
  private.m2_patch_reject_append_only_mutation()
  from public, anon, authenticated, aurum_worker;
revoke execute on function public.worker_record_mt5_symbol_observation(jsonb),
  public.worker_upsert_mt5_latest_tick(jsonb),
  public.worker_read_mt5_reconciliation_state(),
  public.worker_begin_reconciliation(jsonb),
  public.worker_record_reconciliation_mismatch(uuid, jsonb),
  public.worker_complete_reconciliation(jsonb)
  from public, anon, authenticated, aurum_worker;
grant execute on function public.worker_record_mt5_symbol_observation(jsonb),
  public.worker_upsert_mt5_latest_tick(jsonb),
  public.worker_read_mt5_reconciliation_state(),
  public.worker_begin_reconciliation(jsonb),
  public.worker_record_reconciliation_mismatch(uuid, jsonb),
  public.worker_complete_reconciliation(jsonb)
  to aurum_worker;
reset role;
