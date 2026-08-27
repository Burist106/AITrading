-- Aurum Console Milestone 1: strict command payload validation and nine
-- authenticated, idempotent intent actions. These functions only record
-- control-plane intent; none calls a broker or mutates a Position.

create or replace function private.is_uuid(value text)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $function$
begin
  if value is null then
    return false;
  end if;
  perform value::uuid;
  return true;
exception when invalid_text_representation then
  return false;
end
$function$;

create or replace function private.is_identifier(value text)
returns boolean
language sql
immutable
security definer
set search_path = ''
as $function$
  select value is not null
    and pg_catalog.btrim(value) <> ''
    and pg_catalog.length(value) <= 160
$function$;

create or replace function private.json_positive_integer(payload jsonb, key_name text)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $function$
declare
  parsed numeric;
begin
  if pg_catalog.jsonb_typeof(payload -> key_name) <> 'number' then
    return false;
  end if;
  parsed := (payload ->> key_name)::numeric;
  return private.numeric_is_finite(parsed)
    and parsed > 0
    and parsed = pg_catalog.trunc(parsed)
    and parsed <= 2147483647;
exception when others then
  return false;
end
$function$;

create or replace function private.json_positive_number(payload jsonb, key_name text)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $function$
declare
  parsed numeric;
begin
  if pg_catalog.jsonb_typeof(payload -> key_name) <> 'number' then
    return false;
  end if;
  parsed := (payload ->> key_name)::numeric;
  return private.numeric_is_finite(parsed) and parsed > 0;
exception when others then
  return false;
end
$function$;

create or replace function private.json_number(payload jsonb, key_name text)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $function$
begin
  if pg_catalog.jsonb_typeof(payload -> key_name) <> 'number' then
    return false;
  end if;
  return private.numeric_is_finite((payload ->> key_name)::numeric);
exception when others then
  return false;
end
$function$;

create or replace function private.json_has_exact_keys(
  payload jsonb,
  required_keys text[],
  optional_keys text[] default '{}'::text[]
)
returns boolean
language sql
immutable
security definer
set search_path = ''
as $function$
  select pg_catalog.jsonb_typeof(payload) = 'object'
    and payload ?& required_keys
    and not exists (
      select 1
      from pg_catalog.jsonb_object_keys(payload) as supplied(key_name)
      where not (supplied.key_name = any (required_keys || optional_keys))
    )
$function$;

create or replace function private.risk_rule_value_is_safe(
  rule_key text,
  new_value numeric
)
returns boolean
language sql
immutable
security definer
set search_path = ''
as $function$
  select private.numeric_is_finite(new_value) and case rule_key
    when 'risk_per_trade_pct' then new_value between 0 and 0.25
    when 'daily_loss_limit_pct' then new_value between 0 and 1.00
    when 'weekly_loss_limit_pct' then new_value between 0 and 3.00
    when 'maximum_drawdown_pct' then new_value between 0 and 5.00
    when 'maximum_trades_per_day' then
      new_value between 0 and 3 and new_value = pg_catalog.trunc(new_value)
    when 'minimum_risk_reward' then new_value between 1.50 and 9999.9999
    when 'stale_data_max_age_seconds' then
      new_value between 0 and 10 and new_value = pg_catalog.trunc(new_value)
    when 'maximum_spread_points' then new_value between 0 and 3.50
    when 'news_blackout_minutes' then
      new_value between 15 and 2147483647
      and new_value = pg_catalog.trunc(new_value)
    else false
  end
$function$;

create or replace function private.assert_system_command_payload(
  command_type public.system_command_type,
  payload jsonb,
  target_resource_type text,
  target_resource_id uuid,
  expected_resource_version integer
)
returns void
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if pg_catalog.jsonb_typeof(payload) <> 'object' then
    raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
  end if;

  case command_type
    when 'APPROVE_PROPOSAL' then
      if not private.json_has_exact_keys(
          payload,
          array['proposalId', 'proposalVersion'],
          array['approvalSessionId']
        )
        or pg_catalog.jsonb_typeof(payload -> 'proposalId') <> 'string'
        or not private.is_uuid(payload ->> 'proposalId')
        or not private.json_positive_integer(payload, 'proposalVersion')
        or (
          payload ? 'approvalSessionId'
          and (
            pg_catalog.jsonb_typeof(payload -> 'approvalSessionId') <> 'string'
            or not private.is_uuid(payload ->> 'approvalSessionId')
          )
        )
        or target_resource_type <> 'trade_proposal'
        or target_resource_id is null
        or target_resource_id <> (payload ->> 'proposalId')::uuid
        or expected_resource_version <> (payload ->> 'proposalVersion')::integer then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;

    when 'REJECT_PROPOSAL' then
      if not private.json_has_exact_keys(
          payload,
          array['proposalId', 'proposalVersion', 'reason']
        )
        or pg_catalog.jsonb_typeof(payload -> 'proposalId') <> 'string'
        or not private.is_uuid(payload ->> 'proposalId')
        or not private.json_positive_integer(payload, 'proposalVersion')
        or pg_catalog.jsonb_typeof(payload -> 'reason') <> 'string'
        or not private.is_identifier(payload ->> 'reason')
        or target_resource_type <> 'trade_proposal'
        or target_resource_id is null
        or target_resource_id <> (payload ->> 'proposalId')::uuid
        or expected_resource_version <> (payload ->> 'proposalVersion')::integer then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;

    when 'PAUSE_NEW_TRADES' then
      if not private.json_has_exact_keys(payload, '{}'::text[], array['reason'])
        or (
          payload ? 'reason'
          and (
            pg_catalog.jsonb_typeof(payload -> 'reason') <> 'string'
            or not private.is_identifier(payload ->> 'reason')
          )
        )
        or target_resource_type is not null
        or target_resource_id is not null
        or expected_resource_version is not null then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;

    when 'RESUME_SYSTEM' then
      if not private.json_has_exact_keys(payload, array['checklistAcknowledgementId'])
        or pg_catalog.jsonb_typeof(payload -> 'checklistAcknowledgementId') <> 'string'
        or not private.is_uuid(payload ->> 'checklistAcknowledgementId')
        or target_resource_type is not null
        or target_resource_id is not null
        or expected_resource_version is not null then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;

    when 'ACTIVATE_EMERGENCY_STOP' then
      if not private.json_has_exact_keys(payload, array['reason'])
        or pg_catalog.jsonb_typeof(payload -> 'reason') <> 'string'
        or not private.is_identifier(payload ->> 'reason')
        or target_resource_type is not null
        or target_resource_id is not null
        or expected_resource_version is not null then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;

    when 'REQUEST_POSITION_CLOSE' then
      if not private.json_has_exact_keys(
          payload,
          array['positionId', 'expectedPositionVersion', 'reason']
        )
        or pg_catalog.jsonb_typeof(payload -> 'positionId') <> 'string'
        or not private.is_uuid(payload ->> 'positionId')
        or not private.json_positive_integer(payload, 'expectedPositionVersion')
        or pg_catalog.jsonb_typeof(payload -> 'reason') <> 'string'
        or not private.is_identifier(payload ->> 'reason')
        or target_resource_type <> 'position'
        or target_resource_id is null
        or target_resource_id <> (payload ->> 'positionId')::uuid
        or expected_resource_version <> (payload ->> 'expectedPositionVersion')::integer then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;

    when 'REQUEST_STOP_LOSS_CHANGE' then
      if not private.json_has_exact_keys(
          payload,
          array['positionId', 'expectedPositionVersion', 'newStopLoss']
        )
        or pg_catalog.jsonb_typeof(payload -> 'positionId') <> 'string'
        or not private.is_uuid(payload ->> 'positionId')
        or not private.json_positive_integer(payload, 'expectedPositionVersion')
        or not private.json_positive_number(payload, 'newStopLoss')
        or target_resource_type <> 'position'
        or target_resource_id is null
        or target_resource_id <> (payload ->> 'positionId')::uuid
        or expected_resource_version <> (payload ->> 'expectedPositionVersion')::integer then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;

    when 'REQUEST_TAKE_PROFIT_CHANGE' then
      if not private.json_has_exact_keys(
          payload,
          array['positionId', 'expectedPositionVersion', 'newTakeProfit']
        )
        or pg_catalog.jsonb_typeof(payload -> 'positionId') <> 'string'
        or not private.is_uuid(payload ->> 'positionId')
        or not private.json_positive_integer(payload, 'expectedPositionVersion')
        or not private.json_positive_number(payload, 'newTakeProfit')
        or target_resource_type <> 'position'
        or target_resource_id is null
        or target_resource_id <> (payload ->> 'positionId')::uuid
        or expected_resource_version <> (payload ->> 'expectedPositionVersion')::integer then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;

    when 'REQUEST_RISK_POLICY_CHANGE' then
      if not private.json_has_exact_keys(
          payload,
          array['ruleKey', 'newValue', 'reason']
        )
        or pg_catalog.jsonb_typeof(payload -> 'ruleKey') <> 'string'
        or not private.is_identifier(payload ->> 'ruleKey')
        or not private.json_number(payload, 'newValue')
        or pg_catalog.jsonb_typeof(payload -> 'reason') <> 'string'
        or not private.is_identifier(payload ->> 'reason')
        or not private.risk_rule_value_is_safe(
          payload ->> 'ruleKey',
          (payload ->> 'newValue')::numeric
        )
        or target_resource_type <> 'risk_policy'
        or target_resource_id is null
        or expected_resource_version is null
        or expected_resource_version <= 0 then
        raise exception using errcode = '22023', message = 'AURUM_INVALID_COMMAND_PAYLOAD';
      end if;
  end case;
end
$function$;

create or replace function private.validate_system_command_row()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  perform private.assert_system_command_payload(
    new.type,
    new.payload,
    new.target_resource_type,
    new.target_resource_id,
    new.expected_resource_version
  );
  return new;
end
$function$;

create trigger system_commands_validate_payload
before insert or update of type, payload, target_resource_type, target_resource_id, expected_resource_version
on public.system_commands
for each row execute function private.validate_system_command_row();

create or replace function private.append_command_event(
  command_id uuid,
  event_type public.command_event_type,
  from_status public.system_command_status,
  to_status public.system_command_status,
  event_actor_type public.actor_type,
  event_actor_id text,
  result_code text default null,
  message text default null,
  metadata jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $function$
declare
  command_owner uuid;
  next_sequence integer;
begin
  if not private.is_identifier(event_actor_id) then
    raise exception using errcode = '22023', message = 'AURUM_INVALID_ACTOR';
  end if;

  update public.system_commands
  set event_sequence = event_sequence + 1,
      updated_at = pg_catalog.clock_timestamp()
  where id = command_id
  returning owner_id, event_sequence into command_owner, next_sequence;

  if command_owner is null then
    raise exception using errcode = 'P0002', message = 'AURUM_COMMAND_NOT_FOUND';
  end if;

  insert into public.system_command_events (
    owner_id,
    system_command_id,
    sequence,
    event_type,
    from_status,
    to_status,
    actor_type,
    actor_id,
    result_code,
    message,
    metadata
  ) values (
    command_owner,
    command_id,
    next_sequence,
    event_type,
    from_status,
    to_status,
    event_actor_type,
    event_actor_id,
    result_code,
    message,
    metadata
  );
end
$function$;

create or replace function private.append_audit(
  audit_owner_id uuid,
  audit_actor_type public.actor_type,
  audit_actor_id text,
  audit_action text,
  audit_target_type text,
  audit_target_id uuid,
  audit_request_id uuid,
  audit_old_version integer default null,
  audit_new_version integer default null,
  audit_metadata jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if not private.is_identifier(audit_actor_id)
    or not private.is_identifier(audit_action)
    or not private.is_identifier(audit_target_type) then
    raise exception using errcode = '22023', message = 'AURUM_INVALID_AUDIT_RECORD';
  end if;

  insert into public.audit_logs (
    owner_id,
    actor_type,
    actor_id,
    action,
    target_type,
    target_id,
    request_id,
    old_version,
    new_version,
    metadata
  ) values (
    audit_owner_id,
    audit_actor_type,
    audit_actor_id,
    audit_action,
    audit_target_type,
    audit_target_id,
    audit_request_id,
    audit_old_version,
    audit_new_version,
    audit_metadata
  );
end
$function$;

create or replace function private.preflight_user_command(
  command_type public.system_command_type,
  command_payload jsonb,
  target_type text,
  target_id uuid,
  expected_version integer,
  idempotency_key text,
  command_expires_at timestamptz
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.session_user_id();
  requested_time timestamptz := pg_catalog.clock_timestamp();
  existing public.system_commands%rowtype;
begin
  if v_owner_id is null then
    return (false, null, false, null, 'UNAUTHENTICATED')::public.command_action_result;
  end if;
  if not private.is_identifier($6) then
    return (false, null, false, null, 'INVALID_IDEMPOTENCY_KEY')::public.command_action_result;
  end if;

  perform private.assert_system_command_payload($1, $2, $3, $4, $5);

  -- Serialize the lookup with every other caller using this owner/key. RPCs
  -- with mutable resource gates acquire their resource lock before entering
  -- this helper, so a concurrent original request becomes visible before an
  -- exact replay is compared with expiry, status, or version state.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      v_owner_id::text || ':command-key:' || pg_catalog.btrim($6),
      0
    )
  );

  select * into existing
  from public.system_commands as command_row
  where command_row.owner_id = v_owner_id
    and command_row.idempotency_key = pg_catalog.btrim($6);

  if found then
    if existing.type = $1
      and existing.payload = $2
      and existing.target_resource_type is not distinct from $3
      and existing.target_resource_id is not distinct from $4
      and existing.expected_resource_version is not distinct from $5 then
      return (
        true,
        existing.id,
        false,
        existing.status,
        'IDEMPOTENT_REPLAY'
      )::public.command_action_result;
    end if;

    return (
      false,
      existing.id,
      false,
      existing.status,
      'IDEMPOTENCY_CONFLICT'
    )::public.command_action_result;
  end if;

  if $7 is null
    or $7 <= requested_time
    or $7 > requested_time + interval '5 minutes' then
    return (false, null, false, null, 'INVALID_COMMAND_EXPIRY')::public.command_action_result;
  end if;

  return null;
end
$function$;

create or replace function private.enqueue_user_command(
  command_type public.system_command_type,
  command_payload jsonb,
  target_type text,
  target_id uuid,
  expected_version integer,
  idempotency_key text,
  command_expires_at timestamptz
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.session_user_id();
  requested_time timestamptz := pg_catalog.clock_timestamp();
  inserted_id uuid;
  inserted_status public.system_command_status;
  existing public.system_commands%rowtype;
  preflight_result public.command_action_result;
  audit_action text;
begin
  preflight_result := private.preflight_user_command($1, $2, $3, $4, $5, $6, $7);
  if preflight_result.result_code is not null then
    return preflight_result;
  end if;

  insert into public.system_commands (
    owner_id,
    type,
    payload,
    status,
    requested_by,
    requested_at,
    target_resource_type,
    target_resource_id,
    expected_resource_version,
    idempotency_key,
    priority,
    expires_at
  ) values (
    v_owner_id,
    command_type,
    command_payload,
    'pending',
    v_owner_id,
    requested_time,
    target_type,
    target_id,
    expected_version,
    pg_catalog.btrim($6),
    case when command_type = 'ACTIVATE_EMERGENCY_STOP' then 100 else 0 end,
    command_expires_at
  )
  on conflict on constraint system_commands_owner_id_idempotency_key_key do nothing
  returning id, status into inserted_id, inserted_status;

  if inserted_id is null then
    select * into existing
    from public.system_commands as command
    where command.owner_id = v_owner_id
      and command.idempotency_key = pg_catalog.btrim($6);

    if existing.type = command_type
      and existing.payload = command_payload
      and existing.target_resource_type is not distinct from target_type
      and existing.target_resource_id is not distinct from target_id
      and existing.expected_resource_version is not distinct from expected_version then
      return (
        true,
        existing.id,
        false,
        existing.status,
        'IDEMPOTENT_REPLAY'
      )::public.command_action_result;
    end if;

    return (
      false,
      existing.id,
      false,
      existing.status,
      'IDEMPOTENCY_CONFLICT'
    )::public.command_action_result;
  end if;

  audit_action := case command_type
    when 'APPROVE_PROPOSAL' then 'proposal_approval_requested'
    when 'REJECT_PROPOSAL' then 'proposal_rejection_requested'
    when 'PAUSE_NEW_TRADES' then 'pause_requested'
    when 'RESUME_SYSTEM' then 'resume_requested'
    when 'ACTIVATE_EMERGENCY_STOP' then 'emergency_stop_requested'
    when 'REQUEST_POSITION_CLOSE' then 'position_close_requested'
    when 'REQUEST_STOP_LOSS_CHANGE' then 'stop_loss_change_requested'
    when 'REQUEST_TAKE_PROFIT_CHANGE' then 'take_profit_change_requested'
    when 'REQUEST_RISK_POLICY_CHANGE' then 'risk_policy_change_requested'
  end;

  perform private.append_command_event(
    inserted_id,
    'created',
    null,
    'pending',
    'user',
    v_owner_id::text,
    'CONTROL_PLANE_RECORDED',
    'Durable command recorded; no Worker or broker outcome is implied.',
    pg_catalog.jsonb_build_object('commandType', command_type::text)
  );
  perform private.append_audit(
    v_owner_id,
    'user',
    v_owner_id::text,
    audit_action,
    coalesce(target_type, 'system'),
    target_id,
    inserted_id,
    expected_version,
    null,
    pg_catalog.jsonb_build_object(
      'commandType', command_type::text,
      'controlPlaneOnly', true
    )
  );

  return (true, inserted_id, true, inserted_status, 'CREATED')::public.command_action_result;
end
$function$;

alter function private.is_uuid(text) owner to aurum_function_owner;
alter function private.is_identifier(text) owner to aurum_function_owner;
alter function private.json_positive_integer(jsonb, text) owner to aurum_function_owner;
alter function private.json_positive_number(jsonb, text) owner to aurum_function_owner;
alter function private.json_number(jsonb, text) owner to aurum_function_owner;
alter function private.json_has_exact_keys(jsonb, text[], text[]) owner to aurum_function_owner;
alter function private.risk_rule_value_is_safe(text, numeric) owner to aurum_function_owner;
alter function private.assert_system_command_payload(
  public.system_command_type, jsonb, text, uuid, integer
) owner to aurum_function_owner;
alter function private.validate_system_command_row() owner to aurum_function_owner;
alter function private.append_command_event(
  uuid, public.command_event_type, public.system_command_status,
  public.system_command_status, public.actor_type, text, text, text, jsonb
) owner to aurum_function_owner;
alter function private.append_audit(
  uuid, public.actor_type, text, text, text, uuid, uuid, integer, integer, jsonb
) owner to aurum_function_owner;
alter function private.preflight_user_command(
  public.system_command_type, jsonb, text, uuid, integer, text, timestamptz
) owner to aurum_function_owner;
alter function private.enqueue_user_command(
  public.system_command_type, jsonb, text, uuid, integer, text, timestamptz
) owner to aurum_function_owner;

revoke all on function private.is_uuid(text) from public, anon, authenticated, aurum_worker;
revoke all on function private.is_identifier(text) from public, anon, authenticated, aurum_worker;
revoke all on function private.json_positive_integer(jsonb, text) from public, anon, authenticated, aurum_worker;
revoke all on function private.json_positive_number(jsonb, text) from public, anon, authenticated, aurum_worker;
revoke all on function private.json_number(jsonb, text) from public, anon, authenticated, aurum_worker;
revoke all on function private.json_has_exact_keys(jsonb, text[], text[]) from public, anon, authenticated, aurum_worker;
revoke all on function private.risk_rule_value_is_safe(text, numeric) from public, anon, authenticated, aurum_worker;
revoke all on function private.assert_system_command_payload(
  public.system_command_type, jsonb, text, uuid, integer
) from public, anon, authenticated, aurum_worker;
revoke all on function private.validate_system_command_row() from public, anon, authenticated, aurum_worker;
revoke all on function private.append_command_event(
  uuid, public.command_event_type, public.system_command_status,
  public.system_command_status, public.actor_type, text, text, text, jsonb
) from public, anon, authenticated, aurum_worker;
revoke all on function private.append_audit(
  uuid, public.actor_type, text, text, text, uuid, uuid, integer, integer, jsonb
) from public, anon, authenticated, aurum_worker;
revoke all on function private.preflight_user_command(
  public.system_command_type, jsonb, text, uuid, integer, text, timestamptz
) from public, anon, authenticated, aurum_worker;
revoke all on function private.enqueue_user_command(
  public.system_command_type, jsonb, text, uuid, integer, text, timestamptz
) from public, anon, authenticated, aurum_worker;

create or replace function public.request_proposal_approval(
  proposal_id uuid,
  proposal_version integer,
  idempotency_key text,
  approval_session_id uuid default null,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.session_user_id();
  proposal public.trade_proposals%rowtype;
  existing_decision public.trade_decisions%rowtype;
  action_result public.command_action_result;
  replay_result public.command_action_result;
  payload jsonb;
  effective_expires_at timestamptz;
begin
  if v_owner_id is null then
    return (false, null, false, null, 'UNAUTHENTICATED')::public.command_action_result;
  end if;
  if proposal_version is null or proposal_version <= 0 then
    return (false, null, false, null, 'INVALID_PROPOSAL_VERSION')::public.command_action_result;
  end if;
  if proposal_id is null then
    return (false, null, false, null, 'PROPOSAL_NOT_FOUND')::public.command_action_result;
  end if;

  payload := pg_catalog.jsonb_build_object(
    'proposalId', proposal_id::text,
    'proposalVersion', proposal_version
  );
  if approval_session_id is not null then
    payload := payload || pg_catalog.jsonb_build_object(
      'approvalSessionId', approval_session_id::text
    );
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_owner_id::text || ':' || proposal_id::text, 0)
  );
  effective_expires_at := coalesce(
    command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds'
  );
  replay_result := private.preflight_user_command(
    'APPROVE_PROPOSAL', payload, 'trade_proposal', proposal_id,
    proposal_version, idempotency_key, effective_expires_at
  );
  if replay_result.result_code is not null then
    return replay_result;
  end if;

  select * into proposal
  from public.trade_proposals as proposal_row
  where proposal_row.id = proposal_id and proposal_row.owner_id = v_owner_id;
  if not found then
    return (false, null, false, null, 'PROPOSAL_NOT_FOUND')::public.command_action_result;
  end if;
  if proposal.proposal_version <> proposal_version then
    return (false, null, false, null, 'STALE_PROPOSAL_VERSION')::public.command_action_result;
  end if;
  if proposal.expires_at <= pg_catalog.clock_timestamp() then
    return (false, null, false, null, 'PROPOSAL_EXPIRED')::public.command_action_result;
  end if;
  if proposal.status not in ('validated', 'pending_approval') then
    return (false, null, false, null, 'PROPOSAL_NOT_ACTIONABLE')::public.command_action_result;
  end if;

  select * into existing_decision
  from public.trade_decisions as decision_row
  where decision_row.trade_proposal_id = proposal_id
    and decision_row.owner_id = v_owner_id
    and decision_row.proposal_version = $2;
  if found then
    if existing_decision.decision = 'approve'
      and exists (
        select 1 from public.system_commands as command_row
        where command_row.id = existing_decision.command_id
          and command_row.owner_id = v_owner_id
          and command_row.idempotency_key = pg_catalog.btrim($3)
      ) then
      return private.enqueue_user_command(
        'APPROVE_PROPOSAL', payload, 'trade_proposal', proposal_id,
        proposal_version, idempotency_key,
        effective_expires_at
      );
    end if;
    return (false, existing_decision.command_id, false, null, 'PROPOSAL_ALREADY_DECIDED')::public.command_action_result;
  end if;

  action_result := private.enqueue_user_command(
    'APPROVE_PROPOSAL',
    payload,
    'trade_proposal',
    proposal_id,
    proposal_version,
    idempotency_key,
    effective_expires_at
  );

  if action_result.accepted and action_result.created then
    insert into public.trade_decisions (
      owner_id, trade_proposal_id, proposal_version, decision,
      reason, command_id, decided_by
    ) values (
      v_owner_id, proposal_id, proposal_version, 'approve',
      null, action_result.command_id, v_owner_id
    );
  end if;
  return action_result;
end
$function$;

create or replace function public.request_proposal_rejection(
  proposal_id uuid,
  proposal_version integer,
  reason text,
  idempotency_key text,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.session_user_id();
  proposal public.trade_proposals%rowtype;
  existing_decision public.trade_decisions%rowtype;
  action_result public.command_action_result;
  replay_result public.command_action_result;
  payload jsonb;
  effective_expires_at timestamptz;
begin
  if v_owner_id is null then
    return (false, null, false, null, 'UNAUTHENTICATED')::public.command_action_result;
  end if;
  if proposal_version is null or proposal_version <= 0 then
    return (false, null, false, null, 'INVALID_PROPOSAL_VERSION')::public.command_action_result;
  end if;
  if not private.is_identifier(reason) then
    return (false, null, false, null, 'INVALID_REASON')::public.command_action_result;
  end if;
  if proposal_id is null then
    return (false, null, false, null, 'PROPOSAL_NOT_FOUND')::public.command_action_result;
  end if;

  payload := pg_catalog.jsonb_build_object(
    'proposalId', proposal_id::text,
    'proposalVersion', proposal_version,
    'reason', pg_catalog.btrim(reason)
  );
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_owner_id::text || ':' || proposal_id::text, 0)
  );
  effective_expires_at := coalesce(
    command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds'
  );
  replay_result := private.preflight_user_command(
    'REJECT_PROPOSAL', payload, 'trade_proposal', proposal_id,
    proposal_version, idempotency_key, effective_expires_at
  );
  if replay_result.result_code is not null then
    return replay_result;
  end if;

  select * into proposal
  from public.trade_proposals as proposal_row
  where proposal_row.id = proposal_id and proposal_row.owner_id = v_owner_id;
  if not found then
    return (false, null, false, null, 'PROPOSAL_NOT_FOUND')::public.command_action_result;
  end if;
  if proposal.proposal_version <> proposal_version then
    return (false, null, false, null, 'STALE_PROPOSAL_VERSION')::public.command_action_result;
  end if;
  if proposal.expires_at <= pg_catalog.clock_timestamp() then
    return (false, null, false, null, 'PROPOSAL_EXPIRED')::public.command_action_result;
  end if;
  if proposal.status not in ('candidate', 'validated', 'pending_approval') then
    return (false, null, false, null, 'PROPOSAL_NOT_ACTIONABLE')::public.command_action_result;
  end if;

  select * into existing_decision
  from public.trade_decisions as decision_row
  where decision_row.trade_proposal_id = proposal_id
    and decision_row.owner_id = v_owner_id
    and decision_row.proposal_version = $2;
  if found then
    if existing_decision.decision = 'reject'
      and exists (
        select 1 from public.system_commands as command_row
        where command_row.id = existing_decision.command_id
          and command_row.owner_id = v_owner_id
          and command_row.idempotency_key = pg_catalog.btrim($4)
      ) then
      return private.enqueue_user_command(
        'REJECT_PROPOSAL', payload, 'trade_proposal', proposal_id,
        proposal_version, idempotency_key,
        effective_expires_at
      );
    end if;
    return (false, existing_decision.command_id, false, null, 'PROPOSAL_ALREADY_DECIDED')::public.command_action_result;
  end if;

  action_result := private.enqueue_user_command(
    'REJECT_PROPOSAL',
    payload,
    'trade_proposal',
    proposal_id,
    proposal_version,
    idempotency_key,
    effective_expires_at
  );
  if action_result.accepted and action_result.created then
    insert into public.trade_decisions (
      owner_id, trade_proposal_id, proposal_version, decision,
      reason, command_id, decided_by
    ) values (
      v_owner_id, proposal_id, proposal_version, 'reject',
      pg_catalog.btrim(reason), action_result.command_id, v_owner_id
    );
  end if;
  return action_result;
end
$function$;

create or replace function public.request_pause_new_trades(
  idempotency_key text,
  reason text default null,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare payload jsonb := '{}'::jsonb;
begin
  if reason is not null then
    if not private.is_identifier(reason) then
      return (false, null, false, null, 'INVALID_REASON')::public.command_action_result;
    end if;
    payload := pg_catalog.jsonb_build_object('reason', pg_catalog.btrim(reason));
  end if;
  return private.enqueue_user_command(
    'PAUSE_NEW_TRADES', payload, null, null, null, idempotency_key,
    coalesce(command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds')
  );
end
$function$;

create or replace function public.request_resume_system(
  checklist_acknowledgement_id uuid,
  idempotency_key text,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if checklist_acknowledgement_id is null then
    return (false, null, false, null, 'INVALID_CHECKLIST_ACKNOWLEDGEMENT')::public.command_action_result;
  end if;
  return private.enqueue_user_command(
    'RESUME_SYSTEM',
    pg_catalog.jsonb_build_object(
      'checklistAcknowledgementId', checklist_acknowledgement_id::text
    ),
    null, null, null, idempotency_key,
    coalesce(command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds')
  );
end
$function$;

create or replace function public.request_emergency_stop(
  reason text,
  idempotency_key text,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if not private.is_identifier(reason) then
    return (false, null, false, null, 'INVALID_REASON')::public.command_action_result;
  end if;
  return private.enqueue_user_command(
    'ACTIVATE_EMERGENCY_STOP',
    pg_catalog.jsonb_build_object('reason', pg_catalog.btrim(reason)),
    null, null, null, idempotency_key,
    coalesce(command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds')
  );
end
$function$;

create or replace function public.request_position_close(
  position_id uuid,
  expected_position_version integer,
  reason text,
  idempotency_key text,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.session_user_id();
  position public.positions%rowtype;
  replay_result public.command_action_result;
  payload jsonb;
  effective_expires_at timestamptz;
begin
  if v_owner_id is null then
    return (false, null, false, null, 'UNAUTHENTICATED')::public.command_action_result;
  end if;
  if expected_position_version is null or expected_position_version <= 0 then
    return (false, null, false, null, 'INVALID_POSITION_VERSION')::public.command_action_result;
  end if;
  if not private.is_identifier(reason) then
    return (false, null, false, null, 'INVALID_REASON')::public.command_action_result;
  end if;
  if position_id is null then
    return (false, null, false, null, 'POSITION_NOT_FOUND')::public.command_action_result;
  end if;

  payload := pg_catalog.jsonb_build_object(
    'positionId', position_id::text,
    'expectedPositionVersion', expected_position_version,
    'reason', pg_catalog.btrim(reason)
  );
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_owner_id::text || ':' || position_id::text, 0)
  );
  effective_expires_at := coalesce(
    command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds'
  );
  replay_result := private.preflight_user_command(
    'REQUEST_POSITION_CLOSE', payload, 'position', position_id,
    expected_position_version, idempotency_key, effective_expires_at
  );
  if replay_result.result_code is not null then
    return replay_result;
  end if;

  select * into position from public.positions as position_row
  where position_row.id = position_id and position_row.owner_id = v_owner_id;
  if not found then
    return (false, null, false, null, 'POSITION_NOT_FOUND')::public.command_action_result;
  end if;
  if position.position_version <> expected_position_version then
    return (false, null, false, null, 'STALE_POSITION_VERSION')::public.command_action_result;
  end if;
  if position.status <> 'open' then
    return (false, null, false, null, 'POSITION_NOT_ACTIONABLE')::public.command_action_result;
  end if;
  return private.enqueue_user_command(
    'REQUEST_POSITION_CLOSE',
    payload,
    'position', position_id, expected_position_version, idempotency_key,
    effective_expires_at
  );
end
$function$;

create or replace function public.request_stop_loss_change(
  position_id uuid,
  expected_position_version integer,
  new_stop_loss numeric,
  idempotency_key text,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.session_user_id();
  position public.positions%rowtype;
  replay_result public.command_action_result;
  payload jsonb;
  effective_expires_at timestamptz;
begin
  if v_owner_id is null then
    return (false, null, false, null, 'UNAUTHENTICATED')::public.command_action_result;
  end if;
  if expected_position_version is null or expected_position_version <= 0 then
    return (false, null, false, null, 'INVALID_POSITION_VERSION')::public.command_action_result;
  end if;
  if new_stop_loss is null
    or not private.numeric_is_finite(new_stop_loss)
    or new_stop_loss <= 0 then
    return (false, null, false, null, 'INVALID_STOP_LOSS')::public.command_action_result;
  end if;
  if position_id is null then
    return (false, null, false, null, 'POSITION_NOT_FOUND')::public.command_action_result;
  end if;

  payload := pg_catalog.jsonb_build_object(
    'positionId', position_id::text,
    'expectedPositionVersion', expected_position_version,
    'newStopLoss', new_stop_loss
  );
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_owner_id::text || ':' || position_id::text, 0)
  );
  effective_expires_at := coalesce(
    command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds'
  );
  replay_result := private.preflight_user_command(
    'REQUEST_STOP_LOSS_CHANGE', payload, 'position', position_id,
    expected_position_version, idempotency_key, effective_expires_at
  );
  if replay_result.result_code is not null then
    return replay_result;
  end if;

  select * into position from public.positions as position_row
  where position_row.id = position_id and position_row.owner_id = v_owner_id;
  if not found then
    return (false, null, false, null, 'POSITION_NOT_FOUND')::public.command_action_result;
  end if;
  if position.position_version <> expected_position_version then
    return (false, null, false, null, 'STALE_POSITION_VERSION')::public.command_action_result;
  end if;
  if position.status <> 'open' then
    return (false, null, false, null, 'POSITION_NOT_ACTIONABLE')::public.command_action_result;
  end if;
  return private.enqueue_user_command(
    'REQUEST_STOP_LOSS_CHANGE',
    payload,
    'position', position_id, expected_position_version, idempotency_key,
    effective_expires_at
  );
end
$function$;

create or replace function public.request_take_profit_change(
  position_id uuid,
  expected_position_version integer,
  new_take_profit numeric,
  idempotency_key text,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.session_user_id();
  position public.positions%rowtype;
  replay_result public.command_action_result;
  payload jsonb;
  effective_expires_at timestamptz;
begin
  if v_owner_id is null then
    return (false, null, false, null, 'UNAUTHENTICATED')::public.command_action_result;
  end if;
  if expected_position_version is null or expected_position_version <= 0 then
    return (false, null, false, null, 'INVALID_POSITION_VERSION')::public.command_action_result;
  end if;
  if new_take_profit is null
    or not private.numeric_is_finite(new_take_profit)
    or new_take_profit <= 0 then
    return (false, null, false, null, 'INVALID_TAKE_PROFIT')::public.command_action_result;
  end if;
  if position_id is null then
    return (false, null, false, null, 'POSITION_NOT_FOUND')::public.command_action_result;
  end if;

  payload := pg_catalog.jsonb_build_object(
    'positionId', position_id::text,
    'expectedPositionVersion', expected_position_version,
    'newTakeProfit', new_take_profit
  );
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_owner_id::text || ':' || position_id::text, 0)
  );
  effective_expires_at := coalesce(
    command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds'
  );
  replay_result := private.preflight_user_command(
    'REQUEST_TAKE_PROFIT_CHANGE', payload, 'position', position_id,
    expected_position_version, idempotency_key, effective_expires_at
  );
  if replay_result.result_code is not null then
    return replay_result;
  end if;

  select * into position from public.positions as position_row
  where position_row.id = position_id and position_row.owner_id = v_owner_id;
  if not found then
    return (false, null, false, null, 'POSITION_NOT_FOUND')::public.command_action_result;
  end if;
  if position.position_version <> expected_position_version then
    return (false, null, false, null, 'STALE_POSITION_VERSION')::public.command_action_result;
  end if;
  if position.status <> 'open' then
    return (false, null, false, null, 'POSITION_NOT_ACTIONABLE')::public.command_action_result;
  end if;
  return private.enqueue_user_command(
    'REQUEST_TAKE_PROFIT_CHANGE',
    payload,
    'position', position_id, expected_position_version, idempotency_key,
    effective_expires_at
  );
end
$function$;

create or replace function public.request_risk_policy_change(
  rule_key text,
  new_value numeric,
  reason text,
  expected_policy_version integer,
  idempotency_key text,
  command_expires_at timestamptz default null
)
returns public.command_action_result
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owner_id uuid := private.session_user_id();
  policy public.risk_policies%rowtype;
  active_version public.risk_policy_versions%rowtype;
  action_result public.command_action_result;
  replay_result public.command_action_result;
  payload jsonb;
  effective_expires_at timestamptz;
  next_version integer;
  normalized_key text := pg_catalog.btrim(rule_key);
begin
  if v_owner_id is null then
    return (false, null, false, null, 'UNAUTHENTICATED')::public.command_action_result;
  end if;
  if expected_policy_version is null or expected_policy_version <= 0 then
    return (false, null, false, null, 'INVALID_RISK_POLICY_VERSION')::public.command_action_result;
  end if;
  if not private.is_identifier(reason) then
    return (false, null, false, null, 'INVALID_REASON')::public.command_action_result;
  end if;
  if normalized_key not in (
    'risk_per_trade_pct',
    'daily_loss_limit_pct',
    'weekly_loss_limit_pct',
    'maximum_drawdown_pct',
    'maximum_trades_per_day',
    'minimum_risk_reward',
    'stale_data_max_age_seconds',
    'maximum_spread_points',
    'news_blackout_minutes'
  ) then
    return (false, null, false, null, 'UNSUPPORTED_RISK_RULE')::public.command_action_result;
  end if;
  if new_value is null or not private.risk_rule_value_is_safe(normalized_key, new_value) then
    return (false, null, false, null, 'RISK_RULE_VALUE_OUT_OF_BOUNDS')::public.command_action_result;
  end if;

  payload := pg_catalog.jsonb_build_object(
    'ruleKey', normalized_key,
    'newValue', new_value,
    'reason', pg_catalog.btrim(reason)
  );

  select * into policy
  from public.risk_policies as policy_row
  where policy_row.owner_id = v_owner_id
  order by policy_row.created_at, policy_row.id
  limit 1
  for update;
  if not found then
    return (false, null, false, null, 'RISK_POLICY_NOT_FOUND')::public.command_action_result;
  end if;

  effective_expires_at := coalesce(
    command_expires_at, pg_catalog.clock_timestamp() + interval '30 seconds'
  );
  replay_result := private.preflight_user_command(
    'REQUEST_RISK_POLICY_CHANGE', payload, 'risk_policy', policy.id,
    expected_policy_version, idempotency_key, effective_expires_at
  );
  if replay_result.result_code is not null then
    return replay_result;
  end if;

  if policy.active_version_id is null then
    return (false, null, false, null, 'RISK_POLICY_NOT_FOUND')::public.command_action_result;
  end if;
  if policy.resource_version <> expected_policy_version then
    return (false, null, false, null, 'STALE_RISK_POLICY_VERSION')::public.command_action_result;
  end if;
  select * into active_version
  from public.risk_policy_versions as version_row
  where version_row.id = policy.active_version_id
    and version_row.owner_id = v_owner_id;

  action_result := private.enqueue_user_command(
    'REQUEST_RISK_POLICY_CHANGE',
    payload,
    'risk_policy', policy.id, expected_policy_version, idempotency_key,
    effective_expires_at
  );

  if action_result.accepted and action_result.created then
    select coalesce(pg_catalog.max(version_row.version), 0) + 1
    into next_version
    from public.risk_policy_versions as version_row
    where version_row.risk_policy_id = policy.id
      and version_row.owner_id = v_owner_id;
    insert into public.risk_policy_versions (
      owner_id, risk_policy_id, trading_account_id, version, version_label, source_command_id,
      environment, canonical_symbol, maximum_permitted_volume,
      maximum_open_positions, stop_loss_required, martingale_allowed,
      grid_trading_allowed, averaging_down_allowed,
      loss_based_volume_increase_allowed, risk_per_trade_pct,
      daily_loss_limit_pct, weekly_loss_limit_pct, maximum_drawdown_pct,
      maximum_trades_per_day, minimum_risk_reward,
      stale_data_max_age_seconds, maximum_spread_points,
      spread_warning_points, news_blackout_minutes,
      proposal_expiry_seconds, entry_tolerance_points, minimum_sample_size,
      require_calibrated_model, maximum_slippage_points,
      automatic_retry_on_broker_reject, reason, created_by_type,
      created_by, created_at
    )
    values (
      v_owner_id,
      policy.id,
      policy.trading_account_id,
      next_version,
      policy.policy_key || '-v' || next_version::text,
      action_result.command_id,
      active_version.environment,
      active_version.canonical_symbol,
      active_version.maximum_permitted_volume,
      active_version.maximum_open_positions,
      active_version.stop_loss_required,
      active_version.martingale_allowed,
      active_version.grid_trading_allowed,
      active_version.averaging_down_allowed,
      active_version.loss_based_volume_increase_allowed,
      case when normalized_key = 'risk_per_trade_pct' then new_value else active_version.risk_per_trade_pct end,
      case when normalized_key = 'daily_loss_limit_pct' then new_value else active_version.daily_loss_limit_pct end,
      case when normalized_key = 'weekly_loss_limit_pct' then new_value else active_version.weekly_loss_limit_pct end,
      case when normalized_key = 'maximum_drawdown_pct' then new_value else active_version.maximum_drawdown_pct end,
      case when normalized_key = 'maximum_trades_per_day' then new_value::smallint else active_version.maximum_trades_per_day end,
      case when normalized_key = 'minimum_risk_reward' then new_value else active_version.minimum_risk_reward end,
      case when normalized_key = 'stale_data_max_age_seconds' then new_value::integer else active_version.stale_data_max_age_seconds end,
      case when normalized_key = 'maximum_spread_points' then new_value else active_version.maximum_spread_points end,
      case when normalized_key = 'maximum_spread_points'
        then least(active_version.spread_warning_points, new_value)
        else active_version.spread_warning_points end,
      case when normalized_key = 'news_blackout_minutes' then new_value::integer else active_version.news_blackout_minutes end,
      active_version.proposal_expiry_seconds,
      active_version.entry_tolerance_points,
      active_version.minimum_sample_size,
      active_version.require_calibrated_model,
      active_version.maximum_slippage_points,
      active_version.automatic_retry_on_broker_reject,
      pg_catalog.btrim(reason),
      'user',
      v_owner_id::text,
      pg_catalog.clock_timestamp()
    );

    perform private.append_audit(
      v_owner_id, 'user', v_owner_id::text,
      'risk_policy_version_created', 'risk_policy', policy.id,
      action_result.command_id, active_version.version, next_version,
      pg_catalog.jsonb_build_object(
        'ruleKey', normalized_key,
        'activation', 'pending_worker_acknowledgement',
        'newsBlackoutSymmetric', normalized_key = 'news_blackout_minutes'
      )
    );
  end if;
  return action_result;
end
$function$;

alter function public.request_proposal_approval(uuid, integer, text, uuid, timestamptz) owner to aurum_function_owner;
alter function public.request_proposal_rejection(uuid, integer, text, text, timestamptz) owner to aurum_function_owner;
alter function public.request_pause_new_trades(text, text, timestamptz) owner to aurum_function_owner;
alter function public.request_resume_system(uuid, text, timestamptz) owner to aurum_function_owner;
alter function public.request_emergency_stop(text, text, timestamptz) owner to aurum_function_owner;
alter function public.request_position_close(uuid, integer, text, text, timestamptz) owner to aurum_function_owner;
alter function public.request_stop_loss_change(uuid, integer, numeric, text, timestamptz) owner to aurum_function_owner;
alter function public.request_take_profit_change(uuid, integer, numeric, text, timestamptz) owner to aurum_function_owner;
alter function public.request_risk_policy_change(text, numeric, text, integer, text, timestamptz) owner to aurum_function_owner;

revoke all on function public.request_proposal_approval(uuid, integer, text, uuid, timestamptz) from public, anon, aurum_worker;
revoke all on function public.request_proposal_rejection(uuid, integer, text, text, timestamptz) from public, anon, aurum_worker;
revoke all on function public.request_pause_new_trades(text, text, timestamptz) from public, anon, aurum_worker;
revoke all on function public.request_resume_system(uuid, text, timestamptz) from public, anon, aurum_worker;
revoke all on function public.request_emergency_stop(text, text, timestamptz) from public, anon, aurum_worker;
revoke all on function public.request_position_close(uuid, integer, text, text, timestamptz) from public, anon, aurum_worker;
revoke all on function public.request_stop_loss_change(uuid, integer, numeric, text, timestamptz) from public, anon, aurum_worker;
revoke all on function public.request_take_profit_change(uuid, integer, numeric, text, timestamptz) from public, anon, aurum_worker;
revoke all on function public.request_risk_policy_change(text, numeric, text, integer, text, timestamptz) from public, anon, aurum_worker;

grant execute on function public.request_proposal_approval(uuid, integer, text, uuid, timestamptz) to authenticated;
grant execute on function public.request_proposal_rejection(uuid, integer, text, text, timestamptz) to authenticated;
grant execute on function public.request_pause_new_trades(text, text, timestamptz) to authenticated;
grant execute on function public.request_resume_system(uuid, text, timestamptz) to authenticated;
grant execute on function public.request_emergency_stop(text, text, timestamptz) to authenticated;
grant execute on function public.request_position_close(uuid, integer, text, text, timestamptz) to authenticated;
grant execute on function public.request_stop_loss_change(uuid, integer, numeric, text, timestamptz) to authenticated;
grant execute on function public.request_take_profit_change(uuid, integer, numeric, text, timestamptz) to authenticated;
grant execute on function public.request_risk_policy_change(text, numeric, text, integer, text, timestamptz) to authenticated;

-- request_emergency_stop records CONTROL_PLANE_RECORDED only; it never claims
-- Worker acknowledgement or broker state. request_position_close records only
-- a version-bound intent and never mutates public.positions or calls MT5.
