"""Light polling must not renew health from a mixed-account or expired read."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from mt5_factories import NOW, account, fake_adapter
from test_mt5_reconciliation import config, confirmed_state

from aurum_worker.adapters.fake_mt5 import FakeMt5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountTradeMode,
    ComponentHeartbeat,
    ComponentHeartbeatState,
    HealthState,
    LatestTickObservation,
    Mt5ComponentCode,
    Mt5ReadFailure,
    Mt5ReasonCode,
)
from aurum_worker.polling import ReadOnlyPollingService
from aurum_worker.reconciliation import ReadOnlyReconciliationService


def setup_poller() -> tuple[
    FakeMt5ReadAdapter,
    InMemoryMt5ObservationPersistence,
    ReadOnlyPollingService,
    list[LatestTickObservation],
]:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    callbacks: list[LatestTickObservation] = []
    worker_config = config()
    reconciler = ReadOnlyReconciliationService(
        adapter, store, worker_config, clock=lambda: NOW
    )
    polling = ReadOnlyPollingService(
        adapter,
        store,
        reconciler,
        worker_config,
        clock=lambda: NOW,
        on_tick=lambda tick, _account: callbacks.append(tick),
    )
    assert polling.run_once().health.state is HealthState.HEALTHY
    adapter.call_log.clear()
    return adapter, store, polling, callbacks


def after_read(
    monkeypatch: pytest.MonkeyPatch, method: str, callback: Callable[[], None]
) -> None:
    original = FakeMt5ReadAdapter._record

    def record(adapter: FakeMt5ReadAdapter, name: str) -> None:
        original(adapter, name)
        if name == method:
            callback()

    monkeypatch.setattr(FakeMt5ReadAdapter, "_record", record)


@pytest.mark.parametrize("operation", ["tick", "position"])
@pytest.mark.parametrize(
    "replacement",
    [
        account(AccountTradeMode.REAL),
        account(AccountTradeMode.CONTEST),
        account(AccountTradeMode.UNKNOWN),
        account().model_copy(update={"server_fingerprint": "mt5-server-v1:changed"}),
    ],
)
def test_account_change_during_light_read_never_publishes_mixed_health(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    replacement: AccountObservation,
) -> None:
    adapter, store, polling, callbacks = setup_poller()
    original_tick = store.ticks["XAUUSD"]

    def change_account() -> None:
        adapter.accounts = (replacement,)

    after_read(
        monkeypatch,
        "get_latest_tick" if operation == "tick" else "get_active_orders",
        change_account,
    )
    accepted = (
        polling.run_tick_once() if operation == "tick" else polling.run_position_once()
    )
    assert accepted is False
    assert polling.state.health_state is not HealthState.HEALTHY
    assert polling.state.reconciliation_required is True
    assert store.ticks["XAUUSD"] is original_tick
    assert callbacks == []
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is not (
        ComponentHeartbeatState.HEALTHY
    )
    assert "get_order_history" not in adapter.call_log
    assert "get_deal_history" not in adapter.call_log


def test_position_poll_checks_current_account_before_reading_positions() -> None:
    adapter, store, polling, _ = setup_poller()
    market_before = store.heartbeats[Mt5ComponentCode.MARKET_DATA]
    adapter.accounts = (account(AccountTradeMode.REAL),)
    assert polling.run_position_once() is False
    assert polling.state.reason_code is Mt5ReasonCode.REAL_ACCOUNT_BLOCKED
    assert "get_open_positions" not in adapter.call_log
    assert "get_active_orders" not in adapter.call_log
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA] is market_before


def test_account_switch_during_tick_persistence_never_reaches_consumers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, store, polling, callbacks = setup_poller()
    original = InMemoryMt5ObservationPersistence.upsert_tick

    def switching_upsert(
        persistence: InMemoryMt5ObservationPersistence,
        observation: LatestTickObservation,
        fingerprint: str,
    ) -> str:
        result = original(persistence, observation, fingerprint)
        adapter.accounts = (account(AccountTradeMode.REAL),)
        return result

    monkeypatch.setattr(
        InMemoryMt5ObservationPersistence, "upsert_tick", switching_upsert
    )
    assert polling.run_tick_once() is False
    assert polling.state.reason_code is Mt5ReasonCode.REAL_ACCOUNT_BLOCKED
    assert polling.state.reconciliation_required is True
    assert callbacks == []
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.FAILED
    )


@pytest.mark.parametrize("change", ["stale", "real"])
def test_heartbeat_latency_or_account_switch_cannot_dispatch_a_tick(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    adapter, store, polling, callbacks = setup_poller()
    clock = [NOW]
    polling._clock = lambda: clock[0]
    original = InMemoryMt5ObservationPersistence.record_component_heartbeat

    def changing_heartbeat(
        persistence: InMemoryMt5ObservationPersistence, heartbeat: ComponentHeartbeat
    ) -> str:
        result = original(persistence, heartbeat)
        if change == "stale":
            clock[0] = NOW + timedelta(seconds=120)
        else:
            adapter.accounts = (account(AccountTradeMode.REAL),)
        return result

    monkeypatch.setattr(
        InMemoryMt5ObservationPersistence,
        "record_component_heartbeat",
        changing_heartbeat,
    )
    assert polling.run_tick_once() is False
    assert polling.state.health_state is not HealthState.HEALTHY
    assert polling.state.reconciliation_required is True
    assert callbacks == []
    assert store.heartbeats[Mt5ComponentCode.WORKER].state is not (
        ComponentHeartbeatState.HEALTHY
    )


@pytest.mark.parametrize("operation", ["tick", "position"])
def test_terminal_disconnect_during_light_read_clears_cached_health(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    adapter, store, polling, callbacks = setup_poller()
    original_tick = store.ticks["XAUUSD"]

    def disconnect() -> None:
        adapter.connected = False

    after_read(
        monkeypatch,
        "get_latest_tick" if operation == "tick" else "get_active_orders",
        disconnect,
    )
    with pytest.raises(Mt5ReadFailure):
        if operation == "tick":
            polling.run_tick_once()
        else:
            polling.run_position_once()
    assert polling.state.health_state is not HealthState.HEALTHY
    assert polling.state.connected is False
    assert polling.state.reconciliation_required is True
    assert store.ticks["XAUUSD"] is original_tick
    assert callbacks == []


@pytest.mark.parametrize("delay_at", ["get_latest_tick", "upsert_tick"])
def test_tick_age_is_rechecked_after_read_and_persistence_latency(
    monkeypatch: pytest.MonkeyPatch, delay_at: str
) -> None:
    _, store, polling, callbacks = setup_poller()
    clock = [NOW]
    polling._clock = lambda: clock[0]

    def advance() -> None:
        clock[0] = NOW + timedelta(seconds=120)

    if delay_at == "get_latest_tick":
        after_read(monkeypatch, delay_at, advance)
    else:
        original = InMemoryMt5ObservationPersistence.upsert_tick

        def slow_upsert(
            persistence: InMemoryMt5ObservationPersistence,
            observation: LatestTickObservation,
            fingerprint: str,
        ) -> str:
            result = original(persistence, observation, fingerprint)
            advance()
            return result

        monkeypatch.setattr(
            InMemoryMt5ObservationPersistence, "upsert_tick", slow_upsert
        )

    assert polling.run_tick_once() is False
    assert polling.state.reason_code is Mt5ReasonCode.TICK_STALE
    assert polling.state.reconciliation_required is True
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.ticks["XAUUSD"].observed_at == NOW
    assert callbacks == []
