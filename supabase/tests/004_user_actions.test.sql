begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(47);

insert into public.market_snapshots (
  id, owner_id, trading_account_id, bid, ask, spread_points, session,
  regime, atr, freshness, age_ms, transport, captured_at
) values (
  '00000000-0000-4000-8000-000000007101',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301',
  2300.00, 2300.30, 3.0, 'london', 'trending', 4.0, 'live', 100,
  'database_fallback', pg_catalog.clock_timestamp()
);

insert into public.feature_snapshots (
  id, owner_id, trading_account_id, market_snapshot_id,
  feature_schema_version, feature_values, captured_at
) values (
  '00000000-0000-4000-8000-000000007102',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301',
  '00000000-0000-4000-8000-000000007101',
  'fixture-v1', '{"fixture":true}', pg_catalog.clock_timestamp()
);

insert into public.trade_proposals (
  id, owner_id, proposal_version, trading_account_id, broker_symbol_id,
  risk_policy_version_id, account_currency, broker_server, broker_symbol,
  symbol_specification_version, direction, strategy_code, strategy_version,
  eligibility_policy_id, eligibility_policy_version, eligibility_outcome,
  eligibility_evaluated_at, risk_policy_version, entry_price,
  stop_loss_price, take_profit_price, calculated_volume, requested_volume,
  approved_volume, maximum_permitted_volume, risk_amount, risk_pct,
  risk_reward, market_snapshot_id, feature_snapshot_id, decision_trace_id,
  status, created_at, expires_at
) values
  (
    '00000000-0000-4000-8000-000000007201',
    '00000000-0000-4000-8000-000000000201', 1,
    '00000000-0000-4000-8000-000000000301',
    '00000000-0000-4000-8000-000000000311',
    '00000000-0000-4000-8000-000000000332', 'USD',
    'DEMO-FIXTURE-SERVER', 'XAUUSD', 'development-spec-v1', 'BUY',
    'fixture-strategy', 'v1', 'fixture-policy', 'v1', 'ask',
    pg_catalog.clock_timestamp(), 'demo-risk-policy-v1', 2300, 2290, 2320,
    0.01, 0.01, 0.01, 0.01, 10, 0.10, 2.0,
    '00000000-0000-4000-8000-000000007101',
    '00000000-0000-4000-8000-000000007102',
    '00000000-0000-4000-8000-000000007211', 'validated',
    pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp() + interval '10 minutes'
  ),
  (
    '00000000-0000-4000-8000-000000007202',
    '00000000-0000-4000-8000-000000000201', 1,
    '00000000-0000-4000-8000-000000000301',
    '00000000-0000-4000-8000-000000000311',
    '00000000-0000-4000-8000-000000000332', 'USD',
    'DEMO-FIXTURE-SERVER', 'XAUUSD', 'development-spec-v1', 'BUY',
    'fixture-strategy', 'v1', 'fixture-policy', 'v1', 'ask',
    pg_catalog.clock_timestamp(), 'demo-risk-policy-v1', 2300, 2290, 2320,
    0.01, 0.01, 0.01, 0.01, 10, 0.10, 2.0,
    '00000000-0000-4000-8000-000000007101',
    '00000000-0000-4000-8000-000000007102',
    '00000000-0000-4000-8000-000000007212', 'validated',
    pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp() + interval '10 minutes'
  ),
  (
    '00000000-0000-4000-8000-000000007203',
    '00000000-0000-4000-8000-000000000201', 1,
    '00000000-0000-4000-8000-000000000301',
    '00000000-0000-4000-8000-000000000311',
    '00000000-0000-4000-8000-000000000332', 'USD',
    'DEMO-FIXTURE-SERVER', 'XAUUSD', 'development-spec-v1', 'BUY',
    'fixture-strategy', 'v1', 'fixture-policy', 'v1', 'ask',
    pg_catalog.clock_timestamp(), 'demo-risk-policy-v1', 2300, 2290, 2320,
    0.01, 0.01, 0.01, 0.01, 10, 0.10, 2.0,
    '00000000-0000-4000-8000-000000007101',
    '00000000-0000-4000-8000-000000007102',
    '00000000-0000-4000-8000-000000007213', 'validated',
    pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp() + interval '10 minutes'
  );

insert into public.system_commands (
  id, owner_id, type, payload, requested_by, target_resource_type,
  target_resource_id, expected_resource_version, idempotency_key, expires_at
) values (
  '00000000-0000-4000-8000-000000007301',
  '00000000-0000-4000-8000-000000000201', 'APPROVE_PROPOSAL',
  '{"proposalId":"00000000-0000-4000-8000-000000007203","proposalVersion":1}',
  '00000000-0000-4000-8000-000000000201', 'trade_proposal',
  '00000000-0000-4000-8000-000000007203', 1,
  'fixture-position-source', pg_catalog.clock_timestamp() + interval '10 minutes'
);

insert into public.broker_orders (
  id, owner_id, trading_account_id, trade_proposal_id, system_command_id,
  broker_order_reference, direction, requested_volume, requested_price,
  stop_loss_price, take_profit_price, status
) values (
  '00000000-0000-4000-8000-000000007401',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301',
  '00000000-0000-4000-8000-000000007203',
  '00000000-0000-4000-8000-000000007301', 'fixture-order', 'BUY', 0.01,
  2300, 2290, 2320, 'recorded'
);

insert into public.positions (
  id, owner_id, trading_account_id, trade_proposal_id, broker_order_id,
  broker_position_reference, position_version, direction, volume, entry_price,
  current_price, stop_loss_price, take_profit_price, status, opened_at
) values (
  '00000000-0000-4000-8000-000000007501',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301',
  '00000000-0000-4000-8000-000000007203',
  '00000000-0000-4000-8000-000000007401', 'fixture-position', 1, 'BUY',
  0.01, 2300, 2301, 2290, 2320, 'open', pg_catalog.clock_timestamp()
);

set local role authenticated;
select pg_catalog.set_config(
  'request.jwt.claim.sub', '00000000-0000-4000-8000-000000000201', true
);
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"authenticated","sub":"00000000-0000-4000-8000-000000000201"}',
  true
);

select is(
  (public.request_proposal_approval(
    '00000000-0000-4000-8000-000000007201', 1, 'ua-approve'
  )).result_code,
  'CREATED', 'proposal approval creates a durable command'
);
select is(
  (public.request_proposal_rejection(
    '00000000-0000-4000-8000-000000007202', 1, 'operator-reject', 'ua-reject'
  )).result_code,
  'CREATED', 'proposal rejection creates a durable command'
);
select is(
  (public.request_pause_new_trades('ua-pause', 'operator-pause')).result_code,
  'CREATED', 'pause creates a durable command'
);
select is(
  (public.request_resume_system(
    '00000000-0000-4000-8000-000000007601', 'ua-resume'
  )).result_code,
  'CREATED', 'resume creates a durable command'
);
select is(
  (public.request_emergency_stop('operator-emergency', 'ua-emergency')).result_code,
  'CREATED', 'emergency stop creates a durable command'
);
select is(
  (public.request_position_close(
    '00000000-0000-4000-8000-000000007501', 1, 'operator-close', 'ua-close'
  )).result_code,
  'CREATED', 'position-close intent creates a durable command only'
);
select is(
  (public.request_stop_loss_change(
    '00000000-0000-4000-8000-000000007501', 1, 2295, 'ua-stop-loss'
  )).result_code,
  'CREATED', 'stop-loss-change intent creates a durable command only'
);
select is(
  (public.request_take_profit_change(
    '00000000-0000-4000-8000-000000007501', 1, 2330, 'ua-take-profit'
  )).result_code,
  'CREATED', 'take-profit-change intent creates a durable command only'
);
select is(
  (public.request_risk_policy_change(
    'risk_per_trade_pct', 0.20, 'operator-risk', 1, 'ua-risk-one'
  )).result_code,
  'CREATED', 'risk-policy intent creates a durable command and pending version'
);

reset role;

select throws_ok(
  $$insert into public.risk_policy_versions
    select (pg_catalog.jsonb_populate_record(
      null::public.risk_policy_versions,
      pg_catalog.to_jsonb(version_row) || pg_catalog.jsonb_build_object(
        'id', '00000000-0000-4000-8000-000000007299',
        'version', 9990,
        'version_label', 'duplicate-source-command'
      )
    )).* from public.risk_policy_versions as version_row
    where version_row.source_command_id = (
      select id from public.system_commands where idempotency_key = 'ua-risk-one'
    )$$,
  '23505',
  null,
  'one command can create at most one immutable risk-policy snapshot'
);

select is(
  (
    select pg_catalog.count(distinct type)
    from public.system_commands
    where idempotency_key like 'ua-%'
  ),
  9::bigint,
  'the nine authenticated intent RPCs cover exactly all nine command types'
);

select ok(
  not exists (
    select 1 from public.system_commands as command_row
    where command_row.idempotency_key in (
      'ua-approve', 'ua-reject', 'ua-pause', 'ua-resume', 'ua-emergency',
      'ua-close', 'ua-stop-loss', 'ua-take-profit', 'ua-risk-one'
    ) and case command_row.type
      when 'APPROVE_PROPOSAL' then command_row.payload <> pg_catalog.jsonb_build_object(
        'proposalId', '00000000-0000-4000-8000-000000007201', 'proposalVersion', 1
      )
      when 'REJECT_PROPOSAL' then command_row.payload <> pg_catalog.jsonb_build_object(
        'proposalId', '00000000-0000-4000-8000-000000007202',
        'proposalVersion', 1, 'reason', 'operator-reject'
      )
      when 'PAUSE_NEW_TRADES' then command_row.payload <> '{"reason":"operator-pause"}'::jsonb
      when 'RESUME_SYSTEM' then command_row.payload <> pg_catalog.jsonb_build_object(
        'checklistAcknowledgementId', '00000000-0000-4000-8000-000000007601'
      )
      when 'ACTIVATE_EMERGENCY_STOP' then command_row.payload <> '{"reason":"operator-emergency"}'::jsonb
      when 'REQUEST_POSITION_CLOSE' then command_row.payload <> pg_catalog.jsonb_build_object(
        'positionId', '00000000-0000-4000-8000-000000007501',
        'expectedPositionVersion', 1, 'reason', 'operator-close'
      )
      when 'REQUEST_STOP_LOSS_CHANGE' then command_row.payload <> pg_catalog.jsonb_build_object(
        'positionId', '00000000-0000-4000-8000-000000007501',
        'expectedPositionVersion', 1, 'newStopLoss', 2295
      )
      when 'REQUEST_TAKE_PROFIT_CHANGE' then command_row.payload <> pg_catalog.jsonb_build_object(
        'positionId', '00000000-0000-4000-8000-000000007501',
        'expectedPositionVersion', 1, 'newTakeProfit', 2330
      )
      when 'REQUEST_RISK_POLICY_CHANGE' then command_row.payload <> pg_catalog.jsonb_build_object(
        'ruleKey', 'risk_per_trade_pct', 'newValue', 0.20, 'reason', 'operator-risk'
      )
    end
  ),
  'all nine durable command payloads use exact canonical field names and values'
);

set local role authenticated;

select is(
  (public.request_pause_new_trades(
    'ua-pause',
    'operator-pause',
    pg_catalog.clock_timestamp() - interval '1 minute'
  )).result_code,
  'IDEMPOTENT_REPLAY',
  'global enqueue replay takes precedence over a newly supplied past expiry'
);
select is(
  (public.request_proposal_approval(
    '00000000-0000-4000-8000-000000007201', 1, 'ua-approve'
  )).result_code,
  'IDEMPOTENT_REPLAY', 'exact approval replay returns its original command'
);
select is(
  (public.request_proposal_rejection(
    '00000000-0000-4000-8000-000000007202', 1, 'operator-reject', 'ua-reject'
  )).result_code,
  'IDEMPOTENT_REPLAY', 'exact rejection replay returns its original command'
);

reset role;
update public.trade_proposals
set expires_at = created_at + interval '1 millisecond'
where id = '00000000-0000-4000-8000-000000007201';
set local role authenticated;

select is(
  (public.request_proposal_approval(
    '00000000-0000-4000-8000-000000007201',
    1,
    'ua-approve',
    null,
    pg_catalog.clock_timestamp() - interval '1 minute'
  )).result_code,
  'IDEMPOTENT_REPLAY',
  'exact approval replay survives proposal and requested-command expiry'
);
select is(
  (public.request_position_close(
    '00000000-0000-4000-8000-000000007501',
    1,
    'operator-close',
    'ua-close',
    pg_catalog.clock_timestamp() - interval '1 minute'
  )).result_code,
  'IDEMPOTENT_REPLAY',
  'exact Position-close replay ignores a newly supplied past command expiry'
);
select is(
  (public.request_stop_loss_change(
    '00000000-0000-4000-8000-000000007501',
    1,
    2295,
    'ua-stop-loss',
    pg_catalog.clock_timestamp() - interval '1 minute'
  )).result_code,
  'IDEMPOTENT_REPLAY',
  'exact stop-loss replay ignores a newly supplied past command expiry'
);
select is(
  (public.request_take_profit_change(
    '00000000-0000-4000-8000-000000007501',
    1,
    2330,
    'ua-take-profit',
    pg_catalog.clock_timestamp() - interval '1 minute'
  )).result_code,
  'IDEMPOTENT_REPLAY',
  'exact take-profit replay ignores a newly supplied past command expiry'
);

reset role;
update public.trade_proposals
set expires_at = pg_catalog.clock_timestamp() + interval '10 minutes'
where id = '00000000-0000-4000-8000-000000007201';
set local role authenticated;

select is(
  (public.request_pause_new_trades(
    'ua-pause',
    'different-reason',
    pg_catalog.clock_timestamp() - interval '1 minute'
  )).result_code,
  'IDEMPOTENCY_CONFLICT',
  'global enqueue conflict takes precedence over a newly supplied past expiry'
);
select is(
  (public.request_pause_new_trades(
    'ua-new-past-expiry',
    'new-request',
    pg_catalog.clock_timestamp() - interval '1 minute'
  )).result_code,
  'INVALID_COMMAND_EXPIRY',
  'a past expiry is rejected when the idempotency key has not been used'
);
select is(
  (public.request_proposal_approval(
    '00000000-0000-4000-8000-000000007201', 2, 'ua-stale-proposal'
  )).result_code,
  'STALE_PROPOSAL_VERSION', 'stale proposal version returns a deterministic code'
);
select is(
  (public.request_position_close(
    '00000000-0000-4000-8000-000000007501', 2, 'stale', 'ua-stale-position'
  )).result_code,
  'STALE_POSITION_VERSION', 'stale Position version returns a deterministic code'
);
select is(
  (public.request_risk_policy_change(
    'risk_per_trade_pct', 0.19, 'stale', 2, 'ua-stale-risk'
  )).result_code,
  'STALE_RISK_POLICY_VERSION', 'stale risk-policy version returns a deterministic code'
);

select is(
  (public.request_proposal_approval(
    '00000000-0000-4000-8000-000000007201', null, 'ua-null-approve'
  )).result_code,
  'INVALID_PROPOSAL_VERSION', 'null approval version returns safely'
);
select is(
  (public.request_proposal_rejection(
    '00000000-0000-4000-8000-000000007202', 0, 'reject', 'ua-zero-reject'
  )).result_code,
  'INVALID_PROPOSAL_VERSION', 'nonpositive rejection version returns safely'
);
select is(
  (public.request_position_close(
    '00000000-0000-4000-8000-000000007501', null, 'close', 'ua-null-close'
  )).result_code,
  'INVALID_POSITION_VERSION', 'null close version returns safely'
);
select is(
  (public.request_stop_loss_change(
    '00000000-0000-4000-8000-000000007501', 0, 2295, 'ua-zero-sl'
  )).result_code,
  'INVALID_POSITION_VERSION', 'nonpositive stop-loss version returns safely'
);
select is(
  (public.request_take_profit_change(
    '00000000-0000-4000-8000-000000007501', null, 2330, 'ua-null-tp'
  )).result_code,
  'INVALID_POSITION_VERSION', 'null take-profit version returns safely'
);
select is(
  (public.request_risk_policy_change(
    'risk_per_trade_pct', 0.20, 'invalid', 0, 'ua-zero-risk'
  )).result_code,
  'INVALID_RISK_POLICY_VERSION', 'nonpositive risk-policy version returns safely'
);
select is(
  (public.request_resume_system(null, 'ua-null-resume')).result_code,
  'INVALID_CHECKLIST_ACKNOWLEDGEMENT', 'null resume checklist UUID returns safely'
);
select is(
  (public.request_proposal_approval(null, 1, 'ua-null-proposal')).result_code,
  'PROPOSAL_NOT_FOUND', 'null proposal target returns safely'
);
select is(
  (public.request_position_close(null, 1, 'close', 'ua-null-position')).result_code,
  'POSITION_NOT_FOUND', 'null Position target returns safely'
);

select is(
  (public.request_proposal_rejection(
    '00000000-0000-4000-8000-000000007201', 1, 'second', 'ua-approve-then-reject'
  )).result_code,
  'PROPOSAL_ALREADY_DECIDED', 'approve then reject is deterministic, not a unique violation'
);
select is(
  (public.request_proposal_approval(
    '00000000-0000-4000-8000-000000007202', 1, 'ua-reject-then-approve'
  )).result_code,
  'PROPOSAL_ALREADY_DECIDED', 'reject then approve is deterministic, not a unique violation'
);

select is(
  (public.request_risk_policy_change(
    'daily_loss_limit_pct', 0.90, 'second-pending', 1, 'ua-risk-two'
  )).result_code,
  'CREATED', 'a second pending risk change allocates after existing pending versions'
);
select results_eq(
  $$select version from public.risk_policy_versions
    where source_command_id is not null order by version$$,
  $$values (2), (3)$$,
  'pending risk versions allocate from max(existing version) plus one'
);
select is(
  (public.request_risk_policy_change(
    'minimum_risk_reward', 9999.5, 'large-valid-minimum', 1, 'ua-risk-large-rr'
  )).result_code,
  'CREATED', 'large minimum risk-reward fits the storage-safe numeric bound'
);
select is(
  (public.request_risk_policy_change(
    'news_blackout_minutes', 1441, 'large-valid-blackout', 1, 'ua-risk-large-news'
  )).result_code,
  'CREATED', 'large integral news blackout fits the storage-safe integer bound'
);
select is(
  (public.request_risk_policy_change(
    'minimum_risk_reward', 10000, 'numeric-overflow', 1, 'ua-risk-rr-overflow'
  )).result_code,
  'RISK_RULE_VALUE_OUT_OF_BOUNDS',
  'minimum risk-reward overflow returns a deterministic safe code'
);
select is(
  (public.request_risk_policy_change(
    'news_blackout_minutes', 2147483648, 'integer-overflow', 1, 'ua-risk-news-overflow'
  )).result_code,
  'RISK_RULE_VALUE_OUT_OF_BOUNDS',
  'news blackout integer overflow returns a deterministic safe code'
);
select is(
  (public.request_risk_policy_change(
    'made_up_rule', 1, 'unsupported', 1, 'ua-risk-unsupported'
  )).result_code,
  'UNSUPPORTED_RISK_RULE', 'unsupported risk key returns safely'
);
select is(
  (public.request_risk_policy_change(
    'risk_per_trade_pct', 0.26, 'unsafe', 1, 'ua-risk-unsafe'
  )).result_code,
  'RISK_RULE_VALUE_OUT_OF_BOUNDS', 'unsafe risk value returns safely'
);
select is(
  (public.request_risk_policy_change(
    'minimum_risk_reward', 'NaN'::numeric, 'nonfinite', 1, 'ua-risk-nan'
  )).result_code,
  'RISK_RULE_VALUE_OUT_OF_BOUNDS', 'non-finite risk value returns safely'
);
select is(
  (public.request_risk_policy_change(
    'risk_per_trade_pct', 0.20, 'operator-risk', 1, 'ua-risk-one'
  )).result_code,
  'IDEMPOTENT_REPLAY', 'risk intent replay does not create another policy version'
);

reset role;

select is(
  (
    select pg_catalog.count(*) from public.risk_policy_versions
    where source_command_id is not null
  ),
  4::bigint,
  'only four distinct risk commands create pending immutable versions'
);
select ok(
  not exists (
    select 1 from public.system_commands as command_row
    where command_row.idempotency_key like 'ua-%'
      and command_row.event_sequence <> 1
  ) and not exists (
    select 1 from public.system_commands as command_row
    where command_row.idempotency_key like 'ua-%'
      and not exists (
        select 1 from public.audit_logs as audit_row
        where audit_row.request_id = command_row.id
      )
  ),
  'each newly accepted intent records its created event and durable audit row'
);

select * from finish();
rollback;
