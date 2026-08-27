"""Read-only and health-only adapter boundaries for the Bootstrap Milestone."""

from aurum_worker.adapters.fake_mt5 import FakeMt5ReadAdapter
from aurum_worker.adapters.fakes import FakeBrokerReadAdapter, FakeSubsystemAdapter
from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import (
    InMemoryMt5ObservationPersistence,
    WorkerRpcMt5ObservationPersistence,
)
from aurum_worker.adapters.protocols import (
    BrokerReadAdapter,
    ExecutionAdapter,
    Mt5ObservationPersistencePort,
    Mt5ReadAdapter,
    Mt5ReadPort,
    NotificationAdapter,
    PersistenceAdapter,
    RiskAdapter,
    StrategyAdapter,
)

__all__ = [
    "BrokerReadAdapter",
    "ExecutionAdapter",
    "FakeMt5ReadAdapter",
    "FakeBrokerReadAdapter",
    "FakeSubsystemAdapter",
    "Mt5ReadAdapter",
    "MetaTrader5ReadAdapter",
    "Mt5ObservationPersistencePort",
    "Mt5ReadPort",
    "InMemoryMt5ObservationPersistence",
    "NotificationAdapter",
    "PersistenceAdapter",
    "RiskAdapter",
    "StrategyAdapter",
    "WorkerRpcMt5ObservationPersistence",
]
