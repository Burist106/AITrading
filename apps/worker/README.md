# Aurum Worker — Demo/Shadow production components

This package contains the typed Demo-only Worker foundation plus deterministic
fake and Windows-only native MT5 read adapters. The native package is an
optional dependency; non-Windows development remains MT5-independent.

The package provides broker observations, sanitized persistence reporting,
health, polling, and reconciliation. Milestone 3 is in progress: `shadow/market.py`
adds a bounded confirmed-source market/feature stage and `shadow/risk.py` adds
deterministic risk calculations from explicit current evidence. Both are
non-executing components, now connected by `shadow/runtime.py` and `pipeline.py`
to a versioned research baseline, immutable Shadow RPC journal and the dashboard.
Real ledger/news/cost/safety providers and native acceptance remain incomplete.
Risk-reached cycles also require an explicit outside-checkout local replay archive
before remote publication. `pnpm worker:shadow:replay` verifies one historical
record without MT5, network access or credentials. This proves deterministic
reproduction only; it does not confirm a remote write or genuine source truth.
See `docs/SHADOW_REPLAY.md` for archive setup, privacy and bounds.
See `docs/MILESTONE_3_IMPLEMENTATION.md` at the
repository root for interfaces, requirements and verification.

It contains no broker mutation, Position mutation, executable strategy, command
consumer, or order-execution capability. Missing native transaction-time evidence
still blocks full reconciliation; a component test is not a real-terminal pass.

Install with `pnpm worker:install`; on Windows, use
`pnpm worker:install:mt5` to include the pinned official read boundary. See
`docs/MT5_READ_ONLY.md` for configuration and the optional smoke command.

## Local checks

From this directory, after installing the `dev` extra:

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests
python -m pytest
python -m hatchling build
```
