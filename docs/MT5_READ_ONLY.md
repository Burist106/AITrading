# Windows MT5 Read-Only Worker

## Scope

Milestone 2 is **IMPLEMENTED — PATCH AND CI VERIFICATION PENDING**. It observes one already-open MetaTrader 5 Demo terminal for canonical `XAUUSD`. The environment remains `DEMO_ONLY`, runtime mode remains `SHADOW`, maximum permitted volume remains `0.01`, maximum open Positions remains one, and a Stop Loss remains mandatory for any future proposal. This milestone contains no strategy, proposal generation, Risk Engine, approval, command consumer, order execution, broker write, or Position mutation. Milestone 3 is not started or authorized.

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
AURUM_MT5_POSITION_POLL_SECONDS
AURUM_MT5_FULL_RECONCILIATION_SECONDS
AURUM_MT5_RECONNECT_MAX_SECONDS
AURUM_MT5_READONLY_SMOKE
```

`.env.example` contains empty names/defaults only. There is no password variable. Do not put local values in Git, logs, screenshots, prompts, or browser configuration.

The conservative defaults are 5 seconds for lightweight tick polling, 15 seconds for Position/active-Order observation, and 600 seconds for full reconciliation. Tick polling is bounded to 1–30 seconds. The Web read model expires its connected/available liveness projection after 60 seconds without a new bounded tick observation, so every valid tick cadence has room for one missed cycle but cannot remain healthy indefinitely.

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

The polling service has one cancellable non-daemon thread, bounded exponential reconnect backoff, injected jitter for deterministic tests, and a terminal shutdown barrier. No API call is permitted after shutdown. Three independently typed cadences separate lightweight tick/connection reads, Position plus active-Order observation, and slower full safety reconciliation. Startup and reconnect each require one full reconciliation before health can become healthy. Lightweight polling continues at its bounded cadence while a connected read-capable state is degraded or blocked, preserving current liveness without restoring Healthy. A stable blocked condition does not trigger a full cycle on every short poll; a material account/tick/Position/active-Order change or recovery requires one new full reconciliation. Only full reconciliation performs bounded Order/Deal history queries or creates reconciliation rows; a normal short poll does neither.

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

Mismatches and safe incidents block or degrade health. A current Order or Deal history failure/incomplete result prevents healthy state; no stale boolean is reused. Mismatch append and completion serialize on the owner-scoped parent run, completion requires the exact normalized persisted-child and report mismatch sets, and completed runs reject new mismatch evidence. Reconciliation never sends, cancels, modifies, or closes anything and never transitions a command. Latest-tick persistence is a bounded upsert and does not append a security-audit row for routine market telemetry.

## Supabase and Web boundary

Six tables persist sanitized state: `mt5_account_observations`, `mt5_symbol_observations`, `mt5_latest_tick_observations`, `mt5_reconciliation_runs`, `mt5_reconciliation_mismatches`, and `mt5_history_query_evidence`. The existing append-only `broker_symbols` versions hold explicit confirmation metadata. Every application table enables and forces RLS. Authenticated users can read their own rows only. The browser cannot write them, and the Worker cannot perform direct DML.

Seven Worker-only RPCs record/read observation and reconciliation state. They derive owner and Worker identity from claims, validate exact payload keys, use pinned empty search paths, are owned by a NOLOGIN function owner, and reject public/browser execution. The existing reconciliation-completion RPC atomically persists exactly the current Order and Deal evidence; no confirmation RPC was added. Existing bounded heartbeat and incident RPCs are reused. Routine tick telemetry intentionally omits security-audit growth.

The Web Console uses owner-scoped selects and maps rows through strict Zod contracts. It exposes masked identity, symbol/specification, latest tick, safe health, counts, and reconciliation evidence only. A healthy projection additionally requires a current tick observation, a live tick, a usable symbol, successful Order and Deal evidence, zero mismatches, and exact agreement between the latest account/symbol/tick identifiers and the matched reconciliation. It has no MT5 action buttons.

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

The deterministic fake proves account modes, strict connected state, actual XAU/USD validation and alias behavior, immutable confirmation comparison across repeated cycles, decimal/time validation, bucket-based candles, independent Order/Deal evidence, separated polling cadences, persistence failure, health policy, replay, reconnect backoff, cancellation, authoritative smoke exit codes, and no calls after shutdown. Windows CI proves exact package installation/import, positional initialization, static native calls, serialization, safe shutdown paths, and scanner enforcement without needing a Terminal. pgTAP proves clean reset, forced RLS, owner isolation, least privilege, immutable confirmation, exact history evidence, bounded tick upsert without per-tick audit, and idempotent reconciliation.

The fake does not prove a particular broker terminal, symbol naming convention, local installation, network availability, or hosted deployment. Those remain explicit operator/environment limitations. Milestone 3 is not started.
