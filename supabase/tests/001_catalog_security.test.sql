begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(44);

select is(
  (
    select pg_catalog.count(*)::integer
    from pg_catalog.pg_class as relation
    join pg_catalog.pg_namespace as namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname = any (array[
        'profiles', 'trading_accounts', 'broker_symbols', 'trading_modes',
        'risk_policies', 'risk_policy_versions', 'market_snapshots',
        'feature_snapshots', 'trade_proposals', 'risk_checks',
        'trade_decisions', 'system_commands', 'system_command_events',
        'broker_orders', 'trade_executions', 'positions', 'position_events',
        'system_components', 'system_heartbeats', 'system_incidents',
        'audit_logs', 'mt5_account_observations', 'mt5_symbol_observations',
        'mt5_latest_tick_observations', 'mt5_reconciliation_runs',
        'mt5_reconciliation_mismatches'
      ])
      and relation.relrowsecurity
      and relation.relforcerowsecurity
  ),
  26,
  'every application table has RLS enabled and forced'
);

select ok(
  exists (
    select 1 from pg_catalog.pg_roles
    where rolname = 'aurum_worker' and not rolcanlogin and not rolbypassrls
  ),
  'Worker role is NOLOGIN and cannot bypass RLS'
);

select ok(
  exists (
    select 1 from pg_catalog.pg_roles
    where rolname = 'aurum_function_owner' and not rolcanlogin and not rolbypassrls
  ),
  'secured-function owner is NOLOGIN and cannot bypass RLS'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from information_schema.table_privileges
    where grantee = 'anon'
      and table_schema = 'public'
      and table_name = any (array[
        'profiles', 'trading_accounts', 'broker_symbols', 'trading_modes',
        'risk_policies', 'risk_policy_versions', 'market_snapshots',
        'feature_snapshots', 'trade_proposals', 'risk_checks',
        'trade_decisions', 'system_commands', 'system_command_events',
        'broker_orders', 'trade_executions', 'positions', 'position_events',
        'system_components', 'system_heartbeats', 'system_incidents', 'audit_logs',
        'mt5_account_observations', 'mt5_symbol_observations',
        'mt5_latest_tick_observations', 'mt5_reconciliation_runs',
        'mt5_reconciliation_mismatches'
      ])
  ),
  0,
  'anonymous role has no application-table privileges'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from information_schema.table_privileges
    where grantee = 'authenticated'
      and table_schema = 'public'
      and table_name <> 'profiles'
      and privilege_type in ('INSERT', 'UPDATE', 'DELETE')
      and table_name = any (array[
        'trading_accounts', 'broker_symbols', 'trading_modes', 'risk_policies',
        'risk_policy_versions', 'market_snapshots', 'feature_snapshots',
        'trade_proposals', 'risk_checks', 'trade_decisions', 'system_commands',
        'system_command_events', 'broker_orders', 'trade_executions',
        'positions', 'position_events', 'system_components',
        'system_heartbeats', 'system_incidents', 'audit_logs',
        'mt5_account_observations', 'mt5_symbol_observations',
        'mt5_latest_tick_observations', 'mt5_reconciliation_runs',
        'mt5_reconciliation_mismatches'
      ])
  ),
  0,
  'authenticated browser has no operational-table DML grant'
);

select ok(
  not pg_catalog.has_table_privilege('authenticated', 'public.system_commands', 'SELECT'),
  'browser cannot select the base command table containing lease tokens'
);

select ok(
  pg_catalog.has_table_privilege(
    'authenticated', 'public.system_command_read_models', 'SELECT'
  ),
  'browser can read the safe command progress view'
);

select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public'
      and table_name = 'system_command_read_models'
      and column_name = 'lease_token'
  ),
  'safe command progress view omits lease_token'
);

select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public'
      and table_name = 'system_command_read_models'
      and column_name = 'last_error'
  ),
  'safe command progress view omits unfiltered Worker error text'
);

select ok(
  not pg_catalog.has_column_privilege(
    'authenticated', 'public.system_commands', 'lease_token', 'SELECT'
  ) and not pg_catalog.has_column_privilege(
    'authenticated', 'public.system_commands', 'last_error', 'SELECT'
  ) and not pg_catalog.has_column_privilege(
    'authenticated', 'public.system_commands', 'payload', 'SELECT'
  ),
  'browser has no base-column read grant for command secrets or raw payload'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from information_schema.table_privileges
    where grantee = 'aurum_worker'
      and table_schema = 'public'
      and privilege_type in ('INSERT', 'UPDATE', 'DELETE')
  ),
  0,
  'Worker has no direct table DML grants'
);

select ok(
  pg_catalog.has_table_privilege('aurum_worker', 'public.system_commands', 'SELECT'),
  'Worker can read owner-scoped command rows under RLS'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname in ('public', 'private')
      and procedure.prosecdef
      and pg_catalog.has_function_privilege(
        'public', procedure.oid, 'EXECUTE'
      )
  ),
  0,
  'PUBLIC cannot execute any Aurum SECURITY DEFINER function'
);

select ok(
  not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname in ('public', 'private')
      and procedure.prosecdef
      and not exists (
        select 1 from pg_catalog.unnest(procedure.proconfig) as setting(value)
        where setting.value in ('search_path=""', 'search_path=')
      )
  ),
  'every SECURITY DEFINER function pins an empty search_path'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and procedure.proname = any (array[
        'request_proposal_approval', 'request_proposal_rejection',
        'request_pause_new_trades', 'request_resume_system',
        'request_emergency_stop', 'request_position_close',
        'request_stop_loss_change', 'request_take_profit_change',
        'request_risk_policy_change'
      ])
      and pg_catalog.has_function_privilege(
        'authenticated', procedure.oid, 'EXECUTE'
      )
  ),
  9,
  'authenticated role can execute exactly the nine user intent RPCs'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and procedure.proname like 'request_%'
      and pg_catalog.has_function_privilege('aurum_worker', procedure.oid, 'EXECUTE')
  ),
  0,
  'Worker cannot execute authenticated user intent RPCs'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and procedure.proname = any (array[
        'worker_claim_next_command', 'worker_renew_command_lease',
        'worker_mark_command_validating', 'worker_mark_command_executing',
        'worker_complete_command', 'worker_reject_command',
        'worker_fail_command', 'worker_record_heartbeat',
        'worker_record_incident',
        'worker_record_mt5_account_observation',
        'worker_record_mt5_symbol_observation',
        'worker_upsert_mt5_latest_tick',
        'worker_read_mt5_reconciliation_state',
        'worker_begin_reconciliation',
        'worker_record_reconciliation_mismatch',
        'worker_complete_reconciliation'
      ])
      and pg_catalog.has_function_privilege('aurum_worker', procedure.oid, 'EXECUTE')
  ),
  16,
  'Worker can execute exactly the sixteen least-privilege Worker RPCs'
);

select ok(
  (
    select pg_catalog.array_agg(attribute.attname::text order by attribute.attnum)
      = array[
        'accepted', 'command_id', 'status', 'lease_token',
        'lease_expires_at', 'command_version', 'result_code'
      ]::text[]
      and pg_catalog.array_agg(attribute.atttypid order by attribute.attnum)
      = array[
        'boolean'::regtype::oid, 'uuid'::regtype::oid,
        'public.system_command_status'::regtype::oid, 'uuid'::regtype::oid,
        'timestamptz'::regtype::oid, 'integer'::regtype::oid, 'text'::regtype::oid
      ]
    from pg_catalog.pg_attribute as attribute
    where attribute.attrelid = (
      select type_row.typrelid
      from pg_catalog.pg_type as type_row
      where type_row.oid = 'public.worker_claim_result'::regtype
    )
      and attribute.attnum > 0
      and not attribute.attisdropped
  ),
  'Worker claim envelope exposes only claim identifiers, lease state, version, and safe code'
);

select ok(
  (
    select pg_catalog.array_agg(attribute.attname::text order by attribute.attnum)
      = array['accepted', 'incident_id', 'created', 'result_code']::text[]
      and pg_catalog.array_agg(attribute.atttypid order by attribute.attnum)
      = array[
        'boolean'::regtype::oid, 'uuid'::regtype::oid,
        'boolean'::regtype::oid, 'text'::regtype::oid
      ]
    from pg_catalog.pg_attribute as attribute
    where attribute.attrelid = (
      select type_row.typrelid
      from pg_catalog.pg_type as type_row
      where type_row.oid = 'public.worker_incident_result'::regtype
    )
      and attribute.attnum > 0
      and not attribute.attisdropped
  ),
  'Worker incident envelope exposes only acceptance, identity, replay state, and safe code'
);

select ok(
  (
    select procedure.prorettype = 'public.worker_claim_result'::regtype
      and not procedure.proretset
    from pg_catalog.pg_proc as procedure
    where procedure.oid = 'public.worker_claim_next_command(integer)'::regprocedure
  ) and (
    select procedure.prorettype = 'public.worker_incident_result'::regtype
      and not procedure.proretset
    from pg_catalog.pg_proc as procedure
    where procedure.oid = 'public.worker_record_incident(text,public.incident_severity,text,text,timestamptz,uuid)'::regprocedure
  ),
  'claim and incident RPCs return one deterministic typed envelope per call'
);

select ok(
  pg_catalog.has_type_privilege('aurum_worker', 'public.worker_claim_result', 'USAGE')
  and pg_catalog.has_type_privilege('aurum_worker', 'public.worker_incident_result', 'USAGE')
  and pg_catalog.has_type_privilege('aurum_function_owner', 'public.worker_claim_result', 'USAGE')
  and pg_catalog.has_type_privilege('aurum_function_owner', 'public.worker_incident_result', 'USAGE')
  and not exists (
    select 1
    from pg_catalog.pg_type as type_row
    cross join lateral pg_catalog.aclexplode(
      coalesce(
        type_row.typacl,
        pg_catalog.acldefault('T', type_row.typowner)
      )
    ) as type_acl
    where type_row.oid in (
      'public.worker_claim_result'::regtype,
      'public.worker_incident_result'::regtype
    )
      and type_acl.grantee = 0
      and type_acl.privilege_type = 'USAGE'
  )
  and not pg_catalog.has_type_privilege('anon', 'public.worker_claim_result', 'USAGE')
  and not pg_catalog.has_type_privilege('anon', 'public.worker_incident_result', 'USAGE')
  and not pg_catalog.has_type_privilege('authenticated', 'public.worker_claim_result', 'USAGE')
  and not pg_catalog.has_type_privilege('authenticated', 'public.worker_incident_result', 'USAGE'),
  'among application roles, typed envelopes are usable only by the Worker and secured owner'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and (procedure.proname like 'request_%' or procedure.proname like 'worker_%')
      and pg_catalog.has_function_privilege('anon', procedure.oid, 'EXECUTE')
  ),
  0,
  'anonymous role cannot execute secured actions'
);

select ok(
  not exists (
    select 1
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'public'
      and procedure.proname ~ '(broker|order|position).*(write|insert|update|mutate|execute|send)'
  ),
  'no broker, order, execution, or Position write RPC exists'
);

select set_eq(
  $$select enumlabel::text from pg_catalog.pg_enum
    where enumtypid = 'public.system_command_type'::regtype$$,
  $$values
    ('APPROVE_PROPOSAL'), ('REJECT_PROPOSAL'), ('PAUSE_NEW_TRADES'),
    ('RESUME_SYSTEM'), ('ACTIVATE_EMERGENCY_STOP'),
    ('REQUEST_POSITION_CLOSE'), ('REQUEST_STOP_LOSS_CHANGE'),
    ('REQUEST_TAKE_PROFIT_CHANGE'), ('REQUEST_RISK_POLICY_CHANGE')$$,
  'database command type set matches the shared contract'
);

select set_eq(
  $$select enumlabel::text from pg_catalog.pg_enum
    where enumtypid = 'public.system_command_status'::regtype$$,
  $$values ('pending'), ('claimed'), ('validating'), ('executing'),
    ('succeeded'), ('rejected'), ('failed'), ('expired'), ('cancelled')$$,
  'database command status set matches the shared contract'
);

select set_eq(
  $$select enumlabel::text from pg_catalog.pg_enum
    where enumtypid = 'public.risk_check_state'::regtype$$,
  $$values ('pass'), ('warn'), ('fail'), ('na')$$,
  'risk-check state set matches the risk-check contract'
);

select ok(
  exists (
    select 1 from pg_catalog.pg_class
    where oid = 'public.system_command_read_models'::regclass
      and reloptions @> array['security_invoker=true']
  ),
  'safe command view is SECURITY INVOKER'
);

select ok(
  pg_catalog.pg_has_role('authenticator', 'aurum_worker', 'MEMBER'),
  'PostgREST authenticator can assume only an explicitly claimed Worker role'
);

select ok(
  not pg_catalog.has_schema_privilege('authenticated', 'private', 'USAGE'),
  'authenticated browser cannot use the private helper schema'
);

select set_eq(
  $$select procedure.proname::text
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'private'
      and pg_catalog.has_function_privilege('aurum_worker', procedure.oid, 'EXECUTE')$$,
  $$values ('worker_owner_id')$$,
  'Worker can execute only the owner-claim helper required by its RLS policies'
);

select ok(
  pg_catalog.has_function_privilege(
    'postgres', 'private.numeric_is_finite(numeric)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'public', 'private.numeric_is_finite(numeric)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'anon', 'private.numeric_is_finite(numeric)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated', 'private.numeric_is_finite(numeric)', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'aurum_worker', 'private.numeric_is_finite(numeric)', 'EXECUTE'
  ),
  'only the migration/seed actor and secured function owner can evaluate the finite-number helper'
);

select ok(
  not pg_catalog.has_schema_privilege('aurum_function_owner', 'auth', 'USAGE'),
  'secured-function owner reads request-local claims without auth-schema access'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from information_schema.column_privileges
    where grantee = 'authenticated'
      and table_schema = 'public'
      and table_name = 'profiles'
      and privilege_type = 'UPDATE'
  ),
  3,
  'browser profile update grant is limited to three safe columns'
);

select ok(
  not pg_catalog.has_table_privilege('aurum_worker', 'public.audit_logs', 'SELECT'),
  'Worker cannot browse owner audit history directly'
);

select ok(
  not pg_catalog.has_table_privilege('aurum_worker', 'public.profiles', 'SELECT'),
  'Worker cannot browse owner profile data'
);

select ok(
  not pg_catalog.has_schema_privilege('aurum_function_owner', 'public', 'CREATE'),
  'secured-function owner loses temporary public-schema CREATE after migrations'
);

select ok(
  not pg_catalog.has_schema_privilege('aurum_function_owner', 'private', 'CREATE'),
  'secured-function owner loses temporary private-schema CREATE after migrations'
);

select ok(
  not exists (
    select 1
    from information_schema.routine_privileges
    where grantee = 'authenticated'
      and routine_schema = 'public'
      and routine_name like 'worker_%'
      and privilege_type = 'EXECUTE'
  ),
  'authenticated browser cannot execute Worker RPCs'
);

select ok(
  exists (
    select 1 from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace on namespace.oid = procedure.pronamespace
    where namespace.nspname = 'private'
      and procedure.proname = 'validate_system_command_row'
      and procedure.prosecdef
  ),
  'command payload trigger validator exists behind the private boundary'
);

select set_eq(
  $$select table_name::text
    from information_schema.table_privileges
    where grantee = 'aurum_function_owner'
      and table_schema = 'public'
      and privilege_type = 'SELECT'$$,
  $$values
    ('risk_policies'), ('risk_policy_versions'), ('trade_proposals'),
    ('trade_decisions'), ('system_commands'), ('system_command_events'),
    ('positions'), ('system_components'), ('system_heartbeats'),
    ('system_incidents'), ('broker_orders'),
    ('mt5_account_observations'), ('mt5_symbol_observations'),
    ('mt5_latest_tick_observations'), ('mt5_reconciliation_runs'),
    ('mt5_reconciliation_mismatches')$$,
  'secured function owner SELECT grants match the exact RPC read set'
);

select set_eq(
  $$select table_name::text
    from information_schema.table_privileges
    where grantee = 'aurum_function_owner'
      and table_schema = 'public'
      and privilege_type = 'INSERT'$$,
  $$values
    ('risk_policy_versions'), ('trade_decisions'), ('system_commands'),
    ('system_command_events'), ('system_heartbeats'), ('system_incidents'),
    ('audit_logs'), ('mt5_account_observations'),
    ('mt5_symbol_observations'), ('mt5_latest_tick_observations'),
    ('mt5_reconciliation_runs'), ('mt5_reconciliation_mismatches')$$,
  'secured function owner INSERT grants match the exact durable-write set'
);

select set_eq(
  $$select table_name::text
    from information_schema.table_privileges
    where grantee = 'aurum_function_owner'
      and table_schema = 'public'
      and privilege_type = 'UPDATE'$$,
  $$values ('risk_policies'), ('system_commands'), ('system_heartbeats'),
    ('mt5_latest_tick_observations'), ('mt5_reconciliation_runs')$$,
  'secured function owner UPDATE grants match the exact lifecycle set'
);

select is(
  (
    select pg_catalog.count(*)::integer
    from information_schema.table_privileges
    where grantee = 'aurum_function_owner'
      and table_schema = 'public'
      and privilege_type = 'DELETE'
  ),
  0,
  'secured function owner has no table DELETE grant'
);

select set_eq(
  $$select relation.relname::text || ':' || policy.polcmd::text
    from pg_catalog.pg_policy as policy
    join pg_catalog.pg_class as relation on relation.oid = policy.polrelid
    join pg_catalog.pg_namespace as namespace on namespace.oid = relation.relnamespace
    join pg_catalog.pg_roles as policy_role on policy_role.oid = any (policy.polroles)
    where namespace.nspname = 'public'
      and policy_role.rolname = 'aurum_function_owner'$$,
  $$values
    ('risk_policies:r'), ('risk_policies:w'),
    ('risk_policy_versions:r'), ('risk_policy_versions:a'),
    ('trade_proposals:r'),
    ('trade_decisions:r'), ('trade_decisions:a'),
    ('system_commands:r'), ('system_commands:a'), ('system_commands:w'),
    ('system_command_events:r'), ('system_command_events:a'),
    ('positions:r'), ('system_components:r'),
    ('system_heartbeats:r'), ('system_heartbeats:a'), ('system_heartbeats:w'),
    ('system_incidents:r'), ('system_incidents:a'),
    ('audit_logs:a'),
    ('mt5_account_observations:r'), ('mt5_account_observations:a'),
    ('mt5_symbol_observations:r'), ('mt5_symbol_observations:a'),
    ('mt5_latest_tick_observations:r'), ('mt5_latest_tick_observations:a'),
    ('mt5_latest_tick_observations:w'),
    ('mt5_reconciliation_runs:r'), ('mt5_reconciliation_runs:a'),
    ('mt5_reconciliation_runs:w'),
    ('mt5_reconciliation_mismatches:r'),
    ('mt5_reconciliation_mismatches:a'), ('broker_orders:r')$$,
  'function-owner RLS policies expose only the exact operation matrix'
);

select * from finish();
rollback;
