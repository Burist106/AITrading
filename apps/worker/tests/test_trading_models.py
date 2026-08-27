"""Read-side trading contract validation tests."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from aurum_worker.models.trading import (
    POSITION_SIZING_ADAPTER,
    BrokerSymbolSpecification,
    MobileApprovalSession,
    PositionSizingPass,
    TradeProposal,
)


def _sizing_payload() -> dict[str, Any]:
    return {
        "entryPrice": 2410.40,
        "stopLossPrice": 2404.90,
        "stopDistancePrice": 5.50,
        "stopDistancePoints": 550.0,
        "accountEquity": 2200.0,
        "riskLimitPct": 0.25,
        "riskBudgetAmount": 5.50,
        "calculatedVolume": 0.01,
        "brokerMinimumVolume": 0.01,
        "brokerVolumeStep": 0.01,
        "maximumPermittedVolume": 0.01,
        "requestedVolume": 0.01,
        "approvedVolume": None,
        "estimatedLossAtStop": 5.50,
        "actualRiskPct": 0.25,
        "unusedRiskCapacity": 0.0,
        "calculationSource": "simulation",
        "result": "pass",
    }


def test_broker_specification_is_xauusd_and_validates_volume_range(
    broker_specification_payload: dict[str, Any],
) -> None:
    specification = BrokerSymbolSpecification.model_validate_json(
        json.dumps(broker_specification_payload)
    )
    assert specification.canonical_symbol == "XAUUSD"

    invalid = broker_specification_payload | {
        "minimumVolume": 0.02,
        "maximumVolume": 0.01,
    }
    with pytest.raises(ValidationError):
        BrokerSymbolSpecification.model_validate_json(json.dumps(invalid))


def test_position_sizing_reconciles_human_approval_fixture() -> None:
    sizing = POSITION_SIZING_ADAPTER.validate_json(json.dumps(_sizing_payload()))
    assert isinstance(sizing, PositionSizingPass)
    assert sizing.maximum_permitted_volume == 0.01
    assert sizing.requested_volume == 0.01

    increased_approval = _sizing_payload() | {
        "calculatedVolume": 0.005,
        "requestedVolume": 0.005,
        "approvedVolume": 0.01,
    }
    with pytest.raises(ValidationError):
        POSITION_SIZING_ADAPTER.validate_json(json.dumps(increased_approval))


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("maximumPermittedVolume", 0.02),
        ("requestedVolume", 0.02),
        ("stopDistancePrice", 4.0),
        ("riskBudgetAmount", 6.0),
        ("actualRiskPct", 0.5),
    ],
)
def test_position_sizing_rejects_unsafe_or_inconsistent_values(
    field: str, invalid_value: object
) -> None:
    payload = _sizing_payload()
    payload[field] = invalid_value
    with pytest.raises(ValidationError):
        POSITION_SIZING_ADAPTER.validate_json(json.dumps(payload))


def test_blocked_sizing_has_no_requested_or_approved_volume() -> None:
    payload = _sizing_payload() | {
        "result": "block",
        "requestedVolume": None,
        "approvedVolume": None,
        "blockReason": "BROKER_MINIMUM_VOLUME_EXCEEDS_RISK",
    }
    blocked = POSITION_SIZING_ADAPTER.validate_json(json.dumps(payload))
    assert blocked.requested_volume is None

    payload["requestedVolume"] = 0.01
    with pytest.raises(ValidationError):
        POSITION_SIZING_ADAPTER.validate_json(json.dumps(payload))


def test_trade_proposal_requires_demo_xauusd_mandatory_sl_and_volume_ceiling(
    proposal_payload: dict[str, Any],
) -> None:
    proposal = TradeProposal.model_validate_json(json.dumps(proposal_payload))
    assert proposal.account_type == "demo"
    assert proposal.canonical_symbol == "XAUUSD"
    assert proposal.stop_loss_price == 2404.90

    invalid_variants: list[dict[str, Any]] = []
    for field, value in (
        ("accountType", "real"),
        ("canonicalSymbol", "EURUSD"),
        ("maximumPermittedVolume", 0.02),
        ("requestedVolume", 0.02),
    ):
        variant = copy.deepcopy(proposal_payload)
        variant[field] = value
        invalid_variants.append(variant)

    missing_stop = copy.deepcopy(proposal_payload)
    del missing_stop["stopLossPrice"]
    invalid_variants.append(missing_stop)

    increased_approval = copy.deepcopy(proposal_payload)
    increased_approval["requestedVolume"] = 0.005
    increased_approval["approvedVolume"] = 0.01
    invalid_variants.append(increased_approval)

    for invalid in invalid_variants:
        with pytest.raises(ValidationError):
            TradeProposal.model_validate_json(json.dumps(invalid))


def test_blocked_proposal_cannot_carry_volume(
    proposal_payload: dict[str, Any],
) -> None:
    proposal_payload["status"] = "blocked"
    proposal_payload["eligibility"]["outcome"] = "block"
    proposal_payload["eligibility"]["checks"][0]["state"] = "fail"

    with pytest.raises(ValidationError):
        TradeProposal.model_validate_json(json.dumps(proposal_payload))


def test_used_mobile_session_requires_used_time() -> None:
    payload = {
        "id": "00000000-0000-4000-8000-000000000030",
        "proposalId": "00000000-0000-4000-8000-000000000031",
        "proposalVersion": 1,
        "allowedUserId": "line-user-1",
        "tokenHash": "a" * 64,
        "nonce": "nonce-1",
        "status": "used",
        "createdAt": "2026-08-26T09:00:00+07:00",
        "expiresAt": "2026-08-26T09:01:00+07:00",
    }

    with pytest.raises(ValidationError):
        MobileApprovalSession.model_validate_json(json.dumps(payload))

    payload["usedAt"] = "2026-08-26T09:00:10+07:00"
    assert MobileApprovalSession.model_validate_json(json.dumps(payload)).used_at
