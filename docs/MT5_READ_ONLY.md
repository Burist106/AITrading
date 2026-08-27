# Windows MT5 Read-Only Worker

## Scope

Milestone 2 observes one already-open MetaTrader 5 Demo terminal for canonical `XAUUSD`. The environment remains `DEMO_ONLY`, runtime mode remains `SHADOW`, maximum permitted volume remains `0.01`, maximum open Positions remains one, and a Stop Loss remains mandatory for any future proposal. This milestone contains no strategy, proposal generation, Risk Engine, approval, command consumer, order execution, broker write, or Position mutation.

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

Calls are direct and statically visible in `native_mt5.py`; a process-wide lock serializes them. Lazy import keeps non-Windows systems package-independent. An explicit absolute terminal executable path is mandatory, and `initialize()` receives that path only.

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
AURUM_MT5_MAX_TICK_AGE_SECONDS
AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS
AURUM_MT5_CANDLE_LIMIT
AURUM_MT5_HISTORY_WINDOW_HOURS
AURUM_MT5_POLL_INTERVAL_SECONDS
AURUM_MT5_RECONNECT_MAX_SECONDS
AURUM_MT5_READONLY_SMOKE
```

`.env.example` contains empty names/defaults only. There is no password variable. Do not put local values in Git, logs, screenshots, prompts, or browser configuration.

## Account and symbol safety

`account_info()` may expose login and server values transiently. The adapter immediately produces `••••` plus the last four login digits, a short masked server label, and domain-separated SHA-256 fingerprints. Account holder name is ignored. Raw values never enter Pydantic output, persistence, incidents, UI, snapshots, or test output.

- Demo plus an expected matching fingerprint is `verified_demo_bound` and eligible for read-only health.
- Demo without an expected fingerprint is `verified_demo_unbound`, diagnostic only, and never healthy.
- Real, contest, unknown, unavailable, or mismatched identity is blocked without override.

Symbol discovery returns candidates only. It never calls `symbol_select()` and never auto-binds. The configured symbol, or a previously confirmed owner-scoped database symbol, must be used. The operator must make the symbol visible manually in Market Watch. A usable specification requires currencies, positive point/tick size/contract size/minimum volume/volume step, valid bounds, and a stable normalized fingerprint. A changed fingerprint blocks reconciliation.

## Decimal, ticket, and time policy

All native numeric values are converted with `Decimal(str(value))`; NaN and infinity are rejected. Decimal JSON boundaries are canonical strings, never JavaScript numbers. Ticket identifiers are strings so values above JavaScript's safe integer range remain exact. The shared parity fixture is consumed by Vitest and pytest.

All timestamps are timezone-aware UTC. Tick age and future-clock drift are explicit. Candle requests are capped at 2,000 records, current/incomplete bars are excluded by default, OHLC constraints are validated, and missing intervals produce gap metadata. Order/deal history is capped at 168 hours, distinguishes native failure from a valid empty result, sanitizes comments, and excludes sensitive fields.

## Polling, health, and reconciliation

The polling service has one cancellable non-daemon thread, bounded exponential reconnect backoff, injected jitter for deterministic tests, and a terminal shutdown barrier. No API call is permitted after shutdown.

Healthy requires all of the following:

- package/platform boundary available;
- connected terminal;
- verified bound Demo account;
- confirmed usable XAUUSD broker symbol;
- fresh valid tick;
- completed clean reconciliation;
- successful observation reporting.

Startup and every reconnect compare broker observations with the previous database state before recording the new account observation. Categories are:

```text
UNEXPECTED_BROKER_POSITION
DATABASE_POSITION_MISSING_AT_BROKER
UNEXPECTED_ACTIVE_ORDER
DATABASE_ORDER_MISSING_AT_BROKER
EXECUTION_RESULT_UNCERTAIN
ACCOUNT_CHANGED
SERVER_CHANGED
SYMBOL_SPEC_CHANGED
HISTORY_WINDOW_INCOMPLETE
CLOCK_INCONSISTENCY
```

Mismatches and safe incidents block or degrade health. Reconciliation never sends, cancels, modifies, or closes anything and never transitions a command.

## Supabase and Web boundary

Five tables persist sanitized state: `mt5_account_observations`, `mt5_symbol_observations`, `mt5_latest_tick_observations`, `mt5_reconciliation_runs`, and `mt5_reconciliation_mismatches`. Every table enables and forces RLS. Authenticated users can read their own rows only. The browser cannot write them, and the Worker cannot perform direct DML.

Seven Worker-only RPCs record/read observation and reconciliation state. They derive owner and Worker identity from claims, validate exact payload keys, use pinned empty search paths, are owned by a NOLOGIN function owner, reject public/browser execution, and append audit evidence where appropriate. Existing bounded heartbeat and incident RPCs are reused.

The Web Console uses owner-scoped selects and maps rows through strict Zod contracts. It exposes masked identity, symbol/specification, latest tick, safe health, counts, and reconciliation evidence only. It has no MT5 action buttons.

## Optional real-terminal smoke

The command is:

```text
pnpm worker:mt5:smoke
```

It runs only on Windows when `AURUM_MT5_READONLY_SMOKE=1`, an explicit terminal path, a broker symbol, and an already-open Demo session are present. It requests no credentials and performs allowed reads only. Without every precondition it prints exactly:

```text
NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET
```

CI never runs this command. A NOT RUN result is recorded as not run, not passed.

Milestone 2 completion result in this workspace:

```text
NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET
```

The optional official package was installed and imported locally, but no explicit Terminal path, broker symbol, opt-in flag, or already-open verified Demo session was supplied. This result is therefore not counted as a passing real-terminal smoke test.

## Test evidence and limits

The deterministic fake proves account modes, symbol binding, decimal/time validation, ticks, candles, position/order/history reads, persistence failure, health policy, mismatch detection, replay, reconnect backoff, cancellation, and no calls after shutdown. Windows CI proves exact package installation/import, static native calls, serialization, safe shutdown paths, and scanner enforcement without needing a Terminal. pgTAP proves schema reset, forced RLS, owner isolation, least privilege, safe RPC validation, bounded upsert, audit evidence, and idempotent reconciliation.

The fake does not prove a particular broker terminal, symbol naming convention, local installation, network availability, or hosted deployment. Those remain explicit operator/environment limitations. Milestone 3 is not started.
