"""Fixed Bootstrap safety-policy tests."""

import pytest
from pydantic import ValidationError

from aurum_worker.models.safety import (
    BOOTSTRAP_SAFETY_POLICY,
    BootstrapSafetyPolicy,
)
from aurum_worker.models.scenarios import PrototypeScenarioId


def test_bootstrap_policy_is_locked_and_serializes_camel_case() -> None:
    assert BOOTSTRAP_SAFETY_POLICY.model_dump(mode="json") == {
        "schemaVersion": 1,
        "environment": "DEMO_ONLY",
        "runtimeMode": "shadow",
        "canonicalSymbol": "XAUUSD",
        "maximumPermittedVolume": 0.01,
        "maximumOpenPositions": 1,
        "stopLossRequired": True,
    }


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("environment", "PRODUCTION"),
        ("runtimeMode", "conditional_auto"),
        ("canonicalSymbol", "EURUSD"),
        ("maximumPermittedVolume", 0.02),
        ("maximumOpenPositions", 2),
        ("stopLossRequired", False),
    ],
)
def test_bootstrap_policy_rejects_every_unsafe_variant(
    field: str, unsafe_value: object
) -> None:
    payload = BOOTSTRAP_SAFETY_POLICY.model_dump(mode="json")
    payload[field] = unsafe_value

    with pytest.raises(ValidationError):
        BootstrapSafetyPolicy.model_validate(payload)


def test_wire_models_reject_python_field_names_and_unknown_fields() -> None:
    payload = BOOTSTRAP_SAFETY_POLICY.model_dump(mode="json")
    payload["runtime_mode"] = payload.pop("runtimeMode")
    payload["unknown"] = "not permitted"

    with pytest.raises(ValidationError):
        BootstrapSafetyPolicy.model_validate(payload)


def test_scenario_contract_has_exactly_twenty_ids() -> None:
    assert len(PrototypeScenarioId) == 20
    assert PrototypeScenarioId.NO_SIGNAL.value == "no_signal"
    assert (
        PrototypeScenarioId.MINIMUM_LOT_EXCEEDS_RISK.value == "minimum_lot_exceeds_risk"
    )
