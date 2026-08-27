begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(14);

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
  (public.request_pause_new_trades('immutability-fixture', 'audit-fixture')).result_code,
  'CREATED', 'fixture intent creates command, event, and audit truth'
);
select throws_ok($$update public.audit_logs set action = 'tampered'$$, '42501');
select throws_ok($$delete from public.audit_logs$$, '42501');

reset role;

select throws_ok(
  $$update public.audit_logs set action = 'tampered'
    where request_id = (
      select id from public.system_commands where idempotency_key = 'immutability-fixture'
    )$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'audit rows remain append-only even for an internal table mutation'
);
select throws_ok(
  $$delete from public.audit_logs where request_id = (
      select id from public.system_commands where idempotency_key = 'immutability-fixture'
    )$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'audit rows cannot be deleted'
);
select throws_ok(
  $$update public.system_command_events set message = 'tampered'
    where system_command_id = (
      select id from public.system_commands where idempotency_key = 'immutability-fixture'
    )$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'command event history cannot be rewritten'
);
select throws_ok(
  $$delete from public.system_command_events where system_command_id = (
      select id from public.system_commands where idempotency_key = 'immutability-fixture'
    )$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'command event history cannot be deleted'
);
select throws_ok(
  $$update public.risk_policy_versions set reason = 'tampered'
    where id = '00000000-0000-4000-8000-000000000332'$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'risk policy snapshots are immutable'
);
select throws_ok(
  $$delete from public.risk_policy_versions
    where id = '00000000-0000-4000-8000-000000000332'$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'risk policy snapshots cannot be deleted'
);
select throws_ok(
  $$update public.broker_symbols set broker_symbol = 'tampered'
    where id = '00000000-0000-4000-8000-000000000311'$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'broker specification snapshots are immutable'
);
select throws_ok(
  $$delete from public.broker_symbols
    where id = '00000000-0000-4000-8000-000000000311'$$,
  '55000', 'AURUM_APPEND_ONLY_RECORD',
  'broker specification snapshots cannot be deleted'
);
select throws_ok(
  $$update public.system_commands set payload = '{"reason":"tampered"}'
    where idempotency_key = 'immutability-fixture'$$,
  '55000', 'AURUM_COMMAND_IDENTITY_IMMUTABLE',
  'durable command identity and payload cannot be rewritten'
);
select throws_ok(
  $$update public.system_commands
    set id = '00000000-0000-4000-8000-000000009999'
    where idempotency_key = 'immutability-fixture'$$,
  '55000', 'AURUM_COMMAND_IDENTITY_IMMUTABLE',
  'durable command ID cannot be rewritten'
);

insert into public.system_commands (
  owner_id, type, payload, status, requested_by, idempotency_key,
  expires_at, completed_at, result_code
) values (
  '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
  'succeeded', '00000000-0000-4000-8000-000000000201',
  'terminal-immutability-fixture', pg_catalog.clock_timestamp() + interval '5 minutes',
  pg_catalog.clock_timestamp(), 'COMPLETED'
);
select throws_ok(
  $$update public.system_commands set result_message = 'tampered'
    where idempotency_key = 'terminal-immutability-fixture'$$,
  '55000', 'AURUM_COMMAND_TERMINAL',
  'terminal command result is immutable after completion'
);

select * from finish();
rollback;
