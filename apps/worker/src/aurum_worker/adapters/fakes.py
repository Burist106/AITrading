"""In-memory adapters for tests and local Bootstrap development."""

from dataclasses import dataclass
from typing import Literal

from aurum_worker.models.bootstrap import AccountInspection
from aurum_worker.models.health import SystemComponentHealth
from aurum_worker.models.trading import BrokerSymbolSpecification


@dataclass(frozen=True, slots=True)
class FakeBrokerReadAdapter:
    account: AccountInspection
    symbol_specification: BrokerSymbolSpecification | None
    open_position_count: int | None

    async def inspect_account(self) -> AccountInspection:
        return self.account

    async def read_symbol_specification(
        self, canonical_symbol: Literal["XAUUSD"]
    ) -> BrokerSymbolSpecification | None:
        return self.symbol_specification

    async def count_open_positions(
        self, canonical_symbol: Literal["XAUUSD"]
    ) -> int | None:
        return self.open_position_count


@dataclass(frozen=True, slots=True)
class FakeSubsystemAdapter:
    component: SystemComponentHealth

    async def health(self) -> SystemComponentHealth:
        return self.component
