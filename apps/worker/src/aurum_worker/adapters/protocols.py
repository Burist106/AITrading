"""Capability-limited adapter protocols.

All Bootstrap boundaries are either broker-read-only or subsystem-health-only.
The execution boundary is intentionally health-only until a later milestone is
explicitly authorized.
"""

from typing import Literal, Protocol, runtime_checkable

from aurum_worker.models.bootstrap import AccountInspection
from aurum_worker.models.health import SystemComponentHealth
from aurum_worker.models.trading import BrokerSymbolSpecification

CanonicalSymbol = Literal["XAUUSD"]


@runtime_checkable
class BrokerReadAdapter(Protocol):
    """Only the broker observations needed for fail-closed Bootstrap startup."""

    async def inspect_account(self) -> AccountInspection: ...

    async def read_symbol_specification(
        self, canonical_symbol: CanonicalSymbol
    ) -> BrokerSymbolSpecification | None: ...

    async def count_open_positions(
        self, canonical_symbol: CanonicalSymbol
    ) -> int | None: ...


@runtime_checkable
class Mt5ReadAdapter(BrokerReadAdapter, Protocol):
    """Future MT5 boundary; Bootstrap grants read capability only."""


class PersistenceAdapter(Protocol):
    """Future persistence boundary, limited to health in Bootstrap."""

    async def health(self) -> SystemComponentHealth: ...


class StrategyAdapter(Protocol):
    """Future strategy boundary, limited to health in Bootstrap."""

    async def health(self) -> SystemComponentHealth: ...


class RiskAdapter(Protocol):
    """Future deterministic-risk boundary, limited to health in Bootstrap."""

    async def health(self) -> SystemComponentHealth: ...


class ExecutionAdapter(Protocol):
    """Reserved execution boundary with no trading operation in Bootstrap."""

    async def health(self) -> SystemComponentHealth: ...


class NotificationAdapter(Protocol):
    """Future notification boundary, limited to health in Bootstrap."""

    async def health(self) -> SystemComponentHealth: ...
