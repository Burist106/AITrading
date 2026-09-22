from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from mt5_factories import NOW
from shadow_factories import MemoryJournal, control, market_service
from test_shadow_outcomes import proposal, quote
from test_shadow_pipeline import pipeline

from aurum_worker.models.mt5 import Mt5ReadFailure
from aurum_worker.polling import ReadOnlyPollingService
from aurum_worker.shadow.market import MarketCapture
from aurum_worker.shadow.runtime import ShadowRuntime


class NoNetworkRpc:
    def call(self, function: str, parameters: dict[str, object]) -> dict[str, object]:
        raise AssertionError("Network RPC not permitted in this test")


def runtime(journal: MemoryJournal | None = None) -> ShadowRuntime:
    market, config = market_service()
    ctx = control()
    host = ShadowRuntime(
        market._adapter,
        NoNetworkRpc(),
        config,
        owner_id=ctx.owner_id,
        trading_account_id=ctx.trading_account_id,
        clock=lambda: NOW,
    )
    host.journal = journal or MemoryJournal()
    return host


def test_full_hook_reuses_history_and_tick_hook_never_queries_history() -> None:
    host, _ = pipeline()
    market = host.market
    collected = []
    ticks = []
    poller = ReadOnlyPollingService(
        market._adapter,
        market._persistence,
        market._reconciliation,
        market._config,
        clock=lambda: NOW,
        on_full_cycle=lambda result, trace: collected.append(
            host.run_cycle(reconciliation_result=result)
        ),
        on_tick=lambda tick, account: ticks.append(tick),
    )
    poller.run_once()
    assert collected[0].cycle is not None and collected[0].cycle.status == "PROPOSAL"
    port: Any = market._adapter
    assert port.call_log.count("get_order_history") == 1
    assert port.call_log.count("get_deal_history") == 1
    before = tuple(port.call_log)
    poller.run_tick_once()
    assert len(ticks) == 1
    assert "get_order_history" not in port.call_log[len(before) :]
    assert "get_deal_history" not in port.call_log[len(before) :]


def test_restart_records_unknown_without_native_reads() -> None:
    cycle = proposal()
    journal = MemoryJournal(cycles={cycle.cycle_key: cycle})
    host = runtime(journal)
    host.clock = lambda: NOW + timedelta(seconds=10)
    host.recover()
    assert len(journal.events) == 1
    assert journal.events[0].status == "UNKNOWN"
    assert journal.events[0].reason_code == "RESTART_CONTINUITY_UNKNOWN"
    assert journal.events[0].net_pnl_usd is None
    host.recover()
    assert len(journal.events) == 1


def test_failed_recovery_does_not_start_poller(monkeypatch: pytest.MonkeyPatch) -> None:
    host = runtime(MemoryJournal(fail_read=True))
    started = []
    monkeypatch.setattr(host.poller, "start", lambda: started.append(True))
    with pytest.raises(Mt5ReadFailure):
        host.start()
    assert not started


def test_full_cycle_registers_research_then_tick_persists_same_parent() -> None:
    pipeline_host, journal = pipeline()
    host = runtime(journal)
    host.pipeline = pipeline_host
    capture = pipeline_host.market.capture_bundle(trace_id="runtime-test")
    assert isinstance(capture, MarketCapture)
    host._full(capture.reconciliation, "runtime-test")
    cycle = host.last_result.cycle if host.last_result is not None else None
    assert cycle is not None and cycle.status == "PROPOSAL"
    host.clock = lambda: NOW + timedelta(seconds=1)
    host._tick(quote(), capture.account)
    assert len(journal.events) == 1
    assert journal.events[0].cycle_id == cycle.id
    assert journal.events[0].status == "OBSERVED"


def test_wrong_account_quote_cannot_produce_favorable_research_result() -> None:
    cycle = proposal()
    journal = MemoryJournal(cycles={cycle.cycle_key: cycle})
    host = runtime(journal)
    host._cycles[cycle.id] = cycle
    host.clock = lambda: NOW + timedelta(seconds=1)
    market, _ = market_service()
    capture = market.capture_bundle(trace_id="different-account")
    assert isinstance(capture, MarketCapture)
    host._tick(
        quote(bid="3000", ask="3000.02"),
        capture.account.model_copy(
            update={"account_fingerprint": "mt5-account-v1:" + "c" * 64}
        ),
    )
    assert journal.events[-1].status == "UNKNOWN"


def test_persistence_failure_lowers_full_cycle_instead_of_claiming_health() -> None:
    pipeline_host, _ = pipeline(journal=MemoryJournal(fail_read=True))
    host = runtime()
    host.pipeline = pipeline_host
    market, _ = market_service()
    capture = market.capture_bundle(trace_id="db-failure")
    assert isinstance(capture, MarketCapture)
    with pytest.raises(Mt5ReadFailure):
        host._full(capture.reconciliation, "db-failure")
    assert host.last_result is not None and host.last_result.cycle is None
