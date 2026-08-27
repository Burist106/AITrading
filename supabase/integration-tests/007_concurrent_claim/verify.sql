select 1 / case
  when exists (
    select 1
    from public.system_commands
    where id = '00000000-0000-4000-8000-000000007001'
      and status = 'pending'
      and claimed_at is null
      and claimed_by is null
      and lease_token is null
      and lease_expires_at is null
      and attempt_count = 0
      and command_version = 1
      and event_sequence = 0
  ) then 1
  else 0
end;

select 1 / case
  when (
    select pg_catalog.count(*)
    from public.system_command_events
    where system_command_id = '00000000-0000-4000-8000-000000007001'
  ) + (
    select pg_catalog.count(*)
    from public.audit_logs
    where target_id = '00000000-0000-4000-8000-000000007001'
  ) = 0 then 1
  else 0
end;
