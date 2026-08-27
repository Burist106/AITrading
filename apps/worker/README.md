# Aurum Worker — Milestone 2 read-only boundary

This package contains the typed Demo-only Worker foundation plus deterministic
fake and Windows-only native MT5 read adapters. The native package is an
optional dependency; non-Windows development remains MT5-independent.

The package exposes only broker observations, sanitized persistence reporting,
health, polling, and reconciliation. It contains no broker mutation, Position
mutation, trading strategy, command consumer, or order-execution capability.

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
