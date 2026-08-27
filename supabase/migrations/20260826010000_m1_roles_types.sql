-- Aurum Console Milestone 1: database roles, private helpers, and closed status sets.
-- This migration creates authorization roles only. It does not create or mint a
-- Worker credential.

do $migration$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'aurum_function_owner'
  ) then
    create role aurum_function_owner nologin noinherit nobypassrls;
  end if;

  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'aurum_worker'
  ) then
    create role aurum_worker nologin noinherit nobypassrls;
  end if;
end
$migration$;

alter role aurum_function_owner nologin noinherit nobypassrls;
alter role aurum_worker nologin noinherit nobypassrls;

-- The local Supabase migration role must be able to transfer SECURITY DEFINER
-- functions to the dedicated NOLOGIN owner. Membership confers SET only: it
-- does not make application sessions inherit the function owner's privileges.
grant aurum_function_owner to postgres
  with admin false, inherit false, set true;

-- PostgREST can assume this role only when a separately issued local Worker JWT
-- carries role=aurum_worker. No JWT or secret is created in this milestone.
grant aurum_worker to authenticator;

create schema if not exists private;
revoke all on schema private from public;
grant usage, create on schema private to aurum_function_owner;
-- Required temporarily so PostgreSQL permits ownership transfer of secured
-- public RPCs. The final Milestone 1 migration revokes CREATE again.
grant usage, create on schema public to aurum_function_owner;

-- PostgreSQL numeric accepts NaN and infinities, while the shared contracts
-- require finite values. Every persisted numeric field and numeric RPC input
-- uses this immutable fail-closed predicate.
create function private.numeric_is_finite(value numeric)
returns boolean
language sql
immutable
security definer
set search_path = ''
as $function$
  select value is not null
    and value not in (
      'NaN'::numeric,
      'Infinity'::numeric,
      '-Infinity'::numeric
    )
$function$;

alter function private.numeric_is_finite(numeric) owner to aurum_function_owner;
revoke all on function private.numeric_is_finite(numeric)
  from public, anon, authenticated, aurum_worker;
grant execute on function private.numeric_is_finite(numeric)
  to aurum_function_owner;

create type public.runtime_system_state as enum (
  'running',
  'paused',
  'emergency_stop',
  'recovering'
);

create type public.trade_direction as enum ('BUY', 'SELL');

create type public.trade_proposal_status as enum (
  'candidate',
  'validated',
  'pending_approval',
  'approved',
  'rejected',
  'blocked',
  'expired',
  'execution_pending',
  'executed',
  'failed'
);

create type public.eligibility_outcome as enum ('auto', 'ask', 'block');
create type public.risk_check_state as enum ('pass', 'warn', 'fail', 'na');
create type public.trade_decision_kind as enum ('approve', 'reject');

create type public.system_command_type as enum (
  'APPROVE_PROPOSAL',
  'REJECT_PROPOSAL',
  'PAUSE_NEW_TRADES',
  'RESUME_SYSTEM',
  'ACTIVATE_EMERGENCY_STOP',
  'REQUEST_POSITION_CLOSE',
  'REQUEST_STOP_LOSS_CHANGE',
  'REQUEST_TAKE_PROFIT_CHANGE',
  'REQUEST_RISK_POLICY_CHANGE'
);

create type public.system_command_status as enum (
  'pending',
  'claimed',
  'validating',
  'executing',
  'succeeded',
  'rejected',
  'failed',
  'expired',
  'cancelled'
);

create type public.command_event_type as enum (
  'created',
  'claimed',
  'claim_recovered',
  'lease_renewed',
  'status_changed',
  'retry_scheduled'
);

create type public.actor_type as enum ('user', 'worker', 'system');
create type public.system_plane as enum ('control_plane', 'execution_plane');

create type public.system_health_state as enum (
  'healthy',
  'degraded',
  'warning',
  'failed',
  'unknown'
);

create type public.incident_severity as enum ('critical', 'warning', 'info');
create type public.incident_status as enum ('open', 'resolved');

create type public.market_session as enum (
  'asia',
  'london',
  'newyork',
  'overlap'
);

create type public.market_regime as enum (
  'trending',
  'range',
  'high_volatility',
  'news_risk'
);

create type public.market_freshness as enum ('live', 'delayed', 'stale');
create type public.market_transport as enum (
  'realtime_broadcast',
  'database_fallback'
);

create type public.position_status as enum (
  'open',
  'close_requested',
  'closing',
  'closed',
  'mismatch'
);

create type public.position_event_type as enum (
  'observed',
  'status_changed',
  'mismatch_detected',
  'reconciled'
);

create type public.broker_order_status as enum (
  'recorded',
  'submitted',
  'accepted',
  'rejected',
  'cancelled',
  'failed'
);

create type public.broker_execution_kind as enum (
  'open',
  'close',
  'stop_loss_change',
  'take_profit_change'
);

create type public.command_action_result as (
  accepted boolean,
  command_id uuid,
  created boolean,
  status public.system_command_status,
  result_code text
);

create type public.worker_action_result as (
  accepted boolean,
  command_id uuid,
  status public.system_command_status,
  command_version integer,
  result_code text
);

-- PostgreSQL grants EXECUTE on new functions to PUBLIC by default. Revoke it
-- for functions created by both migration and secured-function owner roles.
alter default privileges for role postgres in schema public
  revoke execute on functions from public;
alter default privileges for role postgres in schema private
  revoke execute on functions from public;

-- Functions are created by the migration role and then transferred to the
-- NOLOGIN owner. PostgreSQL does not permit this local migration role to alter
-- another role's future defaults, so every transferred function is also
-- explicitly revoked below at creation time and is covered by catalog tests.

comment on role aurum_worker is
  'Dedicated least-privilege Aurum Worker database role; no credential is stored or minted by migrations.';
comment on type public.system_command_type is
  'Must remain in parity with SystemCommandPayloadMap in TypeScript and Pydantic.';
comment on type public.system_command_status is
  'Durable queue lifecycle. Realtime is notification-only and is never required for correctness.';
