-- Aurum Console Milestone 1: durable commands, operational read models,
-- health records, append-only events, and audit foundation.

create type public.worker_claim_result as (
  accepted boolean,
  command_id uuid,
  status public.system_command_status,
  lease_token uuid,
  lease_expires_at timestamptz,
  command_version integer,
  result_code text
);

create type public.worker_incident_result as (
  accepted boolean,
  incident_id uuid,
  created boolean,
  result_code text
);

revoke usage on type public.worker_claim_result from public, anon, authenticated;
revoke usage on type public.worker_incident_result from public, anon, authenticated;
grant usage on type public.worker_claim_result
  to aurum_worker, aurum_function_owner;
grant usage on type public.worker_incident_result
  to aurum_worker, aurum_function_owner;

create table public.system_commands (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  type public.system_command_type not null,
  payload jsonb not null,
  payload_schema_version smallint not null default 1
    check (payload_schema_version = 1),
  status public.system_command_status not null default 'pending',
  requested_by uuid not null references public.profiles (id) on delete restrict,
  requested_at timestamptz not null default pg_catalog.clock_timestamp(),
  target_resource_type text
    check (target_resource_type is null or target_resource_type in (
      'trade_proposal', 'position', 'risk_policy'
    )),
  target_resource_id uuid,
  expected_resource_version integer
    check (expected_resource_version is null or expected_resource_version > 0),
  idempotency_key text not null,
  priority smallint not null default 0 check (priority between 0 and 100),
  claimed_at timestamptz,
  claimed_by text,
  lease_token uuid,
  lease_expires_at timestamptz,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  maximum_attempts integer not null default 3 check (maximum_attempts > 0),
  next_retry_at timestamptz,
  expires_at timestamptz not null,
  completed_at timestamptz,
  result_code text,
  result_message text,
  last_error text,
  command_version integer not null default 1 check (command_version > 0),
  event_sequence integer not null default 0 check (event_sequence >= 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.jsonb_typeof(payload) = 'object'),
  check (expires_at > requested_at),
  check (requested_by = owner_id),
  check (attempt_count <= maximum_attempts),
  check (status not in ('claimed', 'validating', 'executing') or attempt_count >= 1),
  check (pg_catalog.btrim(idempotency_key) <> '' and pg_catalog.length(idempotency_key) <= 160),
  check (claimed_by is null or (
    pg_catalog.btrim(claimed_by) <> '' and pg_catalog.length(claimed_by) <= 160
  )),
  check (
    (
      status in ('claimed', 'validating', 'executing')
      and claimed_at is not null
      and claimed_by is not null
      and lease_token is not null
      and lease_expires_at is not null
    )
    or
    (
      status not in ('claimed', 'validating', 'executing')
      and claimed_at is null
      and claimed_by is null
      and lease_token is null
      and lease_expires_at is null
    )
  ),
  check (claimed_at is null or lease_expires_at > claimed_at),
  check (lease_expires_at is null or lease_expires_at <= expires_at),
  check (
    (status in ('succeeded', 'rejected', 'failed', 'expired', 'cancelled') and completed_at is not null)
    or
    (status not in ('succeeded', 'rejected', 'failed', 'expired', 'cancelled') and completed_at is null)
  ),
  check (
    (type = 'ACTIVATE_EMERGENCY_STOP' and priority = 100)
    or
    (type <> 'ACTIVATE_EMERGENCY_STOP' and priority between 0 and 99)
  ),
  check (result_code is null or result_code ~ '^[A-Z][A-Z0-9_]{0,159}$'),
  check (result_message is null or pg_catalog.length(result_message) <= 512),
  check (last_error is null or pg_catalog.length(last_error) <= 512),
  unique (id, owner_id),
  unique (owner_id, idempotency_key)
);

create index system_commands_claim_idx
  on public.system_commands (
    owner_id,
    status,
    priority desc,
    next_retry_at,
    lease_expires_at,
    expires_at,
    requested_at,
    id
  );

create index system_commands_target_idx
  on public.system_commands (owner_id, target_resource_type, target_resource_id);

create table public.system_command_events (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  system_command_id uuid not null,
  sequence integer not null check (sequence > 0),
  event_type public.command_event_type not null,
  from_status public.system_command_status,
  to_status public.system_command_status,
  actor_type public.actor_type not null,
  actor_id text not null,
  result_code text,
  message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.btrim(actor_id) <> '' and pg_catalog.length(actor_id) <= 160),
  check (result_code is null or result_code ~ '^[A-Z][A-Z0-9_]{0,159}$'),
  check (message is null or pg_catalog.length(message) <= 512),
  check (pg_catalog.jsonb_typeof(metadata) = 'object'),
  check (pg_catalog.octet_length(metadata::text) <= 4096),
  unique (id, owner_id),
  unique (system_command_id, sequence),
  foreign key (system_command_id, owner_id)
    references public.system_commands (id, owner_id) on delete cascade
);

create index system_command_events_owner_command_idx
  on public.system_command_events (owner_id, system_command_id, sequence);

alter table public.trade_decisions
  add constraint trade_decisions_command_owner_fk
  foreign key (command_id, owner_id)
  references public.system_commands (id, owner_id) on delete restrict;

alter table public.risk_policy_versions
  add constraint risk_policy_versions_source_command_owner_fk
  foreign key (source_command_id, owner_id)
  references public.system_commands (id, owner_id) on delete restrict;

create table public.broker_orders (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trading_account_id uuid not null,
  trade_proposal_id uuid not null,
  system_command_id uuid not null,
  broker_order_reference text,
  direction public.trade_direction not null,
  requested_volume numeric(8, 4) not null
    check (requested_volume > 0 and requested_volume <= 0.01),
  requested_price numeric(24, 8) check (requested_price is null or requested_price > 0),
  stop_loss_price numeric(24, 8) not null check (stop_loss_price > 0),
  take_profit_price numeric(24, 8) not null check (take_profit_price > 0),
  status public.broker_order_status not null,
  broker_result_code text,
  broker_result_message text,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (broker_order_reference is null or (
    pg_catalog.btrim(broker_order_reference) <> ''
    and pg_catalog.length(broker_order_reference) <= 160
  )),
  check (broker_result_code is null or pg_catalog.length(broker_result_code) <= 160),
  check (broker_result_message is null or pg_catalog.length(broker_result_message) <= 512),
  unique (id, owner_id),
  unique (id, owner_id, trading_account_id, trade_proposal_id),
  unique (owner_id, broker_order_reference),
  foreign key (trading_account_id, owner_id)
    references public.trading_accounts (id, owner_id) on delete restrict,
  foreign key (trade_proposal_id, owner_id, trading_account_id)
    references public.trade_proposals (id, owner_id, trading_account_id) on delete restrict,
  foreign key (system_command_id, owner_id)
    references public.system_commands (id, owner_id) on delete restrict
);

create index broker_orders_owner_account_idx
  on public.broker_orders (owner_id, trading_account_id, created_at desc);

create table public.trade_executions (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  broker_order_id uuid not null,
  execution_kind public.broker_execution_kind not null,
  broker_deal_reference text not null,
  volume numeric(8, 4) not null check (volume > 0 and volume <= 0.01),
  price numeric(24, 8) not null check (price > 0),
  commission numeric(24, 8) not null default 0,
  swap numeric(24, 8) not null default 0,
  executed_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (
    pg_catalog.btrim(broker_deal_reference) <> ''
    and pg_catalog.length(broker_deal_reference) <= 160
  ),
  unique (id, owner_id),
  unique (owner_id, broker_deal_reference),
  foreign key (broker_order_id, owner_id)
    references public.broker_orders (id, owner_id) on delete restrict
);

create index trade_executions_owner_order_idx
  on public.trade_executions (owner_id, broker_order_id, executed_at);

create table public.positions (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trading_account_id uuid not null,
  trade_proposal_id uuid not null,
  broker_order_id uuid not null,
  broker_position_reference text not null,
  position_version integer not null default 1 check (position_version > 0),
  direction public.trade_direction not null,
  volume numeric(8, 4) not null check (volume > 0 and volume <= 0.01),
  entry_price numeric(24, 8) not null check (entry_price > 0),
  current_price numeric(24, 8) not null check (current_price > 0),
  stop_loss_price numeric(24, 8) not null check (stop_loss_price > 0),
  take_profit_price numeric(24, 8) not null check (take_profit_price > 0),
  unrealized_pnl numeric(24, 8) not null default 0,
  r_multiple numeric(16, 8) not null default 0,
  status public.position_status not null,
  opened_at timestamptz not null,
  closed_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (
    (direction = 'BUY' and stop_loss_price < entry_price and entry_price < take_profit_price)
    or
    (direction = 'SELL' and take_profit_price < entry_price and entry_price < stop_loss_price)
  ),
  check (
    (status = 'closed' and closed_at is not null)
    or (status <> 'closed' and closed_at is null)
  ),
  check (closed_at is null or closed_at >= opened_at),
  check (
    pg_catalog.btrim(broker_position_reference) <> ''
    and pg_catalog.length(broker_position_reference) <= 160
  ),
  unique (id, owner_id),
  unique (id, owner_id, position_version),
  unique (owner_id, trading_account_id, broker_position_reference),
  foreign key (trading_account_id, owner_id)
    references public.trading_accounts (id, owner_id) on delete restrict,
  foreign key (trade_proposal_id, owner_id, trading_account_id)
    references public.trade_proposals (id, owner_id, trading_account_id) on delete restrict,
  foreign key (broker_order_id, owner_id, trading_account_id, trade_proposal_id)
    references public.broker_orders (
      id, owner_id, trading_account_id, trade_proposal_id
    ) on delete restrict
);

create unique index positions_one_active_per_account_idx
  on public.positions (trading_account_id)
  where status in ('open', 'close_requested', 'closing', 'mismatch');
create index positions_owner_status_idx
  on public.positions (owner_id, status, opened_at desc);

create table public.position_events (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  position_id uuid not null,
  position_version integer not null check (position_version > 0),
  event_type public.position_event_type not null,
  actor_type public.actor_type not null,
  actor_id text not null,
  detail text not null,
  metadata jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.btrim(actor_id) <> '' and pg_catalog.length(actor_id) <= 160),
  check (pg_catalog.btrim(detail) <> '' and pg_catalog.length(detail) <= 512),
  check (pg_catalog.jsonb_typeof(metadata) = 'object'),
  check (pg_catalog.octet_length(metadata::text) <= 4096),
  unique (id, owner_id),
  foreign key (position_id, owner_id)
    references public.positions (id, owner_id) on delete cascade
);

create index position_events_owner_position_idx
  on public.position_events (owner_id, position_id, occurred_at);

create table public.system_components (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  code text not null,
  label_th text not null,
  plane public.system_plane not null,
  expected_heartbeat_seconds integer check (
    expected_heartbeat_seconds is null or expected_heartbeat_seconds > 0
  ),
  enabled boolean not null default true,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.btrim(code) <> '' and pg_catalog.length(code) <= 160),
  check (pg_catalog.btrim(label_th) <> '' and pg_catalog.length(label_th) <= 160),
  unique (id, owner_id),
  unique (owner_id, code)
);

create index system_components_owner_plane_idx
  on public.system_components (owner_id, plane, code);

create table public.system_heartbeats (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  system_component_id uuid not null,
  worker_id text not null,
  state public.system_health_state not null,
  detail text not null,
  observed_at timestamptz not null,
  expires_at timestamptz not null,
  version integer not null default 1 check (version > 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (expires_at > observed_at),
  check (pg_catalog.btrim(worker_id) <> '' and pg_catalog.length(worker_id) <= 160),
  check (pg_catalog.btrim(detail) <> '' and pg_catalog.length(detail) <= 512),
  unique (id, owner_id),
  unique (owner_id, system_component_id),
  foreign key (system_component_id, owner_id)
    references public.system_components (id, owner_id) on delete cascade
);

create index system_heartbeats_owner_state_idx
  on public.system_heartbeats (owner_id, state, observed_at desc);

create table public.system_incidents (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  code text not null,
  severity public.incident_severity not null,
  status public.incident_status not null default 'open',
  title text not null,
  detail text not null,
  request_id uuid,
  reported_by_worker_id text not null,
  occurred_at timestamptz not null,
  resolved_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (status <> 'resolved' or resolved_at is not null),
  check (resolved_at is null or resolved_at >= occurred_at),
  check (pg_catalog.btrim(code) <> '' and pg_catalog.length(code) <= 160),
  check (pg_catalog.btrim(title) <> '' and pg_catalog.length(title) <= 160),
  check (pg_catalog.btrim(detail) <> '' and pg_catalog.length(detail) <= 512),
  check (
    pg_catalog.btrim(reported_by_worker_id) <> ''
    and pg_catalog.length(reported_by_worker_id) <= 160
  ),
  unique (id, owner_id)
);

create index system_incidents_owner_status_idx
  on public.system_incidents (owner_id, status, severity, occurred_at desc);

create table public.audit_logs (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  actor_type public.actor_type not null,
  actor_id text not null,
  action text not null,
  target_type text not null,
  target_id uuid,
  request_id uuid not null,
  old_version integer check (old_version is null or old_version > 0),
  new_version integer check (new_version is null or new_version > 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.btrim(actor_id) <> '' and pg_catalog.length(actor_id) <= 160),
  check (pg_catalog.btrim(action) <> '' and pg_catalog.length(action) <= 160),
  check (pg_catalog.btrim(target_type) <> '' and pg_catalog.length(target_type) <= 160),
  check (pg_catalog.jsonb_typeof(metadata) = 'object'),
  check (pg_catalog.octet_length(metadata::text) <= 4096),
  unique (id, owner_id)
);

create index audit_logs_owner_time_idx
  on public.audit_logs (owner_id, created_at desc, id);
create index audit_logs_request_idx
  on public.audit_logs (request_id);

alter table public.broker_orders add constraint broker_orders_numeric_finite
  check (
    private.numeric_is_finite(requested_volume)
    and (requested_price is null or private.numeric_is_finite(requested_price))
    and private.numeric_is_finite(stop_loss_price)
    and private.numeric_is_finite(take_profit_price)
  );
alter table public.trade_executions add constraint trade_executions_numeric_finite
  check (
    private.numeric_is_finite(volume)
    and private.numeric_is_finite(price)
    and private.numeric_is_finite(commission)
    and private.numeric_is_finite(swap)
  );
alter table public.positions add constraint positions_numeric_finite
  check (
    private.numeric_is_finite(volume)
    and private.numeric_is_finite(entry_price)
    and private.numeric_is_finite(current_price)
    and private.numeric_is_finite(stop_loss_price)
    and private.numeric_is_finite(take_profit_price)
    and private.numeric_is_finite(unrealized_pnl)
    and private.numeric_is_finite(r_multiple)
  );

create or replace function private.reject_append_only_mutation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  raise exception using
    errcode = '55000',
    message = 'AURUM_APPEND_ONLY_RECORD';
end
$function$;

alter function private.reject_append_only_mutation() owner to aurum_function_owner;
revoke all on function private.reject_append_only_mutation() from public;

create trigger broker_symbols_append_only
before update or delete on public.broker_symbols
for each row execute function private.reject_append_only_mutation();

create trigger risk_policy_versions_append_only
before update or delete on public.risk_policy_versions
for each row execute function private.reject_append_only_mutation();

create trigger market_snapshots_append_only
before update or delete on public.market_snapshots
for each row execute function private.reject_append_only_mutation();

create trigger feature_snapshots_append_only
before update or delete on public.feature_snapshots
for each row execute function private.reject_append_only_mutation();

create trigger risk_checks_append_only
before update or delete on public.risk_checks
for each row execute function private.reject_append_only_mutation();

create trigger system_command_events_append_only
before update or delete on public.system_command_events
for each row execute function private.reject_append_only_mutation();

create trigger trade_executions_append_only
before update or delete on public.trade_executions
for each row execute function private.reject_append_only_mutation();

create trigger position_events_append_only
before update or delete on public.position_events
for each row execute function private.reject_append_only_mutation();

create trigger audit_logs_append_only
before update or delete on public.audit_logs
for each row execute function private.reject_append_only_mutation();

create or replace function private.validate_safe_metadata()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  metadata_key text;
begin
  if pg_catalog.jsonb_typeof(new.metadata) <> 'object'
     or pg_catalog.octet_length(new.metadata::text) > 4096 then
    raise exception using errcode = '22023', message = 'AURUM_UNSAFE_METADATA';
  end if;

  for metadata_key in
    select pg_catalog.lower(value)
    from pg_catalog.jsonb_object_keys(new.metadata) as keys(value)
  loop
    if metadata_key ~ '(token|password|secret|authorization|cookie|credential|header|exception|stack)' then
      raise exception using errcode = '22023', message = 'AURUM_UNSAFE_METADATA_KEY';
    end if;
  end loop;
  return new;
end
$function$;

alter function private.validate_safe_metadata() owner to aurum_function_owner;
revoke all on function private.validate_safe_metadata() from public;

create trigger system_command_events_safe_metadata
before insert on public.system_command_events
for each row execute function private.validate_safe_metadata();

create trigger position_events_safe_metadata
before insert on public.position_events
for each row execute function private.validate_safe_metadata();

create trigger audit_logs_safe_metadata
before insert on public.audit_logs
for each row execute function private.validate_safe_metadata();

create or replace function private.guard_system_command_update()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  bookkeeping_only boolean;
  lease_renewal boolean;
  fresh_claim boolean;
  recovered_claim boolean;
  lifecycle_progression boolean;
  retry_transition boolean;
  terminal_transition boolean;
begin
  if old.id is distinct from new.id
     or old.owner_id is distinct from new.owner_id
     or old.type is distinct from new.type
     or old.payload is distinct from new.payload
     or old.payload_schema_version is distinct from new.payload_schema_version
     or old.requested_by is distinct from new.requested_by
     or old.requested_at is distinct from new.requested_at
     or old.target_resource_type is distinct from new.target_resource_type
     or old.target_resource_id is distinct from new.target_resource_id
     or old.expected_resource_version is distinct from new.expected_resource_version
     or old.idempotency_key is distinct from new.idempotency_key
     or old.priority is distinct from new.priority
     or old.maximum_attempts is distinct from new.maximum_attempts
     or old.expires_at is distinct from new.expires_at
     or old.created_at is distinct from new.created_at then
    raise exception using errcode = '55000', message = 'AURUM_COMMAND_IDENTITY_IMMUTABLE';
  end if;

  bookkeeping_only := new.status = old.status
    and new.claimed_at is not distinct from old.claimed_at
    and new.claimed_by is not distinct from old.claimed_by
    and new.lease_token is not distinct from old.lease_token
    and new.lease_expires_at is not distinct from old.lease_expires_at
    and new.attempt_count = old.attempt_count
    and new.next_retry_at is not distinct from old.next_retry_at
    and new.completed_at is not distinct from old.completed_at
    and new.result_code is not distinct from old.result_code
    and new.result_message is not distinct from old.result_message
    and new.last_error is not distinct from old.last_error
    and new.command_version = old.command_version
    and new.event_sequence = old.event_sequence + 1
    and new.updated_at >= old.updated_at;

  if old.status in ('succeeded', 'rejected', 'failed', 'expired', 'cancelled') then
    if bookkeeping_only then
      return new;
    end if;
    raise exception using errcode = '55000', message = 'AURUM_COMMAND_TERMINAL';
  end if;

  lease_renewal := old.status in ('claimed', 'validating', 'executing')
    and new.status = old.status
    and new.claimed_at is not distinct from old.claimed_at
    and new.claimed_by is not distinct from old.claimed_by
    and new.lease_token is not distinct from old.lease_token
    and old.lease_expires_at > new.updated_at
    and new.lease_expires_at > old.lease_expires_at
    and new.lease_expires_at <= new.expires_at
    and new.attempt_count = old.attempt_count
    and new.next_retry_at is not distinct from old.next_retry_at
    and new.completed_at is not distinct from old.completed_at
    and new.result_code is not distinct from old.result_code
    and new.result_message is not distinct from old.result_message
    and new.last_error is not distinct from old.last_error
    and new.command_version = old.command_version + 1
    and new.event_sequence = old.event_sequence
    and new.updated_at >= old.updated_at;

  fresh_claim := old.status = 'pending'
    and new.status = 'claimed'
    and new.claimed_at is not null
    and new.claimed_by is not null
    and new.lease_token is not null
    and new.lease_expires_at > new.claimed_at
    and new.lease_expires_at <= new.expires_at
    and new.attempt_count = old.attempt_count + 1
    and new.next_retry_at is null
    and new.completed_at is not distinct from old.completed_at
    and new.result_code is not distinct from old.result_code
    and new.result_message is not distinct from old.result_message
    and new.last_error is not distinct from old.last_error
    and new.command_version = old.command_version + 1
    and new.event_sequence = old.event_sequence
    and new.updated_at >= old.updated_at
    and new.updated_at >= new.claimed_at;

  recovered_claim := old.status in ('claimed', 'validating')
    and new.status = 'claimed'
    and old.lease_expires_at <= new.claimed_at
    and new.claimed_at is not null
    and new.claimed_by is not null
    and new.lease_token is not null
    and new.lease_token is distinct from old.lease_token
    and new.lease_expires_at > new.claimed_at
    and new.lease_expires_at <= new.expires_at
    and new.attempt_count = old.attempt_count + 1
    and new.next_retry_at is null
    and new.completed_at is not distinct from old.completed_at
    and new.result_code is not distinct from old.result_code
    and new.result_message is not distinct from old.result_message
    and new.last_error is not distinct from old.last_error
    and new.command_version = old.command_version + 1
    and new.event_sequence = old.event_sequence
    and new.updated_at >= old.updated_at
    and new.updated_at >= new.claimed_at;

  lifecycle_progression := (
      (old.status = 'claimed' and new.status = 'validating')
      or (old.status = 'validating' and new.status = 'executing')
    )
    and new.claimed_at is not distinct from old.claimed_at
    and new.claimed_by is not distinct from old.claimed_by
    and new.lease_token is not distinct from old.lease_token
    and new.lease_expires_at is not distinct from old.lease_expires_at
    and new.lease_expires_at > new.updated_at
    and new.expires_at > new.updated_at
    and new.attempt_count = old.attempt_count
    and new.next_retry_at is not distinct from old.next_retry_at
    and new.completed_at is not distinct from old.completed_at
    and new.result_code is not distinct from old.result_code
    and new.result_message is not distinct from old.result_message
    and new.last_error is not distinct from old.last_error
    and new.command_version = old.command_version + 1
    and new.event_sequence = old.event_sequence
    and new.updated_at >= old.updated_at;

  retry_transition := old.status in ('claimed', 'validating')
    and new.status = 'pending'
    and old.lease_expires_at > new.updated_at
    and new.claimed_at is null
    and new.claimed_by is null
    and new.lease_token is null
    and new.lease_expires_at is null
    and new.attempt_count = old.attempt_count
    and new.next_retry_at > new.updated_at
    and new.next_retry_at < new.expires_at
    and new.completed_at is null
    and new.result_code is null
    and new.result_message is null
    and new.command_version = old.command_version + 1
    and new.event_sequence = old.event_sequence
    and new.updated_at >= old.updated_at;

  terminal_transition := (
      (old.status = 'pending' and new.status in ('failed', 'expired', 'cancelled'))
      or (old.status = 'claimed' and new.status in ('rejected', 'failed', 'expired', 'cancelled'))
      or (old.status = 'validating' and new.status in (
        'succeeded', 'rejected', 'failed', 'expired', 'cancelled'
      ))
      or (old.status = 'executing' and new.status in ('succeeded', 'rejected', 'failed'))
    )
    and new.claimed_at is null
    and new.claimed_by is null
    and new.lease_token is null
    and new.lease_expires_at is null
    and new.attempt_count = old.attempt_count
    and new.next_retry_at is null
    and new.completed_at is not null
    and new.completed_at = new.updated_at
    and new.result_code is not null
    and (new.status = 'failed' or new.last_error is null)
    and new.command_version = old.command_version + 1
    and new.event_sequence = old.event_sequence
    and new.updated_at >= old.updated_at;

  if bookkeeping_only
    or lease_renewal
    or fresh_claim
    or recovered_claim
    or lifecycle_progression
    or retry_transition
    or terminal_transition then
    return new;
  end if;

  raise exception using errcode = '55000', message = 'AURUM_INVALID_COMMAND_DELTA';
end
$function$;

alter function private.guard_system_command_update() owner to aurum_function_owner;
revoke all on function private.guard_system_command_update() from public;

create trigger system_commands_guard_update
before update on public.system_commands
for each row execute function private.guard_system_command_update();

comment on table public.system_commands is
  'Durable command truth. Realtime may wake a Worker but is not required for claim, lease, retry, or completion correctness.';
comment on table public.broker_orders is
  'Schema foundation only. Milestone 1 exposes no insert/update function and contains no broker call.';
comment on table public.trade_executions is
  'Schema foundation only. Milestone 1 records no execution behavior.';
comment on table public.positions is
  'Schema foundation only. Milestone 1 exposes no Position mutation function.';
