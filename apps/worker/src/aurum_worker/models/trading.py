"""Read-side broker and proposal wire contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from aurum_worker.models.base import (
    CurrencyCode,
    FiniteFloat,
    Identifier,
    MaximumPermittedVolume,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    WireModel,
)
from aurum_worker.models.eligibility import EligibilityPolicyResult

PermittedVolume = Annotated[float, Field(gt=0, le=0.01, allow_inf_nan=False)]
TokenHash = Annotated[
    str,
    StringConstraints(strict=True, min_length=32, max_length=256),
]


class BrokerSymbolSpecification(WireModel):
    canonical_symbol: Literal["XAUUSD"]
    broker_symbol: Identifier
    specification_version: Identifier
    account_currency: CurrencyCode
    contract_size: PositiveFloat
    digits: NonNegativeInt
    point_size: PositiveFloat
    tick_size: PositiveFloat
    tick_value: PositiveFloat | None
    minimum_volume: PositiveFloat
    maximum_volume: PositiveFloat
    volume_step: PositiveFloat
    stop_level: NonNegativeInt
    calculation_mode: Identifier
    fetched_at: AwareDatetime

    @model_validator(mode="after")
    def validate_volume_range(self) -> BrokerSymbolSpecification:
        if self.minimum_volume > self.maximum_volume:
            raise ValueError(
                "Broker minimum volume cannot exceed broker maximum volume."
            )
        return self


class PositionSizingCalculationSource(StrEnum):
    MT5_ORDER_CALC_PROFIT = "mt5_order_calc_profit"
    BROKER_TICK_VALUE = "broker_tick_value"
    SIMULATION = "simulation"


class _PositionSizingBase(WireModel):
    entry_price: PositiveFloat
    stop_loss_price: PositiveFloat
    stop_distance_price: PositiveFloat
    stop_distance_points: PositiveFloat
    account_equity: PositiveFloat
    risk_limit_pct: PositiveFloat
    risk_budget_amount: PositiveFloat
    calculated_volume: PositiveFloat
    broker_minimum_volume: PositiveFloat
    broker_volume_step: PositiveFloat
    maximum_permitted_volume: MaximumPermittedVolume
    estimated_loss_at_stop: PositiveFloat
    actual_risk_pct: PositiveFloat
    unused_risk_capacity: FiniteFloat
    calculation_source: PositionSizingCalculationSource

    @model_validator(mode="after")
    def validate_reconciliation(self) -> _PositionSizingBase:
        tolerance = 0.011
        expected_distance = abs(self.entry_price - self.stop_loss_price)
        if abs(expected_distance - self.stop_distance_price) > tolerance:
            raise ValueError("Stop distance must match entry and Stop Loss prices.")

        expected_budget = self.account_equity * (self.risk_limit_pct / 100)
        if abs(expected_budget - self.risk_budget_amount) > tolerance:
            raise ValueError(
                "Risk budget must reconcile with equity and risk percentage."
            )

        expected_risk = (self.estimated_loss_at_stop / self.account_equity) * 100
        if abs(expected_risk - self.actual_risk_pct) > tolerance:
            raise ValueError(
                "Actual risk must reconcile with estimated loss and equity."
            )
        return self


class PositionSizingPass(_PositionSizingBase):
    result: Literal["pass"]
    requested_volume: PermittedVolume
    approved_volume: PermittedVolume | None

    @model_validator(mode="after")
    def validate_approval_ceiling(self) -> PositionSizingPass:
        if (
            self.approved_volume is not None
            and self.approved_volume > self.requested_volume
        ):
            raise ValueError("Approved volume cannot exceed requested volume.")
        return self


class PositionSizingBlock(_PositionSizingBase):
    result: Literal["block"]
    requested_volume: None
    approved_volume: None
    block_reason: Identifier


type PositionSizingResult = Annotated[
    PositionSizingPass | PositionSizingBlock,
    Field(discriminator="result"),
]
POSITION_SIZING_ADAPTER: TypeAdapter[PositionSizingResult] = TypeAdapter(
    PositionSizingResult
)


class TradeProposalStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    EXECUTION_PENDING = "execution_pending"
    EXECUTED = "executed"
    FAILED = "failed"


class TradeDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class TradeProposal(WireModel):
    id: UUID
    proposal_version: PositiveInt
    user_id: UUID
    trading_account_id: UUID
    account_type: Literal["demo"]
    account_currency: CurrencyCode
    broker_server: Identifier
    canonical_symbol: Literal["XAUUSD"]
    broker_symbol: Identifier
    symbol_specification_version: Identifier
    direction: TradeDirection
    strategy_code: Identifier
    strategy_version: Identifier
    model_version: Identifier | None = None
    eligibility_policy_version: Identifier
    risk_policy_version: Identifier
    entry_price: PositiveFloat
    stop_loss_price: PositiveFloat
    take_profit_price: PositiveFloat
    calculated_volume: PositiveFloat
    requested_volume: PermittedVolume | None
    approved_volume: PermittedVolume | None
    maximum_permitted_volume: MaximumPermittedVolume
    risk_amount: PositiveFloat
    risk_pct: PositiveFloat
    risk_reward: PositiveFloat
    market_snapshot_id: UUID
    feature_snapshot_id: UUID
    decision_trace_id: UUID
    eligibility: EligibilityPolicyResult
    status: TradeProposalStatus
    created_at: AwareDatetime
    expires_at: AwareDatetime
    processed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_trade_invariants(self) -> TradeProposal:
        if self.direction is TradeDirection.BUY:
            prices_are_ordered = (
                self.stop_loss_price < self.entry_price < self.take_profit_price
            )
        else:
            prices_are_ordered = (
                self.take_profit_price < self.entry_price < self.stop_loss_price
            )
        if not prices_are_ordered:
            raise ValueError(
                "Entry, Stop Loss, and Take Profit are invalid for direction."
            )

        if self.created_at >= self.expires_at:
            raise ValueError("Proposal expiry must be after creation.")
        if self.status is TradeProposalStatus.BLOCKED and (
            self.requested_volume is not None or self.approved_volume is not None
        ):
            raise ValueError("Blocked proposals cannot request or approve volume.")
        if self.approved_volume is not None and self.requested_volume is None:
            raise ValueError("Approved volume requires a requested volume.")
        if (
            self.approved_volume is not None
            and self.requested_volume is not None
            and self.approved_volume > self.requested_volume
        ):
            raise ValueError("Approved volume cannot exceed requested volume.")
        return self


class PersistedTradeProposal(WireModel):
    """SQL proposal summary without unpersisted eligibility-check evidence."""

    id: UUID
    owner_id: UUID
    proposal_version: PositiveInt
    trading_account_id: UUID
    broker_symbol_id: UUID
    risk_policy_version_id: UUID
    account_type: Literal["demo"]
    account_currency: CurrencyCode
    broker_server: Identifier
    canonical_symbol: Literal["XAUUSD"]
    broker_symbol: Identifier
    symbol_specification_version: Identifier
    direction: TradeDirection
    strategy_code: Identifier
    strategy_version: Identifier
    model_version: Identifier | None
    eligibility_policy_id: Identifier
    eligibility_policy_version: Identifier
    eligibility_outcome: Literal["auto", "ask", "block"]
    eligibility_evaluated_at: AwareDatetime
    risk_policy_version: Identifier
    entry_price: PositiveFloat
    stop_loss_price: PositiveFloat
    take_profit_price: PositiveFloat
    calculated_volume: PositiveFloat
    requested_volume: PermittedVolume | None
    approved_volume: PermittedVolume | None
    maximum_permitted_volume: MaximumPermittedVolume
    risk_amount: PositiveFloat
    risk_pct: PositiveFloat
    risk_reward: PositiveFloat
    market_snapshot_id: UUID
    feature_snapshot_id: UUID
    decision_trace_id: UUID
    status: TradeProposalStatus
    created_at: AwareDatetime
    expires_at: AwareDatetime
    processed_at: AwareDatetime | None
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_persisted_summary(self) -> PersistedTradeProposal:
        if self.direction is TradeDirection.BUY:
            prices_are_ordered = (
                self.stop_loss_price < self.entry_price < self.take_profit_price
            )
        else:
            prices_are_ordered = (
                self.take_profit_price < self.entry_price < self.stop_loss_price
            )
        if not prices_are_ordered:
            raise ValueError(
                "Entry, Stop Loss, and Take Profit are invalid for direction."
            )
        if self.created_at >= self.expires_at:
            raise ValueError("Proposal expiry must be after creation.")
        if self.status is TradeProposalStatus.BLOCKED and (
            self.requested_volume is not None or self.approved_volume is not None
        ):
            raise ValueError("Blocked proposals cannot request or approve volume.")
        if self.approved_volume is not None and self.requested_volume is None:
            raise ValueError("Approved volume requires a requested volume.")
        if (
            self.approved_volume is not None
            and self.requested_volume is not None
            and self.approved_volume > self.requested_volume
        ):
            raise ValueError("Approved volume cannot exceed requested volume.")
        return self


class MobileApprovalSessionStatus(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


class MobileApprovalSession(WireModel):
    id: UUID
    proposal_id: UUID
    proposal_version: PositiveInt
    allowed_user_id: Identifier
    token_hash: TokenHash
    nonce: Identifier
    status: MobileApprovalSessionStatus
    created_at: AwareDatetime
    expires_at: AwareDatetime
    used_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_session_lifecycle(self) -> MobileApprovalSession:
        if self.created_at >= self.expires_at:
            raise ValueError("Approval session expiry must be after creation.")
        if self.status is MobileApprovalSessionStatus.USED and self.used_at is None:
            raise ValueError("Used approval sessions require a usedAt timestamp.")
        return self
