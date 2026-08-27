# AGENTS.md — Aurum Console

## Mission

Build a safety-first XAU/USD trading research and Demo execution platform. The system is strictly `DEMO ONLY` until a separate future project explicitly changes that rule. No task in the current roadmap authorizes Live Trading.

## Source-of-truth order

When sources disagree, use this precedence:

1. This `AGENTS.md`
2. Explicit current user instruction
3. `docs/P0_ACCEPTANCE_GATES.md`
4. `docs/IMPLEMENTATION_ROADMAP.md`
5. `docs/design-reference/Aurum Handoff Spec.dc.html`
6. `docs/design-reference/Aurum Console.dc.html`
7. `docs/design-reference/PATCH_REPORT.md`

The prototype is a visual and behavioral reference, not production source code.

## Non-negotiable safety rules

- Enforce `DEMO ONLY` in configuration, domain validation, Worker startup, and tests.
- A detected Live account must fail closed with no UI or configuration override.
- Do not add `order_send()` before the explicitly authorized Demo Execution milestone.
- Do not add a Live Trading switch, hidden flag, environment variable, or alternate execution path.
- The frontend must never create or mutate broker orders, executions, positions, or risk-validation results directly.
- Every future order must pass the deterministic Risk Engine and final current-state revalidation.
- Every future order must have a valid Stop Loss before submission.
- Martingale, grid trading, averaging down, and loss-based volume increases are prohibited.
- Maximum permitted volume is 0.01; 0.01 is not a mandatory fixed volume.
- If broker minimum volume exceeds the risk budget, return `BLOCK`.
- Risk Engine hard failures cannot be overridden by AI, Worker, frontend, LINE, or user UI.
- Fail closed when account state, market data, database state, time, symbol specification, Worker health, or MT5 state is unavailable, stale, inconsistent, or uncertain.
- Supabase Realtime is a notification/wake-up mechanism, not the durable source of command truth.
- Emergency Stop requested, Worker acknowledged, and broker state are distinct states.
- LLM output must not be in the deterministic order-execution path.

## Credential boundaries

Never request, print, log, commit, upload, or place into prompts:

- MT5 password, server credentials, or terminal secrets
- Supabase secret keys or Worker credential
- LINE channel secret or access token
- OpenAI API keys
- Browser cookies or personal access tokens

An MT5 password must never be requested, read, accepted, persisted, logged, uploaded, or passed to `initialize()`. The Worker must never call `login()`. A full account login must never be logged, persisted remotely, displayed, or committed. The Worker may transiently inspect the account identifier and server returned by `account_info()` solely for fail-closed Demo and binding verification; raw values must stay in process memory, and every log, database row, UI response, test snapshot, and incident must use a masked or one-way fingerprinted identifier. Use `.env.example` with empty placeholder names only.

## Development workflow

- Read all required documentation before editing.
- Start every milestone with a concise implementation plan and a list of assumptions.
- Do not ask the user to decide routine implementation details already specified here.
- Record non-trivial assumptions and decisions in `docs/DECISIONS.md`.
- Work one milestone at a time. Do not implement future milestones opportunistically.
- Keep commits and changes bounded and reviewable.
- Add or update tests with every behavior change.
- Run format, lint, type checks, and tests before reporting completion.
- Report failures honestly. Never claim a gate passed without evidence.

## Architecture boundaries

Expected high-level structure:

```text
apps/web                 React/Next.js Thai-first dashboard
apps/worker              Python Windows MT5 Worker
packages/contracts       Shared TypeScript domain contracts and validators
supabase/migrations      Database schema and RLS migrations
supabase/functions       Secured command and approval endpoints, later milestones
fixtures                  Central prototype/demo fixtures
scripts                   Development and verification scripts
docs                      Architecture, decisions, security, risk, traceability
```

Use current stable supported versions and lock dependencies. Document exact versions chosen.

## Web requirements

- TypeScript strict mode.
- Thai-first accessible UI.
- Componentized architecture; no monolithic prototype conversion.
- Use design tokens, Tailwind, and reusable variants.
- Central fixture/scenario source; no duplicated hard-coded market values across components.
- Development State Simulator must be development-only and excluded from production.
- No Supabase secret key in browser code.
- Browser submits intents only.

## Python Worker requirements

- Typed Python with Pydantic models.
- Separate adapters for MT5, persistence, strategy, risk, execution, and notifications.
- No execution method before its authorized milestone.
- Local safety state and reconciliation must be designed before Demo execution.
- Tests must use fakes/adapters; CI must not require a running MT5 terminal.
- Milestone 2 native access is Windows-only, serialized, uses an explicit local terminal path, and may call only `initialize`, `shutdown`, `version`, `last_error`, `terminal_info`, `account_info`, `symbols_get`, `symbol_info`, `symbol_info_tick`, `copy_rates_from_pos`, `copy_rates_range`, `positions_get`, `orders_get`, `history_orders_get`, and `history_deals_get`.
- `order_send`, `order_check`, `order_calc_profit`, `order_calc_margin`, `login`, `symbol_select`, and every `market_book_*` call remain forbidden. Do not use dynamic dispatch to bypass this boundary.

## Database requirements

- Use migrations; no manual production schema edits.
- Enable RLS on user-facing tables.
- Protected operational records are not directly writable from the browser.
- Durable commands require idempotency, claim/lease semantics, expiry, retry metadata, and typed runtime-validated payloads.
- Audit and event history should be append-oriented where practical.

## Trading and model evaluation rules

- Use chronological splits for time-series evaluation.
- Do not use random train/test splits for trading performance claims.
- Include spread, commission, slippage, and swap in performance calculations.
- `WAIT` and `BLOCK` are valid outcomes.
- Quality score is supporting evidence only and must not be presented as calibrated probability unless it is actually calibrated and versioned.
- Do not retrain or promote models automatically.

## Definition of done for every milestone

- Scope matches the milestone and contains no unauthorized future functionality.
- Documentation and code agree.
- Tests cover success, failure, stale, duplicate, and restart cases relevant to the milestone.
- Lint and type checking pass.
- No secrets are present in files or git history.
- Design traceability is updated.
- Known limitations and the exact next milestone are documented.
