"""Versioned SMA/ATR research baseline. Direction is not trading authority."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    localcontext,
)
from uuid import NAMESPACE_URL, UUID, uuid5

from aurum_worker.models.trading import TradeDirection
from aurum_worker.shadow.market import MarketCapture
from aurum_worker.shadow.models import ShadowCheck, ShadowEligibility
from aurum_worker.shadow.risk import ShadowCandidate, ShadowRiskProvenance


def baseline_candidate(
    capture: MarketCapture,
    provenance: ShadowRiskProvenance,
    *,
    cycle_id: UUID,
    trace_id: str,
    evaluated_at: datetime,
    expiry_seconds: int,
) -> ShadowCandidate | None:
    """Outward tick-rounded 2 ATR stop, target 3 times stop, no volume."""
    features = capture.features
    if features.atr <= 0 or features.fast_sma == features.slow_sma:
        return None
    if not 1 <= expiry_seconds <= 30:
        raise ValueError("invalid proposal lifetime")
    direction = (
        TradeDirection.BUY
        if features.fast_sma > features.slow_sma
        else TradeDirection.SELL
    )
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        grid = capture.specification.tick_size
        quote = (
            capture.tick.ask if direction is TradeDirection.BUY else capture.tick.bid
        )
        # Entry is the actual side, not a silently rounded replacement quote.
        if quote % grid:
            raise ValueError("quote is off broker tick grid")
        distance = max(features.atr * 2, grid)
        if direction is TradeDirection.BUY:
            stop = ((quote - distance) / grid).to_integral_value(
                rounding=ROUND_FLOOR
            ) * grid
            target = ((quote + 3 * (quote - stop)) / grid).to_integral_value(
                rounding=ROUND_CEILING
            ) * grid
        else:
            stop = ((quote + distance) / grid).to_integral_value(
                rounding=ROUND_CEILING
            ) * grid
            target = ((quote - 3 * (stop - quote)) / grid).to_integral_value(
                rounding=ROUND_FLOOR
            ) * grid
        if stop <= Decimal(0) or target <= Decimal(0):
            raise ValueError("positive directional prices required")
        return ShadowCandidate(
            candidate_id=uuid5(NAMESPACE_URL, f"aurum:shadow-candidate:{cycle_id}"),
            provenance=provenance,
            market_trace_id=trace_id,
            created_at=evaluated_at,
            expires_at=evaluated_at + timedelta(seconds=expiry_seconds),
            direction=direction,
            entry_price=quote,
            stop_loss_price=stop,
            take_profit_price=target,
        )


def evaluate_baseline_eligibility(
    *, minimum_sample_size: int, risk_passed: bool
) -> ShadowEligibility:
    """No validated historical sample/model exists for this new research version.

    Quote observations are not independent cost-complete evaluation samples, so
    accumulating them cannot automatically promote this baseline.
    """
    return ShadowEligibility(
        outcome="BLOCK",
        checks=(
            ShadowCheck(code="STRATEGY_VERSION", passed=True),
            ShadowCheck(code="DATA_QUALITY", passed=True),
            ShadowCheck(code="REGIME_VALIDATION", passed=False),
            ShadowCheck(code="SAMPLE_SIZE", passed=False),
            ShadowCheck(code="CALIBRATION_NOT_REQUIRED", passed=True),
            ShadowCheck(code="HARD_RISK", passed=risk_passed),
            ShadowCheck(code="EXECUTION_DISABLED", passed=False),
        ),
        sample_count=0,
        minimum_sample_size=minimum_sample_size,
        calibrated=False,
    )
