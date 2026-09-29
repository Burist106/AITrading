"""Single-owner composition of existing read-only polling and Shadow journaling."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from aurum_worker.adapters.persistence_mt5 import (
    WorkerRpcClient,
    WorkerRpcMt5ObservationPersistence,
)
from aurum_worker.adapters.protocols import Mt5ReadPort
from aurum_worker.models.mt5 import (
    AccountObservation,
    LatestTickObservation,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    SafeMt5Error,
)
from aurum_worker.polling import ReadOnlyPollingService
from aurum_worker.reconciliation import (
    ReadOnlyReconciliationService,
    ReconciliationResult,
)
from aurum_worker.shadow.context import MissingEvidenceProvider, ShadowEvidenceProvider
from aurum_worker.shadow.market import ShadowMarketService
from aurum_worker.shadow.models import ShadowCycle, ShadowOutcomeEvent
from aurum_worker.shadow.outcomes import observe_outcome
from aurum_worker.shadow.persistence import RpcShadowStore
from aurum_worker.shadow.pipeline import (
    ShadowJournalPort,
    ShadowPipeline,
    ShadowPipelineResult,
    ShadowReplayArchivePort,
)


class ShadowRuntime:
    """Callbacks run synchronously on the poller's sole native owner thread.

    Full reconciliation is reused by the market stage; ticks never read history.
    The current runtime accepts no command-consumption or execution capability.
    """

    def __init__(
        self,
        adapter: Mt5ReadPort,
        rpc: WorkerRpcClient,
        config: Mt5WorkerConfig,
        *,
        owner_id: UUID,
        trading_account_id: UUID,
        evidence: ShadowEvidenceProvider | None = None,
        replay_archive: ShadowReplayArchivePort | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self.owner_id, self.trading_account_id = owner_id, trading_account_id
        self.journal: ShadowJournalPort = RpcShadowStore(rpc)
        persistence = WorkerRpcMt5ObservationPersistence(rpc)
        reconciliation = ReadOnlyReconciliationService(
            adapter, persistence, config, clock=self.clock
        )
        market = ShadowMarketService(
            adapter, persistence, reconciliation, config, clock=self.clock
        )
        self.pipeline = ShadowPipeline(
            market,
            self.journal,
            evidence or MissingEvidenceProvider(),
            config,
            owner_id=owner_id,
            trading_account_id=trading_account_id,
            replay_archive=replay_archive,
            clock=self.clock,
        )
        self.poller = ReadOnlyPollingService(
            adapter,
            persistence,
            reconciliation,
            config,
            clock=self.clock,
            on_full_cycle=self._full,
            on_tick=self._tick,
            on_failure=self._source_failure,
        )
        self.last_result: ShadowPipelineResult | None = None
        self._cycles: dict[UUID, ShadowCycle] = {}
        self._outcomes: dict[UUID, ShadowOutcomeEvent] = {}
        self._pending_events: dict[UUID, ShadowOutcomeEvent] = {}
        self._started = False

    @staticmethod
    def _failure() -> Mt5ReadFailure:
        return Mt5ReadFailure(
            SafeMt5Error(
                reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                safe_detail="Shadow journal could not confirm durable state.",
                retryable=True,
            )
        )

    def _record_event(self, event: ShadowOutcomeEvent) -> None:
        self._pending_events[event.cycle_id] = event
        try:
            code = self.journal.append_outcome(event)
            if code not in {"OUTCOME_RECORDED", "IDEMPOTENT_REPLAY"}:
                raise self._failure()
        except Exception:
            raise self._failure() from None
        self._outcomes[event.cycle_id] = event
        del self._pending_events[event.cycle_id]
        if event.status != "OBSERVED":
            self._cycles.pop(event.cycle_id, None)

    def recover(self) -> None:
        """Recover pending research; downtime never implies continuous prices."""
        try:
            cycles, events = self.journal.read_cycles(self.trading_account_id)
            if any(cycle.owner_id != self.owner_id for cycle in cycles):
                raise self._failure()
            self._outcomes = {
                event.cycle_id: event
                for event in sorted(events, key=lambda event: event.sequence)
            }
            for cycle in cycles:
                previous = self._outcomes.get(cycle.id)
                if cycle.status != "PROPOSAL" or (
                    previous is not None and previous.status != "OBSERVED"
                ):
                    continue
                self._cycles[cycle.id] = cycle
                event = observe_outcome(
                    cycle, previous, None, observed_at=self.clock(), restarted=True
                )
                if event is not None:
                    self._record_event(event)
        except Exception:
            raise self._failure() from None

    def _full(self, result: ReconciliationResult, trace_id: str) -> None:
        self.last_result = self.pipeline.run_cycle(reconciliation_result=result)
        cycle = self.last_result.cycle
        if cycle is None:
            raise self._failure()
        if cycle.status == "PROPOSAL" and cycle.id not in self._outcomes:
            self._cycles[cycle.id] = cycle
        # Even when a full cycle fails, expired/gapped research remains UNKNOWN.
        now = self.clock()
        for cycle_id, active in tuple(self._cycles.items()):
            previous = self._outcomes.get(cycle_id)
            last = previous.observed_at if previous is not None else active.evaluated_at
            if (now - last).total_seconds() > 5:
                event = observe_outcome(active, previous, None, observed_at=now)
                if event is not None:
                    self._record_event(event)

    def _tick(self, tick: LatestTickObservation, account: AccountObservation) -> None:
        for pending_event in tuple(self._pending_events.values()):
            self._record_event(pending_event)
        for cycle_id, cycle in tuple(self._cycles.items()):
            market = cycle.market
            bound = (
                market is not None
                and account.source == "mt5"
                and account.account_fingerprint == market.account_fingerprint
                and account.server_fingerprint == market.server_fingerprint
                and account.adapter_version == market.adapter_version
            )
            event = observe_outcome(
                cycle,
                self._outcomes.get(cycle_id),
                tick if bound else None,
                observed_at=self.clock(),
            )
            if event is not None:
                self._record_event(event)

    def _source_failure(self, failure: Mt5ReadFailure, trace_id: str) -> None:
        self.last_result = self.pipeline.run_cycle(
            source_failure=failure.error.reason_code
        )
        if (
            self.last_result.cycle is not None
            and self.last_result.cycle.status != "BLOCK"
        ):
            # The existing immutable minute record is historical, not recovery.
            self.last_result = ShadowPipelineResult(None, "SOURCE_UNAVAILABLE")
        now = self.clock()
        for cycle_id, cycle in tuple(self._cycles.items()):
            event = observe_outcome(
                cycle, self._outcomes.get(cycle_id), None, observed_at=now
            )
            if event is not None:
                self._record_event(event)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("Shadow runtime already started")
        self.recover()
        self._started = True
        self.poller.start()

    def stop(self) -> None:
        self.poller.stop()
