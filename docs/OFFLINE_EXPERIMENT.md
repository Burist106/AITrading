# Offline read-only experiment

Scope: synthetic experiment authorized on 2026-09-21. **DEMO ONLY / SHADOW**.

This exercises the existing Milestone 2 reconciliation and recovery code without a terminal, account profile, broker, Docker, Supabase, or network. It does not implement the Milestone 3 strategy or Risk Engine. At this experiment's completion on 2026-09-21, Milestone 2 was **COMPLETE WITH DOCUMENTED LIMITATIONS** and Milestone 3 was **NOT STARTED**. The real-source [readiness gate](MILESTONE_3_READINESS.md) remains unresolved.

On 2026-09-22 the user separately authorized the real Demo/Shadow implementation, correcting an offline-only interpretation. Milestone 3 is now **IN PROGRESS — PRODUCTION DEMO/SHADOW COMPONENTS; NOT COMPLETE**. Production market normalization, feature, and deterministic risk components have been added; runtime orchestration, baseline strategy/Shadow proposals, durable persistence/journal, and dashboard integration are pending. See [Milestone 3 implementation](MILESTONE_3_IMPLEMENTATION.md). This historical experiment remains test-only evidence; native smoke was not rerun for the new implementation.

## Run

From the project root, with the existing Node/pnpm and Python development environment:

```text
pnpm worker:offline:experiment
```

The command runs a test-only experiment, also included in the ordinary Worker test suite. A nonzero exit means an assertion or setup failed. No MT5 setup or fingerprint is required. Each successful scenario prints an allowlisted JSON summary labeled `synthetic_fixture`, `grants_eligibility: false`, and `real_mt5_smoke: NOT_RUN_BY_THIS_EXPERIMENT`.

## Experiment design

Use existing `mt5_factories` synthetic observations at a fixed UTC instant and in-memory persistence. Run each of eight cases twice from fresh fake state and compare the summary exactly. This validates repeatable software behavior under supplied observations, not price discovery, native normalization, or profitability.

| Synthetic condition                          | Expected simulated result                                       |
| -------------------------------------------- | --------------------------------------------------------------- |
| Confirmed Demo, current tick, matching state | Healthy within the fixture only                                 |
| Six-second delayed tick                      | Degraded / TICK_DELAYED                                         |
| Stale tick                                   | Blocked / TICK_STALE                                            |
| Future tick                                  | Blocked / reconciliation incomplete due to clock mismatch       |
| Missing symbol confirmation                  | Blocked / confirmation required                                 |
| Deal-history read failure                    | Blocked / history query failed                                  |
| Non-Demo account classification              | Blocked / real account rejected; no real account is used        |
| Unexpected synthetic position                | Blocked / reconciliation incomplete; position remains unchanged |

A separate sequence verifies stale -> fresh tick alone remains blocked -> full reconciliation restores simulated health. A newly constructed poller must reconcile again, even with the previous in-memory store. This is an in-process restart model, not evidence of durable database/crash recovery.

Native/profile imports, common socket entry points, and environment-based MT5 configuration are disabled during these tests. Sentinel process settings prove that an ambient smoke opt-in is not used. These are test guards, not a security sandbox. Synthetic confirmation never changes the user's encrypted profile. No production runtime path is added.

## Evidence boundary

This experiment cannot establish broker transaction timestamps, history query endpoints, current market availability, strategy quality, trade eligibility, or a real-terminal smoke pass. It does not change the existing goal into a completed one and does not authorize commit, push, or merge.

## Actual local results (2026-09-21)

- `pnpm worker:offline:experiment`: exit 0, all 10 tests passed (eight replay cases, recovery/restart, and guard rejection).
- `pnpm check`: exit 0 after format, lint, TypeScript and Python type checks, 88 JavaScript/TypeScript tests, 771 Worker tests including this experiment, production builds, and security scans. All seven scanner regressions passed.
- `pnpm audit --audit-level high`: no known vulnerabilities reported. `pip check`: no broken requirements. These are bounded checks, not a guarantee of absence of all vulnerabilities.
- The built Worker wheel was inspected: no test-only experiment or test factories were included. The production Web bundle check also passed.
- `git diff --check`: passed.
- No real-terminal smoke, real profile check, or database integration check was run for this offline experiment. The earlier database results retain their earlier scope; no database code changed here. Current-patch GitHub Actions were not run, and nothing was committed or pushed.

Initial local lint and type-check attempts found an overlong test row and an optional-binding annotation error. Both were corrected before the successful complete run above; no production behavior was changed.
