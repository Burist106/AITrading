-- M3 research-only journal. No approval, command or broker mutation capability.
-- Financial input stays decimal text; JSON null means genuinely absent evidence.
grant create on schema private, public to aurum_function_owner;
set local role aurum_function_owner;

create function private.m3_text(value jsonb, maximum integer default 128)
returns boolean language sql immutable security definer set search_path = ''
as $fn$
  select coalesce(pg_catalog.jsonb_typeof(value) = 'string'
    and pg_catalog.length(value #>> '{}') between 1 and maximum
    and private.safe_worker_text(value #>> '{}'), false)
$fn$;

create function private.m3_uuid(value jsonb)
returns boolean language sql immutable security definer set search_path = ''
as $fn$
  select coalesce(pg_catalog.jsonb_typeof(value) = 'string'
    and (value #>> '{}') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', false)
$fn$;

create function private.m3_time(value jsonb)
returns boolean language plpgsql immutable security definer set search_path = ''
as $fn$
begin
  if pg_catalog.jsonb_typeof(value) is distinct from 'string'
    or (value #>> '{}') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]([.][0-9]{1,6})?(Z|[+]00:00)$'
    then return false; end if;
  return pg_catalog.isfinite((value #>> '{}')::timestamptz);
exception when others then return false;
end
$fn$;

create function private.m3_decimal(value jsonb, positive boolean default true)
returns boolean language plpgsql immutable security definer set search_path = ''
as $fn$
declare amount numeric;
begin
  if pg_catalog.jsonb_typeof(value) is distinct from 'string'
    or pg_catalog.length(value #>> '{}') > 96
    or (value #>> '{}') !~ '^(0|[1-9][0-9]*)([.][0-9]+)?$'
    then return false; end if;
  amount := (value #>> '{}')::numeric;
  return private.numeric_is_finite(amount)
    and case when positive then amount > 0 else amount >= 0 end;
exception when others then return false;
end
$fn$;

create function private.m3_integer(value jsonb, minimum integer default 1)
returns boolean language sql immutable security definer set search_path = ''
as $fn$
  select coalesce(pg_catalog.jsonb_typeof(value) = 'number'
    and (value #>> '{}') ~ '^(0|[1-9][0-9]{0,9})$'
    and (value #>> '{}')::numeric between minimum and 2147483647, false)
$fn$;

create function private.m3_code(value jsonb)
returns boolean language sql immutable security definer set search_path = ''
as $fn$
  select coalesce(pg_catalog.jsonb_typeof(value) = 'string'
    and (value #>> '{}') ~ '^[A-Z][A-Z0-9_]{0,79}$', false)
$fn$;

create function private.m3_checks(value jsonb, outcome text)
returns boolean language plpgsql immutable security definer set search_path = ''
as $fn$
declare item jsonb; codes text[] := '{}'; passed boolean := true;
begin
  if pg_catalog.jsonb_typeof(value) is distinct from 'array'
    or pg_catalog.jsonb_array_length(value) not between 1 and 64
    or outcome is null or outcome not in ('PASS', 'BLOCK') then return false; end if;
  for item in select * from pg_catalog.jsonb_array_elements(value) loop
    if not private.jsonb_exact_keys(item, array['code','passed'])
      or not private.m3_code(item -> 'code')
      or pg_catalog.jsonb_typeof(item -> 'passed') is distinct from 'boolean'
      or (item ->> 'code') = any(codes) then return false; end if;
    codes := pg_catalog.array_append(codes, item ->> 'code');
    passed := passed and (item ->> 'passed')::boolean;
  end loop;
  return (outcome = 'PASS') = passed;
exception when others then return false;
end
$fn$;

create function private.m3_market(value jsonb)
returns boolean language plpgsql immutable security definer set search_path = ''
as $fn$
declare key_name text; bar jsonb; prior_open timestamptz;
  opened timestamptz; captured timestamptz; last_close timestamptz;
begin
  if not private.jsonb_exact_keys(value, array[
    'snapshot_id','feature_id','reconciliation_id','input_digest',
    'account_fingerprint','server_fingerprint','specification_fingerprint',
    'adapter_version','market_adapter_version','market_time_policy','broker_symbol',
    'captured_at','tick_at','last_bar_closed_at','bid','ask','point','tick_size',
    'fast_sma','slow_sma','atr','bars'
  ]) then return false; end if;
  foreach key_name in array array['snapshot_id','feature_id','reconciliation_id'] loop
    if not private.m3_uuid(value -> key_name) then return false; end if;
  end loop;
  if not private.m3_text(value -> 'input_digest',64)
    or value ->> 'input_digest' !~ '^[a-f0-9]{64}$'
    or not private.m3_text(value -> 'account_fingerprint',160)
    or value ->> 'account_fingerprint' !~ '^mt5-account-v1:[a-f0-9]{64}$'
    or not private.m3_text(value -> 'server_fingerprint',160)
    or value ->> 'server_fingerprint' !~ '^mt5-server-v1:[a-f0-9]{64}$'
    or not private.m3_text(value -> 'specification_fingerprint',160)
    or value ->> 'specification_fingerprint' !~ '^mt5-spec-v1:[a-f0-9]{64}$'
    then return false; end if;
  foreach key_name in array array['adapter_version','market_adapter_version','market_time_policy','broker_symbol'] loop
    if not private.m3_text(value -> key_name)
      or value ->> key_name !~ '^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,127}$' then return false; end if;
  end loop;
  foreach key_name in array array['captured_at','tick_at','last_bar_closed_at'] loop
    if not private.m3_time(value -> key_name) then return false; end if;
  end loop;
  foreach key_name in array array['bid','ask','point','tick_size','fast_sma','slow_sma'] loop
    if not private.m3_decimal(value -> key_name) then return false; end if;
  end loop;
  if not private.m3_decimal(value -> 'atr',false)
    or (value ->> 'ask')::numeric < (value ->> 'bid')::numeric
    or pg_catalog.jsonb_typeof(value -> 'bars') is distinct from 'array'
    or pg_catalog.jsonb_array_length(value -> 'bars') <> 6 then return false; end if;
  captured := (value ->> 'captured_at')::timestamptz;
  last_close := (value ->> 'last_bar_closed_at')::timestamptz;
  if captured < (value ->> 'tick_at')::timestamptz
    or captured - (value ->> 'tick_at')::timestamptz > interval '5 seconds'
    or captured < last_close or captured - last_close >= interval '1 minute'
    then return false; end if;
  for bar in select * from pg_catalog.jsonb_array_elements(value -> 'bars') loop
    if not private.jsonb_exact_keys(bar, array['open_at','open','high','low','close'])
      or not private.m3_time(bar -> 'open_at') then return false; end if;
    foreach key_name in array array['open','high','low','close'] loop
      if not private.m3_decimal(bar -> key_name) then return false; end if;
    end loop;
    opened := (bar ->> 'open_at')::timestamptz;
    if (pg_catalog.date_trunc('minute',opened at time zone 'UTC') at time zone 'UTC') <> opened
      or opened + interval '1 minute' > captured
      or (prior_open is not null and opened <> prior_open + interval '1 minute')
      or (bar ->> 'low')::numeric > least((bar ->> 'open')::numeric,(bar ->> 'close')::numeric)
      or (bar ->> 'high')::numeric < greatest((bar ->> 'open')::numeric,(bar ->> 'close')::numeric)
      then return false; end if;
    prior_open := opened;
  end loop;
  return prior_open + interval '1 minute' = last_close;
exception when others then return false;
end
$fn$;

create function private.m3_cycle(value jsonb)
returns boolean language plpgsql immutable security definer set search_path = ''
as $fn$
declare key_name text; reason jsonb; codes text[] := '{}'; candidate jsonb;
  receipt jsonb; kinds text[] := '{}';
  risk jsonb; eligibility jsonb; at_time timestamptz;
begin
  if pg_catalog.octet_length(value::text) > 65536
    or not private.jsonb_exact_keys(value,array[
      'schema_version','pipeline_version','strategy_version','eligibility_version',
      'id','owner_id','trading_account_id','trace_id','cycle_key','evaluated_at',
      'environment','runtime_mode','source','grants_eligibility','status','reason_codes',
      'policy_version_id','policy_version','mode_version','market','candidate','risk','eligibility'
    ]) then return false; end if;
  if value ->> 'schema_version' is distinct from 'shadow-cycle-v1'
    or value ->> 'pipeline_version' is distinct from 'shadow-pipeline-v1'
    or value ->> 'strategy_version' is distinct from 'sma-atr-shadow-v1'
    or value ->> 'eligibility_version' is distinct from 'shadow-eligibility-v1'
    or value ->> 'environment' is distinct from 'DEMO_ONLY'
    or value ->> 'runtime_mode' is distinct from 'SHADOW'
    or value ->> 'source' is distinct from 'mt5'
    or value -> 'grants_eligibility' is distinct from 'false'::jsonb
    or value ->> 'status' is null or value ->> 'status' not in ('WAIT','BLOCK','PROPOSAL')
    or not private.m3_time(value -> 'evaluated_at')
    or not private.m3_text(value -> 'cycle_key',64)
    or value ->> 'cycle_key' !~ '^[a-f0-9]{64}$'
    then return false; end if;
  at_time := (value ->> 'evaluated_at')::timestamptz;
  foreach key_name in array array['id','owner_id','trading_account_id','trace_id'] loop
    if not private.m3_uuid(value -> key_name) then return false; end if;
  end loop;
  if value -> 'policy_version_id' <> 'null'::jsonb and not private.m3_uuid(value -> 'policy_version_id') then return false; end if;
  foreach key_name in array array['policy_version','mode_version'] loop
    if value -> key_name <> 'null'::jsonb and not private.m3_integer(value -> key_name) then return false; end if;
  end loop;
  if (value -> 'policy_version_id' = 'null'::jsonb) <> (value -> 'policy_version' = 'null'::jsonb)
    or pg_catalog.jsonb_typeof(value -> 'reason_codes') is distinct from 'array'
    or pg_catalog.jsonb_array_length(value -> 'reason_codes') not between 1 and 32 then return false; end if;
  for reason in select * from pg_catalog.jsonb_array_elements(value -> 'reason_codes') loop
    if not private.m3_code(reason) or (reason #>> '{}') = any(codes) then return false; end if;
    codes := pg_catalog.array_append(codes,reason #>> '{}');
  end loop;
  if value -> 'market' <> 'null'::jsonb then
    if not private.m3_market(value -> 'market')
      or (value #>> '{market,captured_at}')::timestamptz > at_time
      or at_time - (value #>> '{market,captured_at}')::timestamptz > interval '5 seconds'
      then return false; end if;
  end if;
  candidate := value -> 'candidate';
  if candidate <> 'null'::jsonb then
    if value -> 'market' = 'null'::jsonb
      or not private.jsonb_exact_keys(candidate,array['id','direction','created_at','expires_at','entry_price','stop_loss_price','take_profit_price'])
      or not private.m3_uuid(candidate -> 'id')
      or candidate ->> 'direction' is null or candidate ->> 'direction' not in ('BUY','SELL')
      or not private.m3_time(candidate -> 'created_at')
      or not private.m3_time(candidate -> 'expires_at') then return false; end if;
    foreach key_name in array array['entry_price','stop_loss_price','take_profit_price'] loop
      if not private.m3_decimal(candidate -> key_name) then return false; end if;
    end loop;
    if (candidate ->> 'created_at')::timestamptz <> at_time
      or (candidate ->> 'expires_at')::timestamptz <= (candidate ->> 'created_at')::timestamptz
      or (candidate ->> 'expires_at')::timestamptz - (candidate ->> 'created_at')::timestamptz > interval '30 seconds'
      or not (case when candidate ->> 'direction' = 'BUY' then
        (candidate ->> 'stop_loss_price')::numeric < (candidate ->> 'entry_price')::numeric
        and (candidate ->> 'entry_price')::numeric < (candidate ->> 'take_profit_price')::numeric
      else (candidate ->> 'take_profit_price')::numeric < (candidate ->> 'entry_price')::numeric
        and (candidate ->> 'entry_price')::numeric < (candidate ->> 'stop_loss_price')::numeric end)
      then return false; end if;
  end if;
  risk := value -> 'risk';
  if risk <> 'null'::jsonb then
    if candidate = 'null'::jsonb or not private.jsonb_exact_keys(risk,array[
      'version','outcome','checks','input_digest','source_receipts','calculated_volume','estimated_loss_usd','estimated_net_reward_usd'])
      or risk ->> 'version' is distinct from 'shadow-risk-v1'
      or not private.m3_checks(risk -> 'checks',risk ->> 'outcome')
      or not private.m3_text(risk -> 'input_digest',64)
      or risk ->> 'input_digest' !~ '^[a-f0-9]{64}$'
      or pg_catalog.jsonb_typeof(risk -> 'source_receipts') is distinct from 'array'
      or pg_catalog.jsonb_array_length(risk -> 'source_receipts') > 4 then return false; end if;
    for receipt in select * from pg_catalog.jsonb_array_elements(risk -> 'source_receipts') loop
      if not private.jsonb_exact_keys(receipt,array['kind','source_id','source_version','evidence_digest',
        'observed_at','valid_until','covered_from','covered_until'])
        or receipt ->> 'kind' is null or receipt ->> 'kind' not in ('ledger','safety','news','costs')
        or (receipt ->> 'kind') = any(kinds)
        or not private.m3_text(receipt -> 'evidence_digest',64)
        or receipt ->> 'evidence_digest' !~ '^[a-f0-9]{64}$' then return false; end if;
      kinds := pg_catalog.array_append(kinds,receipt ->> 'kind');
      foreach key_name in array array['source_id','source_version'] loop
        if not private.m3_text(receipt -> key_name)
          or receipt ->> key_name !~ '^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,127}$' then return false; end if;
      end loop;
      foreach key_name in array array['observed_at','valid_until'] loop
        if not private.m3_time(receipt -> key_name) then return false; end if;
      end loop;
      if (receipt ->> 'observed_at')::timestamptz > (receipt ->> 'valid_until')::timestamptz
        or (receipt -> 'covered_from' = 'null'::jsonb) <> (receipt -> 'covered_until' = 'null'::jsonb) then return false; end if;
      if risk ->> 'outcome' = 'PASS' and (
        (receipt ->> 'observed_at')::timestamptz > at_time
        or (receipt ->> 'valid_until')::timestamptz < at_time
      ) then return false; end if;
      if receipt -> 'covered_from' <> 'null'::jsonb then
        if not private.m3_time(receipt -> 'covered_from') or not private.m3_time(receipt -> 'covered_until')
          or (receipt ->> 'covered_from')::timestamptz > (receipt ->> 'covered_until')::timestamptz then return false; end if;
      end if;
    end loop;
    if risk ->> 'outcome' = 'PASS' and pg_catalog.cardinality(kinds) <> 4 then return false; end if;
    foreach key_name in array array['calculated_volume','estimated_loss_usd','estimated_net_reward_usd'] loop
      if risk ->> 'outcome' = 'PASS' then
        if not private.m3_decimal(risk -> key_name) then return false; end if;
      elsif risk -> key_name is distinct from 'null'::jsonb then return false;
      end if;
    end loop;
    if risk ->> 'outcome' = 'PASS' and (risk ->> 'calculated_volume')::numeric > 0.01 then return false; end if;
  end if;
  eligibility := value -> 'eligibility';
  if eligibility <> 'null'::jsonb then
    if not private.jsonb_exact_keys(eligibility,array['outcome','checks','sample_count','minimum_sample_size','calibrated'])
      or not private.m3_checks(eligibility -> 'checks',eligibility ->> 'outcome')
      or not private.m3_integer(eligibility -> 'sample_count',0)
      or not private.m3_integer(eligibility -> 'minimum_sample_size',30)
      or eligibility -> 'calibrated' is distinct from 'false'::jsonb then return false; end if;
    if not exists (select 1 from pg_catalog.jsonb_array_elements(eligibility -> 'checks') item
      where item ->> 'code' = 'SAMPLE_SIZE'
      and (item ->> 'passed')::boolean = ((eligibility ->> 'sample_count')::integer >= (eligibility ->> 'minimum_sample_size')::integer)) then return false; end if;
  end if;
  if value ->> 'status' = 'WAIT' and (candidate <> 'null'::jsonb or risk <> 'null'::jsonb) then return false; end if;
  if value ->> 'status' = 'PROPOSAL' and (
    value -> 'market' = 'null'::jsonb or candidate = 'null'::jsonb or risk = 'null'::jsonb
    or eligibility = 'null'::jsonb or risk ->> 'outcome' <> 'PASS'
    or value -> 'policy_version_id' = 'null'::jsonb or value -> 'mode_version' = 'null'::jsonb
    or (candidate ->> 'expires_at')::timestamptz <= at_time
  ) then return false; end if;
  return true;
exception when others then return false;
end
$fn$;

create function private.m3_outcome(value jsonb)
returns boolean language plpgsql immutable security definer set search_path = ''
as $fn$
declare key_name text;
begin
  if pg_catalog.octet_length(value::text) > 4096
    or not private.jsonb_exact_keys(value,array[
      'schema_version','tracker_version','simulation','grants_eligibility',
      'id','owner_id','trading_account_id','cycle_id','sequence','observed_at',
      'status','reason_code','bid','ask','price_source','net_pnl_usd'])
    or value ->> 'schema_version' is distinct from 'shadow-outcome-v1'
    or value ->> 'tracker_version' is distinct from 'quote-observed-v1'
    or value -> 'simulation' is distinct from 'true'::jsonb
    or value -> 'grants_eligibility' is distinct from 'false'::jsonb
    or value -> 'net_pnl_usd' is distinct from 'null'::jsonb
    or not private.m3_integer(value -> 'sequence') or (value ->> 'sequence')::integer > 32
    or not private.m3_time(value -> 'observed_at')
    or not private.m3_code(value -> 'reason_code')
    or value ->> 'status' is null or value ->> 'status' not in ('OBSERVED','STOP_OBSERVED','TARGET_OBSERVED','EXPIRED','UNKNOWN')
    or ((value ->> 'sequence')::integer = 32 and value ->> 'status' = 'OBSERVED')
    or value ->> 'price_source' is null or value ->> 'price_source' not in ('mt5','unavailable')
    then return false; end if;
  foreach key_name in array array['id','owner_id','trading_account_id','cycle_id'] loop
    if not private.m3_uuid(value -> key_name) then return false; end if;
  end loop;
  if value ->> 'price_source' = 'unavailable' then
    return value -> 'bid' = 'null'::jsonb and value -> 'ask' = 'null'::jsonb
      and value ->> 'status' in ('UNKNOWN','EXPIRED');
  end if;
  return private.m3_decimal(value -> 'bid') and private.m3_decimal(value -> 'ask')
    and (value ->> 'ask')::numeric >= (value ->> 'bid')::numeric;
exception when others then return false;
end
$fn$;

revoke all on function private.m3_text(jsonb,integer),private.m3_uuid(jsonb),
  private.m3_time(jsonb),private.m3_decimal(jsonb,boolean),private.m3_integer(jsonb,integer),
  private.m3_code(jsonb),private.m3_checks(jsonb,text),private.m3_market(jsonb),
  private.m3_cycle(jsonb),private.m3_outcome(jsonb)
  from public, anon, authenticated, aurum_worker;
reset role;

-- Create the trigger helper as the migration role, then transfer it after
-- CREATE TRIGGER. postgres intentionally cannot inherit the private owner ACL.
create function private.m3_reject_append_only()
returns trigger language plpgsql security definer set search_path = ''
as $fn$
begin
  raise exception using errcode='55000',message='AURUM_APPEND_ONLY_RECORD';
end
$fn$;

create table public.shadow_cycles (
  id uuid primary key,
  owner_id uuid not null,
  trading_account_id uuid not null,
  cycle_key text not null check (cycle_key ~ '^[a-f0-9]{64}$'),
  status text not null check (status in ('WAIT','BLOCK','PROPOSAL')),
  evaluated_at timestamptz not null,
  payload jsonb not null check (private.m3_cycle(payload)),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (payload ->> 'id' = id::text and payload ->> 'owner_id' = owner_id::text
    and payload ->> 'trading_account_id' = trading_account_id::text
    and payload ->> 'cycle_key' = cycle_key and payload ->> 'status' = status
    and (payload ->> 'evaluated_at')::timestamptz = evaluated_at),
  unique (id,owner_id,trading_account_id),
  unique (owner_id,trading_account_id,cycle_key),
  foreign key (trading_account_id,owner_id)
    references public.trading_accounts(id,owner_id) on delete restrict
);
create index shadow_cycles_owner_account_time_idx
  on public.shadow_cycles(owner_id,trading_account_id,evaluated_at desc,id desc);

create table public.shadow_outcome_events (
  id uuid primary key,
  owner_id uuid not null,
  trading_account_id uuid not null,
  cycle_id uuid not null,
  sequence integer not null check (sequence between 1 and 32),
  observed_at timestamptz not null,
  status text not null check (status in ('OBSERVED','STOP_OBSERVED','TARGET_OBSERVED','EXPIRED','UNKNOWN')),
  payload jsonb not null check (private.m3_outcome(payload)),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (payload ->> 'id' = id::text and payload ->> 'owner_id' = owner_id::text
    and payload ->> 'trading_account_id' = trading_account_id::text
    and payload ->> 'cycle_id' = cycle_id::text and (payload ->> 'sequence')::integer = sequence
    and payload ->> 'status' = status and (payload ->> 'observed_at')::timestamptz = observed_at),
  unique (owner_id,cycle_id,sequence),
  foreign key (cycle_id,owner_id,trading_account_id)
    references public.shadow_cycles(id,owner_id,trading_account_id) on delete restrict
);
create index shadow_outcome_events_owner_cycle_idx
  on public.shadow_outcome_events(owner_id,trading_account_id,cycle_id,sequence);

create trigger shadow_cycles_append_only before update or delete on public.shadow_cycles
for each row execute function private.m3_reject_append_only();
create trigger shadow_outcome_events_append_only before update or delete on public.shadow_outcome_events
for each row execute function private.m3_reject_append_only();
alter function private.m3_reject_append_only() owner to aurum_function_owner;

alter table public.shadow_cycles enable row level security;
alter table public.shadow_cycles force row level security;
alter table public.shadow_outcome_events enable row level security;
alter table public.shadow_outcome_events force row level security;
create policy shadow_cycles_owner_select on public.shadow_cycles for select to authenticated
  using (owner_id = (select auth.uid()));
create policy shadow_outcome_events_owner_select on public.shadow_outcome_events for select to authenticated
  using (owner_id = (select auth.uid()));
create policy shadow_cycles_function_select on public.shadow_cycles for select to aurum_function_owner using (true);
create policy shadow_cycles_function_insert on public.shadow_cycles for insert to aurum_function_owner with check (true);
create policy shadow_outcome_events_function_select on public.shadow_outcome_events for select to aurum_function_owner using (true);
create policy shadow_outcome_events_function_insert on public.shadow_outcome_events for insert to aurum_function_owner with check (true);
create policy trading_accounts_function_select_m3 on public.trading_accounts for select to aurum_function_owner using (true);
create policy trading_modes_function_select_m3 on public.trading_modes for select to aurum_function_owner using (true);
revoke all on public.shadow_cycles,public.shadow_outcome_events from public,anon,authenticated,aurum_worker,aurum_function_owner;
grant select on public.shadow_cycles,public.shadow_outcome_events to authenticated;
grant select,insert on public.shadow_cycles,public.shadow_outcome_events to aurum_function_owner;
grant select on public.trading_accounts,public.trading_modes to aurum_function_owner;

set local role aurum_function_owner;
revoke all on function private.m3_reject_append_only() from public,anon,authenticated,aurum_worker;

create function public.worker_read_shadow_context(p_trading_account_id uuid)
returns jsonb language plpgsql security definer set search_path = ''
as $fn$
declare owner uuid := private.worker_owner_id(); policy public.risk_policy_versions%rowtype;
  mode_row public.trading_modes%rowtype;
begin
  if not private.m2_worker_authorized() then return pg_catalog.jsonb_build_object('result_code','WORKER_UNAUTHORIZED','data',null); end if;
  if not exists (select 1 from public.trading_accounts a where a.id = p_trading_account_id
    and a.owner_id = owner and a.environment = 'DEMO_ONLY' and a.account_type = 'demo'
    and a.verification_state = 'verified_demo') then
    return pg_catalog.jsonb_build_object('result_code','ACCOUNT_UNAVAILABLE','data',null); end if;
  select * into mode_row from public.trading_modes m where m.owner_id = owner and m.trading_account_id = p_trading_account_id;
  if not found or mode_row.mode <> 'shadow' or mode_row.system_state <> 'running'
    or exists (select 1 from public.system_commands c where c.owner_id = owner
      and (c.status = 'executing' or (c.status in ('pending','claimed','validating') and c.type in (
        'PAUSE_NEW_TRADES','RESUME_SYSTEM','ACTIVATE_EMERGENCY_STOP','REQUEST_RISK_POLICY_CHANGE')))) then
    return pg_catalog.jsonb_build_object('result_code','SAFETY_STATE_BLOCKED','data',null); end if;
  if (select count(*) from public.risk_policies p where p.owner_id = owner and p.trading_account_id = p_trading_account_id) <> 1 then
    return pg_catalog.jsonb_build_object('result_code','POLICY_UNAVAILABLE','data',null); end if;
  select v.* into policy from public.risk_policies p join public.risk_policy_versions v
    on v.id = p.active_version_id and v.owner_id = p.owner_id and v.trading_account_id = p.trading_account_id
    where p.owner_id = owner and p.trading_account_id = p_trading_account_id;
  if not found then return pg_catalog.jsonb_build_object('result_code','POLICY_UNAVAILABLE','data',null); end if;
  return pg_catalog.jsonb_build_object('result_code','CONTEXT_READY','data',pg_catalog.jsonb_build_object(
    'owner_id',owner,'trading_account_id',p_trading_account_id,'observed_at',pg_catalog.clock_timestamp(),
    'mode_version',mode_row.version,'system_state',mode_row.system_state,'policy',pg_catalog.to_jsonb(policy)));
end
$fn$;

create function public.worker_read_shadow_cycles(p_trading_account_id uuid,p_cycle_key text default null)
returns jsonb language plpgsql stable security definer set search_path = ''
as $fn$
declare owner uuid := private.worker_owner_id(); cycles jsonb; outcomes jsonb;
begin
  if not private.m2_worker_authorized() then return pg_catalog.jsonb_build_object('result_code','WORKER_UNAUTHORIZED','data',null); end if;
  if p_cycle_key is not null and p_cycle_key !~ '^[a-f0-9]{64}$' then return pg_catalog.jsonb_build_object('result_code','INVALID_CYCLE_KEY','data',null); end if;
  if not exists (select 1 from public.trading_accounts a where a.id = p_trading_account_id and a.owner_id = owner) then
    return pg_catalog.jsonb_build_object('result_code','ACCOUNT_UNAVAILABLE','data',null); end if;
  with selected as (select c.id,c.evaluated_at,c.payload from public.shadow_cycles c
    where c.owner_id = owner and c.trading_account_id = p_trading_account_id
      and (p_cycle_key is null or c.cycle_key = p_cycle_key)
    order by c.evaluated_at desc,c.id desc limit 100)
  select coalesce((select pg_catalog.jsonb_agg(s.payload order by s.evaluated_at desc,s.id desc) from selected s),'[]'::jsonb),
    coalesce((select pg_catalog.jsonb_agg(e.payload order by e.cycle_id,e.sequence) from public.shadow_outcome_events e
      join selected s on s.id = e.cycle_id where e.owner_id = owner and e.trading_account_id = p_trading_account_id),'[]'::jsonb)
    into cycles,outcomes;
  return pg_catalog.jsonb_build_object('result_code','CYCLES_READ','data',pg_catalog.jsonb_build_object('cycles',cycles,'outcomes',outcomes));
end
$fn$;

create function public.worker_record_shadow_cycle(p_cycle jsonb)
returns jsonb language plpgsql security definer set search_path = ''
as $fn$
declare owner uuid := private.worker_owner_id(); existing public.shadow_cycles%rowtype;
  account_id uuid; cycle_id uuid; context jsonb; market jsonb; report public.mt5_reconciliation_runs%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp(); binding public.broker_symbols%rowtype;
begin
  if not private.m2_worker_authorized() then return pg_catalog.jsonb_build_object('result_code','WORKER_UNAUTHORIZED'); end if;
  if not private.m3_cycle(p_cycle) then return pg_catalog.jsonb_build_object('result_code','INVALID_CYCLE'); end if;
  if (p_cycle ->> 'owner_id')::uuid <> owner then return pg_catalog.jsonb_build_object('result_code','OWNER_MISMATCH'); end if;
  account_id := (p_cycle ->> 'trading_account_id')::uuid; cycle_id := (p_cycle ->> 'id')::uuid;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('shadow:' || owner::text || ':' || account_id::text,0));
  select * into existing from public.shadow_cycles c where c.owner_id = owner
    and c.trading_account_id = account_id and c.cycle_key = p_cycle ->> 'cycle_key';
  if found then
    if existing.payload = p_cycle then return pg_catalog.jsonb_build_object('result_code','IDEMPOTENT_REPLAY','cycle_id',existing.id,'created',false); end if;
    return pg_catalog.jsonb_build_object('result_code','CYCLE_CONFLICT');
  end if;
  if not exists (select 1 from public.trading_accounts a where a.id = account_id and a.owner_id = owner) then
    return pg_catalog.jsonb_build_object('result_code','ACCOUNT_UNAVAILABLE'); end if;
  if (p_cycle ->> 'evaluated_at')::timestamptz > now_at then return pg_catalog.jsonb_build_object('result_code','CYCLE_FROM_FUTURE'); end if;
  if p_cycle ->> 'status' = 'PROPOSAL' then
    -- Evidence at the current database check; it never grants execution authority.
    -- No extra operational-table UPDATE privilege is granted merely to acquire locks.
    context := public.worker_read_shadow_context(account_id);
    now_at := pg_catalog.clock_timestamp();
    if context ->> 'result_code' <> 'CONTEXT_READY'
      or context #>> '{data,mode_version}' <> p_cycle ->> 'mode_version'
      or context #>> '{data,policy,id}' <> p_cycle ->> 'policy_version_id'
      or context #>> '{data,policy,version}' <> p_cycle ->> 'policy_version'
      or (p_cycle #>> '{candidate,expires_at}')::timestamptz <= now_at
      or now_at - (p_cycle ->> 'evaluated_at')::timestamptz > interval '5 seconds'
      then return pg_catalog.jsonb_build_object('result_code','CURRENT_STATE_BLOCKED'); end if;
    market := p_cycle -> 'market';
    select * into binding from public.broker_symbols b where b.owner_id = owner and b.trading_account_id = account_id
      and b.confirmation_status = 'confirmed' order by b.confirmation_version desc,b.id desc limit 1;
    if not found or binding.confirmed_specification_fingerprint <> market ->> 'specification_fingerprint'
      or binding.broker_symbol <> market ->> 'broker_symbol' or binding.confirmed_at > (p_cycle ->> 'evaluated_at')::timestamptz
      then return pg_catalog.jsonb_build_object('result_code','BINDING_MISMATCH'); end if;
    select * into report from public.mt5_reconciliation_runs r where r.id = (market ->> 'reconciliation_id')::uuid and r.owner_id = owner;
    if not found or report.status <> 'completed' or report.outcome <> 'matched' or report.reason_code <> 'HEALTHY'
      or report.account_fingerprint is distinct from market ->> 'account_fingerprint'
      or report.server_fingerprint is distinct from market ->> 'server_fingerprint'
      or report.symbol_specification_fingerprint is distinct from market ->> 'specification_fingerprint'
      or report.broker_symbol is distinct from market ->> 'broker_symbol'
      or report.open_position_count <> 0 or report.active_order_count <> 0 or report.mismatch_count <> 0
      or report.completed_at > (market ->> 'captured_at')::timestamptz
      or now_at - report.completed_at > interval '5 seconds'
      or exists (select 1 from public.mt5_reconciliation_mismatches mm where mm.owner_id = owner and mm.reconciliation_id = report.id)
      or (select count(*) from public.mt5_history_query_evidence h where h.owner_id = owner and h.reconciliation_id = report.id
        and h.result_state in ('query_succeeded','empty_valid_result') and h.requested_end_at = report.started_at
        and h.query_completed_at <= report.completed_at) <> 2
      or (select count(distinct h.requested_start_at) from public.mt5_history_query_evidence h where h.owner_id = owner and h.reconciliation_id = report.id) <> 1
      then return pg_catalog.jsonb_build_object('result_code','RECONCILIATION_BLOCKED'); end if;
    if not exists (select 1 from public.mt5_account_observations a where a.owner_id = owner
      and a.account_fingerprint = market ->> 'account_fingerprint' and a.server_fingerprint = market ->> 'server_fingerprint'
      and a.trade_mode = 'demo' and a.verification_state = 'verified_demo_bound' and a.source = 'mt5'
      and a.adapter_version = market ->> 'adapter_version' and a.observed_at <= now_at
      and now_at - a.observed_at <= interval '5 seconds'
      and a.id = (select aa.id from public.mt5_account_observations aa where aa.owner_id = owner order by aa.observed_at desc,aa.id desc limit 1))
      then return pg_catalog.jsonb_build_object('result_code','ACCOUNT_OBSERVATION_BLOCKED'); end if;
  end if;
  begin
    insert into public.shadow_cycles(id,owner_id,trading_account_id,cycle_key,status,evaluated_at,payload)
      values(cycle_id,owner,account_id,p_cycle ->> 'cycle_key',p_cycle ->> 'status',(p_cycle ->> 'evaluated_at')::timestamptz,p_cycle);
  exception when unique_violation then return pg_catalog.jsonb_build_object('result_code','CYCLE_CONFLICT');
  end;
  return pg_catalog.jsonb_build_object('result_code','CYCLE_RECORDED','cycle_id',cycle_id,'created',true);
end
$fn$;

create function public.worker_append_shadow_outcome(p_event jsonb)
returns jsonb language plpgsql security definer set search_path = ''
as $fn$
declare owner uuid := private.worker_owner_id(); existing public.shadow_outcome_events%rowtype;
  cycle public.shadow_cycles%rowtype; prior public.shadow_outcome_events%rowtype;
  event_id uuid; at_time timestamptz; prior_at timestamptz; expires timestamptz;
  quote numeric; stopped boolean; targeted boolean; candidate jsonb; gap boolean;
begin
  if not private.m2_worker_authorized() then return pg_catalog.jsonb_build_object('result_code','WORKER_UNAUTHORIZED'); end if;
  if not private.m3_outcome(p_event) then return pg_catalog.jsonb_build_object('result_code','INVALID_OUTCOME'); end if;
  if (p_event ->> 'owner_id')::uuid <> owner then return pg_catalog.jsonb_build_object('result_code','OWNER_MISMATCH'); end if;
  event_id := (p_event ->> 'id')::uuid;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('shadow-outcome:' || owner::text || ':' || (p_event ->> 'cycle_id'),0));
  select * into existing from public.shadow_outcome_events e where e.id = event_id and e.owner_id = owner;
  if found then
    if existing.payload = p_event then return pg_catalog.jsonb_build_object('result_code','IDEMPOTENT_REPLAY','event_id',event_id,'created',false); end if;
    return pg_catalog.jsonb_build_object('result_code','OUTCOME_CONFLICT');
  end if;
  select * into cycle from public.shadow_cycles c where c.id = (p_event ->> 'cycle_id')::uuid and c.owner_id = owner
    and c.trading_account_id = (p_event ->> 'trading_account_id')::uuid;
  if not found or cycle.status <> 'PROPOSAL' then return pg_catalog.jsonb_build_object('result_code','PROPOSAL_UNAVAILABLE'); end if;
  select * into prior from public.shadow_outcome_events e where e.owner_id = owner and e.cycle_id = cycle.id order by e.sequence desc limit 1;
  if (p_event ->> 'sequence')::integer <> coalesce(prior.sequence,0) + 1 or (prior.id is not null and prior.status <> 'OBSERVED') then
    return pg_catalog.jsonb_build_object('result_code','OUTCOME_SEQUENCE_CONFLICT'); end if;
  at_time := (p_event ->> 'observed_at')::timestamptz;
  prior_at := coalesce(prior.observed_at,cycle.evaluated_at);
  candidate := cycle.payload -> 'candidate'; expires := (candidate ->> 'expires_at')::timestamptz;
  if at_time <= prior_at then return pg_catalog.jsonb_build_object('result_code','OUTCOME_TIME_INVALID'); end if;
  gap := at_time - prior_at > interval '5 seconds' or at_time > pg_catalog.clock_timestamp();
  if gap and p_event ->> 'status' <> 'UNKNOWN' then return pg_catalog.jsonb_build_object('result_code','OUTCOME_GAP_REQUIRES_UNKNOWN'); end if;
  if p_event ->> 'status' <> 'UNKNOWN' then
    if p_event ->> 'status' = 'EXPIRED' then
      if at_time < expires then return pg_catalog.jsonb_build_object('result_code','OUTCOME_NOT_EXPIRED'); end if;
    else
      if at_time >= expires or p_event ->> 'price_source' <> 'mt5' then return pg_catalog.jsonb_build_object('result_code','OUTCOME_EVIDENCE_INVALID'); end if;
      quote := case when candidate ->> 'direction' = 'BUY' then (p_event ->> 'bid')::numeric else (p_event ->> 'ask')::numeric end;
      stopped := case when candidate ->> 'direction' = 'BUY' then quote <= (candidate ->> 'stop_loss_price')::numeric else quote >= (candidate ->> 'stop_loss_price')::numeric end;
      targeted := case when candidate ->> 'direction' = 'BUY' then quote >= (candidate ->> 'take_profit_price')::numeric else quote <= (candidate ->> 'take_profit_price')::numeric end;
      if (p_event ->> 'status' = 'STOP_OBSERVED') <> stopped
        or (p_event ->> 'status' = 'TARGET_OBSERVED') <> targeted then return pg_catalog.jsonb_build_object('result_code','OUTCOME_THRESHOLD_INVALID'); end if;
    end if;
  end if;
  begin
    insert into public.shadow_outcome_events(id,owner_id,trading_account_id,cycle_id,sequence,observed_at,status,payload)
      values(event_id,owner,cycle.trading_account_id,cycle.id,(p_event ->> 'sequence')::integer,at_time,p_event ->> 'status',p_event);
  exception when unique_violation then return pg_catalog.jsonb_build_object('result_code','OUTCOME_CONFLICT'); end;
  return pg_catalog.jsonb_build_object('result_code','OUTCOME_RECORDED','event_id',event_id,'created',true);
end
$fn$;

revoke all on function public.worker_read_shadow_context(uuid),public.worker_read_shadow_cycles(uuid,text),
  public.worker_record_shadow_cycle(jsonb),public.worker_append_shadow_outcome(jsonb)
  from public,anon,authenticated,aurum_worker;
grant execute on function public.worker_read_shadow_context(uuid),public.worker_read_shadow_cycles(uuid,text),
  public.worker_record_shadow_cycle(jsonb),public.worker_append_shadow_outcome(jsonb) to aurum_worker;
reset role;
revoke create on schema private,public from aurum_function_owner;

comment on table public.shadow_cycles is 'Immutable non-executable DEMO_ONLY/SHADOW research cycles, including unavailable-evidence BLOCK and WAIT.';
comment on table public.shadow_outcome_events is 'Append-only quote observations, never broker fills or realized PnL. Missing paths terminate UNKNOWN.';
