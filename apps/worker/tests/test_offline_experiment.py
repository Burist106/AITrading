"""Synthetic read-only experiment; never a real-terminal or M3 acceptance gate."""

from __future__ import annotations

import importlib
import json
import socket
import sys
from datetime import timedelta
from decimal import Decimal
from itertools import count
from typing import NoReturn

import pytest
from mt5_factories import NOW, account, confirmed_binding, fake_adapter, position, tick

from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    ConfirmedSymbolBinding,
    DatabaseReconciliationState,
    HealthState,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    TickFreshness,
)
from aurum_worker.models.safety import BOOTSTRAP_SAFETY_POLICY
from aurum_worker.polling import ReadOnlyPollingService
from aurum_worker.reconciliation import ReadOnlyReconciliationService

_BLOCKED_MODULES = (
    "MetaTrader5",
    "aurum_worker.adapters.native_mt5",
    "aurum_worker.local_mt5_profile",
    "aurum_worker.mt5_profile_cli",
    "aurum_worker.mt5_cli",
    "aurum_worker.mt5_market_cli",
)


def _deny_external_access(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("External access is forbidden in the offline experiment")


@pytest.fixture(autouse=True)
def offline_only(monkeypatch: pytest.MonkeyPatch) -> None:
    # These test guards are not an OS sandbox. No native adapter is constructed.
    for module in _BLOCKED_MODULES:
        monkeypatch.setitem(sys.modules, module, None)
    for method in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, method, _deny_external_access)
    monkeypatch.setattr(socket, "create_connection", _deny_external_access)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_external_access)
    monkeypatch.setattr(Mt5WorkerConfig, "from_environ", _deny_external_access)
    monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", "1")
    monkeypatch.setenv("AURUM_MT5_TERMINAL_PATH", "offline-sentinel-not-a-terminal")


def _config() -> Mt5WorkerConfig:
    config = Mt5WorkerConfig(
        broker_symbol="XAUUSD",
        expected_account_fingerprint=account().account_fingerprint,
    )
    assert config.terminal_path is None and config.readonly_smoke is False
    assert BOOTSTRAP_SAFETY_POLICY.environment == "DEMO_ONLY"
    assert BOOTSTRAP_SAFETY_POLICY.runtime_mode == "shadow"
    return config


def _run_case(scenario: str) -> dict[str, str]:
    adapter = fake_adapter()
    binding: ConfirmedSymbolBinding | None = confirmed_binding()
    if scenario == "stale":
        adapter.replace_tick("XAUUSD", tick(TickFreshness.STALE))
    elif scenario == "future":
        adapter.replace_tick("XAUUSD", tick(TickFreshness.FUTURE_INVALID))
    elif scenario == "delayed":
        delayed = tick().model_copy(
            update={
                "freshness": TickFreshness.DELAYED,
                "age_seconds": Decimal("6"),
                "tick_at": NOW - timedelta(seconds=6),
            }
        )
        adapter.replace_tick("XAUUSD", delayed)
    elif scenario == "unconfirmed":
        binding = None
    elif scenario == "history_failure":
        adapter.failures["get_deal_history"] = Mt5ReasonCode.HISTORY_QUERY_FAILED
    elif scenario == "real_account_rejected":
        # Adversarial synthetic classification, never a real account connection.
        adapter.accounts = (account(AccountTradeMode.REAL),)
    elif scenario == "unexpected_position":
        adapter.positions = (position(),)
    elif scenario != "healthy":
        raise ValueError("Unknown offline scenario")
    store = InMemoryMt5ObservationPersistence(
        database_state=DatabaseReconciliationState(confirmed_symbol_binding=binding)
    )
    identifiers = count(1)
    service = ReadOnlyReconciliationService(
        adapter,
        store,
        _config(),
        clock=lambda: NOW,
        identifier_factory=lambda: f"00000000-0000-4000-8000-{next(identifiers):012d}",
    )
    original_positions = adapter.positions
    try:
        result = service.run(trace_id="offline-experiment")
        assert adapter.positions == original_positions
        assert store.database_state.confirmed_symbol_binding == binding
        return {
            "scenario": scenario,
            "simulated_health": result.health.state.value,
            "reason": result.health.reason_code.value,
            "reconciliation": result.report.outcome.value,
        }
    finally:
        adapter.disconnect()
        assert not adapter.connected


@pytest.mark.parametrize(
    ("scenario", "expected_health", "expected_reason"),
    [
        ("healthy", HealthState.HEALTHY, Mt5ReasonCode.HEALTHY),
        ("delayed", HealthState.DEGRADED, Mt5ReasonCode.TICK_DELAYED),
        ("stale", HealthState.BLOCKED, Mt5ReasonCode.TICK_STALE),
        ("future", HealthState.BLOCKED, Mt5ReasonCode.RECONCILIATION_INCOMPLETE),
        (
            "unconfirmed",
            HealthState.BLOCKED,
            Mt5ReasonCode.SYMBOL_SPEC_CONFIRMATION_REQUIRED,
        ),
        ("history_failure", HealthState.BLOCKED, Mt5ReasonCode.HISTORY_QUERY_FAILED),
        (
            "real_account_rejected",
            HealthState.BLOCKED,
            Mt5ReasonCode.REAL_ACCOUNT_BLOCKED,
        ),
        (
            "unexpected_position",
            HealthState.BLOCKED,
            Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
        ),
    ],
)
def test_offline_scenario_replays_identically(
    scenario: str, expected_health: HealthState, expected_reason: Mt5ReasonCode
) -> None:
    first = _run_case(scenario)
    assert first == _run_case(scenario)
    assert first["simulated_health"] == expected_health.value
    assert first["reason"] == expected_reason.value
    print(
        json.dumps(
            {
                "experiment": "offline_reconciliation_v1",
                "data_source": "synthetic_fixture",
                "environment": "DEMO_ONLY",
                "runtime_mode": "SHADOW",
                "grants_eligibility": False,
                "real_mt5_smoke": "NOT_RUN_BY_THIS_EXPERIMENT",
                **first,
            },
            sort_keys=True,
        )
    )


def test_offline_recovery_and_restart_require_full_reconciliation() -> None:
    adapter = fake_adapter(freshness=TickFreshness.STALE)
    store = InMemoryMt5ObservationPersistence(
        database_state=DatabaseReconciliationState(
            confirmed_symbol_binding=confirmed_binding()
        )
    )
    identifiers = count(1)
    config = _config()

    def new_poller() -> ReadOnlyPollingService:
        reconciler = ReadOnlyReconciliationService(
            adapter,
            store,
            config,
            clock=lambda: NOW,
            identifier_factory=lambda: (
                f"00000000-0000-4000-8000-{next(identifiers):012d}"
            ),
        )
        return ReadOnlyPollingService(
            adapter,
            store,
            reconciler,
            config,
            clock=lambda: NOW,
            monotonic_clock=lambda: 0.0,
            jitter=lambda _attempt: Decimal("0"),
            trace_factory=lambda: "offline-recovery",
        )

    poller = new_poller()
    try:
        assert poller.run_once().health.state is HealthState.BLOCKED
        adapter.replace_tick("XAUUSD", tick())
        assert poller.run_tick_once() is True
        assert poller.state.health_state is HealthState.BLOCKED
        assert poller.state.reconciliation_required is True
        assert poller.run_once().health.state is HealthState.HEALTHY
    finally:
        poller.stop()
    assert not adapter.connected
    prior_reports = len(store.reports)
    restarted = new_poller()
    try:
        assert restarted.state.reconciliation_required is True
        assert restarted.state.health_state is not HealthState.HEALTHY
        assert restarted.run_once().health.state is HealthState.HEALTHY
        assert len(store.reports) == prior_reports + 1
    finally:
        restarted.stop()
    assert not adapter.connected


def test_offline_guards_reject_native_profile_network_and_environment() -> None:
    for module in _BLOCKED_MODULES:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)
    with pytest.raises(AssertionError, match="External access"):
        socket.create_connection(("127.0.0.1", 1))
    with pytest.raises(AssertionError, match="External access"):
        Mt5WorkerConfig.from_environ()
