"""Eligibility, Emergency Stop, and health contract tests."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from aurum_worker.models.eligibility import (
    EligibilityOutcome,
    EligibilityPolicyResult,
    SignalEvidence,
)
from aurum_worker.models.emergency_stop import EmergencyStopState
from aurum_worker.models.health import (
    SystemComponentHealth,
    SystemHealthSnapshot,
    SystemHealthState,
    derive_system_health_state,
)


def test_warn_eligibility_requires_ask_outcome(
    eligibility_payload: dict[str, Any],
) -> None:
    result = EligibilityPolicyResult.model_validate_json(
        json.dumps(eligibility_payload)
    )
    assert result.outcome is EligibilityOutcome.ASK

    invalid = eligibility_payload | {"outcome": "auto"}
    with pytest.raises(ValidationError):
        EligibilityPolicyResult.model_validate_json(json.dumps(invalid))


def test_eligibility_rejects_duplicate_check_keys(
    eligibility_payload: dict[str, Any],
) -> None:
    duplicate = dict(eligibility_payload)
    duplicate["checks"] = [
        eligibility_payload["checks"][0],
        eligibility_payload["checks"][0],
    ]

    with pytest.raises(ValidationError):
        EligibilityPolicyResult.model_validate_json(json.dumps(duplicate))


def test_quality_score_is_separate_supporting_evidence() -> None:
    evidence = SignalEvidence.model_validate_json(
        json.dumps(
            {
                "qualityScore": 71.0,
                "calibratedProbability": None,
                "calibrationStatus": "not_calibrated",
                "similarSampleCount": 24,
                "minimumRequiredSampleCount": 30,
                "strategyVersion": "v0",
            }
        )
    )

    assert evidence.quality_score == 71.0
    assert not hasattr(evidence, "outcome")


def test_emergency_stop_confirmation_requires_local_evidence() -> None:
    state = {
        "commandId": "00000000-0000-4000-8000-000000000020",
        "controlPlane": "CONTROL_PLANE_RECORDED",
        "worker": "CONFIRMED",
        "localKillSwitchEngaged": False,
        "requestedAt": "2026-08-26T09:00:00+07:00",
        "workerAckAt": "2026-08-26T09:00:05+07:00",
        "ackDeadlineAt": "2026-08-26T09:00:10+07:00",
    }

    with pytest.raises(ValidationError):
        EmergencyStopState.model_validate_json(json.dumps(state))

    state["localKillSwitchEngaged"] = True
    confirmed = EmergencyStopState.model_validate_json(json.dumps(state))
    assert confirmed.worker is not None


def test_unacknowledged_emergency_stop_keeps_unknown_local_state() -> None:
    state = EmergencyStopState.model_validate_json(
        json.dumps(
            {
                "commandId": "00000000-0000-4000-8000-000000000021",
                "controlPlane": "REQUESTED",
                "worker": None,
                "localKillSwitchEngaged": None,
                "requestedAt": "2026-08-26T09:00:00+07:00",
                "ackDeadlineAt": "2026-08-26T09:00:10+07:00",
            }
        )
    )
    assert state.worker is None
    assert state.local_kill_switch_engaged is None


def _component(state: str, code: str) -> SystemComponentHealth:
    return SystemComponentHealth.model_validate_json(
        json.dumps(
            {
                "code": code,
                "labelTh": code,
                "plane": "execution_plane",
                "state": state,
                "detail": "fixture health",
                "observedAt": "2026-08-26T09:00:00+07:00",
            }
        )
    )


def test_health_aggregation_returns_worst_state() -> None:
    components = (
        _component("healthy", "worker.local"),
        _component("warning", "data.age"),
        _component("degraded", "strategy.boundary"),
    )
    snapshot = SystemHealthSnapshot.model_validate(
        {
            "capturedAt": components[0].observed_at,
            "components": components,
        }
    )

    assert snapshot.components == components
    assert derive_system_health_state(components) is SystemHealthState.WARNING
    assert derive_system_health_state(()) is SystemHealthState.UNKNOWN
