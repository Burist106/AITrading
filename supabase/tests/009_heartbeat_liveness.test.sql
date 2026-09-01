begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to aurum_worker;
grant execute on all functions in schema extensions to aurum_worker;
set local search_path = public, extensions;

select plan(34);

select has_function(
  'public',
  'worker_record_heartbeat',
  array['text', 'system_health_state', 'text', 'timestamp with time zone', 'integer'],
  'bounded component-heartbeat RPC exists with the published signature'
);
select ok(
  has_function_privilege(
    'aurum_worker',
    'public.worker_record_heartbeat(text,public.system_health_state,text,timestamptz,integer)',
    'execute'
  )
  and not has_function_privilege(
    'authenticated',
    'public.worker_record_heartbeat(text,public.system_health_state,text,timestamptz,integer)',
    'execute'
  )
  and not has_function_privilege(
    'anon',
    'public.worker_record_heartbeat(text,public.system_health_state,text,timestamptz,integer)',
    'execute'
  ),
  'only the dedicated Worker role can execute the heartbeat RPC'
);
select ok(
  not has_table_privilege('aurum_worker', 'public.system_heartbeats', 'insert')
  and not has_table_privilege('aurum_worker', 'public.system_heartbeats', 'update')
  and not has_table_privilege('authenticated', 'public.system_heartbeats', 'insert')
  and not has_table_privilege('authenticated', 'public.system_heartbeats', 'update'),
  'Worker and browser roles receive no direct heartbeat DML'
);
select is(
  (
    select pg_catalog.count(*)
    from pg_catalog.pg_class as relation
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname in ('system_components', 'system_heartbeats')
      and relation.relrowsecurity
      and relation.relforcerowsecurity
  ),
  2::bigint,
  'component and heartbeat tables keep forced RLS'
);
select results_eq(
  $$select code, label_th, expected_heartbeat_seconds, enabled
    from public.system_components
    where plane = 'execution_plane' and enabled
    order by code$$,
  $$values
    ('execution.market_data', 'ข้อมูลตลาด XAU/USD', 15, true),
    ('execution.mt5_adapter', 'การเชื่อมต่อ MT5', 15, true),
    ('execution.worker', 'Aurum Worker', 15, true)$$,
  'the exact three enabled execution components have producers and a 15-second expectation'
);
select ok(
  (
    select procedure.prosecdef
      and pg_catalog.pg_get_userbyid(procedure.proowner) = 'aurum_function_owner'
      and exists (
        select 1
        from pg_catalog.unnest(procedure.proconfig) as setting(value)
        where setting.value in ('search_path=""', 'search_path=')
      )
    from pg_catalog.pg_proc as procedure
    where procedure.oid =
      'public.worker_record_heartbeat(text,public.system_health_state,text,timestamptz,integer)'::regprocedure
  ),
  'heartbeat RPC remains SECURITY DEFINER under the NOLOGIN owner with an empty search path'
);
select ok(
  pg_catalog.pg_get_functiondef(
    'public.worker_record_heartbeat(text,public.system_health_state,text,timestamptz,integer)'::regprocedure
  ) not like '%append_audit%',
  'routine heartbeat telemetry has no security-audit append path'
);

create temporary table heartbeat_liveness_baseline on commit drop as
select pg_catalog.count(*) as audit_count from public.audit_logs;

set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"heartbeat-worker"}',
  true
);

select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'HEALTHY', pg_catalog.clock_timestamp()
  ),
  'HEARTBEAT_RECORDED',
  'Worker heartbeat uses the valid 30-second default TTL'
);
select is(
  public.worker_record_heartbeat(
    'execution.mt5_adapter', 'degraded', 'DEMO_ACCOUNT_UNBOUND',
    pg_catalog.clock_timestamp(), 15
  ),
  'HEARTBEAT_RECORDED',
  'MT5-adapter heartbeat accepts the minimum bounded TTL'
);
select is(
  public.worker_record_heartbeat(
    'execution.market_data', 'degraded', 'TICK_DELAYED',
    pg_catalog.clock_timestamp(), 300
  ),
  'HEARTBEAT_RECORDED',
  'market-data heartbeat accepts its exact degraded reason and maximum TTL'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'degraded', 'Worker remains safe.',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'arbitrary safe prose cannot enter the strict heartbeat reason-code field'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'failed', 'ARBITRARY_FAILURE',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'an uppercase identifier outside Mt5ReasonCode is rejected'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'failed', 'RECONCILIATION_REQUIRED',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'a Web-derived console reason cannot cross the producer boundary'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'RECONCILIATION_INCOMPLETE',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'healthy state requires the exact HEALTHY reason'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'degraded', 'HEALTHY',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'degraded state rejects the HEALTHY reason'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'failed', 'HEALTHY',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'failed state rejects the HEALTHY reason'
);
select is(
  public.worker_record_heartbeat(
    'execution.market_data', 'degraded', 'RECONCILIATION_INCOMPLETE',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'degraded market data requires the exact TICK_DELAYED reason'
);
select is(
  public.worker_record_heartbeat(
    'execution.market_data', 'failed', 'REAL_ACCOUNT_BLOCKED',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'market-data failure rejects an account or adapter reason'
);
select is(
  public.worker_record_heartbeat(
    'execution.strategy', 'healthy', 'HEALTHY',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'an arbitrary execution component is rejected'
);
select is(
  public.worker_record_heartbeat(
    ' execution.worker ', 'healthy', 'HEALTHY',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'component codes are exact and whitespace aliases are rejected'
);
select is(
  public.worker_record_heartbeat(
    'control.database', 'healthy', 'HEALTHY',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'control-plane components cannot enter the Worker heartbeat path'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'unknown', 'TICK_UNAVAILABLE',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'unknown remains a derived browser state and cannot be producer-reported'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'warning', 'TICK_DELAYED',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT',
  'legacy warning state cannot be producer-reported'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'HEALTHY',
    pg_catalog.clock_timestamp(), 14
  ),
  'INVALID_HEARTBEAT',
  'heartbeat TTL below 15 seconds is rejected'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'HEALTHY',
    pg_catalog.clock_timestamp(), 301
  ),
  'INVALID_HEARTBEAT',
  'heartbeat TTL above 300 seconds is rejected'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'HEALTHY',
    pg_catalog.clock_timestamp() + interval '2 minutes', 30
  ),
  'INVALID_HEARTBEAT',
  'future heartbeat observations remain fail-closed'
);
select is(
  (
    select pg_catalog.count(*)
    from (
      select public.worker_record_heartbeat(
        component.component_code,
        component.heartbeat_state,
        component.heartbeat_detail,
        pg_catalog.clock_timestamp(),
        30
      ) as result_code
      from pg_catalog.generate_series(1, 20) as renewal(sequence)
      cross join (
        values
          ('execution.worker', 'healthy'::public.system_health_state, 'HEALTHY'),
          (
            'execution.mt5_adapter', 'degraded'::public.system_health_state,
            'DEMO_ACCOUNT_UNBOUND'
          ),
          (
            'execution.market_data', 'failed'::public.system_health_state,
            'TICK_UNAVAILABLE'
          )
      ) as component(component_code, heartbeat_state, heartbeat_detail)
    ) as renewal_result
    where renewal_result.result_code = 'HEARTBEAT_RECORDED'
  ),
  60::bigint,
  'many lightweight renewals succeed for all three component producers'
);

reset role;
select results_eq(
  $$select count(*), min(version), max(version)
    from public.system_heartbeats
    where worker_id = 'heartbeat-worker'$$,
  $$values (3::bigint, 21, 21)$$,
  'many renewals retain exactly three bounded rows with monotonic versions'
);
select results_eq(
  $$select component.code, heartbeat.state::text, heartbeat.detail
    from public.system_heartbeats as heartbeat
    join public.system_components as component
      on component.id = heartbeat.system_component_id
      and component.owner_id = heartbeat.owner_id
    where heartbeat.worker_id = 'heartbeat-worker'
    order by component.code$$,
  $$values
    ('execution.market_data', 'failed', 'TICK_UNAVAILABLE'),
    ('execution.mt5_adapter', 'degraded', 'DEMO_ACCOUNT_UNBOUND'),
    ('execution.worker', 'healthy', 'HEALTHY')$$,
  'each bounded row retains its explicit component-specific state and detail'
);
select ok(
  not exists (
    select 1
    from public.system_heartbeats
    where worker_id = 'heartbeat-worker'
      and extract(epoch from expires_at - observed_at) <> 30
  ),
  'renewed heartbeat expiries use the caller-provided 30-second TTL'
);
select is(
  (select pg_catalog.count(*) from public.audit_logs),
  (select audit_count from heartbeat_liveness_baseline),
  'many routine heartbeat renewals do not grow the audit log'
);
select is(
  (
    select pg_catalog.count(*)
    from public.audit_logs
    where action in ('heartbeat_recorded', 'heartbeat_updated')
  ),
  0::bigint,
  'no routine heartbeat audit action is recorded'
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
  (select pg_catalog.count(*) from public.system_heartbeats),
  3::bigint,
  'authenticated owner can read the three current component heartbeats'
);
select pg_catalog.set_config(
  'request.jwt.claim.sub', '00000000-0000-4000-8000-000000009201', true
);
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"authenticated","sub":"00000000-0000-4000-8000-000000009201"}',
  true
);
select is(
  (select pg_catalog.count(*) from public.system_heartbeats),
  0::bigint,
  'heartbeat RLS hides another owner current state'
);

reset role;
select * from finish();
rollback;
