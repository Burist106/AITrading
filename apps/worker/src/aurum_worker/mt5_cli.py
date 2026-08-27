"""Local-only account fingerprint and optional real-terminal read-only smoke CLI."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    CandleRequest,
    HistoryRequest,
    Mt5ReadFailure,
    Mt5WorkerConfig,
    Timeframe,
)
from aurum_worker.mt5_safety import verify_account
from aurum_worker.reconciliation import ReadOnlyReconciliationService

_NOT_RUN = "NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET"


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
    adapter = MetaTrader5ReadAdapter(config)
    persistence = InMemoryMt5ObservationPersistence()
    reconciliation = ReadOnlyReconciliationService(adapter, persistence, config)
    try:
        terminal = adapter.connect(trace_id="local-readonly-smoke")
        account = adapter.get_account_info(trace_id="local-readonly-smoke")
        if account.trade_mode is not AccountTradeMode.DEMO:
            print(f"BLOCKED — account mode {account.trade_mode.value.upper()}")
            return 2
        if not config.broker_symbol:
            print(_NOT_RUN)
            return 0
        specification = adapter.get_symbol_specification(
            config.broker_symbol, trace_id="local-readonly-smoke"
        )
        tick = adapter.get_latest_tick(
            config.broker_symbol, trace_id="local-readonly-smoke"
        )
        candles = adapter.get_candles(
            config.broker_symbol,
            Timeframe.M1,
            CandleRequest(start_position=1, count=5),
            trace_id="local-readonly-smoke",
        )
        positions = adapter.get_open_positions(trace_id="local-readonly-smoke")
        orders = adapter.get_active_orders(trace_id="local-readonly-smoke")
        now = datetime.now(UTC)
        history = HistoryRequest(start_at=now - timedelta(hours=1), end_at=now)
        historical_orders = adapter.get_order_history(
            history, trace_id="local-readonly-smoke"
        )
        deals = adapter.get_deal_history(history, trace_id="local-readonly-smoke")
        report = reconciliation.run(trace_id="local-readonly-smoke")
        print(f"Terminal version: {terminal.terminal_version}")
        print(f"Account mode: {account.trade_mode.value.upper()}")
        print(f"Account identity: {account.masked_login}")
        print(f"Server identity: {account.masked_server}")
        print(f"Broker symbol: {specification.broker_symbol}")
        print(f"Tick freshness: {tick.freshness.value}")
        print(f"Completed M1 candles: {len(candles.candles)}")
        print(f"Open Positions: {len(positions)}")
        print(f"Active Orders: {len(orders)}")
        print(f"Historical Orders: {len(historical_orders)}")
        print(f"Historical Deals: {len(deals)}")
        print(f"Reconciliation: {report.report.outcome.value}")
        return 0
    except (Mt5ReadFailure, OSError):
        print(_NOT_RUN)
        return 0
    finally:
        adapter.disconnect()


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    config = Mt5WorkerConfig.from_environ()
    if args == ["fingerprint"]:
        return _fingerprint(config)
    if args == ["smoke"]:
        return _smoke(config)
    print("Usage: aurum-mt5-readonly [fingerprint|smoke]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
