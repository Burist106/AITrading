"""Fixed Bootstrap safety policy."""

from typing import Literal

from aurum_worker.models.base import MaximumPermittedVolume, WireModel


class BootstrapSafetyPolicy(WireModel):
    """Compile-time and runtime locked Demo policy."""

    schema_version: Literal[1]
    environment: Literal["DEMO_ONLY"]
    runtime_mode: Literal["shadow"]
    canonical_symbol: Literal["XAUUSD"]
    maximum_permitted_volume: MaximumPermittedVolume
    maximum_open_positions: Literal[1]
    stop_loss_required: Literal[True]


BOOTSTRAP_SAFETY_POLICY = BootstrapSafetyPolicy.model_validate(
    {
        "schemaVersion": 1,
        "environment": "DEMO_ONLY",
        "runtimeMode": "shadow",
        "canonicalSymbol": "XAUUSD",
        "maximumPermittedVolume": 0.01,
        "maximumOpenPositions": 1,
        "stopLossRequired": True,
    }
)
