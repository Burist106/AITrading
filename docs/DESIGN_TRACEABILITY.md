# Bootstrap Design Traceability

## Milestone 1 integration status

Milestone 1 adds the local Supabase domain/security foundation and an owner-scoped, read-only web adapter boundary. It does not connect that adapter to the existing screens and does not turn any fixture control into an operational action. Proposal facts and normalized risk checks remain separate read models, a missing or expired heartbeat resolves to `unknown`, and command progress uses the browser-safe projection without payload, lease token, or raw last error. The table below continues to describe the Bootstrap visual shell; its broker/order/Position and emergency scenarios remain presentation-only.

## Reference policy

The source precedence is defined by `AGENTS.md`. The principal visual reference is `docs/design-reference/Aurum Console.dc.html`; implementation semantics and accessibility requirements come from `docs/design-reference/Aurum Handoff Spec.dc.html`; source-level corrections are summarized in `docs/design-reference/PATCH_REPORT.md`.

The `.dc.html` files are specifications, not production source. No production component imports the prototype, `support.js`, or `_ds` assets.

## Bootstrap component coverage

| Bootstrap surface                   | Design reference                                          | Bootstrap coverage                                                                                         | Explicitly deferred                                                                        |
| ----------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `ApplicationShell`                  | Prototype global header/nav; handoff §03, §09, §10        | Persistent Demo identity, XAUUSD, read-only Shadow mode, global/MT5/freshness states, responsive landmarks | Auth/session, secured mode change, pause/resume/emergency commands, secondary P0 workflows |
| `DemoEnvironmentBadge`              | Prototype header; handoff §09 and §11C                    | Always visible and cannot be dismissed                                                                     | None; this identity remains permanent                                                      |
| `GlobalSystemStatus` / indicators   | Prototype header and banners; handoff §09                 | Running, paused, emergency, recovering, unknown; icon + text + boundary                                    | Real heartbeat, Realtime, MT5, or database reads                                           |
| Dashboard market summary            | Prototype `ภาพรวม`; handoff §03 and §09                   | Fixture bid/ask, spread, session, regime, freshness, event warning                                         | Live market subscriptions, charting, economic provider                                     |
| Dashboard proposal summary          | Prototype `ภาพรวม`; handoff §05, §06, §09                 | WAIT/ASK/AUTO-eligible/BLOCK/expired/progress fixture states, levels, evidence disclaimer                  | Approval/rejection, server expiry, order checks, broker submission                         |
| Proposal detail shell               | Prototype `ข้อเสนอการเทรด`; handoff §05–§07, §09          | Fixture proposal, eligibility, provenance, risk summary, sizing, disabled/static decisions                 | Secured decisions, durable command creation, Worker revalidation                           |
| `RiskValidationSummary` / checklist | Prototype proposal; handoff §09 and §11C                  | Totals derived from the fixture check array; PASS/WARN/FAIL/N/A                                            | Deterministic Worker Risk Engine implementation                                            |
| `PositionSizingBreakdown`           | Prototype proposal; handoff §05 and §6C                   | Consistent normal and minimum-lot-block examples; 0.01 shown as ceiling                                    | Broker symbol reads and profit/margin calculations                                         |
| Active Position shell               | Prototype Dashboard/Position; handoff §09                 | Empty, open, profit/loss, and closed presentation states                                                   | Mismatch workflow, close, Stop Loss, Take Profit, reconciliation, broker confirmation      |
| System Health                       | Prototype `สถานะระบบ`; handoff §03, §6B, §09              | Separate execution/control plane cards, derived tallies, and component failure/warning/unknown states      | Operational monitoring, an incident feed, and Supabase/MT5/LINE connectivity               |
| Emergency Stop visuals              | Prototype global shell/timeline; handoff §6B and §09      | Requested, confirmed, unconfirmed and failure guidance remain distinct                                     | Command persistence, Worker acknowledgement, local tray/CLI kill switch                    |
| Development State Simulator         | Prototype simulator; handoff §07 and §11; patch report §G | Exact 20-scenario fixture selector in development/test only                                                | Production availability; runtime mode or command mutation                                  |

## Scenario coverage

All scenario keys, labels, values, and selected view models derive from one authoritative fixture store.

| Scenario                     | Primary visual coverage                                                          |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `no_signal`                  | Shadow default; proposal waiting state                                           |
| `wait`                       | Explicit WAIT outcome                                                            |
| `auto_eligible`              | Eligibility evidence only; execution remains disabled and runtime remains Shadow |
| `human_approval`             | Internally consistent ASK fixture; no approval processing                        |
| `blocked`                    | Hard-risk block with no override                                                 |
| `proposal_expired`           | Expired proposal and disabled decision                                           |
| `approval_recorded`          | Presentation-only progress state                                                 |
| `revalidation_failed`        | Approval recorded but current-state validation failed                            |
| `order_pending`              | Presentation-only pending broker result                                          |
| `order_rejected`             | Presentation-only rejection; no automatic retry                                  |
| `position_open`              | Active-position shell                                                            |
| `position_closed`            | Closed-position state                                                            |
| `mt5_disconnected`           | Global banner and Health component failure                                       |
| `market_data_stale`          | Stale pricing/freshness and fail-closed banner                                   |
| `daily_loss_limit`           | Risk-limit pause state                                                           |
| `emergency_stop_requested`   | Request recorded, acknowledgement still pending                                  |
| `emergency_stop_confirmed`   | Fixture Worker acknowledgement explicitly present                                |
| `emergency_stop_unconfirmed` | Critical unknown local state and manual guidance                                 |
| `live_account_detected`      | Full hard-block failure visualization only                                       |
| `minimum_lot_exceeds_risk`   | Calculated 0.0045, minimum 0.01, requested null, BLOCK                           |

The application default is `no_signal`. Scenario selection exists only in development/test, changes presentation only, and never changes the fixed `SHADOW` runtime mode. Production ignores scenario query values and always resolves to `no_signal`.

## Human Approval fixture reconciliation

The authoritative fixture uses equity 2,200.00 USD, risk limit 0.25%, risk budget 5.50 USD, entry 2,410.40, current price 2,410.55, tolerance ±0.60, deviation +0.15, Stop Loss 2,404.90, Take Profit 2,421.95, requested volume 0.01, estimated loss 5.50 USD, actual risk 0.25%, 24 similar samples, and a requirement of 30.

Its outcome is `ASK` because `minimum_sample_size` is `WARN`. Quality score is not a probability and does not produce the outcome. Repeated values are derived from this fixture rather than duplicated in components.

## Design tokens and typography

| Role                     | Token/value                                | Implementation rule                                                                  |
| ------------------------ | ------------------------------------------ | ------------------------------------------------------------------------------------ |
| Background / surfaces    | `#141312`, `#1c1b1a`, `#242322`, `#302e2d` | Square, layered dark surfaces; radius remains zero                                   |
| Primary / secondary text | `#f5f3f2`, `#b9b4b2`                       | Thai-first readable contrast                                                         |
| Tertiary text            | `#9a9593`                                  | Do not use as normal small text on `#302e2d`; use secondary text there               |
| Gold / focus             | `#d9b054`                                  | XAU accent and 2 px focus ring with 2 px offset                                      |
| BUY / positive           | `#4cc39e`                                  | Direction or positive P&L only                                                       |
| SELL / negative          | `#ff8a6e`                                  | Direction or negative P&L only                                                       |
| Blocked                  | `#e8836b`                                  | Trade block, distinct from system failure                                            |
| Warning / information    | `#e8a54a`, `#6fb0e0`                       | Non-critical warning and general system state                                        |
| Critical                 | `#ff5c3d`; fill `#c62810` with white       | Use filled treatment on elevated/row surfaces where normal critical text is below AA |
| Decorative border        | `#3f3d3c`                                  | Never the only visible boundary of an interactive control                            |

IBM Plex Sans Thai is the primary font. Archivo is limited to the wordmark and large English display text; IBM Plex Mono is used for time, identifiers, prices, and aligned numbers. Thai text never receives uppercase-style letter spacing. Text is at least 11 px; important mobile body content is at least 14 px. Numeric columns use tabular numerals.

## Accessibility and responsive behavior

- Keyboard-visible focus, a skip link, semantic landmarks, and logical headings are required.
- Interactive targets are at least 44 × 44 px; primary mobile actions are 52 px high.
- Status is communicated with text and an icon/boundary, never color alone.
- Critical uncertainty uses `role="alert"`; routine status changes use polite announcements.
- Countdown text is not announced each second; only meaningful threshold crossings are announced.
- Tables have captions, meters expose current/maximum values, and charts require text summaries.
- Desktop uses the three-column 1.05 / 1.45 / 1.05 composition; 1024 px collapses to two columns; 390 px prioritizes decision and safety information in one column.

## Deferred screens and behavior

| Priority | Deferred from Bootstrap                                                                                                                                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0       | Setup/demo verification, real Mobile Approval/LIFF, secured approval/rejection, Position requests, full Risk Center editing, journal details, command processing, Supabase integration, local Emergency Stop implementation |
| P1       | Live market screen/analysis drawer and every Conditional Auto capability                                                                                                                                                    |
| P2       | Performance analytics and large reporting/chart features                                                                                                                                                                    |

Minimal route labels or placeholders do not imply capability. Storybook is also deferred; component tests and the development-only simulator provide Bootstrap state coverage.
