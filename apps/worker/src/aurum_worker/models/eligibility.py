"""Eligibility and signal-evidence wire contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, model_validator

from aurum_worker.models.base import (
    FiniteFloat,
    Identifier,
    NonNegativeFloat,
    NonNegativeInt,
    WireModel,
)


class EligibilityCheckKey(StrEnum):
    STRATEGY_POLICY = "strategy_policy"
    REGIME_ELIGIBILITY = "regime_eligibility"
    MINIMUM_SAMPLE_SIZE = "minimum_sample_size"
    DATA_QUALITY = "data_quality"
    CALIBRATION_REQUIREMENT = "calibration_requirement"
    HARD_RISK_VALIDATION = "hard_risk_validation"
    EXECUTION_ENVIRONMENT = "execution_environment"


class EligibilityCheckState(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NOT_REQUIRED = "not_required"


class EligibilityOutcome(StrEnum):
    AUTO = "auto"
    ASK = "ask"
    BLOCK = "block"


class CalibrationStatus(StrEnum):
    NOT_CALIBRATED = "not_calibrated"
    INSUFFICIENT_DATA = "insufficient_data"
    CALIBRATED = "calibrated"
    OUT_OF_DATE = "out_of_date"


class EligibilityCheck(WireModel):
    key: EligibilityCheckKey
    label_th: Identifier
    state: EligibilityCheckState
    actual_value: str | FiniteFloat | None = None
    required_value: str | FiniteFloat | None = None
    explanation: Identifier | None = None


class EligibilityPolicyResult(WireModel):
    policy_id: Identifier
    policy_version: Identifier
    outcome: EligibilityOutcome
    evaluated_at: AwareDatetime
    checks: tuple[EligibilityCheck, ...]

    @model_validator(mode="after")
    def validate_outcome(self) -> EligibilityPolicyResult:
        if not self.checks:
            raise ValueError("Eligibility result requires at least one check.")

        keys = [check.key for check in self.checks]
        if len(set(keys)) != len(keys):
            raise ValueError("Eligibility check keys must be unique.")

        states = {check.state for check in self.checks}
        if EligibilityCheckState.FAIL in states:
            expected = EligibilityOutcome.BLOCK
        elif EligibilityCheckState.WARN in states:
            expected = EligibilityOutcome.ASK
        else:
            expected = EligibilityOutcome.AUTO

        if self.outcome is not expected:
            raise ValueError(
                f"Outcome must be {expected.value} for the supplied checks."
            )
        return self


class SignalEvidence(WireModel):
    """Supporting evidence only; it grants no trading permission."""

    quality_score: NonNegativeFloat | None
    calibrated_probability: NonNegativeFloat | None
    calibration_status: CalibrationStatus
    similar_sample_count: NonNegativeInt
    minimum_required_sample_count: NonNegativeInt
    strategy_version: Identifier
    model_version: Identifier | None = None

    @model_validator(mode="after")
    def validate_bounded_scores(self) -> SignalEvidence:
        if self.quality_score is not None and self.quality_score > 100:
            raise ValueError("Quality score cannot exceed 100.")
        if self.calibrated_probability is not None and self.calibrated_probability > 1:
            raise ValueError("Calibrated probability cannot exceed 1.")
        if (
            self.calibration_status is not CalibrationStatus.CALIBRATED
            and self.calibrated_probability is not None
        ):
            raise ValueError(
                "A calibrated probability requires calibrated model status."
            )
        return self
