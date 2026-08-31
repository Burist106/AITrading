"""Cancellable multi-cadence polling for read-only MT5 observations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from threading import Event, RLock, Thread
from time import monotonic
from uuid import uuid4

from aurum_worker.adapters.protocols import (
    Mt5ObservationPersistencePort,
    Mt5ReadPort,
)
from aurum_worker.models.mt5 import (
    AccountVerificationState,
    HealthState,
    Mt5HealthSnapshot,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReadOnlyPollingState,
    SafeMt5Error,
    TickFreshness,
)
from aurum_worker.mt5_safety import verify_account
from aurum_worker.reconciliation import (
    ReadOnlyReconciliationService,
    ReconciliationResult,
)

_DEMO_VERIFICATION_STATES = frozenset(
    {
        AccountVerificationState.VERIFIED_DEMO_BOUND,
        AccountVerificationState.VERIFIED_DEMO_UNBOUND,
    }
)
_KNOWN_BROKER_GAP_REASONS = frozenset(
    {
        Mt5ReasonCode.SYMBOL_AMBIGUOUS,
        Mt5ReasonCode.SYMBOL_NOT_CONFIGURED,
        Mt5ReasonCode.SYMBOL_SPEC_CONFIRMATION_REQUIRED,
    }
)


class ReadOnlyPollingService:
    """Runs light telemetry separately from bounded full reconciliation."""

    def __init__(
        self,
        adapter: Mt5ReadPort,
        persistence: Mt5ObservationPersistencePort,
        reconciliation: ReadOnlyReconciliationService,
        config: Mt5WorkerConfig,
        *,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        jitter: Callable[[int], Decimal] | None = None,
        trace_factory: Callable[[], str] | None = None,
    ) -> None:
        self._adapter = adapter
        self._persistence = persistence
        self._reconciliation = reconciliation
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic_clock or monotonic
        self._jitter = jitter or (lambda _attempt: Decimal("0"))
        self._trace_factory = trace_factory or (lambda: str(uuid4()))
        self._cancel = Event()
        self._lock = RLock()
        self._thread: Thread | None = None
        self._running = False
        self._shutdown = False
        self._connected = False
        self._attempt = 0
        self._next_reconnect = Decimal("0")
        self._last_success: datetime | None = None
        self._reconciliation_required = True
        self._health_state: HealthState | None = None
        self._reason_code: Mt5ReasonCode | None = None
        self._account_fingerprint: str | None = None
        self._server_fingerprint: str | None = None
        self._account_verification_state: AccountVerificationState | None = None
        self._broker_symbol: str | None = None
        self._last_tick_freshness: TickFreshness | None = None
        self._position_tickets: frozenset[str] = frozenset()
        self._active_order_tickets: frozenset[str] = frozenset()
        self._next_tick_at = 0.0
        self._next_position_at = 0.0
        self._next_full_at = 0.0

    @property
    def state(self) -> ReadOnlyPollingState:
        with self._lock:
            return ReadOnlyPollingState(
                running=self._running,
                connected=self._connected,
                reconnect_attempt=self._attempt,
                next_reconnect_seconds=self._next_reconnect,
                last_successful_observation_at=self._last_success,
                reconciliation_required=self._reconciliation_required,
                health_state=self._health_state,
                reason_code=self._reason_code,
                stopped_at=self._clock() if self._shutdown else None,
            )

    def start(self) -> None:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Polling service cannot restart after shutdown.")
            if self._running:
                return
            self._running = True
            self._reconciliation_required = True
            self._cancel.clear()
            self._thread = Thread(
                target=self._run,
                name="aurum-mt5-readonly-poller",
                daemon=False,
            )
            self._thread.start()

    def stop(self, timeout_seconds: float = 10.0) -> None:
        with self._lock:
            self._cancel.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout_seconds)
            if thread.is_alive():
                raise RuntimeError("Polling service did not stop within the timeout.")
        with self._lock:
            self._adapter.disconnect()
            self._connected = False
            self._running = False
            self._shutdown = True
            self._reconciliation_required = True
            self._next_reconnect = Decimal("0")
            self._thread = None

    def _backoff(self) -> Decimal:
        base = min(
            Decimal(2) ** max(self._attempt - 1, 0),
            self._config.reconnect_max_seconds,
        )
        jitter = self._jitter(self._attempt)
        if jitter < 0:
            jitter = Decimal("0")
        return min(base + jitter, self._config.reconnect_max_seconds)

    def _ensure_active(self) -> None:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("No MT5 API call is allowed after polling shutdown.")

    def _accept_full_result(self, result: ReconciliationResult) -> None:
        with self._lock:
            self._connected = result.health.terminal_connected
            self._reconciliation_required = False
            self._health_state = result.health.state
            self._reason_code = result.health.reason_code
            self._account_fingerprint = result.report.account_fingerprint
            self._server_fingerprint = result.report.server_fingerprint
            self._account_verification_state = result.health.account_verification_state
            self._broker_symbol = result.health.broker_symbol
            self._last_tick_freshness = result.tick_freshness
            self._position_tickets = result.position_tickets
            self._active_order_tickets = result.active_order_tickets
            if result.health.last_successful_observation_at is not None:
                self._last_success = result.health.last_successful_observation_at
            if (
                result.health.terminal_connected
                and result.health.account_verification_state
                is AccountVerificationState.VERIFIED_DEMO_BOUND
            ):
                self._attempt = 0
                self._next_reconnect = Decimal("0")

    def _schedule_after_full(self) -> None:
        now = self._monotonic()
        with self._lock:
            self._next_tick_at = now + float(self._config.tick_poll_seconds)
            self._next_position_at = now + float(self._config.position_poll_seconds)
            self._next_full_at = now + float(self._config.full_reconciliation_seconds)

    def run_once(self) -> ReconciliationResult:
        """Run one full reconciliation, used for startup and reconnect."""

        self._ensure_active()
        result = self._reconciliation.run(trace_id=self._trace_factory())
        self._accept_full_result(result)
        self._schedule_after_full()
        return result

    def request_full_reconciliation(self) -> None:
        """Mark the next cycle as full without performing broker writes."""

        with self._lock:
            self._reconciliation_required = True

    def run_tick_once(self) -> bool:
        """Read only terminal/account/tick state; never query history."""

        self._ensure_active()
        trace_id = self._trace_factory()
        terminal = self._adapter.get_terminal_info(trace_id=trace_id)
        if not terminal.connected:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.TERMINAL_DISCONNECTED,
                    safe_detail="Terminal reported a disconnected state.",
                    retryable=True,
                )
            )
        account = self._adapter.get_account_info(trace_id=trace_id)
        verification = verify_account(
            account, self._config.expected_account_fingerprint
        )
        with self._lock:
            account_changed = (
                self._account_fingerprint is None
                or self._server_fingerprint is None
                or account.account_fingerprint != self._account_fingerprint
                or account.server_fingerprint != self._server_fingerprint
            )
            broker_symbol = self._broker_symbol
            verification_changed = (
                self._account_verification_state is None
                or verification.state is not self._account_verification_state
            )
            prior_health_state = self._health_state
            prior_reason = self._reason_code
        if account_changed or verification_changed:
            with self._lock:
                self._health_state = (
                    verification.health_state
                    if verification.state not in _DEMO_VERIFICATION_STATES
                    else HealthState.BLOCKED
                )
                self._reason_code = (
                    verification.reason_code
                    if verification.state not in _DEMO_VERIFICATION_STATES
                    else Mt5ReasonCode.RECONCILIATION_INCOMPLETE
                )
                self._reconciliation_required = True
            return False
        if verification.state not in _DEMO_VERIFICATION_STATES:
            with self._lock:
                self._health_state = verification.health_state
                self._reason_code = verification.reason_code
            return False
        if broker_symbol is None:
            with self._lock:
                if (
                    prior_health_state is HealthState.HEALTHY
                    or prior_reason not in _KNOWN_BROKER_GAP_REASONS
                ):
                    self._health_state = HealthState.BLOCKED
                    self._reason_code = Mt5ReasonCode.RECONCILIATION_INCOMPLETE
                    self._reconciliation_required = True
            return False
        tick = self._adapter.get_latest_tick(broker_symbol, trace_id=trace_id)
        self._persistence.upsert_tick(tick, account.account_fingerprint)
        with self._lock:
            prior_tick_freshness = self._last_tick_freshness
            self._last_tick_freshness = tick.freshness
            if tick.freshness is not TickFreshness.LIVE:
                self._health_state = HealthState.BLOCKED
                self._reason_code = (
                    Mt5ReasonCode.TICK_FROM_FUTURE
                    if tick.freshness is TickFreshness.FUTURE_INVALID
                    else Mt5ReasonCode.TICK_STALE
                )
                if tick.freshness is not prior_tick_freshness:
                    self._reconciliation_required = True
                return False
            self._last_success = tick.observed_at
            if (
                prior_tick_freshness is not None
                and prior_tick_freshness is not TickFreshness.LIVE
            ):
                # Recovery is evidence for a new full cycle, never permission to
                # restore Healthy from the lightweight path.
                self._reconciliation_required = True
        return True

    def run_position_once(self) -> bool:
        """Read current Position/Order sets without history or report creation."""

        self._ensure_active()
        with self._lock:
            if (
                self._account_verification_state not in _DEMO_VERIFICATION_STATES
                or self._broker_symbol is None
            ):
                return True
        trace_id = self._trace_factory()
        positions = self._adapter.get_open_positions(trace_id=trace_id)
        orders = self._adapter.get_active_orders(trace_id=trace_id)
        position_tickets = frozenset(position.ticket for position in positions)
        order_tickets = frozenset(order.ticket for order in orders)
        with self._lock:
            changed = (
                position_tickets != self._position_tickets
                or order_tickets != self._active_order_tickets
            )
            if changed:
                self._reconciliation_required = True
                self._health_state = HealthState.BLOCKED
                self._reason_code = Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        return not changed

    def run_due_once(self) -> str:
        """Run at most one due responsibility for deterministic orchestration tests."""

        self._ensure_active()
        with self._lock:
            reconciliation_required = self._reconciliation_required
        if reconciliation_required:
            self.run_once()
            return "full"
        now = self._monotonic()
        if now >= self._next_full_at:
            self.request_full_reconciliation()
            self.run_once()
            return "full"
        if now >= self._next_tick_at:
            self.run_tick_once()
            self._next_tick_at = now + float(self._config.tick_poll_seconds)
            return "tick"
        if now >= self._next_position_at:
            self.run_position_once()
            self._next_position_at = now + float(self._config.position_poll_seconds)
            return "position"
        return "idle"

    def _record_failure(self, failure: Mt5ReadFailure, trace_id: str) -> None:
        now = self._clock()
        blocked_codes = {
            Mt5ReasonCode.CONTEST_ACCOUNT_BLOCKED,
            Mt5ReasonCode.REAL_ACCOUNT_BLOCKED,
            Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH,
            Mt5ReasonCode.SYMBOL_CANONICAL_MISMATCH,
            Mt5ReasonCode.SYMBOL_SPEC_CONFIRMATION_REQUIRED,
            Mt5ReasonCode.SYMBOL_SPEC_CHANGED,
            Mt5ReasonCode.HISTORY_QUERY_FAILED,
            Mt5ReasonCode.HISTORY_WINDOW_INCOMPLETE,
        }
        snapshot = Mt5HealthSnapshot(
            observed_at=now,
            source="mt5",
            adapter_version="aurum-poller-v1",
            trace_id=trace_id,
            state=(
                HealthState.BLOCKED
                if failure.error.reason_code in blocked_codes
                else HealthState.UNAVAILABLE
            ),
            reason_code=failure.error.reason_code,
            package_available=(
                failure.error.reason_code is not Mt5ReasonCode.MT5_PACKAGE_NOT_INSTALLED
            ),
            platform="windows",
            terminal_connected=False,
            last_successful_observation_at=self._last_success,
        )
        with self._lock:
            self._health_state = snapshot.state
            self._reason_code = snapshot.reason_code
        try:
            self._persistence.record_heartbeat(snapshot)
            self._persistence.record_incident(
                failure.error.reason_code,
                "critical" if snapshot.state is HealthState.BLOCKED else "warning",
                "MT5 read-only polling failure",
                failure.error.safe_detail,
                trace_id,
                snapshot.observed_at,
            )
        except Mt5ReadFailure:
            return

    def _handle_failure(self, failure: Mt5ReadFailure, trace_id: str) -> None:
        self._adapter.disconnect()
        with self._lock:
            self._connected = False
            self._reconciliation_required = True
            self._last_tick_freshness = None
            self._attempt += 1
            self._next_reconnect = self._backoff()
        self._record_failure(failure, trace_id)

    def _wait_for_due_cycle(self) -> bool:
        now = self._monotonic()
        with self._lock:
            deadline = min(
                self._next_tick_at,
                self._next_position_at,
                self._next_full_at,
            )
        return self._cancel.wait(max(0.0, deadline - now))

    def _run(self) -> None:
        try:
            while not self._cancel.is_set():
                with self._lock:
                    reconciliation_required = self._reconciliation_required
                if reconciliation_required:
                    trace_id = self._trace_factory()
                    try:
                        result = self._reconciliation.run(trace_id=trace_id)
                    except Mt5ReadFailure as failure:
                        self._handle_failure(failure, trace_id)
                        if self._cancel.wait(float(self._next_reconnect)):
                            break
                        continue
                    self._accept_full_result(result)
                    self._schedule_after_full()
                    continue

                now = self._monotonic()
                if now >= self._next_full_at:
                    self.request_full_reconciliation()
                    continue
                trace_id = self._trace_factory()
                try:
                    if now >= self._next_tick_at:
                        self.run_tick_once()
                        self._next_tick_at = now + float(self._config.tick_poll_seconds)
                    with self._lock:
                        if self._reconciliation_required:
                            continue
                    if now >= self._next_position_at:
                        self.run_position_once()
                        self._next_position_at = now + float(
                            self._config.position_poll_seconds
                        )
                    with self._lock:
                        if self._reconciliation_required:
                            continue
                except Mt5ReadFailure as failure:
                    self._handle_failure(failure, trace_id)
                    if self._cancel.wait(float(self._next_reconnect)):
                        break
                    continue
                if self._wait_for_due_cycle():
                    break
        finally:
            self._adapter.disconnect()
            with self._lock:
                self._connected = False
                self._running = False
