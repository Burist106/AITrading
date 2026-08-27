# Codex Next Prompts

Do not use these until the preceding milestone passes its acceptance gates.

## Next prompt — Milestone 1

```text
Read AGENTS.md, docs/P0_ACCEPTANCE_GATES.md, docs/IMPLEMENTATION_ROADMAP.md, docs/DECISIONS.md, and the current repository state.

Implement only Milestone 1 — Supabase Domain and Security Foundation.

Deliver the operational schema, migrations, RLS policies and tests, durable system_commands with typed payload validation, trade proposals, risk checks, positions, position events, incidents, audit logs, and single-user Auth integration. The browser must not directly write protected operational records. Realtime is wake-up/notification only. Use local Supabase tests where possible.

Do not implement MT5 order execution, trading strategy, LINE approval, Conditional Auto, or Live Trading.

Run all checks and report exact evidence against the milestone exit gate.
```

## Next prompt — Milestone 2

```text
Read all project instructions and verify Milestone 1 gates are complete.

Implement only Milestone 2 — Read-only Windows MT5 Worker.

Add an MT5 adapter for initialize/shutdown, Demo-account verification, Live-account fail-closed detection, symbol discovery, broker symbol specification, latest tick, historical candles, open positions, order history, Worker heartbeat, and system health. Provide a fake MT5 adapter so CI runs without MetaTrader installed.

Do not implement order_send, broker writes, position modification, Conditional Auto, or Live Trading.
```

## Next prompt — Milestone 3

```text
Verify earlier milestone gates, then implement only Milestone 3 — Shadow Pipeline.

Create normalized market data, a deterministic rule-based baseline strategy, eligibility policy, deterministic Risk Engine, Trade Proposal generation, Risk Checks, decision provenance, Supabase persistence, and shadow outcome journaling. WAIT and BLOCK are valid outcomes. Include realistic trading-cost fields, but do not send or simulate broker orders as successful executions.

Do not implement order_send, LINE approval, Conditional Auto, or Live Trading.
```
