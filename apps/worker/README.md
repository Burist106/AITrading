# Aurum Worker — Bootstrap scaffold

This package is a typed, MT5-independent Worker foundation for the Bootstrap
Milestone. It validates shared wire contracts and verifies the fixed Demo safety
policy before a Worker may start in Shadow mode.

The package intentionally exposes only broker reads and subsystem health
boundaries. It contains no broker mutation, Position mutation, trading strategy,
or order-execution capability.

## Local checks

From this directory, after installing the `dev` extra:

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests
python -m pytest
python -m hatchling build
```
