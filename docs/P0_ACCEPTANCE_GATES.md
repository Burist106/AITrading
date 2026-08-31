# P0 Acceptance Gates

These gates apply before any Demo broker execution is introduced.

`[x]` means verified in the current workspace. `[ ]` means deliberately pending. Milestone 2 is **IMPLEMENTED — PATCH AND CI VERIFICATION PENDING**; it adds read-only observation and reconciliation only and does not authorize execution. Milestone 3 is not started.

## Repository and quality

- [x] TypeScript strict mode passes
- [x] Python static checks pass
- [x] Web tests pass
- [x] Worker tests pass without MT5 installed
- [x] Formatting and linting pass
- [ ] The final Milestone 2 source-review patch passes all three Pull Request jobs on a clean checkout
- [x] No credentials or secret values are committed

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

## Broker execution authorization gate

The following must remain absent until Milestone 5 is explicitly approved:

A checked item here means the prohibited capability was verified absent; it does not mean that capability was implemented.

- [x] `order_send()`
- [x] Position modification calls
- [x] Conditional Auto execution
- [x] Live account support
