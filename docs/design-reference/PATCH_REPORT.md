# Aurum Console Design v2.1 — Source-Level Consistency Patch Report

```
Aurum Console Design v2.1
Status: APPROVED FOR P0 IMPLEMENTATION
Environment: DEMO ONLY
Asset: XAU/USD ONLY
Maximum permitted volume: 0.01
Maximum open positions: 1
```

Every claim below was measured against the actual source after patching, using the source-aware methods described in §L. All prototype values are fictional design data (ข้อมูลจำลองสำหรับการออกแบบ).

---

## A. Final file inventory

| File | Updated | Source size | Purpose |
| --- | --- | --- | --- |
| `Aurum Console.dc.html` | Yes | 216,161 bytes | Interactive prototype. Holds the authoritative scenario store (`SCEN`, 20 states) and sample store (`SAMPLE`, 4 scenarios), the computed price-tolerance gate, and the Emergency Stop transition logic. |
| `Aurum Handoff Spec.dc.html` | Yes | 122,261 bytes | Developer handoff. Holds the TypeScript domain model incl. `PrototypeScenarioId` and `SystemCommandPayloadMap`, component-state definitions, Supabase contracts, contrast audit, acceptance checklist. |
| `PATCH_REPORT.md` | Rewritten | this file | Source-level verification record. |

Unchanged: `_ds/` (bound Modernist design system), `support.js` (runtime, not authored).

---

## B. Actual-source corrections

| Issue | Old source location | New source location | Resolution | Verification method |
| --- | --- | --- | --- | --- |
| Scenario keys were ad-hoc abbreviations (`human`, `posprof`, `estopreq`, `minlot`) | `const SCEN` object | `const SCEN` + `SCEN_KEYS` + `DEFAULT_SCEN` | Rebuilt as 20 snake_case ids matching `PrototypeScenarioId`; each entry carries `labelTh`, `labelEn`, `sample`, `result`, optional `estop` | Parsed the object literal, extracted keys, diffed against the required list |
| Default state initialised the price at `2412.85` — outside tolerance while approval was enabled | `state = {… px:2412.85}` | `constructor(props)` → `px: SAMPLE[SCEN[start].sample].currentPrice` | Default is `human_approval` → Scenario A → `currentPrice 2410.55`, deviation `+0.15` | Regex-matched the constructor; confirmed no literal `2412.85` initialiser remains |
| Price ticker drifted freely from any scenario, so deviation was arbitrary at render time | `componentDidMount` interval, `px: s.px + drift` | interval now recentres on `SAMPLE[SCEN[s.scen].sample].currentPrice ± 0.06` | Displayed price stays in the scenario's neighbourhood; the gate stays meaningful | Read the interval body |
| Quality score was generated from the verdict (`isBlocked?31:(isAsk?68:79)`) | `renderVals()` | `const sc = SC.qualityScore` | Score now read from the scenario; per-scenario values A 71 / B 74 / C 71 / D 82 | Searched for `isAsk?<digits>` and `isBlocked?<digits>` — 0 matches |
| Score bar colour switched on `isBlocked`, implying the score caused the block | `scoreBars` | single gold fill regardless of verdict | Score is presentationally neutral | Read `scoreBars` |
| Verdict explanations described score bands ("สัญญาณอยู่ในเกณฑ์ก้ำกึ่ง", "คะแนน…68/100") | proposal `ex` strings, upcoming-event copy | rewritten to eligibility-policy language | ASK is explained by `minimum_sample_size` WARN; the copy states the score does not determine AUTO or ASK | Searched `ก้ำกึ่ง` — 0 matches |
| Sample counts disagreed across components (24 / 34 / 46 on one screen) | eligibility rows, `sampleN`, why-this-trade copy, Risk Center note | all read `SC.similarSampleCount` / `SC.minimumRequiredSampleCount` | Human Approval shows 24 of 30 everywhere | Searched `34 ตัวอย่าง`, `มี 46`, `46 ตัวอย่าง` — 0 matches |
| No tolerance test existed; `isPriceMoved` was asserted from a scenario flag | `renderVals()` | `priceDeviation` and `priceWithinTolerance` computed, `isPriceMoved = !priceWithinTolerance` | The gate is derived arithmetic, not a label | Regex-matched all three declarations |
| Approval remained enabled out of tolerance | `pActions` branch order | new leading `if(isPriceMoved)` branch disables approval, shows entry/current/deviation/tolerance and "Risk เดิมไม่สามารถใช้ได้ ต้องคำนวณข้อเสนอใหม่" | No override control offered | Read the branch; confirmed `disabled:true` |
| Confirm dialog could still submit out of tolerance | approve modal `dis:` | `dis: st.expiry<=0 \|\| isPriceMoved` | Confirm button disabled | Regex-matched the expression |
| Emergency Stop jumped straight to confirmed | `confirmModal` | `k==='estop'` sets `emergency_stop_requested` + `estopAck:'waiting'`, then a 4 s simulated Worker ack resolves to `emergency_stop_confirmed` (reachable) or `emergency_stop_unconfirmed` (timeout) | Confirmation now requires an acknowledgement event | Read the handler and the timer callback |
| Resume was reachable while the stop was unconfirmed | `askEstop`, `togglePause`, resume modal | `askEstop` only opens Resume when `estop==='confirmed'`; `togglePause` intercepts unconfirmed with local-kill-switch guidance; resume modal `dis:` includes `estop==='unconfirmed'` | Resume is not the primary action while unconfirmed | Read all three sites |
| `showStateSwitcher` prop existed but did not gate anything | template | simulator bar wrapped in `<sc-if value="{{ showSwitcher }}">`, fed by `this.props.showStateSwitcher ?? true` | Prop now controls rendering | Confirmed both the `sc-if` and the `renderVals` key |
| `data-props` enum still listed 13 stale keys incl. `posrisk`, `recover` | `data-props` JSON | 20 `PrototypeScenarioId` options, default `human_approval`, `tsType: 'PrototypeScenarioId'` | Metadata matches the store | Parsed the JSON and diffed the option list |
| `defaultScenario` prop was decorative | constructor | `SCEN[props.defaultScenario] ? props.defaultScenario : DEFAULT_SCEN` | Prop selects the starting state | Read the constructor |
| `SystemCommand` carried no typed payload | handoff schema | `SystemCommandPayloadMap` (9 keys) + `SystemCommandType = keyof …` + generic `SystemCommand<T>` with `payload: SystemCommandPayloadMap[T]` | Payload is typed per command; runtime validation (Zod / Pydantic) required in the handoff note | Structural search of the code block |
| `ExecutionProgressTimeline` documented 7 stages | component inventory | 9 primary stages + 7 terminal states | Matches the durable-command workflow | Read the row |
| `CommandStatusTimeline` used a 4-value ad-hoc set | component inventory | all 9 `SystemCommandStatus` values | Matches the domain union | Read the row |
| Visual-regression note said "13 simulated states" | developer notes | "20 scenarios × 1440×900, 1280×720, 390×844" | Matches the store | Searched the old string — 0 matches |
| `ACTIVATE_EMERGENCY_STOP` intent described instant shutdown | intents list | "บันทึกคำขอ…แบบถาวร แล้วรอ Windows Worker ยืนยัน" | Intent wording matches the state machine | Read the entry |
| Codex warnings lacked three new prohibitions | warnings list | added: score as AUTO/ASK eligibility, Realtime as durable command source, unvalidated payloads | 17 prohibitions total | Counted the array |

---

## C. Active scenario consistency — Human Approval

Read directly from `SAMPLE.A` in the prototype source:

| Field | Value |
| --- | --- |
| Account equity | 2,200.00 USD |
| Risk limit | 0.25 % |
| Risk budget | 5.50 USD |
| Entry | 2,410.40 |
| Current price | 2,410.55 |
| Entry tolerance | ±0.60 |
| Price deviation | +0.15 |
| Stop Loss | 2,404.90 |
| Take Profit | 2,421.95 |
| Stop distance | 5.50 USD |
| Contract size | 100 oz / 1.00 lot |
| Calculated volume | 0.01 |
| Requested volume | 0.01 |
| Approved volume | 0.01 |
| Estimated loss at stop | 5.50 USD |
| Actual risk | 0.25 % |
| Quality score | 71 / 100 (supporting evidence only) |
| Sample count | 24 |
| Required sample count | 30 |
| Calibration status | `not_calibrated` |
| Eligibility outcome | **ASK** — `minimum_sample_size` = WARN |

Arithmetic: 2,200.00 × 0.25 % = 5.50. Volume = 5.50 ÷ (5.50 × 100) = 0.01. Loss = 5.50 × 100 × 0.01 = 5.50 → 5.50 ÷ 2,200.00 = 0.25 %. R:R = (2,421.95 − 2,410.40) ÷ 5.50 = 2.10. Deviation = 2,410.55 − 2,410.40 = 0.15 ≤ 0.60 → approval available.

Components confirmed reading from the active scenario (no independent literals): proposal levels grid, position-sizing breakdown, eligibility panel, signal-evidence panel, why-this-trade rows, hard-risk checklist (SL / TP / R:R / min-lot / risk rows), approve confirmation dialog, market card price line, chart price lines, invalidation sentence, mobile approval detail rows, mobile price-moved card, command timeline.

Other scenarios: **B** `minimum_lot_exceeds_risk` (equity 1,000, budget 2.50, calculated 0.0045, loss at min volume 5.50, risk 0.55 %, `BROKER_MINIMUM_VOLUME_EXCEEDS_RISK`), **C** `revalidation_failed` (current 2,412.85, deviation +2.45, `PRICE_MOVED_BEYOND_TOLERANCE`), **D** `auto_eligible` (score 82, 46 samples ≥ 30 → all checks pass → AUTO). D is a separate scenario, not the Human Approval screen — 46 samples never appear alongside 24.

---

## D. Price-tolerance test

Source logic:

```js
const priceDeviation = +(SC.currentPrice - SC.entryPrice).toFixed(2);
const priceWithinTolerance = Math.abs(priceDeviation) <= SC.entryTolerance;
const isPriceMoved = !priceWithinTolerance;
```

```
Happy-path deviation:  0.15
Happy-path tolerance:  0.60
Approval enabled:      true

Price-moved deviation: 2.45
Price-moved tolerance: 0.60
Approval enabled:      false
Block reason:          PRICE_MOVED_BEYOND_TOLERANCE
Displayed risk:        ต้องคำนวณใหม่  (riskDisplay switches when out of tolerance)
```

Out of tolerance the UI shows entry, current price, deviation and tolerance, states that the previous risk figure cannot be used, and offers only "ดูกราฟ". No trade-anyway, force-execution or ignore-tolerance control exists in the source.

---

## E. Score-semantics audit

```
Quality score used to calculate verdict:        false
Verdict used to generate quality score:        false
ASK explained by eligibility checks:           true
AUTO explained by eligibility checks:          true
Score described as supporting evidence only:   true
```

- `isAsk?<n>` / `isBlocked?<n>` patterns: **0 matches**.
- `ก้ำกึ่ง` (mid-band) copy: **0 matches**.
- The score panel carries the inline caveat "ข้อมูลประกอบเท่านั้น · ไม่ได้กำหนด AUTO หรือ ASK".
- The verdict line reads from the eligibility result; ASK cites `minimum_sample_size` with actual 24 against required 30 and policy `demo-auto-policy v1.0.4`.

---

## F. Emergency Stop transition test

```
User confirmation      → emergency_stop_requested   (estopAck: 'waiting')
Worker acknowledgement → emergency_stop_confirmed   (estopAck: 'confirmed')
Worker timeout         → emergency_stop_unconfirmed (estopAck: 'timeout', command halted)

Resume shown as primary action while unconfirmed: false
```

The confirm handler returns early on `estop`, setting only the requested state; a 4 s timer supplies the simulated acknowledgement and resolves to confirmed when the Worker is reachable, or unconfirmed when it is not. While unconfirmed: `askEstop` will not open the Resume dialog, `togglePause` intercepts with local-kill-switch and MT5 guidance (tray application, `aurum-worker emergency-stop`), and the Resume dialog's confirm button is disabled. Open positions are never auto-closed.

---

## G. State Simulator report

```
Expected states:   20
Prototype states:  20
Metadata states:   20
Handoff states:    20
Missing:            0
Extra:              0
Stale keys:         0
```

The three lists are identical in content and order. `posrisk`, `recover` and `mismatch` no longer appear anywhere; dangling `st.scen===` / `scen:'…'` references: **0**.

`no_signal` · `wait` · `auto_eligible` · `human_approval` · `blocked` · `proposal_expired` · `approval_recorded` · `revalidation_failed` · `order_pending` · `order_rejected` · `position_open` · `position_closed` · `mt5_disconnected` · `market_data_stale` · `daily_loss_limit` · `emergency_stop_requested` · `emergency_stop_confirmed` · `emergency_stop_unconfirmed` · `live_account_detected` · `minimum_lot_exceeds_risk`

Rendering is gated by `showStateSwitcher` (default true in the prototype, to be false in production builds); options, labels, count badge and default selection all derive from `SCEN`.

---

## H. Schema report

| Type | Present | Complete |
| --- | --- | --- |
| `PrototypeScenarioId` | ✓ | 20-member union |
| `SystemCommandPayloadMap` | ✓ | 9 command payloads |
| `SystemCommandType` | ✓ | `keyof SystemCommandPayloadMap` |
| `SystemCommandStatus` | ✓ | 9 values |
| `SystemCommand<T>` | ✓ | generic, typed `payload`, lease + retry + idempotency fields |
| `TradeProposal` | ✓ | version, account, symbol-spec binding, 10-value status |
| `EligibilityCheck` / `EligibilityCheckKey` / `EligibilityCheckState` | ✓ | 7 keys, 4 states, actual/required/explanation |
| `EligibilityPolicyResult` | ✓ | policyId, policyVersion, outcome, evaluatedAt, checks |
| `MobileApprovalSession` | ✓ | + status union, tokenHash, proposalVersion |
| `BrokerSymbolSpecification` | ✓ | 15 fields |
| `PositionSizingResult` | ✓ | incl. unusedRiskCapacity, calculationSource, blockReason |

Supporting types present: `EmergencyStopControlPlaneState`, `EmergencyStopWorkerState`, `EmergencyStopState`, `SignalEvidence`, `DecisionProvenance`, `RiskCheck`, `MarketSnapshot`, `Position` (with `positionVersion`), `JournalRow`.

**Compilation status: not verified.** No TypeScript compiler is available in this environment. Verification was structural — the block was extracted and each required declaration, union member and field checked by parsing. Duplicate or superseded interfaces were removed rather than left alongside: the pre-v2.1 `SystemCommand` (untyped, `requested/received/submitted/confirmed/timeout`) and the boolean-flag eligibility model are both gone. Treat "parses successfully" as unverified until `tsc --noEmit` is run against the extracted block.

---

## I. Thai spacing report

```
Rendered Thai-containing elements audited: 134
Inherited spacing checked:                 yes (ancestor letter-spacing wrapping Thai)
Violations before:                          22
Violations after:                            0
```

Method: every `<span> / <div> / <button> / <label> / <h1> / <h2> / <h3> / <p>` whose inner text matches `[\u0E00-\u0E7F]` was checked for `letter-spacing > 0.02em` on its own tag, then separately for any ancestor `<div>` carrying wide tracking that wraps Thai text. Both counts are zero. English-only uppercase eyebrows retain controlled tracking; Thai section titles and English eyebrows sit in separate elements. Thai minimum size remains 11 px.

---

## J. Contradiction report

Comparing prototype, handoff, TypeScript types, component inventory, change log and acceptance checklist:

```
Unresolved P0 contradictions: 0
```

Resolved in this pass: default price outside tolerance while approval enabled; score generated from verdict; three different sample counts on one screen; Emergency Stop confirmed without acknowledgement; Resume reachable while unconfirmed; `showStateSwitcher` non-functional; `data-props` enum listing stale keys; component-state docs using a status model the domain no longer had; visual-regression note citing 13 states; `ACTIVATE_EMERGENCY_STOP` described as instant.

---

## K. Release gate

| Condition | Measured | Pass |
| --- | --- | --- |
| Default approval price within tolerance | deviation 0.15 ≤ 0.60 | ✓ |
| Out-of-tolerance approval disabled | `disabled:true` + modal `dis:` | ✓ |
| No score-based AUTO/ASK semantics remain | 0 matches for verdict→score and mid-band copy | ✓ |
| One sample count per active scenario | 24 / 30 throughout Scenario A | ✓ |
| Emergency Stop transitions correct | requested → ack → confirmed / timeout → unconfirmed | ✓ |
| Simulator and metadata both exactly 20 | 20 / 20 / 20, identical | ✓ |
| Component states match domain unions | 9 statuses, 9 timeline stages | ✓ |
| `SystemCommand` has typed validated payloads | payload map + validation requirement | ✓ |
| Thai spacing violations zero | 0 of 134 | ✓ |
| Unresolved P0 contradictions zero | 0 | ✓ |

```
Aurum Console Design v2.1
Status: APPROVED FOR P0 IMPLEMENTATION
```

---

## L. Verification methods used

- **Prototype:** read the file as source; extracted `SCEN` and `SAMPLE` object literals and parsed their keys and fields; regex-matched control-flow declarations (tolerance gate, score assignment, Emergency Stop handler, constructor); parsed the `data-props` JSON; walked element open-tags plus inner text for the Thai audit, including ancestor-inherited tracking. Element matching used tag/attribute/content structure rather than quoted-literal search, so `>2410.40<` in markup would have been caught.
- **Handoff:** located the TypeScript block, then structurally checked each required declaration, union member and field; read component-inventory rows as data rather than searching for one phrasing.
- **Cross-file:** diffed the prototype scenario keys against the `data-props` enum and the handoff `PrototypeScenarioId` union for content and order.

### Limits of this report

1. **No compiler run.** Schema checks are structural (§H). `tsc --noEmit` has not been executed.
2. **No live DOM instrumentation.** The Thai audit and gate checks read source and computed logic, not a browser-computed style tree. Inherited tracking was checked by ancestor inspection, which catches inline ancestors but would miss tracking introduced by a stylesheet rule — none exists in this file beyond the helmet resets.
3. **Emergency Stop acknowledgement is simulated** by a 4 s timer whose branch depends on the scenario's MT5 reachability. It demonstrates the three transitions; it is not a Worker integration.
4. **Contrast ratios** in the handoff are computed values for documented token pairs, not measured from a rendered screenshot.

---

## Notes carried forward (not gates)

1. **`--system-critical` (#ff5c3d)** measures 5.4:1 on `#141312`, 5.1:1 on `#1c1b1a`, 4.7:1 on `#242322`, 4.1:1 on `#302e2d` — below AA for normal text on the two lighter surfaces. The documented correction is the filled treatment (`#c62810` with white text, 5.2:1) or large-text-only use there. The token was deliberately not brightened: doing so pulls it toward `--direction-sell #ff8a6e` and weakens the semantic separation between system failure and SELL. Open for your decision.
2. **`--border #3f3d3c`** is decorative at 1.5:1 and must not be the visible boundary of an interactive control.
3. **Still stubbed:** trade-journal row-detail drawer and risk-rule edit form open explanatory toasts rather than full screens. Both are specified in the component inventory; neither is claimed as built.
4. **Tablet (1024 px)** is specified in the responsive table, not built as a screen.
5. **Take Profit is 2,421.95**, not the earlier 2,422.10, so that R:R is exactly 2.10 against the 5.50 stop.
