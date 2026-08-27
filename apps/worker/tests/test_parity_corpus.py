"""Cross-language tests over the single canonical contract corpus."""

from __future__ import annotations

import copy
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from aurum_worker.models.commands import (
    SYSTEM_COMMAND_ADAPTER,
    SYSTEM_COMMAND_PAYLOAD_ADAPTER,
    SYSTEM_COMMAND_TYPES,
    SystemCommandStatus,
    SystemCommandTargetResourceType,
)
from aurum_worker.models.eligibility import SignalEvidence
from aurum_worker.models.emergency_stop import (
    EmergencyStopControlPlaneState,
    EmergencyStopWorkerState,
)
from aurum_worker.models.health import SystemHealthState, SystemPlane
from aurum_worker.models.positions import PersistedPosition, Position, PositionStatus
from aurum_worker.models.risk_checks import (
    PersistedRiskCheck,
    RiskCheck,
    RiskCheckState,
)
from aurum_worker.models.risk_policy import (
    RiskPolicyActorType,
    RiskPolicyNumericRuleKey,
    RiskPolicyVersion,
)
from aurum_worker.models.trading import PersistedTradeProposal, TradeProposalStatus

CORPUS_PATH = (
    Path(__file__).resolve().parents[3]
    / "contract-fixtures"
    / "v1"
    / "domain-parity.json"
)
CORPUS: dict[str, Any] = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]


def test_python_domain_sets_match_the_canonical_manifest_exactly() -> None:
    manifest = {
        "commandTypes": list(SYSTEM_COMMAND_TYPES),
        "commandStatuses": _values(SystemCommandStatus),
        "commandTargetResourceTypes": _values(SystemCommandTargetResourceType),
        "tradeProposalStatuses": _values(TradeProposalStatus),
        "positionStatuses": _values(PositionStatus),
        "riskCheckStates": _values(RiskCheckState),
        "riskPolicyNumericRuleKeys": _values(RiskPolicyNumericRuleKey),
        "riskPolicyActorTypes": _values(RiskPolicyActorType),
        "systemHealthStates": _values(SystemHealthState),
        "systemPlanes": _values(SystemPlane),
        "emergencyStopControlPlaneStates": _values(EmergencyStopControlPlaneState),
        "emergencyStopWorkerStates": _values(EmergencyStopWorkerState),
    }
    assert CORPUS["schemaVersion"] == 1
    assert manifest == CORPUS["domainSets"]


def test_python_accepts_all_nine_valid_typed_payloads() -> None:
    fixtures = CORPUS["validPayloads"]
    assert len(fixtures) == len(SYSTEM_COMMAND_TYPES)
    assert [fixture["type"] for fixture in fixtures] == list(SYSTEM_COMMAND_TYPES)
    for fixture in fixtures:
        SYSTEM_COMMAND_PAYLOAD_ADAPTER.validate_json(
            json.dumps({"type": fixture["type"], "payload": fixture["payload"]})
        )


def test_python_rejects_every_invalid_typed_payload() -> None:
    fixtures = CORPUS["invalidPayloads"]
    assert [fixture["type"] for fixture in fixtures] == list(SYSTEM_COMMAND_TYPES)
    for fixture in fixtures:
        with pytest.raises(ValidationError):
            SYSTEM_COMMAND_PAYLOAD_ADAPTER.validate_json(
                json.dumps({"type": fixture["type"], "payload": fixture["payload"]})
            )


def test_python_enforces_every_sql_aligned_risk_rule_bound() -> None:
    for change in CORPUS["validRiskPolicyRuleChanges"]:
        SYSTEM_COMMAND_PAYLOAD_ADAPTER.validate_json(
            json.dumps(
                {
                    "type": "REQUEST_RISK_POLICY_CHANGE",
                    "payload": {**change, "reason": "Parity boundary fixture"},
                }
            )
        )
    for change in CORPUS["invalidRiskPolicyRuleChanges"]:
        with pytest.raises(ValidationError):
            SYSTEM_COMMAND_PAYLOAD_ADAPTER.validate_json(
                json.dumps(
                    {
                        "type": "REQUEST_RISK_POLICY_CHANGE",
                        "payload": {**change, "reason": "Parity boundary fixture"},
                    }
                )
            )


def _valid_envelope(case_id: str) -> dict[str, Any]:
    fixture = next(
        item for item in CORPUS["validEnvelopes"] if item["caseId"] == case_id
    )
    return {**CORPUS["envelopeDefaults"], **fixture["value"]}


def test_python_accepts_every_valid_lifecycle_envelope() -> None:
    assert [item["caseId"] for item in CORPUS["validEnvelopes"]] == _values(
        SystemCommandStatus
    )
    for fixture in CORPUS["validEnvelopes"]:
        SYSTEM_COMMAND_ADAPTER.validate_json(
            json.dumps({**CORPUS["envelopeDefaults"], **fixture["value"]})
        )
    long_result = {**_valid_envelope("succeeded"), "resultMessage": "x" * 512}
    SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(long_result))
    with pytest.raises(ValidationError):
        SYSTEM_COMMAND_ADAPTER.validate_json(
            json.dumps({**long_result, "resultMessage": "x" * 513})
        )


def test_python_rejects_every_invalid_lifecycle_target_and_idempotency_case() -> None:
    for fixture in CORPUS["invalidEnvelopes"]:
        value = copy.deepcopy(_valid_envelope(fixture["patchValidCase"]))
        value.update(fixture.get("patch", {}))
        for field in fixture.get("remove", []):
            value.pop(field, None)
        with pytest.raises(ValidationError):
            SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(value))

    for unsafe_result_message in (
        "sk-" + "1234567890abcdefghijklmnop",
        ".".join(("eyJabcdefghijk", "eyJmnopqrstuv", "wxyzABCDEFGHI")),
    ):
        with pytest.raises(ValidationError):
            SYSTEM_COMMAND_ADAPTER.validate_json(
                json.dumps(
                    {
                        **_valid_envelope("succeeded"),
                        "resultMessage": unsafe_result_message,
                    }
                )
            )

    for fixture in CORPUS["unsafeResultCodes"]:
        unsafe_result_code = fixture["separator"].join(fixture["parts"])
        with pytest.raises(ValidationError):
            SYSTEM_COMMAND_ADAPTER.validate_json(
                json.dumps(
                    {
                        **_valid_envelope("succeeded"),
                        "resultCode": unsafe_result_code,
                    }
                )
            )


def test_python_validates_shared_read_records_and_explicit_mapper() -> None:
    risk_check = RiskCheck.model_validate_json(
        json.dumps(CORPUS["domainRecords"]["riskCheck"])
    )
    assert risk_check.state is RiskCheckState.PASS
    long_risk_check = {**CORPUS["domainRecords"]["riskCheck"], "actual": "x" * 512}
    RiskCheck.model_validate_json(json.dumps(long_risk_check))
    with pytest.raises(ValidationError):
        RiskCheck.model_validate_json(
            json.dumps({**long_risk_check, "actual": "x" * 513})
        )

    persisted = PersistedRiskCheck.model_validate_json(
        json.dumps(CORPUS["domainRecords"]["persistedRiskCheck"])
    )
    mapped = persisted.to_risk_check()
    assert mapped.key == "maximum_spread"
    assert mapped.limit == "3.50 points"

    position = Position.model_validate_json(
        json.dumps(CORPUS["domainRecords"]["position"])
    )
    assert position.status is PositionStatus.OPEN

    persisted_position = PersistedPosition.model_validate_json(
        json.dumps(CORPUS["domainRecords"]["persistedPosition"])
    )
    mapped_position = persisted_position.to_position()
    assert mapped_position.account_type == "demo"
    assert mapped_position.canonical_symbol == "XAUUSD"
    assert mapped_position.entry == 2405.85

    persisted_trade_proposal = PersistedTradeProposal.model_validate_json(
        json.dumps(CORPUS["domainRecords"]["persistedTradeProposal"])
    )
    assert persisted_trade_proposal.eligibility_outcome == "ask"
    assert not hasattr(persisted_trade_proposal, "eligibility")
    with pytest.raises(ValidationError):
        PersistedTradeProposal.model_validate_json(
            json.dumps(
                {
                    **CORPUS["domainRecords"]["persistedTradeProposal"],
                    "maximumPermittedVolume": 0.005,
                }
            )
        )
    with pytest.raises(ValidationError):
        PersistedTradeProposal.model_validate_json(
            json.dumps(
                {
                    **CORPUS["domainRecords"]["persistedTradeProposal"],
                    "requestedVolume": 0.005,
                    "approvedVolume": 0.01,
                }
            )
        )

    policy = RiskPolicyVersion.model_validate_json(
        json.dumps(CORPUS["domainRecords"]["riskPolicy"])
    )
    assert policy.maximum_permitted_volume == 0.01
    assert policy.automatic_retry_on_broker_reject is False
    for patch in (
        {"minimumRiskReward": 10_000},
        {"newsBlackoutMinutes": 2_147_483_648},
    ):
        with pytest.raises(ValidationError):
            RiskPolicyVersion.model_validate_json(
                json.dumps({**CORPUS["domainRecords"]["riskPolicy"], **patch})
            )


def test_python_keeps_calibration_behavior_aligned_with_typescript() -> None:
    invalid = {
        "qualityScore": 71.0,
        "calibratedProbability": 0.8,
        "calibrationStatus": "not_calibrated",
        "similarSampleCount": 24,
        "minimumRequiredSampleCount": 30,
        "strategyVersion": "fixture-v1",
    }
    with pytest.raises(ValidationError):
        SignalEvidence.model_validate_json(json.dumps(invalid))
