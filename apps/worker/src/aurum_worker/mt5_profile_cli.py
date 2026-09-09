"""Opt-in profile-backed local commands, separate from legacy environment commands."""

from __future__ import annotations

import os
import sys

from aurum_worker import mt5_cli
from aurum_worker.local_mt5_profile import (
    ProfileError,
    ProfileStore,
    reject_binding_environment,
)
from aurum_worker.models.mt5 import Mt5ReadFailure, Mt5ReasonCode
from aurum_worker.mt5_profile_setup import verify_saved_binding

_PROFILE_CODES = frozenset(
    {
        "PROFILE_WINDOWS_ONLY",
        "PROFILE_LOCATION_INVALID",
        "PROFILE_INVALID",
        "PROFILE_READ_FAILED",
        "PROFILE_NOT_CONFIGURED",
        "PROFILE_UNREADABLE",
        "PROFILE_WRITE_FAILED",
        "PROFILE_BUSY",
        "PROFILE_CHANGED",
        "PROFILE_CANCELLED",
        "PROFILE_ENV_CONFLICT",
        "PROFILE_LIMIT_CONFLICT",
        "PROFILE_SMOKE_CONFLICT",
        "PROFILE_CLEANUP_FAILED",
    }
)


def safe_reason(error: Exception) -> str:
    if isinstance(error, Mt5ReadFailure):
        return error.error.reason_code.value
    if isinstance(error, ProfileError):
        code = str(error)
        if code in _PROFILE_CODES or code in {item.value for item in Mt5ReasonCode}:
            return code
    return "PROFILE_FAILED"


def run_saved(action: str, store: ProfileStore | None = None) -> int:
    if action not in {"status", "check", "tick-time", "smoke"}:
        print("Usage: aurum-mt5-profile [gui|status|check|tick-time|smoke]")
        return 2
    # Consent is per invocation, never persisted or inferred from profile existence.
    if action == "smoke" and os.environ.get("AURUM_MT5_READONLY_SMOKE") != "1":
        print("NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET")
        return 0
    try:
        reject_binding_environment()
        if action != "smoke" and os.environ.get("AURUM_MT5_READONLY_SMOKE") not in {
            None,
            "",
            "0",
        }:
            raise ProfileError("PROFILE_SMOKE_CONFLICT")
        local = store if store is not None else ProfileStore()
        profile = local.load()
        if action == "status":
            print("CONFIGURED — ENCRYPTED LOCAL PROFILE (NOT VERIFIED; NOT SMOKE)")
            return 0
        if action == "tick-time":
            return mt5_cli._tick_time(profile.worker_config())
        verify_saved_binding(profile)
        if action == "smoke":
            return mt5_cli._smoke(profile.worker_config(smoke=True))
        print("VERIFIED — SAVED DEMO ACCOUNT AND SYMBOL MATCH (NOT SMOKE)")
        return 0
    except Exception as error:
        reason = safe_reason(error)
        blocked = reason in mt5_cli._BLOCKED_REASON_VALUES or reason in {
            "PROFILE_NOT_CONFIGURED",
            "PROFILE_CANCELLED",
            "PROFILE_CHANGED",
            "PROFILE_BUSY",
            "PROFILE_ENV_CONFLICT",
            "PROFILE_LIMIT_CONFLICT",
            "PROFILE_SMOKE_CONFLICT",
        }
        print(f"{'BLOCKED' if blocked else 'FAILED'} — {reason}")
        return 2 if blocked else 3


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    if args == ["gui"]:
        if sys.platform != "win32":
            print("BLOCKED — PROFILE_WINDOWS_ONLY")
            return 2
        try:
            from aurum_worker.mt5_profile_ui import open_profile_window

            return open_profile_window()
        except Exception:
            print("BLOCKED — PROFILE_UI_UNAVAILABLE")
            return 2
    return run_saved(args[0] if len(args) == 1 else "")


if __name__ == "__main__":
    raise SystemExit(main())
