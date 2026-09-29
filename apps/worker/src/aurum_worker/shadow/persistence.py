"""Strict account-scoped Shadow RPC reads and immutable journal writes."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from aurum_worker.adapters.persistence_mt5 import WorkerRpcClient
from aurum_worker.models.risk_policy import RiskPolicyVersion
from aurum_worker.shadow.context import ShadowControlContext
from aurum_worker.shadow.models import ShadowCycle, ShadowOutcomeEvent

_NOT_READY_CODES = frozenset(
    {
        "WORKER_UNAUTHORIZED",
        "ACCOUNT_UNAVAILABLE",
        "SAFETY_STATE_BLOCKED",
        "POLICY_UNAVAILABLE",
    }
)
_POLICY_BOOLEAN_FIELDS = (
    "stop_loss_required",
    "martingale_allowed",
    "grid_trading_allowed",
    "averaging_down_allowed",
    "loss_based_volume_increase_allowed",
    "require_calibrated_model",
    "automatic_retry_on_broker_reject",
)


class ShadowPersistenceCode(StrEnum):
    TRANSPORT_UNAVAILABLE = "SHADOW_TRANSPORT_UNAVAILABLE"
    RESPONSE_INVALID = "SHADOW_RESPONSE_INVALID"
    REQUEST_INVALID = "SHADOW_REQUEST_INVALID"
    RPC_REJECTED = "SHADOW_RPC_REJECTED"


class ShadowPersistenceError(RuntimeError):
    def __init__(self, code: ShadowPersistenceCode) -> None:
        self.code = code
        super().__init__(code.value)


def _parse[M: BaseModel](model: type[M], payload: object) -> M:
    try:
        parsed = model.model_validate_json(json.dumps(payload, allow_nan=False))
        if not _same_shape(payload, parsed.model_dump(mode="json", by_alias=True)):
            raise ValueError("wire fields must all be explicit")
        return parsed
    except Exception:
        raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID) from None


def _same_shape(raw: object, normalized: object) -> bool:
    if isinstance(normalized, dict):
        return (
            isinstance(raw, dict)
            and set(raw) == set(normalized)
            and all(_same_shape(raw[key], value) for key, value in normalized.items())
        )
    if isinstance(normalized, list):
        return (
            isinstance(raw, list)
            and len(raw) == len(normalized)
            and all(
                _same_shape(left, right)
                for left, right in zip(raw, normalized, strict=True)
            )
        )
    return True


def _policy(raw: object) -> RiskPolicyVersion:
    if not isinstance(raw, dict) or set(raw) != set(RiskPolicyVersion.model_fields):
        raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
    if any(type(raw[name]) is not bool for name in _POLICY_BOOLEAN_FIELDS):
        raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
    if type(raw["maximum_open_positions"]) is not int:
        raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
    camel = {
        field.alias: raw[name] for name, field in RiskPolicyVersion.model_fields.items()
    }
    return _parse(RiskPolicyVersion, camel)


class RpcShadowStore:
    def __init__(self, client: WorkerRpcClient) -> None:
        self._client = client

    def _call(self, function: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            result = self._client.call(function, payload)
            if not isinstance(result, dict):
                raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
            return result
        except ShadowPersistenceError:
            raise
        except Exception:
            raise ShadowPersistenceError(
                ShadowPersistenceCode.TRANSPORT_UNAVAILABLE
            ) from None

    def read_context(self, account_id: UUID) -> ShadowControlContext | None:
        if not isinstance(account_id, UUID):
            raise ShadowPersistenceError(ShadowPersistenceCode.REQUEST_INVALID)
        response = self._call(
            "worker_read_shadow_context", {"p_trading_account_id": str(account_id)}
        )
        if set(response) != {"result_code", "data"}:
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        code, data = response["result_code"], response["data"]
        if isinstance(code, str) and code in _NOT_READY_CODES and data is None:
            return None
        if code != "CONTEXT_READY" or not isinstance(data, dict):
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        if set(data) != {
            "owner_id",
            "trading_account_id",
            "observed_at",
            "mode_version",
            "system_state",
            "policy",
        }:
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        policy = _policy(data["policy"])
        context = _parse(
            ShadowControlContext,
            data | {"policy": policy.model_dump(mode="json", by_alias=True)},
        )
        if context.trading_account_id != account_id:
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        return context

    def read_cycles(
        self, account_id: UUID, cycle_key: str | None = None
    ) -> tuple[tuple[ShadowCycle, ...], tuple[ShadowOutcomeEvent, ...]]:
        if not isinstance(account_id, UUID) or (
            cycle_key is not None
            and (
                not isinstance(cycle_key, str)
                or re.fullmatch(r"[0-9a-f]{64}", cycle_key) is None
            )
        ):
            raise ShadowPersistenceError(ShadowPersistenceCode.REQUEST_INVALID)
        response = self._call(
            "worker_read_shadow_cycles",
            {"p_trading_account_id": str(account_id), "p_cycle_key": cycle_key},
        )
        if set(response) != {"result_code", "data"}:
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        if response["result_code"] != "CYCLES_READ":
            raise ShadowPersistenceError(ShadowPersistenceCode.RPC_REJECTED)
        data = response["data"]
        if not isinstance(data, dict) or set(data) != {"cycles", "outcomes"}:
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        raw_cycles, raw_outcomes = data["cycles"], data["outcomes"]
        if (
            not isinstance(raw_cycles, list)
            or not isinstance(raw_outcomes, list)
            or len(raw_cycles) > (1 if cycle_key is not None else 100)
            or len(raw_outcomes) > 3200
        ):
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        cycles = tuple(_parse(ShadowCycle, row) for row in raw_cycles)
        outcomes = tuple(_parse(ShadowOutcomeEvent, row) for row in raw_outcomes)
        if (
            any(cycle.trading_account_id != account_id for cycle in cycles)
            or any(
                cycle_key is not None and cycle.cycle_key != cycle_key
                for cycle in cycles
            )
            or len({cycle.id for cycle in cycles}) != len(cycles)
            or len({cycle.cycle_key for cycle in cycles}) != len(cycles)
            or len({cycle.owner_id for cycle in cycles}) > 1
            or len({event.id for event in outcomes}) != len(outcomes)
        ):
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        by_id = {cycle.id: cycle for cycle in cycles}
        for event in outcomes:
            cycle = by_id.get(event.cycle_id)
            if (
                cycle is None
                or cycle.status != "PROPOSAL"
                or event.owner_id != cycle.owner_id
                or event.trading_account_id != account_id
                or event.observed_at <= cycle.evaluated_at
            ):
                raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        for cycle in cycles:
            events = sorted(
                (event for event in outcomes if event.cycle_id == cycle.id),
                key=lambda item: item.sequence,
            )
            if len(events) > 32 or any(
                event.sequence != index + 1 for index, event in enumerate(events)
            ):
                raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
            if any(
                left.observed_at >= right.observed_at or left.status != "OBSERVED"
                for left, right in zip(events, events[1:], strict=False)
            ):
                raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        return cycles, outcomes

    def _record(
        self,
        function: str,
        parameter: str,
        payload: dict[str, object],
        identifier: UUID,
        identifier_key: str,
        success_code: str,
    ) -> str:
        response = self._call(function, {parameter: payload})
        code = response.get("result_code")
        if code not in (success_code, "IDEMPOTENT_REPLAY"):
            raise ShadowPersistenceError(ShadowPersistenceCode.RPC_REJECTED)
        if (
            set(response) != {"result_code", identifier_key, "created"}
            or response[identifier_key] != str(identifier)
            or type(response["created"]) is not bool
            or response["created"] is not (code == success_code)
        ):
            raise ShadowPersistenceError(ShadowPersistenceCode.RESPONSE_INVALID)
        return str(code)

    def record_cycle(self, cycle: ShadowCycle) -> str:
        try:
            validated = ShadowCycle.model_validate_json(
                cycle.model_dump_json(warnings=False)
            )
        except Exception:
            raise ShadowPersistenceError(
                ShadowPersistenceCode.REQUEST_INVALID
            ) from None
        return self._record(
            "worker_record_shadow_cycle",
            "p_cycle",
            validated.model_dump(mode="json"),
            validated.id,
            "cycle_id",
            "CYCLE_RECORDED",
        )

    def append_outcome(self, event: ShadowOutcomeEvent) -> str:
        try:
            validated = ShadowOutcomeEvent.model_validate_json(
                event.model_dump_json(warnings=False)
            )
        except Exception:
            raise ShadowPersistenceError(
                ShadowPersistenceCode.REQUEST_INVALID
            ) from None
        return self._record(
            "worker_append_shadow_outcome",
            "p_event",
            validated.model_dump(mode="json"),
            validated.id,
            "event_id",
            "OUTCOME_RECORDED",
        )
