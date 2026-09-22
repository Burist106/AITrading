# Explicit Demo market-time policy

Status: **LOCAL CODE CHECKS AND BOUNDED NATIVE MARKET CHECK PASSED; NOT MILESTONE 3 READINESS**.

This follow-up implements a bounded correction for the independently selected Pepperstone Demo market-data source. It does not introduce a general broker timezone override or complete the transaction-time contract. Its original authorization did not start Milestone 3. `DEMO_ONLY`, `SHADOW`, existing account/specification confirmations, and the native read-only allowlist remain mandatory.

The user separately authorized the real Demo/Shadow implementation on 2026-09-22. Milestone 3 is **IN PROGRESS — PRODUCTION DEMO/SHADOW COMPONENTS; NOT COMPLETE**: production market normalization, feature, and deterministic risk components have been added, while runtime orchestration, baseline strategy/Shadow proposals, durable persistence/journal, and dashboard integration remain pending. See [Milestone 3 implementation](MILESTONE_3_IMPLEMENTATION.md). Native smoke was not rerun for that implementation, and its authorization does not change this policy's coverage or unblock transaction reads.

## Evidence and interpretation

The [official Pepperstone trading-hours page](https://pepperstone.com/en-gb/about-us/trading-hours) states that its server uses GMT+3 during US daylight saving time and GMT+2 during US standard time. That establishes the published server-time rule, not a universal specification for every Python field. Earlier local tick/bar observations were compatible with a summer server clock, but did not establish Pepperstone source provenance. They must not be attributed to Pepperstone merely because that provider was intended or its portal was open. The optional policy remains an unverified source-specific implementation until the exact native provider, bindings and market-query behavior are verified together. Actual observations remain in sanitized local reports outside Git.

The [official MQL5 `copy_rates_range` reference](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py) instead describes UTC input datetimes and UTC tick/bar timestamps without a shift. This discrepancy is explicit: the optional policy is a bounded source-specific interpretation supported by the provider rule and local market observations, not a claim that all MetaTrader5 Python timestamps use server time. Neither document establishes the Position, Order, or Deal timestamp convention for the selected account.

The Windows clock correction performed during the investigation was separately authorized and completed. It addressed local clock accuracy, not the server-label interpretation. This patch never changes the PC clock or timezone and never uses clock adjustment to force a freshness pass.

## Codec contract

`market_time_policy` has two named values. The default remains `utc_epoch_v1`; existing environment-backed commands, saved-profile commands, raw tick diagnostic, and ordinary Worker startup do not silently select a new policy. The opt-in is `pepperstone_demo_market_2026_summer_v1`.

The optional policy covers only UTC instants in the half-open interval:

```text
2026-03-09T00:00:00Z <= instant < 2026-11-01T00:00:00Z
```

This conservative interval excludes the spring and autumn transition dates. It is not a permanent DST calendar, winter policy, or authorization to extend coverage automatically. Unknown policies, captures outside the interval, unsupported events, and unsupported query endpoints fail closed. A candle's entire open-to-close interval must be covered; an open inside coverage does not permit a close at or beyond its unsupported end.

| Boundary                                   | Explicit summer-policy mapping                         | Domain meaning                                       |
| ------------------------------------------ | ------------------------------------------------------ | ---------------------------------------------------- |
| Tick `time` / `time_msc`                   | Decode native numeric label, then subtract three hours | UTC event instant; milliseconds preserved            |
| Candle `time`                              | Decode native numeric label, then subtract three hours | UTC bar open; completeness calculated in UTC         |
| `copy_rates_range` bounds                  | Add three hours to each UTC event boundary             | Native transport labels only, not UTC event instants |
| Observation clock and request objects      | No adjustment                                          | Remain UTC                                           |
| Position, active Order, Order/Deal history | No assumed mapping                                     | Blocked before the native read                       |

Range transport datetimes deliberately retain aware-UTC encoding while their numeric value is shifted. They are used only as native market-query arguments; they must never be persisted as observation instants or reused as transaction-history bounds. Domain request objects remain unchanged. Returned bars outside the original UTC request window invalidate the entire result.

The fixed offset comes from the selected provider's documented summer rule, never from `native_time - now`, a moving tick, a median of ticks, or whichever correction would make a test pass. Event conversion happens exactly once at the native market-data boundary. Raw numbers do not carry a normalization tag, so a second conversion cannot generally be detected by the pure codec alone.

The codec accepts the integral scalar shape returned by native NumPy candle arrays without importing NumPy as a production dependency. Invalid/non-finite values and booleans fail closed. Tick seconds and nonzero milliseconds must agree at whole-second precision; missing or zero milliseconds use the validated seconds field instead.

## Independent safety checks

Before and after policy-enabled market reads, the adapter checks Terminal connectivity, a currently matching confirmed Demo account, and the usable separately confirmed canonical XAU/USD specification. The public company field must also identify Pepperstone; that is an additional rejection guard, not an account identity, automatic policy selector, or substitute for either confirmation. A wrong provider, changed binding, non-Demo account, or changed specification discards the result. No observed fingerprint becomes confirmation.

The [official Python account reference](https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py) exposes `company`; the [account-property reference](https://www.mql5.com/en/docs/constants/environment_state/accountinformation) distinguishes the serving company from the account holder's name. Provider rejection can export only one of five allowlisted `provider_evidence` constants: `PUBLIC_PROVIDER_MISSING`, `PUBLIC_PROVIDER_INVALID`, `PUBLIC_PROVIDER_EMPTY`, `PUBLIC_PROVIDER_METAQUOTES` (exact known public-company names only), or `PUBLIC_PROVIDER_UNSUPPORTED`. Raw values and arbitrary error details are never exported. This diagnostic adds no native call and does not broaden the existing Pepperstone acceptance rule. An unsupported label alone does not prove which other provider is in use.

Policy configuration requires the existing 10-second maximum tick age and 30-second future allowance. After conversion, the original classifications remain:

- Age at most five seconds: `LIVE`, subject to the unchanged future allowance.
- Age greater than five and at most ten seconds: `DELAYED`.
- Age greater than ten seconds: `STALE`.
- More than thirty seconds in the future: `FUTURE_INVALID`.

These are not relaxed by source selection. A delayed stream still produces old UTC events; advancing labels do not prove freshness. Candle count/range limits, increasing time order, OHLC validation, gap detection, and closed-bucket checks also remain in force.

## Explicit local commands

Use the already manually confirmed encrypted Demo profile. These commands neither create nor rewrite it and add no persistent environment setting, schema migration, automatic account rebinding, or remembered smoke consent. Do not supply conflicting legacy binding environment values.

```text
pnpm worker:mt5:market:check --confirm-pepperstone-demo
```

The confirmation flag explicitly selects the source policy for this invocation. The command verifies a current tick, five completed contiguous M1 bars, and a native range-query roundtrip over those same bars. It compares timestamps and bar content in memory, then obtains a fresh tick again and checks that the last completed M1 close is current. A mismatched roundtrip, stale second tick, stale bars, or failed shutdown cannot produce success. This runtime comparison tests the range-input interpretation separately from merely shifting output labels.

An exit-zero `market_check_passed` result means only that the bounded market check completed. Its JSON always says `grants_eligibility=false` and `smoke_invoked=false`; the transaction contract remains `unverified`. It outputs no account/server identity, fingerprint, terminal path, broker alias, prices, or raw native structures. Failure output discards partial results and reports only safe reasons.

The separate complete-workflow attempt is:

```text
pnpm worker:mt5:market:smoke --confirm-pepperstone-demo
```

It additionally requires `AURUM_MT5_READONLY_SMOKE=1` only in the invocation's process, never in the saved profile or persistent configuration. Without that consent it reports `NOT RUN` before loading the profile or contacting MT5. The market check rejects that smoke flag rather than silently becoming a smoke run.

With opt-in, the smoke follows the existing complete workflow; it does not skip transaction or reconciliation stages to obtain a pass. Under this market-only policy, `get_open_positions`, `get_active_orders`, `get_order_history`, and `get_deal_history` fail with `RECONCILIATION_INCOMPLETE` before their native reads. Even a potentially empty result cannot validate an unproven timestamp or query contract. A smoke may block earlier on other safety gates; this policy cannot yield a full smoke pass.

No password, login call, account switch, Market Watch mutation, broker write, Position modification, command consumer, or trading action is added. No support request is drafted or sent by these commands.

## Verification and remaining work

The new fake-backed suites exercise conversion, strict scalars, native-shaped arrays, preserved freshness thresholds, coverage boundaries, full candle intervals, before/after binding changes, range arguments/results, and transaction-read rejection. Such tests demonstrate implementation behavior, not a real broker contract or real-terminal pass.

Current-patch local verification on 2026-09-21 passed `pnpm check`: formatting, lint, TypeScript and Python type checks, 88 JavaScript/TypeScript tests, 761 Worker tests, production and Worker builds, the production-bundle check, secret/runtime-boundary scanners, and seven scanner tests. The optional native-shaped NumPy regressions ran without skipping on Windows. `pnpm audit --audit-level high`, `pip check`, and `git diff --check` also passed. Bounded independent source review of the preceding market-only implementation found no remaining P1/P2 findings after fixing native integral scalars, measuring freshness after potentially slow binding checks, and adding bounded provider-rejection evidence. The ten provider evidence integration cases were run first and failed before that diagnostic was implemented, then passed after implementation. The follow-up transaction inventory has 44 adapter regressions plus CLI coverage; its initial and 30-day tests each failed before implementation. Review of the eventual full transaction resolution remains an open gate.

The initial database lint attempt failed because the local Docker engine was unavailable. Its subsequent non-destructive runtime-socket recovery succeeded. On a fresh isolated fixture stack, `pnpm db:check` then passed both deterministic resets, schema lint, all 400 pgTAP assertions, four concurrent-claim assertions, and generated-type comparison. Clean-checkout CI for this uncommitted patch has not run; local verification and historical green checks do not replace that gate.

Actual native attempts and their sanitized outputs, exit codes and shutdown evidence are retained outside Git. After the operator manually connected the intended Demo source and saved the new account/specification binding, the current-patch bounded market check passed, including the independent provider guard and market-query roundtrip. The complete opted-in smoke remains blocked at the unverified transaction-time contract. This evidence supports only the exact bounded market validation, not a universal broker timestamp rule, transaction mapping, full smoke or Milestone 3 readiness. A saved account/specification match alone does not establish the provider required by this policy; no automatic rebinding, policy relaxation or account switching was performed.

Remaining native readiness requirements include an independently supported transaction timestamp and query-boundary contract, safe reviewed implementation for every consumed field, a complete opted-in read-only smoke, and all required current-patch checks and review. Milestone 3 implementation is separately authorized and in progress; that is not evidence of native readiness or milestone completion. Keep [PR #2](https://github.com/Burist106/AITrading/pull/2) in Draft; no automatic commit, push, merge, or branch deletion is authorized. See [Milestone 3 readiness](MILESTONE_3_READINESS.md).

### Evidence needed for the complete transaction contract

The authorized follow-up adds an evidence-availability diagnostic:

```text
pnpm worker:mt5:transaction:inventory --confirm-pepperstone-demo
```

If the seven-day inventory supplies no existing samples, the only optional longer lookback is explicitly selected with:

```text
pnpm worker:mt5:transaction:inventory --confirm-pepperstone-demo --lookback-days=30
```

The default stays seven days. No arbitrary duration or custom date is accepted. The longer inventory retains the same row cap, whole-window coverage checks, source binding, and no-eligibility result. This option is rejected on `check` and `smoke` commands and cannot replace source confirmation.

It uses the saved confirmed profile without changing it and rejects smoke consent rather than invoking smoke. All native access stays in the serialized adapter. Current provider, Demo binding, confirmed canonical symbol and coverage checks run before and after each of four read-only calls. The two history calls each use one bounded hypothesis envelope, from capture UTC minus the selected seven or thirty days through capture UTC plus three hours. These are unverified transport labels covering the UTC and summer server-label hypotheses, not validated UTC event bounds. No range interpretation is promoted to a runtime contract.

Each collection is limited to 1,000 returned rows. Output contains only row counts and timestamp-field shape/pair-consistency counts; no native times, account/server identity, fingerprints, alias, ticket, comment, or financial values leave the diagnostic. Failed reads or shutdown discard partial output. Exit zero means only `inventory_observed`; output explicitly retains `transaction_time_contract=unverified`, `grants_eligibility=false`, and `smoke_invoked=false`. Empty collections do not establish completeness or validate a timezone. No diagnostic observation can unblock the four production transaction methods or change the saved profile.

The official Python references for [Positions](https://www.mql5.com/en/docs/python_metatrader5/mt5positionsget_py), [active Orders](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersget_py), and [Deal history](https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py) expose time fields and query arguments without resolving the selected source's UTC-versus-server-label bridge behavior. The [official history-selection book](https://www.mql5.com/en/book/automation/experts/experts_history_select) describes inclusive server-time bounds and selection of historical Orders by completion time, not setup time. Combining this with the provider's trading-hours page supplies a hypothesis, not proof of Python serialization.

Required evidence is an independently timed, existing, nonempty transaction sample from the exactly bound source, covering the consumed event fields, plus bounded include/exclude history queries around known events to establish argument encoding and endpoint behavior. Seconds/milliseconds agreement alone does not establish a timezone; empty history does not prove a query window. Zero or absent completion/expiration fields and unsupported conversion intervals also need explicit handling and tests. No new transaction, broker write, Position change, or account operation is authorized merely to manufacture that evidence.
