-- Aurum Console Milestone 1: least-privilege Worker queue and health actions.
-- There is deliberately no broker-order, trade-execution, or Position-write RPC.

create or replace function private.safe_worker_text(value text)
returns boolean
language sql
immutable
security definer
set search_path = ''
as $function$
  select value is null or (
    pg_catalog.btrim(value) <> ''
    and pg_catalog.length(value) <= 512
    and value !~ '[[:cntrl:]]'
    and value !~*
      '(bearer[[:space:]]|authorization[[:space:]]*[:=]|password[[:space:]]*[:=]|token[[:space:]]*[:=]|secret[[:space:]]*[:=]|client[_-]?secret[[:space:]]*[:=]|api[_-]?key[[:space:]]*[:=]|access[_-]?key[[:space:]]*[:=]|sb_secret_)'
    and value !~
      '(^|[^A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}[.][A-Za-z0-9_-]{8,}[.][A-Za-z0-9_-]{8,}($|[^A-Za-z0-9_-])'
    and value !~
      '(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,})'
    and value !~*
      '(postgres(ql)?|mysql|redis|amqps?|mongodb([+]srv)?)://[^[:space:]/:@]+:[^[:space:]/@]+@'
    and value !~* '-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----'
  )
$function$;

-- Result codes are browser-readable machine identifiers. Keep the table
-- boundary fail-closed as well as validating public Worker RPC inputs, so a
-- privileged direct insert cannot persist a secret-shaped identifier.
create or replace function private.guard_safe_result_code()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if new.result_code is not null and (
    new.result_code !~ '^[A-Z][A-Z0-9_]{0,159}$'
    or not private.safe_worker_text(new.result_code)
  ) then
    raise exception using errcode = '22023', message = 'AURUM_INVALID_RESULT_CODE';
  end if;
  return new;
end
$function$;

create trigger system_commands_00_validate_result_code
before insert or update of result_code on public.system_commands
for each row execute function private.guard_safe_result_code();

create trigger system_command_events_00_validate_result_code
before insert or update of result_code on public.system_command_events
for each row execute function private.guard_safe_result_code();

create or replace function private.terminalize_unexecutable_commands(
  p_owner_id uuid,
  p_actor_id text,
  p_observed_at timestamptz
)
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  candidate public.system_commands%rowtype;
  terminal_status public.system_command_status;
  terminal_code text;
  terminal_message text;
  terminal_count integer := 0;
begin
  for candidate in
    select command_row.*
    from public.system_commands as command_row
    where command_row.owner_id = p_owner_id
      and command_row.status in ('pending', 'claimed', 'validating')
      and (
        command_row.expires_at <= p_observed_at
        or (
          command_row.attempt_count >= command_row.maximum_attempts
          and (
            command_row.status = 'pending'
            or command_row.lease_expires_at <= p_observed_at
          )
        )
      )
    order by command_row.requested_at, command_row.id
    for update skip locked
  loop
    if candidate.expires_at <= p_observed_at then
      terminal_status := 'expired';
      terminal_code := 'COMMAND_EXPIRED';
      terminal_message := 'Command expired before deterministic execution could begin.';
    else
      terminal_status := 'failed';
      terminal_code := 'MAXIMUM_ATTEMPTS_EXHAUSTED';
      terminal_message := 'Maximum claim attempts exhausted before deterministic execution.';
    end if;

    update public.system_commands as command_row
    set status = terminal_status,
        claimed_at = null,
        claimed_by = null,
        lease_token = null,
        lease_expires_at = null,
        next_retry_at = null,
        completed_at = p_observed_at,
        result_code = terminal_code,
        result_message = terminal_message,
        last_error = null,
        command_version = command_row.command_version + 1,
        updated_at = p_observed_at
    where command_row.id = candidate.id;

    perform private.append_command_event(
      candidate.id,
      'status_changed',
      candidate.status,
      terminal_status,
      'worker',
      p_actor_id,
      terminal_code,
      terminal_message,
      pg_catalog.jsonb_build_object(
        'attemptCount', candidate.attempt_count,
        'maximumAttempts', candidate.maximum_attempts,
        'deterministicTerminalization', true
      )
    );
    perform private.append_audit(
      p_owner_id,
      'worker',
      p_actor_id,
      case terminal_status
        when 'expired' then 'command_expired'
        else 'command_attempts_exhausted'
      end,
      'system_command',
      candidate.id,
      candidate.id,
      candidate.command_version,
      candidate.command_version + 1,
      pg_catalog.jsonb_build_object(
        'resultCode', terminal_code,
        'deterministicTerminalization', true
      )
    );
    terminal_count := terminal_count + 1;
  end loop;

  return terminal_count;
end
$function$;

create or replace function public.worker_claim_next_command(
  lease_seconds integer default 30
)
returns public.worker_claim_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  v_now timestamptz := pg_catalog.clock_timestamp();
  candidate public.system_commands%rowtype;
  previous_status public.system_command_status;
  event_kind public.command_event_type;
  claimed_lease_token uuid;
  claimed_lease_expires_at timestamptz;
  next_version integer;
begin
  if v_owner_id is null
    or v_worker_id is null
    or not private.safe_worker_text(v_worker_id)
    or v_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$' then
    return (
      false, null, null, null, null, null, 'WORKER_UNAUTHORIZED'
    )::public.worker_claim_result;
  end if;
  if lease_seconds is null or lease_seconds not between 5 and 300 then
    return (
      false, null, null, null, null, null, 'INVALID_LEASE_DURATION'
    )::public.worker_claim_result;
  end if;

  perform private.terminalize_unexecutable_commands(
    v_owner_id, v_worker_id, v_now
  );

  select command.* into candidate
  from public.system_commands as command
  where command.owner_id = v_owner_id
    and command.expires_at > v_now
    and (command.next_retry_at is null or command.next_retry_at <= v_now)
    and command.attempt_count < command.maximum_attempts
    and (
      command.status = 'pending'
      or (
        command.status in ('claimed', 'validating')
        and command.lease_expires_at <= v_now
      )
    )
  order by command.priority desc, command.requested_at, command.id
  for update skip locked
  limit 1;

  if not found then
    return (
      false, null, null, null, null, null, 'NO_ELIGIBLE_COMMAND'
    )::public.worker_claim_result;
  end if;

  previous_status := candidate.status;
  event_kind := case
    when previous_status = 'pending' then 'claimed'::public.command_event_type
    else 'claim_recovered'::public.command_event_type
  end;
  claimed_lease_token := pg_catalog.gen_random_uuid();
  claimed_lease_expires_at := least(
    v_now + pg_catalog.make_interval(secs => lease_seconds),
    candidate.expires_at
  );
  next_version := candidate.command_version + 1;

  update public.system_commands
  set status = 'claimed',
      claimed_at = v_now,
      claimed_by = v_worker_id,
      lease_token = claimed_lease_token,
      lease_expires_at = claimed_lease_expires_at,
      attempt_count = attempt_count + 1,
      next_retry_at = null,
      command_version = next_version,
      updated_at = v_now
  where id = candidate.id;

  perform private.append_command_event(
    candidate.id,
    event_kind,
    previous_status,
    'claimed',
    'worker',
    v_worker_id,
    case when event_kind = 'claim_recovered' then 'LEASE_RECOVERED' else 'CLAIMED' end,
    null,
    pg_catalog.jsonb_build_object('attempt', candidate.attempt_count + 1)
  );
  perform private.append_audit(
    v_owner_id,
    'worker',
    v_worker_id,
    case when event_kind = 'claim_recovered' then 'command_claim_recovered' else 'command_claimed' end,
    'system_command',
    candidate.id,
    candidate.id,
    candidate.command_version,
    candidate.command_version + 1,
    pg_catalog.jsonb_build_object('attempt', candidate.attempt_count + 1)
  );

  return (
    true,
    candidate.id,
    'claimed',
    claimed_lease_token,
    claimed_lease_expires_at,
    next_version,
    'CLAIMED'
  )::public.worker_claim_result;
end
$function$;

create or replace function public.worker_renew_command_lease(
  command_id uuid,
  lease_token uuid,
  lease_seconds integer default 30
)
returns public.worker_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  v_now timestamptz := pg_catalog.clock_timestamp();
  command public.system_commands%rowtype;
  next_version integer;
  proposed_lease_expires_at timestamptz;
begin
  if v_owner_id is null
    or v_worker_id is null
    or not private.safe_worker_text(v_worker_id)
    or v_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$' then
    return (false, command_id, null, null, 'WORKER_UNAUTHORIZED')::public.worker_action_result;
  end if;
  if lease_seconds is null or lease_seconds not between 5 and 300 then
    return (false, command_id, null, null, 'INVALID_LEASE_DURATION')::public.worker_action_result;
  end if;

  select * into command from public.system_commands as command_row
  where command_row.id = command_id and command_row.owner_id = v_owner_id
  for update;
  if not found then
    return (false, command_id, null, null, 'COMMAND_NOT_FOUND')::public.worker_action_result;
  end if;
  if command.claimed_by is distinct from v_worker_id
    or command.lease_token is distinct from lease_token then
    return (false, command_id, command.status, command.command_version, 'LEASE_NOT_OWNED')::public.worker_action_result;
  end if;
  if command.status not in ('claimed', 'validating', 'executing') then
    return (false, command_id, command.status, command.command_version, 'COMMAND_NOT_LEASED')::public.worker_action_result;
  end if;
  if command.lease_expires_at <= v_now then
    return (false, command_id, command.status, command.command_version, 'LEASE_EXPIRED')::public.worker_action_result;
  end if;

  if command.expires_at <= v_now then
    return (false, command_id, command.status, command.command_version, 'COMMAND_EXPIRED')::public.worker_action_result;
  end if;

  proposed_lease_expires_at := least(
    v_now + pg_catalog.make_interval(secs => lease_seconds),
    command.expires_at
  );
  if proposed_lease_expires_at <= command.lease_expires_at then
    return (false, command_id, command.status, command.command_version, 'LEASE_NOT_EXTENDED')::public.worker_action_result;
  end if;

  next_version := command.command_version + 1;
  update public.system_commands
  set lease_expires_at = proposed_lease_expires_at,
      command_version = next_version,
      updated_at = v_now
  where id = command_id;
  perform private.append_command_event(
    command_id, 'lease_renewed', command.status, command.status,
    'worker', v_worker_id, 'LEASE_RENEWED', null,
    pg_catalog.jsonb_build_object(
      'requestedLeaseSeconds', lease_seconds,
      'clampedToCommandExpiry', proposed_lease_expires_at = command.expires_at
    )
  );
  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id,
    'command_lease_renewed', 'system_command', command_id,
    command_id, command.command_version, next_version,
    pg_catalog.jsonb_build_object(
      'requestedLeaseSeconds', lease_seconds,
      'clampedToCommandExpiry', proposed_lease_expires_at = command.expires_at
    )
  );
  return (true, command_id, command.status, next_version, 'LEASE_RENEWED')::public.worker_action_result;
end
$function$;

create or replace function private.worker_transition_command(
  command_id uuid,
  lease_token uuid,
  target_status public.system_command_status,
  transition_result_code text default null,
  transition_result_message text default null,
  transition_last_error text default null,
  retryable boolean default false,
  retry_at timestamptz default null
)
returns public.worker_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  v_now timestamptz := pg_catalog.clock_timestamp();
  command public.system_commands%rowtype;
  actual_status public.system_command_status;
  next_version integer;
  pending_policy_version public.risk_policy_versions%rowtype;
  policy public.risk_policies%rowtype;
begin
  if v_owner_id is null
    or v_worker_id is null
    or not private.safe_worker_text(v_worker_id)
    or v_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$' then
    return (false, command_id, null, null, 'WORKER_UNAUTHORIZED')::public.worker_action_result;
  end if;
  if transition_result_code is not null and (
    transition_result_code !~ '^[A-Z][A-Z0-9_]{0,159}$'
    or not private.safe_worker_text(transition_result_code)
  ) then
    return (false, command_id, null, null, 'INVALID_RESULT_CODE')::public.worker_action_result;
  end if;
  if not private.safe_worker_text(transition_result_message) then
    return (false, command_id, null, null, 'UNSAFE_RESULT_MESSAGE')::public.worker_action_result;
  end if;
  if not private.safe_worker_text(transition_last_error) then
    return (false, command_id, null, null, 'UNSAFE_LAST_ERROR')::public.worker_action_result;
  end if;

  select * into command from public.system_commands as command_row
  where command_row.id = command_id and command_row.owner_id = v_owner_id
  for update;
  if not found then
    return (false, command_id, null, null, 'COMMAND_NOT_FOUND')::public.worker_action_result;
  end if;

  if command.status in ('succeeded', 'rejected', 'failed', 'expired', 'cancelled') then
    if command.status = target_status
      and command.result_code is not distinct from transition_result_code
      and command.result_message is not distinct from transition_result_message
      and command.last_error is not distinct from transition_last_error
      and exists (
        select 1
        from public.system_command_events as terminal_event
        where terminal_event.system_command_id = command.id
          and terminal_event.owner_id = v_owner_id
          and terminal_event.to_status = command.status
          and terminal_event.actor_type = 'worker'
          and terminal_event.actor_id = v_worker_id
      ) then
      return (
        true, command_id, command.status, command.command_version, 'IDEMPOTENT_COMPLETION'
      )::public.worker_action_result;
    end if;
    return (
      false, command_id, command.status, command.command_version, 'TERMINAL_STATE_CONFLICT'
    )::public.worker_action_result;
  end if;

  if command.claimed_by is distinct from v_worker_id
    or command.lease_token is distinct from lease_token then
    return (false, command_id, command.status, command.command_version, 'LEASE_NOT_OWNED')::public.worker_action_result;
  end if;
  if command.lease_expires_at <= v_now then
    return (false, command_id, command.status, command.command_version, 'LEASE_EXPIRED')::public.worker_action_result;
  end if;
  if command.expires_at <= v_now then
    return (false, command_id, command.status, command.command_version, 'COMMAND_EXPIRED')::public.worker_action_result;
  end if;

  if retryable
    and command.status in ('claimed', 'validating')
    and command.attempt_count < command.maximum_attempts then
    if retry_at is null or retry_at <= v_now or retry_at >= command.expires_at then
      return (false, command_id, command.status, command.command_version, 'INVALID_RETRY_TIME')::public.worker_action_result;
    end if;
    next_version := command.command_version + 1;
    update public.system_commands
    set status = 'pending',
        claimed_at = null,
        claimed_by = null,
        lease_token = null,
        lease_expires_at = null,
        next_retry_at = retry_at,
        result_code = null,
        result_message = null,
        last_error = transition_last_error,
        command_version = next_version,
        updated_at = v_now
    where id = command_id;
    perform private.append_command_event(
      command_id, 'retry_scheduled', command.status, 'pending',
      'worker', v_worker_id, 'RETRY_SCHEDULED', null,
      pg_catalog.jsonb_build_object('attempt', command.attempt_count)
    );
    perform private.append_audit(
      v_owner_id, 'worker', v_worker_id,
      'command_retry_scheduled', 'system_command', command_id,
      command_id, command.command_version, next_version,
      pg_catalog.jsonb_build_object(
        'attempt', command.attempt_count,
        'nextRetryAt', retry_at
      )
    );
    return (true, command_id, 'pending', next_version, 'RETRY_SCHEDULED')::public.worker_action_result;
  end if;

  if target_status = 'validating' and command.status <> 'claimed' then
    return (false, command_id, command.status, command.command_version, 'INVALID_TRANSITION')::public.worker_action_result;
  end if;
  if target_status = 'executing' and command.status <> 'validating' then
    return (false, command_id, command.status, command.command_version, 'INVALID_TRANSITION')::public.worker_action_result;
  end if;
  if target_status = 'succeeded' and command.status not in ('validating', 'executing') then
    return (false, command_id, command.status, command.command_version, 'INVALID_TRANSITION')::public.worker_action_result;
  end if;
  if target_status in ('rejected', 'failed')
    and command.status not in ('claimed', 'validating', 'executing') then
    return (false, command_id, command.status, command.command_version, 'INVALID_TRANSITION')::public.worker_action_result;
  end if;
  if target_status in ('succeeded', 'rejected', 'failed')
    and transition_result_code is null then
    return (false, command_id, command.status, command.command_version, 'RESULT_CODE_REQUIRED')::public.worker_action_result;
  end if;

  if target_status = 'succeeded' and command.type = 'REQUEST_RISK_POLICY_CHANGE' then
    select * into policy from public.risk_policies as policy_row
    where policy_row.id = command.target_resource_id
      and policy_row.owner_id = v_owner_id
    for update;
    if not found or policy.resource_version <> command.expected_resource_version then
      return (
        false, command_id, command.status, command.command_version, 'STALE_RISK_POLICY_VERSION'
      )::public.worker_action_result;
    end if;
    select * into pending_policy_version
    from public.risk_policy_versions as version_row
    where version_row.source_command_id = command_id
      and version_row.owner_id = v_owner_id;
    if not found then
      return (
        false, command_id, command.status, command.command_version, 'RISK_POLICY_VERSION_NOT_FOUND'
      )::public.worker_action_result;
    end if;
  end if;

  next_version := command.command_version + 1;
  actual_status := target_status;
  update public.system_commands as command_row
  set status = actual_status,
      claimed_at = case
        when actual_status in ('succeeded', 'rejected', 'failed') then null
        else command_row.claimed_at
      end,
      claimed_by = case
        when actual_status in ('succeeded', 'rejected', 'failed') then null
        else command_row.claimed_by
      end,
      lease_token = case
        when actual_status in ('succeeded', 'rejected', 'failed') then null
        else command_row.lease_token
      end,
      lease_expires_at = case
        when actual_status in ('succeeded', 'rejected', 'failed') then null
        else command_row.lease_expires_at
      end,
      completed_at = case
        when actual_status in ('succeeded', 'rejected', 'failed') then v_now
        else null
      end,
      result_code = case
        when actual_status in ('succeeded', 'rejected', 'failed') then transition_result_code
        else null
      end,
      result_message = case
        when actual_status in ('succeeded', 'rejected', 'failed') then transition_result_message
        else null
      end,
      last_error = case when actual_status = 'failed' then transition_last_error else null end,
      command_version = next_version,
      updated_at = v_now
  where id = command_id;

  if actual_status = 'succeeded' and command.type = 'REQUEST_RISK_POLICY_CHANGE' then
    update public.risk_policies
    set active_version_id = pending_policy_version.id,
        resource_version = resource_version + 1,
        updated_at = v_now
    where id = policy.id;
    perform private.append_audit(
      v_owner_id, 'worker', v_worker_id,
      'risk_policy_version_activated', 'risk_policy', policy.id,
      command_id, policy.resource_version, policy.resource_version + 1,
      pg_catalog.jsonb_build_object('policyVersion', pending_policy_version.version)
    );
  end if;

  perform private.append_command_event(
    command_id, 'status_changed', command.status, actual_status,
    'worker', v_worker_id, transition_result_code,
    transition_result_message, '{}'::jsonb
  );
  if actual_status in ('validating', 'executing') then
    perform private.append_audit(
      v_owner_id, 'worker', v_worker_id,
      case actual_status
        when 'validating' then 'command_validation_started'
        else 'command_execution_started'
      end,
      'system_command', command_id, command_id,
      command.command_version, next_version,
      pg_catalog.jsonb_build_object(
        'fromStatus', command.status,
        'toStatus', actual_status
      )
    );
  elsif actual_status in ('succeeded', 'rejected', 'failed') then
    perform private.append_audit(
      v_owner_id, 'worker', v_worker_id,
      case actual_status
        when 'succeeded' then 'command_completed'
        when 'rejected' then 'command_rejected'
        else 'command_failed'
      end,
      'system_command', command_id, command_id,
      command.command_version, next_version,
      pg_catalog.jsonb_build_object('resultCode', transition_result_code)
    );
  end if;
  return (true, command_id, actual_status, next_version, transition_result_code)::public.worker_action_result;
end
$function$;

create or replace function public.worker_mark_command_validating(
  command_id uuid,
  lease_token uuid
)
returns public.worker_action_result
language sql
security definer
set search_path = ''
as $function$
  select private.worker_transition_command(
    command_id, lease_token, 'validating', null, null, null, false, null
  )
$function$;

create or replace function public.worker_mark_command_executing(
  command_id uuid,
  lease_token uuid
)
returns public.worker_action_result
language sql
security definer
set search_path = ''
as $function$
  select private.worker_transition_command(
    command_id, lease_token, 'executing', null, null, null, false, null
  )
$function$;

create or replace function public.worker_complete_command(
  command_id uuid,
  lease_token uuid,
  result_code text,
  result_message text default null
)
returns public.worker_action_result
language sql
security definer
set search_path = ''
as $function$
  select private.worker_transition_command(
    command_id, lease_token, 'succeeded', result_code, result_message,
    null, false, null
  )
$function$;

create or replace function public.worker_reject_command(
  command_id uuid,
  lease_token uuid,
  result_code text,
  result_message text default null
)
returns public.worker_action_result
language sql
security definer
set search_path = ''
as $function$
  select private.worker_transition_command(
    command_id, lease_token, 'rejected', result_code, result_message,
    null, false, null
  )
$function$;

create or replace function public.worker_fail_command(
  command_id uuid,
  lease_token uuid,
  result_code text,
  result_message text,
  last_error text,
  retryable boolean default false,
  next_retry_at timestamptz default null
)
returns public.worker_action_result
language sql
security definer
set search_path = ''
as $function$
  select private.worker_transition_command(
    command_id, lease_token, 'failed', result_code, result_message,
    last_error, retryable, next_retry_at
  )
$function$;

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
  heartbeat_version integer;
begin
  if v_owner_id is null
    or v_worker_id is null
    or not private.safe_worker_text(v_worker_id)
    or v_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$' then
    return 'WORKER_UNAUTHORIZED';
  end if;
  if not private.is_identifier(component_code)
    or detail is null or not private.safe_worker_text(detail) then
    return 'INVALID_HEARTBEAT';
  end if;
  if state is null
    or observed_at is null
    or observed_at > pg_catalog.clock_timestamp() + interval '1 minute'
    or valid_for_seconds is null
    or valid_for_seconds not between 5 and 300 then
    return 'INVALID_HEARTBEAT';
  end if;
  select * into component from public.system_components as component_row
  where component_row.owner_id = v_owner_id
    and component_row.code = pg_catalog.btrim(component_code)
    and component_row.plane = 'execution_plane'
    and component_row.enabled;
  if not found then
    return 'COMPONENT_NOT_FOUND';
  end if;

  insert into public.system_heartbeats as heartbeat_target (
    owner_id, system_component_id, worker_id, state, detail,
    observed_at, expires_at
  ) values (
    v_owner_id, component.id, v_worker_id, state, pg_catalog.btrim(detail),
    observed_at, observed_at + pg_catalog.make_interval(secs => valid_for_seconds)
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
  returning heartbeat_target.id, heartbeat_target.version
    into heartbeat_id, heartbeat_version;

  if heartbeat_id is null then
    return 'STALE_HEARTBEAT';
  end if;
  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id,
    case heartbeat_version
      when 1 then 'heartbeat_recorded'
      else 'heartbeat_updated'
    end,
    'system_heartbeat', heartbeat_id, heartbeat_id,
    case heartbeat_version when 1 then null else heartbeat_version - 1 end,
    heartbeat_version,
    pg_catalog.jsonb_build_object(
      'componentCode', component.code,
      'state', state,
      'observedAt', observed_at
    )
  );
  return 'HEARTBEAT_RECORDED';
end
$function$;

create unique index system_incidents_request_idempotency_idx
  on public.system_incidents (owner_id, request_id)
  where request_id is not null;

create or replace function public.worker_record_incident(
  code text,
  severity public.incident_severity,
  title text,
  detail text,
  occurred_at timestamptz,
  request_id uuid default null
)
returns public.worker_incident_result
language plpgsql
security definer
set search_path = ''
as $function$
#variable_conflict use_column
declare
  v_owner_id uuid := private.worker_owner_id();
  v_worker_id text := private.worker_identifier();
  incident_id uuid;
  existing_incident public.system_incidents%rowtype;
begin
  if v_owner_id is null
    or v_worker_id is null
    or not private.safe_worker_text(v_worker_id)
    or v_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$' then
    return (
      false, null, false, 'WORKER_UNAUTHORIZED'
    )::public.worker_incident_result;
  end if;
  if $1 is null
    or $1 !~ '^[A-Z][A-Z0-9_]{0,159}$'
    or not private.safe_worker_text($1) then
    return (
      false, null, false, 'INVALID_INCIDENT_CODE'
    )::public.worker_incident_result;
  end if;
  if $2 is null then
    return (
      false, null, false, 'INVALID_INCIDENT_SEVERITY'
    )::public.worker_incident_result;
  end if;
  if $3 is null
    or not private.is_identifier($3)
    or not private.safe_worker_text($3) then
    return (
      false, null, false, 'INVALID_INCIDENT_TITLE'
    )::public.worker_incident_result;
  end if;
  if $4 is null or not private.safe_worker_text($4) then
    return (
      false, null, false, 'INVALID_INCIDENT_DETAIL'
    )::public.worker_incident_result;
  end if;
  if $5 is null then
    return (
      false, null, false, 'INVALID_INCIDENT_TIME'
    )::public.worker_incident_result;
  end if;

  insert into public.system_incidents as incident_target (
    owner_id, code, severity, status, title, detail,
    request_id, reported_by_worker_id, occurred_at
  ) values (
    v_owner_id, pg_catalog.btrim($1), $2, 'open',
    pg_catalog.btrim($3), pg_catalog.btrim($4), $6,
    v_worker_id, $5
  )
  on conflict (owner_id, request_id)
    where incident_target.request_id is not null
  do nothing
  returning id into incident_id;

  if incident_id is null and $6 is not null then
    select incident.* into existing_incident
    from public.system_incidents as incident
    where incident.owner_id = v_owner_id
      and incident.request_id = $6;
    if not found then
      return (
        false, null, false, 'INCIDENT_NOT_RECORDED'
      )::public.worker_incident_result;
    end if;
    if existing_incident.code = pg_catalog.btrim($1)
      and existing_incident.severity = $2
      and existing_incident.title = pg_catalog.btrim($3)
      and existing_incident.detail = pg_catalog.btrim($4)
      and existing_incident.occurred_at = $5 then
      return (
        true, existing_incident.id, false, 'IDEMPOTENT_REPLAY'
      )::public.worker_incident_result;
    end if;
    return (
      false, null, false, 'IDEMPOTENCY_CONFLICT'
    )::public.worker_incident_result;
  end if;
  if incident_id is null then
    return (
      false, null, false, 'INCIDENT_NOT_RECORDED'
    )::public.worker_incident_result;
  end if;

  perform private.append_audit(
    v_owner_id, 'worker', v_worker_id,
    'incident_recorded', 'system_incident', incident_id,
    coalesce($6, incident_id), null, null,
    pg_catalog.jsonb_build_object('code', pg_catalog.btrim($1), 'severity', $2::text)
  );
  return (
    true, incident_id, true, 'CREATED'
  )::public.worker_incident_result;
end
$function$;

alter function public.worker_claim_next_command(integer) owner to aurum_function_owner;
alter function private.safe_worker_text(text) owner to aurum_function_owner;
alter function private.guard_safe_result_code() owner to aurum_function_owner;
alter function private.terminalize_unexecutable_commands(uuid, text, timestamptz)
  owner to aurum_function_owner;
alter function public.worker_renew_command_lease(uuid, uuid, integer) owner to aurum_function_owner;
alter function private.worker_transition_command(
  uuid, uuid, public.system_command_status, text, text, text, boolean, timestamptz
) owner to aurum_function_owner;
alter function public.worker_mark_command_validating(uuid, uuid) owner to aurum_function_owner;
alter function public.worker_mark_command_executing(uuid, uuid) owner to aurum_function_owner;
alter function public.worker_complete_command(uuid, uuid, text, text) owner to aurum_function_owner;
alter function public.worker_reject_command(uuid, uuid, text, text) owner to aurum_function_owner;
alter function public.worker_fail_command(uuid, uuid, text, text, text, boolean, timestamptz) owner to aurum_function_owner;
alter function public.worker_record_heartbeat(text, public.system_health_state, text, timestamptz, integer) owner to aurum_function_owner;
alter function public.worker_record_incident(text, public.incident_severity, text, text, timestamptz, uuid) owner to aurum_function_owner;

revoke all on function private.worker_transition_command(
  uuid, uuid, public.system_command_status, text, text, text, boolean, timestamptz
) from public, anon, authenticated, aurum_worker;
revoke all on function private.safe_worker_text(text)
  from public, anon, authenticated, aurum_worker;
revoke all on function private.guard_safe_result_code()
  from public, anon, authenticated, aurum_worker;
revoke all on function private.terminalize_unexecutable_commands(uuid, text, timestamptz)
  from public, anon, authenticated, aurum_worker;
revoke all on function public.worker_claim_next_command(integer) from public, anon, authenticated;
revoke all on function public.worker_renew_command_lease(uuid, uuid, integer) from public, anon, authenticated;
revoke all on function public.worker_mark_command_validating(uuid, uuid) from public, anon, authenticated;
revoke all on function public.worker_mark_command_executing(uuid, uuid) from public, anon, authenticated;
revoke all on function public.worker_complete_command(uuid, uuid, text, text) from public, anon, authenticated;
revoke all on function public.worker_reject_command(uuid, uuid, text, text) from public, anon, authenticated;
revoke all on function public.worker_fail_command(uuid, uuid, text, text, text, boolean, timestamptz) from public, anon, authenticated;
revoke all on function public.worker_record_heartbeat(text, public.system_health_state, text, timestamptz, integer) from public, anon, authenticated;
revoke all on function public.worker_record_incident(text, public.incident_severity, text, text, timestamptz, uuid) from public, anon, authenticated;

grant execute on function public.worker_claim_next_command(integer) to aurum_worker;
grant execute on function public.worker_renew_command_lease(uuid, uuid, integer) to aurum_worker;
grant execute on function public.worker_mark_command_validating(uuid, uuid) to aurum_worker;
grant execute on function public.worker_mark_command_executing(uuid, uuid) to aurum_worker;
grant execute on function public.worker_complete_command(uuid, uuid, text, text) to aurum_worker;
grant execute on function public.worker_reject_command(uuid, uuid, text, text) to aurum_worker;
grant execute on function public.worker_fail_command(uuid, uuid, text, text, text, boolean, timestamptz) to aurum_worker;
grant execute on function public.worker_record_heartbeat(text, public.system_health_state, text, timestamptz, integer) to aurum_worker;
grant execute on function public.worker_record_incident(text, public.incident_severity, text, text, timestamptz, uuid) to aurum_worker;

-- Normalize ACLs only after every Milestone-1 function exists and ownership
-- has been transferred. PostgreSQL otherwise gives a newly created function a
-- NULL ACL whose effective default includes PUBLIC EXECUTE.
set local role aurum_function_owner;

revoke execute on all functions in schema public, private
  from public, anon, authenticated, aurum_worker;

-- Supabase CLI 2.x applies migrations and seed.sql as the local `postgres`
-- role. CHECK constraints evaluate this private finite-number predicate as the
-- inserting role, so grant only that one deterministic seed helper.
grant execute on function private.numeric_is_finite(numeric)
  to postgres;

-- Worker RLS policies evaluate this helper as the calling Worker role. The
-- worker identifier helper remains private to SECURITY DEFINER RPC bodies.
grant execute on function private.worker_owner_id()
  to aurum_worker;

grant execute on function public.request_proposal_approval(
  uuid, integer, text, uuid, timestamptz
) to authenticated;
grant execute on function public.request_proposal_rejection(
  uuid, integer, text, text, timestamptz
) to authenticated;
grant execute on function public.request_pause_new_trades(
  text, text, timestamptz
) to authenticated;
grant execute on function public.request_resume_system(
  uuid, text, timestamptz
) to authenticated;
grant execute on function public.request_emergency_stop(
  text, text, timestamptz
) to authenticated;
grant execute on function public.request_position_close(
  uuid, integer, text, text, timestamptz
) to authenticated;
grant execute on function public.request_stop_loss_change(
  uuid, integer, numeric, text, timestamptz
) to authenticated;
grant execute on function public.request_take_profit_change(
  uuid, integer, numeric, text, timestamptz
) to authenticated;
grant execute on function public.request_risk_policy_change(
  text, numeric, text, integer, text, timestamptz
) to authenticated;

grant execute on function public.worker_claim_next_command(integer)
  to aurum_worker;
grant execute on function public.worker_renew_command_lease(uuid, uuid, integer)
  to aurum_worker;
grant execute on function public.worker_mark_command_validating(uuid, uuid)
  to aurum_worker;
grant execute on function public.worker_mark_command_executing(uuid, uuid)
  to aurum_worker;
grant execute on function public.worker_complete_command(uuid, uuid, text, text)
  to aurum_worker;
grant execute on function public.worker_reject_command(uuid, uuid, text, text)
  to aurum_worker;
grant execute on function public.worker_fail_command(
  uuid, uuid, text, text, text, boolean, timestamptz
) to aurum_worker;
grant execute on function public.worker_record_heartbeat(
  text, public.system_health_state, text, timestamptz, integer
) to aurum_worker;
grant execute on function public.worker_record_incident(
  text, public.incident_severity, text, text, timestamptz, uuid
) to aurum_worker;

reset role;

-- worker_claim_next_command is owner-scoped and uses SKIP LOCKED. Expired
-- executing leases are never reissued automatically. Worker completion updates
-- control-plane records only; no function here calls MT5 or writes Position state.

revoke create on schema public from aurum_function_owner;
revoke create on schema private from aurum_function_owner;
