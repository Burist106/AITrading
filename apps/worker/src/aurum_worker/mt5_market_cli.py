"""Explicit process-only, bound Pepperstone Demo market-time validation.

This is not a profile migration, provider discovery, transaction-time contract,
or readiness grant. Raw diagnostic and legacy commands remain unchanged.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta

from aurum_worker import mt5_cli
from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.local_mt5_profile import (
    ProfileError,
    ProfileStore,
    reject_binding_environment,
)
from aurum_worker.models.mt5 import (
    CandleRequest,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    SafeMt5Error,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_market_provider import PUBLIC_PROVIDER_FAILURE_DETAILS
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY
from aurum_worker.mt5_profile_cli import safe_reason
from aurum_worker.mt5_transaction_inventory import InventoryLookback


def _require_live(freshness: TickFreshness) -> None:
    if freshness is TickFreshness.LIVE:
        return
    reason = {
        TickFreshness.DELAYED: Mt5ReasonCode.TICK_DELAYED,
        TickFreshness.STALE: Mt5ReasonCode.TICK_STALE,
        TickFreshness.FUTURE_INVALID: Mt5ReasonCode.TICK_FROM_FUTURE,
        TickFreshness.UNAVAILABLE: Mt5ReasonCode.TICK_UNAVAILABLE,
    }[freshness]
    raise Mt5ReadFailure(
        SafeMt5Error(
            reason_code=reason,
            safe_detail="Market validation requires a current tick.",
        )
    )


def _market_check(config: Mt5WorkerConfig) -> int:
    adapter = MetaTrader5ReadAdapter(config)
    payload: dict[str, object] = {"status": "failed", "reason": "UNEXPECTED_ERROR"}
    code = 3
    try:
        adapter.connect(trace_id="local-market-time-check")
        tick = adapter.get_latest_tick(
            config.broker_symbol or "", trace_id="local-market-time-check"
        )
        _require_live(tick.freshness)
        if tick.freshness is TickFreshness.LIVE:
            candles = adapter.get_candles(
                config.broker_symbol or "",
                Timeframe.M1,
                CandleRequest(start_position=1, count=5),
                trace_id="local-market-time-check",
            )
            if (
                len(candles.candles) != 5
                or candles.gaps
                or not all(c.is_complete for c in candles.candles)
            ):
                raise Mt5ReadFailure(
                    SafeMt5Error(
                        reason_code=Mt5ReasonCode.CANDLE_DATA_INVALID,
                        safe_detail="Completed contiguous candles unavailable.",
                    )
                )
            repeated = adapter.get_candles(
                config.broker_symbol or "",
                Timeframe.M1,
                CandleRequest(
                    count=5,
                    range_start=candles.candles[0].open_at,
                    range_end=candles.candles[-1].open_at,
                ),
                trace_id="local-market-time-check",
            )
            # Compare actual content in memory. Export no prices or identities.
            fields = {
                "open_at",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "spread",
                "real_volume",
                "is_complete",
            }
            if repeated.gaps or (
                [c.model_dump(include=fields) for c in candles.candles]
                != [c.model_dump(include=fields) for c in repeated.candles]
            ):
                raise Mt5ReadFailure(
                    SafeMt5Error(
                        reason_code=Mt5ReasonCode.CANDLE_DATA_INVALID,
                        safe_detail="Candle range roundtrip did not match.",
                    )
                )
            # Slow native requests must not reuse the initial freshness result.
            tick = adapter.get_latest_tick(
                config.broker_symbol or "", trace_id="local-market-time-check"
            )
            _require_live(tick.freshness)
            close_age = (
                tick.observed_at - (candles.candles[-1].open_at + timedelta(minutes=1))
            ).total_seconds()
            if not 0 <= close_age <= 60:
                raise Mt5ReadFailure(
                    SafeMt5Error(
                        reason_code=Mt5ReasonCode.CANDLE_DATA_INVALID,
                        safe_detail="Latest completed candle is not current.",
                    )
                )
            payload = {
                "status": "market_check_passed",
                "policy": config.market_time_policy,
                "observed_at": tick.observed_at.isoformat(),
                "tick_at_utc": tick.tick_at.isoformat(),
                "tick_age_seconds": str(tick.age_seconds),
                "completed_m1_count": len(candles.candles),
                "last_m1_open_utc": candles.candles[-1].open_at.isoformat(),
                "range_roundtrip_matched": True,
                "transaction_time_contract": "unverified",
            }
            code = 0
    except Mt5ReadFailure as error:
        payload = {"status": "blocked", "reason": safe_reason(error)}
        if (
            error.error.reason_code is Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH
            and error.error.safe_detail in PUBLIC_PROVIDER_FAILURE_DETAILS
        ):
            # Only known constants may leave the process; never echo a company,
            # account, server, native structure, or arbitrary failure detail.
            payload["provider_evidence"] = error.error.safe_detail
        code = 2
    except Exception:
        payload = {"status": "failed", "reason": "MARKET_CHECK_FAILED"}
        code = 3
    finally:
        try:
            adapter.disconnect()
        except Exception:
            payload = {"status": "failed", "reason": "SHUTDOWN_FAILED"}
            code = 3
    print(json.dumps({"grants_eligibility": False, "smoke_invoked": False, **payload}))
    return code


def _transaction_inventory(
    config: Mt5WorkerConfig, *, lookback_days: InventoryLookback = 7
) -> int:
    adapter = MetaTrader5ReadAdapter(config)
    payload: dict[str, object] = {}
    code = 3
    try:
        adapter.connect(trace_id="local-transaction-inventory")
        result = adapter.inspect_transaction_inventory(
            trace_id="local-transaction-inventory", lookback_days=lookback_days
        )
        payload = result.model_dump(mode="json")
        code = 0
    except Mt5ReadFailure as error:
        payload = {"status": "blocked", "reason": safe_reason(error)}
        code = 2
    except Exception:
        payload = {"status": "failed", "reason": "TRANSACTION_INVENTORY_FAILED"}
    finally:
        try:
            adapter.disconnect()
        except Exception:
            payload = {"status": "failed", "reason": "SHUTDOWN_FAILED"}
            code = 3
    print(json.dumps({"grants_eligibility": False, "smoke_invoked": False, **payload}))
    return code


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    lookback_days: InventoryLookback = 7
    if args == ["inventory", "--confirm-pepperstone-demo", "--lookback-days=30"]:
        lookback_days = 30
        args = args[:2]
    if (
        len(args) != 2
        or args[0] not in {"check", "smoke", "inventory"}
        or args[1] != "--confirm-pepperstone-demo"
    ):
        print("BLOCKED — Explicit Pepperstone Demo source confirmation required.")
        return 2
    action = args[0]
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
        profile = ProfileStore().load()
        config = Mt5WorkerConfig(
            **{
                **profile.worker_config(smoke=action == "smoke").model_dump(),
                "market_time_policy": PEPPERSTONE_POLICY,
            }
        )
        if action == "smoke":
            return mt5_cli._smoke(config)
        if action == "inventory":
            return _transaction_inventory(config, lookback_days=lookback_days)
        return _market_check(config)
    except Exception as error:
        print(f"BLOCKED — {safe_reason(error)}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
