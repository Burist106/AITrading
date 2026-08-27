"""Cancellable serialized polling lifecycle for read-only MT5 observations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from threading import Event, RLock, Thread
from uuid import uuid4

from aurum_worker.adapters.protocols import (
    Mt5ObservationPersistencePort,
    Mt5ReadPort,
)
from aurum_worker.models.mt5 import (
    HealthState,
    Mt5HealthSnapshot,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReadOnlyPollingState,
)
from aurum_worker.reconciliation import (
    ReadOnlyReconciliationService,
    ReconciliationResult,
)


class ReadOnlyPollingService:
    """One thread, one adapter, cancellation-aware backoff, and no command work."""

    def __init__(
        self,
        adapter: Mt5ReadPort,
        persistence: Mt5ObservationPersistencePort,
        reconciliation: ReadOnlyReconciliationService,
        config: Mt5WorkerConfig,
        *,
        clock: Callable[[], datetime] | None = None,
        jitter: Callable[[int], Decimal] | None = None,
        trace_factory: Callable[[], str] | None = None,
    ) -> None:
        self._adapter = adapter
        self._persistence = persistence
        self._reconciliation = reconciliation
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))
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

    @property
    def state(self) -> ReadOnlyPollingState:
        with self._lock:
            return ReadOnlyPollingState(
                running=self._running,
                connected=self._connected,
                reconnect_attempt=self._attempt,
                next_reconnect_seconds=self._next_reconnect,
                last_successful_observation_at=self._last_success,
                reconciliation_required=not self._connected,
                stopped_at=self._clock() if self._shutdown else None,
            )

    def start(self) -> None:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Polling service cannot restart after shutdown.")
            if self._running:
                return
            self._running = True
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

    def run_once(self) -> ReconciliationResult:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("No MT5 API call is allowed after polling shutdown.")
        result = self._reconciliation.run(trace_id=self._trace_factory())
        with self._lock:
            self._connected = True
            self._attempt = 0
            self._next_reconnect = Decimal("0")
            self._last_success = result.health.observed_at
        return result

    def _record_failure(self, failure: Mt5ReadFailure, trace_id: str) -> None:
        now = self._clock()
        snapshot = Mt5HealthSnapshot(
            observed_at=now,
            source="mt5",
            adapter_version="aurum-poller-v1",
            trace_id=trace_id,
            state=(
                HealthState.BLOCKED
                if failure.error.reason_code
                in {
                    Mt5ReasonCode.CONTEST_ACCOUNT_BLOCKED,
                    Mt5ReasonCode.REAL_ACCOUNT_BLOCKED,
                    Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH,
                }
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

    def _run(self) -> None:
        try:
            while not self._cancel.is_set():
                trace_id = self._trace_factory()
                try:
                    self._reconciliation.run(trace_id=trace_id)
                except Mt5ReadFailure as failure:
                    self._adapter.disconnect()
                    with self._lock:
                        self._connected = False
                        self._attempt += 1
                        self._next_reconnect = self._backoff()
                    self._record_failure(failure, trace_id)
                    if self._cancel.wait(float(self._next_reconnect)):
                        break
                    continue
                with self._lock:
                    self._connected = True
                    self._attempt = 0
                    self._next_reconnect = Decimal("0")
                    self._last_success = self._clock()
                if self._cancel.wait(float(self._config.poll_interval_seconds)):
                    break
        finally:
            self._adapter.disconnect()
            with self._lock:
                self._connected = False
                self._running = False
