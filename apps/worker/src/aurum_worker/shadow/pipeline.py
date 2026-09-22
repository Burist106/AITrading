"""Serialized production Shadow pipeline; every reached stage is journaled."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from aurum_worker.models.mt5 import Mt5ReasonCode, Mt5WorkerConfig
from aurum_worker.reconciliation import ReconciliationResult
from aurum_worker.shadow.context import (
    ShadowControlContext,
    ShadowEvidenceProvider,
    ValidatedEvidenceProvider,
    build_risk_input,
    risk_input_digest,
)
from aurum_worker.shadow.market import MarketBlocked, MarketCapture, ShadowMarketService
from aurum_worker.shadow.models import (
    ShadowBar,
    ShadowCandidateRecord,
    ShadowCheck,
    ShadowCycle,
    ShadowMarket,
    ShadowOutcomeEvent,
    ShadowRiskRecord,
    ShadowSourceReceipt,
)
from aurum_worker.shadow.persistence import (
    ShadowPersistenceCode,
    ShadowPersistenceError,
)
from aurum_worker.shadow.replay import ReplayEnvelope, make_replay_envelope
from aurum_worker.shadow.risk import ShadowRiskProvenance, evaluate_shadow_risk
from aurum_worker.shadow.strategy import (
    baseline_candidate,
    evaluate_baseline_eligibility,
)


class ShadowJournalPort(Protocol):
    def read_context(self, trading_account_id: UUID) -> ShadowControlContext | None: ...
    def read_cycles(
        self, trading_account_id: UUID, cycle_key: str | None = None
    ) -> tuple[tuple[ShadowCycle, ...], tuple[ShadowOutcomeEvent, ...]]: ...
    def record_cycle(self, cycle: ShadowCycle) -> str: ...
    def append_outcome(self, event: ShadowOutcomeEvent) -> str: ...


class ShadowReplayArchivePort(Protocol):
    def record(self, envelope: ReplayEnvelope) -> str: ...


def cycle_identity(trading_account_id: UUID, now: datetime) -> tuple[str, UUID]:
    if now.utcoffset() is None:
        raise ValueError("aware clock required")
    minute = now.astimezone(UTC).replace(second=0, microsecond=0)
    material = (
        f"{trading_account_id}|{minute.isoformat()}"
        "|shadow-pipeline-v1|sma-atr-shadow-v1"
    )
    key = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return key, uuid5(NAMESPACE_URL, "aurum:shadow-cycle:" + key)


def market_record(capture: MarketCapture) -> ShadowMarket:
    f, tick, spec = capture.features, capture.tick, capture.specification
    return ShadowMarket(
        snapshot_id=UUID(f.market_snapshot_id),
        feature_id=UUID(f.feature_snapshot_id),
        reconciliation_id=UUID(f.reconciliation_id),
        input_digest=f.input_digest,
        account_fingerprint=capture.account.account_fingerprint,
        server_fingerprint=capture.account.server_fingerprint,
        specification_fingerprint=spec.specification_fingerprint,
        adapter_version=f.adapter_version,
        market_adapter_version=f.market_adapter_version,
        market_time_policy=f.market_time_policy,
        broker_symbol=spec.broker_symbol,
        captured_at=f.evaluated_at,
        tick_at=tick.tick_at,
        last_bar_closed_at=f.last_bar_closed_at,
        bid=tick.bid,
        ask=tick.ask,
        point=spec.point,
        tick_size=spec.tick_size,
        fast_sma=f.fast_sma,
        slow_sma=f.slow_sma,
        atr=f.atr,
        bars=tuple(
            ShadowBar(
                open_at=bar.open_at,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
            )
            for bar in capture.series.candles
        ),
    )


@dataclass(frozen=True, slots=True)
class ShadowPipelineResult:
    cycle: ShadowCycle | None
    persistence_code: str


class ShadowPipeline:
    """One owner calls this on the full reconciliation cadence, never each tick.

    Database loss produces an explicit local persistence failure, not a pretend
    durable BLOCK. An uncertain write retains its exact envelope for replay.
    """

    def __init__(
        self,
        market: ShadowMarketService,
        journal: ShadowJournalPort,
        evidence: ShadowEvidenceProvider,
        config: Mt5WorkerConfig,
        *,
        owner_id: UUID,
        trading_account_id: UUID,
        replay_archive: ShadowReplayArchivePort | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.market, self.journal, self.evidence, self.config = (
            market,
            journal,
            evidence,
            config,
        )
        self.owner_id, self.trading_account_id = owner_id, trading_account_id
        self.replay_archive = replay_archive
        self.clock = clock or (lambda: datetime.now(UTC))
        self._pending: ShadowCycle | None = None
        self._pending_replay: ReplayEnvelope | None = None

    def _persist(
        self, cycle: ShadowCycle, replay: ReplayEnvelope | None = None
    ) -> ShadowPipelineResult:
        self._pending = cycle
        self._pending_replay = replay
        if cycle.risk is not None:
            try:
                if (
                    replay is None
                    or self.replay_archive is None
                    or self.replay_archive.record(replay)
                    not in {"ARCHIVED", "IDEMPOTENT_REPLAY"}
                ):
                    return ShadowPipelineResult(None, "REPLAY_ARCHIVE_UNAVAILABLE")
            except Exception:
                return ShadowPipelineResult(None, "REPLAY_ARCHIVE_UNAVAILABLE")
        try:
            code = self.journal.record_cycle(cycle)
            if code not in {"CYCLE_RECORDED", "IDEMPOTENT_REPLAY"}:
                self._pending = None
                self._pending_replay = None
                return ShadowPipelineResult(None, "PERSISTENCE_REJECTED")
        except ShadowPersistenceError as error:
            if error.code is ShadowPersistenceCode.RPC_REJECTED:
                self._pending = None
                self._pending_replay = None
                return ShadowPipelineResult(None, "PERSISTENCE_REJECTED")
            return ShadowPipelineResult(None, "PERSISTENCE_UNAVAILABLE")
        except Exception:
            return ShadowPipelineResult(None, "PERSISTENCE_UNAVAILABLE")
        self._pending = None
        self._pending_replay = None
        return ShadowPipelineResult(cycle, code)

    def run_cycle(
        self,
        *,
        reconciliation_result: ReconciliationResult | None = None,
        source_failure: Mt5ReasonCode | None = None,
    ) -> ShadowPipelineResult:
        if self._pending is not None:
            return self._persist(self._pending, self._pending_replay)
        clock_value = self.clock()
        if clock_value.utcoffset() is None:
            return ShadowPipelineResult(None, "CLOCK_INVALID")
        now = clock_value.astimezone(UTC)
        key, identifier = cycle_identity(self.trading_account_id, now)
        try:
            existing, _ = self.journal.read_cycles(self.trading_account_id, key)
            if existing:
                if (
                    len(existing) != 1
                    or existing[0].owner_id != self.owner_id
                    or existing[0].trading_account_id != self.trading_account_id
                    or existing[0].cycle_key != key
                    or existing[0].id != identifier
                ):
                    return ShadowPipelineResult(None, "PERSISTENCE_INVALID")
                return ShadowPipelineResult(
                    ShadowCycle.model_validate(existing[0].model_dump()),
                    "IDEMPOTENT_REPLAY",
                )
        except Exception:
            return ShadowPipelineResult(None, "PERSISTENCE_UNAVAILABLE")
        trace = uuid5(NAMESPACE_URL, f"aurum:shadow-trace:{identifier}")
        base = ShadowCycle(
            id=identifier,
            owner_id=self.owner_id,
            trading_account_id=self.trading_account_id,
            trace_id=trace,
            cycle_key=key,
            evaluated_at=now,
            status="BLOCK",
            reason_codes=(
                source_failure.value
                if source_failure is not None
                else "CONTROL_CONTEXT_UNAVAILABLE",
            ),
            policy_version_id=None,
            policy_version=None,
            mode_version=None,
            market=None,
            candidate=None,
            risk=None,
            eligibility=None,
        )
        # A failed control read does not authorize a native capture. A separate
        # write may still persist the missing-context reason if DB recovers.
        try:
            control = self.journal.read_context(self.trading_account_id)
        except Exception:
            control = None
        if control is None:
            return self._persist(base)
        now = self.clock().astimezone(UTC)
        if (
            control.owner_id != self.owner_id
            or control.trading_account_id != self.trading_account_id
            or not timedelta(0) <= now - control.observed_at <= timedelta(seconds=5)
        ):
            return self._persist(
                base.model_copy(update={"reason_codes": ("CONTROL_CONTEXT_INVALID",)})
            )
        base = base.model_copy(
            update={
                "policy_version_id": control.policy.id,
                "policy_version": control.policy.version,
                "mode_version": control.mode_version,
            }
        )
        if source_failure is not None:
            return self._persist(base)
        try:
            capture = self.market.capture_bundle(
                trace_id=str(trace), reconciliation_result=reconciliation_result
            )
            if isinstance(capture, MarketBlocked):
                reasons = tuple(
                    dict.fromkeys(
                        (capture.reason.value,)
                        + (
                            (capture.native_reason.value,)
                            if capture.native_reason is not None
                            else ()
                        )
                    )
                )
                return self._persist(base.model_copy(update={"reason_codes": reasons}))
            now = self.clock().astimezone(UTC)
            if not timedelta(0) <= now - control.observed_at <= timedelta(seconds=5):
                return self._persist(
                    base.model_copy(
                        update={"reason_codes": ("CONTROL_CONTEXT_INVALID",)}
                    )
                )
            market = market_record(capture)
            base = ShadowCycle.model_validate(
                base.model_copy(
                    update={"evaluated_at": now, "market": market}
                ).model_dump()
            )
            provenance = ShadowRiskProvenance(
                source="mt5",
                adapter_version=capture.features.adapter_version,
                market_adapter_version=capture.features.market_adapter_version,
                owner_id=self.owner_id,
                trading_account_id=self.trading_account_id,
                account_fingerprint=capture.account.account_fingerprint,
                server_fingerprint=capture.account.server_fingerprint,
                broker_symbol=capture.specification.broker_symbol,
                specification_fingerprint=capture.specification.specification_fingerprint,
                risk_policy_version_id=control.policy.id,
                risk_policy_version=control.policy.version,
            )
            candidate = baseline_candidate(
                capture,
                provenance,
                cycle_id=identifier,
                trace_id=capture.tick.trace_id,
                evaluated_at=now,
                expiry_seconds=control.policy.proposal_expiry_seconds,
            )
            if candidate is None:
                return self._persist(
                    base.model_copy(
                        update={
                            "status": "WAIT",
                            "reason_codes": ("NO_DIRECTIONAL_SIGNAL",),
                        }
                    )
                )
            base = base.model_copy(
                update={
                    "candidate": ShadowCandidateRecord(
                        id=candidate.candidate_id,
                        direction=candidate.direction.value,
                        created_at=candidate.created_at,
                        expires_at=candidate.expires_at,
                        entry_price=candidate.entry_price,
                        stop_loss_price=candidate.stop_loss_price,
                        take_profit_price=candidate.take_profit_price,
                    )
                }
            )
            raw_evidence = self.evidence.read_evidence(capture, control, now)
            now = self.clock().astimezone(UTC)
            evidence = ValidatedEvidenceProvider(
                lambda _capture, _control, _at: raw_evidence
            ).read_evidence(capture, control, now)
            candidate = candidate.model_copy(
                update={
                    "created_at": now,
                    "expires_at": now
                    + timedelta(seconds=control.policy.proposal_expiry_seconds),
                }
            )
            assert base.candidate is not None
            base = ShadowCycle.model_validate(
                base.model_copy(
                    update={
                        "evaluated_at": now,
                        "candidate": base.candidate.model_copy(
                            update={
                                "created_at": candidate.created_at,
                                "expires_at": candidate.expires_at,
                            }
                        ),
                    }
                ).model_dump()
            )
            risk_input = build_risk_input(
                capture,
                control,
                candidate,
                evidence,
                self.config,
                self.clock().astimezone(UTC),
            )
            result = evaluate_shadow_risk(risk_input)
            risk = ShadowRiskRecord(
                outcome=result.outcome,
                input_digest=risk_input_digest(risk_input),
                source_receipts=tuple(
                    ShadowSourceReceipt(
                        kind=receipt.kind,
                        source_id=receipt.source_id,
                        source_version=receipt.source_version,
                        evidence_digest=receipt.evidence_digest,
                        observed_at=receipt.observed_at,
                        valid_until=receipt.valid_until,
                        covered_from=receipt.covered_from,
                        covered_until=receipt.covered_until,
                    )
                    for receipt in evidence.receipts
                ),
                checks=tuple(
                    ShadowCheck(code=check.code, passed=check.passed)
                    for check in result.checks
                ),
                calculated_volume=result.calculated_volume,
                estimated_loss_usd=result.estimated_loss_usd,
                estimated_net_reward_usd=result.estimated_net_reward_usd,
            )
            eligibility = evaluate_baseline_eligibility(
                minimum_sample_size=control.policy.minimum_sample_size,
                risk_passed=result.outcome == "PASS",
            )
            reasons = (
                tuple(check.code for check in risk.checks if not check.passed)[:32]
                if risk.outcome == "BLOCK"
                else ("SHADOW_RESEARCH_ONLY", "ELIGIBILITY_BLOCKED")
            )
            cycle = ShadowCycle.model_validate(
                base.model_copy(
                    update={
                        "status": "PROPOSAL" if result.outcome == "PASS" else "BLOCK",
                        "reason_codes": reasons,
                        "risk": risk,
                        "eligibility": eligibility,
                    }
                ).model_dump()
            )
            # The complete local envelope commits before publishing its cycle.
            # This is not a distributed transaction: a later RPC failure can
            # leave a local-only envelope, never a fabricated remote success.
            try:
                replay = make_replay_envelope(cycle, risk_input)
            except Exception:
                return ShadowPipelineResult(None, "REPLAY_ARCHIVE_UNAVAILABLE")
            return self._persist(cycle, replay)
        except Exception:
            # Raw exceptions may contain input/provider data: never serialize them.
            return self._persist(
                ShadowCycle.model_validate(
                    base.model_copy(
                        update={
                            "status": "BLOCK",
                            "reason_codes": ("STAGE_INPUT_INVALID",),
                        }
                    ).model_dump()
                )
            )
