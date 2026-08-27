"""Declarative durable-command wire contracts.

These models validate messages only. This module deliberately contains no command
processor and no broker-side capability.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from aurum_worker.models.base import (
    Identifier,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    WireModel,
)
from aurum_worker.models.risk_policy import (
    RiskPolicyNumericRuleKey,
    validate_risk_policy_rule_value,
)


class SystemCommandStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    VALIDATING = "validating"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SystemCommandTargetResourceType(StrEnum):
    TRADE_PROPOSAL = "trade_proposal"
    POSITION = "position"
    RISK_POLICY = "risk_policy"


SYSTEM_COMMAND_TYPES: tuple[str, ...] = (
    "APPROVE_PROPOSAL",
    "REJECT_PROPOSAL",
    "PAUSE_NEW_TRADES",
    "RESUME_SYSTEM",
    "ACTIVATE_EMERGENCY_STOP",
    "REQUEST_POSITION_CLOSE",
    "REQUEST_STOP_LOSS_CHANGE",
    "REQUEST_TAKE_PROFIT_CHANGE",
    "REQUEST_RISK_POLICY_CHANGE",
)

CommandDetail = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=512),
]
UNSAFE_WORKER_TEXT = re.compile(
    r"[\x00-\x1f\x7f-\x9f]|bearer\s|authorization\s*[:=]|"
    r"password\s*[:=]|token\s*[:=]|secret\s*[:=]|"
    r"client[_-]?secret\s*[:=]|api[_-]?key\s*[:=]|"
    r"access[_-]?key\s*[:=]|sb_secret_|"
    r"(?:^|[^A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}\."
    r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:$|[^A-Za-z0-9_-])|"
    r"sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"(?:postgres(?:ql)?|mysql|redis|amqps?|mongodb(?:\+srv)?):"
    r"//[^\s/:@]+:[^\s/@]+@|"
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----",
    re.IGNORECASE,
)


def _validate_secret_free_result_code(value: str) -> str:
    if UNSAFE_WORKER_TEXT.search(value) is not None:
        raise ValueError("Result code must be bounded, printable, and secret-free.")
    return value


ResultCode = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[A-Z][A-Z0-9_]{0,159}$"),
    AfterValidator(_validate_secret_free_result_code),
]


class ApproveProposalPayload(WireModel):
    proposal_id: UUID
    proposal_version: PositiveInt
    approval_session_id: UUID | None = None

    @model_validator(mode="after")
    def reject_null_approval_session(self) -> ApproveProposalPayload:
        if (
            "approval_session_id" in self.model_fields_set
            and self.approval_session_id is None
        ):
            raise ValueError("approvalSessionId must be omitted rather than null.")
        return self


class RejectProposalPayload(WireModel):
    proposal_id: UUID
    proposal_version: PositiveInt
    reason: Identifier


class PauseNewTradesPayload(WireModel):
    reason: Identifier | None = None

    @model_validator(mode="after")
    def reject_null_reason(self) -> PauseNewTradesPayload:
        if "reason" in self.model_fields_set and self.reason is None:
            raise ValueError("reason must be omitted rather than null.")
        return self


class ResumeSystemPayload(WireModel):
    checklist_acknowledgement_id: UUID


class ActivateEmergencyStopPayload(WireModel):
    reason: Identifier


class RequestPositionClosePayload(WireModel):
    position_id: UUID
    expected_position_version: PositiveInt
    reason: Identifier


class RequestStopLossChangePayload(WireModel):
    position_id: UUID
    expected_position_version: PositiveInt
    new_stop_loss: PositiveFloat


class RequestTakeProfitChangePayload(WireModel):
    position_id: UUID
    expected_position_version: PositiveInt
    new_take_profit: PositiveFloat


class RequestRiskPolicyChangePayload(WireModel):
    rule_key: RiskPolicyNumericRuleKey
    new_value: NonNegativeFloat
    reason: Identifier

    @model_validator(mode="after")
    def validate_rule_bound(self) -> RequestRiskPolicyChangePayload:
        validate_risk_policy_rule_value(self.rule_key, self.new_value)
        return self


class ApproveProposalPayloadEnvelope(WireModel):
    type: Literal["APPROVE_PROPOSAL"]
    payload: ApproveProposalPayload


class RejectProposalPayloadEnvelope(WireModel):
    type: Literal["REJECT_PROPOSAL"]
    payload: RejectProposalPayload


class PauseNewTradesPayloadEnvelope(WireModel):
    type: Literal["PAUSE_NEW_TRADES"]
    payload: PauseNewTradesPayload


class ResumeSystemPayloadEnvelope(WireModel):
    type: Literal["RESUME_SYSTEM"]
    payload: ResumeSystemPayload


class ActivateEmergencyStopPayloadEnvelope(WireModel):
    type: Literal["ACTIVATE_EMERGENCY_STOP"]
    payload: ActivateEmergencyStopPayload


class RequestPositionClosePayloadEnvelope(WireModel):
    type: Literal["REQUEST_POSITION_CLOSE"]
    payload: RequestPositionClosePayload


class RequestStopLossChangePayloadEnvelope(WireModel):
    type: Literal["REQUEST_STOP_LOSS_CHANGE"]
    payload: RequestStopLossChangePayload


class RequestTakeProfitChangePayloadEnvelope(WireModel):
    type: Literal["REQUEST_TAKE_PROFIT_CHANGE"]
    payload: RequestTakeProfitChangePayload


class RequestRiskPolicyChangePayloadEnvelope(WireModel):
    type: Literal["REQUEST_RISK_POLICY_CHANGE"]
    payload: RequestRiskPolicyChangePayload


type SystemCommandPayloadEnvelope = Annotated[
    ApproveProposalPayloadEnvelope
    | RejectProposalPayloadEnvelope
    | PauseNewTradesPayloadEnvelope
    | ResumeSystemPayloadEnvelope
    | ActivateEmergencyStopPayloadEnvelope
    | RequestPositionClosePayloadEnvelope
    | RequestStopLossChangePayloadEnvelope
    | RequestTakeProfitChangePayloadEnvelope
    | RequestRiskPolicyChangePayloadEnvelope,
    Field(discriminator="type"),
]

SYSTEM_COMMAND_PAYLOAD_ADAPTER: TypeAdapter[SystemCommandPayloadEnvelope] = TypeAdapter(
    SystemCommandPayloadEnvelope
)


class _SystemCommandBase(WireModel):
    id: UUID
    owner_id: UUID
    status: SystemCommandStatus
    payload_schema_version: Literal[1]
    requested_by: UUID
    requested_at: AwareDatetime
    target_resource_type: SystemCommandTargetResourceType | None = None
    target_resource_id: UUID | None = None
    expected_resource_version: PositiveInt | None = None
    idempotency_key: Identifier
    priority: Annotated[int, Field(ge=0, le=100)]
    claimed_at: AwareDatetime | None = None
    claimed_by: Identifier | None = None
    lease_token: UUID | None = None
    lease_expires_at: AwareDatetime | None = None
    attempt_count: NonNegativeInt
    maximum_attempts: PositiveInt
    next_retry_at: AwareDatetime | None = None
    expires_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    result_code: ResultCode | None = None
    result_message: CommandDetail | None = None
    last_error: CommandDetail | None = None
    command_version: PositiveInt
    event_sequence: NonNegativeInt
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("result_message", "last_error")
    @classmethod
    def validate_safe_worker_text(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.strip() or UNSAFE_WORKER_TEXT.search(value) is not None
        ):
            raise ValueError(
                "Command detail must be bounded, printable, and secret-free."
            )
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> _SystemCommandBase:
        optional_fields = (
            "target_resource_type",
            "target_resource_id",
            "expected_resource_version",
            "claimed_at",
            "claimed_by",
            "lease_token",
            "lease_expires_at",
            "next_retry_at",
            "completed_at",
            "result_code",
            "result_message",
            "last_error",
        )
        for field_name in optional_fields:
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(
                    f"{field_name} must be omitted rather than explicitly null."
                )

        if self.requested_at >= self.expires_at:
            raise ValueError("Command expiry must be after the request time.")

        claim_fields = (
            self.claimed_at,
            self.claimed_by,
            self.lease_token,
            self.lease_expires_at,
        )
        supplied_claim_fields = sum(value is not None for value in claim_fields)
        if supplied_claim_fields not in (0, 4):
            raise ValueError(
                "Claim time, owner, token, and lease expiry must be supplied together."
            )

        active_statuses = {
            SystemCommandStatus.CLAIMED,
            SystemCommandStatus.VALIDATING,
            SystemCommandStatus.EXECUTING,
        }
        if self.status is SystemCommandStatus.PENDING and supplied_claim_fields:
            raise ValueError("A pending command cannot carry an active claim.")
        terminal_statuses = {
            SystemCommandStatus.SUCCEEDED,
            SystemCommandStatus.REJECTED,
            SystemCommandStatus.FAILED,
            SystemCommandStatus.EXPIRED,
            SystemCommandStatus.CANCELLED,
        }
        if self.status in terminal_statuses and supplied_claim_fields:
            raise ValueError(
                "Terminal command claim ownership belongs in immutable event history."
            )
        if self.status in active_statuses and supplied_claim_fields != 4:
            raise ValueError("An active command requires a complete claim and lease.")
        if self.status in active_statuses and self.attempt_count < 1:
            raise ValueError(
                "An active command must record at least one claim attempt."
            )
        if self.attempt_count > self.maximum_attempts:
            raise ValueError("Attempt count cannot exceed the configured maximum.")
        if (
            self.claimed_at is not None
            and self.lease_expires_at is not None
            and self.claimed_at >= self.lease_expires_at
        ):
            raise ValueError("Lease expiry must be after claim time.")
        if (
            self.lease_expires_at is not None
            and self.lease_expires_at > self.expires_at
        ):
            raise ValueError("Lease expiry cannot exceed command expiry.")

        if self.status in terminal_statuses and self.completed_at is None:
            raise ValueError("Terminal commands require a completion time.")
        if self.status not in terminal_statuses and self.completed_at is not None:
            raise ValueError("A non-terminal command cannot have a completion time.")
        if (
            self.next_retry_at is not None
            and self.status is not SystemCommandStatus.PENDING
        ):
            raise ValueError(
                "Retry scheduling is valid only while a command is pending."
            )

        command_type = getattr(self, "type", None)
        if command_type == "ACTIVATE_EMERGENCY_STOP":
            if self.priority != 100:
                raise ValueError("Emergency Stop command priority must be 100.")
        elif self.priority >= 100:
            raise ValueError("Non-emergency command priority must be below 100.")

        if self.updated_at < self.created_at:
            raise ValueError("Command update time cannot precede creation.")
        lifecycle_times = [self.requested_at]
        if self.claimed_at is not None:
            lifecycle_times.append(self.claimed_at)
        if self.completed_at is not None:
            lifecycle_times.append(self.completed_at)
        if self.updated_at < max(lifecycle_times):
            raise ValueError("Command update time cannot precede lifecycle evidence.")

        payload = getattr(self, "payload", None)

        def require_target(
            resource_type: SystemCommandTargetResourceType,
            resource_id: UUID | None = None,
            resource_version: int | None = None,
        ) -> None:
            if (
                self.target_resource_type is not resource_type
                or self.target_resource_id is None
                or self.expected_resource_version is None
            ):
                raise ValueError(
                    f"Command requires a versioned {resource_type.value} target."
                )
            if resource_id is not None and self.target_resource_id != resource_id:
                raise ValueError("Command target id must match its typed payload.")
            if (
                resource_version is not None
                and self.expected_resource_version != resource_version
            ):
                raise ValueError("Command target version must match its typed payload.")

        if command_type in ("APPROVE_PROPOSAL", "REJECT_PROPOSAL") and isinstance(
            payload, (ApproveProposalPayload, RejectProposalPayload)
        ):
            require_target(
                SystemCommandTargetResourceType.TRADE_PROPOSAL,
                payload.proposal_id,
                payload.proposal_version,
            )
        elif command_type in (
            "REQUEST_POSITION_CLOSE",
            "REQUEST_STOP_LOSS_CHANGE",
            "REQUEST_TAKE_PROFIT_CHANGE",
        ) and isinstance(
            payload,
            (
                RequestPositionClosePayload,
                RequestStopLossChangePayload,
                RequestTakeProfitChangePayload,
            ),
        ):
            require_target(
                SystemCommandTargetResourceType.POSITION,
                payload.position_id,
                payload.expected_position_version,
            )
        elif command_type == "REQUEST_RISK_POLICY_CHANGE":
            require_target(SystemCommandTargetResourceType.RISK_POLICY)
        elif command_type in (
            "PAUSE_NEW_TRADES",
            "RESUME_SYSTEM",
            "ACTIVATE_EMERGENCY_STOP",
        ) and any(
            value is not None
            for value in (
                self.target_resource_type,
                self.target_resource_id,
                self.expected_resource_version,
            )
        ):
            raise ValueError("A global command cannot carry a resource target.")
        return self


class ApproveProposalCommand(_SystemCommandBase):
    type: Literal["APPROVE_PROPOSAL"]
    payload: ApproveProposalPayload


class RejectProposalCommand(_SystemCommandBase):
    type: Literal["REJECT_PROPOSAL"]
    payload: RejectProposalPayload


class PauseNewTradesCommand(_SystemCommandBase):
    type: Literal["PAUSE_NEW_TRADES"]
    payload: PauseNewTradesPayload


class ResumeSystemCommand(_SystemCommandBase):
    type: Literal["RESUME_SYSTEM"]
    payload: ResumeSystemPayload


class ActivateEmergencyStopCommand(_SystemCommandBase):
    type: Literal["ACTIVATE_EMERGENCY_STOP"]
    payload: ActivateEmergencyStopPayload


class RequestPositionCloseCommand(_SystemCommandBase):
    type: Literal["REQUEST_POSITION_CLOSE"]
    payload: RequestPositionClosePayload


class RequestStopLossChangeCommand(_SystemCommandBase):
    type: Literal["REQUEST_STOP_LOSS_CHANGE"]
    payload: RequestStopLossChangePayload


class RequestTakeProfitChangeCommand(_SystemCommandBase):
    type: Literal["REQUEST_TAKE_PROFIT_CHANGE"]
    payload: RequestTakeProfitChangePayload


class RequestRiskPolicyChangeCommand(_SystemCommandBase):
    type: Literal["REQUEST_RISK_POLICY_CHANGE"]
    payload: RequestRiskPolicyChangePayload


type SystemCommand = Annotated[
    ApproveProposalCommand
    | RejectProposalCommand
    | PauseNewTradesCommand
    | ResumeSystemCommand
    | ActivateEmergencyStopCommand
    | RequestPositionCloseCommand
    | RequestStopLossChangeCommand
    | RequestTakeProfitChangeCommand
    | RequestRiskPolicyChangeCommand,
    Field(discriminator="type"),
]

SYSTEM_COMMAND_ADAPTER: TypeAdapter[SystemCommand] = TypeAdapter(SystemCommand)
