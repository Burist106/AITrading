"""System health wire contracts and deterministic aggregation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, model_validator

from aurum_worker.models.base import Identifier, WireModel


class SystemHealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    WARNING = "warning"
    FAILED = "failed"
    UNKNOWN = "unknown"


class SystemPlane(StrEnum):
    CONTROL_PLANE = "control_plane"
    EXECUTION_PLANE = "execution_plane"


class SystemComponentHealth(WireModel):
    code: Identifier
    label_th: Identifier
    plane: SystemPlane
    state: SystemHealthState
    detail: Identifier
    observed_at: AwareDatetime


class SystemHealthSnapshot(WireModel):
    captured_at: AwareDatetime
    components: tuple[SystemComponentHealth, ...]

    @model_validator(mode="after")
    def require_components(self) -> SystemHealthSnapshot:
        if not self.components:
            raise ValueError("System health snapshot requires a component.")
        return self


_STATE_SEVERITY: dict[SystemHealthState, int] = {
    SystemHealthState.HEALTHY: 0,
    SystemHealthState.UNKNOWN: 1,
    SystemHealthState.DEGRADED: 2,
    SystemHealthState.WARNING: 3,
    SystemHealthState.FAILED: 4,
}


def derive_system_health_state(
    components: tuple[SystemComponentHealth, ...],
) -> SystemHealthState:
    """Return the worst reported state; an empty set is uncertain."""

    if not components:
        return SystemHealthState.UNKNOWN
    return max(components, key=lambda item: _STATE_SEVERITY[item.state]).state
