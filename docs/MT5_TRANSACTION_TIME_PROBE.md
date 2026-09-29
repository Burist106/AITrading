# Bounded transaction-time investigation

This is an explicitly invoked, local **DEMO ONLY / SHADOW** diagnostic. It observes existing historical Order/Deal query behavior; it does not implement a production transaction clock, grant eligibility, or run the full smoke. All four production transaction methods remain gated under the selected market-only policy.

The user later accepted the existing references and authorized a [separate bounded transaction implementation](MT5_TRANSACTION_TIME_POLICY.md) without more native proof. That decision does not change this diagnostic's outputs or silently upgrade its market-only configuration. The findings below remain historical observations, not a full-smoke pass.

## Scope and safeguards

The saved independently confirmed encrypted profile and explicit Pepperstone Demo selection are mandatory. The adapter verifies the current connected terminal, Demo/provider/account and canonical symbol/specification before and after every history call. No password, login call, account switch, broker write, Position change, new transaction or profile update is involved.

There are at most 24 history calls: two initial seven-day hypothesis envelopes, ten fixed queries for one existing Order and one Deal, and two identical final envelopes. Each result is limited to 1,000 rows. Missing/invalid results, duplicate tickets, malformed or inconsistent seconds/milliseconds, changed source bindings, unexpected returned samples, and changed final history discard the entire result. Matching ticket/time fields are compared only in process memory. A 30-second wall/monotonic budget is checked between calls; the SDK does not offer cancellation of an individually blocked native history call.

The initial envelope covers capture UTC minus seven days through capture UTC plus three hours. These are hypothesis transport labels, not certified event bounds. All probes must stay within that envelope and the conservative summer coverage of both fixed interpretations. No adaptive widening, searching for a convenient offset, retry loop, or manufactured sample is allowed.

## Invocation

```text
pnpm worker:mt5:transaction:probe --confirm-pepperstone-demo
```

Optionally add both `--reference-start=<aware-ISO-time>` and `--reference-end=<aware-ISO-time>` using an independently supplied operator interval. Both need an explicit timezone; the model normalizes them to UTC. The interval must be positive, at most one hour, recent and already elapsed. It is approximate operator-reported evidence, not a verified timestamp service. The command never derives that interval from MT5 and never infers a new runtime offset from a match. Unknown/duplicate flags, incomplete or naive reference times, conflicting profile environment settings and smoke consent fail closed.

## Fixed experiment

Let `s` be the selected Order completion second or Deal event second, and `m` its validated millisecond label. The latest Order with distinguishable setup/completion seconds is preferred when one exists. Otherwise that distinction is explicitly unavailable. Comparisons inspect membership of the selected private ticket, not merely whether any row was returned.

| Probe                         | Arguments                                           | Question observed for this sample                                |
| ----------------------------- | --------------------------------------------------- | ---------------------------------------------------------------- |
| Local label neighborhood      | Integer and aware-UTC datetime `[s−1, s+1]`         | Do the two Python argument shapes return the same anchor?        |
| Minus-three-hour neighborhood | Integer and aware-UTC datetime `[s−10801, s−10799]` | Does this alternative argument hypothesis return the anchor?     |
| Left/exact/right second       | Integer `[s−1, s]`, `[s, s]`, `[s, s+1]`            | Is the anchor included at these whole-second edges?              |
| Next second                   | Integer `[s+1, s+2]`                                | Is the anchor excluded outside its event second?                 |
| Millisecond points            | Aware-UTC datetime `[m−1ms, m−1ms]`, `[m, m]`       | What behavior is observed around the returned millisecond label? |

For a distinguishable Order, the redundant shifted-datetime neighborhood is replaced by integer `[setup, setup]`. This compares completion-second membership against setup-second membership without assuming they are always different. Datetimes are constructed by exact integer `timedelta`, not float conversion.

These experiments can reveal coarse second selection or argument conversion behavior; they do not prove arbitrary microsecond precision, all endpoints, account-history completeness, other events, other providers, or DST/winter behavior. A returned millisecond value whose fractional part is zero cannot distinguish subsecond hypotheses. An independently supplied reference interval can support one event-time interpretation for existing samples, but not certify every MT5 time field.

## Output and acceptance boundary

Success means only `probe_observed` after clean shutdown. JSON contains safe query codes, booleans and counts, always with `grants_eligibility=false`, `smoke_invoked=false` and `transaction_time_contract=unverified`. No ticket, account/server identity, fingerprint, alias, event timestamp, price, P&L, comment, path or raw exception leaves this boundary. Reports stay local and actual samples are never copied into test fixtures.

History probes do not supply samples for open Positions or active Orders. Their opening/update/setup times, nonzero expiration, zero/sentinel behavior and unsupported periods remain unverified. A successful diagnostic cannot unlock those reads, declare full-smoke success, or complete real-source readiness.

The separately invoked [Position–Order–Deal link diagnostic](MT5_POSITION_TIME_LINKS.md) can compare existing open-Position labels with independently supplied terminal display references and linked history. It does not expand this query probe, infer active-Order behavior or change either diagnostic's non-eligibility boundary.

Official references distinguish the available API signatures from the missing bridge contract: [Python Order history](https://www.mql5.com/en/docs/python_metatrader5/mt5historyordersget_py), [Python Deal history](https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py), and [native history selection](https://www.mql5.com/en/book/automation/experts/experts_history_select). Native MQL5 documents inclusive server-time selection and Order completion-time selection; equivalence across Python is investigated here, not assumed.

## Observed result and remaining limits (2026-09-28)

The first actual probe completed all 24 queries with unchanged filtered identity/time snapshots and successful shutdown. The four Order completion labels and four Deal labels all fit the independently supplied approximate operator interval after subtracting three hours; none fit it when interpreted directly as UTC. Both integer and aware-datetime raw-label neighborhoods included each chosen anchor; shifted neighborhoods excluded them. Exact whole-second edge queries included the anchor and the next-second query excluded it. Both fractional singleton probes included it, which cannot distinguish server second-granularity from Python datetime truncation.

All Order setup/completion pairs fell in the same whole second, so completion-versus-setup selection was **NOT DISTINGUISHABLE**. Open Position and active-Order semantics were not sampled. This is useful source-specific diagnostic evidence, not sufficient proof for all consumed fields or a full-smoke pass. The output remains `transaction_time_contract=unverified`. Actual reports stay outside Git; only constructed fixtures appear in tests.
