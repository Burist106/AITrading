"""Capability-limited adapter protocols.

All Bootstrap boundaries are either broker-read-only or subsystem-health-only.
The execution boundary is intentionally health-only until a later milestone is
explicitly authorized.
"""

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from aurum_worker.models.bootstrap import AccountInspection
from aurum_worker.models.health import SystemComponentHealth
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountVerificationState,
    ActiveOrderObservation,
    BrokerSymbolCandidate,
    BrokerSymbolObservation,
    CandleRequest,
    CandleSeries,
    ComponentHeartbeat,
    DatabaseReconciliationState,
    HistoricalDealObservation,
    HistoricalOrderObservation,
    HistoryRequest,
    LatestTickObservation,
    OpenPositionObservation,
    ReconciliationMismatch,
    ReconciliationReport,
    TerminalObservation,
    Timeframe,
)
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


@runtime_checkable
class Mt5ReadPort(Protocol):
    """Complete Milestone 2 read-only terminal capability."""

    def connect(self, *, trace_id: str) -> TerminalObservation: ...

    def disconnect(self) -> None: ...

    def get_terminal_info(self, *, trace_id: str) -> TerminalObservation: ...

    def get_account_info(self, *, trace_id: str) -> AccountObservation: ...

    def list_symbol_candidates(
        self, *, trace_id: str
    ) -> list[BrokerSymbolCandidate]: ...

    def get_symbol_specification(
        self, broker_symbol: str, *, trace_id: str
    ) -> BrokerSymbolObservation: ...

    def get_latest_tick(
        self, broker_symbol: str, *, trace_id: str
    ) -> LatestTickObservation: ...

    def get_candles(
        self,
        broker_symbol: str,
        timeframe: Timeframe,
        request: CandleRequest,
        *,
        trace_id: str,
    ) -> CandleSeries: ...

    def get_open_positions(self, *, trace_id: str) -> list[OpenPositionObservation]: ...

    def get_active_orders(self, *, trace_id: str) -> list[ActiveOrderObservation]: ...

    def get_order_history(
        self, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalOrderObservation]: ...

    def get_deal_history(
        self, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalDealObservation]: ...


class Mt5ObservationPersistencePort(Protocol):
    """Least-privilege observation/reporting RPC boundary."""

    def record_account(
        self,
        observation: AccountObservation,
        verification_state: AccountVerificationState,
    ) -> str: ...

    def record_symbol(
        self, observation: BrokerSymbolObservation, account_fingerprint: str
    ) -> str: ...

    def upsert_tick(
        self, observation: LatestTickObservation, account_fingerprint: str
    ) -> str: ...

    def load_reconciliation_state(self) -> DatabaseReconciliationState: ...

    def begin_reconciliation(self, report: ReconciliationReport) -> str: ...

    def record_mismatch(
        self, reconciliation_id: str, mismatch: ReconciliationMismatch
    ) -> str: ...

    def complete_reconciliation(self, report: ReconciliationReport) -> str: ...

    def record_component_heartbeat(self, heartbeat: ComponentHeartbeat) -> str: ...

    def record_incident(
        self,
        code: str,
        severity: str,
        title: str,
        detail: str,
        trace_id: str,
        occurred_at: datetime,
    ) -> str: ...


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
