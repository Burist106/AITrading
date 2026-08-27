begin;

do $test$
begin
  if not pg_catalog.pg_has_role('postgres', 'aurum_worker', 'SET') then
    raise exception using
      errcode = '55000',
      message = 'AURUM_CONCURRENCY_TEST_WORKER_SET_ROLE_UNAVAILABLE';
  end if;
end
$test$;

-- The pinned local Supabase role graph already lets its passwordless migration
-- test identity SET ROLE aurum_worker. Do not mutate that baseline membership.

delete from public.system_commands
where id = '00000000-0000-4000-8000-000000007001';

insert into public.system_commands (
  id, owner_id, type, payload, status, requested_by, requested_at,
  idempotency_key, expires_at
) values (
  '00000000-0000-4000-8000-000000007001',
  '00000000-0000-4000-8000-000000000201',
  'PAUSE_NEW_TRADES', '{}'::jsonb, 'pending',
  '00000000-0000-4000-8000-000000000201', pg_catalog.clock_timestamp(),
  'concurrent-claim-fixture', pg_catalog.clock_timestamp() + interval '5 minutes'
);

commit;
