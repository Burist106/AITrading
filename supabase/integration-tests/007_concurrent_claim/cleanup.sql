begin;

delete from public.system_commands
where id = '00000000-0000-4000-8000-000000007001';

do $test$
begin
  if not pg_catalog.pg_has_role('postgres', 'aurum_worker', 'SET') then
    raise exception using
      errcode = '55000',
      message = 'AURUM_CONCURRENCY_TEST_ROLE_BASELINE_CHANGED';
  end if;
end
$test$;

commit;
