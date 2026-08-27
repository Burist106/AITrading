from __future__ import annotations

from decimal import Decimal
from time import monotonic

import pytest
from mt5_factories import (
    NOW,
    account,
    active_order,
    fake_adapter,
    position,
)

from aurum_worker.adapters.persistence_mt5 import (
    InMemoryMt5ObservationPersistence,
)
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    DatabaseReconciliationState,
    HealthState,
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
        poll_interval_seconds=Decimal("1"),
        reconnect_max_seconds=Decimal("4"),
    )


def service(
    *,
    adapter=None,
    persistence: InMemoryMt5ObservationPersistence | None = None,
    worker_config: Mt5WorkerConfig | None = None,
) -> tuple[ReadOnlyReconciliationService, InMemoryMt5ObservationPersistence]:
    store = persistence or InMemoryMt5ObservationPersistence()
    reconciler = ReadOnlyReconciliationService(
        adapter or fake_adapter(),
        store,
        worker_config or config(),
        clock=lambda: NOW,
        identifier_factory=lambda: "reconciliation-fixture",
    )
    return reconciler, store


def test_clean_reconciliation_is_required_before_healthy() -> None:
    reconciler, store = service()
    result = reconciler.run(trace_id="trace-clean")
    assert result.report.outcome is ReconciliationOutcome.MATCHED
    assert result.health.state is HealthState.HEALTHY
    assert result.health.reconciliation_outcome is ReconciliationOutcome.MATCHED
    assert store.accounts and store.symbols and store.ticks
    assert (
        store.reports["reconciliation-fixture"].outcome is ReconciliationOutcome.MATCHED
    )


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
    assert store.incidents
    assert "get_symbol_specification" not in adapter.call_log


def test_missing_or_ambiguous_symbol_never_auto_binds() -> None:
    adapter = fake_adapter()
    reconciler, _ = service(adapter=adapter, worker_config=config(broker_symbol=None))
    result = reconciler.run(trace_id="trace-symbol")
    assert result.health.reason_code is Mt5ReasonCode.SYMBOL_NOT_CONFIGURED
    assert "get_symbol_specification" not in adapter.call_log

    adapter = fake_adapter()
    adapter.candidates = adapter.candidates + adapter.candidates
    reconciler, _ = service(adapter=adapter, worker_config=config(broker_symbol=None))
    result = reconciler.run(trace_id="trace-ambiguous")
    assert result.health.reason_code is Mt5ReasonCode.SYMBOL_AMBIGUOUS


def test_previously_confirmed_database_symbol_is_reused_without_discovery() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence(
        database_state=DatabaseReconciliationState(broker_symbol="XAUUSD")
    )
    reconciler, _ = service(
        adapter=adapter,
        persistence=store,
        worker_config=config(broker_symbol=None),
    )
    result = reconciler.run(trace_id="trace-confirmed-symbol")
    assert result.health.broker_symbol == "XAUUSD"
    assert "list_symbol_candidates" not in adapter.call_log


def test_position_order_and_execution_uncertainty_mismatches_are_observation_only() -> (
    None
):
    adapter = fake_adapter(positions=(position(),), orders=(active_order(),))
    store = InMemoryMt5ObservationPersistence(
        database_state=DatabaseReconciliationState(
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


def test_account_server_spec_history_and_clock_changes_are_detected() -> None:
    adapter = fake_adapter(freshness=TickFreshness.FUTURE_INVALID)
    store = InMemoryMt5ObservationPersistence(
        database_state=DatabaseReconciliationState(
            account_fingerprint="mt5-account-v1:previous",
            server_fingerprint="mt5-server-v1:previous",
            symbol_specification_fingerprint="mt5-spec-v1:previous",
            history_window_complete=False,
        )
    )
    reconciler, _ = service(adapter=adapter, persistence=store)
    result = reconciler.run(trace_id="trace-changes")
    categories = {mismatch.category for mismatch in result.report.mismatches}
    assert {
        ReconciliationCategory.ACCOUNT_CHANGED,
        ReconciliationCategory.SERVER_CHANGED,
        ReconciliationCategory.SYMBOL_SPEC_CHANGED,
        ReconciliationCategory.HISTORY_WINDOW_INCOMPLETE,
        ReconciliationCategory.CLOCK_INCONSISTENCY,
    }.issubset(categories)


def test_stale_tick_blocks_and_unusable_symbol_cannot_report_healthy() -> None:
    adapter = fake_adapter(freshness=TickFreshness.STALE)
    reconciler, _ = service(adapter=adapter)
    stale = reconciler.run(trace_id="trace-stale")
    assert stale.health.state is HealthState.BLOCKED
    assert stale.health.reason_code is Mt5ReasonCode.TICK_STALE

    adapter = fake_adapter()
    adapter.specifications["XAUUSD"] = adapter.specifications["XAUUSD"].model_copy(
        update={
            "usability_state": SymbolUsabilityState.NOT_VISIBLE,
            "unusable_reason": Mt5ReasonCode.SYMBOL_NOT_VISIBLE,
        }
    )
    reconciler, _ = service(adapter=adapter)
    with pytest.raises(Mt5ReadFailure) as raised:
        reconciler.run(trace_id="trace-unusable-symbol")
    assert raised.value.error.reason_code is Mt5ReasonCode.SYMBOL_NOT_VISIBLE
    assert "Market Watch" in raised.value.error.safe_detail


def test_reconciliation_report_replay_is_idempotent() -> None:
    reconciler, store = service()
    first = reconciler.run(trace_id="same-trace")
    second = reconciler.run(trace_id="same-trace")
    assert first.report.reconciliation_id == second.report.reconciliation_id
    assert len(store.reports) == 1


def test_database_reporting_failure_fails_closed() -> None:
    store = InMemoryMt5ObservationPersistence(fail_operations={"record_account"})
    reconciler, _ = service(persistence=store)
    with pytest.raises(Mt5ReadFailure) as raised:
        reconciler.run(trace_id="trace-db-failure")
    assert raised.value.error.reason_code is Mt5ReasonCode.DATABASE_REPORT_FAILED


def test_polling_backoff_is_bounded_and_resets_after_verified_cycle() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence()
    reconciler, _ = service(adapter=adapter, persistence=store)
    poller = ReadOnlyPollingService(
        adapter,
        store,
        reconciler,
        config(),
        clock=lambda: NOW,
        jitter=lambda _attempt: Decimal("0.25"),
        trace_factory=lambda: "poll-trace",
    )
    poller._attempt = 20
    assert poller._backoff() == Decimal("4")
    result = poller.run_once()
    assert result.health.state is HealthState.HEALTHY
    assert poller.state.reconnect_attempt == 0
    assert poller.state.reconciliation_required is False
    assert poller.state.last_successful_observation_at == NOW
    poller.stop()
    with pytest.raises(RuntimeError):
        poller.run_once()


def test_polling_start_stop_is_cancellable_and_leaves_no_thread() -> None:
    adapter = fake_adapter()
    store = InMemoryMt5ObservationPersistence()
    reconciler, _ = service(adapter=adapter, persistence=store)
    poller = ReadOnlyPollingService(
        adapter,
        store,
        reconciler,
        config(),
        clock=lambda: NOW,
        trace_factory=lambda: "poll-thread-trace",
    )
    started = monotonic()
    poller.start()
    poller.stop(timeout_seconds=2)
    assert monotonic() - started < 2
    assert poller.state.running is False
    assert poller.state.connected is False
    calls_after_stop = len(adapter.call_log)
    assert len(adapter.call_log) == calls_after_stop
