You are the lead engineer for **Aurum Console**, a safety-first XAU/USD trading research and MT5 Demo control system.

Work directly in the current workspace. The attached starter pack is authoritative for this initial task.

## Read before editing

Read these files completely, in this order:

1. `AGENTS.md`
2. `README_FIRST.md`
3. `docs/P0_ACCEPTANCE_GATES.md`
4. `docs/IMPLEMENTATION_ROADMAP.md`
5. `docs/design-reference/Aurum Handoff Spec.dc.html`
6. `docs/design-reference/Aurum Console.dc.html`
7. `docs/design-reference/PATCH_REPORT.md`

Treat the `.dc.html` files as **visual and behavioral specifications**, not production source code. Do not copy the prototype into one production component. Do not use `support.js` or `_ds` assets as the production runtime.

## Fixed product decisions

These are not open questions:

```text
Environment: DEMO ONLY
Asset: XAU/USD ONLY
Initial runtime mode: SHADOW
Maximum permitted volume: 0.01
Maximum open positions: 1
Mandatory Stop Loss
No martingale
No grid trading
No averaging down
No loss-based volume increase
No hard-risk override
No live-account execution
Supabase: control plane and operational database
Windows Python MT5 Worker: execution plane
User-facing language: Thai
```

## Current task

Implement only the **Bootstrap Milestone — Foundation and Static P0 Shell**.

Do not implement later milestones.

### Required deliverables

1. **Repository structure**

Create a maintainable workspace with this conceptual structure:

```text
apps/web
apps/worker
packages/contracts
supabase/migrations
supabase/functions
fixtures
docs
scripts
```

Use a current stable Next.js App Router setup for `apps/web`, TypeScript strict mode, Tailwind CSS, and reusable accessible components. Use a typed Python package for `apps/worker` with `pyproject.toml`, Pydantic models, pytest, Ruff, and static type checking. Choose and lock exact stable dependency versions, then record them in `docs/DECISIONS.md`.

2. **Documentation**

Create or update:

```text
docs/ARCHITECTURE.md
docs/SECURITY_BOUNDARIES.md
docs/DESIGN_TRACEABILITY.md
docs/DECISIONS.md
docs/LOCAL_DEVELOPMENT.md
```

`DESIGN_TRACEABILITY.md` must map each Bootstrap/P0 component to the relevant design-reference screen or section and state clearly which design details are deferred.

3. **Shared domain contracts**

Extract and normalize the current handoff contracts into `packages/contracts`.

At minimum include and validate:

```text
PrototypeScenarioId
EligibilityCheck
EligibilityPolicyResult
SystemCommandPayloadMap
SystemCommandType
SystemCommandStatus
SystemCommand
TradeProposal
MobileApprovalSession
BrokerSymbolSpecification
PositionSizingResult
Emergency Stop states
System health states
```

Use Zod or an equivalent TypeScript runtime validator. Create matching Pydantic models for cross-boundary messages used by the Worker scaffold. Add contract tests proving representative valid and invalid payloads.

4. **Authoritative fixture store**

Create one central fixture/scenario source for the 20 design states:

```text
no_signal
wait
auto_eligible
human_approval
blocked
proposal_expired
approval_recorded
revalidation_failed
order_pending
order_rejected
position_open
position_closed
mt5_disconnected
market_data_stale
daily_loss_limit
emergency_stop_requested
emergency_stop_confirmed
emergency_stop_unconfirmed
live_account_detected
minimum_lot_exceeds_risk
```

Do not duplicate active prices, sample counts, risk values, or tolerance values in multiple components.

The Human Approval fixture must be internally consistent:

```text
Equity: 2,200.00 USD
Risk limit: 0.25%
Risk budget: 5.50 USD
Entry: 2,410.40
Current price: 2,410.55
Entry tolerance: ±0.60
Deviation: +0.15
Stop Loss: 2,404.90
Take Profit: 2,421.95
Volume: 0.01
Estimated loss at stop: 5.50 USD
Actual risk: 0.25%
Similar samples: 24
Required samples: 30
Eligibility outcome: ASK because minimum_sample_size is WARN
```

Quality score is supporting evidence only. Do not calculate the verdict from the score and do not generate a predetermined score from the verdict.

5. **Static P0 application shell**

Build a production-quality static shell using fixtures only. Implement:

```text
Application shell
Persistent DEMO identity
Global system status
Trading mode indicator
MT5 connection indicator
Market-data freshness indicator
Main Dashboard shell
Trade Proposal summary/detail shell
Risk Validation summary
Position Sizing breakdown
Active Position shell
System Health shell
Emergency Stop requested/confirmed/unconfirmed visual states
Development State Simulator
```

The State Simulator must be enabled only in development and test builds. It must be absent from the production bundle.

Do not implement real Supabase reads/writes yet beyond typed adapter interfaces and local placeholders.

6. **Worker scaffold only**

Create the Python Worker structure and health models with fake adapters. Include interfaces for future MT5, persistence, strategy, risk, and execution modules.

Do not import or call MT5 order execution APIs. Do not implement `order_send()` or any broker mutation.

CI tests must run without MetaTrader installed.

7. **Supabase skeleton**

Create local Supabase structure and empty/initial migration placeholders sufficient to establish naming and migration workflow. Do not invent broad browser write permissions. Document the planned RLS model, but only implement schema that is necessary for the Bootstrap contracts if you can test it locally.

8. **Quality tooling**

Configure:

```text
Formatting
Linting
Type checking
Unit tests
Component tests where practical
Accessibility checks for the static shell
CI workflow
Secret scanning or at least a deterministic secret-pattern check
```

Provide root commands for a clean checkout, such as install, dev, lint, typecheck, test, and build. Use commands that work on Windows where practical.

## Explicitly forbidden in this task

Do not implement:

- `order_send()`
- Any MT5 broker write or position modification
- Live account support
- Conditional Auto execution
- Real trading strategy logic
- AI/ML trading decisions
- Real LINE webhook or LIFF approval
- Real Supabase Worker secret
- Any secret or credential
- Large performance analytics features
- P1 or P2 screens beyond minimal placeholders required for routing

Do not add hidden future functionality “for convenience.”

## Working method

1. Inspect the workspace and design references.
2. Write a concise implementation plan before changing files.
3. Record assumptions in `docs/DECISIONS.md` instead of guessing silently.
4. Implement the Bootstrap Milestone in bounded, reviewable steps.
5. Run all available checks.
6. Review the git diff against `AGENTS.md` and `docs/P0_ACCEPTANCE_GATES.md`.
7. Do not claim completion if a check did not run or failed.

## Completion response

At the end, report:

1. Files and architecture created
2. Commands to install and run locally
3. Tests/checks run and exact results
4. Design traceability coverage
5. Safety controls enforced in this milestone
6. Explicit confirmation that no broker execution or Live Trading path was added
7. Remaining limitations
8. Recommended next task: **Milestone 1 — Supabase Domain and Security Foundation**

Start now with the workspace audit and implementation plan, then complete only the Bootstrap Milestone.
