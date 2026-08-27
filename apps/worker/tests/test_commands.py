"""Durable command payload and lifecycle validation tests."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from aurum_worker.models.commands import (
    SYSTEM_COMMAND_ADAPTER,
    ApproveProposalCommand,
)


def _command_payload() -> dict[str, Any]:
    return {
        "id": "00000000-0000-4000-8000-000000000010",
        "ownerId": "00000000-0000-4000-8000-000000000012",
        "type": "APPROVE_PROPOSAL",
        "payload": {
            "proposalId": "00000000-0000-4000-8000-000000000011",
            "proposalVersion": 3,
        },
        "status": "pending",
        "payloadSchemaVersion": 1,
        "requestedBy": "00000000-0000-4000-8000-000000000012",
        "requestedAt": "2026-08-26T09:00:00+07:00",
        "targetResourceType": "trade_proposal",
        "targetResourceId": "00000000-0000-4000-8000-000000000011",
        "expectedResourceVersion": 3,
        "idempotencyKey": "idem-1",
        "priority": 0,
        "attemptCount": 0,
        "maximumAttempts": 3,
        "expiresAt": "2026-08-26T09:01:00+07:00",
        "commandVersion": 1,
        "eventSequence": 0,
        "createdAt": "2026-08-26T09:00:00+07:00",
        "updatedAt": "2026-08-26T09:00:00+07:00",
    }


def _validate(payload: dict[str, Any]) -> ApproveProposalCommand:
    command = SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(payload))
    assert isinstance(command, ApproveProposalCommand)
    return command


def test_valid_command_payload_round_trips_with_camel_case() -> None:
    command = _validate(_command_payload())

    assert command.payload.proposal_version == 3
    dumped = command.model_dump(mode="json")
    assert dumped["requestedBy"] == "00000000-0000-4000-8000-000000000012"
    assert "requested_by" not in dumped


def test_command_payload_is_discriminated_by_command_type() -> None:
    payload = _command_payload()
    payload["payload"] = {"reason": "wrong shape"}

    with pytest.raises(ValidationError):
        SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(payload))


def test_command_rejects_partial_claim_and_invalid_lease() -> None:
    partial = _command_payload()
    partial["claimedAt"] = "2026-08-26T09:00:05+07:00"
    with pytest.raises(ValidationError):
        SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(partial))

    invalid_lease = _command_payload()
    invalid_lease.update(
        {
            "status": "claimed",
            "claimedAt": "2026-08-26T09:00:10+07:00",
            "claimedBy": "worker-1",
            "leaseToken": "00000000-0000-4000-8000-000000000099",
            "leaseExpiresAt": "2026-08-26T09:00:09+07:00",
            "attemptCount": 1,
        }
    )
    with pytest.raises(ValidationError):
        SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(invalid_lease))

    overlong_lease = _command_payload()
    overlong_lease.update(
        {
            "status": "claimed",
            "claimedAt": "2026-08-26T09:00:10+07:00",
            "claimedBy": "worker-1",
            "leaseToken": "00000000-0000-4000-8000-000000000099",
            "leaseExpiresAt": "2026-08-26T09:01:01+07:00",
            "attemptCount": 1,
        }
    )
    with pytest.raises(ValidationError):
        SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(overlong_lease))


def test_terminal_command_requires_completion_time() -> None:
    payload = _command_payload()
    payload["status"] = "succeeded"

    with pytest.raises(ValidationError):
        SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(payload))


def test_command_rejects_expired_at_creation_and_extra_data() -> None:
    expired = _command_payload()
    expired["expiresAt"] = expired["requestedAt"]
    with pytest.raises(ValidationError):
        SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(expired))

    extra = _command_payload()
    extra["brokerAction"] = "not part of Bootstrap"
    with pytest.raises(ValidationError):
        SYSTEM_COMMAND_ADAPTER.validate_json(json.dumps(extra))
