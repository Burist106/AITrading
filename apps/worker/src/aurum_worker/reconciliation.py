"""Observation-only restart and reconnect reconciliation service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from aurum_worker.adapters.protocols import (
    Mt5ObservationPersistencePort,
    Mt5ReadPort,
)
from aurum_worker.models.mt5 import (
    AccountVerificationState,
    DatabaseReconciliationState,
    HealthState,
    HistoryRequest,
    Mt5HealthSnapshot,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReconciliationCategory,
    ReconciliationMismatch,
    ReconciliationOutcome,
    ReconciliationReport,
    SafeMt5Error,
    SymbolUsabilityState,
    TickFreshness,
)
from aurum_worker.mt5_safety import verify_account


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    report: ReconciliationReport
    health: Mt5HealthSnapshot


class ReadOnlyReconciliationService:
    """Compares broker observations with persistence without mutating operations."""

    def __init__(
        self,
        adapter: Mt5ReadPort,
        persistence: Mt5ObservationPersistencePort,
        config: Mt5WorkerConfig,
        *,
        clock: Callable[[], datetime] | None = None,
        identifier_factory: Callable[[], str] | None = None,
    ) -> None:
        self._adapter = adapter
        self._persistence = persistence
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))
        self._identifier_factory = identifier_factory or (lambda: str(uuid4()))

    def _report(
        self,
        *,
        reconciliation_id: str,
        trace_id: str,
        started_at: datetime,
        outcome: ReconciliationOutcome,
        reason: Mt5ReasonCode,
        mismatches: tuple[ReconciliationMismatch, ...] = (),
        account_fingerprint: str | None = None,
        server_fingerprint: str | None = None,
        symbol_fingerprint: str | None = None,
        positions: int = 0,
        orders: int = 0,
        order_history: int = 0,
        deal_history: int = 0,
    ) -> ReconciliationReport:
        return ReconciliationReport(
            observed_at=self._clock(),
            source="mt5",
            adapter_version="aurum-reconciliation-v1",
            trace_id=trace_id,
            reconciliation_id=reconciliation_id,
            started_at=started_at,
            completed_at=self._clock(),
            outcome=outcome,
            reason_code=reason,
            account_fingerprint=account_fingerprint,
            server_fingerprint=server_fingerprint,
            symbol_specification_fingerprint=symbol_fingerprint,
            open_position_count=positions,
            active_order_count=orders,
            order_history_count=order_history,
            deal_history_count=deal_history,
            mismatches=mismatches,
        )

    def _persist_report(self, report: ReconciliationReport) -> None:
        self._persistence.begin_reconciliation(report)
        for mismatch in report.mismatches:
            self._persistence.record_mismatch(report.reconciliation_id, mismatch)
            self._persistence.record_incident(
                mismatch.category.value,
                mismatch.severity,
                "MT5 reconciliation mismatch",
                f"{mismatch.category}: {mismatch.resource_type}",
                report.trace_id,
                report.completed_at,
            )
        self._persistence.complete_reconciliation(report)

    def _health(
        self,
        *,
        trace_id: str,
        state: HealthState,
        reason: Mt5ReasonCode,
        terminal_version: str | None = None,
        verification_state: AccountVerificationState | None = None,
        masked_account: str | None = None,
        masked_server: str | None = None,
        broker_symbol: str | None = None,
        specification_fingerprint: str | None = None,
        tick_age: Decimal | None = None,
        reconciliation_outcome: ReconciliationOutcome | None = None,
        positions: int | None = None,
        orders: int | None = None,
    ) -> Mt5HealthSnapshot:
        now = self._clock()
        return Mt5HealthSnapshot(
            observed_at=now,
            source="mt5",
            adapter_version="aurum-reconciliation-v1",
            trace_id=trace_id,
            state=state,
            reason_code=reason,
            package_available=reason is not Mt5ReasonCode.MT5_PACKAGE_NOT_INSTALLED,
            platform="windows",
            terminal_connected=terminal_version is not None,
            terminal_version=terminal_version,
            account_verification_state=verification_state,
            masked_account=masked_account,
            masked_server=masked_server,
            broker_symbol=broker_symbol,
            specification_fingerprint=specification_fingerprint,
            tick_age_seconds=tick_age,
            last_successful_observation_at=(
                now if state in {HealthState.HEALTHY, HealthState.DEGRADED} else None
            ),
            reconciliation_outcome=reconciliation_outcome,
            open_position_count=positions,
            active_order_count=orders,
        )

    def run(self, *, trace_id: str) -> ReconciliationResult:
        started_at = self._clock()
        reconciliation_id = self._identifier_factory()
        terminal = self._adapter.connect(trace_id=trace_id)
        terminal = self._adapter.get_terminal_info(trace_id=trace_id)
        account = self._adapter.get_account_info(trace_id=trace_id)
        verification = verify_account(
            account, self._config.expected_account_fingerprint
        )
        database = self._persistence.load_reconciliation_state()
        self._persistence.record_account(account, verification.state)

        if verification.state not in {
            AccountVerificationState.VERIFIED_DEMO_BOUND,
            AccountVerificationState.VERIFIED_DEMO_UNBOUND,
        }:
            mismatch = ReconciliationMismatch(
                category=ReconciliationCategory.ACCOUNT_CHANGED,
                severity="critical",
                resource_type="account",
                resource_reference=account.account_fingerprint,
                reason_code=verification.reason_code,
            )
            report = self._report(
                reconciliation_id=reconciliation_id,
                trace_id=trace_id,
                started_at=started_at,
                outcome=ReconciliationOutcome.INCOMPLETE,
                reason=verification.reason_code,
                mismatches=(mismatch,),
                account_fingerprint=account.account_fingerprint,
                server_fingerprint=account.server_fingerprint,
            )
            self._persist_report(report)
            health = self._health(
                trace_id=trace_id,
                state=verification.health_state,
                reason=verification.reason_code,
                terminal_version=terminal.terminal_version,
                verification_state=verification.state,
                masked_account=account.masked_login,
                masked_server=account.masked_server,
                reconciliation_outcome=report.outcome,
            )
            self._persistence.record_heartbeat(health)
            return ReconciliationResult(report=report, health=health)

        broker_symbol = self._config.broker_symbol or database.broker_symbol
        if broker_symbol is None:
            reason = Mt5ReasonCode.SYMBOL_NOT_CONFIGURED
            candidates = self._adapter.list_symbol_candidates(trace_id=trace_id)
            if len(candidates) > 1:
                reason = Mt5ReasonCode.SYMBOL_AMBIGUOUS
            report = self._report(
                reconciliation_id=reconciliation_id,
                trace_id=trace_id,
                started_at=started_at,
                outcome=ReconciliationOutcome.INCOMPLETE,
                reason=reason,
                account_fingerprint=account.account_fingerprint,
                server_fingerprint=account.server_fingerprint,
            )
            self._persist_report(report)
            health = self._health(
                trace_id=trace_id,
                state=HealthState.BLOCKED,
                reason=reason,
                terminal_version=terminal.terminal_version,
                verification_state=verification.state,
                masked_account=account.masked_login,
                masked_server=account.masked_server,
                reconciliation_outcome=report.outcome,
            )
            self._persistence.record_heartbeat(health)
            return ReconciliationResult(report=report, health=health)

        specification = self._adapter.get_symbol_specification(
            broker_symbol, trace_id=trace_id
        )
        if specification.usability_state is not SymbolUsabilityState.USABLE:
            detail = "Configured broker symbol is not usable for read-only observation."
            if specification.usability_state is SymbolUsabilityState.NOT_VISIBLE:
                detail = (
                    "Configured broker symbol must be made visible manually in "
                    "Market Watch."
                )
            raise Mt5ReadFailure(
                error=self._safe_error(
                    specification.unusable_reason
                    or Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE,
                    detail,
                )
            )
        tick = self._adapter.get_latest_tick(broker_symbol, trace_id=trace_id)
        positions = self._adapter.get_open_positions(trace_id=trace_id)
        orders = self._adapter.get_active_orders(trace_id=trace_id)
        history_request = HistoryRequest(
            start_at=self._clock() - timedelta(hours=self._config.history_window_hours),
            end_at=self._clock(),
        )
        order_history = self._adapter.get_order_history(
            history_request, trace_id=trace_id
        )
        deal_history = self._adapter.get_deal_history(
            history_request, trace_id=trace_id
        )
        self._persistence.record_symbol(specification, account.account_fingerprint)
        self._persistence.upsert_tick(tick, account.account_fingerprint)

        mismatches = self._mismatches(
            account=account,
            specification_fingerprint=specification.specification_fingerprint,
            tick_freshness=tick.freshness,
            broker_positions={position.ticket for position in positions},
            broker_orders={order.ticket for order in orders},
            database=database,
        )
        outcome = (
            ReconciliationOutcome.MATCHED
            if not mismatches
            else ReconciliationOutcome.MISMATCH
        )
        reason = (
            Mt5ReasonCode.HEALTHY
            if outcome is ReconciliationOutcome.MATCHED
            else Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        )
        report = self._report(
            reconciliation_id=reconciliation_id,
            trace_id=trace_id,
            started_at=started_at,
            outcome=outcome,
            reason=reason,
            mismatches=mismatches,
            account_fingerprint=account.account_fingerprint,
            server_fingerprint=account.server_fingerprint,
            symbol_fingerprint=specification.specification_fingerprint,
            positions=len(positions),
            orders=len(orders),
            order_history=len(order_history),
            deal_history=len(deal_history),
        )
        self._persist_report(report)

        health_state = HealthState.HEALTHY
        health_reason = Mt5ReasonCode.HEALTHY
        if outcome is not ReconciliationOutcome.MATCHED:
            health_state = HealthState.BLOCKED
            health_reason = Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        elif tick.freshness is TickFreshness.STALE:
            health_state = HealthState.BLOCKED
            health_reason = Mt5ReasonCode.TICK_STALE
        elif tick.freshness is TickFreshness.FUTURE_INVALID:
            health_state = HealthState.BLOCKED
            health_reason = Mt5ReasonCode.TICK_FROM_FUTURE
        elif tick.freshness is not TickFreshness.LIVE:
            health_state = HealthState.DEGRADED
            health_reason = Mt5ReasonCode.TICK_STALE
        elif verification.state is AccountVerificationState.VERIFIED_DEMO_UNBOUND:
            health_state = HealthState.DEGRADED
            health_reason = Mt5ReasonCode.DEMO_ACCOUNT_UNBOUND

        health = self._health(
            trace_id=trace_id,
            state=health_state,
            reason=health_reason,
            terminal_version=terminal.terminal_version,
            verification_state=verification.state,
            masked_account=account.masked_login,
            masked_server=account.masked_server,
            broker_symbol=broker_symbol,
            specification_fingerprint=specification.specification_fingerprint,
            tick_age=tick.age_seconds,
            reconciliation_outcome=report.outcome,
            positions=len(positions),
            orders=len(orders),
        )
        self._persistence.record_heartbeat(health)
        return ReconciliationResult(report=report, health=health)

    @staticmethod
    def _safe_error(reason: Mt5ReasonCode, detail: str) -> SafeMt5Error:
        return SafeMt5Error(reason_code=reason, safe_detail=detail)

    @staticmethod
    def _mismatches(
        *,
        account,
        specification_fingerprint: str,
        tick_freshness: TickFreshness,
        broker_positions: set[str],
        broker_orders: set[str],
        database: DatabaseReconciliationState,
    ) -> tuple[ReconciliationMismatch, ...]:
        mismatches: list[ReconciliationMismatch] = []

        def add(
            category: ReconciliationCategory,
            reference: str,
            resource_type: str,
            severity: str = "critical",
        ) -> None:
            mismatches.append(
                ReconciliationMismatch(
                    category=category,
                    severity="critical" if severity == "critical" else "warning",
                    resource_type=resource_type,
                    resource_reference=reference,
                )
            )

        for ticket in sorted(broker_positions - set(database.position_tickets)):
            add(ReconciliationCategory.UNEXPECTED_BROKER_POSITION, ticket, "position")
        for ticket in sorted(set(database.position_tickets) - broker_positions):
            add(
                ReconciliationCategory.DATABASE_POSITION_MISSING_AT_BROKER,
                ticket,
                "position",
            )
        for ticket in sorted(broker_orders - set(database.active_order_tickets)):
            add(ReconciliationCategory.UNEXPECTED_ACTIVE_ORDER, ticket, "order")
        for ticket in sorted(set(database.active_order_tickets) - broker_orders):
            add(
                ReconciliationCategory.DATABASE_ORDER_MISSING_AT_BROKER,
                ticket,
                "order",
            )
        for command_id in sorted(database.executing_command_ids):
            add(
                ReconciliationCategory.EXECUTION_RESULT_UNCERTAIN,
                command_id,
                "system_command",
            )
        if (
            database.account_fingerprint
            and database.account_fingerprint != account.account_fingerprint
        ):
            add(
                ReconciliationCategory.ACCOUNT_CHANGED,
                account.account_fingerprint,
                "account",
            )
        if (
            database.server_fingerprint
            and database.server_fingerprint != account.server_fingerprint
        ):
            add(
                ReconciliationCategory.SERVER_CHANGED,
                account.server_fingerprint,
                "server",
            )
        if (
            database.symbol_specification_fingerprint
            and database.symbol_specification_fingerprint != specification_fingerprint
        ):
            add(
                ReconciliationCategory.SYMBOL_SPEC_CHANGED,
                specification_fingerprint,
                "symbol_specification",
            )
        if not database.history_window_complete:
            add(
                ReconciliationCategory.HISTORY_WINDOW_INCOMPLETE,
                "bounded-history-window",
                "history",
            )
        if tick_freshness is TickFreshness.FUTURE_INVALID:
            add(
                ReconciliationCategory.CLOCK_INCONSISTENCY,
                "tick-clock",
                "clock",
            )
        return tuple(mismatches)
