from __future__ import annotations

from datetime import timedelta, timezone
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext

import pytest
from mt5_factories import NOW, account, confirmed_binding, fake_adapter

from aurum_worker.adapters.fake_mt5 import FakeMt5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountTradeMode,
    BrokerSymbolObservation,
    CandleSeries,
    DatabaseReconciliationState,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_market_time import (
    PEPPERSTONE_POLICY,
    UTC_POLICY,
    MarketTimePolicy,
)
from aurum_worker.reconciliation import ReadOnlyReconciliationService
from aurum_worker.shadow.market import (
    MarketBlockCode,
    MarketBlocked,
    MarketFeatures,
    ShadowMarketService,
)


def read_port() -> FakeMt5ReadAdapter:
    # Test-double transport carrying native-shaped observations; no SDK access.
    adapter = fake_adapter()
    adapter.terminal = adapter.terminal.model_copy(update={"source": "mt5"})
    adapter.accounts = tuple(
        item.model_copy(update={"source": "mt5"}) for item in adapter.accounts
    )
    adapter.specifications = {
        key: item.model_copy(update={"source": "mt5"})
        for key, item in adapter.specifications.items()
    }
    adapter.ticks = {
        key: item.model_copy(update={"source": "mt5"})
        for key, item in adapter.ticks.items()
    }
    bar = adapter.candles[("XAUUSD", Timeframe.M1)].candles[0]
    adapter.candles[("XAUUSD", Timeframe.M1)] = CandleSeries(
        candles=tuple(
            bar.model_copy(
                update={"source": "mt5", "open_at": NOW - timedelta(minutes=6 - i)}
            )
            for i in range(6)
        )
    )
    return adapter


def service(
    adapter: FakeMt5ReadAdapter,
    persistence: InMemoryMt5ObservationPersistence | None = None,
    max_tick_age_seconds: int = 10,
    market_time_policy: MarketTimePolicy = UTC_POLICY,
) -> ShadowMarketService:
    config = Mt5WorkerConfig(
        broker_symbol="XAUUSD",
        expected_account_fingerprint=account().account_fingerprint,
        max_tick_age_seconds=max_tick_age_seconds,
        market_time_policy=market_time_policy,
        smoke_confirmed_specification_fingerprint=(
            confirmed_binding().confirmed_specification_fingerprint
        ),
    )
    persistence = persistence or InMemoryMt5ObservationPersistence(
        database_state=DatabaseReconciliationState(
            account_fingerprint=account().account_fingerprint,
            server_fingerprint=account().server_fingerprint,
            confirmed_symbol_binding=confirmed_binding(),
        )
    )
    reconciler = ReadOnlyReconciliationService(
        adapter,
        persistence,
        config,
        clock=lambda: NOW,
        identifier_factory=lambda: "00000000-0000-4000-8000-000000000001",
    )
    return ShadowMarketService(
        adapter, persistence, reconciler, config, clock=lambda: NOW
    )


def test_native_shaped_data_produces_reproducible_versioned_features() -> None:
    first = service(read_port()).capture(trace_id="first")
    second = service(read_port()).capture(trace_id="second")
    assert isinstance(first, MarketFeatures)
    assert first == second
    assert first.fast_sma == first.slow_sma == Decimal("2345.50")
    assert first.atr == Decimal("2")
    assert first.environment == "DEMO_ONLY" and first.runtime_mode == "SHADOW"
    assert first.grants_eligibility is False
    assert len(first.input_digest) == 64


def test_production_service_never_accepts_fixture_source() -> None:
    result = service(fake_adapter()).capture(trace_id="fake")
    assert isinstance(result, MarketBlocked)
    assert result.reason is MarketBlockCode.SOURCE_MISMATCH


@pytest.mark.parametrize("mismatch", [None, "tick", "bar", "config", "spec"])
def test_explicit_market_normalization_version_is_not_the_base_adapter_version(
    mismatch: str | None,
) -> None:
    adapter = read_port()
    market_version = f"{adapter.accounts[0].adapter_version}:{PEPPERSTONE_POLICY}"
    adapter.ticks["XAUUSD"] = adapter.ticks["XAUUSD"].model_copy(
        update={"adapter_version": market_version if mismatch != "tick" else "other"}
    )
    series = adapter.candles[("XAUUSD", Timeframe.M1)]
    adapter.candles[("XAUUSD", Timeframe.M1)] = CandleSeries(
        candles=tuple(
            bar.model_copy(
                update={
                    "adapter_version": market_version if mismatch != "bar" else "other"
                }
            )
            for bar in series.candles
        )
    )
    if mismatch == "spec":
        adapter.specifications["XAUUSD"] = adapter.specifications["XAUUSD"].model_copy(
            update={"adapter_version": market_version}
        )
    result = service(
        adapter,
        market_time_policy=UTC_POLICY if mismatch == "config" else PEPPERSTONE_POLICY,
    ).capture(trace_id="versioned-market")
    if mismatch is None:
        assert isinstance(result, MarketFeatures)
        assert result.market_adapter_version == market_version
        assert result.adapter_version == adapter.accounts[0].adapter_version
        assert result.market_time_policy == PEPPERSTONE_POLICY
    else:
        assert isinstance(result, MarketBlocked)
        assert result.reason is MarketBlockCode.SOURCE_MISMATCH


def test_blocked_reconciliation_never_reads_candles() -> None:
    adapter = read_port()
    adapter.failures["get_deal_history"] = Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    result = service(adapter).capture(trace_id="blocked")
    assert isinstance(result, MarketBlocked)
    assert "get_candles" not in adapter.call_log


@pytest.mark.parametrize(
    "mutation",
    [
        "gap",
        "duplicate",
        "incomplete",
        "future",
        "stale",
        "source",
        "symbol",
        "version",
        "timeframe",
        "off_minute",
        "ohlc",
    ],
)
def test_candles_fail_closed(mutation: str) -> None:
    adapter = read_port()
    bars = list(adapter.candles[("XAUUSD", Timeframe.M1)].candles)
    updates: dict[str, object] = {}
    if mutation == "gap":
        updates["open_at"] = bars[0].open_at - timedelta(minutes=1)
    elif mutation == "duplicate":
        updates["open_at"] = bars[1].open_at
    elif mutation == "incomplete":
        updates["is_complete"] = False
    elif mutation == "future":
        updates["open_at"] = NOW
    elif mutation == "stale":
        bars = [
            item.model_copy(update={"open_at": item.open_at - timedelta(minutes=1)})
            for item in bars
        ]
    elif mutation == "source":
        updates["source"] = "fake_mt5"
    elif mutation == "symbol":
        updates["symbol"] = "OTHER"
    elif mutation == "version":
        updates["adapter_version"] = "different-v1"
    elif mutation == "timeframe":
        updates["timeframe"] = Timeframe.M5
    elif mutation == "off_minute":
        updates["open_at"] = bars[0].open_at + timedelta(seconds=1)
    elif mutation == "ohlc":
        updates["high"] = Decimal("1")
    bars[0] = bars[0].model_copy(update=updates)
    # Deliberately bypass the series model to verify the service revalidates it.
    adapter.candles[("XAUUSD", Timeframe.M1)] = CandleSeries.model_construct(
        candles=tuple(bars), gaps=()
    )
    result = service(adapter).capture(trace_id="bad-candles")
    assert isinstance(result, MarketBlocked)


@pytest.mark.parametrize("age", [Decimal("5.001"), Decimal("-0.001")])
def test_freshness_is_recomputed_not_trusted_from_label(age: Decimal) -> None:
    adapter = read_port()
    adapter.ticks["XAUUSD"] = adapter.ticks["XAUUSD"].model_copy(
        update={
            "tick_at": NOW - timedelta(seconds=float(age)),
            "freshness": TickFreshness.LIVE,
        }
    )
    result = service(adapter).capture(trace_id="bad-tick")
    assert isinstance(result, MarketBlocked)
    assert result.reason is MarketBlockCode.TICK_NOT_CURRENT


def test_changed_data_changes_content_references() -> None:
    original = service(read_port()).capture(trace_id="a")
    adapter = read_port()
    series = adapter.candles[("XAUUSD", Timeframe.M1)]
    bars = list(series.candles)
    bars[-1] = bars[-1].model_copy(update={"close": Decimal("2345.75")})
    adapter.candles[("XAUUSD", Timeframe.M1)] = CandleSeries(candles=tuple(bars))
    changed = service(adapter).capture(trace_id="b")
    assert isinstance(original, MarketFeatures) and isinstance(changed, MarketFeatures)
    assert original.feature_snapshot_id != changed.feature_snapshot_id
    assert original.market_snapshot_id != changed.market_snapshot_id


def test_unexpected_adapter_failure_does_not_leak_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = read_port()

    def fail(*args: object, **kwargs: object) -> CandleSeries:
        raise RuntimeError("private-detail-must-not-appear")

    monkeypatch.setattr(FakeMt5ReadAdapter, "get_candles", fail)
    result = service(adapter).capture(trace_id="error")
    assert isinstance(result, MarketBlocked)
    assert "private-detail" not in result.model_dump_json()


def test_decimal_context_cannot_change_features_or_identifiers() -> None:
    adapter = read_port()
    series = adapter.candles[("XAUUSD", Timeframe.M1)]
    bars = list(series.candles)
    bars[-1] = bars[-1].model_copy(update={"close": Decimal("2345.51")})
    adapter.candles[("XAUUSD", Timeframe.M1)] = CandleSeries(candles=tuple(bars))
    with localcontext() as context:
        context.rounding = ROUND_DOWN
        first = service(adapter).capture(trace_id="down")
    with localcontext() as context:
        context.rounding = ROUND_UP
        second = service(adapter).capture(trace_id="up")
    assert isinstance(first, MarketFeatures) and first == second


def test_content_hash_does_not_round_away_source_decimal_digits() -> None:
    results = []
    for tail in ("1", "2"):
        adapter = read_port()
        series = adapter.candles[("XAUUSD", Timeframe.M1)]
        bars = list(series.candles)
        bars[-1] = bars[-1].model_copy(
            update={"close": Decimal("2345.5" + "0" * 40 + tail)}
        )
        adapter.candles[("XAUUSD", Timeframe.M1)] = CandleSeries(candles=tuple(bars))
        result = service(adapter).capture(trace_id="precise")
        assert isinstance(result, MarketFeatures)
        results.append(result)
    assert results[0].input_digest != results[1].input_digest
    assert results[0].market_snapshot_id != results[1].market_snapshot_id


def test_utc_bucket_alignment_is_not_local_wall_clock_alignment() -> None:
    adapter = read_port()
    series = adapter.candles[("XAUUSD", Timeframe.M1)]
    odd_zone = timezone(timedelta(seconds=30))
    adapter.candles[("XAUUSD", Timeframe.M1)] = CandleSeries(
        candles=tuple(
            bar.model_copy(update={"open_at": bar.open_at.replace(tzinfo=odd_zone)})
            for bar in series.candles
        )
    )
    assert isinstance(service(adapter).capture(trace_id="off-utc-grid"), MarketBlocked)


@pytest.mark.parametrize(
    "change", ["command", "account", "server", "position", "order"]
)
def test_database_change_after_full_reconciliation_blocks(change: str) -> None:
    class ChangedStore(InMemoryMt5ObservationPersistence):
        reads: int = 0

        def load_reconciliation_state(self) -> DatabaseReconciliationState:
            self.reads += 1
            state = super().load_reconciliation_state()
            if self.reads == 1:
                return state
            variants: dict[str, dict[str, object]] = {
                "command": {"executing_command_ids": frozenset({"uncertain"})},
                "account": {"account_fingerprint": "changed"},
                "server": {"server_fingerprint": "changed"},
                "position": {"position_tickets": frozenset({"123"})},
                "order": {"active_order_tickets": frozenset({"123"})},
            }
            return state.model_copy(update=variants[change])

    store = ChangedStore(
        database_state=DatabaseReconciliationState(
            account_fingerprint=account().account_fingerprint,
            server_fingerprint=account().server_fingerprint,
            confirmed_symbol_binding=confirmed_binding(),
        )
    )
    adapter = read_port()
    result = service(adapter, store).capture(trace_id="database-changed")
    assert isinstance(result, MarketBlocked)
    assert result.reason is MarketBlockCode.RECONCILIATION_REQUIRED
    assert "get_candles" not in adapter.call_log


def test_live_switch_blocks_before_any_further_symbol_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = read_port()
    original = FakeMt5ReadAdapter.get_account_info
    calls = 0

    def switch(self: FakeMt5ReadAdapter, *, trace_id: str) -> AccountObservation:
        nonlocal calls
        calls += 1
        observation = original(self, trace_id=trace_id)
        return (
            observation
            if calls == 1
            else observation.model_copy(update={"trade_mode": AccountTradeMode.REAL})
        )

    monkeypatch.setattr(FakeMt5ReadAdapter, "get_account_info", switch)
    result = service(adapter).capture(trace_id="switched")
    assert isinstance(result, MarketBlocked)
    assert adapter.call_log.count("get_symbol_specification") == 1
    assert "get_candles" not in adapter.call_log


def test_refreshing_observation_metadata_does_not_look_like_spec_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = read_port()
    original = FakeMt5ReadAdapter.get_symbol_specification
    count = 0

    def refresh(
        self: FakeMt5ReadAdapter, symbol: str, *, trace_id: str
    ) -> BrokerSymbolObservation:
        nonlocal count
        count += 1
        return original(self, symbol, trace_id=trace_id).model_copy(
            update={"observed_at": NOW - timedelta(milliseconds=5 - count)}
        )

    monkeypatch.setattr(FakeMt5ReadAdapter, "get_symbol_specification", refresh)
    assert isinstance(service(adapter).capture(trace_id="refreshed"), MarketFeatures)


def test_stricter_config_does_not_inherit_five_second_live_allowance() -> None:
    result = service(read_port(), max_tick_age_seconds=1).capture(trace_id="strict")
    assert isinstance(result, MarketBlocked)
    assert result.reason is MarketBlockCode.TICK_NOT_CURRENT
