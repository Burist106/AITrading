"""Explicit external-evidence boundary; unavailable inputs never become healthy."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import Field, model_validator

from aurum_worker.models.mt5 import Mt5WorkerConfig
from aurum_worker.models.risk_policy import RiskPolicyVersion
from aurum_worker.shadow.market import MarketCapture
from aurum_worker.shadow.models import Code, Digest, Identifier, Timestamp, Version
from aurum_worker.shadow.risk import (
    ShadowAccountRiskState,
    ShadowCandidate,
    ShadowCostContext,
    ShadowRiskInput,
    ShadowRiskModel,
    ShadowRiskProvenance,
    ShadowSafetyContext,
)


class ShadowControlContext(ShadowRiskModel):
    owner_id: UUID
    trading_account_id: UUID
    observed_at: Timestamp
    mode_version: Version
    system_state: Literal["running"]
    policy: RiskPolicyVersion

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            self.policy.owner_id != self.owner_id
            or self.policy.trading_account_id != self.trading_account_id
            or self.policy.created_at > self.observed_at
        ):
            raise ValueError("control policy identity/time mismatch")
        return self


class ShadowEvidenceReceipt(ShadowRiskModel):
    """Identity of independently sourced evidence, distinct from market binding."""

    kind: Literal["ledger", "safety", "news", "costs"]
    source_id: Identifier
    source_version: Identifier
    evidence_digest: Digest
    provenance: ShadowRiskProvenance
    observed_at: Timestamp
    valid_until: Timestamp
    covered_from: Timestamp | None
    covered_until: Timestamp | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.valid_until < self.observed_at:
            raise ValueError("evidence validity is inconsistent")
        if (self.covered_from is None) != (self.covered_until is None):
            raise ValueError("coverage boundaries must be paired")
        if (
            self.covered_from is not None
            and self.covered_until is not None
            and self.covered_until < self.covered_from
        ):
            raise ValueError("coverage boundaries are inconsistent")
        return self


class ShadowExternalEvidence(ShadowRiskModel):
    account_risk: ShadowAccountRiskState | None
    safety: ShadowSafetyContext | None
    costs: ShadowCostContext | None
    receipts: Annotated[tuple[ShadowEvidenceReceipt, ...], Field(max_length=16)]
    unavailable_reasons: Annotated[tuple[Code, ...], Field(max_length=16)]


class ShadowEvidenceProvider(Protocol):
    def read_evidence(
        self,
        capture: MarketCapture,
        control: ShadowControlContext,
        evaluated_at: datetime,
    ) -> ShadowExternalEvidence: ...


class MissingEvidenceProvider:
    """Production unavailable result until a genuine source provider is injected."""

    def read_evidence(
        self,
        capture: MarketCapture,
        control: ShadowControlContext,
        evaluated_at: datetime,
    ) -> ShadowExternalEvidence:
        return ShadowExternalEvidence(
            account_risk=None,
            safety=None,
            costs=None,
            receipts=(),
            unavailable_reasons=(
                "ACCOUNT_LEDGER_UNAVAILABLE",
                "NEWS_EVIDENCE_UNAVAILABLE",
                "COST_EVIDENCE_UNAVAILABLE",
                "SAFETY_EVIDENCE_UNAVAILABLE",
            ),
        )


def risk_provenance(
    capture: MarketCapture, control: ShadowControlContext
) -> ShadowRiskProvenance:
    return ShadowRiskProvenance(
        source="mt5",
        adapter_version=capture.account.adapter_version,
        market_adapter_version=capture.tick.adapter_version,
        owner_id=control.owner_id,
        trading_account_id=control.trading_account_id,
        account_fingerprint=capture.account.account_fingerprint,
        server_fingerprint=capture.account.server_fingerprint,
        broker_symbol=capture.specification.broker_symbol,
        specification_fingerprint=capture.specification.specification_fingerprint,
        risk_policy_version_id=control.policy.id,
        risk_policy_version=control.policy.version,
    )


def _validated_evidence(
    evidence: ShadowExternalEvidence,
    capture: MarketCapture,
    control: ShadowControlContext,
    evaluated_at: datetime,
) -> ShadowExternalEvidence:
    control = ShadowControlContext.model_validate(
        control.model_dump(mode="python", by_alias=True, warnings=False)
    )
    evidence = ShadowExternalEvidence.model_validate(
        evidence.model_dump(mode="python", warnings=False)
    )
    expected = risk_provenance(capture, control)
    maximum_age = timedelta(seconds=control.policy.stale_data_max_age_seconds)
    if (
        not timedelta(0)
        <= evaluated_at - control.observed_at
        <= min(maximum_age, timedelta(seconds=5))
    ):
        raise ValueError("stale control context")
    if evidence.unavailable_reasons and all(
        item is not None
        for item in (evidence.account_risk, evidence.safety, evidence.costs)
    ):
        raise ValueError(
            "unavailable evidence cannot establish complete risk readiness"
        )
    kinds: set[str] = set()
    for receipt in evidence.receipts:
        if (
            receipt.kind in kinds
            or receipt.provenance != expected
            or not timedelta(0) <= evaluated_at - receipt.observed_at <= maximum_age
            or evaluated_at > receipt.valid_until
        ):
            raise ValueError("invalid evidence receipt")
        kinds.add(receipt.kind)
    for context, required in (
        (evidence.account_risk, ("ledger",)),
        (evidence.costs, ("costs",)),
        (evidence.safety, ("safety", "news")),
    ):
        if context is None:
            continue
        if context.provenance != expected or not set(required) <= kinds:
            raise ValueError("missing context source receipt")
        if any(
            context.observed_at > receipt.observed_at
            for receipt in evidence.receipts
            if receipt.kind in required
        ):
            raise ValueError("context cannot freshen older source evidence")
    for receipt in evidence.receipts:
        if receipt.kind == "news":
            blackout = timedelta(minutes=control.policy.news_blackout_minutes)
            if (
                receipt.covered_from is None
                or receipt.covered_until is None
                or evaluated_at - receipt.covered_from < blackout
                or receipt.covered_until - evaluated_at < blackout
            ):
                raise ValueError("news coverage incomplete")
        if receipt.kind == "ledger" and evidence.account_risk is not None:
            state = evidence.account_risk
            if (
                state.week_started_at is None
                or receipt.covered_from is None
                or receipt.covered_until is None
                or receipt.covered_from > state.week_started_at
                or receipt.covered_until < state.observed_at
            ):
                raise ValueError("ledger coverage incomplete")
    return evidence


class ValidatedEvidenceProvider:
    """Adapter for an injected genuine provider, with sanitized fail-closed output."""

    def __init__(
        self,
        reader: Callable[
            [MarketCapture, ShadowControlContext, datetime], ShadowExternalEvidence
        ],
    ) -> None:
        self._reader = reader

    def read_evidence(
        self,
        capture: MarketCapture,
        control: ShadowControlContext,
        evaluated_at: datetime,
    ) -> ShadowExternalEvidence:
        try:
            return _validated_evidence(
                self._reader(capture, control, evaluated_at),
                capture,
                control,
                evaluated_at,
            )
        except Exception:
            return ShadowExternalEvidence(
                account_risk=None,
                safety=None,
                costs=None,
                receipts=(),
                unavailable_reasons=("EXTERNAL_EVIDENCE_UNAVAILABLE",),
            )


def build_risk_input(
    capture: MarketCapture,
    control: ShadowControlContext,
    candidate: ShadowCandidate,
    evidence: ShadowExternalEvidence,
    config: Mt5WorkerConfig,
    evaluated_at: datetime,
) -> ShadowRiskInput:
    # Apply the same validation even when a caller implements the provider port
    # directly; no synthetic/source-ready state can be inferred from absence.
    evidence = ValidatedEvidenceProvider(
        lambda _capture, _control, _at: evidence
    ).read_evidence(capture, control, evaluated_at)
    return ShadowRiskInput(
        evaluated_at=evaluated_at,
        provenance=risk_provenance(capture, control),
        candidate=candidate,
        account=capture.account,
        account_risk=evidence.account_risk,
        safety=evidence.safety,
        costs=evidence.costs,
        tick=capture.tick,
        specification=capture.specification,
        confirmed_binding=capture.confirmed_binding,
        reconciliation=capture.reconciliation.report,
        policy=control.policy,
        reconciliation_adapter_version="aurum-reconciliation-v1",
        maximum_tick_age_seconds=config.max_tick_age_seconds,
        maximum_reconciliation_age_seconds=min(
            600, int(config.full_reconciliation_seconds)
        ),
        maximum_specification_age_seconds=min(
            600, int(config.full_reconciliation_seconds)
        ),
    )


def _utc_inputs(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, dict):
        return {key: _utc_inputs(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_utc_inputs(item) for item in value)
    return value


def risk_input_digest(value: ShadowRiskInput) -> str:
    """Hash validated normalized input identity, not a ledger replay artifact.

    UTC timestamps and sorted compact JSON make this stable across timezone and
    mapping order. Exact Decimal strings are retained without numeric rounding.
    No source values or receipt payloads are logged or returned by this helper.
    """
    validated = ShadowRiskInput.model_validate(
        value.model_dump(mode="python", by_alias=True, warnings=False)
    )
    normalized = ShadowRiskInput.model_validate(
        _utc_inputs(validated.model_dump(mode="python", by_alias=True))
    )
    payload = json.dumps(
        normalized.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
