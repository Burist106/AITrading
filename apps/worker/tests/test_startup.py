"""MT5-independent fail-closed Worker startup tests."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from aurum_worker.adapters import (
    BrokerReadAdapter,
    ExecutionAdapter,
    FakeBrokerReadAdapter,
    FakeSubsystemAdapter,
    Mt5ReadAdapter,
    NotificationAdapter,
    PersistenceAdapter,
    RiskAdapter,
    StrategyAdapter,
)
from aurum_worker.models.bootstrap import AccountInspection, WorkerStartupReport
from aurum_worker.models.health import SystemComponentHealth
from aurum_worker.models.trading import BrokerSymbolSpecification
from aurum_worker.startup import (
    StartupBlockCode,
    StartupBlockedError,
    WorkerBootstrap,
)


def _account(is_demo: bool | None) -> AccountInspection:
    return AccountInspection.model_validate(
        {
            "isDemo": is_demo,
            "observedAt": datetime(2026, 8, 26, 2, 0, tzinfo=UTC),
        }
    )


def _specification(payload: dict[str, Any]) -> BrokerSymbolSpecification:
    return BrokerSymbolSpecification.model_validate_json(json.dumps(payload))


def _adapter(
    broker_specification_payload: dict[str, Any],
    *,
    is_demo: bool | None = True,
    open_positions: int | None = 0,
    specification: BrokerSymbolSpecification | None = None,
) -> FakeBrokerReadAdapter:
    resolved_specification = (
        _specification(broker_specification_payload)
        if specification is None
        else specification
    )
    return FakeBrokerReadAdapter(
        account=_account(is_demo),
        symbol_specification=resolved_specification,
        open_position_count=open_positions,
    )


def _start(adapter: FakeBrokerReadAdapter) -> WorkerStartupReport:
    return asyncio.run(
        WorkerBootstrap(adapter).start(
            started_at=datetime(2026, 8, 26, 2, 1, tzinfo=UTC)
        )
    )


def test_demo_startup_is_shadow_only(
    broker_specification_payload: dict[str, Any],
) -> None:
    adapter = _adapter(broker_specification_payload)
    assert isinstance(adapter, BrokerReadAdapter)
    assert isinstance(adapter, Mt5ReadAdapter)

    report = _start(adapter)

    assert report.environment == "DEMO_ONLY"
    assert report.runtime_mode == "shadow"
    assert report.canonical_symbol == "XAUUSD"
    assert report.account_verified_demo is True
    assert report.detected_open_positions == 0


@pytest.mark.parametrize(
    ("is_demo", "expected_code"),
    [
        (False, StartupBlockCode.NON_DEMO_ACCOUNT),
        (None, StartupBlockCode.ACCOUNT_TYPE_UNCERTAIN),
    ],
)
def test_startup_fails_closed_when_demo_status_is_not_verified(
    broker_specification_payload: dict[str, Any],
    is_demo: bool | None,
    expected_code: StartupBlockCode,
) -> None:
    adapter = _adapter(broker_specification_payload, is_demo=is_demo)

    with pytest.raises(StartupBlockedError) as captured:
        _start(adapter)

    assert captured.value.code is expected_code


@pytest.mark.parametrize(
    ("open_positions", "expected_code"),
    [
        (None, StartupBlockCode.OPEN_POSITION_STATE_UNAVAILABLE),
        (-1, StartupBlockCode.OPEN_POSITION_STATE_UNAVAILABLE),
        (2, StartupBlockCode.OPEN_POSITION_LIMIT_EXCEEDED),
    ],
)
def test_startup_fails_closed_for_uncertain_or_excess_position_state(
    broker_specification_payload: dict[str, Any],
    open_positions: int | None,
    expected_code: StartupBlockCode,
) -> None:
    adapter = _adapter(
        broker_specification_payload,
        open_positions=open_positions,
    )

    with pytest.raises(StartupBlockedError) as captured:
        _start(adapter)

    assert captured.value.code is expected_code


def test_startup_fails_closed_when_symbol_specification_is_missing(
    broker_specification_payload: dict[str, Any],
) -> None:
    adapter = FakeBrokerReadAdapter(
        account=_account(True),
        symbol_specification=None,
        open_position_count=0,
    )

    with pytest.raises(StartupBlockedError) as captured:
        _start(adapter)

    assert captured.value.code is StartupBlockCode.SYMBOL_SPECIFICATION_UNAVAILABLE


def test_startup_blocks_broker_minimum_above_policy_ceiling(
    broker_specification_payload: dict[str, Any],
) -> None:
    broker_specification_payload["minimumVolume"] = 0.02
    specification = _specification(broker_specification_payload)
    adapter = _adapter(
        broker_specification_payload,
        specification=specification,
    )

    with pytest.raises(StartupBlockedError) as captured:
        _start(adapter)

    assert captured.value.code is StartupBlockCode.BROKER_MINIMUM_VOLUME_EXCEEDS_POLICY


def test_all_future_subsystem_boundaries_are_health_only() -> None:
    component = SystemComponentHealth.model_validate_json(
        json.dumps(
            {
                "code": "bootstrap.boundary",
                "labelTh": "ขอบเขตบูตสแตรป",
                "plane": "execution_plane",
                "state": "unknown",
                "detail": "No implementation in Bootstrap",
                "observedAt": "2026-08-26T09:00:00+07:00",
            }
        )
    )
    fake = FakeSubsystemAdapter(component)

    adapters: tuple[
        PersistenceAdapter
        | StrategyAdapter
        | RiskAdapter
        | ExecutionAdapter
        | NotificationAdapter,
        ...,
    ] = (fake, fake, fake, fake, fake)

    assert all(asyncio.run(adapter.health()) == component for adapter in adapters)
