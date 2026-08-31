"""Local-only account fingerprint and optional real-terminal read-only smoke CLI."""

from __future__ import annotations

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
from aurum_worker.mt5_safety import is_canonical_xauusd, verify_account
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
        "TICK_STALE",
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
            reason = (
                Mt5ReasonCode.TICK_FROM_FUTURE
                if tick.freshness is TickFreshness.FUTURE_INVALID
                else Mt5ReasonCode.TICK_STALE
            )
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
        if args == ["smoke"]:
            print("FAILED — CONFIG_INVALID")
            return 3
        print("Configuration invalid")
        return 2
    if args == ["fingerprint"]:
        return _fingerprint(config)
    if args == ["smoke"]:
        return _smoke(config)
    print("Usage: aurum-mt5-readonly [fingerprint|smoke]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
