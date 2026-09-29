# Existing Position time-link diagnostic

This is a local, explicitly invoked **DEMO ONLY / SHADOW** diagnostic, not a production transaction-clock implementation, health assessment or complete native smoke. It never creates, closes or modifies a Position or Order. All four runtime transaction methods retain their existing market-policy gate.

The later [operator-accepted transaction policy](MT5_TRANSACTION_TIME_POLICY.md) is selected separately. Its implementation uses the existing references without another native experiment; it does not rewrite these historical diagnostic findings or auto-select itself from a matching link result.

## Purpose and reference boundary

An operator-provided terminal screenshot can supply a current Position ticket and a displayed opening label to whole-second precision. These are input references, not a newly inferred account binding or proof of UTC event time. The separate Windows clock visible in a screenshot identifies its capture minute, not the precise instant of each trade; this command does not promote it to an exact UTC event reference.

The explicit command is:

```text
pnpm worker:mt5:position:links --confirm-pepperstone-demo --position=<current-ticket>@<YYYY-MM-DDTHH:MM:SS>
```

Repeat `--position` for one to ten independently supplied references. Placeholders above must be replaced locally, never checked into source or test fixtures. Tickets must be unique positive signed-64-bit integers. Labels must be exactly whole-second timezone-naive terminal display labels; offsets, fractional seconds, missing/duplicate confirmations, unknown flags, duplicate references and malformed dates fail before profile/native access. A label is not silently assigned a real timezone or rounded to make it match. Local command arguments can be visible to the local shell/process tooling; the CLI never echoes them, even on failure.

Use only the existing independently confirmed encrypted profile. Conflicting environment bindings or smoke consent fail before native initialization. No password, login call, account switch, Market Watch change, profile rewrite or persistent setting is used.

## Bounded reads and joins

There are exactly six collection reads on success: Positions, historical Orders, historical Deals, followed by the same Order and Deal history envelopes and a final Position read. The envelope is fixed at capture UTC minus seven days through capture UTC plus three hours. These are hypothesis transport bounds, not certified UTC event bounds. Missing evidence never widens the lookback or triggers repeated probing.

Every read is serialized and guarded before and after by current connected Terminal, bound Demo account, explicit Pepperstone provider, canonical XAU/USD and separately confirmed unchanged usable specification checks. A wall/monotonic 30-second budget is checked between calls; the SDK cannot cancel a blocked individual native call. Each collection is at most 1,000 rows. Exact selected-scope scalar shapes, identifiers, second/millisecond pairs and ordering are validated. Initial/final sorted identity/time/direction/entry snapshots must agree, including Position update timestamps. This is not a claim of atomic broker state or a risk snapshot; prices, P&L, volume and Stop Loss are not assessed.

The [official Position properties](https://www.mql5.com/en/docs/constants/tradingconstants/positionproperties) distinguish the current ticket from the stable Position identifier and associate that identifier with its original opening Order. The [Order properties](https://www.mql5.com/en/docs/constants/tradingconstants/orderproperties) and [Deal properties](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties) provide the cross-links used here:

- The screenshot reference selects the current `Position.ticket`; its label is compared with `Position.time` at whole-second precision.
- `Position.identifier` must equal the original opening `Order.ticket`, that Order's `position_id`, and the linked Deal's `position_id`.
- `Deal.order` must equal the opening Order's ticket, with entry `IN` and compatible BUY/SELL direction.
- Only one linked original market Order and one linked entry Deal are supported. Additions, multiple/partial fills, exits/reversals, missing original history, duplicate identifiers or inconsistent links fail closed as unsupported evidence. No nearest-time heuristic substitutes for identity.

The command compares Position/Deal seconds and milliseconds, observed setup-to-Deal-to-completion ordering, and whether Order setup/completion differ at whole-second precision. Disagreement is a reported comparison, not grounds to choose a convenient timestamp or derive a new offset. The operation neither proves history completeness nor covers an opening Order outside its fixed history envelope.

## Safe output and interpretation

Only `position_links_observed`, counts, stable-filtered-snapshot confirmation and fixed `grants_eligibility=false`, `smoke_invoked=false`, `transaction_time_contract=unverified` can be emitted after successful shutdown. Native tickets, aliases, timestamps, account/server details, financial values, input labels and raw errors are not exported. Failure discards partial results; failed shutdown replaces any provisional success. Actual reports remain local outside Git, while tests use exclusively constructed fictional examples.

For `RECONCILIATION_INCOMPLETE`, failure output may additionally contain one exact allowlisted `failure_stage`. Six identity/reference/snapshot categories distinguish unavailable evidence, and fixed `LINK_STAGE_*` values identify bounded coordinator stages. Arbitrary exception details or strings merely sharing a prefix are never exported. Missing current references are `LINK_POSITION_NOT_FOUND`; this does not establish whether a Position closed, its ticket changed, or the operator reference was wrong.

A matching result establishes label/identity agreement for those observed simple chains. It does not establish a universal Python UTC contract, active-Order/expiration semantics, history selection/boundary behavior, DST/winter support, a complete smoke pass, or trading permission. Closed or changed reference Positions may make a later invocation unavailable; do not ask the operator to create or keep exposure solely for this diagnostic.

## Verification record

The first real invocation blocked with the generic reconciliation reason. An allowlisted failure-classification improvement was then tested before one diagnostic retry, which also blocked, with actual process exit `2` and `failure_stage=LINK_POSITION_NOT_FOUND`. At that point, the result established only that at least one supplied reference was absent, not that a real Position had closed.

After the user confirmed the Positions remained open, reinspection of the original image and an independent second visual transcription identified an assistant input error: one digit had been omitted from each current-ticket reference. Both reference values were corrected from the image, never copied from newly observed native identifiers. The same diagnostic implementation then completed one read-only invocation with actual process exit `0`, `position_links_observed`, successful shutdown, six collection reads and unchanged filtered snapshots. Both of the two Positions linked to their original Orders and entry Deals; both displayed opening seconds matched, both Position/Deal seconds and milliseconds matched, and both observed setup-to-Deal-to-completion orderings matched. Neither Order had distinguishable setup/completion whole seconds.

This resolves the lookup/input mistake and supplies two source-specific Position label/link observations. It does not resolve the Python UTC interpretation, active-Order/expiration contract, or history selection/boundary gaps. No additional transaction, source-binding change, wider history search, production mapping change or full smoke was used. Runtime source and tests were unchanged by the reference correction; sanitized actual reports retain all three attempts outside Git.

The initial implementation's full local check passed with 1,907 Worker tests and 393 JavaScript/TypeScript tests. After adding failure classification, final `pnpm check` exited zero with 1,933 Worker tests including 363 diagnostic regressions, 393 JavaScript/TypeScript tests, formatting/lint, TypeScript/mypy (100 files), builds, bundle isolation and security checks. Fresh dependency checks and non-reset database validation also passed; exact counts and scope are in the [readiness record](MILESTONE_3_READINESS.md). Initial source review found a serializer-warning privacy leak and an incorrect millisecond-based distinguishability counter; both were corrected and independently rechecked before native invocation. A malformed reference now emits no private warning, and setup/completion distinguishability means different whole seconds. No current-patch CI or publication has occurred.
