"""Vertical Worker tests use test ports; they do not establish native readiness."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal, localcontext
from uuid import UUID

import pytest
from mt5_factories import NOW
from pydantic import ValidationError
from shadow_factories import (
    CompleteTestEvidence,
    MemoryJournal,
    MemoryReplayArchive,
    control,
    market_service,
)

from aurum_worker.shadow.context import MissingEvidenceProvider
from aurum_worker.shadow.market import MarketCapture
from aurum_worker.shadow.models import ShadowCycle
from aurum_worker.shadow.pipeline import ShadowPipeline, cycle_identity


def pipeline(
    *,
    direction: str = "BUY",
    complete: bool = True,
    journal: MemoryJournal | None = None,
) -> tuple[ShadowPipeline, MemoryJournal]:
    market, config = market_service(direction=direction)
    journal = journal or MemoryJournal()
    context = control()
    return ShadowPipeline(
        market,
        journal,
        CompleteTestEvidence() if complete else MissingEvidenceProvider(),
        config,
        owner_id=context.owner_id,
        trading_account_id=context.trading_account_id,
        replay_archive=MemoryReplayArchive(),
        clock=lambda: NOW,
    ), journal


@pytest.mark.parametrize("direction", ["BUY", "SELL"])
def test_source_pipeline_to_durable_research_proposal(direction: str) -> None:
    host, journal = pipeline(direction=direction)
    result = host.run_cycle()
    assert result.persistence_code == "CYCLE_RECORDED"
    cycle = result.cycle
    assert cycle is not None, result
    assert cycle.status == "PROPOSAL", cycle.reason_codes
    assert cycle.candidate is not None and cycle.candidate.direction == direction
    assert cycle.risk is not None and cycle.risk.calculated_volume == Decimal("0.01")
    assert cycle.eligibility is not None and cycle.eligibility.outcome == "BLOCK"
    assert cycle.grants_eligibility is False
    assert len(journal.cycles) == 1
    assert ShadowCycle.model_validate_json(cycle.model_dump_json()) == cycle


def test_missing_external_sources_are_durably_blocked_not_zero_fallback() -> None:
    host, _ = pipeline(complete=False)
    cycle = host.run_cycle().cycle
    assert cycle is not None and cycle.status == "BLOCK"
    assert {"ACCOUNT_RISK_AVAILABLE", "SAFETY_AVAILABLE", "COSTS_AVAILABLE"} <= set(
        cycle.reason_codes
    )
    assert cycle.risk is not None and cycle.risk.calculated_volume is None


def test_wait_is_durable_and_never_sized() -> None:
    host, _ = pipeline(direction="WAIT")
    cycle = host.run_cycle().cycle
    assert cycle is not None and cycle.status == "WAIT"
    assert cycle.candidate is None and cycle.risk is None
    assert cycle.market is not None


def test_restart_and_duplicate_do_not_recapture_or_duplicate() -> None:
    host, journal = pipeline()
    first = host.run_cycle()
    assert first.cycle is not None
    second = host.run_cycle()
    fresh_host, _ = pipeline(journal=journal)
    third = fresh_host.run_cycle()
    assert first.cycle == second.cycle == third.cycle
    assert second.persistence_code == third.persistence_code == "IDEMPOTENT_REPLAY"
    assert journal.writes == 1


def test_uncertain_write_replays_exact_envelope_before_new_work() -> None:
    journal = MemoryJournal(uncertain_write=True)
    host, _ = pipeline(journal=journal)
    assert host.run_cycle().persistence_code == "PERSISTENCE_UNAVAILABLE"
    first = next(iter(journal.cycles.values()))
    journal.uncertain_write = False
    host.clock = lambda: NOW + timedelta(minutes=1)
    replay = host.run_cycle()
    assert replay.persistence_code == "IDEMPOTENT_REPLAY" and replay.cycle == first
    assert len(journal.cycles) == 1


def test_database_read_failure_cannot_invent_durable_block() -> None:
    host, journal = pipeline(journal=MemoryJournal(fail_read=True))
    result = host.run_cycle()
    assert result.cycle is None and result.persistence_code == "PERSISTENCE_UNAVAILABLE"
    assert not journal.cycles and journal.writes == 0


@pytest.mark.parametrize("issue", ["missing", "owner", "future", "stale"])
def test_control_failure_is_durable_without_market_data(issue: str) -> None:
    value = control()
    context = (
        None
        if issue == "missing"
        else value.model_copy(
            update={
                "owner_id": UUID(int=77) if issue == "owner" else value.owner_id,
                "observed_at": NOW + timedelta(seconds=1)
                if issue == "future"
                else NOW - timedelta(seconds=6)
                if issue == "stale"
                else NOW,
            }
        )
    )
    host, _ = pipeline(journal=MemoryJournal(context=context))
    result = host.run_cycle()
    assert result.cycle is not None and result.cycle.status == "BLOCK"
    assert result.cycle.market is None


def test_reconciliation_failure_keeps_exact_native_reason() -> None:
    host, _ = pipeline()
    host.config = host.config.model_copy(update={"expected_account_fingerprint": None})
    # A separately constructed market service missing binding is not allowed to capture.
    host.market._config = host.config
    cycle = host.run_cycle().cycle
    assert cycle is not None and cycle.status == "BLOCK"
    assert cycle.reason_codes == ("BINDING_CHANGED",)


def test_content_addresses_reproduce_from_persisted_normalized_inputs() -> None:
    host, _ = pipeline()
    cycle = host.run_cycle().cycle
    assert cycle is not None and cycle.market is not None
    m = cycle.market

    def number(value: Decimal) -> str:
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    payload = {
        "normalization": "completed-m1-v1",
        "source": "mt5",
        "adapter": m.market_adapter_version,
        "account": m.account_fingerprint,
        "server": m.server_fingerprint,
        "specification": m.specification_fingerprint,
        "symbol": m.broker_symbol,
        "point": number(m.point),
        "tick_size": number(m.tick_size),
        "tick_at": m.tick_at.isoformat(),
        "bid": number(m.bid),
        "ask": number(m.ask),
        "bars": [
            [bar.open_at.isoformat()]
            + [number(value) for value in (bar.open, bar.high, bar.low, bar.close)]
            for bar in m.bars
        ],
    }
    import hashlib

    assert (
        hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == m.input_digest
    )


def test_strategy_decimal_context_independent() -> None:
    first, _ = pipeline()
    baseline = first.run_cycle().cycle
    with localcontext() as ctx:
        ctx.prec = 6
        ctx.rounding = ROUND_DOWN
        second, _ = pipeline()
        assert second.run_cycle().cycle == baseline


def test_minute_identity_is_stable_but_new_minute_is_distinct() -> None:
    account = control().trading_account_id
    assert cycle_identity(account, NOW) == cycle_identity(
        account, NOW + timedelta(seconds=59)
    )
    assert cycle_identity(account, NOW) != cycle_identity(
        account, NOW + timedelta(minutes=1)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "live",
        "execute",
        "fake",
        "bool",
        "unknown",
        "price",
        "oversize",
        "probability",
        "timestamp",
        "sample",
    ],
)
def test_wire_rejects_unsafe_or_inconsistent_envelopes(mutation: str) -> None:
    host, _ = pipeline()
    cycle = host.run_cycle().cycle
    assert cycle is not None
    raw = json.loads(cycle.model_dump_json())
    if mutation == "live":
        raw["environment"] = "LIVE"
    elif mutation == "execute":
        raw["runtime_mode"] = "AUTO"
    elif mutation == "fake":
        raw["source"] = "fake_mt5"
    elif mutation == "bool":
        raw["grants_eligibility"] = 0
    elif mutation == "unknown":
        raw["credential"] = "unexpected"
    elif mutation == "price":
        raw["candidate"]["entry_price"] = 2000.02
    elif mutation == "oversize":
        raw["risk"]["calculated_volume"] = "0.02"
    elif mutation == "probability":
        raw["eligibility"]["probability"] = 0.99
    elif mutation == "timestamp":
        raw["evaluated_at"] = "2026-08-27T12:00:00.0000001Z"
    elif mutation == "sample":
        raw["eligibility"]["sample_count"] = 30
    with pytest.raises(ValidationError):
        ShadowCycle.model_validate_json(json.dumps(raw))


def test_naive_clock_never_gets_local_timezone_assumed() -> None:
    host, journal = pipeline()
    host.clock = lambda: NOW.replace(tzinfo=None)
    assert host.run_cycle().persistence_code == "CLOCK_INVALID"
    assert not journal.cycles


def test_source_failure_is_journaled_without_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aurum_worker.models.mt5 import Mt5ReasonCode

    host, journal = pipeline()

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("no native capture on a failed source")

    monkeypatch.setattr(host.market, "capture_bundle", forbidden)
    cycle = host.run_cycle(source_failure=Mt5ReasonCode.TERMINAL_DISCONNECTED).cycle
    assert cycle is not None and cycle.status == "BLOCK"
    assert cycle.reason_codes == ("TERMINAL_DISCONNECTED",)
    assert cycle.market is None and len(journal.cycles) == 1


def test_capture_bundle_is_native_readonly_and_contains_risk_sources() -> None:
    service, _ = market_service()
    capture = service.capture_bundle(trace_id="test-bundle")
    assert isinstance(capture, MarketCapture)
    assert len(capture.series.candles) == 6
    assert (
        capture.features.reconciliation_id
        == capture.reconciliation.report.reconciliation_id
    )


@pytest.mark.parametrize("complete", [True, False])
def test_reached_risk_input_is_archived_before_remote_cycle(complete: bool) -> None:
    host, journal = pipeline(complete=complete)
    assert isinstance(host.replay_archive, MemoryReplayArchive)
    saved = host.replay_archive

    class OrderedJournal(MemoryJournal):
        def record_cycle(self, cycle: ShadowCycle) -> str:
            assert cycle.id in saved.envelopes
            assert saved.envelopes[cycle.id].cycle == cycle
            return super().record_cycle(cycle)

    host.journal = OrderedJournal()
    result = host.run_cycle()
    assert result.cycle is not None and result.cycle.risk is not None
    assert len(saved.envelopes) == 1
    assert journal.writes == 0


@pytest.mark.parametrize("issue", ["missing", "failure", "conflict"])
def test_archive_failure_never_publishes_calculated_cycle(issue: str) -> None:
    host, journal = pipeline()

    class FailedArchive(MemoryReplayArchive):
        def record(self, envelope: object) -> str:
            if issue == "failure":
                raise OSError("private archive path")
            return "CONFLICT"

    host.replay_archive = None if issue == "missing" else FailedArchive()
    result = host.run_cycle()
    assert result.cycle is None
    assert result.persistence_code == "REPLAY_ARCHIVE_UNAVAILABLE"
    assert journal.writes == 0 and not journal.cycles


def test_remote_failure_retains_one_local_envelope_for_exact_retry() -> None:
    host, journal = pipeline(journal=MemoryJournal(uncertain_write=True))
    result = host.run_cycle()
    assert result.cycle is None and result.persistence_code == "PERSISTENCE_UNAVAILABLE"
    assert isinstance(host.replay_archive, MemoryReplayArchive)
    saved = tuple(host.replay_archive.envelopes.values())
    assert len(saved) == 1
    journal.uncertain_write = False
    host.clock = lambda: NOW + timedelta(minutes=1)
    retried = host.run_cycle()
    assert retried.cycle == saved[0].cycle
    assert tuple(host.replay_archive.envelopes.values()) == saved


def test_wait_without_risk_does_not_invent_replay_inputs() -> None:
    host, _ = pipeline(direction="WAIT")
    host.replay_archive = None
    result = host.run_cycle()
    assert result.cycle is not None and result.cycle.status == "WAIT"


def test_pending_remote_retry_rechecks_archive_before_publish() -> None:
    host, journal = pipeline(journal=MemoryJournal(uncertain_write=True))
    assert host.run_cycle().persistence_code == "PERSISTENCE_UNAVAILABLE"
    saved_archive = host.replay_archive
    host.replay_archive = None
    journal.uncertain_write = False
    assert host.run_cycle().persistence_code == "REPLAY_ARCHIVE_UNAVAILABLE"
    assert journal.writes == 1
    host.replay_archive = saved_archive
    assert host.run_cycle().persistence_code == "IDEMPOTENT_REPLAY"
    assert journal.writes == 2


def test_restart_cannot_replace_changed_unpublished_local_cycle() -> None:
    class OfflineJournal(MemoryJournal):
        def record_cycle(self, cycle: ShadowCycle) -> str:
            raise OSError("test remote offline before write")

    first, _ = pipeline(journal=OfflineJournal())
    assert first.run_cycle().persistence_code == "PERSISTENCE_UNAVAILABLE"
    archive = first.replay_archive
    assert isinstance(archive, MemoryReplayArchive)
    original = tuple(archive.envelopes.values())
    restarted, journal = pipeline()
    restarted.replay_archive = archive
    restarted.clock = lambda: NOW + timedelta(seconds=1)
    assert restarted.run_cycle().persistence_code == "REPLAY_ARCHIVE_UNAVAILABLE"
    assert tuple(archive.envelopes.values()) == original
    assert journal.writes == 0
