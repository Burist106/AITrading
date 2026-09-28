# Accepted bounded Pepperstone transaction-time policy

## Decision and scope

On 2026-09-28 the user instructed the project to stop seeking additional timestamp proof and implement support using the operator-provided times and existing observations. This is an explicitly accepted engineering contract, not a claim that the diagnostics proved every MT5 bridge behavior. The implementation checkpoint used deterministic tests only. The subsequently authorized complete native read-only smoke passed with exit `0`; its distinct scope is recorded in [the readiness report](MILESTONE_3_READINESS.md).

The selected contract is `pepperstone_demo_transactions_2026_summer_v1`. It accompanies, but is separate from, `pepperstone_demo_market_2026_summer_v1`. The account-wide server-label convention is based on the existing operator-reference comparisons, Position/Order/Deal linkage, the [Pepperstone server-clock rule](https://pepperstone.com/en-gb/about-us/trading-hours) and documented [history selection semantics](https://www.mql5.com/en/book/automation/experts/experts_history_select). Historical Orders are selected by completion, Deals by occurrence. Applying that convention to the supported Python transaction fields is a recorded assumption, not a new empirical conclusion.

The environment remains **DEMO ONLY / SHADOW**. This policy enables bounded read-only normalization, not broker execution, account switching, automatic binding or a Risk Engine override.

## Fixed mapping

Capture time, decoded event time and original UTC query endpoints must lie in:

```text
2026-03-09T00:00:00Z <= instant < 2026-11-01T00:00:00Z
```

There is no inferred offset, winter fallback or automatic extension through a clock transition.

| Native input                                            | Rule                                                                               | Output                                      |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------- |
| Position `time` / `time_msc`                            | Validate integral pair; subtract three hours once                                  | UTC opening instant with milliseconds       |
| Deal `time` / `time_msc`                                | Validate integral pair; subtract three hours once                                  | UTC occurrence instant with milliseconds    |
| Active/historical Order `time_setup` / `time_setup_msc` | Same                                                                               | UTC setup instant                           |
| Historical Order `time_done` / `time_done_msc`          | Same; only exact `(0,0)` is missing completion                                     | UTC completion or explicit missing evidence |
| Active Order positive `time_expiration`, SPECIFIED mode | Subtract three hours once; require supported coverage and not before setup         | UTC explicit expiry, allowed to be future   |
| Active Order zero `time_expiration`, GTC mode           | Keep absent explicit expiry                                                        | `None`, not a promise of infinite lifetime  |
| Order/Deal history request                              | Add three hours to each original UTC endpoint and floor exactly to integer seconds | Native query arguments only                 |
| Observation clock and original domain request           | Never shift                                                                        | UTC                                         |

Missing or malformed fields, inconsistent second/millisecond pairs, duplicate tickets, invalid chronology and more than 1,000 rows fail closed. Past-event labels beyond the unchanged 30-second future tolerance fail after conversion. DAY/SPECIFIED_DAY expiration modes remain unsupported; this delivery does not guess trading-session expiration rules.

Rows are account-wide, not silently filtered to the configured symbol. A foreign-symbol Position or Order remains visible to reconciliation/exposure checks; this does not authorize trading that symbol. Existing unsupported nontrade Deal shapes and uncertain reconciliation remain failures rather than fabricated valid observations.

## History precision and evidence

For an original inclusive request `[start, end]`, integer-second transport may return events in `[floor(start), floor(end) + 1 second)`. Every returned row is normalized and validated before selection. An event outside that whole-second transport envelope rejects the result. Only the known boundary overfetch outside the original precise inclusive UTC range is removed. Arbitrary out-of-window rows are not concealed.

Historical Order selection uses completion, not setup; setup may legitimately precede the requested window. Missing completion is retained so reconciliation reports incomplete evidence. Duplicate, malformed or unsupported rows cannot escape validation merely because they would later be trimmed. The original UTC request object is unchanged and remains the basis of stored history-query evidence.

This deliberately uses documented whole-second query behavior plus exact returned event times; it does not need a claim that native queries distinguish arbitrary microseconds. All arithmetic is integer/datetime arithmetic, not floating epoch conversion.

## Selection and safety

Ordinary environment-backed Worker composition may explicitly select:

```text
AURUM_MT5_TRANSACTION_TIME_POLICY=pepperstone_demo_transactions_2026_summer_v1
```

This selects both the required market policy and the separate transaction policy. Absent/empty selection retains the previous UTC behavior. Unknown values fail configuration. Existing independently confirmed account/symbol bindings and fixed 10-second tick-age / 30-second future limits are still mandatory. No actual environment value was set or persisted during implementation.

For saved-profile use, the existing complete read-only command selects the transaction contract only for its explicit smoke action:

```text
pnpm worker:mt5:market:smoke --confirm-pepperstone-demo
```

The existing process-only smoke consent is still required. This command passed in the separately authorized native verification follow-up on 2026-09-28; it was not invoked during the preceding implementation checkpoint. A saved-profile command rejects an ambient transaction-policy variable rather than blending configurations. No saved profile is upgraded or rewritten. Market checks, inventories, raw timestamp/Position-link diagnostics and their non-eligibility outputs remain unchanged; market-only selection still blocks production transaction reads.

Before and after every policy-enabled collection read, including an empty result, the serialized adapter checks connected Terminal, current bound Demo account, explicit Pepperstone provider and independently confirmed usable canonical XAU/USD specification. Failed checks discard the result. Transaction observations carry the distinct policy in their adapter version; Shadow capture requires that exact version when selected and rejects wrong/mixed provenance.

## Completion boundary

The time-conversion implementation is separate from an actual terminal acceptance result. Deterministic tests use constructed data and do not load the user's profile or call the native SDK. Existing real diagnostic records remain historical observations; they are not relabeled as full-smoke passes.

The full read-only workflow still performs every reconciliation step. Existing manual Positions/Orders not reflected in confirmed database state can legitimately produce a mismatch. It never adopts current tickets to manufacture a pass. Real account baselines, calendar/cost evidence, hosted configuration and execution authorization are not supplied by this clock policy.

Current implementation/check results are recorded in [the readiness report](MILESTONE_3_READINESS.md). No extra operator timestamp, screenshot or manufactured trade is requested.

The final local check completed with 2,535 Worker tests (419 new policy regressions), 393 JavaScript/TypeScript tests, strict configured Python/TypeScript checks, formatting/lint, builds and security checks passing. Independent non-reset database checks also passed. The root Python type-check command was corrected to load the existing strict configuration explicitly; previously hidden typing issues were repaired without disabling checks. These software results do not relabel an unrun native smoke as passed.
