-- Aurum Console Milestone 2: bounded component heartbeat liveness.
-- Routine heartbeats are operational telemetry and deliberately do not append
-- security-audit rows. Important lifecycle incidents keep their separate,
-- audited incident path.

grant create on schema public to aurum_function_owner;
set local role aurum_function_owner;

create or replace function public.worker_record_heartbeat(
  component_code text,
  state public.system_health_state,
  detail text,
  observed_at timestamptz,
  valid_for_seconds integer default 30
)
returns text
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  component public.system_components%rowtype;
  heartbeat_id uuid;
begin
  if v_owner_id is null
    or v_worker_id is null
    or not private.safe_worker_text(v_worker_id)
    or v_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$' then
    return 'WORKER_UNAUTHORIZED';
  end if;
  if component_code is null
    or component_code not in (
      'execution.worker',
      'execution.mt5_adapter',
      'execution.market_data'
    )
    or detail is null
    or detail not in (
      'HEALTHY',
      'MT5_PACKAGE_NOT_INSTALLED',
      'UNSUPPORTED_PLATFORM',
      'TERMINAL_PATH_NOT_CONFIGURED',
      'TERMINAL_NOT_FOUND',
      'INITIALIZE_FAILED',
      'TERMINAL_INFO_UNAVAILABLE',
      'TERMINAL_DISCONNECTED',
      'ACCOUNT_INFO_UNAVAILABLE',
      'TRADE_MODE_UNKNOWN',
      'CONTEST_ACCOUNT_BLOCKED',
      'REAL_ACCOUNT_BLOCKED',
      'ACCOUNT_BINDING_MISMATCH',
      'DEMO_ACCOUNT_UNBOUND',
      'SYMBOL_NOT_CONFIGURED',
      'SYMBOL_NOT_FOUND',
      'SYMBOL_AMBIGUOUS',
      'SYMBOL_NOT_VISIBLE',
      'SYMBOL_CANONICAL_MISMATCH',
      'SYMBOL_SPEC_INCOMPLETE',
      'SYMBOL_SPEC_CONFIRMATION_REQUIRED',
      'SYMBOL_SPEC_CHANGED',
      'TICK_UNAVAILABLE',
      'TICK_INVALID',
      'TICK_DELAYED',
      'TICK_STALE',
      'TICK_FROM_FUTURE',
      'CLOCK_DRIFT_EXCEEDED',
      'CANDLE_DATA_INVALID',
      'CANDLE_DATA_STALE',
      'HISTORY_EMPTY_VALID_RESULT',
      'HISTORY_QUERY_FAILED',
      'HISTORY_WINDOW_INCOMPLETE',
      'RECONCILIATION_INCOMPLETE',
      'DATABASE_REPORT_FAILED',
      'NATIVE_ACCESS_CONFLICT'
    ) then
    return 'INVALID_HEARTBEAT';
  end if;
  if state is null
    or state not in ('healthy', 'degraded', 'failed')
    or (state = 'healthy' and detail <> 'HEALTHY')
    or (state <> 'healthy' and detail = 'HEALTHY')
    or (
      component_code = 'execution.market_data'
      and (
        (state = 'degraded' and detail <> 'TICK_DELAYED')
        or (
          state = 'failed'
          and detail not in (
            'TICK_INVALID',
            'TICK_STALE',
            'TICK_FROM_FUTURE',
            'TICK_UNAVAILABLE'
          )
        )
      )
    )
    or observed_at is null
    or observed_at > pg_catalog.clock_timestamp() + interval '1 minute'
    or valid_for_seconds is null
    or valid_for_seconds not between 15 and 300 then
    return 'INVALID_HEARTBEAT';
  end if;

  select * into component
  from public.system_components as component_row
  where component_row.owner_id = v_owner_id
    and component_row.code = component_code
    and component_row.plane = 'execution_plane'
    and component_row.enabled;
  if not found then
    return 'COMPONENT_NOT_FOUND';
  end if;

  insert into public.system_heartbeats as heartbeat_target (
    owner_id,
    system_component_id,
    worker_id,
    state,
    detail,
    observed_at,
    expires_at
  ) values (
    v_owner_id,
    component.id,
    v_worker_id,
    state,
    pg_catalog.btrim(detail),
    observed_at,
    observed_at + pg_catalog.make_interval(secs => valid_for_seconds)
  )
  on conflict (owner_id, system_component_id) do update
    set worker_id = excluded.worker_id,
        state = excluded.state,
        detail = excluded.detail,
        observed_at = excluded.observed_at,
        expires_at = excluded.expires_at,
        version = heartbeat_target.version + 1,
        updated_at = pg_catalog.clock_timestamp()
    where excluded.observed_at >= heartbeat_target.observed_at
  returning heartbeat_target.id into heartbeat_id;

  if heartbeat_id is null then
    return 'STALE_HEARTBEAT';
  end if;
  return 'HEARTBEAT_RECORDED';
end
$function$;

alter function public.worker_record_heartbeat(
  text,
  public.system_health_state,
  text,
  timestamptz,
  integer
) owner to aurum_function_owner;

comment on function public.worker_record_heartbeat(
  text,
  public.system_health_state,
  text,
  timestamptz,
  integer
) is
  'Owner-scoped bounded upsert for the three read-only MT5 execution component heartbeats; detail is a strict MT5 reason code and routine renewals do not append audit rows.';

reset role;
revoke create on schema public from aurum_function_owner;

set local role aurum_function_owner;
revoke all on function public.worker_record_heartbeat(
  text,
  public.system_health_state,
  text,
  timestamptz,
  integer
) from public, anon, authenticated, aurum_worker;

grant execute on function public.worker_record_heartbeat(
  text,
  public.system_health_state,
  text,
  timestamptz,
  integer
) to aurum_worker;

reset role;
