# Aurum Console Implementation Roadmap

## Release constraints

- Demo account only
- XAU/USD only
- Initial mode: Shadow
- Maximum permitted volume: 0.01
- One open position maximum
- No Live Trading capability

## Bootstrap Milestone — Foundation and Static P0 Shell

Deliver:

- Repository and workspace structure
- Web application scaffold
- Python Worker scaffold without MT5 execution
- Shared TypeScript contracts and runtime validators
- Python Pydantic equivalents for cross-boundary messages
- Central fixtures for the 20 documented design scenarios
- Design token foundation and accessible application shell
- Static P0 Dashboard and System Health shell using fixture data
- Development-only State Simulator
- Supabase local project/migration skeleton
- CI, formatting, linting, type checking, and tests
- Design traceability and architecture documentation

Forbidden:

- `order_send()`
- Broker execution
- Live account support
- Conditional Auto
- Real LINE webhook
- Trading strategy implementation
- AI/ML decision logic

## Milestone 1 — Supabase Domain and Security Foundation

Status (2026-08-26): **complete with documented limitations**. GitHub Actions verified the published Milestone 1 implementation on commit `ab7df47`. Milestone 2 extends this foundation without changing the Milestone 1 command semantics.

Deliver:

- Initial operational database schema
- RLS policies and tests
- Durable `system_commands` model
- Trade proposal, risk check, position, event, incident, and audit schemas
- Edge/RPC contract stubs with idempotency
- Supabase Auth integration for the single user
- Web read models and repository adapters

Exit gate:

- Browser cannot directly mutate protected operational tables
- RLS tests pass
- Durable commands can be created and read in a local test environment

## Milestone 2 — Read-only Windows MT5 Worker

Release status (2026-09-02): **COMPLETE WITH DOCUMENTED LIMITATIONS**. The final heartbeat/liveness local gates passed, and Pull Request run `33541088560` passed `quality`, `database`, and `windows-mt5-boundary` on implementation commit `3e25007`. At that release, Milestone 3 was not started or authorized and the real-terminal smoke was `NOT RUN`. The later opted-in native smoke was blocked by the unresolved transaction-time contract; its separate evidence is preserved in [Milestone 3 native readiness](MILESTONE_3_READINESS.md).

Deliver:

- MT5 initialize/shutdown adapter
- Demo-account verification
- Live-account fail-closed state
- Symbol discovery and broker specification capture
- Latest tick and historical candle reads
- Open positions and order-history reads
- Worker heartbeat and system health
- Poller-owned `execution.worker`, `execution.mt5_adapter`, and `execution.market_data` heartbeat producers
- Default 5/15/600-second polling cadences with a default 30-second heartbeat TTL, bounds 15–300 seconds, and TTL at least three tick intervals
- Authoritative Worker-health cap, `reconciliation_required` gate, and exact `TICK_DELAYED` freshness semantics
- Missing/expired/invalid Web heartbeat derivation to `unknown` and explicit Thai component labels
- Bounded latest-tick and heartbeat upserts without per-update security-audit growth
- Local fake MT5 adapter for CI
- Sanitized owner-scoped Supabase observations and reconciliation evidence
- Bounded Windows CI import/native-wrapper boundary

Forbidden:

- `order_send()`
- Position modification
- Automated trading

Heartbeat/liveness verification evidence currently present in source:

- Worker regressions for continuous short-poll renewal, authoritative Healthy caps, reconciliation-required behavior, failure propagation, and the five tick-freshness outcomes;
- Web regressions for renewed versus expired evidence, missing/invalid rows, blocked Worker state, delayed market data, labels, and sensitive-field exclusion;
- nine database suites with 400 pgTAP assertions, including many bounded tick/heartbeat updates, no routine audit growth, forced RLS, owner isolation, and least privilege.

The final local suite passed with 88 TypeScript tests, 233 Worker tests, 400 pgTAP assertions, four concurrent-claim assertions, clean builds, generated types, dependency checks, and security scans. Pull Request run `33541088560` passed all three required jobs on implementation commit `3e25007`.

## Milestone 3 — Shadow Pipeline

Status (2026-09-22): **IN PROGRESS — PRODUCTION DEMO/SHADOW COMPONENTS; NOT COMPLETE**.

The user authorized the real Demo system and corrected the earlier offline-only interpretation. The end-to-end code now connects runtime orchestration, market/features, a versioned research baseline, risk/eligibility, Shadow proposals, immutable journal/outcomes and authenticated owner-scoped pages. Genuine ledger/baseline/news/cost/safety evidence, hosted provisioning and full native acceptance remain unavailable; no fixtures are substituted. The [implementation record](MILESTONE_3_IMPLEMENTATION.md) separates integrated code from unresolved operational readiness.

The earlier component slice passed 178 TypeScript tests, 1,052 Worker tests and 582 pgTAP assertions. Those are historical counts. The implementation record contains current integration checks; neither set proves a complete real-terminal smoke or operational milestone completion.

Deliver:

- Market-data normalization
- Feature pipeline
- Rule-based baseline strategy
- Eligibility policy
- Deterministic Risk Engine
- Trade Proposal generation
- Risk checks and decision evidence
- Trade journal and shadow outcome tracking
- Dashboard connected to Supabase read models

Exit gate:

- Shadow proposals are reproducible and traceable
- Every proposal has versioned strategy, policy, risk, market, and feature references

## Milestone 4 — Secure Human Approval Workflow

Deliver:

- LINE LIFF approval identity flow
- Single-use approval sessions
- Secured approval/rejection actions
- Durable commands and Worker claim/lease handling
- Final revalidation simulation
- Command progress UI
- Duplicate, stale, expiry, version mismatch, and restart tests

Execution remains simulated until the next milestone is explicitly authorized.

## Milestone 5 — MT5 Demo Execution

Only start with explicit user authorization after earlier gates pass.

Deliver:

- `order_calc_profit()` and margin checks
- `order_check()`
- `order_send()` for verified Demo account only
- Broker execution result handling
- SL/TP confirmation
- Position reconciliation
- Local Emergency Stop
- Restart recovery
- Safety test matrix

## Milestone 6 — Conditional Auto in Demo

Only start after Human Approval Demo execution is stable.

- AUTO only when every deterministic gate passes
- ASK for configured soft uncertainty
- BLOCK for every hard failure
- Daily/weekly/drawdown circuit breakers
- No adaptive risk increase
- No Live Trading

## Future research — not authorized by this roadmap

- Calibrated ML meta-model
- Regime model improvements
- News/macro enrichment
- LLM explanations
- Other assets
- Live account execution
