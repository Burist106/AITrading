begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to aurum_worker;
grant execute on all functions in schema extensions to aurum_worker;
set local search_path = public, extensions;

select plan(40);

select has_table('public', 'mt5_account_observations', 'account observations exist');
select has_table('public', 'mt5_symbol_observations', 'symbol observations exist');
select has_table('public', 'mt5_latest_tick_observations', 'bounded latest tick exists');
select has_table('public', 'mt5_reconciliation_runs', 'reconciliation runs exist');
select has_table('public', 'mt5_reconciliation_mismatches', 'mismatch evidence exists');

select is(
  (
    select pg_catalog.count(*)
    from pg_catalog.pg_class as relation
    join pg_catalog.pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname like 'mt5_%'
      and relation.relkind = 'r'
      and relation.relrowsecurity and relation.relforcerowsecurity
  ),
  6::bigint,
  'every MT5 observation table enables and forces RLS'
);
select ok(
  has_table_privilege('authenticated', 'public.mt5_account_observations', 'select')
  and has_table_privilege('authenticated', 'public.mt5_symbol_observations', 'select')
  and has_table_privilege('authenticated', 'public.mt5_latest_tick_observations', 'select')
  and has_table_privilege('authenticated', 'public.mt5_reconciliation_runs', 'select')
  and has_table_privilege('authenticated', 'public.mt5_reconciliation_mismatches', 'select')
  and has_table_privilege('authenticated', 'public.mt5_history_query_evidence', 'select'),
  'authenticated receives read-only table privileges'
);
select ok(
  not has_table_privilege('anon', 'public.mt5_account_observations', 'select')
  and not has_table_privilege('anon', 'public.mt5_latest_tick_observations', 'select'),
  'anonymous receives no MT5 observation privileges'
);
select ok(
  not has_table_privilege('aurum_worker', 'public.mt5_account_observations', 'insert')
  and not has_table_privilege('aurum_worker', 'public.mt5_symbol_observations', 'insert')
  and not has_table_privilege('aurum_worker', 'public.mt5_latest_tick_observations', 'update')
  and not has_table_privilege('aurum_worker', 'public.mt5_reconciliation_runs', 'insert')
  and not has_table_privilege('aurum_worker', 'public.mt5_history_query_evidence', 'insert'),
  'Worker receives no direct observation DML'
);
select ok(
  has_function_privilege('aurum_worker', 'public.worker_record_mt5_account_observation(jsonb)', 'execute')
  and not has_function_privilege('authenticated', 'public.worker_record_mt5_account_observation(jsonb)', 'execute')
  and not has_function_privilege('anon', 'public.worker_begin_reconciliation(jsonb)', 'execute'),
  'only the Worker can execute MT5 reporting RPCs'
);

set local role aurum_worker;
select is(
  public.worker_record_mt5_account_observation('{}'::jsonb),
  'WORKER_UNAUTHORIZED',
  'missing Worker claims fail closed'
);
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-mt5"}',
  true
);

reset role;
create temporary table mt5_payloads on commit drop as
select
  pg_catalog.jsonb_build_object(
    'observed_at', '2026-08-28T00:00:00Z',
    'source', 'fake_mt5',
    'adapter_version', 'fake-v1',
    'trace_id', 'trace-account',
    'schema_version', '1',
    'trade_mode', 'demo',
    'masked_login', '••••3456',
    'masked_server', 'demo…a91f',
    'account_fingerprint', 'mt5-account-v1:' || pg_catalog.repeat('a', 64),
    'server_fingerprint', 'mt5-server-v1:' || pg_catalog.repeat('b', 64),
    'currency', 'USD',
    'leverage', 100,
    'verification_state', 'verified_demo_bound'
  ) as account_payload,
  pg_catalog.jsonb_build_object(
    'observed_at', '2026-08-28T00:00:01Z',
    'source', 'fake_mt5',
    'adapter_version', 'fake-v1',
    'trace_id', 'trace-symbol',
    'schema_version', '1',
    'canonical_symbol', 'XAUUSD',
    'broker_symbol', 'XAUUSD',
    'symbol_path', 'Metals',
    'description', 'Gold versus US Dollar',
    'base_currency', 'XAU',
    'profit_currency', 'USD',
    'margin_currency', 'USD',
    'digits', 2,
    'point', '0.01',
    'tick_size', '0.01',
    'tick_value', '1.00',
    'tick_value_profit', '1.00',
    'tick_value_loss', '1.00',
    'contract_size', '100',
    'minimum_volume', '0.01',
    'maximum_volume', '100',
    'volume_step', '0.01',
    'stops_level', 10,
    'freeze_level', 0,
    'trade_calculation_mode', 'calc_1',
    'trade_mode', 'full',
    'filling_mode', 'fill_1',
    'expiration_mode', 'expiration_7',
    'order_mode', 'order_127',
    'specification_fingerprint', 'mt5-spec-v1:' || pg_catalog.repeat('c', 64),
    'usability_state', 'usable',
    'unusable_reason', null,
    'raw_diagnostic_codes', '{"trade_mode":4}'::jsonb,
    'account_fingerprint', 'mt5-account-v1:' || pg_catalog.repeat('a', 64)
  ) as symbol_payload,
  pg_catalog.jsonb_build_object(
    'observed_at', '2026-08-28T00:00:02Z',
    'source', 'fake_mt5',
    'adapter_version', 'fake-v1',
    'trace_id', 'trace-tick',
    'schema_version', '1',
    'symbol', 'XAUUSD',
    'bid', '2345.10',
    'ask', '2345.30',
    'spread_price', '0.20',
    'spread_points', '20',
    'tick_at', '2026-08-28T00:00:01Z',
    'age_seconds', '1',
    'freshness', 'live',
    'account_fingerprint', 'mt5-account-v1:' || pg_catalog.repeat('a', 64)
  ) as tick_payload,
  pg_catalog.jsonb_build_object(
    'observed_at', '2026-08-28T00:00:03Z',
    'source', 'mt5',
    'adapter_version', 'aurum-reconciliation-v1',
    'trace_id', 'trace-reconciliation',
    'schema_version', '1',
    'reconciliation_id', '00000000-0000-4000-8000-000000008201',
    'started_at', '2026-08-28T00:00:03Z',
    'completed_at', '2026-08-28T00:00:04Z',
    'outcome', 'mismatch',
    'reason_code', 'RECONCILIATION_INCOMPLETE',
    'account_fingerprint', 'mt5-account-v1:' || pg_catalog.repeat('a', 64),
    'server_fingerprint', 'mt5-server-v1:' || pg_catalog.repeat('b', 64),
    'broker_symbol', 'XAUUSD',
    'symbol_specification_fingerprint', 'mt5-spec-v1:' || pg_catalog.repeat('c', 64),
    'open_position_count', 0,
    'active_order_count', 0,
    'order_history_count', 0,
    'deal_history_count', 0,
    'order_history_evidence', pg_catalog.jsonb_build_object(
      'history_kind', 'orders',
      'requested_start_at', '2026-08-27T00:00:02Z',
      'requested_end_at', '2026-08-28T00:00:02Z',
      'query_completed_at', '2026-08-28T00:00:02.500Z',
      'returned_count', 0,
      'earliest_returned_at', null,
      'latest_returned_at', null,
      'result_state', 'empty_valid_result',
      'reason_code', 'HISTORY_EMPTY_VALID_RESULT'
    ),
    'deal_history_evidence', pg_catalog.jsonb_build_object(
      'history_kind', 'deals',
      'requested_start_at', '2026-08-27T00:00:02Z',
      'requested_end_at', '2026-08-28T00:00:02Z',
      'query_completed_at', '2026-08-28T00:00:02.750Z',
      'returned_count', 0,
      'earliest_returned_at', null,
      'latest_returned_at', null,
      'result_state', 'empty_valid_result',
      'reason_code', 'HISTORY_EMPTY_VALID_RESULT'
    ),
    'mismatches', pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
      'category', 'EXECUTION_RESULT_UNCERTAIN',
      'severity', 'critical',
      'resource_type', 'system_command',
      'resource_reference', '00000000-0000-4000-8000-000000008299',
      'reason_code', 'RECONCILIATION_INCOMPLETE'
    ))
  ) as report_payload;
grant select on mt5_payloads to aurum_worker;
set local role aurum_worker;

select is(
  public.worker_record_mt5_account_observation(
    (select account_payload from mt5_payloads)
  ),
  'OBSERVATION_RECORDED',
  'valid sanitized account observation is recorded'
);
select is(
  public.worker_record_mt5_account_observation(
    (select account_payload from mt5_payloads)
  ),
  'IDEMPOTENT_REPLAY',
  'account observation replay is idempotent'
);
select is(
  public.worker_record_mt5_account_observation(
    (select account_payload from mt5_payloads)
      || pg_catalog.jsonb_build_object('masked_server', E'authorization: bad\nheader')
  ),
  'INVALID_ACCOUNT_OBSERVATION',
  'unsafe account metadata is rejected'
);
reset role;
select is(
  (select pg_catalog.count(*) from public.mt5_account_observations),
  1::bigint,
  'replay and invalid account calls append no rows'
);
set local role aurum_worker;

select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_payload from mt5_payloads)
  ),
  'OBSERVATION_RECORDED',
  'complete normalized symbol specification is recorded'
);
select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_payload from mt5_payloads)
  ),
  'IDEMPOTENT_REPLAY',
  'identical specification fingerprint replays idempotently'
);
reset role;
select is(
  (select pg_catalog.count(*) from public.mt5_symbol_observations),
  1::bigint,
  'symbol observation is append-versioned by fingerprint'
);
set local role aurum_worker;

select is(
  public.worker_upsert_mt5_latest_tick((select tick_payload from mt5_payloads)),
  'TICK_RECORDED',
  'valid latest tick is recorded'
);
select is(
  public.worker_upsert_mt5_latest_tick(
    (select tick_payload from mt5_payloads)
      || '{"observed_at":"2026-08-28T00:00:03Z","trace_id":"trace-tick-2"}'::jsonb
  ),
  'TICK_RECORDED',
  'newer latest tick replaces the bounded current row'
);
reset role;
select results_eq(
  $$select count(*), max(version) from public.mt5_latest_tick_observations$$,
  $$values (1::bigint, 2)$$,
  'latest tick storage retains one row and increments its version'
);
set local role aurum_worker;
select is(
  public.worker_upsert_mt5_latest_tick(
    (select tick_payload from mt5_payloads)
      || '{"observed_at":"2026-08-27T23:59:00Z","trace_id":"trace-tick-stale"}'::jsonb
  ),
  'STALE_TICK_IGNORED',
  'an older tick cannot overwrite the current observation'
);
select ok(
  (public.worker_read_mt5_reconciliation_state() ? 'position_tickets')
  and (public.worker_read_mt5_reconciliation_state() ? 'executing_command_ids')
  and (public.worker_read_mt5_reconciliation_state() -> 'position_tickets') = '[]'::jsonb,
  'Worker reads a bounded payload-free reconciliation state'
);

select is(
  public.worker_begin_reconciliation((select report_payload from mt5_payloads)),
  'RECONCILIATION_STARTED',
  'reconciliation begins through an idempotent Worker RPC'
);
select is(
  public.worker_begin_reconciliation((select report_payload from mt5_payloads)),
  'IDEMPOTENT_REPLAY',
  'reconciliation begin replay is idempotent'
);
select is(
  public.worker_record_reconciliation_mismatch(
    '00000000-0000-4000-8000-000000008201',
    pg_catalog.jsonb_build_object(
      'category', 'EXECUTION_RESULT_UNCERTAIN',
      'severity', 'critical',
      'resource_type', 'system_command',
      'resource_reference', '00000000-0000-4000-8000-000000008299',
      'reason_code', 'RECONCILIATION_INCOMPLETE'
    )
  ),
  'MISMATCH_RECORDED',
  'uncertain execution is recorded as observation-only mismatch evidence'
);
select is(
  public.worker_record_reconciliation_mismatch(
    '00000000-0000-4000-8000-000000008201',
    pg_catalog.jsonb_build_object(
      'category', 'EXECUTION_RESULT_UNCERTAIN',
      'severity', 'critical',
      'resource_type', 'system_command',
      'resource_reference', '00000000-0000-4000-8000-000000008299',
      'reason_code', 'RECONCILIATION_INCOMPLETE'
    )
  ),
  'IDEMPOTENT_REPLAY',
  'mismatch replay appends no duplicate row'
);
select is(
  public.worker_record_reconciliation_mismatch(
    '00000000-0000-4000-8000-000000008201',
    pg_catalog.jsonb_build_object(
      'category', 'EXECUTION_RESULT_UNCERTAIN',
      'severity', 'critical',
      'resource_type', 'system_command',
      'resource_reference', 'password=' || 'unsafe-value',
      'reason_code', 'RECONCILIATION_INCOMPLETE'
    )
  ),
  'INVALID_RECONCILIATION_MISMATCH',
  'secret-shaped mismatch reference is rejected'
);
select is(
  public.worker_complete_reconciliation((select report_payload from mt5_payloads)),
  'RECONCILIATION_COMPLETED',
  'reconciliation completes without mutating operational resources'
);
select is(
  public.worker_complete_reconciliation((select report_payload from mt5_payloads)),
  'IDEMPOTENT_REPLAY',
  'reconciliation completion replay is idempotent'
);
reset role;
select results_eq(
  $$select status, outcome, mismatch_count
    from public.mt5_reconciliation_runs
    where id = '00000000-0000-4000-8000-000000008201'$$,
  $$values ('completed', 'mismatch', 1)$$,
  'completed reconciliation preserves the submitted safe result'
);
select throws_ok(
  $$update public.mt5_reconciliation_mismatches
    set resolution_state = 'unresolved'$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'reconciliation mismatches are append-only'
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
  (select pg_catalog.count(*) from public.mt5_account_observations),
  1::bigint,
  'owner can read own sanitized account observation'
);
select pg_catalog.set_config(
  'request.jwt.claim.sub', '00000000-0000-4000-8000-000000000202', true
);
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"authenticated","sub":"00000000-0000-4000-8000-000000000202"}',
  true
);
select is(
  (select pg_catalog.count(*) from public.mt5_account_observations),
  0::bigint,
  'another owner cannot read MT5 observations'
);
select throws_ok(
  $$insert into public.mt5_account_observations (
      owner_id, worker_id, account_fingerprint, server_fingerprint,
      masked_login, masked_server, trade_mode, verification_state,
      observed_at, source, adapter_version, trace_id, schema_version
    ) values (
      '00000000-0000-4000-8000-000000000202', 'browser',
      'mt5-account-v1:browser', 'mt5-server-v1:browser', '••••0000',
      'demo…0000', 'demo', 'verified_demo_unbound', clock_timestamp(),
      'fake_mt5', 'browser', 'browser', '1'
    )$$,
  '42501',
  'permission denied for table mt5_account_observations',
  'browser cannot write MT5 observations'
);

reset role;
set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-mt5"}',
  true
);
select throws_ok(
  $$insert into public.mt5_reconciliation_runs (
      id, owner_id, worker_id, status, reason_code, trace_id, started_at
    ) values (
      '00000000-0000-4000-8000-000000008298',
      '00000000-0000-4000-8000-000000000201', 'worker-mt5',
      'running', 'HEALTHY', 'direct-write', clock_timestamp()
    )$$,
  '42501',
  'permission denied for table mt5_reconciliation_runs',
  'Worker cannot bypass secured RPCs with direct DML'
);

reset role;
select is(
  (
    select pg_catalog.count(*) from public.audit_logs
    where action in (
      'mt5_account_observation_recorded', 'mt5_symbol_observation_recorded',
      'mt5_latest_tick_recorded', 'mt5_reconciliation_started',
      'mt5_reconciliation_mismatch_recorded', 'mt5_reconciliation_completed'
    )
  ),
  5::bigint,
  'security-significant MT5 state changes append bounded audit evidence'
);
select ok(
  not exists (
    select 1 from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and procedure.proname ~ '(order|execution|position).*(create|send|submit|modify|close|cancel)'
      and procedure.proname like 'worker_%'
  ),
  'Milestone 2 adds no broker Order, execution, or Position write RPC'
);
select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public'
      and table_name like 'mt5_%'
      and column_name in ('login', 'account_name', 'server', 'password')
  ),
  'MT5 tables contain no raw login, holder name, server, or password column'
);
select is(
  (select pg_catalog.count(*) from public.mt5_reconciliation_mismatches),
  1::bigint,
  'mismatch replay and rejected unsafe input append no rows'
);

select * from finish();
rollback;
