# Windows MT5 Read-Only Worker

## Scope

Milestone 2 has the release status **COMPLETE WITH DOCUMENTED LIMITATIONS**. The final heartbeat/liveness local gates and Pull Request run `33541088560` passed on 2026-09-02; all three required jobs verified implementation commit `3e25007`. The Worker observes one already-open MetaTrader 5 Demo terminal for canonical `XAUUSD`. The environment remains `DEMO_ONLY`, runtime mode remains `SHADOW`, maximum permitted volume remains `0.01`, maximum open Positions remains one, and a Stop Loss remains mandatory for any future proposal. This milestone contains no strategy, proposal generation, Risk Engine, approval, command consumer, order execution, broker write, or Position mutation. Milestone 3 is not started or authorized.

The optional native dependency is exactly:

```text
Python 3.13.7
MetaTrader5==5.0.6090
Windows only
```

Normal Linux installation and CI do not install MetaTrader5. Install the boundary on Windows with `pnpm worker:install:mt5`.

## Native API boundary

The only allowed native methods are:

```text
initialize
shutdown
version
last_error
terminal_info
account_info
symbols_get
symbol_info
symbol_info_tick
copy_rates_from_pos
copy_rates_range
positions_get
orders_get
history_orders_get
history_deals_get
```

Calls are direct and statically visible in `native_mt5.py`; a process-wide lock serializes them. Lazy import keeps non-Windows systems package-independent. An explicit absolute terminal executable path is mandatory, and `initialize()` receives that path as its sole positional argument. It receives no login, password, server, or other credential parameter. Shutdown remains finally-safe after initialization begins.

The following remain forbidden:

```text
order_send
order_check
order_calc_profit
order_calc_margin
login
symbol_select
market_book_*
every broker write or Position modification
```

Dynamic lookup or dispatch of MT5 calls is also forbidden. The syntax-aware runtime scanner and native-adapter AST test enforce the boundary.

## Configuration

Only these local variables are recognized:

```text
AURUM_MT5_TERMINAL_PATH
AURUM_MT5_BROKER_SYMBOL
AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT
AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT
AURUM_MT5_MAX_TICK_AGE_SECONDS
AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS
AURUM_MT5_CANDLE_LIMIT
AURUM_MT5_HISTORY_WINDOW_HOURS
AURUM_MT5_TICK_POLL_SECONDS
AURUM_MT5_HEARTBEAT_VALID_FOR_SECONDS
AURUM_MT5_POSITION_POLL_SECONDS
AURUM_MT5_FULL_RECONCILIATION_SECONDS
AURUM_MT5_RECONNECT_MAX_SECONDS
AURUM_MT5_READONLY_SMOKE
```

`.env.example` contains empty names/defaults only. There is no password variable. Do not put local values in Git, logs, screenshots, prompts, or browser configuration.

The conservative defaults are 5 seconds for lightweight tick polling, 15 seconds for Position/active-Order observation, and 600 seconds for full reconciliation. Tick polling is bounded to 1–30 seconds. Component-heartbeat TTL defaults to 30 seconds, is bounded to 15–300 seconds, and must be at least three times the configured tick interval; invalid combinations are rejected rather than weakened. The seeded expected heartbeat interval is 15 seconds for all three enabled execution components. The MT5 eligibility read model separately rejects a latest-tick observation older than 60 seconds, so heartbeat liveness never substitutes for current market evidence.

`AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT` is a local smoke-only operator assertion captured before the run. It can make the smoke compare against an already known fingerprint; it must never be populated from the observation produced by that same run. The deployed database-backed Worker always reads the immutable owner-scoped confirmed binding instead.

## Account and symbol safety

`account_info()` may expose login and server values transiently. The adapter immediately produces `••••` plus the last four login digits, a short masked server label, and domain-separated SHA-256 fingerprints. Account holder name is ignored. Raw values never enter Pydantic output, persistence, incidents, UI, snapshots, or test output.

- Demo plus an expected matching fingerprint is `verified_demo_bound` and eligible for read-only health.
- Demo without an expected fingerprint is `verified_demo_unbound`, diagnostic only, and never healthy.
- Real, contest, unknown, unavailable, or mismatched identity is blocked without override.

Symbol discovery returns candidates only. It never calls `symbol_select()` and never auto-binds. A name such as `XAUUSD`, `XAUUSDm`, `XAUUSD.a`, or `GOLD` qualifies only when the native specification explicitly reports base currency `XAU` and profit currency `USD`; names and descriptions are never used to infer currencies. Currency values are whitespace-trimmed but never case-normalized or rewritten, so malformed casing fails closed. The configured name selects a candidate but does not confirm it. Ambiguous qualifying aliases block.

The durable confirmed binding is an immutable owner/account record containing canonical symbol, broker symbol, confirmed specification fingerprint, confirmation status, confirmation actor/time, and positive version. The latest symbol observation is separate append-only evidence and never becomes confirmation. No production browser or Worker confirmation action exists in this milestone. Missing confirmation produces `SYMBOL_SPEC_CONFIRMATION_REQUIRED`; a different observed fingerprint produces `SYMBOL_SPEC_CHANGED` on every cycle until an explicitly authorized/manual setup creates a new confirmed version. The operator must still make the symbol visible manually in Market Watch.

Symbol evidence appends when the specification fingerprint or material usability state/reason changes, including a later state reversion. Consecutive identical observations are suppressed, so periodic full reconciliation does not create unbounded duplicate rows.

## Decimal, ticket, and time policy

All native numeric values are converted with `Decimal(str(value))`; NaN and infinity are rejected. Decimal JSON boundaries are canonical strings, never JavaScript numbers. Ticket identifiers are strings so values above JavaScript's safe integer range remain exact. The shared parity fixture is consumed by Vitest and pytest.

All timestamps are timezone-aware UTC. Tick age and future-clock drift are explicit. Candle requests are capped at 2,000 records and use one centralized duration map: M1=60, M5=300, M15=900, H1=3,600 seconds. A candle is complete exactly when `open_at + timeframe_duration <= current_utc_time`. `include_current=true` retains an active bucket as incomplete but does not mislabel closed historical rows; the default filters incomplete buckets. Rows remain ordered and duplicate-free, OHLC constraints are validated, invalid timestamps map to bounded read failures, and missing intervals produce gap metadata.

Order/deal history is capped at 168 hours, sanitizes comments, excludes sensitive fields, and records current evidence separately for both queries. An empty native tuple is a valid empty result with reason `HISTORY_EMPTY_VALID_RESULT`; native `None` is a query failure. Evidence records a strictly positive requested window, completion at or after its end, returned count and returned-time bounds, result state, and a safe reason. Completing a bounded request does not claim broker retention outside that request.

## Polling, health, and reconciliation

The polling service has one cancellable non-daemon thread, bounded exponential reconnect backoff, injected jitter for deterministic tests, and a terminal shutdown barrier. No API call is permitted after shutdown. Three independently typed cadences separate 5-second tick/connection reads, 15-second Position plus active-Order observation, and 600-second full safety reconciliation by default. Startup and reconnect each require one full reconciliation before health can become Healthy. Lightweight polling continues at its bounded cadence while a connected read-capable state is degraded or blocked, preserving current liveness without restoring Healthy. A stable blocked condition does not trigger a full cycle on every short poll; a material account/tick/Position/active-Order change or recovery requires one new full reconciliation. Only full reconciliation performs bounded Order/Deal history queries or creates reconciliation rows; a normal short poll does neither.

### Component heartbeat ownership

The long-running poller has one central publication path and owns exactly three typed components:

- `execution.worker` (“Aurum Worker”) is authoritative for the read-only Worker. It may be Healthy only when the poller is running, the Terminal is connected, the most recent authoritative full reconciliation is Healthy, `reconciliation_required` is false, and no current fatal Worker failure exists. A Degraded full result remains Degraded; blocked or unavailable maps to Failed.
- `execution.mt5_adapter` (“การเชื่อมต่อ MT5”) describes only Terminal/API connectivity and account-read safety. Connected calls plus a verified bound Demo account are Healthy. A connected verified Demo account without a binding is Degraded. Disconnected/unavailable Terminal state, Real or Contest account, unknown account mode, binding mismatch, or native access conflict is Failed.
- `execution.market_data` (“ข้อมูลตลาด XAU/USD”) describes only the current tick. Its exact mapping is `LIVE → healthy/HEALTHY`, `DELAYED → degraded/TICK_DELAYED`, `STALE → failed/TICK_STALE`, `FUTURE_INVALID → failed/TICK_FROM_FUTURE`, and `UNAVAILABLE → failed/TICK_UNAVAILABLE`.

Full reconciliation publishes or renews all three components from the authoritative result. A successful lightweight tick poll renews all three, but preserves or lowers the prior Worker state. A Position/active-Order poll renews Worker and MT5 adapter only; it never marks market data Healthy without a current tick observation. On adapter/poll failure, the poller attempts one bounded Failed report for the affected components and preserves the original safe reason. A database heartbeat-reporting failure is not recursively retried.

### Authoritative health cap

Short polling can renew the expiry of an already-authoritative Healthy Worker or preserve a Degraded/Failed Worker while safe reads continue. It can never promote Degraded or Failed to Healthy. `reconciliation_required` always prevents Worker Healthy, including after a fresh live tick. Position/Order-set changes, material account/tick changes, and recovery from non-live market data set that gate; only a successful full reconciliation clears it.

A component Healthy state is deliberately narrow. Healthy MT5 adapter means that the read-only Terminal/account boundary is functioning; Healthy market data means that the latest tick is live. Neither state implies proposal, strategy, risk, approval, command, execution, or trading eligibility, and neither can clear a blocked reconciliation.

Healthy requires all of the following:

- package/platform boundary available;
- connected terminal;
- verified bound Demo account;
- confirmed usable XAUUSD broker symbol;
- fresh valid tick;
- completed clean reconciliation;
- successful observation reporting.

Startup, reconnect, the full-reconciliation schedule, and explicit inconsistencies compare current broker observations with the separately confirmed database binding. Categories include:

```text
UNEXPECTED_BROKER_POSITION
DATABASE_POSITION_MISSING_AT_BROKER
UNEXPECTED_ACTIVE_ORDER
DATABASE_ORDER_MISSING_AT_BROKER
EXECUTION_RESULT_UNCERTAIN
ACCOUNT_CHANGED
SERVER_CHANGED
SYMBOL_SPEC_CHANGED
SYMBOL_SPEC_CONFIRMATION_REQUIRED
HISTORY_QUERY_FAILED
HISTORY_WINDOW_INCOMPLETE
CLOCK_INCONSISTENCY
```

Mismatches and safe incidents block or degrade health. A current Order or Deal history failure/incomplete result prevents healthy state; no stale boolean is reused. Mismatch append and completion serialize on the owner-scoped parent run, completion requires the exact normalized persisted-child and report mismatch sets, and completed runs reject new mismatch evidence. Reconciliation never sends, cancels, modifies, or closes anything and never transitions a command. Latest-tick and component-heartbeat persistence use bounded versioned upserts and do not append a security-audit row for routine telemetry. Important lifecycle incidents and security-sensitive actions retain their existing audit paths.

## Supabase and Web boundary

Six tables persist sanitized state: `mt5_account_observations`, `mt5_symbol_observations`, `mt5_latest_tick_observations`, `mt5_reconciliation_runs`, `mt5_reconciliation_mismatches`, and `mt5_history_query_evidence`. The existing append-only `broker_symbols` versions hold explicit confirmation metadata. Every application table enables and forces RLS. Authenticated users can read their own rows only. The browser cannot write them, and the Worker cannot perform direct DML.

Seven Worker-only RPCs record/read observation and reconciliation state. They derive owner and Worker identity from claims, validate exact payload keys, use pinned empty search paths, are owned by a NOLOGIN function owner, and reject public/browser execution. The existing reconciliation-completion RPC atomically persists exactly the current Order and Deal evidence; no confirmation RPC was added. The existing heartbeat RPC keeps its signature but is replaced in an additive migration so only the three component codes, producer states `healthy`/`degraded`/`failed`, and TTL values 15–300 are accepted. Its owner derivation, stale-write rejection, forced-RLS boundary, revokes, and Worker-only grant remain intact. Routine tick and heartbeat telemetry intentionally omit security-audit growth.

The Web Console uses owner-scoped selects and maps rows through strict Zod contracts. It exposes masked identity, symbol/specification, latest tick, safe health, counts, and reconciliation evidence only. A missing, expired, duplicate, or invalid heartbeat becomes derived `unknown`, and invalid producer detail is not exposed. A healthy MT5 eligibility projection additionally requires a current tick observation, a live tick, a usable symbol, successful Order and Deal evidence, zero mismatches, and exact agreement between the latest account/symbol/tick identifiers and the matched reconciliation. Component Healthy alone is insufficient. The console has no MT5 action buttons.

## Optional real-terminal smoke

The command is:

```text
pnpm worker:mt5:smoke
```

It requests no credentials and performs allowed reads only. Outcomes and exit codes are authoritative once the operator opts in:

- `NOT RUN`, exit `0`: only when `AURUM_MT5_READONLY_SMOKE` is not `1`, or no terminal path was configured before the workflow begins;
- `PASSED`, exit `0`: only after every enabled terminal/account/canonical-symbol/specification/tick/candle/Position/Order/history/reconciliation check and clean shutdown succeeds;
- `BLOCKED`, exit `2`: an opted-in safety or policy condition such as non-Demo account, binding/canonical mismatch, stale tick, or reconciliation mismatch;
- `FAILED`, exit `3`: an opted-in technical failure such as missing package, invalid path, initialization failure, unavailable data, persistence failure, unexpected error, or failed shutdown.

Safe output contains a bounded reason code and never raw login, account name, full server, full path, native error detail, exception, or credential. A precondition-only not-run result is:

```text
NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET
```

CI never runs this command. A `NOT RUN` result is recorded as not run, not passed. Windows CI installs/imports the exact package and exercises the wrapper without a Terminal or credentials; that is boundary evidence, not a real-terminal smoke pass.

Milestone 2 completion result in this workspace:

```text
NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET
```

The optional official package was installed and imported locally, but no explicit Terminal path, broker symbol, opt-in flag, or already-open verified Demo session was supplied. This result is therefore not counted as a passing real-terminal smoke test.

## Test evidence and limits

The deterministic source regressions cover account modes, strict connected state, actual XAU/USD validation and alias behavior, immutable confirmation comparison across repeated cycles, decimal/time validation, bucket-based candles, independent Order/Deal evidence, separated polling cadences, component allowlists, continuous heartbeat renewal, authoritative Worker caps, `reconciliation_required`, all five market-data mappings, persistence failure, reconnect backoff, cancellation, authoritative smoke exit codes, and no calls after shutdown. Web source regressions cover renewed-versus-expired heartbeats, missing/invalid evidence, blocked Worker state, delayed market data, Thai labels, and sensitive-field exclusion. Database source plans cover 400 assertions across nine pgTAP suites, including bounded repeated tick/heartbeat upserts, no routine audit growth, forced RLS, owner isolation, and least privilege.

The final local run passed format, lint, TypeScript/Python type-check, 88 TypeScript tests, 233 Worker tests, production builds, security scans, dependency checks, two clean database resets, lint, 400 pgTAP assertions, four concurrent-claim assertions, and generated-type freshness. Pull Request run `33541088560` passed `quality`, `database`, and `windows-mt5-boundary` on implementation commit `3e25007`. The Windows job proves the package/native boundary without a Terminal; it does not replace the real-terminal smoke, which remains `NOT RUN`.

The fake does not prove a particular broker terminal, symbol naming convention, local installation, network availability, or hosted deployment. Those remain explicit operator/environment limitations. Milestone 3 is not started.
