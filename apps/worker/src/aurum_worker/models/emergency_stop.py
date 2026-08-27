"""Emergency Stop states keep control-plane and Worker facts separate."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from aurum_worker.models.base import WireModel


class EmergencyStopControlPlaneState(StrEnum):
    REQUESTED = "REQUESTED"
    CONTROL_PLANE_RECORDED = "CONTROL_PLANE_RECORDED"
    CONTROL_PLANE_UNAVAILABLE = "CONTROL_PLANE_UNAVAILABLE"


class EmergencyStopWorkerState(StrEnum):
    WORKER_RECEIVED = "WORKER_RECEIVED"
    LOCAL_EXECUTION_DISABLED = "LOCAL_EXECUTION_DISABLED"
    CONFIRMED = "CONFIRMED"
    WORKER_NOT_REACHABLE = "WORKER_NOT_REACHABLE"
    WORKER_ACK_TIMEOUT = "WORKER_ACK_TIMEOUT"
    LOCAL_STATE_UNCONFIRMED = "LOCAL_STATE_UNCONFIRMED"
    FAILED = "FAILED"


class EmergencyStopState(WireModel):
    command_id: UUID
    control_plane: EmergencyStopControlPlaneState
    worker: EmergencyStopWorkerState | None
    local_kill_switch_engaged: bool | None
    requested_at: AwareDatetime
    worker_ack_at: AwareDatetime | None = None
    ack_deadline_at: AwareDatetime

    @model_validator(mode="after")
    def validate_transition_evidence(self) -> EmergencyStopState:
        if self.requested_at >= self.ack_deadline_at:
            raise ValueError("Acknowledgement deadline must follow the request.")
        if self.worker is None and self.worker_ack_at is not None:
            raise ValueError("A Worker acknowledgement time requires a Worker state.")
        if (
            self.worker is EmergencyStopWorkerState.CONFIRMED
            and self.local_kill_switch_engaged is not True
        ):
            raise ValueError("Confirmed Emergency Stop requires the local switch.")
        return self
