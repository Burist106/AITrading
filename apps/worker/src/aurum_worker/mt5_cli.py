"""Local-only account fingerprint and optional real-terminal read-only smoke CLI."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta

from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    AccountVerificationState,
    CandleRequest,
    ConfirmedSymbolBinding,
    DatabaseReconciliationState,
    HealthState,
    HistoryRequest,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReconciliationOutcome,
    SafeMt5Error,
    SymbolUsabilityState,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_safety import (
    is_canonical_xauusd,
    utc_from_epoch,
    utc_from_epoch_milliseconds,
    verify_account,
)
from aurum_worker.reconciliation import ReadOnlyReconciliationService

_NOT_RUN = "NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET"
_PASSED = "PASSED — REAL MT5 READ-ONLY SMOKE"
_BLOCKED_REASON_VALUES = frozenset(
    {
        "ACCOUNT_BINDING_MISMATCH",
        "CONTEST_ACCOUNT_BLOCKED",
        "DEMO_ACCOUNT_UNBOUND",
        "CANDLE_DATA_STALE",
        "HISTORY_WINDOW_INCOMPLETE",
        "REAL_ACCOUNT_BLOCKED",
        "RECONCILIATION_INCOMPLETE",
        "SYMBOL_AMBIGUOUS",
        "SYMBOL_CANONICAL_MISMATCH",
        "SYMBOL_NOT_CONFIGURED",
        "SYMBOL_NOT_FOUND",
        "SYMBOL_NOT_VISIBLE",
        "SYMBOL_SPEC_CHANGED",
        "SYMBOL_SPEC_CONFIRMATION_REQUIRED",
        "SYMBOL_SPEC_INCOMPLETE",
        "TICK_FROM_FUTURE",
        "TICK_DELAYED",
        "TICK_STALE",
        "TICK_UNAVAILABLE",
        "TRADE_MODE_UNKNOWN",
    }
)


def _failure(reason: Mt5ReasonCode, detail: str) -> Mt5ReadFailure:
    return Mt5ReadFailure(
        SafeMt5Error(reason_code=reason, safe_detail=detail, retryable=False)
    )


def _smoke_failure_outcome(failure: Mt5ReadFailure) -> tuple[int, str]:
    reason = failure.error.reason_code.value
    if reason in _BLOCKED_REASON_VALUES:
        return 2, f"BLOCKED — {reason}"
    return 3, f"FAILED — {reason}"


def _smoke_database_state(
    config: Mt5WorkerConfig, confirmed_at: datetime
) -> DatabaseReconciliationState:
    fingerprint = config.smoke_confirmed_specification_fingerprint
    if fingerprint is None or config.broker_symbol is None:
        return DatabaseReconciliationState()
    return DatabaseReconciliationState(
        confirmed_symbol_binding=ConfirmedSymbolBinding(
            owner_id="00000000-0000-4000-8000-000000000001",
            trading_account_id="00000000-0000-4000-8000-000000000002",
            canonical_symbol="XAUUSD",
            broker_symbol=config.broker_symbol,
            confirmed_specification_fingerprint=fingerprint,
            confirmation_status="confirmed",
            confirmed_at=confirmed_at,
            confirmed_by="00000000-0000-4000-8000-000000000003",
            version=1,
        )
    )


def _fingerprint(config: Mt5WorkerConfig) -> int:
    adapter = MetaTrader5ReadAdapter(config)
    try:
        adapter.connect(trace_id="local-fingerprint")
        account = adapter.get_account_info(trace_id="local-fingerprint")
        verification = verify_account(account, config.expected_account_fingerprint)
        print(f"Account mode: {account.trade_mode.value.upper()}")
        print(f"Account identity: {account.masked_login}")
        print(f"Server identity: {account.masked_server}")
        print(f"Binding fingerprint: {account.account_fingerprint}")
        print(f"Verification state: {verification.state.value}")
        return 0 if account.trade_mode is AccountTradeMode.DEMO else 2
    except Mt5ReadFailure as failure:
        print(f"Fingerprint unavailable: {failure.error.reason_code}")
        return 2
    finally:
        adapter.disconnect()


def _smoke(config: Mt5WorkerConfig) -> int:
    if not config.readonly_smoke or config.terminal_path is None:
        print(_NOT_RUN)
        return 0
    if not config.broker_symbol:
        print("BLOCKED — SYMBOL_NOT_CONFIGURED")
        return 2
    adapter: MetaTrader5ReadAdapter | None = None
    exit_code = 3
    output = "FAILED — UNEXPECTED_ERROR"
    try:
        adapter = MetaTrader5ReadAdapter(config)
        persistence = InMemoryMt5ObservationPersistence(
            database_state=_smoke_database_state(config, datetime.now(UTC))
        )
        reconciliation = ReadOnlyReconciliationService(adapter, persistence, config)
        terminal = adapter.connect(trace_id="local-readonly-smoke")
        if not terminal.connected:
            raise _failure(
                Mt5ReasonCode.TERMINAL_DISCONNECTED,
                "Terminal reported a disconnected state.",
            )
        account = adapter.get_account_info(trace_id="local-readonly-smoke")
        verification = verify_account(account, config.expected_account_fingerprint)
        if verification.state is not AccountVerificationState.VERIFIED_DEMO_BOUND:
            raise _failure(
                verification.reason_code,
                "Demo account binding policy was not satisfied.",
            )
        specification = adapter.get_symbol_specification(
            config.broker_symbol, trace_id="local-readonly-smoke"
        )
        if not is_canonical_xauusd(
            specification.canonical_symbol,
            specification.base_currency,
            specification.profit_currency,
        ):
            raise _failure(
                Mt5ReasonCode.SYMBOL_CANONICAL_MISMATCH,
                "Configured broker symbol is not canonical XAU/USD.",
            )
        if specification.usability_state is not SymbolUsabilityState.USABLE:
            raise _failure(
                specification.unusable_reason or Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE,
                "Configured broker symbol is not usable.",
            )
        tick = adapter.get_latest_tick(
            config.broker_symbol, trace_id="local-readonly-smoke"
        )
        if tick.freshness is not TickFreshness.LIVE:
            reason = {
                TickFreshness.DELAYED: Mt5ReasonCode.TICK_DELAYED,
                TickFreshness.STALE: Mt5ReasonCode.TICK_STALE,
                TickFreshness.FUTURE_INVALID: Mt5ReasonCode.TICK_FROM_FUTURE,
                TickFreshness.UNAVAILABLE: Mt5ReasonCode.TICK_UNAVAILABLE,
            }[tick.freshness]
            raise _failure(reason, "Latest tick is not acceptable for the smoke test.")
        candles = adapter.get_candles(
            config.broker_symbol,
            Timeframe.M1,
            CandleRequest(start_position=1, count=5),
            trace_id="local-readonly-smoke",
        )
        if not candles.candles or any(
            not candle.is_complete for candle in candles.candles
        ):
            raise _failure(
                Mt5ReasonCode.CANDLE_DATA_INVALID,
                "Completed candle verification failed.",
            )
        adapter.get_open_positions(trace_id="local-readonly-smoke")
        adapter.get_active_orders(trace_id="local-readonly-smoke")
        now = datetime.now(UTC)
        history = HistoryRequest(start_at=now - timedelta(hours=1), end_at=now)
        adapter.get_order_history(history, trace_id="local-readonly-smoke")
        adapter.get_deal_history(history, trace_id="local-readonly-smoke")
        report = reconciliation.run(trace_id="local-readonly-smoke")
        if (
            report.report.outcome is not ReconciliationOutcome.MATCHED
            or report.health.state is not HealthState.HEALTHY
        ):
            reason = report.health.reason_code
            if reason is Mt5ReasonCode.HEALTHY:
                reason = Mt5ReasonCode.RECONCILIATION_INCOMPLETE
            raise _failure(reason, "Read-only reconciliation did not pass.")
        exit_code = 0
        output = _PASSED
    except Mt5ReadFailure as failure:
        exit_code, output = _smoke_failure_outcome(failure)
    except Exception:
        exit_code = 3
        output = "FAILED — UNEXPECTED_ERROR"
    finally:
        if adapter is not None:
            try:
                adapter.disconnect()
            except Exception:
                exit_code = 3
                output = "FAILED — SHUTDOWN_FAILED"
    print(output)
    return exit_code


def _diagnostic_output(payload: dict[str, object], code: int) -> int:
    print(
        json.dumps(
            {
                "diagnostic": "tick_time_v1",
                "grants_eligibility": False,
                "smoke_invoked": False,
                **payload,
            }
        )
    )
    return code


def _tick_time(config: Mt5WorkerConfig) -> int:
    """Explicit local diagnostic, not a smoke test or a health/eligibility check."""
    for present, reason in (
        (config.terminal_path is not None, "TERMINAL_PATH_NOT_CONFIGURED"),
        (bool(config.broker_symbol), "SYMBOL_NOT_CONFIGURED"),
        (bool(config.expected_account_fingerprint), "DEMO_ACCOUNT_UNBOUND"),
        (
            bool(config.smoke_confirmed_specification_fingerprint),
            "SYMBOL_SPEC_CONFIRMATION_REQUIRED",
        ),
    ):
        if not present:
            return _diagnostic_output({"status": "blocked", "reason": reason}, 2)
    if (
        config.readonly_smoke
        or config.max_tick_age_seconds != 10
        or config.max_clock_drift_seconds != 30
    ):
        return _diagnostic_output({"status": "failed", "reason": "CONFIG_INVALID"}, 3)
    adapter: MetaTrader5ReadAdapter | None = None
    payload: dict[str, object] = {"status": "failed", "reason": "UNEXPECTED_ERROR"}
    code = 3
    try:
        adapter = MetaTrader5ReadAdapter(config)
        adapter.connect(trace_id="local-tick-time-diagnostic")
        assert config.broker_symbol is not None
        evidence = adapter.get_tick_time_diagnostic(
            config.broker_symbol, trace_id="local-tick-time-diagnostic"
        )
        seconds_at = utc_from_epoch(evidence.native_time)
        milliseconds_at = (
            utc_from_epoch_milliseconds(evidence.native_time_msc)
            if evidence.native_time_msc
            else None
        )
        selected = milliseconds_at or seconds_at
        observed = evidence.observed_at.astimezone(UTC)
        signed_age = (observed - selected).total_seconds()
        payload = {
            "status": "observed",
            "timestamp_interpretation": (
                "epoch interpreted as UTC; source convention not established"
            ),
            "worker_utc": observed.isoformat(),
            "native_time": evidence.native_time,
            "native_time_msc": evidence.native_time_msc,
            "time_as_utc": seconds_at.isoformat(),
            "time_msc_as_utc": milliseconds_at.isoformat() if milliseconds_at else None,
            "selected_field": "time_msc" if milliseconds_at else "time",
            "selected_as_utc": selected.isoformat(),
            "whole_seconds_agree": (
                evidence.native_time_msc // 1000 == evidence.native_time
                if evidence.native_time_msc
                else None
            ),
            "signed_age_seconds": str(signed_age),
            "future_limit_exceeded": signed_age < -config.max_clock_drift_seconds,
            "age_limit_exceeded": signed_age > config.max_tick_age_seconds,
            "max_tick_age_seconds": config.max_tick_age_seconds,
            "max_clock_drift_seconds": config.max_clock_drift_seconds,
        }
        code = 0
    except Mt5ReadFailure as failure:
        code, _ = _smoke_failure_outcome(failure)
        payload = {
            "status": "blocked" if code == 2 else "failed",
            "reason": failure.error.reason_code.value,
        }
    except Exception:
        payload = {"status": "failed", "reason": "UNEXPECTED_ERROR"}
        code = 3
    finally:
        if adapter is not None:
            try:
                adapter.disconnect()
            except Exception:
                payload = {"status": "failed", "reason": "SHUTDOWN_FAILED"}
                code = 3
    return _diagnostic_output(payload, code)


def _smoke_preconditions_present() -> bool:
    """Check opt-in preconditions without parsing or starting smoke configuration."""

    return os.environ.get("AURUM_MT5_READONLY_SMOKE") == "1" and bool(
        os.environ.get("AURUM_MT5_TERMINAL_PATH", "").strip()
    )


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    if args == ["smoke"] and not _smoke_preconditions_present():
        print(_NOT_RUN)
        return 0
    try:
        config = Mt5WorkerConfig.from_environ()
    except Exception:
        if args == ["tick-time"]:
            return _diagnostic_output(
                {"status": "failed", "reason": "CONFIG_INVALID"}, 3
            )
        if args == ["smoke"]:
            print("FAILED — CONFIG_INVALID")
            return 3
        print("Configuration invalid")
        return 2
    if args == ["fingerprint"]:
        return _fingerprint(config)
    if args == ["smoke"]:
        return _smoke(config)
    if args == ["tick-time"]:
        return _tick_time(config)
    print("Usage: aurum-mt5-readonly [fingerprint|smoke|tick-time]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
