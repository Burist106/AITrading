# P0 Acceptance Gates

These gates apply before any Demo broker execution is introduced.

`[x]` means verified for the identified implementation. `[ ]` means deliberately pending. Milestone 2 is **COMPLETE WITH DOCUMENTED LIMITATIONS**: the final heartbeat/liveness local gates and Pull Request run `33541088560` passed on 2026-09-02, with `quality`, `database`, and `windows-mt5-boundary` green on implementation commit `3e25007`. The milestone remains read-only and does not authorize execution. The checks below retain their identified release scope; they do not certify the current Milestone 3 changes.

Milestone 3 is **IN PROGRESS — INTEGRATED DEMO/SHADOW CODE; REAL-SOURCE ACCEPTANCE BLOCKED**, authorized on 2026-09-22. Runtime, baseline/risk/eligibility, immutable Shadow storage and authenticated read-only pages are now connected in code and tested using constructed evidence. Genuine external providers/configuration and native acceptance remain pending. See [Milestone 3 implementation](MILESTONE_3_IMPLEMENTATION.md).

## Milestone 3 delivery gates

- [ ] Resolve and verify the native transaction timestamp/query contract, preserving the current fail-closed gate until evidence supports it
- [ ] Obtain a complete opted-in native read-only smoke pass; the later attempt remains blocked and no native smoke was rerun for this implementation
- [x] Integrate market, feature, eligibility and risk code into serialized polling with a versioned research baseline and traceable non-executable proposals; constructed-input tests are not native acceptance
- [x] Implement immutable Shadow decisions/outcomes, owner-scoped RPC/read models and actual dashboard routes; local SQL/contract checks are not hosted deployment
- [ ] Supply genuine source-bound equity/ledger/baseline, calendar, cost and safety evidence and a provisioned authenticated hosted connection
- [ ] Complete current-change review, required verification, and clean-checkout CI without reusing historical Milestone 2 results as current evidence

## Repository and quality

- [x] TypeScript strict mode passes
- [x] Python static checks pass
- [x] Web tests pass
- [x] Worker tests pass without MT5 installed
- [x] Formatting and linting pass
- [x] The final Milestone 2 source-review patch passes all three Pull Request jobs on a clean checkout
- [x] No credentials or secret values are committed
- [x] The heartbeat/liveness patch passes the final local format, lint, type, test, build, security, database, and generated-type gates
- [x] The heartbeat/liveness patch implementation commit `3e25007` passes `quality`, `database`, and `windows-mt5-boundary` in clean-checkout Pull Request run `33541088560`

## Design traceability

- [x] Every P0 screen maps to design-reference sections
- [x] Production components do not copy the prototype as one large component
- [x] Central fixture data powers all repeated sample values
- [x] Development State Simulator contains the documented 20 scenarios
- [x] State Simulator is excluded from production builds
- [x] Thai typography and focus behavior meet the handoff requirements

## Architecture boundaries

- [x] Frontend submits intents only
- [x] Protected operational tables are not browser-writable
- [x] Supabase Realtime is not treated as a durable command queue
- [x] Worker, browser, and user authentication are separate concepts
- [x] MT5 credential boundaries are documented
- [x] No Live Trading switch or code path exists

## Domain and command integrity

- [x] Trade Proposal contains account, symbol-specification, policy, strategy, and version bindings
- [x] Durable commands contain typed payloads
- [x] Runtime validation exists for every command payload
- [x] Commands contain idempotency, expiry, claim, lease, retry, and result fields
- [x] Expected resource versions are used for stale-write protection
- [x] Approval, Worker execution, and broker confirmation are separate states

## Risk semantics

- [x] Maximum permitted volume is 0.01
- [x] 0.01 is not treated as a mandatory fixed volume
- [x] Broker minimum volume above risk budget results in BLOCK
- [x] Stop Loss is mandatory in all future execution proposals
- [x] Hard Risk Engine failures have no override
- [x] Quality score is not used as AUTO/ASK probability
- [x] Price outside tolerance disables approval and requires recalculation

## Emergency and recovery

- [x] Requested, recorded, acknowledged, confirmed, and unconfirmed Emergency Stop states are distinct
- [x] Local Emergency Stop is included in the Worker design
- [x] Resume requires reconciliation and a safety checklist
- [x] Open positions are not silently assumed closed
- [x] Worker restart and reconnect reconciliation are designed and tested before execution
- [x] Reconciliation detects account, server, confirmed-specification, Position, Order, current bounded-history-query, clock, and uncertain-execution mismatches without operational mutation
- [x] All three enabled execution components renew bounded heartbeats during their owned lightweight poll cadence without audit growth
- [x] Worker heartbeat remains capped by full reconciliation, and `reconciliation_required` prevents Healthy until a successful full cycle
- [x] LIVE, DELAYED, STALE, FUTURE_INVALID, and UNAVAILABLE tick mappings plus Web missing/expired/invalid `unknown` behavior pass their final regression gates

## Broker execution authorization gate

The following must remain absent until Milestone 5 is explicitly approved:

A checked item here means the prohibited capability was verified absent; it does not mean that capability was implemented.

- [x] `order_send()`
- [x] Position modification calls
- [x] Conditional Auto execution
- [x] Live account support
