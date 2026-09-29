from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from mt5_factories import NOW, tick
from test_shadow_pipeline import pipeline

from aurum_worker.models.mt5 import LatestTickObservation
from aurum_worker.shadow.models import ShadowCycle, ShadowOutcomeEvent
from aurum_worker.shadow.outcomes import observe_outcome


def proposal(direction: str = "BUY") -> ShadowCycle:
    host, _ = pipeline(direction=direction)
    cycle = host.run_cycle().cycle
    assert cycle is not None and cycle.status == "PROPOSAL"
    return cycle


def quote(
    seconds: int = 1, bid: str = "2000", ask: str = "2000.02"
) -> LatestTickObservation:
    return tick().model_copy(
        update={
            "source": "mt5",
            "observed_at": NOW + timedelta(seconds=seconds),
            "tick_at": NOW + timedelta(seconds=seconds),
            "age_seconds": Decimal(0),
            "bid": Decimal(bid),
            "ask": Decimal(ask),
            "spread_price": Decimal(ask) - Decimal(bid),
            "spread_points": (Decimal(ask) - Decimal(bid)) / Decimal("0.01"),
        }
    )


@pytest.mark.parametrize("direction", ["BUY", "SELL"])
def test_observed_quotes_are_not_fills_or_pnl(direction: str) -> None:
    event = observe_outcome(
        proposal(direction), None, quote(), observed_at=NOW + timedelta(seconds=1)
    )
    assert event is not None and event.status == "OBSERVED"
    assert event.simulation is True and event.grants_eligibility is False
    assert event.net_pnl_usd is None and event.sequence == 1
    assert ShadowOutcomeEvent.model_validate_json(event.model_dump_json()) == event


@pytest.mark.parametrize(
    "direction,target", [("BUY", False), ("BUY", True), ("SELL", False), ("SELL", True)]
)
def test_threshold_uses_close_quote_side(direction: str, target: bool) -> None:
    cycle = proposal(direction)
    assert cycle.candidate is not None
    threshold = (
        cycle.candidate.take_profit_price if target else cycle.candidate.stop_loss_price
    )
    bid, ask = (
        (threshold, threshold + Decimal("0.02"))
        if direction == "BUY"
        else (threshold - Decimal("0.02"), threshold)
    )
    event = observe_outcome(
        cycle,
        None,
        quote(bid=str(bid), ask=str(ask)),
        observed_at=NOW + timedelta(seconds=1),
    )
    assert event is not None and event.status == (
        "TARGET_OBSERVED" if target else "STOP_OBSERVED"
    )
    assert event.net_pnl_usd is None


@pytest.mark.parametrize(
    "issue",
    ["missing", "gap", "future", "stale", "fake", "version", "symbol", "restart"],
)
def test_uncertainty_cannot_become_favorable_outcome(issue: str) -> None:
    cycle = proposal()
    current = quote(bid="3000", ask="3000.02")
    seconds = 1
    if issue == "gap":
        seconds = 6
    if issue == "future":
        current = current.model_copy(update={"tick_at": NOW + timedelta(seconds=2)})
    if issue == "stale":
        current = current.model_copy(update={"tick_at": NOW - timedelta(seconds=6)})
    if issue == "fake":
        current = current.model_copy(update={"source": "fake_mt5"})
    if issue == "version":
        current = current.model_copy(update={"adapter_version": "other"})
    if issue == "symbol":
        current = current.model_copy(update={"symbol": "EURUSD"})
    event = observe_outcome(
        cycle,
        None,
        None if issue == "missing" else current,
        observed_at=NOW + timedelta(seconds=seconds),
        restarted=issue == "restart",
    )
    assert event is not None and event.status == "UNKNOWN"
    assert event.net_pnl_usd is None


def test_terminal_state_cannot_reverse_and_duplicate_time_cannot_append() -> None:
    cycle = proposal()
    event = observe_outcome(cycle, None, None, observed_at=NOW + timedelta(seconds=1))
    assert event is not None
    assert (
        observe_outcome(cycle, event, quote(2), observed_at=NOW + timedelta(seconds=2))
        is None
    )
    assert observe_outcome(cycle, None, quote(), observed_at=NOW) is None


def test_contiguous_expiry_and_sequence_have_no_hypothetical_position() -> None:
    cycle = proposal()
    event = None
    for seconds in range(1, 31):
        event = observe_outcome(
            cycle, event, quote(seconds), observed_at=NOW + timedelta(seconds=seconds)
        )
        assert event is not None
        assert event.sequence == seconds
    assert event is not None and event.status == "EXPIRED"
    assert event.net_pnl_usd is None


@pytest.mark.parametrize("bid", ["1000", "3000"])
def test_exact_expiry_precedes_threshold_observation(bid: str) -> None:
    cycle = proposal()
    previous = None
    for second in range(1, 30):
        previous = observe_outcome(
            cycle, previous, quote(second), observed_at=NOW + timedelta(seconds=second)
        )
    event = observe_outcome(
        cycle,
        previous,
        quote(30, bid, str(Decimal(bid) + Decimal("0.02"))),
        observed_at=NOW + timedelta(seconds=30),
    )
    assert event is not None and event.status == "EXPIRED"


def test_wrong_parent_is_rejected() -> None:
    cycle = proposal()
    event = observe_outcome(
        cycle, None, quote(), observed_at=NOW + timedelta(seconds=1)
    )
    assert event is not None
    event = event.model_copy(
        update={"cycle_id": UUID("00000000-0000-4000-8000-000000000999")}
    )
    with pytest.raises(ValueError):
        observe_outcome(cycle, event, quote(2), observed_at=NOW + timedelta(seconds=2))


def test_wait_or_block_cannot_create_outcomes() -> None:
    host, _ = pipeline(direction="WAIT")
    cycle = host.run_cycle().cycle
    assert cycle is not None
    assert (
        observe_outcome(cycle, None, quote(), observed_at=NOW + timedelta(seconds=1))
        is None
    )
