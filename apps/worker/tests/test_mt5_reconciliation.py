from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from itertools import count
from threading import Event
from time import monotonic

import pytest
from mt5_factories import (
    NOW,
    account,
    active_order,
    confirmed_binding,
    fake_adapter,
    position,
    specification,
    terminal,
    tick,
)

from aurum_worker.adapters.persistence_mt5 import (
    InMemoryMt5ObservationPersistence,
    WorkerRpcMt5ObservationPersistence,
)
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    ComponentHeartbeat,
    ComponentHeartbeatState,
    DatabaseReconciliationState,
    HealthState,
    HistoryQueryResultState,
    Mt5ComponentCode,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReconciliationCategory,
    ReconciliationOutcome,
    SafeMt5Error,
    SymbolUsabilityState,
    TickFreshness,
)
from aurum_worker.polling import ReadOnlyPollingService
from aurum_worker.reconciliation import ReadOnlyReconciliationService


def config(
    *, bound: bool = True, broker_symbol: str | None = "XAUUSD"
) -> Mt5WorkerConfig:
    return Mt5WorkerConfig(
        broker_symbol=broker_symbol,
        expected_account_fingerprint=(account().account_fingerprint if bound else None),
        tick_poll_seconds=Decimal("1"),
        position_poll_seconds=Decimal("5"),
        full_reconciliation_seconds=Decimal("60"),
        reconnect_max_seconds=Decimal("4"),
    )


def confirmed_state(**updates: object) -> DatabaseReconciliationState:
    values: dict[str, object] = {"confirmed_symbol_binding": confirmed_binding()}
    values.update(updates)
    return DatabaseReconciliationState.model_validate(values)


class RecordingHeartbeatPersistence(InMemoryMt5ObservationPersistence):
    heartbeat_history: list[ComponentHeartbeat]

    def __init__(self, database_state: DatabaseReconciliationState) -> None:
        super().__init__(database_state=database_state)
        self.heartbeat_history = []

    def record_component_heartbeat(self, heartbeat: ComponentHeartbeat) -> str:
        result = super().record_component_heartbeat(heartbeat)
        self.heartbeat_history.append(heartbeat)
        return result


class FailFirstHeartbeatBatchPersistence(RecordingHeartbeatPersistence):
    heartbeat_attempts: list[ComponentHeartbeat]

    def __init__(self, database_state: DatabaseReconciliationState) -> None:
        super().__init__(database_state)
        self.heartbeat_attempts = []

    def record_component_heartbeat(self, heartbeat: ComponentHeartbeat) -> str:
        self.heartbeat_attempts.append(heartbeat)
        if len(self.heartbeat_attempts) <= len(Mt5ComponentCode):
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Heartbeat persistence is unavailable.",
                    retryable=True,
                )
            )
        return super().record_component_heartbeat(heartbeat)


class LifecycleHeartbeatPersistence(RecordingHeartbeatPersistence):
    running_probe: Callable[[], bool] | None
    worker_publications: list[tuple[ComponentHeartbeat, bool]]

    def __init__(self, database_state: DatabaseReconciliationState) -> None:
        super().__init__(database_state)
        self.running_probe = None
        self.worker_publications = []

    def record_component_heartbeat(self, heartbeat: ComponentHeartbeat) -> str:
        if heartbeat.component_code is Mt5ComponentCode.WORKER:
            running = self.running_probe() if self.running_probe is not None else False
            self.worker_publications.append((heartbeat, running))
        return super().record_component_heartbeat(heartbeat)


class FailFinalHeartbeatPersistence(LifecycleHeartbeatPersistence):
    fail_heartbeat_writes: bool
    failed_heartbeat_attempts: list[ComponentHeartbeat]

    def __init__(self, database_state: DatabaseReconciliationState) -> None:
        super().__init__(database_state)
        self.fail_heartbeat_writes = False
        self.failed_heartbeat_attempts = []

    def record_component_heartbeat(self, heartbeat: ComponentHeartbeat) -> str:
        if self.fail_heartbeat_writes:
            self.failed_heartbeat_attempts.append(heartbeat)
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Heartbeat persistence is unavailable.",
                    retryable=True,
                )
            )
        return super().record_component_heartbeat(heartbeat)


class DownHeartbeatTransportClient:
    def __init__(self, sentinel: str) -> None:
        self.sentinel = sentinel
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, function: str, parameters: dict[str, object]) -> dict[str, object]:
        self.calls.append((function, parameters))
        raise RuntimeError(self.sentinel)


def service(
    *,
    adapter=None,
    persistence: InMemoryMt5ObservationPersistence | None = None,
    worker_config: Mt5WorkerConfig | None = None,
    identifier_factory=None,
) -> tuple[ReadOnlyReconciliationService, InMemoryMt5ObservationPersistence]:
    store = persistence
    if store is None:
        store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    identifiers = count(1)
    reconciler = ReadOnlyReconciliationService(
        adapter or fake_adapter(),
        store,
        worker_config or config(),
        clock=lambda: NOW,
        identifier_factory=identifier_factory
        or (lambda: f"00000000-0000-4000-8000-{next(identifiers):012d}"),
    )
    return reconciler, store


def poller(
    adapter,
    store: InMemoryMt5ObservationPersistence,
    reconciler: ReadOnlyReconciliationService,
    *,
    clock=None,
    monotonic_clock=None,
    worker_config: Mt5WorkerConfig | None = None,
) -> ReadOnlyPollingService:
    return ReadOnlyPollingService(
        adapter,
        store,
        reconciler,
        worker_config or config(),
        clock=clock or (lambda: NOW),
        monotonic_clock=monotonic_clock,
        jitter=lambda _attempt: Decimal("0.25"),
        trace_factory=lambda: "poll-trace",
    )


def test_clean_reconciliation_is_required_before_healthy() -> None:
    reconciler, store = service()
    result = reconciler.run(trace_id="trace-clean")
    assert result.report.outcome is ReconciliationOutcome.MATCHED
    assert result.report.broker_symbol == "XAUUSD"
    assert result.health.state is HealthState.HEALTHY
    assert result.health.reconciliation_outcome is ReconciliationOutcome.MATCHED
    assert store.accounts and store.symbols and store.ticks
    assert store.heartbeats == {}
    assert result.report.order_history_evidence.requested_end_at == NOW
    assert result.report.order_history_evidence.requested_start_at < NOW


def test_demo_unbound_is_diagnostic_but_never_healthy() -> None:
    reconciler, _ = service(worker_config=config(bound=False))
    result = reconciler.run(trace_id="trace-unbound")
    assert result.report.outcome is ReconciliationOutcome.MATCHED
    assert result.health.state is HealthState.DEGRADED
    assert result.health.reason_code is Mt5ReasonCode.DEMO_ACCOUNT_UNBOUND


def test_demo_unbound_stale_tick_remains_blocked() -> None:
    adapter = fake_adapter(freshness=TickFreshness.STALE)
    reconciler, _ = service(adapter=adapter, worker_config=config(bound=False))

    result = reconciler.run(trace_id="trace-unbound-stale")

    assert result.health.state is HealthState.BLOCKED
    assert result.health.reason_code is Mt5ReasonCode.TICK_STALE


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        (AccountTradeMode.REAL, Mt5ReasonCode.REAL_ACCOUNT_BLOCKED),
        (AccountTradeMode.CONTEST, Mt5ReasonCode.CONTEST_ACCOUNT_BLOCKED),
        (AccountTradeMode.UNKNOWN, Mt5ReasonCode.TRADE_MODE_UNKNOWN),
    ],
)
def test_non_demo_account_is_blocked_and_incident_recorded(
    mode: AccountTradeMode, reason: Mt5ReasonCode
) -> None:
    adapter = fake_adapter(account_modes=(mode,))
    reconciler, store = service(adapter=adapter)
    result = reconciler.run(trace_id="trace-blocked")
    assert result.health.state is HealthState.BLOCKED
    assert result.health.reason_code is reason
    assert result.report.outcome is ReconciliationOutcome.INCOMPLETE
    assert result.report.order_history_evidence.result_state is (
        HistoryQueryResultState.WINDOW_UNKNOWN
    )
    assert store.incidents
    assert "get_symbol_specification" not in adapter.call_log


def test_missing_or_ambiguous_symbol_never_auto_binds() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence()
    reconciler, _ = service(
        adapter=adapter,
        persistence=store,
        worker_config=config(broker_symbol=None),
    )
    result = reconciler.run(trace_id="trace-symbol")
    assert result.health.reason_code is Mt5ReasonCode.SYMBOL_NOT_CONFIGURED
    assert result.report.broker_symbol is None
    assert "get_symbol_specification" not in adapter.call_log
    assert store.database_state.confirmed_symbol_binding is None

    adapter = fake_adapter()
    adapter.candidates = adapter.candidates + adapter.candidates
    store = InMemoryMt5ObservationPersistence()
    reconciler, _ = service(
        adapter=adapter,
        persistence=store,
        worker_config=config(broker_symbol=None),
    )
    result = reconciler.run(trace_id="trace-ambiguous")
    assert result.health.reason_code is Mt5ReasonCode.SYMBOL_AMBIGUOUS
    assert store.database_state.confirmed_symbol_binding is None


def test_previously_confirmed_database_symbol_is_reused_without_discovery() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(
        adapter=adapter,
        persistence=store,
        worker_config=config(broker_symbol=None),
    )
    result = reconciler.run(trace_id="trace-confirmed-symbol")
    assert result.health.broker_symbol == "XAUUSD"
    assert result.health.state is HealthState.HEALTHY
    assert "list_symbol_candidates" not in adapter.call_log


def test_missing_confirmation_records_observation_but_never_becomes_healthy() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence()
    reconciler, _ = service(adapter=adapter, persistence=store)

    first = reconciler.run(trace_id="trace-unconfirmed-1")
    second = reconciler.run(trace_id="trace-unconfirmed-2")

    assert first.report.broker_symbol == second.report.broker_symbol == "XAUUSD"
    assert first.health.reason_code is Mt5ReasonCode.SYMBOL_SPEC_CONFIRMATION_REQUIRED
    assert second.health.reason_code is Mt5ReasonCode.SYMBOL_SPEC_CONFIRMATION_REQUIRED
    assert first.health.state is second.health.state is HealthState.BLOCKED
    assert len(store.symbols) == 1
    assert store.database_state.confirmed_symbol_binding is None


def test_changed_observation_never_replaces_permanent_confirmation() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    assert reconciler.run(trace_id="trace-a").health.state is HealthState.HEALTHY

    observed_b = specification("mt5-spec-v1:changed")
    adapter.specifications["XAUUSD"] = observed_b
    first_changed = reconciler.run(trace_id="trace-b-1")
    second_changed = reconciler.run(trace_id="trace-b-2")

    assert first_changed.health.reason_code is Mt5ReasonCode.SYMBOL_SPEC_CHANGED
    assert second_changed.health.reason_code is Mt5ReasonCode.SYMBOL_SPEC_CHANGED
    assert (
        first_changed.health.state is second_changed.health.state is HealthState.BLOCKED
    )
    assert store.database_state.confirmed_symbol_binding == confirmed_binding(
        "mt5-spec-v1:fixture"
    )

    store.database_state = store.database_state.model_copy(
        update={
            "confirmed_symbol_binding": confirmed_binding(
                "mt5-spec-v1:changed", version=2
            )
        }
    )
    explicitly_confirmed = reconciler.run(trace_id="trace-b-confirmed")
    assert explicitly_confirmed.health.state is HealthState.HEALTHY


def test_position_order_and_execution_uncertainty_mismatches_are_observation_only() -> (
    None
):
    adapter = fake_adapter(positions=(position(),), orders=(active_order(),))
    store = InMemoryMt5ObservationPersistence(
        database_state=confirmed_state(
            position_tickets=frozenset({"1002"}),
            active_order_tickets=frozenset({"2002"}),
            executing_command_ids=frozenset({"command-uncertain"}),
        )
    )
    reconciler, store = service(adapter=adapter, persistence=store)
    result = reconciler.run(trace_id="trace-mismatch")
    categories = {mismatch.category for mismatch in result.report.mismatches}
    assert categories == {
        ReconciliationCategory.UNEXPECTED_BROKER_POSITION,
        ReconciliationCategory.DATABASE_POSITION_MISSING_AT_BROKER,
        ReconciliationCategory.UNEXPECTED_ACTIVE_ORDER,
        ReconciliationCategory.DATABASE_ORDER_MISSING_AT_BROKER,
        ReconciliationCategory.EXECUTION_RESULT_UNCERTAIN,
    }
    assert result.health.state is HealthState.BLOCKED
    assert not any("command" in call for call in adapter.call_log)
    assert len(store.incidents) == len(categories)


def test_account_server_spec_and_clock_changes_are_detected() -> None:
    adapter = fake_adapter(freshness=TickFreshness.FUTURE_INVALID)
    store = InMemoryMt5ObservationPersistence(
        database_state=confirmed_state(
            account_fingerprint="mt5-account-v1:previous",
            server_fingerprint="mt5-server-v1:previous",
            confirmed_symbol_binding=confirmed_binding("mt5-spec-v1:previous"),
        )
    )
    reconciler, _ = service(adapter=adapter, persistence=store)
    result = reconciler.run(trace_id="trace-changes")
    categories = {mismatch.category for mismatch in result.report.mismatches}
    assert {
        ReconciliationCategory.ACCOUNT_CHANGED,
        ReconciliationCategory.SERVER_CHANGED,
        ReconciliationCategory.SYMBOL_SPEC_CHANGED,
        ReconciliationCategory.CLOCK_INCONSISTENCY,
    }.issubset(categories)


def test_empty_histories_are_valid_current_bounded_evidence() -> None:
    adapter = fake_adapter()
    adapter.order_history = ()
    adapter.deal_history = ()
    reconciler, _ = service(adapter=adapter)

    result = reconciler.run(trace_id="trace-empty-history")

    assert result.health.state is HealthState.HEALTHY
    assert result.report.order_history_evidence.result_state is (
        HistoryQueryResultState.EMPTY_VALID_RESULT
    )
    assert result.report.deal_history_evidence.result_state is (
        HistoryQueryResultState.EMPTY_VALID_RESULT
    )
    assert result.report.order_history_evidence.reason_code is (
        Mt5ReasonCode.HISTORY_EMPTY_VALID_RESULT
    )
    assert result.report.deal_history_evidence.reason_code is (
        Mt5ReasonCode.HISTORY_EMPTY_VALID_RESULT
    )
    assert result.report.order_history_count == result.report.deal_history_count == 0


@pytest.mark.parametrize(
    ("failed_method", "failed_kind", "successful_kind"),
    [
        ("get_order_history", "orders", "deals"),
        ("get_deal_history", "deals", "orders"),
    ],
)
def test_each_current_history_failure_is_evidenced_and_blocks_healthy(
    failed_method: str, failed_kind: str, successful_kind: str
) -> None:
    adapter = fake_adapter()
    adapter.failures[failed_method] = Mt5ReasonCode.HISTORY_QUERY_FAILED
    reconciler, _ = service(adapter=adapter)

    result = reconciler.run(trace_id=f"trace-{failed_kind}-failed")

    evidence = {
        "orders": result.report.order_history_evidence,
        "deals": result.report.deal_history_evidence,
    }
    assert evidence[failed_kind].result_state is HistoryQueryResultState.QUERY_FAILED
    assert evidence[successful_kind].result_state is (
        HistoryQueryResultState.QUERY_SUCCEEDED
    )
    assert result.health.state is HealthState.BLOCKED
    assert result.health.reason_code is Mt5ReasonCode.HISTORY_QUERY_FAILED
    assert "get_order_history" in adapter.call_log
    assert "get_deal_history" in adapter.call_log


def test_current_report_persists_exact_history_boundaries_and_counts() -> None:
    reconciler, store = service()

    result = reconciler.run(trace_id="trace-history-boundaries")

    orders = result.report.order_history_evidence
    deals = result.report.deal_history_evidence
    assert orders.requested_end_at == deals.requested_end_at == NOW
    assert orders.requested_start_at == deals.requested_start_at
    assert orders.query_completed_at == deals.query_completed_at == NOW
    assert orders.returned_count == deals.returned_count == 1
    assert orders.earliest_returned_at == orders.latest_returned_at
    assert deals.earliest_returned_at == deals.latest_returned_at
    persisted = store.reports[result.report.reconciliation_id]
    assert persisted.order_history_evidence == orders
    assert persisted.deal_history_evidence == deals


def test_stale_tick_blocks_and_symbol_state_changes_are_observed() -> None:
    adapter = fake_adapter(freshness=TickFreshness.STALE)
    reconciler, _ = service(adapter=adapter)
    stale = reconciler.run(trace_id="trace-stale")
    assert stale.health.state is HealthState.BLOCKED
    assert stale.health.reason_code is Mt5ReasonCode.TICK_STALE

    adapter = fake_adapter()
    reconciler, store = service(adapter=adapter)
    assert reconciler.run(trace_id="trace-usable-symbol").health.state is (
        HealthState.HEALTHY
    )
    assert len(store.symbols) == 1

    adapter.specifications["XAUUSD"] = adapter.specifications["XAUUSD"].model_copy(
        update={
            "usability_state": SymbolUsabilityState.NOT_VISIBLE,
            "unusable_reason": Mt5ReasonCode.SYMBOL_NOT_VISIBLE,
        }
    )
    with pytest.raises(Mt5ReadFailure) as raised:
        reconciler.run(trace_id="trace-unusable-symbol")
    assert raised.value.error.reason_code is Mt5ReasonCode.SYMBOL_NOT_VISIBLE
    assert "Market Watch" in raised.value.error.safe_detail
    assert len(store.symbols) == 2
    assert store.symbols[-1].usability_state is SymbolUsabilityState.NOT_VISIBLE

    with pytest.raises(Mt5ReadFailure):
        reconciler.run(trace_id="trace-unusable-symbol-repeated")
    assert len(store.symbols) == 2

    adapter.specifications["XAUUSD"] = specification()
    assert reconciler.run(trace_id="trace-usable-symbol-restored").health.state is (
        HealthState.HEALTHY
    )
    assert len(store.symbols) == 3
    assert store.symbols[-1].usability_state is SymbolUsabilityState.USABLE


def test_reconciliation_report_replay_is_idempotent() -> None:
    reconciler, store = service(identifier_factory=lambda: "same-reconciliation")
    first = reconciler.run(trace_id="same-trace")
    second = reconciler.run(trace_id="same-trace")
    assert first.report.reconciliation_id == second.report.reconciliation_id
    assert len(store.reports) == 1


def test_database_reporting_failure_fails_closed() -> None:
    store = InMemoryMt5ObservationPersistence(
        database_state=confirmed_state(), fail_operations={"record_account"}
    )
    reconciler, _ = service(persistence=store)
    with pytest.raises(Mt5ReadFailure) as raised:
        reconciler.run(trace_id="trace-db-failure")
    assert raised.value.error.reason_code is Mt5ReasonCode.DATABASE_REPORT_FAILED


def test_short_tick_poll_has_no_history_or_reconciliation_run() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling.run_once()
    report_count = len(store.reports)
    adapter.call_log.clear()

    assert polling.run_tick_once() is True

    assert adapter.call_log == [
        "get_terminal_info",
        "get_account_info",
        "get_latest_tick",
    ]
    assert len(store.reports) == report_count
    assert len(store.ticks) == 1
    polling.stop()


@pytest.mark.parametrize(
    ("freshness", "health_state", "reason"),
    [
        (TickFreshness.STALE, HealthState.BLOCKED, Mt5ReasonCode.TICK_STALE),
        (
            TickFreshness.FUTURE_INVALID,
            HealthState.BLOCKED,
            Mt5ReasonCode.TICK_FROM_FUTURE,
        ),
        (
            TickFreshness.DELAYED,
            HealthState.DEGRADED,
            Mt5ReasonCode.TICK_DELAYED,
        ),
    ],
)
def test_non_live_short_tick_requires_full_before_health_can_return(
    freshness: TickFreshness,
    health_state: HealthState,
    reason: Mt5ReasonCode,
) -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling.run_once()
    replacement = tick(freshness)
    adapter.replace_tick("XAUUSD", replacement)

    assert polling.run_tick_once() is False
    assert polling.state.health_state is health_state
    assert polling.state.reason_code is reason
    assert polling.state.reconciliation_required is True
    assert store.ticks["XAUUSD"].freshness is freshness
    polling.stop()


def test_light_tick_recovery_requests_full_without_restoring_healthy() -> None:
    adapter = fake_adapter(freshness=TickFreshness.STALE)
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    blocked = polling.run_once()
    assert blocked.health.state is HealthState.BLOCKED
    assert polling.state.reconciliation_required is False

    adapter.replace_tick("XAUUSD", tick(TickFreshness.LIVE))
    assert polling.run_tick_once() is True
    assert polling.state.health_state is HealthState.BLOCKED
    assert polling.state.reconciliation_required is True

    restored = polling.run_once()
    assert restored.health.state is HealthState.HEALTHY
    assert polling.state.health_state is HealthState.HEALTHY
    polling.stop()


def test_stable_non_live_tick_does_not_flood_full_reconciliation() -> None:
    timeline = [0.0]
    adapter = fake_adapter(freshness=TickFreshness.STALE)
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(
        adapter,
        store,
        reconciler,
        monotonic_clock=lambda: timeline[0],
    )

    assert polling.run_due_once() == "full"
    assert polling.state.health_state is HealthState.BLOCKED
    assert len(store.reports) == 1
    for current_time in (1.0, 2.0, 3.0):
        timeline[0] = current_time
        assert polling.run_due_once() == "tick"
        assert polling.state.reconciliation_required is False
        assert len(store.reports) == 1

    polling.stop()


@pytest.mark.parametrize("bound", [True, False])
def test_background_light_poll_continues_after_non_healthy_full_result(
    bound: bool,
) -> None:
    worker_config = config(bound=bound)
    adapter = fake_adapter()
    if bound:
        adapter.failures["get_order_history"] = Mt5ReasonCode.HISTORY_QUERY_FAILED
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(
        adapter=adapter,
        persistence=store,
        worker_config=worker_config,
    )
    polling = poller(
        adapter,
        store,
        reconciler,
        worker_config=worker_config,
    )

    polling.start()
    try:
        deadline = monotonic() + 2.5
        while adapter.call_log.count("get_latest_tick") < 2 and monotonic() < deadline:
            Event().wait(0.025)
        assert adapter.call_log.count("get_latest_tick") >= 2
        assert adapter.call_log.count("get_order_history") == 1
    finally:
        polling.stop(timeout_seconds=2)


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        (AccountTradeMode.REAL, Mt5ReasonCode.REAL_ACCOUNT_BLOCKED),
        (AccountTradeMode.CONTEST, Mt5ReasonCode.CONTEST_ACCOUNT_BLOCKED),
    ],
)
def test_short_tick_account_policy_clears_prior_healthy_immediately(
    mode: AccountTradeMode, reason: Mt5ReasonCode
) -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling.run_once()
    assert polling.state.health_state is HealthState.HEALTHY
    adapter.accounts = (account(mode),)

    assert polling.run_tick_once() is False
    assert polling.state.health_state is HealthState.BLOCKED
    assert polling.state.reason_code is reason
    assert polling.state.reconciliation_required is True
    assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.WORKER].detail is reason
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].detail is reason
    polling.stop()


@pytest.mark.parametrize("missing_broker", [False, True])
def test_short_tick_identity_or_broker_gap_clears_prior_healthy_immediately(
    missing_broker: bool,
) -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling.run_once()
    assert polling.state.health_state is HealthState.HEALTHY
    if missing_broker:
        polling._broker_symbol = None
    else:
        adapter.accounts = (
            account().model_copy(
                update={"server_fingerprint": "mt5-server-v1:changed"}
            ),
        )

    assert polling.run_tick_once() is False
    assert polling.state.health_state is HealthState.BLOCKED
    assert polling.state.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    assert polling.state.reconciliation_required is True
    polling.stop()


def test_position_poll_is_separate_and_changed_set_requires_full() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling.run_once()
    report_count = len(store.reports)
    adapter.call_log.clear()

    assert polling.run_position_once() is True
    assert adapter.call_log == ["get_open_positions", "get_active_orders"]
    assert len(store.reports) == report_count
    assert polling.state.reconciliation_required is False

    adapter.positions = (position(),)
    assert polling.run_position_once() is False
    assert polling.state.reconciliation_required is True
    assert polling.state.health_state is HealthState.BLOCKED
    assert polling.state.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    assert len(store.reports) == report_count
    polling.stop()


def test_startup_and_periodic_due_cycles_run_full_only_at_full_cadence() -> None:
    timeline = [0.0]
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(
        adapter,
        store,
        reconciler,
        monotonic_clock=lambda: timeline[0],
    )

    assert polling.run_due_once() == "full"
    assert len(store.reports) == 1
    assert adapter.call_log.count("get_order_history") == 1
    timeline[0] = 59.0
    assert polling.run_due_once() == "tick"
    assert len(store.reports) == 1
    timeline[0] = 60.0
    assert polling.run_due_once() == "full"
    assert len(store.reports) == 2
    assert adapter.call_log.count("get_order_history") == 2
    polling.stop()


def test_reconnect_requires_full_reconciliation_before_healthy_returns() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling.run_once()
    assert polling.state.health_state is HealthState.HEALTHY

    adapter.failures["get_terminal_info"] = Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE
    with pytest.raises(Mt5ReadFailure) as raised:
        polling.run_tick_once()
    polling._handle_failure(raised.value, "reconnect-failure")
    assert polling.state.connected is False
    assert polling.state.reconciliation_required is True
    assert polling.state.health_state is HealthState.UNAVAILABLE
    assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.WORKER].detail is (
        Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].detail is (
        Mt5ReasonCode.TICK_UNAVAILABLE
    )

    adapter.failures.clear()
    assert polling.run_due_once() == "full"
    assert polling.state.reconciliation_required is False
    assert polling.state.health_state is HealthState.HEALTHY
    polling.stop()


def test_terminal_disconnect_publishes_exact_component_failures() -> None:
    adapter = fake_adapter()
    adapter.replace_terminal(terminal().model_copy(update={"connected": False}))
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    with pytest.raises(Mt5ReadFailure) as raised:
        polling.run_once()
    assert raised.value.error.reason_code is Mt5ReasonCode.TERMINAL_DISCONNECTED
    polling._handle_failure(raised.value, "terminal-disconnected")

    assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.WORKER].detail is (
        Mt5ReasonCode.TERMINAL_DISCONNECTED
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].detail is (
        Mt5ReasonCode.TERMINAL_DISCONNECTED
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].detail is (
        Mt5ReasonCode.TICK_UNAVAILABLE
    )
    polling.stop()


def test_account_binding_mismatch_publishes_exact_component_failures() -> None:
    adapter = fake_adapter()
    adapter.accounts = (
        account().model_copy(
            update={"account_fingerprint": "mt5-account-v1:unexpected"}
        ),
    )
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    result = polling.run_once()

    assert result.health.reason_code is Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH
    assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.WORKER].detail is (
        Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].detail is (
        Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].detail is (
        Mt5ReasonCode.TICK_UNAVAILABLE
    )
    polling.stop()


def test_symbol_canonical_mismatch_publishes_exact_component_failures() -> None:
    adapter = fake_adapter()
    adapter.specifications["XAUUSD"] = specification().model_copy(
        update={"base_currency": "EUR"}
    )
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    with pytest.raises(Mt5ReadFailure) as raised:
        polling.run_once()
    assert raised.value.error.reason_code is Mt5ReasonCode.SYMBOL_CANONICAL_MISMATCH
    polling._handle_failure(raised.value, "symbol-canonical-mismatch")

    assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.WORKER].detail is (
        Mt5ReasonCode.SYMBOL_CANONICAL_MISMATCH
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].detail is (
        Mt5ReasonCode.SYMBOL_CANONICAL_MISMATCH
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].detail is (
        Mt5ReasonCode.TICK_UNAVAILABLE
    )
    polling.stop()


def test_disconnect_failure_cannot_replace_original_polling_failure() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    original = Mt5ReadFailure(
        SafeMt5Error(
            reason_code=Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE,
            safe_detail="Terminal observation is unavailable.",
            retryable=True,
        )
    )
    adapter.failures["disconnect"] = Mt5ReasonCode.NATIVE_ACCESS_CONFLICT

    polling._handle_failure(original, "disconnect-cleanup-failure")

    assert polling.state.reason_code is Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE
    assert store.heartbeats[Mt5ComponentCode.WORKER].detail is (
        Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].detail is (
        Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE
    )
    assert store.incidents[-1][0] is Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE
    assert all("native" not in incident[3].lower() for incident in store.incidents)

    adapter.failures.clear()
    polling.stop()


def test_polling_backoff_is_bounded_and_resets_after_verified_cycle() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling._attempt = 20
    assert polling._backoff() == Decimal("4")
    result = polling.run_once()
    assert result.health.state is HealthState.HEALTHY
    assert polling.state.reconnect_attempt == 0
    assert polling.state.reconciliation_required is False
    assert polling.state.last_successful_observation_at == NOW
    polling.stop()
    with pytest.raises(RuntimeError):
        polling.run_once()


def test_polling_start_stop_is_cancellable_and_leaves_no_thread() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    started = monotonic()
    polling.start()
    polling.stop(timeout_seconds=2)
    assert monotonic() - started < 2
    assert polling.state.running is False
    assert polling.state.connected is False
    calls_after_stop = len(adapter.call_log)
    assert len(adapter.call_log) == calls_after_stop


@pytest.mark.parametrize("entrypoint", ["run_once", "run_due_once"])
def test_never_started_manual_cycle_cannot_publish_worker_healthy(
    entrypoint: str,
) -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    if entrypoint == "run_once":
        assert polling.run_once().health.state is HealthState.HEALTHY
    else:
        assert polling.run_due_once() == "full"

    assert polling.state.running is False
    assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.WORKER].detail is (
        Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.HEALTHY
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
        ComponentHeartbeatState.HEALTHY
    )
    polling.stop()


def test_started_poller_can_publish_worker_healthy_only_while_running() -> None:
    adapter = fake_adapter()
    store = LifecycleHeartbeatPersistence(confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    store.running_probe = lambda: polling.state.running

    polling.start()
    try:
        deadline = monotonic() + 2
        while (
            not any(
                heartbeat.state is ComponentHeartbeatState.HEALTHY
                for heartbeat, _running in store.worker_publications
            )
            and monotonic() < deadline
        ):
            Event().wait(0.025)
        healthy_publications = [
            running
            for heartbeat, running in store.worker_publications
            if heartbeat.state is ComponentHeartbeatState.HEALTHY
        ]
        assert healthy_publications
        assert all(healthy_publications)
        assert polling.state.running is True
        market_before_stop = store.heartbeats[Mt5ComponentCode.MARKET_DATA]
    finally:
        polling.stop(timeout_seconds=2)

    stopped_publication_count = len(store.worker_publications)
    assert polling.state.running is False
    stopped_worker, running_when_stopped = store.worker_publications[-1]
    assert running_when_stopped is False
    assert stopped_worker.state is ComponentHeartbeatState.FAILED
    assert stopped_worker.detail is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].detail is (
        Mt5ReasonCode.TERMINAL_DISCONNECTED
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA] == market_before_stop
    Event().wait(0.05)
    assert len(store.worker_publications) == stopped_publication_count
    with pytest.raises(RuntimeError):
        polling.run_once()
    assert len(store.worker_publications) == stopped_publication_count


def test_final_heartbeat_persistence_failure_cannot_prevent_shutdown() -> None:
    adapter = fake_adapter()
    store = FailFinalHeartbeatPersistence(confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    polling.start()
    deadline = monotonic() + 2
    while (
        not any(
            heartbeat.state is ComponentHeartbeatState.HEALTHY
            for heartbeat, _running in store.worker_publications
        )
        and monotonic() < deadline
    ):
        Event().wait(0.025)
    assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
        ComponentHeartbeatState.HEALTHY
    )

    store.fail_heartbeat_writes = True
    polling.stop(timeout_seconds=2)

    assert polling.state.running is False
    assert polling.state.connected is False
    assert [
        heartbeat.component_code for heartbeat in store.failed_heartbeat_attempts
    ] == [Mt5ComponentCode.MT5_ADAPTER, Mt5ComponentCode.WORKER]


def test_continuous_live_ticks_renew_all_components_without_full_reconciliation() -> (
    None
):
    timeline = [0.0]
    worker_config = Mt5WorkerConfig(
        broker_symbol="XAUUSD",
        expected_account_fingerprint=account().account_fingerprint,
        tick_poll_seconds=Decimal("5"),
        heartbeat_valid_for_seconds=30,
        position_poll_seconds=Decimal("15"),
        full_reconciliation_seconds=Decimal("600"),
    )
    adapter = fake_adapter()
    store = RecordingHeartbeatPersistence(confirmed_state())
    reconciler, _ = service(
        adapter=adapter,
        persistence=store,
        worker_config=worker_config,
    )
    polling = poller(
        adapter,
        store,
        reconciler,
        worker_config=worker_config,
        clock=lambda: NOW + timedelta(seconds=timeline[0]),
        monotonic_clock=lambda: timeline[0],
    )

    assert polling.run_due_once() == "full"
    assert set(store.heartbeats) == set(Mt5ComponentCode)
    for current_second in range(5, 61, 5):
        timeline[0] = float(current_second)
        current_time = NOW + timedelta(seconds=current_second)
        adapter.replace_tick(
            "XAUUSD",
            tick().model_copy(
                update={
                    "observed_at": current_time,
                    "tick_at": current_time - timedelta(seconds=1),
                }
            ),
        )

        assert polling.run_due_once() == "tick"
        assert set(store.heartbeats) == set(Mt5ComponentCode)
        assert all(
            heartbeat.observed_at == current_time
            and heartbeat.observed_at + timedelta(seconds=heartbeat.valid_for_seconds)
            > current_time
            for heartbeat in store.heartbeats.values()
        )

    assert len(store.heartbeat_history) == 3 + (12 * 3)
    assert len(store.reports) == 1
    assert adapter.call_log.count("get_order_history") == 1
    assert adapter.call_log.count("get_deal_history") == 1
    polling.stop()


def test_live_ticks_preserve_blocked_and_degraded_authoritative_worker_caps() -> None:
    blocked_adapter = fake_adapter()
    blocked_adapter.failures["get_order_history"] = Mt5ReasonCode.HISTORY_QUERY_FAILED
    blocked_store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    blocked_reconciler, _ = service(
        adapter=blocked_adapter,
        persistence=blocked_store,
    )
    blocked_poller = poller(
        blocked_adapter,
        blocked_store,
        blocked_reconciler,
    )

    blocked_poller.start()
    try:
        deadline = monotonic() + 2
        while (
            blocked_poller.state.health_state is not HealthState.BLOCKED
            and monotonic() < deadline
        ):
            Event().wait(0.025)
        assert blocked_poller.state.health_state is HealthState.BLOCKED
        blocked_adapter.call_log.clear()
        assert blocked_poller.run_tick_once() is True
        assert blocked_store.heartbeats[Mt5ComponentCode.WORKER].state is (
            ComponentHeartbeatState.FAILED
        )
        assert blocked_store.heartbeats[Mt5ComponentCode.WORKER].detail is (
            Mt5ReasonCode.HISTORY_QUERY_FAILED
        )
        assert blocked_store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
            ComponentHeartbeatState.HEALTHY
        )
        assert "get_order_history" not in blocked_adapter.call_log
        assert "get_deal_history" not in blocked_adapter.call_log
    finally:
        blocked_poller.stop(timeout_seconds=2)

    degraded_config = config(bound=False)
    degraded_adapter = fake_adapter()
    degraded_store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    degraded_reconciler, _ = service(
        adapter=degraded_adapter,
        persistence=degraded_store,
        worker_config=degraded_config,
    )
    degraded_poller = poller(
        degraded_adapter,
        degraded_store,
        degraded_reconciler,
        worker_config=degraded_config,
    )

    degraded_poller.start()
    try:
        deadline = monotonic() + 2
        while (
            degraded_poller.state.health_state is not HealthState.DEGRADED
            and monotonic() < deadline
        ):
            Event().wait(0.025)
        assert degraded_poller.state.health_state is HealthState.DEGRADED
        assert degraded_poller.run_tick_once() is True
        assert degraded_store.heartbeats[Mt5ComponentCode.WORKER].state is (
            ComponentHeartbeatState.DEGRADED
        )
        assert degraded_store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
            ComponentHeartbeatState.DEGRADED
        )
        assert degraded_store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
            ComponentHeartbeatState.HEALTHY
        )
    finally:
        degraded_poller.stop(timeout_seconds=2)


def test_live_tick_after_delayed_full_keeps_degraded_cap_until_reconciliation() -> None:
    adapter = fake_adapter(freshness=TickFreshness.DELAYED)
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    polling.start()
    try:
        deadline = monotonic() + 2
        while (
            polling.state.health_state is not HealthState.DEGRADED
            and monotonic() < deadline
        ):
            Event().wait(0.025)
        assert polling.state.health_state is HealthState.DEGRADED
        assert polling.state.reason_code is Mt5ReasonCode.TICK_DELAYED
        assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
            ComponentHeartbeatState.DEGRADED
        )
        assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
            ComponentHeartbeatState.DEGRADED
        )

        adapter.replace_tick("XAUUSD", tick(TickFreshness.LIVE))
        adapter.call_log.clear()
        assert polling.run_tick_once() is True
        assert polling.state.reconciliation_required is True
        assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
            ComponentHeartbeatState.DEGRADED
        )
        assert store.heartbeats[Mt5ComponentCode.WORKER].detail is (
            Mt5ReasonCode.TICK_DELAYED
        )
        assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
            ComponentHeartbeatState.HEALTHY
        )
        assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
            ComponentHeartbeatState.HEALTHY
        )
        assert "get_order_history" not in adapter.call_log
        assert "get_deal_history" not in adapter.call_log
    finally:
        polling.stop(timeout_seconds=2)


def test_reconciliation_required_caps_worker_until_a_new_full_cycle() -> None:
    adapter = fake_adapter()
    store = RecordingHeartbeatPersistence(confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    polling.start()
    try:
        deadline = monotonic() + 2
        while (
            store.heartbeats.get(Mt5ComponentCode.WORKER) is None
            and monotonic() < deadline
        ):
            Event().wait(0.025)
        assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
            ComponentHeartbeatState.HEALTHY
        )

        polling.request_full_reconciliation()
        assert polling.run_tick_once() is True
        assert polling.state.reconciliation_required is True
        assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
            ComponentHeartbeatState.FAILED
        )
        assert store.heartbeats[Mt5ComponentCode.WORKER].detail is (
            Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        )
        assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].state is (
            ComponentHeartbeatState.HEALTHY
        )

        heartbeat_count = len(store.heartbeat_history)
        assert polling.run_position_once() is True
        assert polling.state.reconciliation_required is True
        assert len(store.heartbeat_history) == heartbeat_count + 2
        assert store.heartbeat_history[-2].component_code is (
            Mt5ComponentCode.MT5_ADAPTER
        )
        assert store.heartbeat_history[-1].component_code is Mt5ComponentCode.WORKER

        assert polling.run_once().health.state is HealthState.HEALTHY
        assert polling.state.reconciliation_required is False
        assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
            ComponentHeartbeatState.HEALTHY
        )
    finally:
        polling.stop(timeout_seconds=2)


@pytest.mark.parametrize(
    ("freshness", "expected_state", "expected_detail"),
    [
        (
            TickFreshness.LIVE,
            ComponentHeartbeatState.HEALTHY,
            Mt5ReasonCode.HEALTHY,
        ),
        (
            TickFreshness.DELAYED,
            ComponentHeartbeatState.DEGRADED,
            Mt5ReasonCode.TICK_DELAYED,
        ),
        (
            TickFreshness.STALE,
            ComponentHeartbeatState.FAILED,
            Mt5ReasonCode.TICK_STALE,
        ),
        (
            TickFreshness.FUTURE_INVALID,
            ComponentHeartbeatState.FAILED,
            Mt5ReasonCode.TICK_FROM_FUTURE,
        ),
        (
            TickFreshness.UNAVAILABLE,
            ComponentHeartbeatState.FAILED,
            Mt5ReasonCode.TICK_UNAVAILABLE,
        ),
    ],
)
def test_full_and_light_polling_share_exact_market_freshness_policy(
    freshness: TickFreshness,
    expected_state: ComponentHeartbeatState,
    expected_detail: Mt5ReasonCode,
) -> None:
    full_adapter = fake_adapter(freshness=freshness)
    full_store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    full_reconciler, _ = service(adapter=full_adapter, persistence=full_store)
    full_poller = poller(full_adapter, full_store, full_reconciler)
    full_poller.run_once()

    light_adapter = fake_adapter()
    light_store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    light_reconciler, _ = service(adapter=light_adapter, persistence=light_store)
    light_poller = poller(light_adapter, light_store, light_reconciler)
    light_poller.run_once()
    light_adapter.replace_tick("XAUUSD", tick(freshness))
    light_poller.run_tick_once()

    for heartbeat in (
        full_store.heartbeats[Mt5ComponentCode.MARKET_DATA],
        light_store.heartbeats[Mt5ComponentCode.MARKET_DATA],
    ):
        assert heartbeat.state is expected_state
        assert heartbeat.detail is expected_detail

    full_poller.stop()
    light_poller.stop()


def test_database_heartbeat_failure_is_bounded_and_fails_local_state_closed() -> None:
    adapter = fake_adapter()
    store = FailFirstHeartbeatBatchPersistence(confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)

    with pytest.raises(Mt5ReadFailure) as raised:
        polling.run_once()
    assert raised.value.error.reason_code is Mt5ReasonCode.DATABASE_REPORT_FAILED

    polling._handle_failure(raised.value, "database-heartbeat-failure")

    assert len(store.heartbeat_attempts) == 6
    assert set(store.heartbeats) == set(Mt5ComponentCode)
    assert store.heartbeats[Mt5ComponentCode.WORKER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MT5_ADAPTER].state is (
        ComponentHeartbeatState.FAILED
    )
    assert store.heartbeats[Mt5ComponentCode.MARKET_DATA].detail is (
        Mt5ReasonCode.TICK_UNAVAILABLE
    )
    assert polling.state.health_state is HealthState.UNAVAILABLE
    assert polling.state.reconciliation_required is True
    assert store.incidents
    assert len(store.incidents) == 1
    assert all("unavailable" in incident[3].lower() for incident in store.incidents)
    assert not {
        "order_send",
        "order_check",
        "order_calc_profit",
        "order_calc_margin",
        "login",
        "symbol_select",
    }.intersection(adapter.call_log)
    polling.stop()


def test_generic_heartbeat_transport_failure_is_bounded_and_thread_safe() -> None:
    sentinel = r"credential=secret-token C:\Users\private\terminal.ini"
    client = DownHeartbeatTransportClient(sentinel)
    heartbeat_persistence = WorkerRpcMt5ObservationPersistence(client)
    adapter = fake_adapter()
    reconciliation_store = InMemoryMt5ObservationPersistence(
        database_state=confirmed_state()
    )
    reconciler, _ = service(
        adapter=adapter,
        persistence=reconciliation_store,
    )
    polling = ReadOnlyPollingService(
        adapter,
        heartbeat_persistence,
        reconciler,
        config(),
        clock=lambda: NOW,
        jitter=lambda _attempt: Decimal("0.25"),
        trace_factory=lambda: "generic-transport-failure",
    )

    polling.start()
    try:
        deadline = monotonic() + 1
        while (
            not any(
                function == "worker_record_incident" for function, _ in client.calls
            )
            and monotonic() < deadline
        ):
            Event().wait(0.025)

        calls = list(client.calls)
        heartbeat_calls = [
            parameters
            for function, parameters in calls
            if function == "worker_record_heartbeat"
        ]
        incident_calls = [
            parameters
            for function, parameters in calls
            if function == "worker_record_incident"
        ]
        assert len(heartbeat_calls) == 6
        assert len(incident_calls) == 1
        expected_components = [
            Mt5ComponentCode.MT5_ADAPTER.value,
            Mt5ComponentCode.MARKET_DATA.value,
            Mt5ComponentCode.WORKER.value,
        ]
        assert [
            call["component_code"] for call in heartbeat_calls[:3]
        ] == expected_components
        assert [
            call["component_code"] for call in heartbeat_calls[3:]
        ] == expected_components
        assert [call["state"] for call in heartbeat_calls[3:]] == [
            ComponentHeartbeatState.FAILED.value,
            ComponentHeartbeatState.FAILED.value,
            ComponentHeartbeatState.FAILED.value,
        ]
        assert [call["detail"] for call in heartbeat_calls[3:]] == [
            Mt5ReasonCode.DATABASE_REPORT_FAILED.value,
            Mt5ReasonCode.TICK_UNAVAILABLE.value,
            Mt5ReasonCode.DATABASE_REPORT_FAILED.value,
        ]
        assert incident_calls[0]["code"] == Mt5ReasonCode.DATABASE_REPORT_FAILED
        assert incident_calls[0]["detail"] == (
            "Worker persistence transport is unavailable."
        )
        assert sentinel not in repr(calls)
        assert polling.state.running is True
        assert polling.state.health_state is HealthState.UNAVAILABLE
        assert polling.state.reason_code is Mt5ReasonCode.DATABASE_REPORT_FAILED
    finally:
        polling.stop(timeout_seconds=2)

    assert polling.state.running is False
