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

Status (2026-08-26): **complete locally with documented limitations**. The schema, forced RLS, secured actions, durable queue, generated types, read-only Web adapters, and local database tests are implemented. No remote Supabase project was linked or changed. Clean-checkout CI remains pending confirmation on GitHub Actions; Worker restart/reconnect reconciliation remains a pre-execution gate. Milestone 2 has not started.

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

Deliver:

- MT5 initialize/shutdown adapter
- Demo-account verification
- Live-account fail-closed state
- Symbol discovery and broker specification capture
- Latest tick and historical candle reads
- Open positions and order-history reads
- Worker heartbeat and system health
- Local fake MT5 adapter for CI

Forbidden:

- `order_send()`
- Position modification
- Automated trading

## Milestone 3 — Shadow Pipeline

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
