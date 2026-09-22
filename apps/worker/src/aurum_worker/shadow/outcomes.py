"""Conservative quote-observed research outcomes, never broker fills or PnL."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from aurum_worker.models.mt5 import LatestTickObservation, TickFreshness
from aurum_worker.shadow.models import ShadowCycle, ShadowOutcomeEvent


def observe_outcome(
    cycle: ShadowCycle,
    previous: ShadowOutcomeEvent | None,
    tick: LatestTickObservation | None,
    *,
    observed_at: datetime,
    restarted: bool = False,
) -> ShadowOutcomeEvent | None:
    cycle = ShadowCycle.model_validate(cycle.model_dump())
    if cycle.status != "PROPOSAL" or cycle.candidate is None or cycle.market is None:
        return None
    if previous is not None:
        previous = ShadowOutcomeEvent.model_validate(previous.model_dump())
        if (previous.cycle_id, previous.owner_id, previous.trading_account_id) != (
            cycle.id,
            cycle.owner_id,
            cycle.trading_account_id,
        ):
            raise ValueError("outcome parent mismatch")
        if previous.status != "OBSERVED":
            return None
    last_at = previous.observed_at if previous is not None else cycle.evaluated_at
    if observed_at <= last_at:
        # Duplicate/clock-regressed poll cannot append a misleading ordered event.
        return None
    sequence = previous.sequence + 1 if previous is not None else 1
    status: Literal[
        "OBSERVED", "STOP_OBSERVED", "TARGET_OBSERVED", "EXPIRED", "UNKNOWN"
    ] = "UNKNOWN"
    reason = "SOURCE_UNAVAILABLE"
    usable = False
    if tick is not None:
        tick = LatestTickObservation.model_validate(tick.model_dump())
        usable = (
            tick.source == "mt5"
            and tick.adapter_version == cycle.market.market_adapter_version
            and tick.symbol == cycle.market.broker_symbol
            and tick.freshness is TickFreshness.LIVE
            and timedelta(0) <= observed_at - tick.tick_at <= timedelta(seconds=5)
            and timedelta(0) <= observed_at - tick.observed_at <= timedelta(seconds=5)
            and tick.tick_at >= last_at
        )
    if restarted:
        reason = "RESTART_CONTINUITY_UNKNOWN"
    elif observed_at - last_at > timedelta(seconds=5):
        reason = "QUOTE_GAP"
    elif usable and tick is not None:
        candidate = cycle.candidate
        quote = tick.bid if candidate.direction == "BUY" else tick.ask
        if observed_at >= candidate.expires_at:
            status, reason = "EXPIRED", "RESEARCH_WINDOW_EXPIRED"
        elif (
            quote <= candidate.stop_loss_price
            if candidate.direction == "BUY"
            else quote >= candidate.stop_loss_price
        ):
            status, reason = "STOP_OBSERVED", "STOP_QUOTE_OBSERVED_NOT_FILL"
        elif (
            quote >= candidate.take_profit_price
            if candidate.direction == "BUY"
            else quote <= candidate.take_profit_price
        ):
            status, reason = "TARGET_OBSERVED", "TARGET_QUOTE_OBSERVED_NOT_FILL"
        elif sequence >= 32:
            reason = "OBSERVATION_LIMIT"
        else:
            status, reason = "OBSERVED", "QUOTE_OBSERVED_NOT_FILL"
    return ShadowOutcomeEvent(
        id=uuid5(NAMESPACE_URL, f"aurum:shadow-outcome:{cycle.id}:{sequence}"),
        owner_id=cycle.owner_id,
        trading_account_id=cycle.trading_account_id,
        cycle_id=cycle.id,
        sequence=sequence,
        observed_at=observed_at,
        status=status,
        reason_code=reason,
        bid=tick.bid if usable and tick is not None else None,
        ask=tick.ask if usable and tick is not None else None,
        price_source="mt5" if usable else "unavailable",
    )
