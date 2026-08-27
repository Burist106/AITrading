begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to aurum_worker;
grant execute on all functions in schema extensions to aurum_worker;
set local search_path = public, extensions;

select plan(20);

insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, created_at, updated_at,
  confirmation_token, email_change, email_change_token_new, recovery_token
) values (
  '00000000-0000-0000-0000-000000000000',
  '00000000-0000-4000-8000-000000008201', 'authenticated', 'authenticated',
  'rls-owner-two@aurum.invalid', null, clock_timestamp(), clock_timestamp(),
  '', '', '', ''
);
insert into public.profiles (id, display_name)
values ('00000000-0000-4000-8000-000000008201', 'RLS Owner Two');
insert into public.trading_accounts (
  id, owner_id, broker_account_reference, broker_server
) values (
  '00000000-0000-4000-8000-000000008301',
  '00000000-0000-4000-8000-000000008201', 'RLS-DEMO-TWO', 'fixture'
);

insert into public.system_commands (
  id, owner_id, type, payload, requested_by, idempotency_key, expires_at
) values
  (
    '00000000-0000-4000-8000-000000008401',
    '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
    '00000000-0000-4000-8000-000000000201', 'rls-owner-one',
    pg_catalog.clock_timestamp() + interval '5 minutes'
  ),
  (
    '00000000-0000-4000-8000-000000008402',
    '00000000-0000-4000-8000-000000008201', 'PAUSE_NEW_TRADES', '{}',
    '00000000-0000-4000-8000-000000008201', 'rls-owner-two',
    pg_catalog.clock_timestamp() + interval '5 minutes'
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
  (select pg_catalog.count(*) from public.profiles),
  1::bigint,
  'authenticated owner sees only its own profile'
);

select is(
  (select pg_catalog.count(*) from public.trading_accounts),
  1::bigint,
  'authenticated owner sees only its own account'
);

select is(
  (select pg_catalog.count(*) from public.system_command_read_models),
  1::bigint,
  'safe command view remains owner-scoped under SECURITY INVOKER'
);

select is(
  (select pg_catalog.count(id) from public.system_commands),
  1::bigint,
  'safe base command columns remain owner-scoped by RLS'
);

select throws_ok(
  $$select lease_token from public.system_commands$$,
  '42501'
);

select throws_ok(
  $$insert into public.system_commands (
      owner_id, type, payload, requested_by, idempotency_key, expires_at
    ) values (
      '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
      '00000000-0000-4000-8000-000000000201', 'browser-direct-write',
      clock_timestamp() + interval '30 seconds'
    )$$,
  '42501'
);

select throws_ok(
  $$update public.trading_modes set system_state = 'paused'$$,
  '42501'
);

select throws_ok($$insert into public.broker_orders default values$$, '42501');
select throws_ok($$insert into public.trade_executions default values$$, '42501');
select throws_ok($$insert into public.positions default values$$, '42501');

select results_eq(
  $$with changed as (
      update public.profiles
      set display_name = 'must-not-cross-owner'
      where id = '00000000-0000-4000-8000-000000008201'
      returning id
    ) select pg_catalog.count(*)::bigint from changed$$,
  array[0::bigint],
  'authenticated profile update cannot cross owner boundary'
);

select results_eq(
  $$with changed as (
      update public.profiles
      set display_name = 'RLS Owner One Safe Update'
      where id = '00000000-0000-4000-8000-000000000201'
      returning id
    ) select pg_catalog.count(*)::bigint from changed$$,
  array[1::bigint],
  'authenticated owner can update only the granted safe profile fields'
);

select pg_catalog.set_config(
  'request.jwt.claim.sub', '00000000-0000-4000-8000-000000008201', true
);
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"authenticated","sub":"00000000-0000-4000-8000-000000008201"}',
  true
);

select results_eq(
  $$select id from public.system_command_read_models order by id$$,
  $$values ('00000000-0000-4000-8000-000000008402'::uuid)$$,
  'switching JWT owner switches the RLS-visible command set'
);

reset role;
set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"rls-worker"}',
  true
);

select results_eq(
  $$select id from public.system_commands order by id$$,
  $$values ('00000000-0000-4000-8000-000000008401'::uuid)$$,
  'Worker reads commands only for the owner in its Worker claim'
);

select is(
  (select pg_catalog.count(*) from public.trading_accounts),
  1::bigint,
  'Worker domain reads are owner-scoped'
);

select throws_ok(
  $$select * from public.profiles$$,
  '42501'
);

select throws_ok(
  $$update public.system_commands set status = 'cancelled'$$,
  '42501'
);

select throws_ok(
  $$select public.request_pause_new_trades('worker-cannot-request')$$,
  '42501'
);

reset role;
set local role anon;
select throws_ok($$select * from public.trading_accounts$$, '42501');
select throws_ok($$insert into public.system_commands default values$$, '42501');

select * from finish();
rollback;
