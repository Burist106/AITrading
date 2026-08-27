"""Read-only and health-only adapter boundaries for the Bootstrap Milestone."""

from aurum_worker.adapters.fakes import FakeBrokerReadAdapter, FakeSubsystemAdapter
from aurum_worker.adapters.protocols import (
    BrokerReadAdapter,
    ExecutionAdapter,
    Mt5ReadAdapter,
    NotificationAdapter,
    PersistenceAdapter,
    RiskAdapter,
    StrategyAdapter,
)

__all__ = [
    "BrokerReadAdapter",
    "ExecutionAdapter",
    "FakeBrokerReadAdapter",
    "FakeSubsystemAdapter",
    "Mt5ReadAdapter",
    "NotificationAdapter",
    "PersistenceAdapter",
    "RiskAdapter",
    "StrategyAdapter",
]
