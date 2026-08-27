begin;
set local statement_timeout = '12s';
set local role aurum_worker;
set local request.jwt.claims =
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-concurrent-a"}';

select 1 / case
  when pg_catalog.count(*) = 1
    and pg_catalog.count(*) filter (
      where accepted
        and command_id = '00000000-0000-4000-8000-000000007001'::uuid
        and status = 'claimed'
        and lease_token is not null
        and lease_expires_at is not null
        and command_version = 2
        and result_code = 'CLAIMED'
    ) = 1
  then 1
  else 0
end
from public.worker_claim_next_command(30);

reset role;
select pg_catalog.pg_advisory_lock(820260007);
select pg_catalog.pg_sleep(8);
rollback;
