"""Bounded historical decision replay, without native, network or current state.

MATCH proves the retained decision can be recalculated. It does not authenticate
source receipts, establish remote persistence, or grant trading eligibility.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import UnionType
from typing import Annotated, Literal, Self, Union, get_args, get_origin
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    ValidationInfo,
    model_validator,
)

from aurum_worker.shadow.context import risk_input_digest
from aurum_worker.shadow.models import ShadowCycle
from aurum_worker.shadow.risk import ShadowRiskInput, evaluate_shadow_risk
from aurum_worker.shadow.strategy import evaluate_baseline_eligibility

MAX_REPLAY_BYTES = 262_144


class ReplayError(ValueError):
    """Only fixed codes cross this boundary, never validation input or tracebacks."""

    def __init__(self, code: Literal["REPLAY_INVALID", "REPLAY_TOO_LARGE"]) -> None:
        self.code = code
        super().__init__(code)


def _utc(value: object) -> object:
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ReplayError("REPLAY_INVALID")
        return value.astimezone(UTC)
    if isinstance(value, dict):
        return {key: _utc(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return tuple(_utc(item) for item in value)
    return value


def _json_model[M: BaseModel](kind: type[M], value: object) -> M:
    """Decode strict Python-only nested validators without disabling strictness.

    All serialized fields, including nulls and defaults, must be explicit. Only
    the field's declared JSON representation is converted before its existing
    model validators run. In particular decimal numbers and boolean integers
    are never accepted as aliases for decimal strings and safety booleans.
    """
    if not isinstance(value, dict):
        raise ReplayError("REPLAY_INVALID")
    fields = {field.alias or name: field for name, field in kind.model_fields.items()}
    if set(value) != set(fields):
        raise ReplayError("REPLAY_INVALID")
    return kind.model_validate(
        {
            name: _json_value(field.annotation, value[name])
            for name, field in fields.items()
        }
    )


def _json_value(annotation: object, value: object) -> object:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _json_value(args[0], value)
    if origin in (Union, UnionType):
        if value is None and type(None) in args:
            return None
        remaining = tuple(item for item in args if item is not type(None))
        if len(remaining) != 1:
            raise ReplayError("REPLAY_INVALID")
        return _json_value(remaining[0], value)
    if origin is Literal:
        if not any(type(value) is type(item) and value == item for item in args):
            raise ReplayError("REPLAY_INVALID")
        return value
    if origin is tuple:
        if not isinstance(value, list) or len(args) != 2 or args[1] is not Ellipsis:
            raise ReplayError("REPLAY_INVALID")
        return tuple(_json_value(args[0], item) for item in value)
    if origin is dict:
        if not isinstance(value, dict) or args != (str, int):
            raise ReplayError("REPLAY_INVALID")
        return {
            _json_value(str, key): _json_value(int, item) for key, item in value.items()
        }
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _json_model(annotation, value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if not isinstance(value, str):
            raise ReplayError("REPLAY_INVALID")
        return annotation(value)
    if annotation in (datetime, AwareDatetime):
        if (
            not isinstance(value, str)
            or re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)",
                value,
            )
            is None
        ):
            raise ReplayError("REPLAY_INVALID")
        return datetime.fromisoformat(value).astimezone(UTC)
    if annotation is UUID:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ReplayError("REPLAY_INVALID")
        return UUID(value)
    if annotation is Decimal:
        if (
            not isinstance(value, str)
            or len(value) > 96
            or re.fullmatch(
                r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value
            )
            is None
        ):
            raise ReplayError("REPLAY_INVALID")
        return Decimal(value)
    if annotation is float:
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            raise ReplayError("REPLAY_INVALID")
        return float(value)
    if annotation in (bool, int, str, type(None)):
        if type(value) is not annotation:
            raise ReplayError("REPLAY_INVALID")
        return value
    raise ReplayError("REPLAY_INVALID")


def _safe_identities(value: object, *, depth: int = 0) -> None:
    if depth > 24:
        raise ReplayError("REPLAY_INVALID")
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.casefold() in {
                "login",
                "server",
                "password",
                "passwd",
                "credential",
                "token",
                "access_token",
                "apikey",
                "api_key",
                "secret",
                "authorization",
                "cookie",
            }:
                raise ReplayError("REPLAY_INVALID")
            if key == "source" and item != "mt5":
                raise ReplayError("REPLAY_INVALID")
            prefix = {
                "account_fingerprint": "mt5-account-v1:",
                "server_fingerprint": "mt5-server-v1:",
                "specification_fingerprint": "mt5-spec-v1:",
                "confirmed_specification_fingerprint": "mt5-spec-v1:",
                "symbol_specification_fingerprint": "mt5-spec-v1:",
            }.get(key)
            if (
                prefix is not None
                and item is not None
                and (
                    not isinstance(item, str)
                    or re.fullmatch(re.escape(prefix) + r"[0-9a-f]{64}", item) is None
                )
            ):
                raise ReplayError("REPLAY_INVALID")
            if (
                key in {"masked_login", "masked_account"}
                and item is not None
                and (
                    not isinstance(item, str)
                    or re.fullmatch(r"••••(?:[0-9]{4})?", item) is None
                )
            ):
                raise ReplayError("REPLAY_INVALID")
            if (
                key == "masked_server"
                and item is not None
                and (
                    not isinstance(item, str)
                    or re.fullmatch(r"(?:[a-z0-9]{1,4}…[0-9a-f]{4}|demo…unknown)", item)
                    is None
                )
            ):
                raise ReplayError("REPLAY_INVALID")
            _safe_identities(item, depth=depth + 1)
    elif isinstance(value, tuple | list):
        for item in value:
            _safe_identities(item, depth=depth + 1)


class ReplayEnvelope(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        hide_input_in_errors=True,
    )

    schema_version: Literal["shadow-replay-v1"] = "shadow-replay-v1"
    environment: Literal["DEMO ONLY"] = "DEMO ONLY"
    mode: Literal["SHADOW"] = "SHADOW"
    grants_eligibility: Literal[False] = False
    cycle: ShadowCycle
    risk_input: ShadowRiskInput

    @model_validator(mode="before")
    @classmethod
    def strict_boundary(cls, value: object, info: ValidationInfo) -> object:
        if isinstance(value, dict):
            if value.get("grants_eligibility", False) is not False:
                raise ValueError("REPLAY_INVALID")
            if info.mode == "json":
                if set(value) != set(cls.model_fields):
                    raise ValueError("REPLAY_INVALID")
                value = dict(value)
                value["risk_input"] = _json_model(ShadowRiskInput, value["risk_input"])
            elif isinstance(value.get("risk_input"), BaseModel):
                value = dict(value)
                value["risk_input"] = value["risk_input"].model_dump(
                    mode="python", by_alias=True, warnings=False
                )
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        cycle, value = self.cycle, self.risk_input
        market, candidate, risk = cycle.market, cycle.candidate, cycle.risk
        _safe_identities(value.model_dump(mode="python", by_alias=True))
        if (
            market is None
            or candidate is None
            or risk is None
            or cycle.eligibility is None
        ):
            raise ValueError("REPLAY_INVALID")
        provenance = value.provenance
        if (
            cycle.id != uuid5(NAMESPACE_URL, "aurum:shadow-cycle:" + cycle.cycle_key)
            or cycle.trace_id != uuid5(NAMESPACE_URL, f"aurum:shadow-trace:{cycle.id}")
            or provenance.owner_id != cycle.owner_id
            or provenance.trading_account_id != cycle.trading_account_id
            or provenance.risk_policy_version_id != cycle.policy_version_id
            or provenance.risk_policy_version != cycle.policy_version
            or provenance.account_fingerprint != market.account_fingerprint
            or provenance.server_fingerprint != market.server_fingerprint
            or provenance.specification_fingerprint != market.specification_fingerprint
            or provenance.broker_symbol != market.broker_symbol
            or provenance.adapter_version != market.adapter_version
            or provenance.market_adapter_version != market.market_adapter_version
            or value.reconciliation_adapter_version != "aurum-reconciliation-v1"
            or value.candidate.provenance != provenance
            or value.candidate.candidate_id != candidate.id
            or candidate.id
            != uuid5(NAMESPACE_URL, f"aurum:shadow-candidate:{cycle.id}")
            or value.candidate.created_at != candidate.created_at
            or value.candidate.expires_at != candidate.expires_at
            or value.candidate.direction.value != candidate.direction
            or value.candidate.entry_price != candidate.entry_price
            or value.candidate.stop_loss_price != candidate.stop_loss_price
            or value.candidate.take_profit_price != candidate.take_profit_price
            or not timedelta(0)
            <= value.evaluated_at - cycle.evaluated_at
            <= timedelta(seconds=600)
            or risk_input_digest(value) != risk.input_digest
        ):
            raise ValueError("REPLAY_INVALID")
        if value.tick is not None and (
            value.tick.tick_at != market.tick_at
            or value.tick.bid != market.bid
            or value.tick.ask != market.ask
            or value.tick.symbol != market.broker_symbol
            or value.tick.adapter_version != market.market_adapter_version
            or value.tick.trace_id != value.candidate.market_trace_id
        ):
            raise ValueError("REPLAY_INVALID")
        if value.account is not None and (
            value.account.account_fingerprint != market.account_fingerprint
            or value.account.server_fingerprint != market.server_fingerprint
            or value.account.adapter_version != market.adapter_version
        ):
            raise ValueError("REPLAY_INVALID")
        if value.specification is not None and (
            value.specification.specification_fingerprint
            != market.specification_fingerprint
            or value.specification.broker_symbol != market.broker_symbol
            or value.specification.point != market.point
            or value.specification.tick_size != market.tick_size
            or value.specification.adapter_version != market.adapter_version
        ):
            raise ValueError("REPLAY_INVALID")
        if value.confirmed_binding is not None and (
            value.confirmed_binding.owner_id != str(cycle.owner_id)
            or value.confirmed_binding.trading_account_id
            != str(cycle.trading_account_id)
            or value.confirmed_binding.broker_symbol != market.broker_symbol
            or value.confirmed_binding.confirmed_specification_fingerprint
            != market.specification_fingerprint
        ):
            raise ValueError("REPLAY_INVALID")
        if value.reconciliation is not None and (
            value.reconciliation.reconciliation_id != str(market.reconciliation_id)
            or value.reconciliation.account_fingerprint != market.account_fingerprint
            or value.reconciliation.server_fingerprint != market.server_fingerprint
            or value.reconciliation.broker_symbol != market.broker_symbol
            or value.reconciliation.symbol_specification_fingerprint
            != market.specification_fingerprint
            or value.reconciliation.adapter_version
            != value.reconciliation_adapter_version
        ):
            raise ValueError("REPLAY_INVALID")
        if value.policy is not None and (
            value.policy.id != cycle.policy_version_id
            or value.policy.version != cycle.policy_version
            or value.policy.owner_id != cycle.owner_id
            or value.policy.trading_account_id != cycle.trading_account_id
            or candidate.expires_at - candidate.created_at
            != timedelta(seconds=value.policy.proposal_expiry_seconds)
        ):
            raise ValueError("REPLAY_INVALID")
        return self


def make_replay_envelope(
    cycle: ShadowCycle, risk_input: ShadowRiskInput
) -> ReplayEnvelope:
    try:
        result = ReplayEnvelope(
            cycle=ShadowCycle.model_validate(
                cycle.model_dump(mode="python", warnings=False)
            ),
            risk_input=ShadowRiskInput.model_validate(
                _utc(
                    risk_input.model_dump(mode="python", by_alias=True, warnings=False)
                )
            ),
        )
        canonical_replay_json(result)
        return result
    except ReplayError:
        raise
    except Exception:
        raise ReplayError("REPLAY_INVALID") from None


def canonical_replay_json(envelope: ReplayEnvelope) -> str:
    try:
        checked = ReplayEnvelope.model_validate(
            _utc(envelope.model_dump(mode="python", by_alias=True, warnings=False))
        )
        text = json.dumps(
            checked.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(text.encode("utf-8")) > MAX_REPLAY_BYTES:
            raise ReplayError("REPLAY_TOO_LARGE")
        return text
    except ReplayError:
        raise
    except Exception:
        raise ReplayError("REPLAY_INVALID") from None


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError("REPLAY_INVALID")
        result[key] = value
    return result


def _not_finite(value: str) -> object:
    raise ReplayError("REPLAY_INVALID")


def parse_replay_json(text: str) -> ReplayEnvelope:
    try:
        if not isinstance(text, str):
            raise ReplayError("REPLAY_INVALID")
        if len(text.encode("utf-8")) > MAX_REPLAY_BYTES:
            raise ReplayError("REPLAY_TOO_LARGE")
        value = json.loads(text, object_pairs_hook=_unique, parse_constant=_not_finite)
        if not isinstance(value, dict) or set(value) != set(
            ReplayEnvelope.model_fields
        ):
            raise ReplayError("REPLAY_INVALID")
        # The JSON-mode cycle validator also requires every nested wire default.
        value["cycle"] = ShadowCycle.model_validate_json(json.dumps(value["cycle"]))
        value["risk_input"] = _json_model(ShadowRiskInput, value["risk_input"])
        result = ReplayEnvelope.model_validate(value)
        canonical_replay_json(result)
        return result
    except ReplayError:
        raise
    except Exception:
        raise ReplayError("REPLAY_INVALID") from None


@dataclass(frozen=True, slots=True)
class ReplayVerification:
    status: Literal["MATCH", "MISMATCH", "UNAVAILABLE"]
    code: Literal[
        "REPLAY_MATCH",
        "REPLAY_RISK_MISMATCH",
        "REPLAY_ELIGIBILITY_MISMATCH",
        "REPLAY_IDENTITY_MISMATCH",
        "REPLAY_POLICY_UNAVAILABLE",
        "REPLAY_INVALID",
    ]
    grants_eligibility: Literal[False] = False


def verify_replay(
    envelope: ReplayEnvelope, *, owner_id: UUID, trading_account_id: UUID
) -> ReplayVerification:
    try:
        checked = parse_replay_json(canonical_replay_json(envelope))
        cycle, value = checked.cycle, checked.risk_input
        if (
            type(owner_id) is not UUID
            or type(trading_account_id) is not UUID
            or (
                cycle.owner_id != owner_id
                or cycle.trading_account_id != trading_account_id
            )
        ):
            return ReplayVerification("UNAVAILABLE", "REPLAY_IDENTITY_MISMATCH")
        result = evaluate_shadow_risk(value)
        risk = cycle.risk
        assert risk is not None
        if (
            result.outcome != risk.outcome
            or tuple((item.code, item.passed) for item in result.checks)
            != tuple((item.code, item.passed) for item in risk.checks)
            or result.calculated_volume != risk.calculated_volume
            or result.estimated_loss_usd != risk.estimated_loss_usd
            or result.estimated_net_reward_usd != risk.estimated_net_reward_usd
            or cycle.status != ("PROPOSAL" if result.outcome == "PASS" else "BLOCK")
            or cycle.reason_codes
            != (
                tuple(item.code for item in result.checks if not item.passed)[:32]
                if result.outcome == "BLOCK"
                else ("SHADOW_RESEARCH_ONLY", "ELIGIBILITY_BLOCKED")
            )
        ):
            return ReplayVerification("MISMATCH", "REPLAY_RISK_MISMATCH")
        if value.policy is None:
            return ReplayVerification("UNAVAILABLE", "REPLAY_POLICY_UNAVAILABLE")
        eligibility = evaluate_baseline_eligibility(
            minimum_sample_size=value.policy.minimum_sample_size,
            risk_passed=result.outcome == "PASS",
        )
        if eligibility != cycle.eligibility:
            return ReplayVerification("MISMATCH", "REPLAY_ELIGIBILITY_MISMATCH")
        return ReplayVerification("MATCH", "REPLAY_MATCH")
    except Exception:
        return ReplayVerification("UNAVAILABLE", "REPLAY_INVALID")
