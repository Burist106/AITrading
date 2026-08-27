begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(45);

select lives_ok(
  $$insert into public.trading_accounts (
      owner_id, broker_account_reference, broker_server
    ) values (
      '00000000-0000-4000-8000-000000000201', 'accepted-demo', 'fixture'
    )$$,
  'a conservative Demo account is accepted'
);

select is(
  (select canonical_symbol from public.broker_symbols
   where id = '00000000-0000-4000-8000-000000000311'),
  'XAUUSD',
  'the canonical XAUUSD asset is accepted'
);

select throws_ok(
  $$insert into public.trading_accounts (
      owner_id, environment, account_type, broker_account_reference, broker_server
    ) values (
      '00000000-0000-4000-8000-000000000201', 'LIVE', 'demo',
      'bad-live', 'fixture'
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.trading_accounts (
      owner_id, broker_account_reference, broker_server, maximum_permitted_volume
    ) values (
      '00000000-0000-4000-8000-000000000201', 'above-volume', 'fixture', 0.02
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.market_snapshots (
      owner_id, trading_account_id, canonical_symbol, bid, ask, spread_points,
      session, regime, atr, freshness, age_ms, transport, captured_at
    ) values (
      '00000000-0000-4000-8000-000000000201',
      '00000000-0000-4000-8000-000000000301', 'XAGUSD', 30, 30.1, 1,
      'asia', 'range', 1, 'live', 1, 'database_fallback', clock_timestamp()
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.trading_accounts (
      owner_id, account_type, broker_account_reference, broker_server
    ) values (
      '00000000-0000-4000-8000-000000000201', 'real', 'bad-real', 'fixture'
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.trading_accounts (
      owner_id, broker_account_reference, broker_server, maximum_permitted_volume
    ) values (
      '00000000-0000-4000-8000-000000000201', 'bad-volume', 'fixture', 0.005
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.trading_accounts (
      owner_id, broker_account_reference, broker_server, maximum_open_positions
    ) values (
      '00000000-0000-4000-8000-000000000201', 'bad-positions', 'fixture', 2
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.trading_accounts (
      owner_id, broker_account_reference, broker_server, stop_loss_required
    ) values (
      '00000000-0000-4000-8000-000000000201', 'bad-stop', 'fixture', false
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.risk_policy_versions
    select (pg_catalog.jsonb_populate_record(
      null::public.risk_policy_versions,
      pg_catalog.to_jsonb(version_row) || pg_catalog.jsonb_build_object(
        'id', '00000000-0000-4000-8000-000000009001',
        'version', 9001,
        'version_label', 'invalid-volume',
        'source_command_id', null,
        'maximum_permitted_volume', 0.005
      )
    )).* from public.risk_policy_versions as version_row
    where version_row.id = '00000000-0000-4000-8000-000000000332'$$,
  '23514'
);

select throws_ok(
  $$insert into public.risk_policy_versions
    select (pg_catalog.jsonb_populate_record(
      null::public.risk_policy_versions,
      pg_catalog.to_jsonb(version_row) || pg_catalog.jsonb_build_object(
        'id', '00000000-0000-4000-8000-000000009003',
        'version', 9003,
        'version_label', 'invalid-calibrated-model',
        'source_command_id', null,
        'require_calibrated_model', true
      )
    )).* from public.risk_policy_versions as version_row
    where version_row.id = '00000000-0000-4000-8000-000000000332'$$,
  '23514',
  null,
  'Milestone 1 risk policy versions cannot require a calibrated model'
);

select throws_ok(
  $$insert into public.risk_policy_versions
    select (pg_catalog.jsonb_populate_record(
      null::public.risk_policy_versions,
      pg_catalog.to_jsonb(version_row) || pg_catalog.jsonb_build_object(
        'id', '00000000-0000-4000-8000-000000009002',
        'version', 9002,
        'version_label', 'invalid-martingale',
        'source_command_id', null,
        'martingale_allowed', true
      )
    )).* from public.risk_policy_versions as version_row
    where version_row.id = '00000000-0000-4000-8000-000000000332'$$,
  '23514'
);

select is(
  (select maximum_volume from public.broker_symbols
   where id = '00000000-0000-4000-8000-000000000311'),
  100.0000::numeric,
  'broker maximum volume remains an immutable broker fact, not the Aurum cap'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, status, requested_by, idempotency_key,
      claimed_at, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
      'claimed', '00000000-0000-4000-8000-000000000201',
      'invalid-claim-quartet', clock_timestamp(), clock_timestamp() + interval '30 seconds'
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, requested_at,
      idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
      '00000000-0000-4000-8000-000000000201', clock_timestamp(),
      'invalid-command-expiry', clock_timestamp() - interval '1 second'
    )$$,
  '23514'
);

select throws_ok(
  $$select 'not_a_status'::public.system_command_status$$,
  '22P02'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, status, requested_by, idempotency_key,
      claimed_at, claimed_by, lease_token, lease_expires_at,
      completed_at, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
      'succeeded', '00000000-0000-4000-8000-000000000201',
      'invalid-terminal-quartet', clock_timestamp(), 'worker-fixture',
      '00000000-0000-4000-8000-000000009101', clock_timestamp() + interval '20 seconds',
      clock_timestamp(), clock_timestamp() + interval '30 seconds'
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES',
      '{"unexpected":true}', '00000000-0000-4000-8000-000000000201',
      'invalid-extra-key', clock_timestamp() + interval '30 seconds'
    )$$,
  '22023',
  'AURUM_INVALID_COMMAND_PAYLOAD',
  'direct command inserts cannot bypass exact payload validation'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, target_resource_type,
      target_resource_id, expected_resource_version, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'APPROVE_PROPOSAL', '{}',
      '00000000-0000-4000-8000-000000000201', 'trade_proposal',
      '00000000-0000-4000-8000-000000009401', 1, 'invalid-approve-shape',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023', 'AURUM_INVALID_COMMAND_PAYLOAD', 'invalid approval payload is rejected'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, target_resource_type,
      target_resource_id, expected_resource_version, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'REJECT_PROPOSAL', '{}',
      '00000000-0000-4000-8000-000000000201', 'trade_proposal',
      '00000000-0000-4000-8000-000000009402', 1, 'invalid-reject-shape',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023', 'AURUM_INVALID_COMMAND_PAYLOAD', 'invalid rejection payload is rejected'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'RESUME_SYSTEM', '{}',
      '00000000-0000-4000-8000-000000000201', 'invalid-resume-shape',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023', 'AURUM_INVALID_COMMAND_PAYLOAD', 'invalid resume payload is rejected'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, priority, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'ACTIVATE_EMERGENCY_STOP', '{}',
      '00000000-0000-4000-8000-000000000201', 100, 'invalid-emergency-shape',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023', 'AURUM_INVALID_COMMAND_PAYLOAD', 'invalid emergency payload is rejected'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, target_resource_type,
      target_resource_id, expected_resource_version, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'REQUEST_POSITION_CLOSE', '{}',
      '00000000-0000-4000-8000-000000000201', 'position',
      '00000000-0000-4000-8000-000000009403', 1, 'invalid-close-shape',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023', 'AURUM_INVALID_COMMAND_PAYLOAD', 'invalid close payload is rejected'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, target_resource_type,
      target_resource_id, expected_resource_version, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'REQUEST_STOP_LOSS_CHANGE', '{}',
      '00000000-0000-4000-8000-000000000201', 'position',
      '00000000-0000-4000-8000-000000009404', 1, 'invalid-stop-loss-shape',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023', 'AURUM_INVALID_COMMAND_PAYLOAD', 'invalid stop-loss payload is rejected'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, target_resource_type,
      target_resource_id, expected_resource_version, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'REQUEST_TAKE_PROFIT_CHANGE', '{}',
      '00000000-0000-4000-8000-000000000201', 'position',
      '00000000-0000-4000-8000-000000009405', 1, 'invalid-take-profit-shape',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023', 'AURUM_INVALID_COMMAND_PAYLOAD', 'invalid take-profit payload is rejected'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, target_resource_type,
      target_resource_id, expected_resource_version, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'REQUEST_RISK_POLICY_CHANGE',
      '{"ruleKey":"made_up_rule","newValue":1,"reason":"fixture"}',
      '00000000-0000-4000-8000-000000000201', 'risk_policy',
      '00000000-0000-4000-8000-000000000331', 1, 'invalid-risk-key',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023',
  'AURUM_INVALID_COMMAND_PAYLOAD',
  'direct command inserts enforce the canonical nine risk-rule keys'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, target_resource_type,
      target_resource_id, expected_resource_version, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'REQUEST_RISK_POLICY_CHANGE',
      '{"ruleKey":"risk_per_trade_pct","newValue":0.26,"reason":"fixture"}',
      '00000000-0000-4000-8000-000000000201', 'risk_policy',
      '00000000-0000-4000-8000-000000000331', 1, 'invalid-risk-bound',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023',
  'AURUM_INVALID_COMMAND_PAYLOAD',
  'direct command inserts enforce conservative risk-rule bounds'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, target_resource_type,
      target_resource_id, expected_resource_version, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'REQUEST_RISK_POLICY_CHANGE',
      jsonb_build_object('ruleKey', 'minimum_risk_reward', 'newValue', 'NaN'::numeric,
                         'reason', 'fixture'),
      '00000000-0000-4000-8000-000000000201', 'risk_policy',
      '00000000-0000-4000-8000-000000000331', 1, 'invalid-risk-nan',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '22023', 'AURUM_INVALID_COMMAND_PAYLOAD', 'non-finite risk payload is rejected'
);

select throws_ok(
  $$insert into public.broker_symbols
    select (pg_catalog.jsonb_populate_record(
      null::public.broker_symbols,
      pg_catalog.to_jsonb(symbol_row) || pg_catalog.jsonb_build_object(
        'id', '00000000-0000-4000-8000-000000009501',
        'specification_version', 'invalid-nan',
        'contract_size', 'NaN'::numeric
      )
    )).* from public.broker_symbols as symbol_row
    where symbol_row.id = '00000000-0000-4000-8000-000000000311'$$,
  '23514'
);

select throws_ok(
  $$insert into public.audit_logs (
      owner_id, actor_type, actor_id, action, target_type, request_id, metadata
    ) values (
      '00000000-0000-4000-8000-000000000201', 'system', 'fixture',
      'fixture', 'system', '00000000-0000-4000-8000-000000009201',
      '{"accessToken":"must-not-be-stored"}'
    )$$,
  '22023',
  'AURUM_UNSAFE_METADATA_KEY',
  'secret-like metadata keys are rejected at the table boundary'
);

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, created_at, updated_at,
  confirmation_token, email_change, email_change_token_new, recovery_token
) values (
  '00000000-0000-0000-0000-000000000000',
  '00000000-0000-4000-8000-000000009301', 'authenticated', 'authenticated',
  'constraints-owner@aurum.invalid', null, clock_timestamp(), clock_timestamp(),
  '', '', '', ''
);
insert into public.profiles (id, display_name)
values ('00000000-0000-4000-8000-000000009301', 'Constraint Owner');

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
      '00000000-0000-4000-8000-000000009301', 'cross-owner-requester',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, status, requested_by, idempotency_key,
      claimed_at, claimed_by, lease_token, lease_expires_at,
      attempt_count, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
      'claimed', '00000000-0000-4000-8000-000000000201',
      'active-zero-attempt', clock_timestamp(), 'worker-fixture',
      '00000000-0000-4000-8000-000000009613',
      clock_timestamp() + interval '20 seconds', 0,
      clock_timestamp() + interval '30 seconds'
    )$$,
  '23514'
);

insert into public.system_commands (
  id, owner_id, type, payload, requested_by, idempotency_key, expires_at
) values (
  '00000000-0000-4000-8000-000000009613',
  '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
  '00000000-0000-4000-8000-000000000201', 'decision-owner-fixture',
  clock_timestamp() + interval '5 minutes'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, status, requested_by, idempotency_key,
      expires_at, completed_at, result_code
    ) values (
      '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
      'succeeded', '00000000-0000-4000-8000-000000000201',
      'secret-shaped-command-result', clock_timestamp() + interval '30 seconds',
      clock_timestamp(), 'AKIA' || repeat('A', 16)
    )$$,
  '22023',
  'AURUM_INVALID_RESULT_CODE',
  'direct command inserts cannot persist a secret-shaped result code'
);

select throws_ok(
  $$insert into public.system_command_events (
      owner_id, system_command_id, sequence, event_type,
      actor_type, actor_id, result_code
    ) values (
      '00000000-0000-4000-8000-000000000201',
      '00000000-0000-4000-8000-000000009613', 1, 'created',
      'system', 'constraint-fixture',
      'SB_' || 'SECRET_' || repeat('X', 20)
    )$$,
  '22023',
  'AURUM_INVALID_RESULT_CODE',
  'direct event inserts cannot persist a secret-shaped result code'
);

insert into public.trading_accounts (
  id, owner_id, broker_account_reference, broker_server
) values (
  '00000000-0000-4000-8000-000000009601',
  '00000000-0000-4000-8000-000000000201', 'SECOND-SAME-OWNER', 'fixture'
);
insert into public.market_snapshots (
  id, owner_id, trading_account_id, bid, ask, spread_points, session,
  regime, atr, freshness, age_ms, transport, captured_at
) values (
  '00000000-0000-4000-8000-000000009602',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301', 2300, 2300.1, 1,
  'asia', 'range', 1, 'live', 1, 'database_fallback', clock_timestamp()
);
insert into public.feature_snapshots (
  id, owner_id, trading_account_id, market_snapshot_id,
  feature_schema_version, feature_values, captured_at
) values (
  '00000000-0000-4000-8000-000000009603',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301',
  '00000000-0000-4000-8000-000000009602', 'fixture-v1', '{}', clock_timestamp()
);

insert into public.market_snapshots (
  id, owner_id, trading_account_id, bid, ask, spread_points, session,
  regime, atr, freshness, age_ms, transport, captured_at
) values (
  '00000000-0000-4000-8000-000000009606',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301', 2301, 2301.1, 1,
  'asia', 'range', 1, 'live', 1, 'database_fallback', clock_timestamp()
);

select throws_ok(
  $$insert into public.trade_proposals (
      id, owner_id, proposal_version, trading_account_id, broker_symbol_id,
      risk_policy_version_id, account_currency, broker_server, broker_symbol,
      symbol_specification_version, direction, strategy_code, strategy_version,
      eligibility_policy_id, eligibility_policy_version, eligibility_outcome,
      eligibility_evaluated_at, risk_policy_version, entry_price,
      stop_loss_price, take_profit_price, calculated_volume, requested_volume,
      approved_volume, maximum_permitted_volume, risk_amount, risk_pct,
      risk_reward, market_snapshot_id, feature_snapshot_id, decision_trace_id,
      status, created_at, expires_at
    ) values (
      '00000000-0000-4000-8000-000000009604',
      '00000000-0000-4000-8000-000000000201', 1,
      '00000000-0000-4000-8000-000000000301',
      '00000000-0000-4000-8000-000000000311',
      '00000000-0000-4000-8000-000000000332', 'USD',
      'DEMO-FIXTURE-SERVER', 'XAUUSD', 'development-spec-v1', 'BUY',
      'fixture-strategy', 'v1', 'fixture-policy', 'v1', 'ask',
      clock_timestamp(), 'demo-risk-policy-v1', 2300, 2290, 2320,
      0.01, 0.01, 0.01, 0.01, 10, 0.10, 2.0,
      '00000000-0000-4000-8000-000000009602',
      '00000000-0000-4000-8000-000000009603',
      '00000000-0000-4000-8000-000000009605', 'validated',
      '2026-08-26T10:00:00Z', '2026-08-26T10:00:00Z'
    )$$,
  '23514'
);

select lives_ok(
  $$insert into public.trade_proposals (
      id, owner_id, proposal_version, trading_account_id, broker_symbol_id,
      risk_policy_version_id, account_currency, broker_server, broker_symbol,
      symbol_specification_version, direction, strategy_code, strategy_version,
      eligibility_policy_id, eligibility_policy_version, eligibility_outcome,
      eligibility_evaluated_at, risk_policy_version, entry_price,
      stop_loss_price, take_profit_price, calculated_volume, requested_volume,
      approved_volume, maximum_permitted_volume, risk_amount, risk_pct,
      risk_reward, market_snapshot_id, feature_snapshot_id, decision_trace_id,
      status, created_at, expires_at
    ) values (
      '00000000-0000-4000-8000-000000009607',
      '00000000-0000-4000-8000-000000000201', 1,
      '00000000-0000-4000-8000-000000000301',
      '00000000-0000-4000-8000-000000000311',
      '00000000-0000-4000-8000-000000000332', 'USD',
      'DEMO-FIXTURE-SERVER', 'XAUUSD', 'development-spec-v1', 'BUY',
      'fixture-strategy', 'v1', 'fixture-policy', 'v1', 'ask',
      '2026-08-26T10:00:00Z', 'demo-risk-policy-v1', 2300, 2290, 2320,
      0.005, 0.005, 0.005, 0.01, 10, 0.10, 2.0,
      '00000000-0000-4000-8000-000000009602',
      '00000000-0000-4000-8000-000000009603',
      '00000000-0000-4000-8000-000000009608', 'validated',
      '2026-08-26T10:00:00Z', '2026-08-26T10:00:30Z'
    )$$,
  'requested and approved proposal volumes below 0.01 are accepted'
);

select ok(
  exists (
    select 1 from public.trade_proposals
    where id = '00000000-0000-4000-8000-000000009607'
      and requested_volume = 0.005
      and approved_volume = 0.005
      and maximum_permitted_volume = 0.01
  ),
  'sub-cap proposal volumes persist without weakening the exact safety ceiling'
);

select throws_ok(
  $$insert into public.trade_decisions (
      owner_id, trade_proposal_id, proposal_version, decision,
      command_id, decided_by
    ) values (
      '00000000-0000-4000-8000-000000000201',
      '00000000-0000-4000-8000-000000009607', 1, 'approve',
      '00000000-0000-4000-8000-000000009613',
      '00000000-0000-4000-8000-000000009301'
    )$$,
  '23514'
);

select throws_ok(
  $$insert into public.trade_proposals
    select (pg_catalog.jsonb_populate_record(
      null::public.trade_proposals,
      pg_catalog.to_jsonb(proposal_row) || pg_catalog.jsonb_build_object(
        'id', '00000000-0000-4000-8000-000000009611',
        'approved_volume', 0.006,
        'decision_trace_id', '00000000-0000-4000-8000-000000009612'
      )
    )).* from public.trade_proposals as proposal_row
    where proposal_row.id = '00000000-0000-4000-8000-000000009607'$$,
  '23514',
  null,
  'approved proposal volume cannot exceed the requested volume'
);

select throws_ok(
  $$insert into public.trade_proposals
    select (pg_catalog.jsonb_populate_record(
      null::public.trade_proposals,
      pg_catalog.to_jsonb(proposal_row) || pg_catalog.jsonb_build_object(
        'id', '00000000-0000-4000-8000-000000009609',
        'market_snapshot_id', '00000000-0000-4000-8000-000000009606',
        'decision_trace_id', '00000000-0000-4000-8000-000000009610'
      )
    )).* from public.trade_proposals as proposal_row
    where proposal_row.id = '00000000-0000-4000-8000-000000009607'$$,
  '23503',
  null,
  'proposal feature provenance must name the proposal market snapshot exactly'
);

select throws_ok(
  $$insert into public.feature_snapshots (
      owner_id, trading_account_id, market_snapshot_id,
      feature_schema_version, feature_values, captured_at
    ) values (
      '00000000-0000-4000-8000-000000000201',
      '00000000-0000-4000-8000-000000009601',
      '00000000-0000-4000-8000-000000009602', 'cross-account', '{}',
      clock_timestamp()
    )$$,
  '23503'
);

select throws_ok(
  $$insert into public.broker_symbols (
      owner_id, trading_account_id, broker_symbol, specification_version,
      account_currency, contract_size, digits, point_size, tick_size,
      minimum_volume, maximum_volume, volume_step, stop_level,
      calculation_mode, fetched_at
    ) values (
      '00000000-0000-4000-8000-000000009301',
      '00000000-0000-4000-8000-000000000301', 'XAUUSD', 'cross-owner',
      'USD', 100, 2, 0.01, 0.01, 0.01, 100, 0.01, 10, 'fixture', clock_timestamp()
    )$$,
  '23503'
);

select ok(
  exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid = 'public.risk_checks'::regclass
      and contype = 'c'
      and pg_catalog.pg_get_constraintdef(oid) like '%btrim(limit_value)%'
      and pg_catalog.pg_get_constraintdef(oid) like '%length(limit_value) <= 512%'
  ) and exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid = 'public.risk_checks'::regclass
      and contype = 'c'
      and pg_catalog.pg_get_constraintdef(oid) like '%btrim(explanation)%'
      and pg_catalog.pg_get_constraintdef(oid) like '%length(explanation) <= 512%'
  ),
  'optional risk-check text is nullable or trimmed nonblank and at most 512 characters'
);

select ok(
  exists (
    select 1
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as relation on relation.oid = index_row.indrelid
    where relation.oid = 'public.broker_orders'::regclass
      and index_row.indisunique
      and not index_row.indnullsnotdistinct
      and pg_catalog.pg_get_indexdef(index_row.indexrelid)
          like '%(owner_id, broker_order_reference)%'
  ),
  'nullable broker references use ordinary uniqueness and permit multiple NULL values'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from pg_catalog.pg_constraint
    where conrelid = 'public.trade_proposals'::regclass
      and contype = 'f'
      and pg_catalog.pg_get_constraintdef(oid) like '%trading_account_id%'
      and (
        pg_catalog.pg_get_constraintdef(oid) like '%broker_symbols%'
        or pg_catalog.pg_get_constraintdef(oid) like '%risk_policy_versions%'
        or pg_catalog.pg_get_constraintdef(oid) like '%market_snapshots%'
        or pg_catalog.pg_get_constraintdef(oid) like '%feature_snapshots%'
      )
  ),
  4,
  'proposal symbol, policy, market, and feature bindings enforce account consistency'
);

select * from finish();
rollback;
