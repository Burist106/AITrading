begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to aurum_worker;
grant execute on all functions in schema extensions to aurum_worker;
grant usage on schema extensions to aurum_function_owner;
grant execute on all functions in schema extensions to aurum_function_owner;
set local search_path = public, extensions;

select plan(71);

select has_table(
  'public', 'mt5_history_query_evidence',
  'current-run history query evidence exists'
);
select has_column(
  'public', 'broker_symbols', 'base_currency',
  'broker symbol snapshots carry observed base currency'
);
select has_column(
  'public', 'broker_symbols', 'profit_currency',
  'broker symbol snapshots carry observed profit currency'
);
select has_column(
  'public', 'broker_symbols', 'confirmed_specification_fingerprint',
  'broker symbol snapshots carry the explicitly confirmed fingerprint'
);
select has_column(
  'public', 'broker_symbols', 'confirmation_status',
  'broker symbol snapshots carry explicit confirmation status'
);
select has_column(
  'public', 'broker_symbols', 'confirmed_at',
  'broker symbol snapshots carry confirmation time'
);
select has_column(
  'public', 'broker_symbols', 'confirmed_by',
  'broker symbol snapshots carry the confirming actor'
);
select has_column(
  'public', 'broker_symbols', 'confirmation_version',
  'broker symbol snapshots carry append-only confirmation version'
);

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
  'all six MT5 evidence tables enable and force RLS'
);
select ok(
  has_table_privilege(
    'authenticated', 'public.mt5_history_query_evidence', 'select'
  )
  and not has_table_privilege(
    'authenticated', 'public.mt5_history_query_evidence', 'insert'
  )
  and not has_table_privilege(
    'aurum_worker', 'public.mt5_history_query_evidence', 'insert'
  ),
  'history evidence is owner-readable without browser or Worker DML'
);
select ok(
  has_function_privilege(
    'aurum_worker', 'public.worker_read_mt5_reconciliation_state()', 'execute'
  )
  and not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and procedure.proname like 'worker%confirm%symbol%'
  ),
  'Worker can read confirmation but has no confirmation mutation RPC'
);
select ok(
  (
    select pg_catalog.pg_get_userbyid(procedure.proowner)
    from pg_catalog.pg_proc as procedure
    where procedure.oid =
      'private.m2_reconciliation_mismatches_valid(jsonb)'::regprocedure
  ) = 'aurum_function_owner'
  and not has_function_privilege(
    'public', 'private.m2_reconciliation_mismatches_valid(jsonb)', 'execute'
  )
  and not has_function_privilege(
    'anon', 'private.m2_reconciliation_mismatches_valid(jsonb)', 'execute'
  )
  and not has_function_privilege(
    'authenticated',
    'private.m2_reconciliation_mismatches_valid(jsonb)', 'execute'
  )
  and not has_function_privilege(
    'aurum_worker',
    'private.m2_reconciliation_mismatches_valid(jsonb)', 'execute'
  ),
  'mismatch validator is owned privately with no caller execution privilege'
);

create temporary table m2_patch_payloads on commit drop as
select
  pg_catalog.jsonb_build_object(
    'observed_at', '2026-08-28T01:00:00Z',
    'source', 'fake_mt5',
    'adapter_version', 'fake-v2',
    'trace_id', 'trace-symbol-b',
    'schema_version', '1',
    'canonical_symbol', 'XAUUSD',
    'broker_symbol', 'GOLD',
    'symbol_path', 'Metals',
    'description', 'Gold versus US Dollar',
    'base_currency', 'XAU',
    'profit_currency', 'USD',
    'margin_currency', 'EUR',
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
  ) as symbol_b,
  pg_catalog.jsonb_build_object(
    'observed_at', '2026-08-28T02:00:04Z',
    'source', 'mt5',
    'adapter_version', 'aurum-reconciliation-v2',
    'trace_id', 'trace-history-empty',
    'schema_version', '1',
    'reconciliation_id', '00000000-0000-4000-8000-000000008301',
    'started_at', '2026-08-28T02:00:03Z',
    'completed_at', '2026-08-28T02:00:04Z',
    'outcome', 'matched',
    'reason_code', 'HEALTHY',
    'account_fingerprint', 'mt5-account-v1:' || pg_catalog.repeat('a', 64),
    'server_fingerprint', 'mt5-server-v1:' || pg_catalog.repeat('b', 64),
    'broker_symbol', 'GOLD',
    'symbol_specification_fingerprint', 'mt5-spec-v1:' || pg_catalog.repeat('c', 64),
    'open_position_count', 0,
    'active_order_count', 0,
    'order_history_count', 0,
    'deal_history_count', 0,
    'order_history_evidence', pg_catalog.jsonb_build_object(
      'history_kind', 'orders',
      'requested_start_at', '2026-08-27T02:00:00Z',
      'requested_end_at', '2026-08-28T02:00:00Z',
      'query_completed_at', '2026-08-28T02:00:01Z',
      'returned_count', 0,
      'earliest_returned_at', null,
      'latest_returned_at', null,
      'result_state', 'empty_valid_result',
      'reason_code', 'HISTORY_EMPTY_VALID_RESULT'
    ),
    'deal_history_evidence', pg_catalog.jsonb_build_object(
      'history_kind', 'deals',
      'requested_start_at', '2026-08-27T02:00:00Z',
      'requested_end_at', '2026-08-28T02:00:00Z',
      'query_completed_at', '2026-08-28T02:00:02Z',
      'returned_count', 0,
      'earliest_returned_at', null,
      'latest_returned_at', null,
      'result_state', 'empty_valid_result',
      'reason_code', 'HISTORY_EMPTY_VALID_RESULT'
    ),
    'mismatches', '[]'::jsonb
  ) as empty_report;

alter table m2_patch_payloads add column failed_report jsonb;
alter table m2_patch_payloads add column invalid_matched_report jsonb;
alter table m2_patch_payloads add column invalid_matched_claim jsonb;
alter table m2_patch_payloads add column invalid_matched_context jsonb;
alter table m2_patch_payloads add column matched_child_report jsonb;
alter table m2_patch_payloads add column substituted_mismatch_report jsonb;
update m2_patch_payloads set
  failed_report = empty_report || pg_catalog.jsonb_build_object(
    'trace_id', 'trace-history-failed',
    'reconciliation_id', '00000000-0000-4000-8000-000000008302',
    'outcome', 'incomplete',
    'reason_code', 'HISTORY_QUERY_FAILED',
    'order_history_evidence',
      (empty_report -> 'order_history_evidence') || pg_catalog.jsonb_build_object(
        'result_state', 'query_failed',
        'reason_code', 'HISTORY_QUERY_FAILED'
      )
  ),
  invalid_matched_report = empty_report || pg_catalog.jsonb_build_object(
    'trace_id', 'trace-history-invalid-matched',
    'reconciliation_id', '00000000-0000-4000-8000-000000008303',
    'order_history_evidence',
      (empty_report -> 'order_history_evidence') || pg_catalog.jsonb_build_object(
        'result_state', 'query_failed',
        'reason_code', 'HISTORY_QUERY_FAILED'
      )
  ),
  invalid_matched_claim = empty_report || pg_catalog.jsonb_build_object(
    'trace_id', 'trace-history-invalid-claim',
    'reconciliation_id', '00000000-0000-4000-8000-000000008304',
    'reason_code', 'SYMBOL_SPEC_CHANGED',
    'mismatches', pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
      'category', 'SYMBOL_SPEC_CHANGED',
      'severity', 'critical',
      'resource_type', 'symbol_specification',
      'resource_reference', 'mt5-spec-v1:changed',
      'reason_code', 'SYMBOL_SPEC_CHANGED'
    ))
  ),
  invalid_matched_context = empty_report || pg_catalog.jsonb_build_object(
    'trace_id', 'trace-history-missing-context',
    'reconciliation_id', '00000000-0000-4000-8000-000000008305',
    'account_fingerprint', null,
    'server_fingerprint', null,
    'broker_symbol', null,
    'symbol_specification_fingerprint', null
  ),
  matched_child_report = empty_report || pg_catalog.jsonb_build_object(
    'trace_id', 'trace-history-persisted-child',
    'reconciliation_id', '00000000-0000-4000-8000-000000008306'
  ),
  substituted_mismatch_report = empty_report || pg_catalog.jsonb_build_object(
    'trace_id', 'trace-history-substituted-child',
    'reconciliation_id', '00000000-0000-4000-8000-000000008307',
    'outcome', 'mismatch',
    'reason_code', 'RECONCILIATION_INCOMPLETE',
    'mismatches', pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
      'category', 'HISTORY_WINDOW_INCOMPLETE',
      'severity', 'critical',
      'resource_type', 'history_window',
      'resource_reference', 'orders',
      'reason_code', 'HISTORY_WINDOW_INCOMPLETE'
    ))
  );

grant select on m2_patch_payloads to aurum_function_owner;
set local role aurum_function_owner;
select ok(
  not private.m2_history_evidence_valid(
    (select empty_report -> 'order_history_evidence' from m2_patch_payloads)
      || pg_catalog.jsonb_build_object(
        'result_state', 'query_succeeded',
        'reason_code', 'HISTORY_EMPTY_VALID_RESULT',
        'returned_count', 1,
        'earliest_returned_at', '2026-08-27T03:00:00Z',
        'latest_returned_at', '2026-08-27T03:00:00Z'
      ),
    'orders'
  ),
  'non-empty successful evidence cannot carry a valid-empty reason'
);
select ok(
  not private.m2_history_evidence_valid(
    (select empty_report -> 'order_history_evidence' from m2_patch_payloads)
      || '{"result_state":"query_failed","reason_code":"HEALTHY"}'::jsonb,
    'orders'
  ),
  'failed history evidence cannot carry a healthy reason'
);
select ok(
  not private.m2_history_evidence_valid(
    (select empty_report -> 'order_history_evidence' from m2_patch_payloads)
      || pg_catalog.jsonb_build_object(
        'result_state', 'window_unknown',
        'reason_code', 'HEALTHY',
        'query_completed_at', null
      ),
    'orders'
  ),
  'unknown history evidence requires the incomplete-window reason'
);
reset role;

grant select on m2_patch_payloads to aurum_worker;
set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-m2-patch"}',
  true
);

select ok(
  public.worker_read_mt5_reconciliation_state()
    -> 'confirmed_symbol_binding' is not null,
  'state RPC returns an explicit confirmed symbol binding'
);
select is(
  public.worker_read_mt5_reconciliation_state()
    #>> '{confirmed_symbol_binding,confirmed_specification_fingerprint}',
  'mt5-spec-v1:fixture',
  'state RPC starts from the fictional explicitly confirmed fingerprint'
);
select is(
  public.worker_read_mt5_reconciliation_state()
    #>> '{confirmed_symbol_binding,broker_symbol}',
  'XAUUSD',
  'state RPC returns the confirmed broker symbol'
);
select ok(
  not (public.worker_read_mt5_reconciliation_state() ? 'history_window_complete')
  and not (
    public.worker_read_mt5_reconciliation_state()
      ? 'symbol_specification_fingerprint'
  ),
  'state RPC contains neither stale history completeness nor observed spec baseline'
);
select ok(
  pg_catalog.pg_get_functiondef(
    'public.worker_read_mt5_reconciliation_state()'::regprocedure
  ) not like '%mt5_symbol_observations%'
  and pg_catalog.pg_get_functiondef(
    'public.worker_read_mt5_reconciliation_state()'::regprocedure
  ) not like '%history_window_complete%true%',
  'state RPC cannot promote an observation or invent history completeness'
);

select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_b from m2_patch_payloads)
      || '{"base_currency":"EUR"}'::jsonb
  ),
  'SYMBOL_CANONICAL_MISMATCH',
  'wrong base currency returns the dedicated canonical mismatch'
);
select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_b from m2_patch_payloads)
      || '{"profit_currency":"JPY"}'::jsonb
  ),
  'SYMBOL_CANONICAL_MISMATCH',
  'wrong profit currency returns the dedicated canonical mismatch'
);
select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_b from m2_patch_payloads)
      || '{"canonical_symbol":"EURUSD"}'::jsonb
  ),
  'SYMBOL_CANONICAL_MISMATCH',
  'wrong canonical symbol returns the dedicated canonical mismatch'
);
select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_b from m2_patch_payloads)
  ),
  'OBSERVATION_RECORDED',
  'valid XAU/USD alias observation accepts a non-USD margin currency'
);
select is(
  public.worker_read_mt5_reconciliation_state()
    #>> '{confirmed_symbol_binding,confirmed_specification_fingerprint}',
  'mt5-spec-v1:fixture',
  'recording observed B does not replace confirmed A'
);
select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_b from m2_patch_payloads)
  ),
  'IDEMPOTENT_REPLAY',
  'observed B replay remains observation-only'
);
select is(
  public.worker_read_mt5_reconciliation_state()
    #>> '{confirmed_symbol_binding,confirmed_specification_fingerprint}',
  'mt5-spec-v1:fixture',
  'repeated observations still compare against confirmed A'
);

select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_b from m2_patch_payloads)
      || pg_catalog.jsonb_build_object(
        'observed_at', '2026-08-28T01:01:00Z',
        'trace_id', 'trace-symbol-b-not-visible',
        'usability_state', 'not_visible',
        'unusable_reason', 'SYMBOL_NOT_VISIBLE'
      )
  ),
  'OBSERVATION_RECORDED',
  'a material usability-state change appends with the same fingerprint'
);
select is(
  public.worker_record_mt5_symbol_observation(
    (select symbol_b from m2_patch_payloads)
      || pg_catalog.jsonb_build_object(
        'observed_at', '2026-08-28T01:02:00Z',
        'trace_id', 'trace-symbol-b-not-visible-next-cycle',
        'usability_state', 'not_visible',
        'unusable_reason', 'SYMBOL_NOT_VISIBLE'
      )
  ),
  'IDEMPOTENT_REPLAY',
  'unchanged consecutive material state does not grow every poll cycle'
);

reset role;
select is(
  (
    select pg_catalog.count(*)
    from public.mt5_symbol_observations
    where specification_fingerprint =
      'mt5-spec-v1:' || pg_catalog.repeat('c', 64)
  ),
  2::bigint,
  'one fingerprint retains exactly its two distinct consecutive states'
);
insert into public.broker_symbols
select (pg_catalog.jsonb_populate_record(
  null::public.broker_symbols,
  pg_catalog.to_jsonb(binding) || pg_catalog.jsonb_build_object(
    'id', '00000000-0000-4000-8000-000000008311',
    'broker_symbol', 'GOLD',
    'specification_version', 'mt5-spec-v1:' || pg_catalog.repeat('c', 64),
    'confirmed_specification_fingerprint',
      'mt5-spec-v1:' || pg_catalog.repeat('c', 64),
    'confirmation_version', 2,
    'confirmed_at', '2026-08-28T01:30:00Z',
    'fetched_at', '2026-08-28T01:30:00Z',
    'created_at', '2026-08-28T01:30:00Z'
  )
)).*
from public.broker_symbols as binding
where binding.id = '00000000-0000-4000-8000-000000000311';

set local role aurum_worker;
select is(
  public.worker_read_mt5_reconciliation_state()
    #>> '{confirmed_symbol_binding,confirmed_specification_fingerprint}',
  'mt5-spec-v1:' || pg_catalog.repeat('c', 64),
  'only an explicit privileged confirmation version changes A to B'
);
reset role;
select is(
  (
    select pg_catalog.count(*)
    from public.broker_symbols
    where confirmation_status = 'confirmed'
  ),
  2::bigint,
  'confirmed binding history is append-versioned'
);
select is(
  (
    select pg_catalog.count(*)
    from public.audit_logs
    where action = 'mt5_symbol_binding_confirmed'
  ),
  2::bigint,
  'each explicit fictional confirmation appends one security audit row'
);
select throws_ok(
  $$insert into public.broker_symbols
    select (pg_catalog.jsonb_populate_record(
      null::public.broker_symbols,
      pg_catalog.to_jsonb(binding) || pg_catalog.jsonb_build_object(
        'id', '00000000-0000-4000-8000-000000008312',
        'base_currency', 'EUR',
        'specification_version', 'mt5-spec-v1:wrong-base',
        'confirmed_specification_fingerprint', 'mt5-spec-v1:wrong-base',
        'confirmation_version', 3
      )
    )).* from public.broker_symbols as binding
    where binding.id = '00000000-0000-4000-8000-000000000311'$$,
  '23514',
  'new row for relation "broker_symbols" violates check constraint "broker_symbols_confirmation_state_check"',
  'confirmed binding cannot mislabel a non-XAU base as XAUUSD'
);
select throws_ok(
  $$update public.broker_symbols set broker_symbol = 'tampered'
    where id = '00000000-0000-4000-8000-000000008311'$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'confirmed binding versions are append-only'
);

set local role aurum_worker;
select is(
  public.worker_begin_reconciliation(
    (select empty_report from m2_patch_payloads)
  ),
  'RECONCILIATION_STARTED',
  'empty bounded histories begin a reconciliation'
);
select is(
  public.worker_begin_reconciliation(
    (select empty_report from m2_patch_payloads)
  ),
  'IDEMPOTENT_REPLAY',
  'begin replay includes the exact current history evidence'
);
select is(
  public.worker_complete_reconciliation(
    (select empty_report from m2_patch_payloads)
  ),
  'RECONCILIATION_COMPLETED',
  'two valid empty results can complete a matched reconciliation'
);
select is(
  public.worker_complete_reconciliation(
    (select empty_report from m2_patch_payloads)
  ),
  'IDEMPOTENT_REPLAY',
  'completed history evidence replay is idempotent'
);
select is(
  public.worker_record_reconciliation_mismatch(
    '00000000-0000-4000-8000-000000008301',
    pg_catalog.jsonb_build_object(
      'category', 'SYMBOL_SPEC_CHANGED',
      'severity', 'critical',
      'resource_type', 'symbol_specification',
      'resource_reference', 'mt5-spec-v1:late-change',
      'reason_code', 'SYMBOL_SPEC_CHANGED'
    )
  ),
  'INVALID_RECONCILIATION_MISMATCH',
  'completed reconciliation rejects newly appended mismatch evidence'
);
reset role;
select is(
  (
    select broker_symbol
    from public.mt5_reconciliation_runs
    where id = '00000000-0000-4000-8000-000000008301'
  ),
  'GOLD',
  'completed matched reconciliation retains the observed broker symbol'
);
select is(
  (
    select pg_catalog.count(*)
    from public.mt5_history_query_evidence
    where reconciliation_id = '00000000-0000-4000-8000-000000008301'
  ),
  2::bigint,
  'completion atomically persists exactly orders and deals evidence'
);
select results_eq(
  $$select history_kind, result_state, returned_count
    from public.mt5_history_query_evidence
    where reconciliation_id = '00000000-0000-4000-8000-000000008301'
    order by history_kind$$,
  $$values
    ('deals', 'empty_valid_result', 0),
    ('orders', 'empty_valid_result', 0)$$,
  'valid empty native tuples remain distinct successful empty evidence'
);
select results_eq(
  $$select requested_start_at, requested_end_at
    from public.mt5_history_query_evidence
    where reconciliation_id = '00000000-0000-4000-8000-000000008301'
      and history_kind = 'orders'$$,
  $$values (
    '2026-08-27T02:00:00Z'::timestamptz,
    '2026-08-28T02:00:00Z'::timestamptz
  )$$,
  'the current report preserves actual bounded request boundaries'
);
select throws_ok(
  $$update public.mt5_history_query_evidence
    set reason_code = 'TAMPERED'$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'history query evidence is append-only'
);

set local role aurum_worker;
select is(
  public.worker_begin_reconciliation(
    (select failed_report from m2_patch_payloads)
  ),
  'RECONCILIATION_STARTED',
  'a current query failure begins a fail-closed evidence report'
);
select is(
  public.worker_complete_reconciliation(
    (select failed_report from m2_patch_payloads)
  ),
  'RECONCILIATION_COMPLETED',
  'a current query failure is persisted as incomplete reconciliation'
);
reset role;
select results_eq(
  $$select history_kind, result_state
    from public.mt5_history_query_evidence
    where reconciliation_id = '00000000-0000-4000-8000-000000008302'
    order by history_kind$$,
  $$values
    ('deals', 'empty_valid_result'),
    ('orders', 'query_failed')$$,
  'orders and deals preserve their independent current query results'
);
select results_eq(
  $$select outcome, reason_code
    from public.mt5_reconciliation_runs
    where id = '00000000-0000-4000-8000-000000008302'$$,
  $$values ('incomplete', 'HISTORY_QUERY_FAILED')$$,
  'current query failure cannot be stored as Healthy'
);

set local role aurum_worker;
select is(
  public.worker_begin_reconciliation(
    (select invalid_matched_report from m2_patch_payloads)
  ),
  'RECONCILIATION_STARTED',
  'invalid matched report is durably identified before completion validation'
);
select is(
  public.worker_complete_reconciliation(
    (select invalid_matched_report from m2_patch_payloads)
  ),
  'INVALID_RECONCILIATION',
  'matched outcome is rejected when either current query failed'
);
reset role;
select is(
  (
    select pg_catalog.count(*)
    from public.mt5_history_query_evidence
    where reconciliation_id = '00000000-0000-4000-8000-000000008303'
  ),
  0::bigint,
  'rejected matched report leaves no partial history evidence'
);

set local role aurum_worker;
select is(
  public.worker_begin_reconciliation(
    (select invalid_matched_claim from m2_patch_payloads)
  ),
  'RECONCILIATION_STARTED',
  'malformed matched claim is durably identified before completion validation'
);
select is(
  public.worker_complete_reconciliation(
    (select invalid_matched_claim from m2_patch_payloads)
  ),
  'INVALID_RECONCILIATION',
  'matched outcome rejects non-Healthy reason or payload mismatches'
);
select is(
  public.worker_begin_reconciliation(
    (select invalid_matched_context from m2_patch_payloads)
  ),
  'RECONCILIATION_STARTED',
  'matched claim with missing identity reaches completion validation'
);
select is(
  public.worker_complete_reconciliation(
    (select invalid_matched_context from m2_patch_payloads)
  ),
  'INVALID_RECONCILIATION',
  'matched outcome requires account, server, broker, and specification identity'
);
select is(
  public.worker_begin_reconciliation(
    (select matched_child_report from m2_patch_payloads)
  ),
  'RECONCILIATION_STARTED',
  'matched report begins before a persisted child mismatch is injected'
);
select is(
  public.worker_record_reconciliation_mismatch(
    '00000000-0000-4000-8000-000000008306',
    pg_catalog.jsonb_build_object(
      'category', 'SYMBOL_SPEC_CHANGED',
      'severity', 'critical',
      'resource_type', 'symbol_specification',
      'resource_reference', 'mt5-spec-v1:injected',
      'reason_code', 'SYMBOL_SPEC_CHANGED'
    )
  ),
  'MISMATCH_RECORDED',
  'running reconciliation accepts owner-scoped mismatch evidence under lock'
);
select is(
  public.worker_complete_reconciliation(
    (select matched_child_report from m2_patch_payloads)
  ),
  'INVALID_RECONCILIATION',
  'persisted child mismatch prevents a false matched completion'
);
select is(
  public.worker_begin_reconciliation(
    (select substituted_mismatch_report from m2_patch_payloads)
  ),
  'RECONCILIATION_STARTED',
  'mismatch report begins before substituted child evidence is recorded'
);
select is(
  public.worker_record_reconciliation_mismatch(
    '00000000-0000-4000-8000-000000008307',
    pg_catalog.jsonb_build_object(
      'category', 'SYMBOL_SPEC_CHANGED',
      'severity', 'critical',
      'resource_type', 'symbol_specification',
      'resource_reference', 'mt5-spec-v1:substituted',
      'reason_code', 'SYMBOL_SPEC_CHANGED'
    )
  ),
  'MISMATCH_RECORDED',
  'different same-count child evidence is persisted for substitution regression'
);
select is(
  public.worker_complete_reconciliation(
    (select substituted_mismatch_report from m2_patch_payloads)
  ),
  'INVALID_RECONCILIATION',
  'same-count substituted mismatch set cannot complete'
);
reset role;
select is(
  (
    select pg_catalog.count(*)
    from public.mt5_history_query_evidence
    where reconciliation_id in (
      '00000000-0000-4000-8000-000000008304',
      '00000000-0000-4000-8000-000000008305',
      '00000000-0000-4000-8000-000000008306',
      '00000000-0000-4000-8000-000000008307'
    )
  ),
  0::bigint,
  'rejected reconciliation claims leave no partial history evidence'
);
select ok(
  pg_catalog.pg_get_functiondef(
    'public.worker_record_reconciliation_mismatch(uuid,jsonb)'::regprocedure
  ) like '%for update%'
  and pg_catalog.pg_get_functiondef(
    'public.worker_complete_reconciliation(jsonb)'::regprocedure
  ) like '%for update%',
  'parent-row locks serialize mismatch append and reconciliation completion'
);
select ok(
  pg_catalog.pg_get_functiondef(
    'public.worker_upsert_mt5_latest_tick(jsonb)'::regprocedure
  ) not like '%append_audit%',
  'routine latest-tick telemetry does not append security audit rows'
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
  (select pg_catalog.count(*) from public.mt5_history_query_evidence),
  4::bigint,
  'owner can read own current-run history evidence'
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
  (select pg_catalog.count(*) from public.mt5_history_query_evidence),
  0::bigint,
  'another owner cannot read history evidence'
);
select throws_ok(
  $$insert into public.mt5_history_query_evidence (
      owner_id, reconciliation_id, history_kind, requested_start_at,
      requested_end_at, query_completed_at, returned_count,
      result_state, reason_code
    ) values (
      '00000000-0000-4000-8000-000000000202',
      '00000000-0000-4000-8000-000000008302', 'orders',
      clock_timestamp() - interval '1 hour', clock_timestamp(),
      clock_timestamp(), 0, 'empty_valid_result', 'HISTORY_EMPTY_VALID_RESULT'
    )$$,
  '42501', 'permission denied for table mt5_history_query_evidence',
  'browser cannot write history evidence'
);

reset role;
set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-m2-patch"}',
  true
);
select throws_ok(
  $$insert into public.mt5_history_query_evidence (
      owner_id, reconciliation_id, history_kind, requested_start_at,
      requested_end_at, query_completed_at, returned_count,
      result_state, reason_code
    ) values (
      '00000000-0000-4000-8000-000000000201',
      '00000000-0000-4000-8000-000000008302', 'orders',
      clock_timestamp() - interval '1 hour', clock_timestamp(),
      clock_timestamp(), 0, 'empty_valid_result', 'HISTORY_EMPTY_VALID_RESULT'
    )$$,
  '42501', 'permission denied for table mt5_history_query_evidence',
  'Worker cannot bypass secured reconciliation RPCs with direct DML'
);

reset role;
select ok(
  has_table_privilege(
    'aurum_function_owner', 'public.mt5_history_query_evidence', 'select'
  )
  and has_table_privilege(
    'aurum_function_owner', 'public.mt5_history_query_evidence', 'insert'
  )
  and not has_table_privilege(
    'aurum_function_owner', 'public.mt5_history_query_evidence', 'update'
  ),
  'function owner has only exact history read/append privileges'
);
select ok(
  not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and procedure.proname ~ '(confirm|bind).*(symbol|specification)'
  ),
  'patch exposes no production symbol-confirmation action'
);

select * from finish();
rollback;
