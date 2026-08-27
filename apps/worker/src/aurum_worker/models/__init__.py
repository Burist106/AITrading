"""Strict Pydantic equivalents of Aurum cross-boundary contracts."""

from aurum_worker.models.commands import (
    SYSTEM_COMMAND_ADAPTER,
    SYSTEM_COMMAND_PAYLOAD_ADAPTER,
    SystemCommand,
)
from aurum_worker.models.eligibility import EligibilityCheck, EligibilityPolicyResult
from aurum_worker.models.emergency_stop import EmergencyStopState
from aurum_worker.models.health import SystemComponentHealth, SystemHealthSnapshot
from aurum_worker.models.positions import PersistedPosition, Position
from aurum_worker.models.risk_checks import PersistedRiskCheck, RiskCheck
from aurum_worker.models.risk_policy import RiskPolicyVersion
from aurum_worker.models.safety import (
    BOOTSTRAP_SAFETY_POLICY,
    BootstrapSafetyPolicy,
)
from aurum_worker.models.scenarios import PrototypeScenarioId
from aurum_worker.models.trading import (
    BrokerSymbolSpecification,
    MobileApprovalSession,
    PersistedTradeProposal,
    PositionSizingResult,
    TradeProposal,
)

__all__ = [
    "BOOTSTRAP_SAFETY_POLICY",
    "SYSTEM_COMMAND_ADAPTER",
    "SYSTEM_COMMAND_PAYLOAD_ADAPTER",
    "BootstrapSafetyPolicy",
    "BrokerSymbolSpecification",
    "EligibilityCheck",
    "EligibilityPolicyResult",
    "EmergencyStopState",
    "MobileApprovalSession",
    "PositionSizingResult",
    "Position",
    "PersistedPosition",
    "PrototypeScenarioId",
    "PersistedRiskCheck",
    "PersistedTradeProposal",
    "RiskCheck",
    "RiskPolicyVersion",
    "SystemCommand",
    "SystemComponentHealth",
    "SystemHealthSnapshot",
    "TradeProposal",
]
