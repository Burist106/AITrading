from __future__ import annotations

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
    tick,
)

from aurum_worker.adapters.persistence_mt5 import (
    InMemoryMt5ObservationPersistence,
)
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    DatabaseReconciliationState,
    HealthState,
    HistoryQueryResultState,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReconciliationCategory,
    ReconciliationOutcome,
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
    monotonic_clock=None,
    worker_config: Mt5WorkerConfig | None = None,
) -> ReadOnlyPollingService:
    return ReadOnlyPollingService(
        adapter,
        store,
        reconciler,
        worker_config or config(),
        clock=lambda: NOW,
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
    ("freshness", "reason"),
    [
        (TickFreshness.STALE, Mt5ReasonCode.TICK_STALE),
        (TickFreshness.FUTURE_INVALID, Mt5ReasonCode.TICK_FROM_FUTURE),
        (TickFreshness.DELAYED, Mt5ReasonCode.TICK_STALE),
    ],
)
def test_non_live_short_tick_requires_full_before_health_can_return(
    freshness: TickFreshness, reason: Mt5ReasonCode
) -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling.run_once()
    replacement = tick(freshness)
    adapter.replace_tick("XAUUSD", replacement)

    assert polling.run_tick_once() is False
    assert polling.state.health_state is HealthState.BLOCKED
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


def test_short_tick_account_policy_clears_prior_healthy_immediately() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(database_state=confirmed_state())
    reconciler, _ = service(adapter=adapter, persistence=store)
    polling = poller(adapter, store, reconciler)
    polling.run_once()
    assert polling.state.health_state is HealthState.HEALTHY
    adapter.accounts = (account(AccountTradeMode.REAL),)

    assert polling.run_tick_once() is False
    assert polling.state.health_state is HealthState.BLOCKED
    assert polling.state.reason_code is Mt5ReasonCode.REAL_ACCOUNT_BLOCKED
    assert polling.state.reconciliation_required is True
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

    adapter.failures.clear()
    assert polling.run_due_once() == "full"
    assert polling.state.reconciliation_required is False
    assert polling.state.health_state is HealthState.HEALTHY
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
