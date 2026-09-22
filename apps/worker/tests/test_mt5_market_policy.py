from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from mt5_factories import NOW
from test_mt5_native import NativeModuleFake, rate_row
from test_mt5_tick_time import diagnostic_setup

from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.models.mt5 import (
    CandleRequest,
    HistoryRequest,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY

OFFSET = timedelta(hours=3)


def native_tick(event_at: datetime) -> SimpleNamespace:
    encoded = event_at + OFFSET
    return SimpleNamespace(
        bid=2345.1,
        ask=2345.3,
        time=int(encoded.timestamp()),
        time_msc=int(encoded.timestamp() * 1000),
    )


def change_binding(module: NativeModuleFake, change: str) -> None:
    if change == "account":
        cast(SimpleNamespace, module.account_result).login += 1
    elif change == "specification":
        cast(SimpleNamespace, module.symbol_result).trade_contract_size += 1
    elif change == "provider":
        cast(SimpleNamespace, module.account_result).company = "Other Provider"
    else:
        raise AssertionError("Unknown synthetic binding change")


class RangeCapturingFake(NativeModuleFake):
    def __init__(self, *, change_after: str | None = None) -> None:
        super().__init__()
        self.range_arguments: list[tuple[datetime, datetime]] = []
        self.change_after = change_after

    def symbol_info_tick(self, symbol: str) -> object:
        result = super().symbol_info_tick(symbol)
        if self.change_after is not None:
            change_binding(self, self.change_after)
        return result

    def copy_rates_from_pos(
        self, symbol: str, timeframe: int, start_position: int, count: int
    ) -> object:
        result = super().copy_rates_from_pos(symbol, timeframe, start_position, count)
        if self.change_after is not None:
            change_binding(self, self.change_after)
        return result

    def copy_rates_range(
        self, symbol: str, timeframe: int, start: datetime, end: datetime
    ) -> object:
        self.range_arguments.append((start, end))
        self.calls.append("copy_rates_range")
        return self.rate_result


@contextmanager
def market_adapter(
    tmp_path: Path,
    module: NativeModuleFake,
    *,
    now: datetime = NOW,
    policy: str = PEPPERSTONE_POLICY,
) -> Iterator[MetaTrader5ReadAdapter]:
    # Confirm synthetic account/spec fixtures separately, never observe real MT5.
    _, config = diagnostic_setup(tmp_path, module)
    cast(SimpleNamespace, module.account_result).company = "Pepperstone Test"
    selected = config.model_copy(update={"market_time_policy": policy})
    adapter = MetaTrader5ReadAdapter(
        selected, module=module, platform="win32", clock=lambda: now
    )
    adapter.connect(trace_id="test-market-policy")
    module.calls.clear()
    try:
        yield adapter
    finally:
        adapter.disconnect()


@pytest.mark.parametrize(
    ("age_ms", "freshness"),
    [
        (-30_001, TickFreshness.FUTURE_INVALID),
        (-30_000, TickFreshness.LIVE),
        (0, TickFreshness.LIVE),
        (1, TickFreshness.LIVE),
        (5_000, TickFreshness.LIVE),
        (5_001, TickFreshness.DELAYED),
        (10_000, TickFreshness.DELAYED),
        (10_001, TickFreshness.STALE),
        (3_601_000, TickFreshness.STALE),
    ],
)
def test_market_policy_preserves_exact_freshness_boundaries(
    tmp_path: Path, age_ms: int, freshness: TickFreshness
) -> None:
    module = NativeModuleFake()
    event_at = NOW - timedelta(milliseconds=age_ms)
    module.tick_result = native_tick(event_at)
    with market_adapter(tmp_path, module) as adapter:
        observation = adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert observation.tick_at == event_at
        assert observation.observed_at == NOW
        assert observation.freshness is freshness
        expected_age = abs(age_ms) if age_ms < -30_000 else max(age_ms, 0)
        assert observation.age_seconds == Decimal(expected_age) / 1000
        assert PEPPERSTONE_POLICY in observation.adapter_version
        assert module.calls.count("symbol_info_tick") == 1
        assert module.calls.count("account_info") == 2


@pytest.mark.parametrize("milliseconds", [None, 0])
def test_market_policy_has_explicit_seconds_fallback(
    tmp_path: Path, milliseconds: int | None
) -> None:
    module = NativeModuleFake()
    tick = native_tick(NOW - timedelta(seconds=1))
    tick.time_msc = milliseconds
    module.tick_result = tick
    with market_adapter(tmp_path, module) as adapter:
        observation = adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert observation.tick_at == NOW - timedelta(seconds=1)
        assert observation.freshness is TickFreshness.LIVE


def test_slow_post_read_binding_check_cannot_return_stale_tick_as_live(
    tmp_path: Path,
) -> None:
    current_time = [NOW]

    class SlowPostBindingFake(NativeModuleFake):
        def symbol_info(self, symbol: str) -> object:
            result = super().symbol_info(symbol)
            # Pre-check, direct tick specification read, then post-check.
            # Only the final binding read advances the synthetic clock.
            if self.calls.count("symbol_info") == 3:
                current_time[0] += timedelta(milliseconds=10_001)
            return result

    module = SlowPostBindingFake()
    module.tick_result = native_tick(NOW)
    with market_adapter(tmp_path, module) as adapter:
        adapter._clock = lambda: current_time[0]
        observation = adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert module.calls.count("symbol_info") == 3
        assert observation.tick_at == NOW
        assert observation.observed_at == NOW + timedelta(milliseconds=10_001)
        assert observation.age_seconds == Decimal("10.001")
        assert observation.freshness is TickFreshness.STALE


@pytest.mark.parametrize("company", [None, "", "Other Provider", "Pepperstoneish"])
def test_wrong_public_provider_blocks_before_market_read(
    tmp_path: Path, company: object
) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        cast(SimpleNamespace, module.account_result).company = company
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert raised.value.error.reason_code is Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH
        assert "symbol_info_tick" not in module.calls


@pytest.mark.parametrize(
    ("company", "detail"),
    [
        (None, "PUBLIC_PROVIDER_MISSING"),
        (False, "PUBLIC_PROVIDER_INVALID"),
        ("   ", "PUBLIC_PROVIDER_EMPTY"),
        ("MetaQuotes Ltd.", "PUBLIC_PROVIDER_METAQUOTES"),
        ("synthetic-private-company-label", "PUBLIC_PROVIDER_UNSUPPORTED"),
    ],
)
def test_provider_failure_is_bounded_evidence_without_market_reads(
    tmp_path: Path, company: object, detail: str
) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        cast(SimpleNamespace, module.account_result).company = company
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert raised.value.error.reason_code is Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH
        assert raised.value.error.safe_detail == detail
        assert "synthetic-private-company-label" not in str(raised.value)
        assert "symbol_info_tick" not in module.calls
        assert "copy_rates_from_pos" not in module.calls


@pytest.mark.parametrize("mode", [1, 2, 99])
def test_non_demo_never_reaches_policy_market_read(tmp_path: Path, mode: int) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        cast(SimpleNamespace, module.account_result).trade_mode = mode
        with pytest.raises(Mt5ReadFailure):
            adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert "symbol_info_tick" not in module.calls
        assert "symbol_info" not in module.calls


@pytest.mark.parametrize("change", ["account", "specification", "provider"])
def test_changed_binding_blocks_before_read(tmp_path: Path, change: str) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        change_binding(module, change)
        with pytest.raises(Mt5ReadFailure):
            adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert "symbol_info_tick" not in module.calls


@pytest.mark.parametrize("change", ["account", "specification", "provider"])
@pytest.mark.parametrize("kind", ["tick", "candle"])
def test_changed_binding_during_read_discards_result(
    tmp_path: Path, change: str, kind: str
) -> None:
    module = RangeCapturingFake(change_after=change)
    module.tick_result = native_tick(NOW)
    module.rate_result = (rate_row(NOW + OFFSET - timedelta(minutes=1)),)
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            if kind == "tick":
                adapter.get_latest_tick("XAUUSD", trace_id="test")
            else:
                adapter.get_candles(
                    "XAUUSD", Timeframe.M1, CandleRequest(count=1), trace_id="test"
                )
        call = "symbol_info_tick" if kind == "tick" else "copy_rates_from_pos"
        assert module.calls.count(call) == 1


@pytest.mark.parametrize(
    "now",
    [datetime(2026, 3, 8, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)],
)
@pytest.mark.parametrize("kind", ["tick", "candle"])
def test_capture_outside_policy_coverage_blocks_before_market_read(
    tmp_path: Path, now: datetime, kind: str
) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module, now=now) as adapter:
        with pytest.raises(Mt5ReadFailure):
            if kind == "tick":
                adapter.get_latest_tick("XAUUSD", trace_id="test")
            else:
                adapter.get_candles(
                    "XAUUSD", Timeframe.M1, CandleRequest(count=1), trace_id="test"
                )
        assert "symbol_info_tick" not in module.calls
        assert "copy_rates_from_pos" not in module.calls
        assert "copy_rates_range" not in module.calls


def test_unknown_policy_is_rejected_even_if_config_validation_was_bypassed(
    tmp_path: Path,
) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module, policy="unknown") as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert "symbol_info_tick" not in module.calls


@pytest.mark.parametrize("field", ["time", "time_msc"])
@pytest.mark.parametrize("invalid", [True, "123", 1.5, -1])
def test_policy_rejects_invalid_native_timestamp_scalar(
    tmp_path: Path, field: str, invalid: object
) -> None:
    module = NativeModuleFake()
    tick = native_tick(NOW)
    setattr(tick, field, invalid)
    module.tick_result = tick
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert raised.value.error.reason_code is Mt5ReasonCode.TICK_INVALID


def test_seconds_and_milliseconds_disagreement_is_not_a_fresh_tick(
    tmp_path: Path,
) -> None:
    module = NativeModuleFake()
    tick = native_tick(NOW)
    tick.time -= 1
    module.tick_result = tick
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert raised.value.error.reason_code is Mt5ReasonCode.TICK_INVALID


def test_candle_policy_normalizes_completed_and_current_buckets(tmp_path: Path) -> None:
    module = NativeModuleFake()
    opens = [NOW - timedelta(minutes=2), NOW - timedelta(minutes=1), NOW]
    module.rate_result = tuple(rate_row(value + OFFSET) for value in opens)
    with market_adapter(tmp_path, module) as adapter:
        all_bars = adapter.get_candles(
            "XAUUSD",
            Timeframe.M1,
            CandleRequest(start_position=0, count=3, include_current=True),
            trace_id="test",
        )
        assert [bar.open_at for bar in all_bars.candles] == opens
        assert [bar.is_complete for bar in all_bars.candles] == [True, True, False]
        completed = adapter.get_candles(
            "XAUUSD", Timeframe.M1, CandleRequest(count=3), trace_id="test"
        )
        assert [bar.open_at for bar in completed.candles] == opens[:-1]
        assert not completed.gaps


def test_candle_range_encodes_transport_labels_but_retains_utc_results(
    tmp_path: Path,
) -> None:
    module = RangeCapturingFake()
    start, end = NOW - timedelta(minutes=3), NOW - timedelta(minutes=1)
    module.rate_result = tuple(rate_row(value + OFFSET) for value in (start, end))
    request = CandleRequest(count=2, range_start=start, range_end=end)
    with market_adapter(tmp_path, module) as adapter:
        result = adapter.get_candles("XAUUSD", Timeframe.M1, request, trace_id="test")
        assert module.range_arguments == [(start + OFFSET, end + OFFSET)]
        assert request.range_start == start
        assert request.range_end == end
        assert [bar.open_at for bar in result.candles] == [start, end]
        assert result.gaps[0].missing_intervals == 1


def test_native_shaped_numpy_candle_rows_use_the_market_policy(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    module = NativeModuleFake()
    event_at = NOW - timedelta(minutes=1)
    module.rate_result = numpy.array(
        [
            (
                int((event_at + OFFSET).timestamp()),
                2345.0,
                2346.0,
                2344.0,
                2345.5,
                100,
                20,
                0,
            )
        ],
        dtype=[
            ("time", "int64"),
            ("open", "float64"),
            ("high", "float64"),
            ("low", "float64"),
            ("close", "float64"),
            ("tick_volume", "int64"),
            ("spread", "int32"),
            ("real_volume", "int64"),
        ],
    )
    with market_adapter(tmp_path, module) as adapter:
        result = adapter.get_candles(
            "XAUUSD", Timeframe.M1, CandleRequest(count=1), trace_id="test"
        )
        assert len(result.candles) == 1
        assert result.candles[0].open_at == event_at
        assert result.candles[0].is_complete
        assert result.candles[0].tick_volume == Decimal("100")


def test_candle_interval_cannot_cross_the_policy_coverage_end(tmp_path: Path) -> None:
    module = NativeModuleFake()
    now = datetime(2026, 10, 31, 23, 59, 30, tzinfo=UTC)
    module.rate_result = (rate_row(now.replace(second=0) + OFFSET),)
    with market_adapter(tmp_path, module, now=now) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_candles(
                "XAUUSD",
                Timeframe.M1,
                CandleRequest(start_position=0, count=1, include_current=True),
                trace_id="test",
            )
        assert raised.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID


def test_candle_range_crossing_policy_start_never_reaches_native_query(
    tmp_path: Path,
) -> None:
    module = RangeCapturingFake()
    now = datetime(2026, 3, 9, 0, 1, tzinfo=UTC)
    with market_adapter(tmp_path, module, now=now) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_candles(
                "XAUUSD",
                Timeframe.M1,
                CandleRequest(
                    count=2, range_start=now - timedelta(minutes=2), range_end=now
                ),
                trace_id="test",
            )
        assert raised.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID
        assert not module.range_arguments
        assert "copy_rates_range" not in module.calls


@pytest.mark.parametrize("delta", [-1, 1])
def test_outside_range_bar_rejects_entire_result(tmp_path: Path, delta: int) -> None:
    module = RangeCapturingFake()
    start, end = NOW - timedelta(minutes=3), NOW - timedelta(minutes=1)
    outside = (start if delta < 0 else end) + timedelta(minutes=delta)
    module.rate_result = (rate_row(outside + OFFSET),)
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_candles(
                "XAUUSD",
                Timeframe.M1,
                CandleRequest(count=1, range_start=start, range_end=end),
                trace_id="test",
            )
        assert raised.value.error.reason_code is Mt5ReasonCode.CANDLE_DATA_INVALID


@pytest.mark.parametrize("kind", ["positions", "orders", "order_history", "deals"])
def test_market_only_policy_blocks_transaction_calls_even_when_empty(
    tmp_path: Path, kind: str
) -> None:
    module = NativeModuleFake()
    request = HistoryRequest(start_at=NOW - timedelta(hours=1), end_at=NOW)
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            if kind == "positions":
                adapter.get_open_positions(trace_id="test")
            elif kind == "orders":
                adapter.get_active_orders(trace_id="test")
            elif kind == "order_history":
                adapter.get_order_history(request, trace_id="test")
            else:
                adapter.get_deal_history(request, trace_id="test")
        assert raised.value.error.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        assert not set(module.calls) & {
            "positions_get",
            "orders_get",
            "history_orders_get",
            "history_deals_get",
        }


def test_policy_config_keeps_legacy_default_and_rejects_missing_binding() -> None:
    assert Mt5WorkerConfig().market_time_policy == "utc_epoch_v1"
    with pytest.raises(ValueError):
        Mt5WorkerConfig(market_time_policy=PEPPERSTONE_POLICY)


@pytest.mark.parametrize("field", ["max_tick_age_seconds", "max_clock_drift_seconds"])
@pytest.mark.parametrize("value", [1, 300])
@pytest.mark.parametrize("kind", ["tick", "candle"])
def test_corrupted_policy_config_cannot_bypass_fixed_limits_before_market_read(
    tmp_path: Path, field: str, value: int, kind: str
) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        adapter._config = adapter._config.model_copy(update={field: value})
        with pytest.raises(Mt5ReadFailure) as raised:
            if kind == "tick":
                adapter.get_latest_tick("XAUUSD", trace_id="test")
            else:
                adapter.get_candles(
                    "XAUUSD", Timeframe.M1, CandleRequest(count=1), trace_id="test"
                )
        expected = (
            Mt5ReasonCode.TICK_INVALID
            if kind == "tick"
            else Mt5ReasonCode.CANDLE_DATA_INVALID
        )
        assert raised.value.error.reason_code is expected
        assert not set(module.calls) & {
            "symbol_info_tick",
            "copy_rates_from_pos",
            "copy_rates_range",
        }


@pytest.mark.parametrize("seconds", [253_402_300_800, 10**40, 10**400])
@pytest.mark.parametrize("milliseconds", [False, True])
def test_out_of_range_tick_epoch_is_bounded_failure_not_conversion_overflow(
    tmp_path: Path, seconds: int, milliseconds: bool
) -> None:
    module = NativeModuleFake()
    raw = native_tick(NOW)
    raw.time = seconds
    raw.time_msc = seconds * 1000 + 123 if milliseconds else None
    module.tick_result = raw
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_latest_tick("XAUUSD", trace_id="test")
        assert raised.value.error.reason_code is Mt5ReasonCode.TICK_INVALID
        assert (
            raised.value.error.safe_detail
            == "Latest tick could not be normalized safely."
        )
        assert str(seconds) not in str(raised.value)
        assert module.calls.count("symbol_info_tick") == 1
