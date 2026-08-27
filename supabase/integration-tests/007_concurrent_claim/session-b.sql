begin;
set local statement_timeout = '3s';
set local role aurum_worker;
set local request.jwt.claims =
  '{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"worker-concurrent-b"}';

select 1 / case
  when pg_catalog.count(*) = 1
    and pg_catalog.count(*) filter (
      where not accepted
        and command_id is null
        and status is null
        and lease_token is null
        and lease_expires_at is null
        and command_version is null
        and result_code = 'NO_ELIGIBLE_COMMAND'
    ) = 1
  then 1
  else 0
end
from public.worker_claim_next_command(30);

rollback;
