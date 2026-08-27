begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to aurum_worker;
grant execute on all functions in schema extensions to aurum_worker;
set local search_path = public, extensions;

select plan(84);

insert into public.system_commands (
  id, owner_id, type, payload, status, requested_by, requested_at,
  idempotency_key, claimed_at, claimed_by, lease_token, lease_expires_at,
  attempt_count, expires_at
) values (
  '00000000-0000-4000-8000-000000006201',
  '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
  'claimed', '00000000-0000-4000-8000-000000000201',
  pg_catalog.clock_timestamp() - interval '2 minutes', 'queue-expired-claimed',
  pg_catalog.clock_timestamp() - interval '1 minute', 'old-worker',
  '00000000-0000-4000-8000-000000006211',
  pg_catalog.clock_timestamp() - interval '10 seconds', 1,
  pg_catalog.clock_timestamp() + interval '10 minutes'
), (
  '00000000-0000-4000-8000-000000006202',
  '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
  'executing', '00000000-0000-4000-8000-000000000201',
  pg_catalog.clock_timestamp() - interval '3 minutes', 'queue-expired-executing',
  pg_catalog.clock_timestamp() - interval '2 minutes', 'old-worker',
  '00000000-0000-4000-8000-000000006212',
  pg_catalog.clock_timestamp() - interval '90 seconds', 1,
  pg_catalog.clock_timestamp() - interval '1 minute'
), (
  '00000000-0000-4000-8000-000000006203',
  '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
  'pending', '00000000-0000-4000-8000-000000000201',
  pg_catalog.clock_timestamp() - interval '2 minutes', 'queue-expired-pending',
  null, null, null, null, 0,
  pg_catalog.clock_timestamp() - interval '1 minute'
), (
  '00000000-0000-4000-8000-000000006204',
  '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
  'claimed', '00000000-0000-4000-8000-000000000201',
  pg_catalog.clock_timestamp() - interval '3 minutes', 'queue-command-expired-claimed',
  pg_catalog.clock_timestamp() - interval '2 minutes', 'old-worker',
  '00000000-0000-4000-8000-000000006214',
  pg_catalog.clock_timestamp() - interval '90 seconds', 1,
  pg_catalog.clock_timestamp() - interval '1 minute'
), (
  '00000000-0000-4000-8000-000000006205',
  '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
  'validating', '00000000-0000-4000-8000-000000000201',
  pg_catalog.clock_timestamp() - interval '3 minutes', 'queue-command-expired-validating',
  pg_catalog.clock_timestamp() - interval '2 minutes', 'old-worker',
  '00000000-0000-4000-8000-000000006215',
  pg_catalog.clock_timestamp() - interval '90 seconds', 1,
  pg_catalog.clock_timestamp() - interval '1 minute'
), (
  '00000000-0000-4000-8000-000000006206',
  '00000000-0000-4000-8000-000000000201', 'PAUSE_NEW_TRADES', '{}',
  'claimed', '00000000-0000-4000-8000-000000000201',
  pg_catalog.clock_timestamp() - interval '3 minutes', 'queue-attempts-exhausted',
  pg_catalog.clock_timestamp() - interval '2 minutes', 'old-worker',
  '00000000-0000-4000-8000-000000006216',
  pg_catalog.clock_timestamp() - interval '10 seconds', 3,
  pg_catalog.clock_timestamp() + interval '10 minutes'
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
  (public.request_pause_new_trades(
    'queue-normal', 'queue-normal', pg_catalog.clock_timestamp() + interval '4 minutes'
  )).result_code,
  'CREATED', 'normal queue fixture is recorded through the authenticated intent RPC'
);
select is(
  (public.request_emergency_stop(
    'queue-emergency', 'queue-emergency',
    pg_catalog.clock_timestamp() + interval '4 minutes'
  )).result_code,
  'CREATED', 'emergency queue fixture is recorded through the authenticated intent RPC'
);

reset role;
set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-a"}',
  true
);

select pg_catalog.set_config(
  'request.jwt.claims',
  pg_catalog.jsonb_build_object(
    'role', 'aurum_worker',
    'owner_id', '00000000-0000-4000-8000-000000000201',
    'worker_id', 'SB_' || 'SECRET_' || pg_catalog.repeat('X', 20)
  )::text,
  true
);
select results_eq(
  $$select accepted, command_id, status, lease_token, lease_expires_at,
      command_version, result_code
    from public.worker_claim_next_command(30)$$,
  $$values (
    false, null::uuid, null::public.system_command_status, null::uuid,
    null::timestamptz, null::integer, 'WORKER_UNAUTHORIZED'
  )$$,
  'unauthorized claim returns one deterministic payload-free envelope'
);
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-a"}',
  true
);
select results_eq(
  $$select accepted, command_id, status, lease_token, lease_expires_at,
      command_version, result_code
    from public.worker_claim_next_command(null)$$,
  $$values (
    false, null::uuid, null::public.system_command_status, null::uuid,
    null::timestamptz, null::integer, 'INVALID_LEASE_DURATION'
  )$$,
  'NULL claim duration returns a deterministic invalid-lease envelope'
);
reset role;
select ok(
  (
    select pg_catalog.count(*) = 6
    from public.system_commands
    where id in (
      '00000000-0000-4000-8000-000000006201',
      '00000000-0000-4000-8000-000000006202',
      '00000000-0000-4000-8000-000000006203',
      '00000000-0000-4000-8000-000000006204',
      '00000000-0000-4000-8000-000000006205',
      '00000000-0000-4000-8000-000000006206'
    ) and completed_at is null
  ) and not exists (
    select 1 from public.system_command_events
    where system_command_id in (
      '00000000-0000-4000-8000-000000006201',
      '00000000-0000-4000-8000-000000006202',
      '00000000-0000-4000-8000-000000006203',
      '00000000-0000-4000-8000-000000006204',
      '00000000-0000-4000-8000-000000006205',
      '00000000-0000-4000-8000-000000006206'
    )
  ) and not exists (
    select 1 from public.audit_logs
    where target_id in (
      '00000000-0000-4000-8000-000000006201',
      '00000000-0000-4000-8000-000000006202',
      '00000000-0000-4000-8000-000000006203',
      '00000000-0000-4000-8000-000000006204',
      '00000000-0000-4000-8000-000000006205',
      '00000000-0000-4000-8000-000000006206'
    )
  ),
  'unauthorized and invalid claims mutate no command, event, or audit state'
);
set local role aurum_worker;
select results_eq(
  $$select accepted, command_id, status::text, lease_token is not null,
      lease_expires_at is not null, command_version, result_code
    from public.worker_claim_next_command(30)$$,
  $$select true, id, 'claimed', true, true, command_version + 1, 'CLAIMED'
    from public.system_commands where idempotency_key = 'queue-emergency'$$,
  'atomic claim selects emergency priority first'
);
select results_eq(
  $$select id, status::text from public.system_commands
    where id in (
      '00000000-0000-4000-8000-000000006203',
      '00000000-0000-4000-8000-000000006204',
      '00000000-0000-4000-8000-000000006205',
      '00000000-0000-4000-8000-000000006206'
    ) order by id$$,
  $$values
      ('00000000-0000-4000-8000-000000006203'::uuid, 'expired'),
      ('00000000-0000-4000-8000-000000006204'::uuid, 'expired'),
      ('00000000-0000-4000-8000-000000006205'::uuid, 'expired'),
      ('00000000-0000-4000-8000-000000006206'::uuid, 'failed')$$,
  'claim sweep deterministically terminalizes expired and exhausted non-executing work'
);
select is(
  (select pg_catalog.count(*) from public.system_commands
   where id in (
     '00000000-0000-4000-8000-000000006203',
     '00000000-0000-4000-8000-000000006204',
     '00000000-0000-4000-8000-000000006205',
     '00000000-0000-4000-8000-000000006206'
   ) and completed_at is not null
     and claimed_at is null and claimed_by is null
     and lease_token is null and lease_expires_at is null),
  4::bigint,
  'deterministic terminalization clears every active claim field and records completion time'
);
select is(
  (select pg_catalog.count(*) from public.system_command_events
   where system_command_id in (
     '00000000-0000-4000-8000-000000006203',
     '00000000-0000-4000-8000-000000006204',
     '00000000-0000-4000-8000-000000006205',
     '00000000-0000-4000-8000-000000006206'
   ) and event_type = 'status_changed'),
  4::bigint,
  'each deterministic terminalization appends one durable lifecycle event'
);
reset role;
select is(
  (select pg_catalog.count(*) from public.audit_logs
   where target_id in (
     '00000000-0000-4000-8000-000000006203',
     '00000000-0000-4000-8000-000000006204',
     '00000000-0000-4000-8000-000000006205',
     '00000000-0000-4000-8000-000000006206'
   ) and action in ('command_expired', 'command_attempts_exhausted')),
  4::bigint,
  'each deterministic terminalization appends one Worker audit row'
);
set local role aurum_worker;
select is(
  (select result_code from public.system_commands
   where id = '00000000-0000-4000-8000-000000006206'),
  'MAXIMUM_ATTEMPTS_EXHAUSTED',
  'an expired lease at the maximum attempt count fails with a stable result code'
);
select ok(
  exists (
    select 1 from public.system_commands
    where idempotency_key = 'queue-emergency'
      and status = 'claimed'
      and claimed_at is not null and claimed_by = 'worker-a'
      and lease_token is not null and lease_expires_at is not null
  ),
  'a claimed command has the complete active claim quartet'
);
select results_eq(
  $$select accepted, command_id, status::text, lease_token is not null,
      lease_expires_at is not null, command_version, result_code
    from public.worker_claim_next_command(30)$$,
  $$values (
    true, '00000000-0000-4000-8000-000000006201'::uuid,
    'claimed', true, true, 2, 'CLAIMED'
  )$$,
  'an expired claimed lease is recovered before newer pending work'
);
select results_eq(
  $$select accepted, command_id, status::text, lease_token is not null,
      lease_expires_at is not null, command_version, result_code
    from public.worker_claim_next_command(30)$$,
  $$select true, id, 'claimed', true, true, command_version + 1, 'CLAIMED'
    from public.system_commands where idempotency_key = 'queue-normal'$$,
  'a later claim skips active leases and selects the remaining pending work'
);
select ok(
  exists (
    select 1 from public.system_commands as command_row
    join public.system_command_events as event_row
      on event_row.system_command_id = command_row.id
    where command_row.id = '00000000-0000-4000-8000-000000006201'
      and command_row.status = 'claimed'
      and command_row.claimed_by = 'worker-a'
      and command_row.attempt_count = 2
      and event_row.event_type = 'claim_recovered'
      and event_row.actor_id = 'worker-a'
  ),
  'lease recovery increments attempts and records an explicit recovery event'
);

reset role;
select throws_ok(
  $$update public.system_commands
    set attempt_count = attempt_count + 1
    where id = '00000000-0000-4000-8000-000000006201'$$,
  '55000', 'AURUM_INVALID_COMMAND_DELTA',
  'the lifecycle guard rejects an attempt increment outside an atomic claim'
);
select throws_ok(
  $$update public.system_commands
    set lease_expires_at = lease_expires_at - interval '1 second',
        command_version = command_version + 1,
        updated_at = clock_timestamp()
    where id = '00000000-0000-4000-8000-000000006201'$$,
  '55000', 'AURUM_INVALID_COMMAND_DELTA',
  'the lifecycle guard rejects non-monotonic lease mutation'
);
select throws_ok(
  $$update public.system_commands
    set event_sequence = event_sequence + 2,
        updated_at = clock_timestamp()
    where id = '00000000-0000-4000-8000-000000006201'$$,
  '55000', 'AURUM_INVALID_COMMAND_DELTA',
  'the lifecycle guard permits only one append-only event sequence step'
);

create temporary table no_eligible_claim_snapshot on commit drop as
select
  (select pg_catalog.sum(command_version) from public.system_commands
   where owner_id = '00000000-0000-4000-8000-000000000201') as command_versions,
  (select pg_catalog.sum(event_sequence) from public.system_commands
   where owner_id = '00000000-0000-4000-8000-000000000201') as event_sequences,
  (select pg_catalog.count(*) from public.system_command_events
   where owner_id = '00000000-0000-4000-8000-000000000201') as event_count,
  (select pg_catalog.count(*) from public.audit_logs
   where owner_id = '00000000-0000-4000-8000-000000000201') as audit_count;
set local role aurum_worker;
select results_eq(
  $$select accepted, command_id, status, lease_token, lease_expires_at,
      command_version, result_code
    from public.worker_claim_next_command(30)$$,
  $$values (
    false, null::uuid, null::public.system_command_status, null::uuid,
    null::timestamptz, null::integer, 'NO_ELIGIBLE_COMMAND'
  )$$,
  'active leases return NO_ELIGIBLE_COMMAND and expired executing work is not reissued'
);
reset role;
select ok(
  exists (
    select 1 from no_eligible_claim_snapshot as snapshot
    where snapshot.command_versions = (
      select pg_catalog.sum(command_version) from public.system_commands
      where owner_id = '00000000-0000-4000-8000-000000000201'
    ) and snapshot.event_sequences = (
      select pg_catalog.sum(event_sequence) from public.system_commands
      where owner_id = '00000000-0000-4000-8000-000000000201'
    ) and snapshot.event_count = (
      select pg_catalog.count(*) from public.system_command_events
      where owner_id = '00000000-0000-4000-8000-000000000201'
    ) and snapshot.audit_count = (
      select pg_catalog.count(*) from public.audit_logs
      where owner_id = '00000000-0000-4000-8000-000000000201'
    )
  ),
  'NO_ELIGIBLE_COMMAND changes no command version, event, or audit state'
);
select ok(
  exists (
    select 1 from public.system_commands
    where id = '00000000-0000-4000-8000-000000006202'
      and status = 'executing' and completed_at is null
  ) and not exists (
    select 1 from public.system_command_events
    where system_command_id = '00000000-0000-4000-8000-000000006202'
  ) and not exists (
    select 1 from public.audit_logs
    where target_id = '00000000-0000-4000-8000-000000006202'
  ),
  'expired executing uncertainty remains quarantined without synthetic event or audit'
);
set local role aurum_worker;

select is(
  (public.worker_renew_command_lease(
    (select id from public.system_commands where idempotency_key = 'queue-normal'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-normal'),
    45
  )).result_code,
  'LEASE_RENEWED', 'the current lease owner can renew an active lease'
);
select is(
  (public.worker_renew_command_lease(
    (select id from public.system_commands where idempotency_key = 'queue-normal'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-normal'),
    300
  )).result_code,
  'LEASE_RENEWED', 'a lease request beyond command lifetime is safely clamped'
);
select ok(
  exists (
    select 1 from public.system_commands
    where idempotency_key = 'queue-normal'
      and lease_expires_at = expires_at
  ),
  'a renewed lease never crosses the absolute command expiry'
);
reset role;
select is(
  (select pg_catalog.count(*) from public.audit_logs
   where target_id = (
     select id from public.system_commands where idempotency_key = 'queue-normal'
   ) and action = 'command_lease_renewed'),
  2::bigint,
  'each accepted lease renewal appends exactly one audit record'
);
set local role aurum_worker;
select is(
  (public.worker_renew_command_lease(
    (select id from public.system_commands where idempotency_key = 'queue-normal'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-normal'),
    null
  )).result_code,
  'INVALID_LEASE_DURATION',
  'NULL renewal duration returns a deterministic safe code'
);
reset role;
select is(
  (select pg_catalog.count(*) from public.audit_logs
   where target_id = (
     select id from public.system_commands where idempotency_key = 'queue-normal'
   ) and action = 'command_lease_renewed'),
  2::bigint,
  'rejected lease renewal appends no audit record'
);
set local role aurum_worker;

select is(
  (public.worker_mark_command_validating(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-emergency')
  )).result_code,
  null::text,
  'claimed command advances to validating'
);
select is(
  (select status::text from public.system_commands where idempotency_key = 'queue-emergency'),
  'validating', 'validating transition commits'
);
select is(
  (public.worker_mark_command_executing(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-emergency')
  )).result_code,
  null::text,
  'validating command advances to executing'
);
reset role;
select results_eq(
  $$select action from public.audit_logs
    where target_id = (
      select id from public.system_commands where idempotency_key = 'queue-emergency'
    ) and action in ('command_validation_started', 'command_execution_started')
    order by created_at, id$$,
  $$values ('command_validation_started'), ('command_execution_started')$$,
  'accepted validating and executing transitions each append an ordered audit record'
);

create temporary table rejected_result_code_snapshot on commit drop as
select
  command_row.status,
  command_row.command_version,
  command_row.event_sequence,
  (
    select pg_catalog.count(*)
    from public.system_command_events as event_row
    where event_row.system_command_id = command_row.id
  ) as event_count,
  (
    select pg_catalog.count(*)
    from public.audit_logs as audit_row
    where audit_row.target_id = command_row.id
  ) as audit_count
from public.system_commands as command_row
where command_row.idempotency_key = 'queue-emergency';
set local role aurum_worker;

select is(
  (public.worker_complete_command(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-emergency'),
    'SB_' || 'SECRET_' || pg_catalog.repeat('X', 20), 'Must not persist.'
  )).result_code,
  'INVALID_RESULT_CODE',
  'secret-shaped Worker result codes fail closed with a deterministic code'
);

reset role;
select ok(
  exists (
    select 1
    from rejected_result_code_snapshot as snapshot
    join public.system_commands as command_row
      on command_row.idempotency_key = 'queue-emergency'
    where command_row.status = snapshot.status
      and command_row.command_version = snapshot.command_version
      and command_row.event_sequence = snapshot.event_sequence
      and snapshot.event_count = (
        select pg_catalog.count(*)
        from public.system_command_events as event_row
        where event_row.system_command_id = command_row.id
      )
      and snapshot.audit_count = (
        select pg_catalog.count(*)
        from public.audit_logs as audit_row
        where audit_row.target_id = command_row.id
      )
  ),
  'rejected result code changes no command state, event history, or audit evidence'
);
set local role aurum_worker;

select is(
  (public.worker_complete_command(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-emergency'),
    'COMPLETED', E'Authorization: Bearer should-not-persist\n'
  )).result_code,
  'UNSAFE_RESULT_MESSAGE', 'unsafe result messages fail closed before persistence'
);
select is(
  (public.worker_fail_command(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-emergency'),
    'FAILED_SAFE', 'Safe failure', 'password=should-not-persist', false, null
  )).result_code,
  'UNSAFE_LAST_ERROR', 'unsafe last-error text fails closed before persistence'
);
select is(
  (public.worker_complete_command(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-emergency'),
    'COMPLETED',
    'eyJ' || 'abcdefghijk' || '.' || 'eyJmnopqrstuv' || '.' || 'wxyzABCDEFGHI'
  )).result_code,
  'UNSAFE_RESULT_MESSAGE', 'raw JWT-shaped result text is rejected before persistence'
);
select is(
  (public.worker_fail_command(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-emergency'),
    'FAILED_SAFE', 'Safe failure',
    'sk-' || '1234567890abcdefghijklmnop', false, null
  )).result_code,
  'UNSAFE_LAST_ERROR', 'high-confidence API-key-shaped error text is rejected'
);

select is(
  (public.worker_complete_command(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-emergency'),
    'COMPLETED', 'Completed safely.'
  )).result_code,
  'COMPLETED', 'terminal completion commits'
);
select ok(
  exists (
    select 1 from public.system_commands
    where idempotency_key = 'queue-emergency'
      and status = 'succeeded' and completed_at is not null
      and result_code = 'COMPLETED' and result_message = 'Completed safely.'
      and claimed_at is null and claimed_by is null
      and lease_token is null and lease_expires_at is null
  ),
  'terminal completion clears the entire active claim quartet'
);
select results_eq(
  $$select event_type::text from public.system_command_events
    where system_command_id = (
      select id from public.system_commands where idempotency_key = 'queue-emergency'
    ) order by sequence$$,
  $$values ('created'), ('claimed'), ('status_changed'), ('status_changed'), ('status_changed')$$,
  'created, claim, validation, execution, and completion events commit in order'
);
reset role;
select ok(
  exists (
    select 1 from public.audit_logs
    where request_id = (
      select id from public.system_commands where idempotency_key = 'queue-emergency'
    ) and action = 'command_completed' and actor_id = 'worker-a'
  ),
  'terminal completion commits its durable Worker audit row'
);
set local role aurum_worker;
select is(
  (public.worker_complete_command(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    '00000000-0000-4000-8000-000000006299', 'COMPLETED', 'Completed safely.'
  )).result_code,
  'IDEMPOTENT_COMPLETION', 'same Worker may replay the exact terminal result'
);

select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-b"}',
  true
);
select is(
  (public.worker_complete_command(
    (select id from public.system_commands where idempotency_key = 'queue-emergency'),
    '00000000-0000-4000-8000-000000006298', 'COMPLETED', 'Completed safely.'
  )).result_code,
  'TERMINAL_STATE_CONFLICT', 'a different Worker cannot replay another Worker terminal result'
);
reset role;
select is(
  (select pg_catalog.count(*) from public.audit_logs
   where target_id = (
     select id from public.system_commands where idempotency_key = 'queue-emergency'
   ) and action = 'command_completed'),
  1::bigint,
  'idempotent replay and terminal conflict append no additional audit record'
);
set local role aurum_worker;

select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-a"}',
  true
);
select is(
  (public.worker_fail_command(
    (select id from public.system_commands where idempotency_key = 'queue-normal'),
    (select lease_token from public.system_commands where idempotency_key = 'queue-normal'),
    'TRANSIENT_FAILURE', 'Retry scheduled.', 'Safe transient failure.', true,
    pg_catalog.clock_timestamp() + interval '200 milliseconds'
  )).result_code,
  'RETRY_SCHEDULED', 'retryable failure schedules durable pending work'
);
select ok(
  exists (
    select 1 from public.system_commands where idempotency_key = 'queue-normal'
      and status = 'pending' and next_retry_at is not null
      and claimed_at is null and claimed_by is null
      and lease_token is null and lease_expires_at is null
  ),
  'retry scheduling clears the active claim quartet'
);
reset role;
select ok(
  exists (
    select 1 from public.audit_logs
    where target_id = (
      select id from public.system_commands where idempotency_key = 'queue-normal'
    ) and action = 'command_retry_scheduled'
      and old_version is not null and new_version = old_version + 1
  ),
  'accepted retry scheduling appends its monotonic lifecycle audit'
);
set local role aurum_worker;
select results_eq(
  $$select accepted, command_id, status, lease_token, lease_expires_at,
      command_version, result_code
    from public.worker_claim_next_command(30)$$,
  $$values (
    false, null::uuid, null::public.system_command_status, null::uuid,
    null::timestamptz, null::integer, 'NO_ELIGIBLE_COMMAND'
  )$$,
  'claim returns NO_ELIGIBLE_COMMAND until durable next_retry_at is due'
);

select pg_catalog.pg_sleep(0.25);
select results_eq(
  $$select accepted, command_id, status::text, lease_token is not null,
      lease_expires_at is not null, command_version, result_code
    from public.worker_claim_next_command(30)$$,
  $$select true, id, 'claimed', true, true, command_version + 1, 'CLAIMED'
    from public.system_commands where idempotency_key = 'queue-normal'$$,
  'pending retry is claimable once next_retry_at is due'
);
select is(
  (public.worker_fail_command(
    '00000000-0000-4000-8000-000000006202',
    '00000000-0000-4000-8000-000000006212', 'FAILED_SAFE',
    'Safe reconciliation required.', 'Safe expired executing lease.', false, null
  )).result_code,
  'LEASE_NOT_OWNED',
  'a different Worker cannot use another Worker expired executing ownership proof'
);

select pg_catalog.set_config(
  'request.jwt.claims',
  pg_catalog.jsonb_build_object(
    'role', 'aurum_worker',
    'owner_id', '00000000-0000-4000-8000-000000000201',
    'worker_id', 'eyJ' || 'workerheader' || '.' || 'workerpayload' || '.' || 'workersignature'
  )::text,
  true
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'Safe detail.',
    pg_catalog.clock_timestamp(), 30
  ),
  'WORKER_UNAUTHORIZED',
  'JWT-shaped Worker identity is rejected before it can enter durable records'
);
select pg_catalog.set_config(
  'request.jwt.claims',
  pg_catalog.jsonb_build_object(
    'role', 'aurum_worker',
    'owner_id', '00000000-0000-4000-8000-000000000201',
    'worker_id', 'sk-' || 'workeridentitymustnotpersist'
  )::text,
  true
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'Safe detail.',
    pg_catalog.clock_timestamp(), 30
  ),
  'WORKER_UNAUTHORIZED',
  'API-key-shaped Worker identity is rejected before persistence'
);
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-a"}',
  true
);

select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'Worker fixture is healthy.',
    pg_catalog.clock_timestamp(), 30
  ),
  'HEARTBEAT_RECORDED', 'Worker heartbeat upserts through its bounded RPC'
);
select is(
  (select pg_catalog.count(*) from public.system_heartbeats
   where worker_id = 'worker-a' and state = 'healthy'),
  1::bigint,
  'heartbeat state is durable and owner-scoped'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'degraded', 'Worker fixture remains safe.',
    pg_catalog.clock_timestamp(), 30
  ),
  'HEARTBEAT_RECORDED', 'a newer Worker heartbeat updates the durable row'
);
reset role;
select results_eq(
  $$select action, old_version, new_version from public.audit_logs
    where target_id = (
      select id from public.system_heartbeats where worker_id = 'worker-a'
    ) and action in ('heartbeat_recorded', 'heartbeat_updated')
    order by new_version$$,
  $$values
    ('heartbeat_recorded', null::integer, 1),
    ('heartbeat_updated', 1, 2)$$,
  'heartbeat insert and update each append exact monotonic audit evidence'
);
set local role aurum_worker;
select is(
  public.worker_record_heartbeat(
    'execution.worker', null::public.system_health_state, 'Safe detail.',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT', 'NULL heartbeat state returns a deterministic safe code'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'Safe detail.',
    pg_catalog.clock_timestamp(), null
  ),
  'INVALID_HEARTBEAT', 'NULL heartbeat validity returns a deterministic safe code'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'healthy', 'Safe stale detail.',
    pg_catalog.clock_timestamp() - interval '1 day', 30
  ),
  'STALE_HEARTBEAT', 'stale heartbeat is rejected without a state change'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'degraded', E'authorization: bad\nheader',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT', 'unsafe heartbeat detail is rejected'
);
select is(
  public.worker_record_heartbeat(
    'execution.worker', 'degraded',
    'postgresql://aurum:supersecret@database.invalid/demo',
    pg_catalog.clock_timestamp(), 30
  ),
  'INVALID_HEARTBEAT', 'credential-bearing DSN heartbeat detail is rejected'
);
reset role;
select is(
  (select pg_catalog.count(*) from public.audit_logs
   where action in ('heartbeat_recorded', 'heartbeat_updated')
     and target_id = (
       select id from public.system_heartbeats where worker_id = 'worker-a'
     )),
  2::bigint,
  'invalid and stale heartbeat calls append no audit record'
);

create temporary table rejected_incident_snapshot on commit drop as
select
  (
    select pg_catalog.count(*) from public.system_incidents
    where owner_id = '00000000-0000-4000-8000-000000000201'
  ) as incident_count,
  (
    select pg_catalog.count(*) from public.audit_logs
    where owner_id = '00000000-0000-4000-8000-000000000201'
      and action = 'incident_recorded'
  ) as audit_count;
set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  pg_catalog.jsonb_build_object(
    'role', 'aurum_worker',
    'owner_id', '00000000-0000-4000-8000-000000000201',
    'worker_id', 'AKIA' || pg_catalog.repeat('A', 16)
  )::text,
  true
);
select results_eq(
  $$select accepted, incident_id, created, result_code
    from public.worker_record_incident(
      'WORKER_FIXTURE', 'warning', 'Worker fixture incident',
      'Safe incident detail.', '2026-08-26T12:00:00Z',
      '00000000-0000-4000-8000-000000006706'
    )$$,
  $$values (false, null::uuid, false, 'WORKER_UNAUTHORIZED')$$,
  'unauthorized incident returns one deterministic envelope'
);
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-a"}',
  true
);
select is(
  (public.worker_record_incident(
    'WORKER_FIXTURE', null::public.incident_severity,
    'Worker fixture incident', 'Safe incident detail.',
    pg_catalog.clock_timestamp(), '00000000-0000-4000-8000-000000006703'
  )).result_code,
  'INVALID_INCIDENT_SEVERITY',
  'NULL incident severity is rejected without an exception'
);
select is(
  (public.worker_record_incident(
    'worker_fixture', 'warning', 'Worker fixture incident',
    'Safe incident detail.', pg_catalog.clock_timestamp(),
    '00000000-0000-4000-8000-000000006704'
  )).result_code,
  'INVALID_INCIDENT_CODE',
  'incident code must use the uppercase machine-code form'
);
select is(
  (public.worker_record_incident(
    'SB_' || 'SECRET_' || pg_catalog.repeat('X', 20),
    'warning', 'Worker fixture incident', 'Safe incident detail.',
    pg_catalog.clock_timestamp(), '00000000-0000-4000-8000-000000006705'
  )).result_code,
  'INVALID_INCIDENT_CODE',
  'secret-shaped incident code is rejected before metadata persistence'
);
select is(
  (public.worker_record_incident(
    'WORKER_FIXTURE', 'warning',
    'postgresql://aurum:supersecret@database.invalid/demo',
    'Safe incident detail.', pg_catalog.clock_timestamp(),
    '00000000-0000-4000-8000-000000006702'
  )).result_code,
  'INVALID_INCIDENT_TITLE',
  'credential-bearing incident title is rejected before persistence'
);
select is(
  (public.worker_record_incident(
    'WORKER_FIXTURE_DETAIL', 'warning', 'Worker fixture incident',
    'postgresql://aurum:supersecret@database.invalid/demo',
    pg_catalog.clock_timestamp(), '00000000-0000-4000-8000-000000006707'
  )).result_code,
  'INVALID_INCIDENT_DETAIL',
  'credential-bearing incident detail is rejected before persistence'
);
select is(
  (public.worker_record_incident(
    'WORKER_FIXTURE_TIME', 'warning', 'Worker fixture incident',
    'Safe incident detail.', null,
    '00000000-0000-4000-8000-000000006708'
  )).result_code,
  'INVALID_INCIDENT_TIME',
  'NULL incident time returns a deterministic invalid-time code'
);

reset role;
select ok(
  exists (
    select 1 from rejected_incident_snapshot as snapshot
    where snapshot.incident_count = (
      select pg_catalog.count(*) from public.system_incidents
      where owner_id = '00000000-0000-4000-8000-000000000201'
    ) and snapshot.audit_count = (
      select pg_catalog.count(*) from public.audit_logs
      where owner_id = '00000000-0000-4000-8000-000000000201'
        and action = 'incident_recorded'
    )
  ),
  'unauthorized and invalid incident calls mutate no incident or audit state'
);
set local role aurum_worker;
select ok(
  (
    select result.accepted
      and result.incident_id is not null
      and result.created
      and result.result_code = 'CREATED'
    from public.worker_record_incident(
      'WORKER_FIXTURE', 'warning', 'Worker fixture incident', 'Safe incident detail.',
      '2026-08-26T12:00:00Z', '00000000-0000-4000-8000-000000006701'
    ) as result
  ),
  'new Worker incident returns a CREATED envelope'
);
select results_eq(
  $$select accepted, incident_id, created, result_code
    from public.worker_record_incident(
      'WORKER_FIXTURE', 'warning', 'Worker fixture incident', 'Safe incident detail.',
      '2026-08-26T12:00:00Z', '00000000-0000-4000-8000-000000006701'
    )$$,
  $$select true, id, false, 'IDEMPOTENT_REPLAY'
    from public.system_incidents
    where request_id = '00000000-0000-4000-8000-000000006701'$$,
  'exact incident replay returns the existing identity without a new mutation'
);
select results_eq(
  $$select accepted, incident_id, created, result_code
    from public.worker_record_incident(
      'WORKER_FIXTURE', 'warning', 'Worker fixture incident', 'Changed detail.',
      '2026-08-26T12:00:00Z', '00000000-0000-4000-8000-000000006701'
    )$$,
  $$values (false, null::uuid, false, 'IDEMPOTENCY_CONFLICT')$$,
  'same incident request ID with changed canonical input fails closed'
);
reset role;
select ok(
  (select pg_catalog.count(*) = 1 from public.system_incidents
   where request_id = '00000000-0000-4000-8000-000000006701')
  and
  (select pg_catalog.count(*) = 1 from public.audit_logs
   where request_id = '00000000-0000-4000-8000-000000006701'
     and action = 'incident_recorded'),
  'new incident audits once; replay and conflict append no row or audit'
);
reset role;
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
  (public.request_risk_policy_change(
    'risk_per_trade_pct', 0.20, 'activate-first', 1, 'queue-risk-first',
    pg_catalog.clock_timestamp() + interval '4 minutes'
  )).result_code,
  'CREATED', 'first risk-policy command creates pending version two'
);
select is(
  (public.request_risk_policy_change(
    'daily_loss_limit_pct', 0.90, 'stale-second', 1, 'queue-risk-second',
    pg_catalog.clock_timestamp() + interval '4 minutes'
  )).result_code,
  'CREATED', 'second risk-policy command creates pending version three'
);

reset role;
update public.system_commands
set status = 'claimed', claimed_at = pg_catalog.clock_timestamp(),
    claimed_by = 'worker-a', lease_token = '00000000-0000-4000-8000-000000006801',
    lease_expires_at = pg_catalog.clock_timestamp() + interval '2 minutes',
    attempt_count = 1, command_version = command_version + 1,
    updated_at = pg_catalog.clock_timestamp()
where idempotency_key = 'queue-risk-first';

set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-a"}',
  true
);
select is(
  (public.worker_mark_command_validating(
    (select id from public.system_commands where idempotency_key = 'queue-risk-first'),
    '00000000-0000-4000-8000-000000006801'
  )).status::text,
  'validating', 'risk-policy command enters validation under its lease'
);
select is(
  (public.worker_complete_command(
    (select id from public.system_commands where idempotency_key = 'queue-risk-first'),
    '00000000-0000-4000-8000-000000006801', 'POLICY_ACKNOWLEDGED',
    'Policy snapshot acknowledged safely.'
  )).result_code,
  'POLICY_ACKNOWLEDGED', 'Worker acknowledgement activates the pending risk version'
);
select results_eq(
  $$select resource_version, version
    from public.risk_policies as policy_row
    join public.risk_policy_versions as version_row
      on version_row.id = policy_row.active_version_id
    where policy_row.id = '00000000-0000-4000-8000-000000000331'$$,
  $$values (2, 2)$$,
  'successful acknowledgement atomically advances policy resource and active version'
);

reset role;
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
  (public.request_risk_policy_change(
    'risk_per_trade_pct', 0.20, 'activate-first', 1, 'queue-risk-first',
    pg_catalog.clock_timestamp() - interval '1 second'
  )).result_code,
  'IDEMPOTENT_REPLAY',
  'exact risk-policy replay wins over stale version and a now-invalid expiry'
);
select ok(
  (select pg_catalog.count(*) from public.audit_logs
   where request_id = (
     select id from public.system_command_read_models
     where idempotency_key = 'queue-risk-first'
   ) and action = 'risk_policy_change_requested') = 1
  and
  (select pg_catalog.count(*) from public.audit_logs
   where request_id = (
     select id from public.system_command_read_models
     where idempotency_key = 'queue-risk-first'
   ) and action = 'risk_policy_version_created') = 1,
  'exact risk-policy replay appends no duplicate user audit records'
);

reset role;
update public.system_commands
set status = 'claimed', claimed_at = pg_catalog.clock_timestamp(),
    claimed_by = 'worker-a', lease_token = '00000000-0000-4000-8000-000000006802',
    lease_expires_at = pg_catalog.clock_timestamp() + interval '2 minutes',
    attempt_count = 1, command_version = command_version + 1,
    updated_at = pg_catalog.clock_timestamp()
where idempotency_key = 'queue-risk-second';

set local role aurum_worker;
select pg_catalog.set_config(
  'request.jwt.claims',
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-a"}',
  true
);
select is(
  (public.worker_mark_command_validating(
    (select id from public.system_commands where idempotency_key = 'queue-risk-second'),
    '00000000-0000-4000-8000-000000006802'
  )).status::text,
  'validating', 'second risk-policy command enters validation under its lease'
);
select is(
  (public.worker_complete_command(
    (select id from public.system_commands where idempotency_key = 'queue-risk-second'),
    '00000000-0000-4000-8000-000000006802', 'POLICY_ACKNOWLEDGED',
    'Policy snapshot acknowledged safely.'
  )).result_code,
  'STALE_RISK_POLICY_VERSION', 'stale second risk command cannot activate over newer policy state'
);
select ok(
  exists (
    select 1 from public.system_commands where idempotency_key = 'queue-risk-second'
      and status = 'validating' and lease_token is not null
  ) and exists (
    select 1 from public.risk_policies as policy_row
    join public.risk_policy_versions as version_row
      on version_row.id = policy_row.active_version_id
    where policy_row.id = '00000000-0000-4000-8000-000000000331'
      and policy_row.resource_version = 2 and version_row.version = 2
  ),
  'stale acknowledgement leaves command leased for explicit resolution and policy unchanged'
);

select * from finish();
rollback;
