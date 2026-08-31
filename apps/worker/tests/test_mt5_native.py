from __future__ import annotations

import ast
import importlib
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from mt5_factories import NOW, RAW_LOGIN, RAW_SERVER

from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.adapters.protocols import Mt5ReadPort
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    CandleRequest,
    HistoryRequest,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    Timeframe,
)


class NativeModuleFake:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.initialize_paths: list[str] = []
        self.initialize_result = True
        self.terminal_result: object | None = SimpleNamespace(
            connected=True, trade_allowed=False
        )
        self.account_result: object | None = SimpleNamespace(
            login=RAW_LOGIN,
            server=RAW_SERVER,
            trade_mode=0,
            currency="USD",
            leverage=100,
            name="must-not-cross-boundary",
        )
        self.tick_result: object | None = SimpleNamespace(
            bid=2345.1,
            ask=2345.3,
            time=int(NOW.timestamp()),
            time_msc=int(NOW.timestamp() * 1000),
        )
        self.symbol_result: object | None = SimpleNamespace(
            name="XAUUSD",
            path="Metals",
            description="Gold versus US Dollar",
            currency_base="XAU",
            currency_profit="USD",
            currency_margin="USD",
            visible=True,
            digits=2,
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            trade_tick_value_profit=1.0,
            trade_tick_value_loss=1.0,
            trade_contract_size=100.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_stops_level=10,
            trade_freeze_level=0,
            trade_calc_mode=1,
            trade_mode=4,
            filling_mode=1,
            expiration_mode=7,
            order_mode=127,
        )
        self.symbol_catalog_result: object | None = None
        self.position_result: object | None = ()
        self.order_result: object | None = ()
        self.order_history_result: object | None = ()
        self.deal_history_result: object | None = ()
        self.rate_result: object | None = None
        self.active_terminal_calls = 0
        self.max_active_terminal_calls = 0
        self._call_lock = threading.Lock()

    def initialize(self, path: str, /) -> bool:
        self.calls.append("initialize")
        self.initialize_paths.append(path)
        assert Path(path).is_absolute()
        return self.initialize_result

    def shutdown(self) -> None:
        self.calls.append("shutdown")

    def version(self) -> object:
        self.calls.append("version")
        return (5, 0, 6090)

    def last_error(self) -> object:
        self.calls.append("last_error")
        return (-1, "raw native diagnostic")

    def terminal_info(self) -> object:
        self.calls.append("terminal_info")
        with self._call_lock:
            self.active_terminal_calls += 1
            self.max_active_terminal_calls = max(
                self.max_active_terminal_calls, self.active_terminal_calls
            )
        time.sleep(0.01)
        with self._call_lock:
            self.active_terminal_calls -= 1
        return self.terminal_result

    def account_info(self) -> object:
        self.calls.append("account_info")
        return self.account_result

    def symbols_get(self) -> object:
        self.calls.append("symbols_get")
        if self.symbol_catalog_result is not None:
            return self.symbol_catalog_result
        return (self.symbol_result,) if self.symbol_result else None

    def symbol_info(self, symbol: str) -> object:
        self.calls.append("symbol_info")
        assert self.symbol_result is not None
        result = cast(SimpleNamespace, self.symbol_result)
        assert symbol == result.name
        return self.symbol_result

    def symbol_info_tick(self, symbol: str) -> object:
        self.calls.append("symbol_info_tick")
        assert self.symbol_result is not None
        result = cast(SimpleNamespace, self.symbol_result)
        assert symbol == result.name
        return self.tick_result

    def copy_rates_from_pos(
        self, symbol: str, timeframe: int, start_position: int, count: int
    ) -> object:
        self.calls.append("copy_rates_from_pos")
        if self.rate_result is not None:
            return self.rate_result
        return tuple(
            {
                "time": int(NOW.timestamp()) - (count - index) * 60,
                "open": 2345.0,
                "high": 2346.0,
                "low": 2344.0,
                "close": 2345.5,
                "tick_volume": 100,
                "spread": 20,
                "real_volume": 0,
            }
            for index in range(count)
        )

    def copy_rates_range(
        self, symbol: str, timeframe: int, start: datetime, end: datetime
    ) -> object:
        self.calls.append("copy_rates_range")
        return self.copy_rates_from_pos(symbol, timeframe, 1, 2)

    def positions_get(self) -> object:
        self.calls.append("positions_get")
        return self.position_result

    def orders_get(self) -> object:
        self.calls.append("orders_get")
        return self.order_result

    def history_orders_get(self, start: datetime, end: datetime) -> object:
        self.calls.append("history_orders_get")
        return self.order_history_result

    def history_deals_get(self, start: datetime, end: datetime) -> object:
        self.calls.append("history_deals_get")
        return self.deal_history_result


def native_adapter(tmp_path: Path, module: NativeModuleFake) -> MetaTrader5ReadAdapter:
    terminal_path = tmp_path / "terminal64.exe"
    terminal_path.write_bytes(b"fixture")
    return MetaTrader5ReadAdapter(
        Mt5WorkerConfig(
            terminal_path=terminal_path,
            broker_symbol="XAUUSD",
            expected_account_fingerprint=None,
        ),
        clock=lambda: NOW,
        platform="win32",
        module=module,
    )


def rate_row(open_at: datetime) -> dict[str, object]:
    return {
        "time": int(open_at.timestamp()),
        "open": 2345.0,
        "high": 2346.0,
        "low": 2344.0,
        "close": 2345.5,
        "tick_volume": 100,
        "spread": 20,
        "real_volume": 0,
    }


def test_non_windows_import_and_missing_path_fail_closed(tmp_path: Path) -> None:
    adapter = MetaTrader5ReadAdapter(Mt5WorkerConfig(), platform="linux")
    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.connect(trace_id="test")
    assert raised.value.error.reason_code is Mt5ReasonCode.UNSUPPORTED_PLATFORM

    windows = MetaTrader5ReadAdapter(Mt5WorkerConfig(), platform="win32")
    with pytest.raises(Mt5ReadFailure) as missing:
        windows.connect(trace_id="test")
    assert missing.value.error.reason_code is Mt5ReasonCode.TERMINAL_PATH_NOT_CONFIGURED

    invalid = MetaTrader5ReadAdapter(
        Mt5WorkerConfig(terminal_path=tmp_path / "missing.exe"),
        platform="win32",
    )
    with pytest.raises(Mt5ReadFailure) as invalid_path:
        invalid.connect(trace_id="test")
    assert invalid_path.value.error.reason_code is Mt5ReasonCode.TERMINAL_NOT_FOUND


def test_native_package_is_imported_lazily(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terminal_path = tmp_path / "terminal64.exe"
    terminal_path.write_bytes(b"fixture")
    calls = 0

    def missing_package(name: str) -> object:
        nonlocal calls
        calls += 1
        assert name == "MetaTrader5"
        raise ImportError("synthetic")

    monkeypatch.setattr(importlib, "import_module", missing_package)
    adapter = MetaTrader5ReadAdapter(
        Mt5WorkerConfig(terminal_path=terminal_path), platform="win32"
    )
    assert calls == 0
    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.connect(trace_id="test")
    assert calls == 1
    assert raised.value.error.reason_code is Mt5ReasonCode.MT5_PACKAGE_NOT_INSTALLED


def test_connect_account_and_disconnect_are_safe(tmp_path: Path) -> None:
    module = NativeModuleFake()
    adapter = native_adapter(tmp_path, module)
    terminal = adapter.connect(trace_id="test")
    account = adapter.get_account_info(trace_id="test")
    adapter.disconnect()

    assert terminal.connected is True
    assert account.trade_mode is AccountTradeMode.DEMO
    assert account.masked_login.endswith("3456")
    dumped = str(account.model_dump())
    assert str(RAW_LOGIN) not in dumped
    assert RAW_SERVER not in dumped
    assert "must-not-cross-boundary" not in dumped
    assert module.initialize_paths == [str((tmp_path / "terminal64.exe").resolve())]
    assert module.calls.count("shutdown") == 1


def test_fake_satisfies_port_and_account_info_failure_is_safe(tmp_path: Path) -> None:
    from mt5_factories import fake_adapter

    assert isinstance(fake_adapter(), Mt5ReadPort)
    module = NativeModuleFake()
    module.account_result = None
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_account_info(trace_id="test")
    assert raised.value.error.reason_code is Mt5ReasonCode.ACCOUNT_INFO_UNAVAILABLE
    assert "must-not-cross-boundary" not in str(raised.value)

    module.account_result = SimpleNamespace(
        login=RAW_LOGIN,
        server=RAW_SERVER,
        name="must-not-cross-boundary",
    )
    with pytest.raises(Mt5ReadFailure) as missing_mode:
        adapter.get_account_info(trace_id="test")
    assert (
        missing_mode.value.error.reason_code is Mt5ReasonCode.ACCOUNT_INFO_UNAVAILABLE
    )
    assert "must-not-cross-boundary" not in str(missing_mode.value)
    adapter.disconnect()


def test_initialize_and_terminal_info_failures_are_sanitized(tmp_path: Path) -> None:
    module = NativeModuleFake()
    module.initialize_result = False
    adapter = native_adapter(tmp_path, module)
    with pytest.raises(Mt5ReadFailure) as initialize_failure:
        adapter.connect(trace_id="test")
    assert initialize_failure.value.error.reason_code is Mt5ReasonCode.INITIALIZE_FAILED
    assert "raw native diagnostic" not in str(initialize_failure.value)
    assert module.calls.count("shutdown") == 1

    module = NativeModuleFake()
    module.initialize_result = cast(bool, "true")
    adapter = native_adapter(tmp_path, module)
    with pytest.raises(Mt5ReadFailure) as invalid_initialize:
        adapter.connect(trace_id="test")
    assert invalid_initialize.value.error.reason_code is Mt5ReasonCode.INITIALIZE_FAILED
    assert module.calls.count("shutdown") == 1

    module = NativeModuleFake()
    module.terminal_result = None
    adapter = native_adapter(tmp_path, module)
    with pytest.raises(Mt5ReadFailure) as terminal_failure:
        adapter.connect(trace_id="test")
    assert (
        terminal_failure.value.error.reason_code
        is Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE
    )
    assert module.calls.count("shutdown") == 1


@pytest.mark.parametrize(
    ("terminal_result", "expected_reason"),
    [
        (
            SimpleNamespace(connected=False, trade_allowed=False),
            Mt5ReasonCode.TERMINAL_DISCONNECTED,
        ),
        (
            SimpleNamespace(trade_allowed=False),
            Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE,
        ),
        (
            SimpleNamespace(connected="true", trade_allowed=False),
            Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE,
        ),
        (
            SimpleNamespace(connected=1, trade_allowed=False),
            Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE,
        ),
        (
            SimpleNamespace(connected=True, trade_allowed="false"),
            Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE,
        ),
    ],
)
def test_terminal_connection_and_boolean_fields_fail_closed(
    tmp_path: Path,
    terminal_result: object,
    expected_reason: Mt5ReasonCode,
) -> None:
    module = NativeModuleFake()
    module.terminal_result = terminal_result
    adapter = native_adapter(tmp_path, module)

    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.connect(trace_id="test")

    assert raised.value.error.reason_code is expected_reason
    assert "account_info" not in module.calls
    assert module.calls.count("shutdown") == 1


def test_later_terminal_validation_failure_prevents_account_read(
    tmp_path: Path,
) -> None:
    module = NativeModuleFake()
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="connect")
    module.terminal_result = SimpleNamespace(trade_allowed=False)

    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_terminal_info(trace_id="poll")

    assert raised.value.error.reason_code is Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE
    assert "account_info" not in module.calls
    adapter.disconnect()


def test_all_native_calls_are_serialized(tmp_path: Path) -> None:
    module = NativeModuleFake()
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="connect")
    module.max_active_terminal_calls = 0
    threads = [
        threading.Thread(
            target=adapter.get_terminal_info, kwargs={"trace_id": f"thread-{index}"}
        )
        for index in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    adapter.disconnect()
    assert module.max_active_terminal_calls == 1


def test_symbol_tick_and_completed_candles_normalize_decimals(tmp_path: Path) -> None:
    module = NativeModuleFake()
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    candidates = adapter.list_symbol_candidates(trace_id="test")
    specification = adapter.get_symbol_specification("XAUUSD", trace_id="test")
    tick = adapter.get_latest_tick("XAUUSD", trace_id="test")
    candles = adapter.get_candles(
        "XAUUSD",
        Timeframe.M1,
        CandleRequest(start_position=1, count=3),
        trace_id="test",
    )
    adapter.disconnect()
    assert len(candidates) == 1
    assert str(specification.tick_size) == "0.01"
    assert str(tick.spread_price) == "0.2"
    assert len(candles.candles) == 3
    assert all(candle.is_complete for candle in candles.candles)
    assert candles.gaps == ()


@pytest.mark.parametrize(
    ("broker_symbol", "base_currency", "profit_currency"),
    [
        ("EURUSD", "EUR", "USD"),
        ("BTCUSD", "BTC", "USD"),
        ("XAUJPY", "XAU", "JPY"),
        ("XAUUSD", "EUR", "USD"),
        ("XAUUSD", "xau", "USD"),
        ("XAUUSD", "XAU", "usd"),
    ],
)
def test_configured_non_xauusd_specification_is_blocked(
    tmp_path: Path,
    broker_symbol: str,
    base_currency: str,
    profit_currency: str,
) -> None:
    module = NativeModuleFake()
    result = cast(SimpleNamespace, module.symbol_result)
    result.name = broker_symbol
    result.currency_base = base_currency
    result.currency_profit = profit_currency
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")

    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_symbol_specification(broker_symbol, trace_id="test")

    assert raised.value.error.reason_code is Mt5ReasonCode.SYMBOL_CANONICAL_MISMATCH
    adapter.disconnect()


def test_gold_alias_requires_actual_xauusd_specification(tmp_path: Path) -> None:
    module = NativeModuleFake()
    valid_gold = SimpleNamespace(**vars(cast(SimpleNamespace, module.symbol_result)))
    valid_gold.name = "GOLD"
    valid_gold.currency_margin = "EUR"
    invalid_gold = SimpleNamespace(**vars(valid_gold))
    invalid_gold.name = "GOLD.bad"
    invalid_gold.currency_base = "EUR"
    misleading_name = SimpleNamespace(**vars(valid_gold))
    misleading_name.name = "XAUUSD.bad"
    misleading_name.currency_profit = "JPY"
    lowercase_gold = SimpleNamespace(**vars(valid_gold))
    lowercase_gold.name = "GOLD.lowercase"
    lowercase_gold.currency_base = "xau"
    module.symbol_catalog_result = (
        valid_gold,
        invalid_gold,
        misleading_name,
        lowercase_gold,
    )
    module.symbol_result = valid_gold
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")

    candidates = adapter.list_symbol_candidates(trace_id="test")
    specification = adapter.get_symbol_specification("GOLD", trace_id="test")

    assert [candidate.broker_symbol for candidate in candidates] == ["GOLD"]
    assert specification.canonical_symbol == "XAUUSD"
    assert specification.base_currency == "XAU"
    assert specification.profit_currency == "USD"
    assert specification.margin_currency == "EUR"
    adapter.disconnect()


def test_margin_currency_is_validated_without_rewriting(tmp_path: Path) -> None:
    module = NativeModuleFake()
    result = cast(SimpleNamespace, module.symbol_result)
    result.currency_margin = "eur"
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")

    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_symbol_specification("XAUUSD", trace_id="test")

    assert raised.value.error.reason_code is Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE
    adapter.disconnect()


def test_qualifying_symbol_candidate_requires_strict_visible_boolean(
    tmp_path: Path,
) -> None:
    module = NativeModuleFake()
    result = cast(SimpleNamespace, module.symbol_result)
    result.visible = "true"
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")

    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.list_symbol_candidates(trace_id="test")

    assert raised.value.error.reason_code is Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE
    adapter.disconnect()


def test_current_candle_is_incomplete_and_non_monotonic_data_is_rejected(
    tmp_path: Path,
) -> None:
    module = NativeModuleFake()
    module.rate_result = (
        rate_row(NOW - timedelta(minutes=1)),
        rate_row(NOW),
    )
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    current = adapter.get_candles(
        "XAUUSD",
        Timeframe.M1,
        CandleRequest(start_position=0, count=2, include_current=True),
        trace_id="test",
    )
    assert current.candles[-1].is_complete is False

    valid_row = rate_row(NOW)
    module.rate_result = (
        valid_row,
        {**valid_row, "time": int(NOW.timestamp()) - 60},
    )
    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_candles(
            "XAUUSD", Timeframe.M1, CandleRequest(count=2), trace_id="test"
        )
    assert raised.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID
    module.rate_result = (valid_row, valid_row)
    with pytest.raises(Mt5ReadFailure):
        adapter.get_candles(
            "XAUUSD", Timeframe.M1, CandleRequest(count=2), trace_id="test"
        )
    adapter.disconnect()


@pytest.mark.parametrize(
    ("timeframe", "duration_seconds"),
    [
        (Timeframe.M1, 60),
        (Timeframe.M5, 300),
        (Timeframe.M15, 900),
        (Timeframe.H1, 3_600),
    ],
)
def test_candle_completeness_uses_timeframe_bucket_boundaries(
    tmp_path: Path,
    timeframe: Timeframe,
    duration_seconds: int,
) -> None:
    module = NativeModuleFake()
    closed_open = NOW - timedelta(seconds=duration_seconds)
    module.rate_result = (rate_row(closed_open), rate_row(NOW))
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")

    current = adapter.get_candles(
        "XAUUSD",
        timeframe,
        CandleRequest(start_position=0, count=2, include_current=True),
        trace_id="test",
    )
    assert [candle.is_complete for candle in current.candles] == [True, False]

    completed_only = adapter.get_candles(
        "XAUUSD",
        timeframe,
        CandleRequest(start_position=1, count=2),
        trace_id="test",
    )
    assert [candle.open_at for candle in completed_only.candles] == [closed_open]

    module.rate_result = (
        rate_row(closed_open - timedelta(seconds=duration_seconds)),
        rate_row(closed_open),
    )
    historical_position = adapter.get_candles(
        "XAUUSD",
        timeframe,
        CandleRequest(start_position=1, count=2, include_current=True),
        trace_id="test",
    )
    assert all(candle.is_complete for candle in historical_position.candles)

    historical_range = adapter.get_candles(
        "XAUUSD",
        timeframe,
        CandleRequest(
            count=2,
            include_current=True,
            range_start=closed_open - timedelta(seconds=duration_seconds),
            range_end=closed_open,
        ),
        trace_id="test",
    )
    assert all(candle.is_complete for candle in historical_range.candles)
    adapter.disconnect()


def test_candle_range_filters_only_the_active_bucket(tmp_path: Path) -> None:
    module = NativeModuleFake()
    module.rate_result = (
        rate_row(NOW - timedelta(minutes=1)),
        rate_row(NOW),
    )
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    retained = adapter.get_candles(
        "XAUUSD",
        Timeframe.M1,
        CandleRequest(
            count=2,
            include_current=True,
            range_start=NOW - timedelta(minutes=1),
            range_end=NOW,
        ),
        trace_id="test",
    )
    filtered = adapter.get_candles(
        "XAUUSD",
        Timeframe.M1,
        CandleRequest(
            count=2,
            range_start=NOW - timedelta(minutes=1),
            range_end=NOW,
        ),
        trace_id="test",
    )

    assert [candle.is_complete for candle in retained.candles] == [True, False]
    assert [candle.open_at for candle in filtered.candles] == [
        NOW - timedelta(minutes=1)
    ]
    adapter.disconnect()


def test_invalid_candle_timestamp_is_a_bounded_read_failure(tmp_path: Path) -> None:
    module = NativeModuleFake()
    module.rate_result = ({**rate_row(NOW), "time": "invalid"},)
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")

    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_candles(
            "XAUUSD",
            Timeframe.M1,
            CandleRequest(start_position=0, count=1, include_current=True),
            trace_id="test",
        )

    assert raised.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID
    adapter.disconnect()


def test_extreme_candle_timestamp_is_a_bounded_read_failure(tmp_path: Path) -> None:
    module = NativeModuleFake()
    module.rate_result = ({**rate_row(NOW), "time": 10**100},)
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")

    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_candles(
            "XAUUSD",
            Timeframe.M1,
            CandleRequest(start_position=0, count=1, include_current=True),
            trace_id="test",
        )

    assert raised.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID
    adapter.disconnect()


def test_candle_gap_detection_runs_after_active_bucket_filtering(
    tmp_path: Path,
) -> None:
    module = NativeModuleFake()
    module.rate_result = (
        rate_row(NOW - timedelta(minutes=3)),
        rate_row(NOW - timedelta(minutes=1)),
        rate_row(NOW),
    )
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")

    series = adapter.get_candles(
        "XAUUSD",
        Timeframe.M1,
        CandleRequest(start_position=1, count=3),
        trace_id="test",
    )

    assert len(series.candles) == 2
    assert len(series.gaps) == 1
    assert series.gaps[0].missing_intervals == 1
    adapter.disconnect()


def test_candle_response_cannot_exceed_configured_limit(tmp_path: Path) -> None:
    module = NativeModuleFake()
    module.rate_result = tuple(
        {
            "time": int(NOW.timestamp()) - (3 - index) * 60,
            "open": 2345.0,
            "high": 2346.0,
            "low": 2344.0,
            "close": 2345.5,
            "tick_volume": 100,
            "spread": 20,
            "real_volume": 0,
        }
        for index in range(3)
    )
    terminal_path = tmp_path / "terminal64.exe"
    terminal_path.write_bytes(b"fixture")
    adapter = MetaTrader5ReadAdapter(
        Mt5WorkerConfig(
            terminal_path=terminal_path,
            broker_symbol="XAUUSD",
            candle_limit=2,
        ),
        clock=lambda: NOW,
        platform="win32",
        module=module,
    )
    adapter.connect(trace_id="test")

    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_candles(
            "XAUUSD", Timeframe.M1, CandleRequest(count=2), trace_id="test"
        )

    assert raised.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID

    with pytest.raises(Mt5ReadFailure) as unsupported:
        adapter.get_candles(
            "XAUUSD",
            cast(Timeframe, "M30"),
            CandleRequest(count=1),
            trace_id="test",
        )
    assert unsupported.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID
    adapter.disconnect()


@pytest.mark.parametrize(
    "field",
    ["trade_contract_size", "trade_tick_size", "volume_step", "volume_min"],
)
def test_invalid_required_symbol_numbers_fail_closed(
    tmp_path: Path, field: str
) -> None:
    module = NativeModuleFake()
    setattr(module.symbol_result, field, 0)
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_symbol_specification("XAUUSD", trace_id="test")
    assert raised.value.error.reason_code is Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE
    adapter.disconnect()


def test_invisible_symbol_is_diagnostic_and_never_enabled(tmp_path: Path) -> None:
    module = NativeModuleFake()
    assert isinstance(module.symbol_result, SimpleNamespace)
    module.symbol_result.visible = False
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    specification = adapter.get_symbol_specification("XAUUSD", trace_id="test")
    assert specification.usability_state.value == "not_visible"
    assert specification.unusable_reason is Mt5ReasonCode.SYMBOL_NOT_VISIBLE
    assert "symbol_select" not in module.calls
    adapter.disconnect()


def test_position_order_and_history_rows_are_safely_normalized(tmp_path: Path) -> None:
    module = NativeModuleFake()
    common_order = SimpleNamespace(
        ticket=90071992547409930001,
        position_id=90071992547409930002,
        symbol="XAUUSD",
        type=0,
        state=1,
        volume_initial=0.01,
        volume_current=0.01,
        price_open=2345.1,
        sl=2335.1,
        tp=2365.1,
        time_setup=int(NOW.timestamp()),
        time_done=int(NOW.timestamp()),
        time_expiration=0,
        comment="password=" + "must-not-cross",
    )
    module.position_result = (
        SimpleNamespace(
            ticket=90071992547409930003,
            symbol="XAUUSD",
            type=0,
            volume=0.01,
            price_open=2345.1,
            price_current=2346.1,
            sl=2335.1,
            tp=2365.1,
            profit=1.25,
            swap=-0.1,
            magic=42,
            time=int(NOW.timestamp()),
            login="must-not-cross",
        ),
    )
    module.order_result = (common_order,)
    module.order_history_result = (common_order,)
    module.deal_history_result = (
        SimpleNamespace(
            ticket=90071992547409930004,
            order=90071992547409930001,
            position_id=90071992547409930003,
            symbol="XAUUSD",
            type=0,
            volume=0.01,
            price=2346.1,
            profit=1.25,
            commission=-0.2,
            swap=-0.1,
            time=int(NOW.timestamp()),
            comment="password=" + "must-not-cross",
        ),
    )
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    history = HistoryRequest(start_at=NOW - timedelta(hours=1), end_at=NOW)
    positions = adapter.get_open_positions(trace_id="test")
    orders = adapter.get_active_orders(trace_id="test")
    order_history = adapter.get_order_history(history, trace_id="test")
    deals = adapter.get_deal_history(history, trace_id="test")
    assert positions[0].ticket == "90071992547409930003"
    assert orders[0].ticket == "90071992547409930001"
    assert order_history[0].safe_comment == "[redacted]"
    assert deals[0].safe_comment == "[redacted]"
    assert "login" not in positions[0].model_dump()
    assert "must-not-cross" not in str(order_history + deals)
    adapter.disconnect()


def test_candle_range_is_bounded_and_cannot_extend_far_future(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CandleRequest(
            range_start=NOW - timedelta(days=8),
            range_end=NOW,
        )
    module = NativeModuleFake()
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_candles(
            "XAUUSD",
            Timeframe.M1,
            CandleRequest(
                range_start=NOW,
                range_end=NOW + timedelta(seconds=31),
            ),
            trace_id="test",
        )
    assert raised.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID
    adapter.disconnect()


def test_none_collection_is_failure_but_empty_collection_is_valid(
    tmp_path: Path,
) -> None:
    module = NativeModuleFake()
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    assert adapter.get_open_positions(trace_id="test") == []
    module.position_result = None
    with pytest.raises(Mt5ReadFailure) as raised:
        adapter.get_open_positions(trace_id="test")
    assert raised.value.error.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    adapter.disconnect()


def test_history_window_uses_bounded_calls(tmp_path: Path) -> None:
    module = NativeModuleFake()
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="test")
    request = HistoryRequest(
        start_at=NOW.replace(hour=11),
        end_at=NOW,
    )
    assert adapter.get_order_history(request, trace_id="test") == []
    assert adapter.get_deal_history(request, trace_id="test") == []
    assert "history_orders_get" in module.calls
    assert "history_deals_get" in module.calls
    adapter.disconnect()


def test_native_adapter_ast_is_static_and_allowlisted() -> None:
    path = (
        Path(__file__).parents[1]
        / "src"
        / "aurum_worker"
        / "adapters"
        / "native_mt5.py"
    )
    tree = ast.parse(path.read_text(encoding="utf8"))
    allowed = {
        "initialize",
        "shutdown",
        "version",
        "last_error",
        "terminal_info",
        "account_info",
        "symbols_get",
        "symbol_info",
        "symbol_info_tick",
        "copy_rates_from_pos",
        "copy_rates_range",
        "positions_get",
        "orders_get",
        "history_orders_get",
        "history_deals_get",
    }
    referenced = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "module"
    }
    assert referenced == allowed
    initialize_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "module"
        and node.func.attr == "initialize"
    ]
    assert len(initialize_calls) == 1
    assert len(initialize_calls[0].args) == 1
    assert initialize_calls[0].keywords == []
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and "MetaTrader5" in ast.unparse(node)
        for node in ast.walk(tree)
    )

    worker_root = path.parents[2]
    for python_path in worker_root.rglob("*.py"):
        if python_path == path:
            continue
        source_tree = ast.parse(python_path.read_text(encoding="utf8"))
        for node in ast.walk(source_tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            assert "MetaTrader5" not in names
    web_root = path.parents[4] / "web"
    assert not any(
        "aurum_worker" in web_path.read_text(encoding="utf8")
        or "apps/worker" in web_path.read_text(encoding="utf8")
        for web_path in web_root.rglob("*.ts*")
    )
    forbidden = {
        "order_send",
        "order_check",
        "order_calc_profit",
        "order_calc_margin",
        "login",
        "market_book_add",
        "market_book_get",
        "market_book_release",
        "symbol_select",
    }
    assert referenced.isdisjoint(forbidden)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and node.args
        and "mt5" in ast.unparse(node.args[0]).lower()
        for node in ast.walk(tree)
    )
