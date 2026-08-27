-- Aurum Console Milestone 1: default-deny RLS and least-privilege grants.

-- Read only the request-local claims installed by PostgREST. Keeping these
-- helpers private avoids granting the NOLOGIN function owner access to the
-- broader auth schema merely to identify the invoking session.
create or replace function private.session_claims()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  raw_claims text := pg_catalog.current_setting('request.jwt.claims', true);
begin
  if raw_claims is null or pg_catalog.btrim(raw_claims) = '' then
    return '{}'::jsonb;
  end if;
  return raw_claims::jsonb;
exception when invalid_text_representation then
  return '{}'::jsonb;
end
$function$;

create or replace function private.session_user_id()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  claim_value text := nullif(
    pg_catalog.current_setting('request.jwt.claim.sub', true), ''
  );
begin
  if claim_value is null then
    claim_value := private.session_claims() ->> 'sub';
  end if;
  if claim_value is null or pg_catalog.btrim(claim_value) = '' then
    return null;
  end if;
  return claim_value::uuid;
exception when invalid_text_representation then
  return null;
end
$function$;

create or replace function private.worker_owner_id()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  claim_value text;
begin
  claim_value := private.session_claims() ->> 'owner_id';
  if claim_value is null or pg_catalog.btrim(claim_value) = '' then
    return null;
  end if;
  begin
    return claim_value::uuid;
  exception when invalid_text_representation then
    return null;
  end;
end
$function$;

create or replace function private.worker_identifier()
returns text
language sql
stable
security definer
set search_path = ''
as $function$
  select case
    when pg_catalog.length(
      pg_catalog.btrim(private.session_claims() ->> 'worker_id')
    ) between 1 and 160
      then pg_catalog.btrim(private.session_claims() ->> 'worker_id')
    else null
  end
$function$;

alter function private.session_claims() owner to aurum_function_owner;
alter function private.session_user_id() owner to aurum_function_owner;
alter function private.worker_owner_id() owner to aurum_function_owner;
alter function private.worker_identifier() owner to aurum_function_owner;
revoke all on function private.session_claims() from public, anon, authenticated, aurum_worker;
revoke all on function private.session_user_id() from public, anon, authenticated, aurum_worker;
revoke all on function private.worker_owner_id() from public, anon, authenticated, aurum_worker;
revoke all on function private.worker_identifier() from public, anon, authenticated, aurum_worker;
grant execute on function private.worker_owner_id() to aurum_worker, aurum_function_owner;
grant execute on function private.worker_identifier() to aurum_function_owner;
grant usage on schema private to aurum_worker;

alter table public.profiles enable row level security;
alter table public.profiles force row level security;
alter table public.trading_accounts enable row level security;
alter table public.trading_accounts force row level security;
alter table public.broker_symbols enable row level security;
alter table public.broker_symbols force row level security;
alter table public.trading_modes enable row level security;
alter table public.trading_modes force row level security;
alter table public.risk_policies enable row level security;
alter table public.risk_policies force row level security;
alter table public.risk_policy_versions enable row level security;
alter table public.risk_policy_versions force row level security;
alter table public.market_snapshots enable row level security;
alter table public.market_snapshots force row level security;
alter table public.feature_snapshots enable row level security;
alter table public.feature_snapshots force row level security;
alter table public.trade_proposals enable row level security;
alter table public.trade_proposals force row level security;
alter table public.risk_checks enable row level security;
alter table public.risk_checks force row level security;
alter table public.trade_decisions enable row level security;
alter table public.trade_decisions force row level security;
alter table public.system_commands enable row level security;
alter table public.system_commands force row level security;
alter table public.system_command_events enable row level security;
alter table public.system_command_events force row level security;
alter table public.broker_orders enable row level security;
alter table public.broker_orders force row level security;
alter table public.trade_executions enable row level security;
alter table public.trade_executions force row level security;
alter table public.positions enable row level security;
alter table public.positions force row level security;
alter table public.position_events enable row level security;
alter table public.position_events force row level security;
alter table public.system_components enable row level security;
alter table public.system_components force row level security;
alter table public.system_heartbeats enable row level security;
alter table public.system_heartbeats force row level security;
alter table public.system_incidents enable row level security;
alter table public.system_incidents force row level security;
alter table public.audit_logs enable row level security;
alter table public.audit_logs force row level security;

create policy profiles_owner_select on public.profiles
for select to authenticated
using (id = (select auth.uid()));
create policy profiles_owner_update on public.profiles
for update to authenticated
using (id = (select auth.uid()))
with check (id = (select auth.uid()));

create policy trading_accounts_owner_select on public.trading_accounts
for select to authenticated
using (owner_id = (select auth.uid()));
create policy broker_symbols_owner_select on public.broker_symbols
for select to authenticated
using (owner_id = (select auth.uid()));
create policy trading_modes_owner_select on public.trading_modes
for select to authenticated
using (owner_id = (select auth.uid()));
create policy risk_policies_owner_select on public.risk_policies
for select to authenticated
using (owner_id = (select auth.uid()));
create policy risk_policy_versions_owner_select on public.risk_policy_versions
for select to authenticated
using (owner_id = (select auth.uid()));
create policy market_snapshots_owner_select on public.market_snapshots
for select to authenticated
using (owner_id = (select auth.uid()));
create policy feature_snapshots_owner_select on public.feature_snapshots
for select to authenticated
using (owner_id = (select auth.uid()));
create policy trade_proposals_owner_select on public.trade_proposals
for select to authenticated
using (owner_id = (select auth.uid()));
create policy risk_checks_owner_select on public.risk_checks
for select to authenticated
using (owner_id = (select auth.uid()));
create policy trade_decisions_owner_select on public.trade_decisions
for select to authenticated
using (owner_id = (select auth.uid()));
create policy system_commands_owner_select on public.system_commands
for select to authenticated
using (owner_id = (select auth.uid()));
create policy system_command_events_owner_select on public.system_command_events
for select to authenticated
using (owner_id = (select auth.uid()));
create policy broker_orders_owner_select on public.broker_orders
for select to authenticated
using (owner_id = (select auth.uid()));
create policy trade_executions_owner_select on public.trade_executions
for select to authenticated
using (owner_id = (select auth.uid()));
create policy positions_owner_select on public.positions
for select to authenticated
using (owner_id = (select auth.uid()));
create policy position_events_owner_select on public.position_events
for select to authenticated
using (owner_id = (select auth.uid()));
create policy system_components_owner_select on public.system_components
for select to authenticated
using (owner_id = (select auth.uid()));
create policy system_heartbeats_owner_select on public.system_heartbeats
for select to authenticated
using (owner_id = (select auth.uid()));
create policy system_incidents_owner_select on public.system_incidents
for select to authenticated
using (owner_id = (select auth.uid()));
create policy audit_logs_owner_select on public.audit_logs
for select to authenticated
using (owner_id = (select auth.uid()));

-- The browser reads command progress through this security-invoker view. The
-- active lease token is deliberately absent, so an authenticated owner cannot
-- copy the Worker's claim proof even for their own command.
create view public.system_command_read_models
with (security_invoker = true)
as
select
  id,
  owner_id,
  type,
  payload_schema_version,
  status,
  requested_by,
  requested_at,
  target_resource_type,
  target_resource_id,
  expected_resource_version,
  idempotency_key,
  priority,
  claimed_at,
  claimed_by,
  lease_expires_at,
  attempt_count,
  maximum_attempts,
  next_retry_at,
  expires_at,
  completed_at,
  result_code,
  result_message,
  command_version,
  event_sequence,
  created_at,
  updated_at
from public.system_commands;

revoke all on public.system_command_read_models from public, anon, authenticated, aurum_worker;

-- The Worker can read only records for the owner_id carried in its dedicated
-- local test claim. It receives no direct write policy on any table.
create policy trading_accounts_worker_select on public.trading_accounts
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy broker_symbols_worker_select on public.broker_symbols
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy trading_modes_worker_select on public.trading_modes
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy risk_policies_worker_select on public.risk_policies
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy risk_policy_versions_worker_select on public.risk_policy_versions
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy trade_proposals_worker_select on public.trade_proposals
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy risk_checks_worker_select on public.risk_checks
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy system_commands_worker_select on public.system_commands
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy system_command_events_worker_select on public.system_command_events
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy positions_worker_select on public.positions
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy system_components_worker_select on public.system_components
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy system_heartbeats_worker_select on public.system_heartbeats
for select to aurum_worker
using (owner_id = private.worker_owner_id());
create policy system_incidents_worker_select on public.system_incidents
for select to aurum_worker
using (owner_id = private.worker_owner_id());

-- Security-definer functions run as this non-login role. Give that role only
-- the table operations exercised by the nine intent and nine Worker RPCs.
-- In particular, Milestone 1 has no function-owner policy on broker orders,
-- executions, Position events, or the market/feature ingestion tables.
create policy risk_policies_function_select on public.risk_policies
for select to aurum_function_owner using (true);
create policy risk_policies_function_update on public.risk_policies
for update to aurum_function_owner using (true) with check (true);

create policy risk_policy_versions_function_select on public.risk_policy_versions
for select to aurum_function_owner using (true);
create policy risk_policy_versions_function_insert on public.risk_policy_versions
for insert to aurum_function_owner with check (true);

create policy trade_proposals_function_select on public.trade_proposals
for select to aurum_function_owner using (true);
create policy trade_decisions_function_select on public.trade_decisions
for select to aurum_function_owner using (true);
create policy trade_decisions_function_insert on public.trade_decisions
for insert to aurum_function_owner with check (true);

create policy system_commands_function_select on public.system_commands
for select to aurum_function_owner using (true);
create policy system_commands_function_insert on public.system_commands
for insert to aurum_function_owner with check (true);
create policy system_commands_function_update on public.system_commands
for update to aurum_function_owner using (true) with check (true);

create policy system_command_events_function_select on public.system_command_events
for select to aurum_function_owner using (true);
create policy system_command_events_function_insert on public.system_command_events
for insert to aurum_function_owner with check (true);

create policy positions_function_select on public.positions
for select to aurum_function_owner using (true);
create policy system_components_function_select on public.system_components
for select to aurum_function_owner using (true);

create policy system_heartbeats_function_select on public.system_heartbeats
for select to aurum_function_owner using (true);
create policy system_heartbeats_function_insert on public.system_heartbeats
for insert to aurum_function_owner with check (true);
create policy system_heartbeats_function_update on public.system_heartbeats
for update to aurum_function_owner using (true) with check (true);

create policy system_incidents_function_select on public.system_incidents
for select to aurum_function_owner using (true);
create policy system_incidents_function_insert on public.system_incidents
for insert to aurum_function_owner with check (true);
create policy audit_logs_function_insert on public.audit_logs
for insert to aurum_function_owner with check (true);

revoke all on
  public.profiles,
  public.trading_accounts,
  public.broker_symbols,
  public.trading_modes,
  public.risk_policies,
  public.risk_policy_versions,
  public.market_snapshots,
  public.feature_snapshots,
  public.trade_proposals,
  public.risk_checks,
  public.trade_decisions,
  public.system_commands,
  public.system_command_events,
  public.broker_orders,
  public.trade_executions,
  public.positions,
  public.position_events,
  public.system_components,
  public.system_heartbeats,
  public.system_incidents,
  public.audit_logs
from public, anon, authenticated, aurum_worker, aurum_function_owner;
grant usage on schema public to anon, authenticated, aurum_worker;

grant select on public.profiles to authenticated;
grant update (display_name, locale, timezone) on public.profiles to authenticated;
grant select on
  public.trading_accounts,
  public.broker_symbols,
  public.trading_modes,
  public.risk_policies,
  public.risk_policy_versions,
  public.market_snapshots,
  public.feature_snapshots,
  public.trade_proposals,
  public.risk_checks,
  public.trade_decisions,
  public.system_command_events,
  public.broker_orders,
  public.trade_executions,
  public.positions,
  public.position_events,
  public.system_components,
  public.system_heartbeats,
  public.system_incidents,
  public.audit_logs
to authenticated;
grant select on public.system_command_read_models to authenticated;
-- SECURITY INVOKER views require the caller to hold privileges on every base
-- column referenced by the view. Grant only the safe projection: the browser
-- cannot select payload, lease_token, or raw last_error from the base table.
grant select (
  id, owner_id, type, payload_schema_version, status, requested_by,
  requested_at, target_resource_type, target_resource_id,
  expected_resource_version, idempotency_key, priority, claimed_at,
  claimed_by, lease_expires_at, attempt_count, maximum_attempts,
  next_retry_at, expires_at, completed_at, result_code, result_message,
  command_version, event_sequence, created_at, updated_at
) on public.system_commands to authenticated;

grant select on
  public.trading_accounts,
  public.broker_symbols,
  public.trading_modes,
  public.risk_policies,
  public.risk_policy_versions,
  public.trade_proposals,
  public.risk_checks,
  public.system_commands,
  public.system_command_events,
  public.positions,
  public.system_components,
  public.system_heartbeats,
  public.system_incidents
to aurum_worker;

grant usage on schema public, private to aurum_function_owner;
grant select on
  public.risk_policies,
  public.risk_policy_versions,
  public.trade_proposals,
  public.trade_decisions,
  public.system_commands,
  public.system_command_events,
  public.positions,
  public.system_components,
  public.system_heartbeats,
  public.system_incidents
to aurum_function_owner;
grant insert on
  public.risk_policy_versions,
  public.trade_decisions,
  public.system_commands,
  public.system_command_events,
  public.system_heartbeats,
  public.system_incidents,
  public.audit_logs
to aurum_function_owner;
grant update on
  public.risk_policies,
  public.system_commands,
  public.system_heartbeats
to aurum_function_owner;

create or replace function private.touch_profile()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  new.version := old.version + 1;
  new.updated_at := pg_catalog.clock_timestamp();
  return new;
end
$function$;

alter function private.touch_profile() owner to aurum_function_owner;
revoke all on function private.touch_profile() from public, anon, authenticated, aurum_worker;

create trigger profiles_touch_version
before update on public.profiles
for each row execute function private.touch_profile();

comment on schema private is
  'Non-exposed Aurum validation and authorization helpers. Browser roles receive no general access.';
