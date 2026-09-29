"""Opt-in local Position links; observations never establish runtime readiness."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

from aurum_worker.adapters.native_mt5 import (
    POSITION_LINK_STAGE_CODES,
    MetaTrader5ReadAdapter,
)
from aurum_worker.local_mt5_profile import (
    ProfileError,
    ProfileStore,
    reject_binding_environment,
)
from aurum_worker.models.mt5 import Mt5ReadFailure, Mt5ReasonCode, Mt5WorkerConfig
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY
from aurum_worker.mt5_position_link import (
    LINK_FAILURE_CODES,
    PositionLinkProbe,
    PositionReference,
)
from aurum_worker.mt5_profile_cli import safe_reason

_TRACE_ID = "local-position-time-links"
_POSITION_ARGUMENT = re.compile(
    r"--position=([1-9][0-9]{0,18})@"
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
)
_MAX_TICKET = (1 << 63) - 1


def _print_result(payload: dict[str, object]) -> None:
    # Keep assertions last: observations cannot promote eligibility or smoke.
    observations = {
        name: value
        for name, value in payload.items()
        if name
        not in {"grants_eligibility", "smoke_invoked", "transaction_time_contract"}
    }
    print(
        json.dumps(
            {
                **observations,
                "grants_eligibility": False,
                "smoke_invoked": False,
                "transaction_time_contract": "unverified",
            }
        )
    )


def _references(arguments: list[str]) -> tuple[PositionReference, ...]:
    if arguments.count("--confirm-pepperstone-demo") != 1:
        raise ValueError("Explicit source confirmation required.")
    remaining = [arg for arg in arguments if arg != "--confirm-pepperstone-demo"]
    if not 1 <= len(remaining) <= 10:
        raise ValueError("Bounded Position references required.")
    references: list[PositionReference] = []
    tickets: set[int] = set()
    for argument in remaining:
        match = _POSITION_ARGUMENT.fullmatch(argument)
        if match is None:
            raise ValueError("Invalid Position reference.")
        ticket = int(match[1])
        if ticket > _MAX_TICKET or ticket in tickets:
            raise ValueError("Invalid Position reference.")
        # This naive value is a terminal display label, never an asserted UTC time.
        references.append(
            PositionReference(
                ticket=ticket, opening_label=datetime.fromisoformat(match[2])
            )
        )
        tickets.add(ticket)
    return tuple(references)


def _probe(config: Mt5WorkerConfig, references: tuple[PositionReference, ...]) -> int:
    adapter: MetaTrader5ReadAdapter | None = None
    payload: dict[str, object] = {}
    code = 3
    try:
        adapter = MetaTrader5ReadAdapter(config)
        adapter.connect(trace_id=_TRACE_ID)
        result = adapter.inspect_position_time_links(
            trace_id=_TRACE_ID, references=references
        )
        # Reject copied, constructed, subclassed or otherwise forged report fields.
        checked = PositionLinkProbe.model_validate(result.model_dump(warnings="error"))
        if checked.references_checked != len(references):
            raise ValueError("Position reference count mismatch.")
        payload = checked.model_dump(mode="json")
        code = 0
    except Mt5ReadFailure as error:
        payload = {"status": "blocked", "reason": safe_reason(error)}
        if (
            error.error.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
            and error.error.safe_detail
            in LINK_FAILURE_CODES | POSITION_LINK_STAGE_CODES
        ):
            payload["failure_stage"] = error.error.safe_detail
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
        references = _references(args)
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
    return _probe(config, references)


if __name__ == "__main__":
    raise SystemExit(main())
