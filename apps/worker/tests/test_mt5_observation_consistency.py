"""Fake-only regressions for current observation and native scalar boundaries."""

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from enum import IntEnum
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from mt5_factories import NOW, account, confirmed_binding, fake_adapter, specification
from test_mt5_native import NativeModuleFake, native_adapter
from test_mt5_reconciliation import config, confirmed_state

from aurum_worker.adapters.fake_mt5 import FakeMt5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    HealthState,
    HistoricalDealObservation,
    HistoryRequest,
    LatestTickObservation,
    Mt5ReadFailure,
    Mt5ReasonCode,
    ReconciliationOutcome,
    ReconciliationReport,
    TickFreshness,
)
from aurum_worker.reconciliation import ReadOnlyReconciliationService


@pytest.mark.parametrize("value", [False, True, 0.0, 0.9, "0", None])
def test_native_account_mode_never_coerces_malformed_values_to_demo(
    tmp_path: Path, value: object
) -> None:
    module = NativeModuleFake()
    cast(SimpleNamespace, module.account_result).trade_mode = value
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="consistency")
    try:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_account_info(trace_id="consistency")
        assert raised.value.error.reason_code is Mt5ReasonCode.ACCOUNT_INFO_UNAVAILABLE
    finally:
        adapter.disconnect()


@pytest.mark.parametrize(
    ("seconds", "milliseconds"),
    [
        (int(NOW.timestamp()) - 3_600, int(NOW.timestamp()) * 1_000),
        ("invalid", int(NOW.timestamp()) * 1_000),
        (int(NOW.timestamp()), str(int(NOW.timestamp()) * 1_000)),
        (int(NOW.timestamp()), float(int(NOW.timestamp()) * 1_000)),
        (int(NOW.timestamp()), False),
        (int(NOW.timestamp()), -1),
        (False, None),
        (float(NOW.timestamp()), 0),
    ],
)
def test_utc_tick_rejects_malformed_or_conflicting_native_time_pair(
    tmp_path: Path, seconds: object, milliseconds: object
) -> None:
    module = NativeModuleFake()
    raw = cast(SimpleNamespace, module.tick_result)
    raw.time = seconds
    raw.time_msc = milliseconds
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="consistency")
    try:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.get_latest_tick("XAUUSD", trace_id="consistency")
        assert raised.value.error.reason_code is Mt5ReasonCode.TICK_INVALID
    finally:
        adapter.disconnect()


@pytest.mark.parametrize("milliseconds", [None, 0, int(NOW.timestamp()) * 1_000 + 123])
def test_utc_tick_retains_supported_zero_missing_and_exact_millisecond_values(
    tmp_path: Path, milliseconds: int | None
) -> None:
    module = NativeModuleFake()
    cast(SimpleNamespace, module.tick_result).time_msc = milliseconds
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="consistency")
    try:
        result = adapter.get_latest_tick("XAUUSD", trace_id="consistency")
        assert result.tick_at == NOW + timedelta(
            milliseconds=123 if milliseconds else 0
        )
    finally:
        adapter.disconnect()


def test_native_integer_enum_is_supported_without_coercing_other_types(
    tmp_path: Path,
) -> None:
    class Mode(IntEnum):
        DEMO = 0

    module = NativeModuleFake()
    cast(SimpleNamespace, module.account_result).trade_mode = Mode.DEMO
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="consistency")
    try:
        assert (
            adapter.get_account_info(trace_id="consistency").trade_mode
            is AccountTradeMode.DEMO
        )
    finally:
        adapter.disconnect()


def test_native_numpy_integer_scalars_retain_exact_meaning(tmp_path: Path) -> None:
    numpy = pytest.importorskip("numpy")
    module = NativeModuleFake()
    cast(SimpleNamespace, module.account_result).trade_mode = numpy.int64(0)
    raw = cast(SimpleNamespace, module.tick_result)
    raw.time = numpy.int64(int(NOW.timestamp()))
    raw.time_msc = numpy.int64(int(NOW.timestamp()) * 1_000 + 123)
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="consistency")
    try:
        assert (
            adapter.get_account_info(trace_id="consistency").trade_mode
            is AccountTradeMode.DEMO
        )
        assert adapter.get_latest_tick(
            "XAUUSD", trace_id="consistency"
        ).tick_at == NOW + timedelta(milliseconds=123)
    finally:
        adapter.disconnect()


def _after_history(monkeypatch: pytest.MonkeyPatch, change: Callable[[], None]) -> None:
    original = FakeMt5ReadAdapter.get_deal_history

    def changed(
        adapter: FakeMt5ReadAdapter, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalDealObservation]:
        rows = original(adapter, request, trace_id=trace_id)
        change()
        return rows

    monkeypatch.setattr(FakeMt5ReadAdapter, "get_deal_history", changed)


def _reconciler(
    adapter: FakeMt5ReadAdapter,
    *,
    clock: Callable[[], datetime] = lambda: NOW,
) -> tuple[ReadOnlyReconciliationService, InMemoryMt5ObservationPersistence]:
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    return (
        ReadOnlyReconciliationService(
            adapter,
            store,
            config(),
            clock=clock,
            identifier_factory=lambda: "00000000-0000-4000-8000-000000000111",
        ),
        store,
    )


@pytest.mark.parametrize(
    ("change_kind", "reason"),
    [
        ("real", Mt5ReasonCode.REAL_ACCOUNT_BLOCKED),
        ("contest", Mt5ReasonCode.CONTEST_ACCOUNT_BLOCKED),
        ("unknown", Mt5ReasonCode.TRADE_MODE_UNKNOWN),
        ("identity", Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH),
        ("server", Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH),
        ("disconnected", Mt5ReasonCode.TERMINAL_DISCONNECTED),
        ("specification", Mt5ReasonCode.SYMBOL_SPEC_CHANGED),
        ("binding", Mt5ReasonCode.SYMBOL_SPEC_CHANGED),
        ("database_account", Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH),
    ],
)
def test_changed_context_during_full_reads_never_persists_mixed_tick_or_healthy_report(
    monkeypatch: pytest.MonkeyPatch, change_kind: str, reason: Mt5ReasonCode
) -> None:
    adapter = fake_adapter()
    reconciler, store = _reconciler(adapter)

    def change() -> None:
        if change_kind in {"real", "contest", "unknown"}:
            adapter.accounts = (account(AccountTradeMode(change_kind)),)
        elif change_kind in {"identity", "server"}:
            field = (
                "account_fingerprint"
                if change_kind == "identity"
                else "server_fingerprint"
            )
            adapter.accounts = (
                account().model_copy(update={field: "changed-fixture"}),
            )
        elif change_kind == "disconnected":
            adapter.connected = False
        elif change_kind == "specification":
            adapter.specifications["XAUUSD"] = specification("mt5-spec-v1:changed")
        elif change_kind == "binding":
            store.database_state = store.database_state.model_copy(
                update={"confirmed_symbol_binding": confirmed_binding(version=2)}
            )
        else:
            store.database_state = store.database_state.model_copy(
                update={"account_fingerprint": "changed-fixture"}
            )

    _after_history(monkeypatch, change)
    with pytest.raises(Mt5ReadFailure) as raised:
        reconciler.run(trace_id="consistency")
    assert raised.value.error.reason_code is reason
    assert not store.ticks
    assert not store.reports


@pytest.mark.parametrize(
    ("elapsed", "freshness", "health", "reason"),
    [
        (0, TickFreshness.LIVE, HealthState.HEALTHY, Mt5ReasonCode.HEALTHY),
        (5, TickFreshness.DELAYED, HealthState.DEGRADED, Mt5ReasonCode.TICK_DELAYED),
        (120, TickFreshness.STALE, HealthState.BLOCKED, Mt5ReasonCode.TICK_STALE),
    ],
)
def test_reconciliation_uses_tick_age_at_decision_not_before_slow_history(
    monkeypatch: pytest.MonkeyPatch,
    elapsed: int,
    freshness: TickFreshness,
    health: HealthState,
    reason: Mt5ReasonCode,
) -> None:
    current = [NOW]
    adapter = fake_adapter()
    reconciler, store = _reconciler(adapter, clock=lambda: current[0])
    _after_history(
        monkeypatch, lambda: current.__setitem__(0, NOW + timedelta(seconds=elapsed))
    )
    result = reconciler.run(trace_id="consistency")
    assert result.tick_freshness is freshness
    assert result.health.state is health
    assert result.health.reason_code is reason
    assert result.health.tick_age_seconds == Decimal(elapsed + 1)
    persisted = next(iter(store.ticks.values()))
    assert persisted.observed_at == NOW
    assert persisted.tick_at == NOW - timedelta(seconds=1)


@pytest.mark.parametrize(
    "freshness",
    [
        TickFreshness.DELAYED,
        TickFreshness.STALE,
        TickFreshness.FUTURE_INVALID,
        TickFreshness.UNAVAILABLE,
    ],
)
def test_decision_clock_cannot_promote_previously_unsafe_tick(
    freshness: TickFreshness,
) -> None:
    adapter = fake_adapter()
    adapter.ticks["XAUUSD"] = adapter.ticks["XAUUSD"].model_copy(
        update={"freshness": freshness}
    )
    reconciler, _ = _reconciler(adapter)
    result = reconciler.run(trace_id="consistency")
    assert result.tick_freshness is freshness
    assert result.health.state is not HealthState.HEALTHY


@pytest.mark.parametrize("switch_account", [False, True])
def test_slow_report_write_cannot_return_a_current_healthy_or_mixed_result(
    monkeypatch: pytest.MonkeyPatch, switch_account: bool
) -> None:
    current = [NOW]
    adapter = fake_adapter()
    reconciler, store = _reconciler(adapter, clock=lambda: current[0])
    original = InMemoryMt5ObservationPersistence.complete_reconciliation

    def slow_complete(
        persistence: InMemoryMt5ObservationPersistence, report: ReconciliationReport
    ) -> str:
        result = original(persistence, report)
        current[0] += timedelta(seconds=120)
        if switch_account:
            adapter.accounts = (account(AccountTradeMode.REAL),)
        return result

    monkeypatch.setattr(
        InMemoryMt5ObservationPersistence, "complete_reconciliation", slow_complete
    )
    if switch_account:
        with pytest.raises(Mt5ReadFailure) as raised:
            reconciler.run(trace_id="consistency")
        assert raised.value.error.reason_code is Mt5ReasonCode.REAL_ACCOUNT_BLOCKED
    else:
        result = reconciler.run(trace_id="consistency")
        assert result.health.state is HealthState.BLOCKED
        assert result.health.reason_code is Mt5ReasonCode.TICK_STALE
        assert result.health.tick_age_seconds == Decimal(121)
        assert result.tick_freshness is TickFreshness.STALE
    # Historical evidence remains historical, not overwritten as a later read.
    report = next(iter(store.reports.values()))
    assert report.completed_at == NOW
    assert report.outcome is ReconciliationOutcome.MATCHED


def test_slow_tick_upsert_does_not_advance_the_report_evidence_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = [NOW]
    adapter = fake_adapter()
    reconciler, store = _reconciler(adapter, clock=lambda: current[0])
    original = InMemoryMt5ObservationPersistence.upsert_tick

    def slow_upsert(
        persistence: InMemoryMt5ObservationPersistence,
        tick: LatestTickObservation,
        account_fingerprint: str,
    ) -> str:
        result = original(persistence, tick, account_fingerprint)
        current[0] += timedelta(seconds=120)
        return result

    monkeypatch.setattr(InMemoryMt5ObservationPersistence, "upsert_tick", slow_upsert)
    result = reconciler.run(trace_id="consistency")
    assert result.report.completed_at == NOW
    assert result.report.observed_at == NOW
    assert result.report.outcome is ReconciliationOutcome.MATCHED
    assert result.health.observed_at == NOW + timedelta(seconds=120)
    assert result.health.state is HealthState.BLOCKED
    assert result.health.reason_code is Mt5ReasonCode.TICK_STALE
    assert result.health.tick_age_seconds == Decimal(121)
