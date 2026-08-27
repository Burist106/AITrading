"""Immutable Demo risk-policy version sent across the Worker boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from aurum_worker.models.base import (
    Identifier,
    MaximumPermittedVolume,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    WireModel,
)


class RiskPolicyNumericRuleKey(StrEnum):
    RISK_PER_TRADE_PCT = "risk_per_trade_pct"
    DAILY_LOSS_LIMIT_PCT = "daily_loss_limit_pct"
    WEEKLY_LOSS_LIMIT_PCT = "weekly_loss_limit_pct"
    MAXIMUM_DRAWDOWN_PCT = "maximum_drawdown_pct"
    MAXIMUM_TRADES_PER_DAY = "maximum_trades_per_day"
    MINIMUM_RISK_REWARD = "minimum_risk_reward"
    STALE_DATA_MAX_AGE_SECONDS = "stale_data_max_age_seconds"
    MAXIMUM_SPREAD_POINTS = "maximum_spread_points"
    NEWS_BLACKOUT_MINUTES = "news_blackout_minutes"


class RiskPolicyActorType(StrEnum):
    USER = "user"
    WORKER = "worker"
    SYSTEM = "system"


def validate_risk_policy_rule_value(
    rule_key: RiskPolicyNumericRuleKey, new_value: float
) -> None:
    issue: str | None = None
    if rule_key is RiskPolicyNumericRuleKey.RISK_PER_TRADE_PCT and new_value > 0.25:
        issue = "must be at most 0.25"
    elif rule_key is RiskPolicyNumericRuleKey.DAILY_LOSS_LIMIT_PCT and new_value > 1:
        issue = "must be at most 1"
    elif rule_key is RiskPolicyNumericRuleKey.WEEKLY_LOSS_LIMIT_PCT and new_value > 3:
        issue = "must be at most 3"
    elif rule_key is RiskPolicyNumericRuleKey.MAXIMUM_DRAWDOWN_PCT and new_value > 5:
        issue = "must be at most 5"
    elif rule_key is RiskPolicyNumericRuleKey.MAXIMUM_TRADES_PER_DAY and (
        not new_value.is_integer() or new_value > 3
    ):
        issue = "must be an integer at most 3"
    elif rule_key is RiskPolicyNumericRuleKey.MINIMUM_RISK_REWARD and not (
        1.5 <= new_value <= 9999.9999
    ):
        issue = "must be between 1.5 and 9999.9999"
    elif rule_key is RiskPolicyNumericRuleKey.STALE_DATA_MAX_AGE_SECONDS and (
        not new_value.is_integer() or new_value > 10
    ):
        issue = "must be an integer at most 10"
    elif rule_key is RiskPolicyNumericRuleKey.MAXIMUM_SPREAD_POINTS and new_value > 3.5:
        issue = "must be at most 3.5"
    elif rule_key is RiskPolicyNumericRuleKey.NEWS_BLACKOUT_MINUTES and (
        not new_value.is_integer() or not 15 <= new_value <= 2_147_483_647
    ):
        issue = "must be an integer between 15 and 2147483647"
    if issue is not None:
        raise ValueError(f"{rule_key.value} {issue}.")


class RiskPolicyVersion(WireModel):
    """A versioned policy record; database authorization controls activation."""

    id: UUID
    owner_id: UUID
    risk_policy_id: UUID
    trading_account_id: UUID
    version: PositiveInt
    version_label: Identifier
    source_command_id: UUID | None
    environment: Literal["DEMO_ONLY"]
    canonical_symbol: Literal["XAUUSD"]
    maximum_permitted_volume: MaximumPermittedVolume
    maximum_open_positions: Literal[1]
    stop_loss_required: Literal[True]
    martingale_allowed: Literal[False]
    grid_trading_allowed: Literal[False]
    averaging_down_allowed: Literal[False]
    loss_based_volume_increase_allowed: Literal[False]
    risk_per_trade_pct: NonNegativeFloat
    daily_loss_limit_pct: NonNegativeFloat
    weekly_loss_limit_pct: NonNegativeFloat
    maximum_drawdown_pct: NonNegativeFloat
    maximum_trades_per_day: NonNegativeInt
    minimum_risk_reward: NonNegativeFloat
    stale_data_max_age_seconds: NonNegativeInt
    maximum_spread_points: NonNegativeFloat
    spread_warning_points: NonNegativeFloat
    news_blackout_minutes: NonNegativeInt
    proposal_expiry_seconds: PositiveInt
    entry_tolerance_points: NonNegativeFloat
    minimum_sample_size: NonNegativeInt
    require_calibrated_model: Literal[False]
    maximum_slippage_points: NonNegativeFloat
    automatic_retry_on_broker_reject: Literal[False]
    reason: Identifier
    created_by_type: RiskPolicyActorType
    created_by: Identifier
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_fixed_policy_limits(self) -> RiskPolicyVersion:
        if self.risk_per_trade_pct > 0.25:
            raise ValueError("Demo risk per trade cannot exceed 0.25 percent.")
        if self.daily_loss_limit_pct > 1:
            raise ValueError("Daily loss limit cannot exceed 1 percent.")
        if self.weekly_loss_limit_pct > 3:
            raise ValueError("Weekly loss limit cannot exceed 3 percent.")
        if self.maximum_drawdown_pct > 5:
            raise ValueError("Maximum drawdown cannot exceed 5 percent.")
        if self.maximum_trades_per_day > 3:
            raise ValueError("Maximum trades per day cannot exceed 3.")
        if self.minimum_risk_reward < 1.5:
            raise ValueError("Minimum Risk/Reward cannot be below 1.5.")
        if self.minimum_risk_reward > 9999.9999:
            raise ValueError("Minimum Risk/Reward exceeds database precision.")
        if self.stale_data_max_age_seconds > 10:
            raise ValueError("Stale-data maximum age cannot exceed 10 seconds.")
        if self.maximum_spread_points > 3.5:
            raise ValueError("Maximum spread cannot exceed 3.5 points.")
        if self.spread_warning_points > self.maximum_spread_points:
            raise ValueError("Spread warning must not exceed the maximum spread.")
        if self.news_blackout_minutes < 15:
            raise ValueError("News blackout cannot be below 15 minutes.")
        if self.news_blackout_minutes > 2_147_483_647:
            raise ValueError("News blackout exceeds the database integer range.")
        if self.proposal_expiry_seconds > 30:
            raise ValueError("Proposal expiry cannot exceed 30 seconds.")
        if self.entry_tolerance_points > 0.60:
            raise ValueError("Entry tolerance cannot exceed 0.60 points.")
        if self.minimum_sample_size < 30:
            raise ValueError("Minimum sample size cannot be below 30.")
        if self.maximum_slippage_points > 0.50:
            raise ValueError("Maximum slippage cannot exceed 0.50 points.")
        return self
