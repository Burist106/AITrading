# Aurum Console Milestone 1 Architecture

## Scope and invariants

This repository implements **Milestone 1 — Supabase Domain and Security Foundation** on top of the Bootstrap static P0 shell. The executable addition is a local control-plane database, authorization model, durable intent queue, and cross-language contracts. It is still not a trading or broker-execution system.

The following invariants apply at every boundary:

- Environment is `DEMO_ONLY`.
- The only canonical asset is `XAUUSD` (shown to users as XAU/USD).
- Initial and only enabled runtime mode is `SHADOW`.
- Maximum permitted volume is `0.01`; it is a ceiling, not a default order size.
- At most one Position may be represented as open.
- A Stop Loss is mandatory on every proposal and open-Position shape.
- Live accounts fail closed. There is no Live Trading switch or alternate path.
- Martingale, grid trading, averaging down, loss-based volume increases, and hard-risk overrides are prohibited.
- No broker write, order submission, simulated execution, or MT5 Position mutation exists.

## Workspace map

```text
apps/web                 Next.js App Router static P0 shell and read-only control-plane boundary
apps/worker              Typed Python Worker scaffold; no MT5 or command consumer
packages/contracts       Hand-written Zod contracts plus generated Supabase database types
contract-fixtures        One versioned TS/Python parity corpus
fixtures                 Authoritative 20 presentation-only design scenarios
supabase/migrations      Versioned domain, RLS, grant, and secured-function migrations
supabase/tests           pgTAP constraints, RLS, queue, and database-security tests
supabase/integration-tests
                         Credential-free overlapping-session queue tests inside the isolated database
supabase/seed.sql        Deterministic fictional local-only owner and conservative foundation
docs                     Architecture, database, security, decisions, traceability, and runbooks
scripts                  Quality, local Supabase, generated-type, build, and safety checks
```

The design-reference files under `docs/design-reference/` remain visual and behavioral specifications only. Production code does not import them, `support.js`, or anything under `_ds/`.

## Control-plane flow

```mermaid
flowchart TB
    UI[Thai-first P0 web shell] -->|owner-scoped reads| RLS[Supabase forced RLS]
    UI -->|validated owner intents only| UserRPC[Secured user functions]
    UserRPC --> Commands[(Durable system_commands)]
    Commands --> CommandEvents[(Append-only command events)]
    FakeWorker[Fake local Worker claims] -->|claim / lease / transition| WorkerRPC[Worker-only functions]
    WorkerRPC --> Commands
    UserRPC --> Audit[(Append-only audit logs)]
    WorkerRPC --> Audit
    Commands -. optional wake-up only .-> RT[Realtime disabled in Milestone 1]
    Commands -.-x Broker[MT5 / broker]
```

The crossed path is deliberate: a database command is control-plane intent, not approval by a Worker, broker confirmation, or execution. No process consumes commands to create a broker side effect in this milestone.

## Web boundary

`apps/web` remains primarily a fixture-driven presentation layer. Its existing 20 scenarios can display proposal, order, Position, and emergency states for design verification, but do not write those states to Supabase and do not represent live connectivity.

The web control-plane boundary is read-only by construction. Protected writes are not exposed by repository adapters. Authenticated actions, when a later UI connects them, must call the specific intent functions and receive durable command identifiers; browser code cannot insert, update, or delete operational rows. Public browser configuration may never include a Worker or Supabase secret.

The Development State Simulator remains development/test-only. Production forces `no_signal`, ignores manual scenario selection, and scans the bundle for the simulator marker.

## Shared contracts

`packages/contracts` owns intentional cross-boundary Zod models, canonical status arrays, typed command payloads, and row-to-domain mapping rules. It does not treat generated persistence rows as domain objects.

`packages/contracts/src/database.generated.ts` is generated from the local `public` schema. Persistence rows retain snake_case and SQL nullability; domain/wire models use camelCase and deliberate optional-field semantics. Type and test assertions keep database enums aligned with TypeScript, while the versioned JSON corpus is consumed by both Vitest and pytest to keep Zod and Pydantic behavior equivalent.

Numeric PostgreSQL values are authoritative for financial precision. Browser arithmetic requires an explicit conversion/decimal policy rather than silently assuming that a generated `number | string` is safe.

## Worker boundary

`apps/worker` is still a typed Python scaffold with fake adapters. Milestone 1 adds Pydantic equivalents for durable commands, lifecycle metadata, Positions, risk checks, and risk-policy records, but it does not add a polling loop or operational Worker consumer.

The database defines a dedicated NOLOGIN `aurum_worker` role for fake local claim tests and a future independently issued credential. Its JWT claim model includes an assigned owner and Worker identifier. It receives only secured Worker-function execution, never broad administrative authority and never a frontend session.

No MetaTrader package is imported. The existing broker-read adapter remains fake and Bootstrap-limited. Read-only MT5 integration is Milestone 2 and has not started.

## Supabase boundary

Local Supabase is the Milestone 1 control plane and operational database:

- every exposed application table has enabled and forced RLS;
- unauthenticated access is denied and authenticated reads are owner-scoped;
- direct browser DML on protected state is denied;
- user functions validate one of nine typed intents and apply owner idempotency and optimistic concurrency;
- Worker functions atomically claim with `FOR UPDATE SKIP LOCKED`, return one typed safe-code envelope, clamp leases to command expiry, enforce legal transitions, and append history;
- exact idempotent retries remain stable after mutable resource state changes, while changed content on the same key conflicts;
- recoverable pre-execution leases may be reclaimed, expired or attempt-exhausted pre-execution work is terminalized with event/audit evidence, and `executing` uncertainty is never automatically reclaimed or swept;
- risk policies use immutable versions and bounded conservative rule changes;
- audit and event tables reject application update/delete attempts;
- secured functions use a NOLOGIN owner, pinned empty `search_path`, qualified references, narrow grants, and no dynamic SQL;
- Realtime is disabled and never required for queue correctness.

The local CLI is pinned in the lockfile. Docker port publication is verified as loopback-only, and start/status output that can contain local keys is suppressed. The queue concurrency check runs two overlapping, passwordless local `psql` sessions inside the disposable database container. Each session uses the pinned Supabase local role graph to assume the exact `aurum_worker` role without changing role membership; all claimed-row effects roll back and the original state is verified. A failed check destroys the isolated database volume. No remote project, link, push, credential, or production deployment is used.

See [DATABASE_FOUNDATION.md](./DATABASE_FOUNDATION.md) for the table/queue model and [SECURITY.md](./SECURITY.md) for the principal and RLS matrix.

## Responsibility boundaries

The database can enforce Demo/XAUUSD identity, volume and Position ceilings, mandatory Stop Loss shape, immutable prohibited-strategy flags, ownership, versions, expiry ordering, idempotency, command state, and leases. It cannot evaluate current spread, market freshness, news, realized loss, drawdown, broker margin, broker response, or reconciliation without future live inputs. Those remain fail-closed responsibilities of later explicitly authorized Risk Engine and Worker milestones.

## Deferred architecture

The following remain deliberately absent:

- MT5 initialization, account discovery, market/candle reads, or any broker write;
- market ingestion, feature computation, strategy, deterministic live Risk Engine, and Shadow proposal production;
- operational Worker polling and credential issuance;
- LINE/LIFF approval, notification delivery, Conditional Auto, and reconciliation behavior;
- Local Emergency Stop tray/CLI behavior;
- P1 live analysis, AI/ML decisions, P2 analytics, cloud deployment, and all Live Trading capability.

See `docs/IMPLEMENTATION_ROADMAP.md` for the authorized milestone order. Completing this foundation does not start Milestone 2.
