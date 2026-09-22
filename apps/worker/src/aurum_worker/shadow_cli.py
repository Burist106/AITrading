"""Operator-invoked Demo/Shadow host; no credential discovery or profile loading."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from threading import Event
from time import monotonic
from uuid import UUID

from pydantic import SecretStr

from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.adapters.worker_http import HttpsWorkerRpcClient
from aurum_worker.models.mt5 import Mt5WorkerConfig
from aurum_worker.shadow.replay_archive import SqliteReplayArchive
from aurum_worker.shadow.runtime import ShadowRuntime


def configured_runtime(values: Mapping[str, str]) -> ShadowRuntime:
    """Composition only; no connection until the explicit runtime start.

    The operator's host injects an existing least-privilege Worker token. This
    function neither issues credentials nor reads a secret file or MT5 password.
    """
    config = Mt5WorkerConfig.from_environ(dict(values))
    if (
        config.terminal_path is None
        or not config.expected_account_fingerprint
        or not config.broker_symbol
        or not config.smoke_confirmed_specification_fingerprint
    ):
        raise ValueError("explicit confirmed Demo binding required")
    # M3 needs each completed minute and short outcome observations. These are
    # fixed bounded read cadences, not a trading-speed control.
    config = Mt5WorkerConfig.model_validate(
        config.model_copy(
            update={
                "tick_poll_seconds": Decimal("1"),
                "full_reconciliation_seconds": Decimal("60"),
            }
        ).model_dump()
    )
    owner = UUID(values["AURUM_SHADOW_OWNER_ID"])
    account = UUID(values["AURUM_SHADOW_ACCOUNT_ID"])
    archive = SqliteReplayArchive(
        Path(values["AURUM_SHADOW_REPLAY_PATH"]),
        owner_id=owner,
        trading_account_id=account,
    )
    rpc = HttpsWorkerRpcClient(
        values["AURUM_SHADOW_SUPABASE_URL"],
        SecretStr(values["AURUM_SHADOW_WORKER_TOKEN"]),
        api_key=SecretStr(values["AURUM_SHADOW_PUBLISHABLE_KEY"]),
    )
    return ShadowRuntime(
        MetaTrader5ReadAdapter(config),
        rpc,
        config,
        owner_id=owner,
        trading_account_id=account,
        replay_archive=archive,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DEMO ONLY / SHADOW read-only journal host"
    )
    parser.add_argument("command", choices=("run",))
    parser.add_argument("--confirm-demo-read-only", action="store_true")
    parser.add_argument("--duration-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    if not args.confirm_demo_read_only or not 1 <= args.duration_seconds <= 3600:
        print("BLOCKED: EXPLICIT_READ_ONLY_CONFIRMATION_REQUIRED")
        return 2
    try:
        runtime = configured_runtime(os.environ)
    except Exception:
        print("BLOCKED: SHADOW_CONFIGURATION_UNAVAILABLE")
        return 2
    started = False
    result_code = 0
    try:
        runtime.start()
        started = True
        print(
            "DEMO ONLY / SHADOW. No broker writes. External evidence remains required."
        )
        deadline = monotonic() + args.duration_seconds
        wait = Event()
        last_status: tuple[str, str] | None = None
        while monotonic() < deadline:
            result = runtime.last_result
            if result is not None:
                status = (
                    result.cycle.status if result.cycle is not None else "BLOCK",
                    result.persistence_code,
                )
                if status != last_status:
                    print(f"SHADOW: {status[0]} / {status[1]}")
                    last_status = status
            if not runtime.poller.state.running:
                print("BLOCKED: WORKER_STOPPED")
                result_code = 2
                break
            wait.wait(0.25)
    except KeyboardInterrupt:
        pass
    except Exception:
        print("BLOCKED: SHADOW_RUNTIME_UNAVAILABLE")
        result_code = 2
    finally:
        if started:
            try:
                runtime.stop()
            except Exception:
                print("BLOCKED: SHADOW_SHUTDOWN_UNAVAILABLE")
                result_code = 2
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
