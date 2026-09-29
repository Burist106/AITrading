"""Strict, non-executable Shadow journal wire. No operational order models."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictBool,
    StringConstraints,
    ValidationInfo,
    model_validator,
)


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str | Decimal):
        raise ValueError("decimal strings are required")
    text = format(value, "f") if isinstance(value, Decimal) else value
    if len(text) > 96 or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", text) is None:
        raise ValueError("finite nonnegative plain decimal string required")
    return Decimal(text)


def _utc(value: object) -> object:
    if not isinstance(value, str | datetime):
        raise ValueError("timestamp string or aware datetime required")
    if (
        isinstance(value, str)
        and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)",
            value,
        )
        is None
    ):
        raise ValueError("UTC microsecond timestamp required")
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _uuid(value: object) -> UUID:
    if (
        not isinstance(value, str | UUID)
        or re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            str(value),
        )
        is None
    ):
        raise ValueError("canonical RFC UUID required")
    return UUID(value) if isinstance(value, str) else value


def _utc_offset(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("UTC required")
    return value.astimezone(UTC)


Number = Annotated[
    Decimal,
    BeforeValidator(_decimal),
    Field(ge=0, allow_inf_nan=False),
    PlainSerializer(lambda value: format(value, "f"), return_type=str),
]
Positive = Annotated[Number, Field(gt=0)]
Timestamp = Annotated[AwareDatetime, BeforeValidator(_utc), AfterValidator(_utc_offset)]
Code = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,127}$")
]
Count = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
Version = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
WireUUID = Annotated[UUID, BeforeValidator(_uuid)]


class ShadowWireModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )

    @model_validator(mode="before")
    @classmethod
    def complete_json(cls, value: object, info: ValidationInfo) -> object:
        if (
            info.mode == "json"
            and isinstance(value, dict)
            and set(value) != set(cls.model_fields)
        ):
            raise ValueError("every wire field must be explicit")
        return value


class ShadowBar(ShadowWireModel):
    open_at: Timestamp
    open: Positive
    high: Positive
    low: Positive
    close: Positive

    @model_validator(mode="after")
    def valid_bar(self) -> Self:
        if (
            not self.low
            <= min(self.open, self.close)
            <= max(self.open, self.close)
            <= self.high
        ):
            raise ValueError("invalid OHLC")
        if self.open_at.second or self.open_at.microsecond:
            raise ValueError("M1 alignment required")
        return self


class ShadowMarket(ShadowWireModel):
    snapshot_id: WireUUID
    feature_id: WireUUID
    reconciliation_id: WireUUID
    input_digest: Digest
    account_fingerprint: Annotated[
        str, StringConstraints(pattern=r"^mt5-account-v1:[0-9a-f]{64}$")
    ]
    server_fingerprint: Annotated[
        str, StringConstraints(pattern=r"^mt5-server-v1:[0-9a-f]{64}$")
    ]
    specification_fingerprint: Annotated[
        str, StringConstraints(pattern=r"^mt5-spec-v1:[0-9a-f]{64}$")
    ]
    adapter_version: Identifier
    market_adapter_version: Identifier
    market_time_policy: Identifier
    broker_symbol: Identifier
    captured_at: Timestamp
    tick_at: Timestamp
    last_bar_closed_at: Timestamp
    bid: Positive
    ask: Positive
    point: Positive
    tick_size: Positive
    fast_sma: Positive
    slow_sma: Positive
    atr: Number
    bars: Annotated[tuple[ShadowBar, ...], Field(min_length=6, max_length=6)]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.ask < self.bid or not timedelta(
            0
        ) <= self.captured_at - self.tick_at <= timedelta(seconds=5):
            raise ValueError("invalid quote freshness or sides")
        if any(
            right.open_at - left.open_at != timedelta(minutes=1)
            for left, right in zip(self.bars, self.bars[1:], strict=False)
        ):
            raise ValueError("consecutive bars required")
        if self.last_bar_closed_at != self.bars[-1].open_at + timedelta(minutes=1):
            raise ValueError("bar close mismatch")
        if (
            not timedelta(0)
            <= self.captured_at - self.last_bar_closed_at
            < timedelta(minutes=1)
        ):
            raise ValueError("completed current bars required")
        return self


class ShadowCandidateRecord(ShadowWireModel):
    id: WireUUID
    direction: Literal["BUY", "SELL"]
    created_at: Timestamp
    expires_at: Timestamp
    entry_price: Positive
    stop_loss_price: Positive
    take_profit_price: Positive

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            not timedelta(0)
            < self.expires_at - self.created_at
            <= timedelta(seconds=30)
        ):
            raise ValueError("bounded expiry required")
        if not (
            self.stop_loss_price < self.entry_price < self.take_profit_price
            if self.direction == "BUY"
            else self.take_profit_price < self.entry_price < self.stop_loss_price
        ):
            raise ValueError("directional SL/TP required")
        return self


class ShadowCheck(ShadowWireModel):
    code: Code
    passed: StrictBool


Checks = Annotated[tuple[ShadowCheck, ...], Field(min_length=1, max_length=64)]


def _checks(outcome: str, checks: tuple[ShadowCheck, ...]) -> None:
    if len({check.code for check in checks}) != len(checks):
        raise ValueError("duplicate check")
    if (outcome == "PASS") != all(check.passed for check in checks):
        raise ValueError("outcome disagrees with checks")


class ShadowSourceReceipt(ShadowWireModel):
    kind: Literal["ledger", "safety", "news", "costs"]
    source_id: Identifier
    source_version: Identifier
    evidence_digest: Digest
    observed_at: Timestamp
    valid_until: Timestamp
    covered_from: Timestamp | None
    covered_until: Timestamp | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.valid_until < self.observed_at:
            raise ValueError("invalid source validity")
        if (self.covered_from is None) != (self.covered_until is None):
            raise ValueError("coverage must be paired")
        if (
            self.covered_from is not None
            and self.covered_until is not None
            and self.covered_until < self.covered_from
        ):
            raise ValueError("invalid source coverage")
        return self


class ShadowRiskRecord(ShadowWireModel):
    version: Literal["shadow-risk-v1"] = "shadow-risk-v1"
    outcome: Literal["PASS", "BLOCK"]
    checks: Checks
    input_digest: Digest
    source_receipts: Annotated[tuple[ShadowSourceReceipt, ...], Field(max_length=4)]
    calculated_volume: Positive | None
    estimated_loss_usd: Positive | None
    estimated_net_reward_usd: Positive | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        _checks(self.outcome, self.checks)
        kinds = {receipt.kind for receipt in self.source_receipts}
        if len(kinds) != len(self.source_receipts) or (
            self.outcome == "PASS" and kinds != {"ledger", "safety", "news", "costs"}
        ):
            raise ValueError("explicit unique source receipts required")
        amounts = (
            self.calculated_volume,
            self.estimated_loss_usd,
            self.estimated_net_reward_usd,
        )
        if (self.outcome == "BLOCK" and any(item is not None for item in amounts)) or (
            self.outcome == "PASS" and any(item is None for item in amounts)
        ):
            raise ValueError("amounts disagree with outcome")
        if self.calculated_volume is not None and self.calculated_volume > Decimal(
            "0.01"
        ):
            raise ValueError("volume ceiling exceeded")
        return self


class ShadowEligibility(ShadowWireModel):
    outcome: Literal["PASS", "BLOCK"]
    checks: Checks
    sample_count: Count
    minimum_sample_size: Annotated[int, Field(strict=True, ge=30, le=2_147_483_647)]
    calibrated: Literal[False] = False

    @model_validator(mode="before")
    @classmethod
    def strict_calibration(cls, value: object) -> object:
        if (
            isinstance(value, dict)
            and "calibrated" in value
            and value["calibrated"] is not False
        ):
            raise ValueError("strict calibration flag required")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        _checks(self.outcome, self.checks)
        if self.calibrated is not False:
            raise ValueError("uncalibrated baseline")
        sample = [check for check in self.checks if check.code == "SAMPLE_SIZE"]
        if len(sample) != 1 or sample[0].passed != (
            self.sample_count >= self.minimum_sample_size
        ):
            raise ValueError("sample count must agree with gate")
        return self


class ShadowCycle(ShadowWireModel):
    schema_version: Literal["shadow-cycle-v1"] = "shadow-cycle-v1"
    pipeline_version: Literal["shadow-pipeline-v1"] = "shadow-pipeline-v1"
    strategy_version: Literal["sma-atr-shadow-v1"] = "sma-atr-shadow-v1"
    eligibility_version: Literal["shadow-eligibility-v1"] = "shadow-eligibility-v1"
    id: WireUUID
    owner_id: WireUUID
    trading_account_id: WireUUID
    trace_id: WireUUID
    cycle_key: Digest
    evaluated_at: Timestamp
    environment: Literal["DEMO_ONLY"] = "DEMO_ONLY"
    runtime_mode: Literal["SHADOW"] = "SHADOW"
    source: Literal["mt5"] = "mt5"
    grants_eligibility: Literal[False] = False
    status: Literal["WAIT", "BLOCK", "PROPOSAL"]
    reason_codes: Annotated[tuple[Code, ...], Field(min_length=1, max_length=32)]
    policy_version_id: WireUUID | None
    policy_version: Version | None
    mode_version: Version | None
    market: ShadowMarket | None
    candidate: ShadowCandidateRecord | None
    risk: ShadowRiskRecord | None
    eligibility: ShadowEligibility | None

    @model_validator(mode="before")
    @classmethod
    def strict_safety(cls, value: object) -> object:
        if (
            isinstance(value, dict)
            and "grants_eligibility" in value
            and value["grants_eligibility"] is not False
        ):
            raise ValueError("no eligibility authority")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("duplicate reason")
        if (self.policy_version_id is None) != (self.policy_version is None):
            raise ValueError("policy reference pair required")
        if self.candidate is not None and (
            self.market is None or self.candidate.created_at != self.evaluated_at
        ):
            raise ValueError("candidate evidence mismatch")
        if self.market is not None and not timedelta(
            0
        ) <= self.evaluated_at - self.market.captured_at <= timedelta(seconds=5):
            raise ValueError("market/evaluation mismatch")
        if self.status == "WAIT" and (
            self.candidate is not None or self.risk is not None
        ):
            raise ValueError("WAIT cannot have sized candidate")
        if self.risk is not None and self.candidate is None:
            raise ValueError("risk requires candidate")
        if (
            self.risk is not None
            and self.risk.outcome == "PASS"
            and any(
                not receipt.observed_at <= self.evaluated_at <= receipt.valid_until
                for receipt in self.risk.source_receipts
            )
        ):
            raise ValueError("source receipt not valid at decision time")
        if self.status == "PROPOSAL" and (
            any(
                value is None
                for value in (
                    self.policy_version_id,
                    self.mode_version,
                    self.market,
                    self.candidate,
                    self.risk,
                    self.eligibility,
                )
            )
            or self.risk is None
            or self.risk.outcome != "PASS"
        ):
            raise ValueError("proposal requires complete passing risk evidence")
        return self


class ShadowOutcomeEvent(ShadowWireModel):
    schema_version: Literal["shadow-outcome-v1"] = "shadow-outcome-v1"
    tracker_version: Literal["quote-observed-v1"] = "quote-observed-v1"
    simulation: Literal[True] = True
    grants_eligibility: Literal[False] = False
    id: WireUUID
    owner_id: WireUUID
    trading_account_id: WireUUID
    cycle_id: WireUUID
    sequence: Annotated[Version, Field(le=32)]
    observed_at: Timestamp
    status: Literal[
        "OBSERVED", "STOP_OBSERVED", "TARGET_OBSERVED", "EXPIRED", "UNKNOWN"
    ]
    reason_code: Code
    bid: Positive | None
    ask: Positive | None
    price_source: Literal["mt5", "unavailable"]
    net_pnl_usd: None = None

    @model_validator(mode="before")
    @classmethod
    def strict_safety(cls, value: object) -> object:
        if isinstance(value, dict) and (
            ("simulation" in value and value["simulation"] is not True)
            or (
                "grants_eligibility" in value
                and value["grants_eligibility"] is not False
            )
        ):
            raise ValueError("strict simulation safety flags required")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.sequence == 32 and self.status == "OBSERVED":
            raise ValueError("final slot must be terminal")
        if self.price_source == "unavailable":
            if self.bid is not None or self.ask is not None or self.status != "UNKNOWN":
                raise ValueError("unavailable prices cannot establish outcome")
        elif self.bid is None or self.ask is None or self.ask < self.bid:
            raise ValueError("both coherent quote sides required")
        return self
