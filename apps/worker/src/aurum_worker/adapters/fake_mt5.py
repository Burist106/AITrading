"""Deterministic cross-platform fake for the complete MT5 read port."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from aurum_worker.adapters.protocols import Mt5ReadPort
from aurum_worker.models.mt5 import (
    AccountObservation,
    ActiveOrderObservation,
    BrokerSymbolCandidate,
    BrokerSymbolObservation,
    CandleRequest,
    CandleSeries,
    HistoricalDealObservation,
    HistoricalOrderObservation,
    HistoryRequest,
    LatestTickObservation,
    Mt5ReadFailure,
    Mt5ReasonCode,
    OpenPositionObservation,
    SafeMt5Error,
    TerminalObservation,
    Timeframe,
)


@dataclass(slots=True)
class FakeMt5ReadAdapter(Mt5ReadPort):
    """Explicit fake state; no native package, clock, randomness, or broker access."""

    terminal: TerminalObservation
    accounts: tuple[AccountObservation, ...]
    candidates: tuple[BrokerSymbolCandidate, ...]
    specifications: dict[str, BrokerSymbolObservation]
    ticks: dict[str, LatestTickObservation]
    candles: dict[tuple[str, Timeframe], CandleSeries]
    positions: tuple[OpenPositionObservation, ...] = ()
    orders: tuple[ActiveOrderObservation, ...] = ()
    order_history: tuple[HistoricalOrderObservation, ...] = ()
    deal_history: tuple[HistoricalDealObservation, ...] = ()
    failures: dict[str, Mt5ReasonCode] = field(default_factory=dict)
    connected: bool = False
    call_log: list[str] = field(default_factory=list)
    _account_index: int = 0
    _lock: RLock = field(default_factory=RLock, repr=False)

    def _record(self, method: str) -> None:
        with self._lock:
            self.call_log.append(method)
            reason = self.failures.get(method)
            if reason:
                raise Mt5ReadFailure(
                    SafeMt5Error(
                        reason_code=reason,
                        safe_detail=f"Fake {method} failure.",
                        retryable=True,
                    )
                )
            if method not in {"connect", "disconnect"} and not self.connected:
                raise Mt5ReadFailure(
                    SafeMt5Error(
                        reason_code=Mt5ReasonCode.TERMINAL_DISCONNECTED,
                        safe_detail="Fake terminal is disconnected.",
                        retryable=True,
                    )
                )

    def connect(self, *, trace_id: str) -> TerminalObservation:
        self._record("connect")
        with self._lock:
            self.connected = True
            if (
                self._account_index + 1 < len(self.accounts)
                and self.call_log.count("connect") > 1
            ):
                self._account_index += 1
            return self.terminal.model_copy(
                update={"connected": True, "trace_id": trace_id}
            )

    def disconnect(self) -> None:
        self._record("disconnect")
        with self._lock:
            self.connected = False

    def get_terminal_info(self, *, trace_id: str) -> TerminalObservation:
        self._record("get_terminal_info")
        return self.terminal.model_copy(
            update={"connected": self.connected, "trace_id": trace_id}
        )

    def get_account_info(self, *, trace_id: str) -> AccountObservation:
        self._record("get_account_info")
        if not self.accounts:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.ACCOUNT_INFO_UNAVAILABLE,
                    safe_detail="Fake account observation is unavailable.",
                )
            )
        return self.accounts[self._account_index].model_copy(
            update={"trace_id": trace_id}
        )

    def list_symbol_candidates(self, *, trace_id: str) -> list[BrokerSymbolCandidate]:
        self._record("list_symbol_candidates")
        return [
            item.model_copy(update={"trace_id": trace_id}) for item in self.candidates
        ]

    def get_symbol_specification(
        self, broker_symbol: str, *, trace_id: str
    ) -> BrokerSymbolObservation:
        self._record("get_symbol_specification")
        try:
            specification = self.specifications[broker_symbol]
        except KeyError as error:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.SYMBOL_NOT_FOUND,
                    safe_detail="Configured broker symbol was not found.",
                )
            ) from error
        return specification.model_copy(update={"trace_id": trace_id})

    def get_latest_tick(
        self, broker_symbol: str, *, trace_id: str
    ) -> LatestTickObservation:
        self._record("get_latest_tick")
        try:
            tick = self.ticks[broker_symbol]
        except KeyError as error:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.TICK_UNAVAILABLE,
                    safe_detail="Latest tick is unavailable.",
                    retryable=True,
                )
            ) from error
        return tick.model_copy(update={"trace_id": trace_id})

    def get_candles(
        self,
        broker_symbol: str,
        timeframe: Timeframe,
        request: CandleRequest,
        *,
        trace_id: str,
    ) -> CandleSeries:
        self._record("get_candles")
        try:
            series = self.candles[(broker_symbol, timeframe)]
        except KeyError as error:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.CANDLE_DATA_INVALID,
                    safe_detail="Candle data is unavailable.",
                    retryable=True,
                )
            ) from error
        requested = series.candles[: request.count]
        return CandleSeries(
            candles=tuple(
                candle.model_copy(update={"trace_id": trace_id}) for candle in requested
            ),
            gaps=series.gaps,
        )

    def get_open_positions(self, *, trace_id: str) -> list[OpenPositionObservation]:
        self._record("get_open_positions")
        return [
            item.model_copy(update={"trace_id": trace_id}) for item in self.positions
        ]

    def get_active_orders(self, *, trace_id: str) -> list[ActiveOrderObservation]:
        self._record("get_active_orders")
        return [item.model_copy(update={"trace_id": trace_id}) for item in self.orders]

    def get_order_history(
        self, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalOrderObservation]:
        self._record("get_order_history")
        return [
            item.model_copy(update={"trace_id": trace_id})
            for item in self.order_history
            if request.start_at <= item.setup_at <= request.end_at
        ]

    def get_deal_history(
        self, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalDealObservation]:
        self._record("get_deal_history")
        return [
            item.model_copy(update={"trace_id": trace_id})
            for item in self.deal_history
            if request.start_at <= item.occurred_at <= request.end_at
        ]

    def replace_tick(self, symbol: str, tick: LatestTickObservation) -> None:
        """Deterministic scenario transition used by reconnect/polling tests."""

        with self._lock:
            self.ticks[symbol] = tick

    def replace_terminal(self, terminal: TerminalObservation) -> None:
        with self._lock:
            self.terminal = terminal
