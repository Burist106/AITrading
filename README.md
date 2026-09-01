# Aurum Console

Aurum Console is a safety-first control-plane and Windows Worker foundation for researching XAU/USD workflows against a MetaTrader 5 Demo terminal. It is not a profitability claim, an autonomous trading system, or a Live Trading product.

## Current status

- Environment: **`DEMO_ONLY`**
- Asset scope: **`XAU/USD ONLY`** (`XAUUSD` canonical symbol)
- Initial runtime mode: **`SHADOW`**
- Maximum permitted volume: **0.01**
- Maximum open Positions: **1**
- Future executable proposals require a Stop Loss
- Completed: **Bootstrap and Milestone 1**
- Milestone 2 release status: **COMPLETE WITH DOCUMENTED LIMITATIONS**, contingent on the heartbeat/liveness patch passing its final local gates and a new clean-checkout Pull Request run; the local gates passed on 2026-09-02 and the new Pull Request run is pending
- Milestone 3: **NOT STARTED — NOT AUTHORIZED BY THE CURRENT TASK**

Milestone 2 is observation-only. The repository has no broker-write path, no Position modification, no command consumer, and no Live Trading switch. The previously green source-review CI run does not verify the newer heartbeat/liveness changes; the status above must not be treated as re-verified until the new patch HEAD passes all required jobs.

## Architecture

The Next.js Web Console reads owner-scoped, sanitized views. The Python Worker owns local read-only MT5 access behind a typed port. Supabase stores durable owner-scoped domain state and exposes narrowly granted RPCs; forced RLS and a dedicated `aurum_worker` role prevent browser or Worker direct writes to protected tables. Shared TypeScript contracts and cross-language fixtures keep JSON boundaries explicit.

Milestone 2 treats discovery, observation, and confirmation as different states. A broker symbol is XAU/USD only when its native base/profit currencies are `XAU`/`USD`, and an observed fingerprint never confirms itself. Lightweight tick polling, Position/active-Order observation, and full reconciliation default to 5, 15, and 600 seconds; only a full cycle queries Order/Deal history and persists its exact current evidence.

The poller owns three explicit component heartbeats: `execution.worker` (authoritative Worker state), `execution.mt5_adapter` (Terminal/API and Demo-account read safety), and `execution.market_data` (XAU/USD tick freshness). Routine short polls renew the components they actually observe, but the Worker heartbeat remains capped by the last full reconciliation. `reconciliation_required` prevents Worker Healthy, and fresh market data cannot clear that gate. Heartbeats default to a 30-second TTL, are bounded to 15–300 seconds, and must be at least three tick intervals. Missing, expired, duplicate, or invalid heartbeat evidence is displayed as `unknown`. A component reported Healthy describes only its narrow read-only responsibility; it is not trading eligibility.

Latest ticks and component heartbeats are bounded versioned upserts. Neither routine tick updates nor routine heartbeat renewals append security-audit rows; security-sensitive actions and important lifecycle incidents retain their audit paths.

```text
apps/web                 Thai-first Next.js read-only console
apps/worker              Python 3.13 Windows Worker and adapters
packages/contracts       TypeScript/Zod boundary contracts
fixtures                 Deterministic presentation fixtures
contract-fixtures        Cross-language parity corpus
supabase/migrations      Versioned schema, RLS, and secured RPCs
supabase/tests           pgTAP security and lifecycle tests
scripts                  Reproducible build, database, and security checks
docs                     Architecture, safety, decisions, and gates
```

Files under `docs/design-reference/` are visual/behavioral references only. They are not production source, and their `support.js` or `_ds` dependencies must never enter the runtime.

## Local setup

Prerequisites:

- Node.js `24.19.0`
- pnpm `11.24.0`
- Python `3.13.7`
- Docker Desktop for the local Supabase gates
- Windows plus an explicitly configured MT5 Demo terminal only for the optional real read-only smoke test

Install the reproducible JavaScript and Worker development dependencies:

```text
pnpm install --frozen-lockfile
pnpm worker:install
```

On Windows, install the official optional read-only boundary separately:

```text
pnpm worker:install:mt5
```

This pins `MetaTrader5==5.0.6090` for Python `3.13.7`. Normal Linux quality checks do not install it. The optional real-terminal smoke command is disabled unless every explicit local precondition is supplied; see [MT5 read-only runbook](docs/MT5_READ_ONLY.md).

Actual real-terminal smoke status for this patch: **NOT RUN**. No eligible explicitly opted-in local Demo Terminal configuration was supplied; unit tests and Windows import checks are not reported as a real-terminal pass.

Do not add credentials to the repository. Copy variable names from `.env.example` only when local configuration is needed, keep values outside version control, and never configure an MT5 password. The Worker may inspect the account identifier/server returned by the already-open terminal only transiently to verify a masked/hashed binding; raw identifiers never belong in logs, Supabase, browser output, snapshots, prompts, or commits.

## Verification

Run the full non-database gate:

```text
pnpm check
```

The gate includes formatting, lint, TypeScript/Python type checks, unit/component tests, production builds, a tracked-file and Git-history secret scan, and syntax-aware production runtime-boundary checks.

Heartbeat/liveness regression tests cover continuous renewal, authoritative-state caps, tick-freshness mapping, Web expiry handling, bounded database upserts, RLS, and no-audit-growth behavior. The final local run passed 88 TypeScript tests, 233 Worker tests, 400 pgTAP assertions, and four concurrent-claim assertions; format, lint, type-check, production build, generated types, dependency checks, and security scans also passed. The new Pull Request conclusions remain pending and are not claimed here.

Run the dependency checks separately:

```text
pnpm audit --audit-level high
.venv/Scripts/python -m pip check
```

On Linux/macOS use `.venv/bin/python` for the second command.

## Local Supabase workflow

The wrapper starts a disposable, pinned Docker-in-Docker stack and verifies localhost-only bindings. It never links to or pushes a remote Supabase project.

```text
pnpm db:start
pnpm db:reset
pnpm db:reset
pnpm db:lint
pnpm db:test
pnpm db:types:check
pnpm db:stop
```

`pnpm db:check` runs the reset/lint/test/type-drift sequence after the stack is started. No real Supabase credential is required.

## Safety and credential rules

- No Live Trading, alternate environment flag, or hidden execution path.
- No MT5 password is requested, accepted, read, persisted, or logged.
- No full MT5 login, account holder name, full terminal path, privileged Supabase key, token, or cookie appears in browser-visible output or repository history.
- The frontend cannot write MT5 observations or protected broker/order/Position state.
- Ambiguous, stale, incomplete, non-Demo, mismatched, or unavailable state fails closed.
- Healthy component telemetry never overrides reconciliation or establishes proposal, risk, approval, command, or trading eligibility.
- Design prototypes are never copied directly into production components.

## Project documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [Decisions](docs/DECISIONS.md)
- [Implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md)
- [P0 acceptance gates](docs/P0_ACCEPTANCE_GATES.md)
- [Database foundation](docs/DATABASE_FOUNDATION.md)
- [MT5 read-only Worker and smoke runbook](docs/MT5_READ_ONLY.md)

The repository remains strictly `DEMO_ONLY`; changing that rule requires a separate future project, not a configuration change.
