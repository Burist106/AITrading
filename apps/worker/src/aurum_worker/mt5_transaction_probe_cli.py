"""Opt-in, read-only transaction-time evidence; never a runtime time policy."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.local_mt5_profile import (
    ProfileError,
    ProfileStore,
    reject_binding_environment,
)
from aurum_worker.models.mt5 import Mt5ReadFailure, Mt5WorkerConfig
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY
from aurum_worker.mt5_profile_cli import safe_reason
from aurum_worker.mt5_transaction_probe import OperatorTimeWindow, TransactionTimeProbe

_TRACE_ID = "local-transaction-time-probe"


def _print_result(payload: dict[str, object]) -> None:
    # Fixed assertions are last: no observation can promote readiness or smoke.
    print(
        json.dumps(
            {
                **payload,
                "grants_eligibility": False,
                "smoke_invoked": False,
                "transaction_time_contract": "unverified",
            }
        )
    )


def _reference(arguments: list[str]) -> OperatorTimeWindow | None:
    if arguments.count("--confirm-pepperstone-demo") != 1:
        raise ValueError("Explicit source confirmation required.")
    remaining = [arg for arg in arguments if arg != "--confirm-pepperstone-demo"]
    if not remaining:
        return None
    if len(remaining) != 2:
        raise ValueError("Paired reference window required.")
    options: dict[str, str] = {}
    for argument in remaining:
        name, separator, value = argument.partition("=")
        if (
            separator != "="
            or name not in {"--reference-start", "--reference-end"}
            or name in options
            or not value
        ):
            raise ValueError("Unsupported probe argument.")
        options[name] = value
    if options.keys() != {"--reference-start", "--reference-end"}:
        raise ValueError("Paired reference window required.")
    return OperatorTimeWindow(
        start_at=datetime.fromisoformat(options["--reference-start"]),
        end_at=datetime.fromisoformat(options["--reference-end"]),
    )


def _probe(config: Mt5WorkerConfig, reference: OperatorTimeWindow | None) -> int:
    adapter: MetaTrader5ReadAdapter | None = None
    payload: dict[str, object] = {}
    code = 3
    try:
        adapter = MetaTrader5ReadAdapter(config)
        adapter.connect(trace_id=_TRACE_ID)
        result = adapter.inspect_transaction_time_probe(
            trace_id=_TRACE_ID, reference=reference
        )
        # Revalidate at the output boundary, including forbidden extra fields.
        checked = TransactionTimeProbe.model_validate(
            result.model_dump(warnings="error")
        )
        payload = checked.model_dump(mode="json")
        code = 0
    except Mt5ReadFailure as error:
        payload = {"status": "blocked", "reason": safe_reason(error)}
        code = 2
    except Exception as error:
        payload = {"status": "failed", "reason": safe_reason(error)}
    finally:
        if adapter is not None:
            try:
                adapter.disconnect()
            except Exception:
                payload = {"status": "failed", "reason": "SHUTDOWN_FAILED"}
                code = 3
    _print_result(payload)
    return code


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    try:
        reference = _reference(args)
    except Exception:
        _print_result({"status": "blocked", "reason": "PROBE_ARGUMENTS_INVALID"})
        return 2
    try:
        reject_binding_environment()
        if os.environ.get("AURUM_MT5_READONLY_SMOKE") not in {None, "", "0"}:
            raise ProfileError("PROFILE_SMOKE_CONFLICT")
        profile = ProfileStore().load()
        config = Mt5WorkerConfig(
            **{
                **profile.worker_config().model_dump(),
                "market_time_policy": PEPPERSTONE_POLICY,
            }
        )
    except Exception as error:
        _print_result({"status": "blocked", "reason": safe_reason(error)})
        return 2
    return _probe(config, reference)


if __name__ == "__main__":
    raise SystemExit(main())
