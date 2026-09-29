begin;
create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to aurum_worker,aurum_function_owner,authenticated;
grant execute on all functions in schema extensions to aurum_worker,aurum_function_owner,authenticated;
set local search_path = public,extensions;
set local timezone = 'UTC';
select no_plan();

select has_table('public','shadow_cycles','immutable research cycles exist');
select has_table('public','shadow_outcome_events','separate quote-only outcome journal exists');
select is((select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname in ('shadow_cycles','shadow_outcome_events')
    and c.relrowsecurity and c.relforcerowsecurity),2::bigint,'both Shadow tables FORCE RLS');
select ok(not has_table_privilege(role_name,relation_name,privilege_name),
  role_name || ' has no ' || privilege_name || ' on ' || relation_name)
from unnest(array['anon','authenticated','aurum_worker','aurum_function_owner']) role_name
cross join unnest(array['public.shadow_cycles','public.shadow_outcome_events']) relation_name
cross join unnest(array['UPDATE','DELETE','TRUNCATE']) privilege_name;
select ok(not has_table_privilege(role_name,relation_name,'INSERT'),role_name || ' cannot directly insert ' || relation_name)
from unnest(array['anon','authenticated','aurum_worker']) role_name
cross join unnest(array['public.shadow_cycles','public.shadow_outcome_events']) relation_name;
select ok(not has_table_privilege('aurum_worker',relation_name,'SELECT'),'Worker reads via bounded RPC only: ' || relation_name)
from unnest(array['public.shadow_cycles','public.shadow_outcome_events']) relation_name;
select ok(has_function_privilege('aurum_worker',signature,'EXECUTE')
  and not has_function_privilege('anon',signature,'EXECUTE')
  and not has_function_privilege('authenticated',signature,'EXECUTE'),
  'Worker-only RPC ' || signature)
from unnest(array['public.worker_read_shadow_context(uuid)','public.worker_read_shadow_cycles(uuid,text)',
  'public.worker_record_shadow_cycle(jsonb)','public.worker_append_shadow_outcome(jsonb)']) signature;
select ok(p.prosecdef and pg_get_userbyid(p.proowner)='aurum_function_owner'
  and p.proconfig @> array['search_path=""'], 'secured empty-path owner: ' || p.proname)
from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname in ('public','private')
  and (p.proname like 'm3_%' or p.proname like 'worker_%shadow%');
select ok(not has_function_privilege('aurum_worker',p.oid,'EXECUTE')
  and not has_function_privilege('authenticated',p.oid,'EXECUTE')
  and not has_function_privilege('anon',p.oid,'EXECUTE'), 'private helper not exposed: ' || p.proname)
from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='private' and p.proname like 'm3_%';

create temporary table shadow_baseline as select
  (select count(*) from public.system_commands) commands,
  (select count(*) from public.trade_decisions) decisions,
  (select count(*) from public.broker_orders) orders,
  (select count(*) from public.trade_executions) executions,
  (select count(*) from public.positions) positions;

-- Native-shaped fictional evidence: no native session or broker access.
select set_config('request.jwt.claims','{"role":"authenticated","sub":"00000000-0000-4000-8000-000000000201"}',true);
insert into public.broker_symbols
select (jsonb_populate_record(null::public.broker_symbols,to_jsonb(b) || jsonb_build_object(
  'id','00000000-0000-4000-8000-000000009311',
  'specification_version','mt5-spec-v1:' || repeat('c',64),
  'confirmed_specification_fingerprint','mt5-spec-v1:' || repeat('c',64),
  'confirmation_version',2,'confirmed_at',now()-interval '1 minute',
  'fetched_at',now()-interval '1 minute'))).*
from public.broker_symbols b where b.id='00000000-0000-4000-8000-000000000311';
insert into public.mt5_account_observations(owner_id,worker_id,account_fingerprint,server_fingerprint,
  masked_login,masked_server,trade_mode,verification_state,currency,leverage,observed_at,source,adapter_version,trace_id,schema_version)
values('00000000-0000-4000-8000-000000000201','shadow-test','mt5-account-v1:'||repeat('a',64),
  'mt5-server-v1:'||repeat('b',64),'••••1234','Demo…abcd','demo','verified_demo_bound','USD',100,
  now()-interval '2 seconds','mt5','native-v1','shadow-test-account','1');
insert into public.mt5_reconciliation_runs(id,owner_id,worker_id,status,outcome,reason_code,
  account_fingerprint,server_fingerprint,broker_symbol,symbol_specification_fingerprint,
  open_position_count,active_order_count,order_history_count,deal_history_count,mismatch_count,
  report_hash,trace_id,started_at,completed_at)
values('00000000-0000-4000-8000-000000009401','00000000-0000-4000-8000-000000000201',
  'shadow-test','completed','matched','HEALTHY','mt5-account-v1:'||repeat('a',64),
  'mt5-server-v1:'||repeat('b',64),'XAUUSD','mt5-spec-v1:'||repeat('c',64),0,0,0,0,0,
  repeat('a',32),'shadow-test-report',now()-interval '4 seconds',now()-interval '2 seconds');
insert into public.mt5_history_query_evidence(owner_id,reconciliation_id,history_kind,requested_start_at,
  requested_end_at,query_completed_at,returned_count,result_state,reason_code)
select '00000000-0000-4000-8000-000000000201','00000000-0000-4000-8000-000000009401',kind,
  now()-interval '1 day',now()-interval '4 seconds',now()-interval '3 seconds',0,'empty_valid_result','HISTORY_EMPTY_VALID_RESULT'
from unnest(array['orders','deals']) kind;

create temporary table shadow_payloads as
select jsonb_build_object(
  'schema_version','shadow-cycle-v1','pipeline_version','shadow-pipeline-v1',
  'strategy_version','sma-atr-shadow-v1','eligibility_version','shadow-eligibility-v1',
  'id','00000000-0000-4000-8000-000000009501','owner_id','00000000-0000-4000-8000-000000000201',
  'trading_account_id','00000000-0000-4000-8000-000000000301','trace_id','00000000-0000-4000-8000-000000009502',
  'cycle_key',repeat('d',64),'evaluated_at',now()-interval '1 second',
  'environment','DEMO_ONLY','runtime_mode','SHADOW','source','mt5','grants_eligibility',false,
  'status','PROPOSAL','reason_codes',jsonb_build_array('RESEARCH_ONLY'),
  'policy_version_id','00000000-0000-4000-8000-000000000332','policy_version',1,'mode_version',1,
  'market',jsonb_build_object(
    'snapshot_id','00000000-0000-4000-8000-000000009503','feature_id','00000000-0000-4000-8000-000000009504',
    'reconciliation_id','00000000-0000-4000-8000-000000009401','input_digest',repeat('e',64),
    'account_fingerprint','mt5-account-v1:'||repeat('a',64),'server_fingerprint','mt5-server-v1:'||repeat('b',64),
    'specification_fingerprint','mt5-spec-v1:'||repeat('c',64),
    'adapter_version','native-v1','market_adapter_version','native-v1','market_time_policy','utc_epoch_v1','broker_symbol','XAUUSD',
    'captured_at',now()-interval '1 second','tick_at',now()-interval '1 second',
    'last_bar_closed_at',date_trunc('minute',now()-interval '1 second'),
    'bid','3000','ask','3000.02','point','0.01','tick_size','0.01','fast_sma','3000','slow_sma','2999','atr','1',
    'bars',(select jsonb_agg(jsonb_build_object('open_at',date_trunc('minute',now()-interval '1 second')-n*interval '1 minute',
      'open','3000','high','3001','low','2999','close','3000') order by n desc) from generate_series(1,6) n)),
  'candidate',jsonb_build_object('id','00000000-0000-4000-8000-000000009505','direction','BUY',
    'created_at',now()-interval '1 second','expires_at',now()+interval '29 seconds',
    'entry_price','3000.02','stop_loss_price','2998','take_profit_price','3006'),
  'risk',jsonb_build_object('version','shadow-risk-v1','outcome','PASS',
    'checks',jsonb_build_array(jsonb_build_object('code','RISK_COMPLETE','passed',true)),
    'input_digest',repeat('a',64),
    'source_receipts',(select jsonb_agg(jsonb_build_object('kind',kind,'source_id','fixture-source','source_version','v1',
      'evidence_digest',repeat('b',64),'observed_at',now()-interval '2 seconds','valid_until',now()+interval '1 minute',
      'covered_from',null,'covered_until',null) order by kind) from unnest(array['ledger','safety','news','costs']) kind),
    'calculated_volume','0.01','estimated_loss_usd','2','estimated_net_reward_usd','5'),
  'eligibility',jsonb_build_object('outcome','BLOCK','checks',jsonb_build_array(jsonb_build_object('code','SAMPLE_SIZE','passed',false)),
    'sample_count',0,'minimum_sample_size',30,'calibrated',false)
) proposal;
alter table shadow_payloads add column blocked jsonb;
update shadow_payloads set blocked=proposal || jsonb_build_object('id','00000000-0000-4000-8000-000000009511',
  'cycle_key',repeat('f',64),'status','BLOCK','reason_codes',jsonb_build_array('SOURCE_UNAVAILABLE'),
  'policy_version_id',null,'policy_version',null,'mode_version',null,'market',null,'candidate',null,'risk',null,'eligibility',null);
grant select on shadow_payloads to aurum_worker,aurum_function_owner,authenticated;

set local role aurum_worker;
select set_config('request.jwt.claims','{}',true);
select is(worker_read_shadow_context('00000000-0000-4000-8000-000000000301')->>'result_code','WORKER_UNAUTHORIZED','missing claim denied');
select is(worker_record_shadow_cycle((select blocked from shadow_payloads))->>'result_code','WORKER_UNAUTHORIZED','anonymous-shaped Worker denied');
select set_config('request.jwt.claims','{"role":"aurum_worker","owner_id":"00000000-0000-4000-8000-000000000201","worker_id":"shadow-test"}',true);
select is(worker_read_shadow_context('00000000-0000-4000-8000-000000000301')->>'result_code','CONTEXT_READY','fixture Demo Shadow context ready');
select is(worker_read_shadow_context('00000000-0000-4000-8000-000000009999')->>'result_code','ACCOUNT_UNAVAILABLE','unknown account denied');
select is(worker_record_shadow_cycle((select proposal from shadow_payloads))->>'result_code','CYCLE_RECORDED','valid non-eligible research proposal records');
select is(worker_record_shadow_cycle((select proposal from shadow_payloads))->>'result_code','IDEMPOTENT_REPLAY','exact proposal replay');
select is(worker_record_shadow_cycle((select jsonb_set(proposal,'{reason_codes}','["CHANGED"]') from shadow_payloads))->>'result_code','CYCLE_CONFLICT','changed replay fails closed');
select is(worker_record_shadow_cycle((select blocked from shadow_payloads))->>'result_code','CYCLE_RECORDED','early BLOCK has no invented market or risk');
select is(worker_record_shadow_cycle((select blocked from shadow_payloads))->>'result_code','IDEMPOTENT_REPLAY','exact early BLOCK replay');
select is(worker_record_shadow_cycle((select blocked || jsonb_build_object('id','00000000-0000-4000-8000-000000009521','cycle_key',repeat('1',64),'status','WAIT') from shadow_payloads))->>'result_code','CYCLE_RECORDED','WAIT without a sized candidate records');
select is(worker_record_shadow_cycle((select jsonb_set(blocked,'{owner_id}','"00000000-0000-4000-8000-000000009201"') from shadow_payloads))->>'result_code','OWNER_MISMATCH','cross-owner payload rejected');
select is(worker_read_shadow_cycles('00000000-0000-4000-8000-000000000301',repeat('d',64))#>>'{data,cycles,0,id}',
  '00000000-0000-4000-8000-000000009501','exact-key restart reads original cycle');
select is(jsonb_array_length(worker_read_shadow_cycles('00000000-0000-4000-8000-000000000301')#>'{data,cycles}'),3,'bounded restart lists three recorded cycles');
select is(worker_read_shadow_cycles('00000000-0000-4000-8000-000000000301','bad')->>'result_code','INVALID_CYCLE_KEY','malformed key rejected');
reset role;

-- Current control-plane blockers are observed, never consumed or overridden.
update public.trading_modes set system_state='paused' where trading_account_id='00000000-0000-4000-8000-000000000301';
set local role aurum_worker;
select is(worker_read_shadow_context('00000000-0000-4000-8000-000000000301')->>'result_code','SAFETY_STATE_BLOCKED','paused mode is not ready');
select is(worker_record_shadow_cycle((select proposal || jsonb_build_object('id','00000000-0000-4000-8000-000000009522','cycle_key',repeat('2',64)) from shadow_payloads))->>'result_code','CURRENT_STATE_BLOCKED','new proposal rechecks paused mode');
select is(worker_record_shadow_cycle((select proposal from shadow_payloads))->>'result_code','IDEMPOTENT_REPLAY','historical exact replay is independent of later pause');
reset role;
update public.trading_modes set system_state='running' where trading_account_id='00000000-0000-4000-8000-000000000301';
insert into public.system_commands(id,owner_id,type,payload,status,requested_by,requested_at,idempotency_key,expires_at,priority)
values('00000000-0000-4000-8000-000000009701','00000000-0000-4000-8000-000000000201',
  'ACTIVATE_EMERGENCY_STOP','{"reason":"Fixture safety test"}','pending','00000000-0000-4000-8000-000000000201',now(),
  'shadow-safety-fixture',now()+interval '1 minute',100);
set local role aurum_worker;
select is(worker_read_shadow_context('00000000-0000-4000-8000-000000000301')->>'result_code','SAFETY_STATE_BLOCKED','pending emergency stop blocks ready context');
select is(worker_record_shadow_cycle((select proposal || jsonb_build_object('id','00000000-0000-4000-8000-000000009522','cycle_key',repeat('2',64)) from shadow_payloads))->>'result_code','CURRENT_STATE_BLOCKED','pending stop blocks new proposal');
reset role;
delete from public.system_commands where id='00000000-0000-4000-8000-000000009701';

-- Structural parity includes invalid top-level JSON before array/object traversal.
set local role aurum_function_owner;
select ok(not private.m3_cycle(value),'invalid top-level cycle: ' || value::text)
from unnest(array['null'::jsonb,'[]','1','true','"text"','{}']) value;
select ok(private.m3_cycle(proposal) and private.m3_cycle(blocked),'both complete and unavailable-evidence envelopes validate') from shadow_payloads;
select ok(not private.m3_cycle(proposal || jsonb_build_object('unknown',true)),'unknown top-level keys rejected') from shadow_payloads;
select ok(not private.m3_cycle(proposal - key_name),'missing required key rejected: ' || key_name)
from shadow_payloads cross join unnest(array['owner_id','market','risk','source','grants_eligibility','policy_version_id']) key_name;
select ok(not private.m3_cycle(jsonb_set(proposal,array['market',key_name],to_jsonb(bad))), 'decimal rejection ' || key_name || ':' || bad)
from shadow_payloads cross join unnest(array['bid','ask','point','tick_size','fast_sma','slow_sma','atr']) key_name
cross join unnest(array['NaN','Infinity','1e3','+1','-1','01','0.','1.2.3']) bad;
select ok(not private.m3_cycle(jsonb_set(proposal,'{market,bid}','3000')),'JSON number cannot replace decimal string') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{market,bid}',to_jsonb(repeat('1',97)))),'decimal length bounded') from shadow_payloads;
select ok(not private.m3_time(to_jsonb(value)),'invalid UTC/precision time: ' || value)
from unnest(array['2026-09-22T00:00:00.1234567Z','2026-09-22T00:00:00+01:00',
  '2026-09-22T00:00:00','2026-02-30T00:00:00Z','2026-09-22T24:00:00Z','2026-09-22T00:00:60Z']) value;
select ok(private.m3_time(to_jsonb(value)),'UTC microsecond time accepted: ' || value)
from unnest(array['2026-09-22T00:00:00Z','2026-09-22T00:00:00.123456Z','2026-09-22T00:00:00+00:00']) value;
select ok(not private.m3_cycle(jsonb_set(proposal,'{market,bars}',value)),'invalid bar array: ' || value::text)
from shadow_payloads cross join unnest(array['null'::jsonb,'{}','[]','1','true']) value;
select ok(not private.m3_cycle(jsonb_set(proposal,'{market,bars,0,low}','"3001"')),'invalid OHLC rejected') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{market,bars,1,open_at}',proposal#>'{market,bars,0,open_at}')),'duplicate/gapped bar time rejected') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{candidate,stop_loss_price}','"3001"')),'mandatory directional stop') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,calculated_volume}','"0.02"')),'absolute 0.01 volume cap') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,outcome}','"BLOCK"')),'risk outcome and checks must agree') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,checks,0,passed}','"true"')),'risk bool cannot coerce') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{eligibility,checks,0,passed}','true')),'sample gate must match missing sample evidence') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{grants_eligibility}','true')),'cannot grant eligibility') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{source}','"fake_mt5"')),'fake production source rejected') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{status}','"WAIT"')),'WAIT cannot retain candidate/risk') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{reason_codes}','["DUPLICATE","DUPLICATE"]')),'duplicate reason rejected') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{market,account_fingerprint}','"mt5-account-v1:fixture"')),'native hash length required') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{market,broker_symbol}','"password=secret"')),'unsafe identifier rejected') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,source_receipts}','[]')),'PASS requires four independent source receipts') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,source_receipts,0,covered_from}','"2026-01-01T00:00:00Z"')),'source coverage must be paired') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,source_receipts,0,kind}',proposal#>'{risk,source_receipts,1,kind}')),'source receipt kinds are unique') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,source_receipts,0,evidence_digest}','"missing"')),'source receipt digest is required') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,source_receipts,0,valid_until}','"2000-01-01T00:00:00Z"')),'source validity is ordered') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,input_digest}','"missing"')),'full risk input digest is required') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,source_receipts,0,observed_at}',to_jsonb(now()-interval '0.5 second'))),'PASS receipt cannot originate after decision') from shadow_payloads;
select ok(not private.m3_cycle(jsonb_set(proposal,'{risk,source_receipts,0,valid_until}',to_jsonb(now()-interval '1.5 seconds'))),'PASS receipt must remain valid at decision') from shadow_payloads;
reset role;

create temporary table shadow_events as select jsonb_build_object(
  'schema_version','shadow-outcome-v1','tracker_version','quote-observed-v1','simulation',true,'grants_eligibility',false,
  'id','00000000-0000-4000-8000-000000009601','owner_id','00000000-0000-4000-8000-000000000201',
  'trading_account_id','00000000-0000-4000-8000-000000000301','cycle_id','00000000-0000-4000-8000-000000009501',
  'sequence',1,'observed_at',now()-interval '0.5 second','status','OBSERVED','reason_code','QUOTE_OBSERVED',
  'bid','3000','ask','3000.02','price_source','mt5','net_pnl_usd',null) event;
grant select on shadow_events to aurum_worker,aurum_function_owner,authenticated;
set local role aurum_worker;
select is(worker_append_shadow_outcome((select event from shadow_events))->>'result_code','OUTCOME_RECORDED','first observed quote appends');
select is(worker_append_shadow_outcome((select event from shadow_events))->>'result_code','IDEMPOTENT_REPLAY','event exact replay');
select is(worker_append_shadow_outcome((select jsonb_set(event,'{bid}','"2999"') from shadow_events))->>'result_code','OUTCOME_CONFLICT','event payload conflict rejected');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009602','sequence',3) from shadow_events))->>'result_code','OUTCOME_SEQUENCE_CONFLICT','skipped sequence rejected');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009602','sequence',2) from shadow_events))->>'result_code','OUTCOME_TIME_INVALID','nonincreasing time rejected');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009602','sequence',2,'observed_at',now(),'status','TARGET_OBSERVED') from shadow_events))->>'result_code','OUTCOME_THRESHOLD_INVALID','unreached target cannot claim observation');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009602','sequence',2,'observed_at',now(),'status','STOP_OBSERVED','bid','2997','ask','2997.02') from shadow_events))->>'result_code','OUTCOME_RECORDED','BUY exit uses bid at stop');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009603','sequence',3,'observed_at',now()+interval '0.1 second') from shadow_events))->>'result_code','OUTCOME_SEQUENCE_CONFLICT','terminal outcome cannot reverse');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009604','cycle_id','00000000-0000-4000-8000-000000009511') from shadow_events))->>'result_code','PROPOSAL_UNAVAILABLE','BLOCK cycle cannot acquire outcomes');
select is(worker_append_shadow_outcome((select jsonb_set(event,'{net_pnl_usd}','"1"') from shadow_events))->>'result_code','INVALID_OUTCOME','quote-only journal never claims realized PnL');
select is(jsonb_array_length(worker_read_shadow_cycles('00000000-0000-4000-8000-000000000301')#>'{data,outcomes}'),2,'restart retrieves complete bounded outcomes');
reset role;

-- These immutable fixture copies isolate quote-observer transition rules from
-- wall-clock current-proposal admission; they do not bypass production RPCs.
set local role aurum_function_owner;
insert into public.shadow_cycles(id,owner_id,trading_account_id,cycle_key,status,evaluated_at,payload)
select (payload->>'id')::uuid,(payload->>'owner_id')::uuid,(payload->>'trading_account_id')::uuid,
  payload->>'cycle_key',payload->>'status',(payload->>'evaluated_at')::timestamptz,payload
from (select proposal || jsonb_build_object('id','00000000-0000-4000-8000-000000009531','cycle_key',repeat('3',64)) payload from shadow_payloads
  union all select jsonb_set(proposal || jsonb_build_object('id','00000000-0000-4000-8000-000000009541','cycle_key',repeat('4',64)),
    '{candidate,expires_at}',to_jsonb(now()-interval '0.25 second')) from shadow_payloads
  union all select jsonb_set(proposal || jsonb_build_object('id','00000000-0000-4000-8000-000000009551','cycle_key',repeat('5',64)),
    '{candidate}',(proposal->'candidate') || jsonb_build_object('direction','SELL','entry_price','3000','stop_loss_price','3002','take_profit_price','2994')) from shadow_payloads) copies;
reset role;
set local role aurum_worker;
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009631',
  'cycle_id','00000000-0000-4000-8000-000000009531','observed_at',now()+interval '10 seconds') from shadow_events))->>'result_code',
  'OUTCOME_GAP_REQUIRES_UNKNOWN','future or gapped quote cannot continue observation');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009631',
  'cycle_id','00000000-0000-4000-8000-000000009531','observed_at',now()+interval '10 seconds','status','UNKNOWN',
  'reason_code','SOURCE_GAP','bid',null,'ask',null,'price_source','unavailable') from shadow_events))->>'result_code',
  'OUTCOME_RECORDED','source gap terminates UNKNOWN without quote or PnL');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009641',
  'cycle_id','00000000-0000-4000-8000-000000009541','observed_at',now(),'status','EXPIRED') from shadow_events))->>'result_code',
  'OUTCOME_RECORDED','observed expiry ends candidate lifetime');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009651',
  'cycle_id','00000000-0000-4000-8000-000000009551','status','TARGET_OBSERVED','bid','2993','ask','2995') from shadow_events))->>'result_code',
  'OUTCOME_THRESHOLD_INVALID','SELL cannot claim target from favorable bid');
select is(worker_append_shadow_outcome((select event || jsonb_build_object('id','00000000-0000-4000-8000-000000009651',
  'cycle_id','00000000-0000-4000-8000-000000009551','status','TARGET_OBSERVED','bid','2993','ask','2994') from shadow_events))->>'result_code',
  'OUTCOME_RECORDED','SELL target observes conservative ask');
select is(worker_append_shadow_outcome((select jsonb_set(event,'{sequence}','33') from shadow_events))->>'result_code',
  'INVALID_OUTCOME','event count is bounded to32');
reset role;

set local role authenticated;
select set_config('request.jwt.claims','{"role":"authenticated","sub":"00000000-0000-4000-8000-000000000201"}',true);
select is((select count(*) from public.shadow_cycles),6::bigint,'owner sees own cycles');
select is((select count(*) from public.shadow_outcome_events),5::bigint,'owner sees own events');
select set_config('request.jwt.claims','{"role":"authenticated","sub":"00000000-0000-4000-8000-000000009201"}',true);
select is((select count(*) from public.shadow_cycles),0::bigint,'other owner cannot read cycles');
select is((select count(*) from public.shadow_outcome_events),0::bigint,'other owner cannot read outcomes');
reset role;
select throws_ok($$update public.shadow_cycles set status='BLOCK' where id='00000000-0000-4000-8000-000000009501'$$,'55000',null,'privileged cycle update rejected');
select throws_ok($$delete from public.shadow_outcome_events where id='00000000-0000-4000-8000-000000009601'$$,'55000',null,'privileged event delete rejected');

select is((select count(*) from public.system_commands),(select commands from shadow_baseline),'no approval or command creation');
select is((select count(*) from public.trade_decisions),(select decisions from shadow_baseline),'no decision creation');
select is((select count(*) from public.broker_orders),(select orders from shadow_baseline),'no broker order creation');
select is((select count(*) from public.trade_executions),(select executions from shadow_baseline),'no execution creation');
select is((select count(*) from public.positions),(select positions from shadow_baseline),'no position mutation');
select * from finish();
rollback;
