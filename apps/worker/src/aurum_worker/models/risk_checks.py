"""Read-only deterministic risk-check contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, StringConstraints

from aurum_worker.models.base import Identifier, NonNegativeInt, PositiveInt, WireModel

RiskCheckDetail = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        strict=True,
        min_length=1,
        max_length=512,
    ),
]


class RiskCheckState(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NA = "na"


class RiskCheck(WireModel):
    """Deterministic evidence only; this model grants no override."""

    key: Identifier
    label_th: Identifier
    label_en: Identifier
    state: RiskCheckState
    actual: RiskCheckDetail
    limit: RiskCheckDetail | None = None
    hard: bool


class PersistedRiskCheck(WireModel):
    id: UUID
    owner_id: UUID
    trade_proposal_id: UUID
    proposal_version: PositiveInt
    key: Identifier
    label_th: Identifier
    label_en: Identifier
    state: RiskCheckState
    actual: RiskCheckDetail
    limit_value: RiskCheckDetail | None
    explanation: RiskCheckDetail | None
    hard: bool
    ordinal: NonNegativeInt
    created_at: AwareDatetime

    def to_risk_check(self) -> RiskCheck:
        return RiskCheck.model_validate(
            {
                "key": self.key,
                "labelTh": self.label_th,
                "labelEn": self.label_en,
                "state": self.state,
                "actual": self.actual,
                "limit": self.limit_value,
                "hard": self.hard,
            }
        )
