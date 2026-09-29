-- Successful bounded history evidence must describe events inside its request.
-- Preserve out-of-window metadata only when the query is marked incomplete.
-- Existing append-only evidence is never rewritten; invalid historical success
-- causes this migration to fail instead of silently legitimizing that claim.

alter table public.mt5_history_query_evidence
  add constraint mt5_history_query_evidence_success_bounds_check check (
    result_state not in ('query_succeeded', 'empty_valid_result')
    or (
      (earliest_returned_at is null or earliest_returned_at >= requested_start_at)
      and (latest_returned_at is null or latest_returned_at <= requested_end_at)
    )
  );

-- Replace as the existing owner; the migration caller deliberately does not
-- inherit that role. Restore the restricted schema privilege afterward.
grant create on schema private to aurum_function_owner;
set local role aurum_function_owner;

create or replace function private.m2_history_evidence_valid(
  evidence jsonb,
  expected_kind text
)
returns boolean
language plpgsql
immutable
security definer
set search_path = ''
as $function$
declare
  requested_start timestamptz;
  requested_end timestamptz;
  query_completed timestamptz;
  earliest_returned timestamptz;
  latest_returned timestamptz;
  result_count integer;
  result_name text;
  timestamp_key text;
begin
  if expected_kind not in ('orders', 'deals')
    or not private.jsonb_exact_keys(evidence, array[
      'earliest_returned_at', 'history_kind', 'latest_returned_at',
      'query_completed_at', 'reason_code', 'requested_end_at',
      'requested_start_at', 'result_state', 'returned_count'
    ])
    or evidence ->> 'history_kind' <> expected_kind
    or evidence ->> 'returned_count' !~ '^[0-9]+$'
    or evidence ->> 'result_state' not in (
      'query_succeeded', 'empty_valid_result', 'query_failed',
      'window_incomplete', 'window_unknown'
    )
    or evidence ->> 'reason_code' !~ '^[A-Z][A-Z0-9_]{0,159}$' then
    return false;
  end if;

  -- Check raw JSON before timestamptz can round a seventh fractional digit.
  -- Only the three optional timestamp fields may be null. Keep the common
  -- ISO transport shape: whole seconds or 1-6 fractional digits, Z or +/-HH:MM.
  foreach timestamp_key in array array[
    'requested_start_at', 'requested_end_at', 'query_completed_at',
    'earliest_returned_at', 'latest_returned_at'
  ] loop
    if evidence -> timestamp_key = 'null'::jsonb
      and timestamp_key in (
        'query_completed_at', 'earliest_returned_at', 'latest_returned_at'
      ) then
      continue;
    end if;
    if pg_catalog.jsonb_typeof(evidence -> timestamp_key) is distinct from 'string'
      or evidence ->> timestamp_key !~
        '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' then
      return false;
    end if;
  end loop;

  requested_start := (evidence ->> 'requested_start_at')::timestamptz;
  requested_end := (evidence ->> 'requested_end_at')::timestamptz;
  query_completed := (evidence ->> 'query_completed_at')::timestamptz;
  earliest_returned := (evidence ->> 'earliest_returned_at')::timestamptz;
  latest_returned := (evidence ->> 'latest_returned_at')::timestamptz;
  result_count := (evidence ->> 'returned_count')::integer;
  result_name := evidence ->> 'result_state';

  if requested_start >= requested_end
    or (query_completed is not null and query_completed < requested_end) then
    return false;
  end if;
  if (earliest_returned is null) <> (latest_returned is null)
    or (earliest_returned is not null and earliest_returned > latest_returned) then
    return false;
  end if;
  if result_name in ('query_succeeded', 'empty_valid_result') and (
    earliest_returned < requested_start or latest_returned > requested_end
  ) then
    return false;
  end if;
  if (result_name = 'query_succeeded'
    and evidence ->> 'reason_code' <> 'HEALTHY') or (
    result_name = 'empty_valid_result'
    and evidence ->> 'reason_code' <> 'HISTORY_EMPTY_VALID_RESULT'
  ) or (
    result_name = 'query_failed'
    and evidence ->> 'reason_code' <> 'HISTORY_QUERY_FAILED'
  ) or (
    result_name in ('window_incomplete', 'window_unknown')
    and evidence ->> 'reason_code' <> 'HISTORY_WINDOW_INCOMPLETE'
  ) then
    return false;
  end if;
  if result_name = 'query_succeeded' and (
    query_completed is null
    or result_count = 0
    or earliest_returned is null
  ) then
    return false;
  end if;
  if result_name = 'empty_valid_result' and (
    query_completed is null
    or result_count <> 0
    or earliest_returned is not null
  ) then
    return false;
  end if;
  if result_name = 'query_failed' and (
    query_completed is null
    or result_count <> 0
    or earliest_returned is not null
  ) then
    return false;
  end if;
  if result_name = 'window_unknown' and (
    query_completed is not null
    or result_count <> 0
    or earliest_returned is not null
  ) then
    return false;
  end if;
  return true;
exception when others then
  return false;
end
$function$;

reset role;
revoke create on schema private from aurum_function_owner;
