"""Pure, fail-closed Shadow calculations; this module never grants eligibility.

The caller must supply current, independently obtained evidence. No adapter, clock,
configuration, persistence, or execution service is consulted here. USD valuation
uses the broker's explicitly reported loss/profit tick values per lot. Day/week
loss windows use UTC midnight/Monday and include costs and unrealized losses.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import (
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    TypeAdapter,
    field_validator,
    model_validator,
)

from aurum_worker.models.base import CurrencyCode, Identifier
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountTradeMode,
    BrokerSymbolObservation,
    ConfirmedSymbolBinding,
    LatestTickObservation,
    ReconciliationOutcome,
    ReconciliationReport,
    SpecificationFingerprint,
    SymbolTradeMode,
    SymbolUsabilityState,
    TickFreshness,
)
from aurum_worker.models.risk_policy import RiskPolicyVersion
from aurum_worker.models.trading import TradeDirection


def _decimal_input(value: object) -> Decimal:
    if not isinstance(value, Decimal | str):
        raise ValueError("decimal evidence must be a Decimal or decimal string")
    try:
        result = Decimal(value)
    except ArithmeticError as exc:
        raise ValueError("invalid decimal evidence") from exc
    if not result.is_finite():
        raise ValueError("decimal evidence must be finite")
    return result


InputDecimal = Annotated[
    Decimal,
    BeforeValidator(_decimal_input),
    Field(allow_inf_nan=False, max_digits=28, decimal_places=12),
]
PositiveInput = Annotated[InputDecimal, Field(gt=0)]
NonNegativeInput = Annotated[InputDecimal, Field(ge=0)]
NonNegativeResult = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
StrictCount = Annotated[int, Field(strict=True, ge=0)]
ContextAge = Annotated[int, Field(strict=True, ge=1, le=600)]
_INPUT_DECIMAL = TypeAdapter(InputDecimal)


class ShadowRiskModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, revalidate_instances="always"
    )


class ShadowRiskProvenance(ShadowRiskModel):
    """Expected identity shared by all explicit evidence contexts."""

    source: Literal["mt5", "fake_mt5"]
    adapter_version: Identifier
    market_adapter_version: Identifier
    owner_id: UUID
    trading_account_id: UUID
    account_fingerprint: Identifier
    server_fingerprint: Identifier
    broker_symbol: Identifier
    specification_fingerprint: SpecificationFingerprint
    risk_policy_version_id: UUID
    risk_policy_version: Annotated[int, Field(strict=True, ge=1)]


class ShadowCandidate(ShadowRiskModel):
    """A calculation candidate, with mandatory prices and no executable volume."""

    candidate_id: UUID
    provenance: ShadowRiskProvenance
    market_trace_id: Identifier
    created_at: AwareDatetime
    expires_at: AwareDatetime
    direction: TradeDirection
    entry_price: PositiveInput
    stop_loss_price: PositiveInput
    take_profit_price: PositiveInput


class ShadowAccountRiskState(ShadowRiskModel):
    provenance: ShadowRiskProvenance
    trace_id: Identifier
    observed_at: AwareDatetime
    currency: CurrencyCode | None
    equity: PositiveInput | None
    day_start_equity: PositiveInput | None
    week_start_equity: PositiveInput | None
    peak_equity: PositiveInput | None
    daily_loss_amount: NonNegativeInput | None
    weekly_loss_amount: NonNegativeInput | None
    day_started_at: AwareDatetime | None
    week_started_at: AwareDatetime | None
    losses_include_unrealized_and_costs: StrictBool | None
    ledger_complete: StrictBool | None
    trades_today: StrictCount | None
    open_position_count: StrictCount | None
    active_order_count: StrictCount | None


class ShadowSafetyContext(ShadowRiskModel):
    provenance: ShadowRiskProvenance
    trace_id: Identifier
    observed_at: AwareDatetime
    terminal_connected: StrictBool | None
    worker_healthy: StrictBool | None
    database_healthy: StrictBool | None
    clock_synchronized: StrictBool | None
    policy_active: StrictBool | None
    active_policy_version_id: UUID | None
    reconciliation_required: StrictBool | None
    emergency_stop_requested: StrictBool | None
    emergency_stop_active: StrictBool | None
    resume_required: StrictBool | None
    news_blackout_clear: StrictBool | None
    news_checked_from: AwareDatetime | None
    news_checked_until: AwareDatetime | None


class ShadowCostContext(ShadowRiskModel):
    """Conservative costs in USD per lot; slippage is charged on BOTH sides."""

    provenance: ShadowRiskProvenance
    trace_id: Identifier
    observed_at: AwareDatetime
    currency: CurrencyCode | None
    commission_round_trip_per_lot: NonNegativeInput | None
    swap_allowance_per_lot: NonNegativeInput | None
    slippage_points_per_side: NonNegativeInput | None


def _revalidate[M: BaseModel](model_type: type[M], value: object) -> M | None:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python", by_alias=True)
    return model_type.model_validate(value)


class ShadowRiskInput(ShadowRiskModel):
    evaluated_at: AwareDatetime
    provenance: ShadowRiskProvenance
    candidate: ShadowCandidate
    account: AccountObservation | None
    account_risk: ShadowAccountRiskState | None
    safety: ShadowSafetyContext | None
    costs: ShadowCostContext | None
    tick: LatestTickObservation | None
    specification: BrokerSymbolObservation | None
    confirmed_binding: ConfirmedSymbolBinding | None
    reconciliation: ReconciliationReport | None
    policy: RiskPolicyVersion | None
    reconciliation_adapter_version: Identifier
    maximum_tick_age_seconds: Annotated[int, Field(strict=True, ge=1, le=300)]
    maximum_reconciliation_age_seconds: ContextAge
    maximum_specification_age_seconds: ContextAge

    @field_validator("account", mode="before")
    @classmethod
    def validate_account(cls, value: object) -> AccountObservation | None:
        return _revalidate(AccountObservation, value)

    @field_validator("tick", mode="before")
    @classmethod
    def validate_tick(cls, value: object) -> LatestTickObservation | None:
        result = _revalidate(LatestTickObservation, value)
        if result is not None:
            for number in (
                result.bid,
                result.ask,
                result.spread_price,
                result.spread_points,
                result.age_seconds,
            ):
                _INPUT_DECIMAL.validate_python(number)
        return result

    @field_validator("specification", mode="before")
    @classmethod
    def validate_specification(cls, value: object) -> BrokerSymbolObservation | None:
        result = _revalidate(BrokerSymbolObservation, value)
        if result is not None:
            for number in (
                result.point,
                result.tick_size,
                result.tick_value,
                result.tick_value_profit,
                result.tick_value_loss,
                result.contract_size,
                result.minimum_volume,
                result.maximum_volume,
                result.volume_step,
            ):
                _INPUT_DECIMAL.validate_python(number)
        return result

    @field_validator("confirmed_binding", mode="before")
    @classmethod
    def validate_binding(cls, value: object) -> ConfirmedSymbolBinding | None:
        return _revalidate(ConfirmedSymbolBinding, value)

    @field_validator("reconciliation", mode="before")
    @classmethod
    def validate_reconciliation(cls, value: object) -> ReconciliationReport | None:
        return _revalidate(ReconciliationReport, value)

    @field_validator("policy", mode="before")
    @classmethod
    def validate_policy(cls, value: object) -> RiskPolicyVersion | None:
        result = _revalidate(RiskPolicyVersion, value)
        if result is not None:
            # Pydantic Literal[True/False/1] accepts equal ints/bools; inspect the
            # original payload before those literals can erase that distinction.
            payload = (
                value.model_dump(mode="python", by_alias=True)
                if isinstance(value, BaseModel)
                else value
            )
            if isinstance(payload, dict):
                for name in (
                    "stopLossRequired",
                    "martingaleAllowed",
                    "gridTradingAllowed",
                    "averagingDownAllowed",
                    "lossBasedVolumeIncreaseAllowed",
                    "requireCalibratedModel",
                    "automaticRetryOnBrokerReject",
                ):
                    if type(payload.get(name)) is not bool:
                        raise ValueError("policy safety flags must be strict booleans")
                if type(payload.get("maximumOpenPositions")) is not int:
                    raise ValueError("policy position count must be a strict integer")
        return result


class ShadowRiskCheck(ShadowRiskModel):
    code: Identifier
    passed: StrictBool
    hard: Literal[True]
    detail: Annotated[str, Field(strict=True, min_length=1, max_length=240)]


class ShadowRiskCalculation(ShadowRiskModel):
    valuation_source: Literal["broker_tick_values_usd"]
    point_size: NonNegativeResult
    spread_points: NonNegativeResult
    effective_entry_price: NonNegativeResult
    per_trade_budget_usd: NonNegativeResult
    remaining_daily_budget_usd: NonNegativeResult
    remaining_weekly_budget_usd: NonNegativeResult
    remaining_drawdown_budget_usd: NonNegativeResult
    risk_budget_usd: NonNegativeResult
    commission_and_swap_per_lot_usd: NonNegativeResult
    two_sided_slippage_per_lot_usd: NonNegativeResult
    loss_per_lot_usd: NonNegativeResult
    net_reward_per_lot_usd: Annotated[Decimal, Field(allow_inf_nan=False)]
    net_risk_reward: Annotated[Decimal, Field(allow_inf_nan=False)]


class ShadowRiskEvidence(ShadowRiskModel):
    calculator_version: Literal["shadow-risk-v1"]
    outcome: Literal["PASS", "BLOCK"]
    grants_eligibility: Literal[False]
    evaluated_at: AwareDatetime
    candidate_id: UUID
    provenance: ShadowRiskProvenance
    evidence_trace_ids: tuple[Identifier, ...]
    checks: tuple[ShadowRiskCheck, ...]
    calculation: ShadowRiskCalculation | None
    calculated_volume: NonNegativeResult | None
    estimated_loss_usd: NonNegativeResult | None
    estimated_net_reward_usd: NonNegativeResult | None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        passed = all(check.passed for check in self.checks)
        if not self.checks or (self.outcome == "PASS") != passed:
            raise ValueError("outcome must agree with all hard checks")
        amounts = (
            self.calculated_volume,
            self.estimated_loss_usd,
            self.estimated_net_reward_usd,
        )
        if self.outcome == "BLOCK" and any(item is not None for item in amounts):
            raise ValueError("blocked calculations cannot provide a volume or amounts")
        if self.outcome == "PASS" and (
            self.calculation is None
            or any(item is None for item in amounts)
            or self.calculated_volume is None
            or not Decimal(0) < self.calculated_volume <= Decimal("0.01")
        ):
            raise ValueError("passing calculations require bounded volume and amounts")
        return self


def _fresh(now: datetime, observed: datetime, limit: int) -> bool:
    return timedelta(0) <= now - observed <= timedelta(seconds=limit)


def evaluate_shadow_risk(value: ShadowRiskInput) -> ShadowRiskEvidence:
    """Validate and calculate Shadow evidence; malformed input raises validation.

    Validly encoded but missing, stale, inconsistent or unsafe evidence returns
    BLOCK. PASS is a calculation result only and always grants_eligibility=False.
    Decimal precision is local and independent of the caller's numeric context.
    """

    with localcontext(
        Context(
            prec=64,
            rounding=ROUND_HALF_EVEN,
            Emin=-999999,
            Emax=999999,
            capitals=1,
            clamp=0,
            flags=[],
            traps=[InvalidOperation, DivisionByZero, Overflow],
        )
    ):
        value = ShadowRiskInput.model_validate(
            value.model_dump(mode="python", warnings=False)
        )
        return _evaluate(value)


def _evaluate(value: ShadowRiskInput) -> ShadowRiskEvidence:
    checks: list[ShadowRiskCheck] = []
    trace_ids = [value.candidate.market_trace_id]
    calculation: ShadowRiskCalculation | None = None
    volume: Decimal | None = None

    def check(code: str, passed: bool, detail: str) -> None:
        checks.append(
            ShadowRiskCheck(code=code, passed=passed, hard=True, detail=detail)
        )

    def result() -> ShadowRiskEvidence:
        passed = all(item.passed for item in checks)
        selected = volume if passed else None
        return ShadowRiskEvidence(
            calculator_version="shadow-risk-v1",
            outcome="PASS" if passed else "BLOCK",
            grants_eligibility=False,
            evaluated_at=value.evaluated_at,
            candidate_id=value.candidate.candidate_id,
            provenance=value.provenance,
            evidence_trace_ids=tuple(trace_ids),
            checks=tuple(checks),
            calculation=calculation,
            calculated_volume=selected,
            estimated_loss_usd=(
                selected * calculation.loss_per_lot_usd
                if selected is not None and calculation is not None
                else None
            ),
            estimated_net_reward_usd=(
                selected * calculation.net_reward_per_lot_usd
                if selected is not None and calculation is not None
                else None
            ),
        )

    account, state, safety, costs = (
        value.account,
        value.account_risk,
        value.safety,
        value.costs,
    )
    tick, spec, binding, rec, policy = (
        value.tick,
        value.specification,
        value.confirmed_binding,
        value.reconciliation,
        value.policy,
    )
    for name, evidence in (
        ("ACCOUNT_AVAILABLE", account),
        ("ACCOUNT_RISK_AVAILABLE", state),
        ("SAFETY_AVAILABLE", safety),
        ("COSTS_AVAILABLE", costs),
        ("TICK_AVAILABLE", tick),
        ("SPECIFICATION_AVAILABLE", spec),
        ("CONFIRMED_BINDING_AVAILABLE", binding),
        ("RECONCILIATION_AVAILABLE", rec),
        ("POLICY_AVAILABLE", policy),
    ):
        check(name, evidence is not None, "Explicit current evidence is required.")
    if (
        account is None
        or state is None
        or safety is None
        or costs is None
        or tick is None
        or spec is None
        or binding is None
        or rec is None
        or policy is None
    ):
        return result()

    now, expected, candidate = (
        value.evaluated_at,
        value.provenance,
        value.candidate,
    )
    age = policy.stale_data_max_age_seconds
    check(
        "PRODUCTION_SOURCE",
        expected.source == "mt5",
        "Production Shadow calculations require mt5 source evidence.",
    )
    for name, evidence in (
        ("ACCOUNT_RISK", state),
        ("SAFETY", safety),
        ("COSTS", costs),
    ):
        trace_ids.append(evidence.trace_id)
        check(
            name + "_PROVENANCE",
            evidence.provenance == expected,
            "Context identity and source must match the requested binding.",
        )
        check(
            name + "_FRESH",
            _fresh(now, evidence.observed_at, age),
            "Context must be current and cannot come from the future.",
        )
    for name, observation, limit in (
        ("ACCOUNT", account, age),
        ("TICK", tick, age),
        ("SPECIFICATION", spec, value.maximum_specification_age_seconds),
        ("RECONCILIATION", rec, value.maximum_reconciliation_age_seconds),
    ):
        expected_version = (
            value.reconciliation_adapter_version
            if name == "RECONCILIATION"
            else expected.market_adapter_version
            if name == "TICK"
            else expected.adapter_version
        )
        trace_ids.append(observation.trace_id)
        check(
            name + "_SOURCE",
            observation.source == expected.source
            and observation.adapter_version == expected_version,
            "Observation source and adapter version must match the binding.",
        )
        check(
            name + "_FRESH",
            _fresh(now, observation.observed_at, limit),
            "Observation must be current and cannot come from the future.",
        )
    check(
        "DEMO_ACCOUNT_BINDING",
        account.trade_mode is AccountTradeMode.DEMO
        and account.account_fingerprint == expected.account_fingerprint
        and account.server_fingerprint == expected.server_fingerprint,
        "Only the explicitly bound Demo account is supported.",
    )
    check(
        "USD_VALUATION",
        account.currency == state.currency == costs.currency == "USD",
        "Unknown or non-USD currency needs unavailable conversion evidence.",
    )
    check(
        "SYMBOL_BINDING",
        spec.broker_symbol
        == tick.symbol
        == binding.broker_symbol
        == expected.broker_symbol
        and spec.specification_fingerprint
        == binding.confirmed_specification_fingerprint
        == expected.specification_fingerprint
        and binding.owner_id == str(expected.owner_id)
        and binding.trading_account_id == str(expected.trading_account_id)
        and binding.confirmed_at <= now,
        "Current symbol specification must match its confirmed account binding.",
    )
    check(
        "POLICY_BINDING",
        policy.id == expected.risk_policy_version_id == safety.active_policy_version_id
        and policy.version == expected.risk_policy_version
        and policy.owner_id == expected.owner_id
        and policy.trading_account_id == expected.trading_account_id
        and policy.created_at <= now
        and safety.policy_active is True,
        "The current active policy version must match the candidate account and owner.",
    )
    check(
        "CANDIDATE_CURRENT",
        candidate.provenance == expected
        and candidate.market_trace_id == tick.trace_id
        and _fresh(now, candidate.created_at, policy.proposal_expiry_seconds)
        and candidate.created_at < candidate.expires_at
        and now < candidate.expires_at
        and candidate.expires_at - candidate.created_at
        <= timedelta(seconds=policy.proposal_expiry_seconds),
        "Candidate binding, quote trace, creation and expiry must be current.",
    )
    check(
        "OPERATIONAL_SAFETY",
        safety.terminal_connected is True
        and safety.worker_healthy is True
        and safety.database_healthy is True
        and safety.clock_synchronized is True
        and safety.reconciliation_required is False,
        "Healthy terminal, Worker, database, clock and reconciliation required.",
    )
    check(
        "EMERGENCY_CLEAR",
        safety.emergency_stop_requested is False
        and safety.emergency_stop_active is False
        and safety.resume_required is False,
        "Emergency Stop and resume state must all be explicitly clear.",
    )
    blackout = timedelta(minutes=policy.news_blackout_minutes)
    check(
        "NEWS_CLEAR",
        safety.news_blackout_clear is True
        and safety.news_checked_from is not None
        and safety.news_checked_until is not None
        and now - safety.news_checked_from >= blackout
        and safety.news_checked_until - now >= blackout,
        "Confirmed clear news coverage must span the complete policy blackout window.",
    )
    check(
        "RECONCILIATION_MATCHED",
        rec.outcome is ReconciliationOutcome.MATCHED
        and rec.account_fingerprint == expected.account_fingerprint
        and rec.server_fingerprint == expected.server_fingerprint
        and rec.broker_symbol == expected.broker_symbol
        and rec.symbol_specification_fingerprint == expected.specification_fingerprint
        and rec.started_at <= rec.observed_at <= rec.completed_at <= now
        and _fresh(now, rec.completed_at, value.maximum_reconciliation_age_seconds)
        and rec.order_history_evidence.requested_start_at
        == rec.deal_history_evidence.requested_start_at
        and rec.order_history_evidence.requested_end_at
        == rec.deal_history_evidence.requested_end_at
        == rec.started_at
        and all(
            item.query_completed_at is not None
            and rec.started_at <= item.query_completed_at <= rec.completed_at
            and _fresh(
                now, item.requested_end_at, value.maximum_reconciliation_age_seconds
            )
            for item in (rec.order_history_evidence, rec.deal_history_evidence)
        ),
        "Current successful reconciliation with matching identity/history required.",
    )
    check(
        "NO_OPEN_EXPOSURE",
        state.open_position_count == 0
        and state.active_order_count == 0
        and rec.open_position_count == 0
        and rec.active_order_count == 0,
        "Any open Position, active Order, or unknown current count blocks calculation.",
    )
    check(
        "DAILY_TRADE_LIMIT",
        state.trades_today is not None
        and state.trades_today < min(3, policy.maximum_trades_per_day),
        "The policy and absolute three-trade daily limits apply.",
    )
    utc_now = now.astimezone(UTC)
    day_start = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
    check(
        "LOSS_LEDGER_COMPLETE",
        state.ledger_complete is True
        and state.losses_include_unrealized_and_costs is True
        and state.day_started_at == day_start
        and state.week_started_at == day_start - timedelta(days=day_start.weekday())
        and state.equity is not None
        and state.day_start_equity is not None
        and state.week_start_equity is not None
        and state.peak_equity is not None
        and state.peak_equity >= state.equity
        and state.daily_loss_amount is not None
        and state.weekly_loss_amount is not None,
        "UTC day/week loss, equity and peak evidence including costs required.",
    )
    maximum_live_age = min(
        timedelta(seconds=age),
        timedelta(milliseconds=min(5000, value.maximum_tick_age_seconds * 500)),
    )
    check(
        "TICK_CURRENT",
        tick.freshness is TickFreshness.LIVE
        and timedelta(0) <= now - tick.tick_at <= maximum_live_age
        and tick.tick_at <= tick.observed_at
        and tick.age_seconds
        == Decimal(str((tick.observed_at - tick.tick_at).total_seconds())),
        "Current LIVE age must satisfy adapter half-age, 5s cap and stricter policy.",
    )
    spread_points = (tick.ask - tick.bid) / spec.point
    check(
        "SPREAD_LIMIT",
        tick.spread_points == spread_points
        and spread_points <= Decimal(str(policy.maximum_spread_points)),
        "Spread points equal (ask minus bid) divided by broker point size.",
    )
    check(
        "SYMBOL_USABLE",
        spec.usability_state is SymbolUsabilityState.USABLE
        and spec.unusable_reason is None
        and spec.trade_mode
        in (
            SymbolTradeMode.FULL,
            SymbolTradeMode.LONG_ONLY
            if candidate.direction is TradeDirection.BUY
            else SymbolTradeMode.SHORT_ONLY,
        )
        and spec.tick_value_loss > 0
        and spec.tick_value_profit > 0,
        "Usable direction and positive broker loss/profit tick values required.",
    )
    buy = candidate.direction is TradeDirection.BUY
    quote_entry = tick.ask if buy else tick.bid
    effective_entry = (
        max(candidate.entry_price, quote_entry)
        if buy
        else min(candidate.entry_price, quote_entry)
    )
    stop_distance = (
        effective_entry - candidate.stop_loss_price
        if buy
        else candidate.stop_loss_price - effective_entry
    )
    reward_distance = (
        candidate.take_profit_price - effective_entry
        if buy
        else effective_entry - candidate.take_profit_price
    )
    check(
        "DIRECTIONAL_SL_TP",
        (
            candidate.stop_loss_price
            < candidate.entry_price
            < candidate.take_profit_price
            if buy
            else candidate.take_profit_price
            < candidate.entry_price
            < candidate.stop_loss_price
        )
        and stop_distance > 0
        and reward_distance > 0,
        "Mandatory Stop Loss and Take Profit must be correctly ordered for direction.",
    )
    check(
        "ENTRY_TOLERANCE",
        abs(candidate.entry_price - quote_entry)
        <= Decimal(str(policy.entry_tolerance_points)) * spec.point,
        "BUY uses ask, SELL uses bid; entry tolerance is measured in broker points.",
    )
    check(
        "TICK_GRID",
        all(
            price % spec.tick_size == 0
            for price in (
                candidate.entry_price,
                candidate.stop_loss_price,
                candidate.take_profit_price,
                tick.bid,
                tick.ask,
            )
        ),
        "Candidate and quote prices must be exact multiples of broker tick size.",
    )
    exit_side = tick.bid if buy else tick.ask
    stop_from_exit = (
        exit_side - candidate.stop_loss_price
        if buy
        else candidate.stop_loss_price - exit_side
    )
    target_from_exit = (
        candidate.take_profit_price - exit_side
        if buy
        else exit_side - candidate.take_profit_price
    )
    check(
        "BROKER_STOPS",
        min(stop_from_exit, target_from_exit) > 0
        and min(stop_from_exit, target_from_exit) >= spec.stops_level * spec.point,
        "SL/TP must respect broker stop distance from the closing quote side.",
    )
    check(
        "COSTS_COMPLETE",
        costs.commission_round_trip_per_lot is not None
        and costs.swap_allowance_per_lot is not None
        and costs.slippage_points_per_side is not None
        and costs.slippage_points_per_side
        <= Decimal(str(policy.maximum_slippage_points)),
        "Explicit commission, swap and policy-bounded per-side slippage required.",
    )
    if not all(item.passed for item in checks):
        return result()

    # The complete-ledger and complete-cost checks above narrow unknown values.
    assert state.equity is not None
    assert state.day_start_equity is not None
    assert state.week_start_equity is not None
    assert state.peak_equity is not None
    assert state.daily_loss_amount is not None
    assert state.weekly_loss_amount is not None
    assert costs.commission_round_trip_per_lot is not None
    assert costs.swap_allowance_per_lot is not None
    assert costs.slippage_points_per_side is not None
    zero, hundred = Decimal(0), Decimal(100)
    per_trade = state.equity * Decimal(str(policy.risk_per_trade_pct)) / hundred
    daily = max(
        zero,
        state.day_start_equity * Decimal(str(policy.daily_loss_limit_pct)) / hundred
        - max(state.daily_loss_amount, state.day_start_equity - state.equity),
    )
    weekly = max(
        zero,
        state.week_start_equity * Decimal(str(policy.weekly_loss_limit_pct)) / hundred
        - max(state.weekly_loss_amount, state.week_start_equity - state.equity),
    )
    drawdown = max(
        zero,
        state.peak_equity * Decimal(str(policy.maximum_drawdown_pct)) / hundred
        - (state.peak_equity - state.equity),
    )
    budget = min(per_trade, daily, weekly, drawdown)
    commission_swap = costs.commission_round_trip_per_lot + costs.swap_allowance_per_lot
    slippage = (
        Decimal(2)
        * costs.slippage_points_per_side
        * spec.point
        / spec.tick_size
        * max(spec.tick_value_loss, spec.tick_value_profit)
    )
    # Opening BUY ask / SELL bid already includes spread in the price distances;
    # adding a second spread charge here would double count it.
    loss = (
        stop_distance / spec.tick_size * spec.tick_value_loss
        + commission_swap
        + slippage
    )
    reward = (
        reward_distance / spec.tick_size * spec.tick_value_profit
        - commission_swap
        - slippage
    )
    calculation = ShadowRiskCalculation(
        valuation_source="broker_tick_values_usd",
        point_size=spec.point,
        spread_points=spread_points,
        effective_entry_price=effective_entry,
        per_trade_budget_usd=per_trade,
        remaining_daily_budget_usd=daily,
        remaining_weekly_budget_usd=weekly,
        remaining_drawdown_budget_usd=drawdown,
        risk_budget_usd=budget,
        commission_and_swap_per_lot_usd=commission_swap,
        two_sided_slippage_per_lot_usd=slippage,
        loss_per_lot_usd=loss,
        net_reward_per_lot_usd=reward,
        net_risk_reward=reward / loss,
    )
    check(
        "RISK_BUDGET", budget > 0, "Every applicable risk budget must remain positive."
    )
    check(
        "NET_RISK_REWARD",
        reward >= Decimal(str(policy.minimum_risk_reward)) * loss,
        "Net reward after both slippage sides, commission and swap must meet RR.",
    )
    cap = min(
        Decimal("0.01"),
        Decimal(str(policy.maximum_permitted_volume)),
        spec.maximum_volume,
        budget / loss,
    )
    volume = (cap / spec.volume_step).to_integral_value(
        rounding=ROUND_FLOOR
    ) * spec.volume_step
    check(
        "BROKER_MINIMUM_VOLUME",
        volume > 0 and volume >= spec.minimum_volume,
        "Floor to broker volume step; a minimum lot above the budget always blocks.",
    )
    check(
        "SIZED_LOSS_WITHIN_BUDGET",
        volume * loss <= budget,
        "The calculated stop loss including all costs must fit every remaining budget.",
    )
    return result()
