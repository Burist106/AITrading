"""Constructed native-shaped test evidence. Never a runtime data provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from mt5_factories import NOW, confirmed_binding
from test_shadow_market import read_port
from test_shadow_risk import _input

from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    CandleSeries,
    DatabaseReconciliationState,
    Mt5WorkerConfig,
    Timeframe,
)
from aurum_worker.reconciliation import ReadOnlyReconciliationService
from aurum_worker.shadow.context import (
    ShadowControlContext,
    ShadowEvidenceReceipt,
    ShadowExternalEvidence,
    risk_provenance,
)
from aurum_worker.shadow.market import MarketCapture, ShadowMarketService
from aurum_worker.shadow.models import ShadowCycle, ShadowOutcomeEvent
from aurum_worker.shadow.replay import ReplayEnvelope, canonical_replay_json


@dataclass
class MemoryReplayArchive:
    envelopes: dict[UUID, ReplayEnvelope] = field(default_factory=dict)

    def record(self, envelope: ReplayEnvelope) -> str:
        existing = self.envelopes.get(envelope.cycle.id)
        if existing is not None:
            if canonical_replay_json(existing) != canonical_replay_json(envelope):
                return "CONFLICT"
            return "IDEMPOTENT_REPLAY"
        self.envelopes[envelope.cycle.id] = envelope
        return "ARCHIVED"


def market_service(
    *, direction: str = "BUY"
) -> tuple[ShadowMarketService, Mt5WorkerConfig]:
    port = read_port()
    spec = port.specifications["XAUUSD"].model_copy(
        update={"specification_fingerprint": "mt5-spec-v1:" + "a" * 64}
    )
    port.specifications["XAUUSD"] = spec
    binding = confirmed_binding().model_copy(
        update={"confirmed_specification_fingerprint": spec.specification_fingerprint}
    )
    quote = port.ticks["XAUUSD"].model_copy(
        update={
            "bid": Decimal("2000"),
            "ask": Decimal("2000.02"),
            "spread_price": Decimal("0.02"),
            "spread_points": Decimal("2"),
        }
    )
    port.ticks["XAUUSD"] = quote
    bars = port.candles[("XAUUSD", Timeframe.M1)].candles
    closes = [Decimal("1999.5") + Decimal(i) / 10 for i in range(6)]
    if direction == "SELL":
        closes.reverse()
    if direction == "WAIT":
        closes = [Decimal("2000")] * 6
    port.candles[("XAUUSD", Timeframe.M1)] = CandleSeries(
        candles=tuple(
            bar.model_copy(
                update={
                    "open": close,
                    "close": close,
                    "high": close + 1,
                    "low": close - 1,
                }
            )
            for bar, close in zip(bars, closes, strict=True)
        )
    )
    account = port.accounts[0]
    config = Mt5WorkerConfig(
        broker_symbol="XAUUSD",
        expected_account_fingerprint=account.account_fingerprint,
        smoke_confirmed_specification_fingerprint=spec.specification_fingerprint,
        full_reconciliation_seconds=Decimal("60"),
    )
    persistence = InMemoryMt5ObservationPersistence(
        database_state=DatabaseReconciliationState(
            account_fingerprint=account.account_fingerprint,
            server_fingerprint=account.server_fingerprint,
            confirmed_symbol_binding=binding,
        )
    )
    rec = ReadOnlyReconciliationService(
        port,
        persistence,
        config,
        clock=lambda: NOW,
        identifier_factory=lambda: "00000000-0000-4000-8000-000000000001",
    )
    return ShadowMarketService(
        port, persistence, rec, config, clock=lambda: NOW
    ), config


def control() -> ShadowControlContext:
    policy = _input().policy
    assert policy is not None
    return ShadowControlContext(
        owner_id=policy.owner_id,
        trading_account_id=policy.trading_account_id,
        observed_at=NOW,
        mode_version=1,
        system_state="running",
        policy=policy,
    )


class CompleteTestEvidence:
    def read_evidence(
        self,
        capture: MarketCapture,
        context: ShadowControlContext,
        evaluated_at: datetime,
    ) -> ShadowExternalEvidence:
        original = _input()
        provenance = risk_provenance(capture, context)
        assert (
            original.account_risk is not None
            and original.safety is not None
            and original.costs is not None
        )
        return ShadowExternalEvidence(
            account_risk=original.account_risk.model_copy(
                update={"provenance": provenance}
            ),
            safety=original.safety.model_copy(update={"provenance": provenance}),
            costs=original.costs.model_copy(update={"provenance": provenance}),
            receipts=tuple(
                ShadowEvidenceReceipt(
                    kind=kind,
                    source_id="constructed-test-only",
                    source_version="v1",
                    evidence_digest="b" * 64,
                    provenance=provenance,
                    observed_at=NOW,
                    valid_until=NOW + timedelta(seconds=5),
                    covered_from=NOW - timedelta(days=7),
                    covered_until=NOW + timedelta(minutes=30),
                )
                for kind in ("ledger", "safety", "news", "costs")
            ),
            unavailable_reasons=(),
        )


@dataclass
class MemoryJournal:
    context: ShadowControlContext | None = field(default_factory=control)
    cycles: dict[str, ShadowCycle] = field(default_factory=dict)
    events: list[ShadowOutcomeEvent] = field(default_factory=list)
    fail_read: bool = False
    uncertain_write: bool = False
    writes: int = 0

    def read_context(self, trading_account_id: UUID) -> ShadowControlContext | None:
        return self.context

    def read_cycles(
        self, trading_account_id: UUID, cycle_key: str | None = None
    ) -> tuple[tuple[ShadowCycle, ...], tuple[ShadowOutcomeEvent, ...]]:
        if self.fail_read:
            raise OSError("test transport unavailable")
        cycles = tuple(
            cycle
            for cycle in self.cycles.values()
            if cycle.trading_account_id == trading_account_id
            and (cycle_key is None or cycle.cycle_key == cycle_key)
        )
        return cycles, tuple(
            event
            for event in self.events
            if any(cycle.id == event.cycle_id for cycle in cycles)
        )

    def record_cycle(self, cycle: ShadowCycle) -> str:
        self.writes += 1
        cycle = ShadowCycle.model_validate_json(cycle.model_dump_json())
        prior = self.cycles.get(cycle.cycle_key)
        if prior is not None and prior != cycle:
            return "CYCLE_CONFLICT"
        self.cycles[cycle.cycle_key] = cycle
        if self.uncertain_write:
            raise OSError("test uncertain after commit")
        return "IDEMPOTENT_REPLAY" if prior is not None else "CYCLE_RECORDED"

    def append_outcome(self, event: ShadowOutcomeEvent) -> str:
        prior = next((item for item in self.events if item.id == event.id), None)
        if prior is not None:
            return "IDEMPOTENT_REPLAY" if prior == event else "EVENT_CONFLICT"
        self.events.append(event)
        return "OUTCOME_RECORDED"
