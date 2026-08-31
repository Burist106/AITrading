"""Windows-only, lazy, serialized adapter for the official MT5 Python package."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from threading import RLock
from types import TracebackType
from typing import Literal, Protocol, Self, cast

from aurum_worker.adapters.protocols import Mt5ReadPort
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountTradeMode,
    ActiveOrderObservation,
    BrokerSymbolCandidate,
    BrokerSymbolObservation,
    CandleObservation,
    CandleRequest,
    CandleSeries,
    HistoricalDealObservation,
    HistoricalOrderObservation,
    HistoryRequest,
    LatestTickObservation,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    OpenPositionObservation,
    PositionDirection,
    SafeMt5Error,
    SymbolTradeMode,
    SymbolUsabilityState,
    TerminalObservation,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_safety import (
    account_fingerprint,
    candle_gaps,
    candle_is_complete,
    decimal_from_native,
    is_canonical_xauusd,
    mask_login,
    mask_server,
    sanitize_comment,
    server_fingerprint,
    signed_decimal_from_native,
    specification_fingerprint,
    utc_from_epoch,
    utc_from_epoch_milliseconds,
)

ADAPTER_VERSION = "aurum-mt5-read-v1"


class NativeMt5Module(Protocol):
    TIMEFRAME_M1: int
    TIMEFRAME_M5: int
    TIMEFRAME_M15: int
    TIMEFRAME_H1: int

    def initialize(self, path: str, /) -> bool: ...

    def shutdown(self) -> None: ...

    def version(self) -> object: ...

    def last_error(self) -> object: ...

    def terminal_info(self) -> object: ...

    def account_info(self) -> object: ...

    def symbols_get(self) -> object: ...

    def symbol_info(self, symbol: str) -> object: ...

    def symbol_info_tick(self, symbol: str) -> object: ...

    def copy_rates_from_pos(
        self, symbol: str, timeframe: int, start_position: int, count: int
    ) -> object: ...

    def copy_rates_range(
        self, symbol: str, timeframe: int, start: datetime, end: datetime
    ) -> object: ...

    def positions_get(self) -> object: ...

    def orders_get(self) -> object: ...

    def history_orders_get(self, start: datetime, end: datetime) -> object: ...

    def history_deals_get(self, start: datetime, end: datetime) -> object: ...


def _field(raw: object, name: str, default: object | None = None) -> object:
    if isinstance(raw, Mapping):
        return raw.get(name, default)
    try:
        return getattr(raw, name)
    except AttributeError:
        try:
            return raw[name]  # type: ignore[index]
        except (IndexError, KeyError, TypeError):
            return default


def _required(raw: object, name: str) -> object:
    value = _field(raw, name)
    if value is None:
        raise ValueError(f"required field unavailable: {name}")
    return value


def _required_bool(raw: object, name: str) -> bool:
    value = _required(raw, name)
    if type(value) is not bool:
        raise ValueError(f"required boolean field invalid: {name}")
    return value


def _optional_bool(raw: object, name: str) -> bool | None:
    value = _field(raw, name)
    if value is None:
        return None
    if type(value) is not bool:
        raise ValueError(f"optional boolean field invalid: {name}")
    return value


def _safe_code(value: object) -> int | None:
    if isinstance(value, tuple) and value and isinstance(value[0], int):
        return value[0]
    return None


def _ticket(value: object) -> str:
    if isinstance(value, bool):
        raise ValueError("invalid ticket")
    normalized = str(value)
    if normalized.endswith(".0"):
        normalized = normalized[:-2]
    if not normalized.isdecimal():
        raise ValueError("invalid ticket")
    return normalized


def _stable_code(prefix: str, value: object) -> str:
    return f"{prefix}_{int(cast(int | float | str, value))}"


class MetaTrader5ReadAdapter(Mt5ReadPort):
    """The only production source allowed to access native MT5 package state."""

    _process_lock = RLock()
    _active_owner: int | None = None

    def __init__(
        self,
        config: Mt5WorkerConfig,
        *,
        clock: Callable[[], datetime] | None = None,
        platform: str | None = None,
        module: NativeMt5Module | None = None,
    ) -> None:
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))
        self._platform = platform or sys.platform
        self._mt5 = module
        self._connected = False
        self._terminal: TerminalObservation | None = None

    def _failure(
        self, reason: Mt5ReasonCode, detail: str, *, retryable: bool = False
    ) -> Mt5ReadFailure:
        return Mt5ReadFailure(
            SafeMt5Error(
                reason_code=reason,
                safe_detail=detail,
                retryable=retryable,
            )
        )

    def _load_module(self) -> NativeMt5Module:
        if self._mt5 is not None:
            return self._mt5
        try:
            module = importlib.import_module("MetaTrader5")
        except (ImportError, OSError) as error:
            raise self._failure(
                Mt5ReasonCode.MT5_PACKAGE_NOT_INSTALLED,
                "Official MT5 package is unavailable.",
            ) from error
        self._mt5 = cast(NativeMt5Module, module)
        return self._mt5

    def _require_connected(self) -> NativeMt5Module:
        if not self._connected or self._mt5 is None:
            raise self._failure(
                Mt5ReasonCode.TERMINAL_DISCONNECTED,
                "MT5 terminal is disconnected.",
                retryable=True,
            )
        return self._mt5

    def _terminal_observation(
        self, module: NativeMt5Module, raw: object, trace_id: str
    ) -> TerminalObservation:
        version = module.version()
        if version is None:
            version_text = "unavailable"
            build = None
        elif isinstance(version, tuple):
            version_text = ".".join(str(item) for item in version[:2])
            build = str(version[2]) if len(version) > 2 else None
        else:
            version_text = str(version)[:80]
            build = None
        try:
            return TerminalObservation(
                observed_at=self._clock(),
                source="mt5",
                adapter_version=ADAPTER_VERSION,
                trace_id=trace_id,
                connected=_required_bool(raw, "connected"),
                platform="windows",
                terminal_version=version_text,
                terminal_build=build,
                trade_allowed=_optional_bool(raw, "trade_allowed"),
            )
        except (TypeError, ValueError) as error:
            raise self._failure(
                Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE,
                "Terminal connection state could not be normalized safely.",
                retryable=True,
            ) from error

    def connect(self, *, trace_id: str) -> TerminalObservation:
        if self._platform != "win32":
            raise self._failure(
                Mt5ReasonCode.UNSUPPORTED_PLATFORM,
                "Native MT5 access is supported only on Windows.",
            )
        path = self._config.terminal_path
        if path is None:
            raise self._failure(
                Mt5ReasonCode.TERMINAL_PATH_NOT_CONFIGURED,
                "An explicit local terminal path is required.",
            )
        if not path.is_absolute() or not path.is_file():
            raise self._failure(
                Mt5ReasonCode.TERMINAL_NOT_FOUND,
                "The configured local terminal executable was not found.",
            )
        module = self._load_module()
        with self._process_lock:
            if self._connected and self._terminal is not None:
                return self._terminal.model_copy(update={"trace_id": trace_id})
            if type(self)._active_owner not in {None, id(self)}:
                raise self._failure(
                    Mt5ReasonCode.NATIVE_ACCESS_CONFLICT,
                    "Another Worker adapter owns process-global MT5 state.",
                    retryable=True,
                )
            initialization_attempted = False
            try:
                initialization_attempted = True
                initialized = module.initialize(str(path))
                if initialized is not True:
                    code = _safe_code(module.last_error())
                    suffix = f" Native code {code}." if code is not None else ""
                    raise self._failure(
                        Mt5ReasonCode.INITIALIZE_FAILED,
                        f"Terminal initialization failed.{suffix}",
                        retryable=True,
                    )
                raw = module.terminal_info()
                if raw is None:
                    raise self._failure(
                        Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE,
                        "Terminal information is unavailable.",
                        retryable=True,
                    )
                terminal = self._terminal_observation(module, raw, trace_id)
                if not terminal.connected:
                    raise self._failure(
                        Mt5ReasonCode.TERMINAL_DISCONNECTED,
                        "Terminal reported a disconnected state.",
                        retryable=True,
                    )
                type(self)._active_owner = id(self)
                self._connected = True
                self._terminal = terminal
                return terminal
            except BaseException:
                if initialization_attempted:
                    try:
                        module.shutdown()
                    except Exception:
                        pass
                self._connected = False
                self._terminal = None
                if type(self)._active_owner == id(self):
                    type(self)._active_owner = None
                raise

    def disconnect(self) -> None:
        with self._process_lock:
            module = self._mt5
            if module is not None and self._connected:
                try:
                    module.shutdown()
                finally:
                    self._connected = False
                    self._terminal = None
                    if type(self)._active_owner == id(self):
                        type(self)._active_owner = None

    def __enter__(self) -> Self:
        self.connect(trace_id="context-connect")
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.disconnect()

    def get_terminal_info(self, *, trace_id: str) -> TerminalObservation:
        with self._process_lock:
            module = self._require_connected()
            raw = module.terminal_info()
            if raw is None:
                raise self._failure(
                    Mt5ReasonCode.TERMINAL_INFO_UNAVAILABLE,
                    "Terminal information is unavailable.",
                    retryable=True,
                )
            terminal = self._terminal_observation(module, raw, trace_id)
            if not terminal.connected:
                raise self._failure(
                    Mt5ReasonCode.TERMINAL_DISCONNECTED,
                    "Terminal reported a disconnected state.",
                    retryable=True,
                )
            self._terminal = terminal
            return terminal

    def get_account_info(self, *, trace_id: str) -> AccountObservation:
        with self._process_lock:
            module = self._require_connected()
            raw = module.account_info()
            if raw is None:
                raise self._failure(
                    Mt5ReasonCode.ACCOUNT_INFO_UNAVAILABLE,
                    "Account information is unavailable.",
                    retryable=True,
                )
            try:
                login = _required(raw, "login")
                server = str(_required(raw, "server"))
                mode_code = int(cast(int | str, _required(raw, "trade_mode")))
                mode = {
                    0: AccountTradeMode.DEMO,
                    1: AccountTradeMode.CONTEST,
                    2: AccountTradeMode.REAL,
                }.get(mode_code, AccountTradeMode.UNKNOWN)
                return AccountObservation(
                    observed_at=self._clock(),
                    source="mt5",
                    adapter_version=ADAPTER_VERSION,
                    trace_id=trace_id,
                    trade_mode=mode,
                    masked_login=mask_login(cast(int | str, login)),
                    masked_server=mask_server(server),
                    account_fingerprint=account_fingerprint(
                        cast(int | str, login), server
                    ),
                    server_fingerprint=server_fingerprint(server),
                    currency=(
                        str(_field(raw, "currency"))
                        if _field(raw, "currency")
                        else None
                    ),
                    leverage=(
                        int(cast(int | str, _field(raw, "leverage")))
                        if _field(raw, "leverage")
                        else None
                    ),
                )
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.ACCOUNT_INFO_UNAVAILABLE,
                    "Account identity could not be normalized safely.",
                ) from error

    def list_symbol_candidates(self, *, trace_id: str) -> list[BrokerSymbolCandidate]:
        with self._process_lock:
            module = self._require_connected()
            raw_symbols = module.symbols_get()
            if raw_symbols is None:
                raise self._failure(
                    Mt5ReasonCode.SYMBOL_NOT_FOUND,
                    "Symbol catalog is unavailable.",
                    retryable=True,
                )
            candidates = []
            for raw in cast(Iterable[object], raw_symbols):
                name = str(_field(raw, "name", "")).strip()
                description = sanitize_comment(_field(raw, "description", ""))
                base = str(_field(raw, "currency_base", "") or "").strip()
                profit = str(_field(raw, "currency_profit", "") or "").strip()
                if not is_canonical_xauusd("XAUUSD", base, profit):
                    continue
                try:
                    candidates.append(
                        BrokerSymbolCandidate(
                            observed_at=self._clock(),
                            source="mt5",
                            adapter_version=ADAPTER_VERSION,
                            trace_id=trace_id,
                            broker_symbol=name,
                            symbol_path=sanitize_comment(_field(raw, "path", "")),
                            description=description,
                            base_currency=cast(Literal["XAU"], base),
                            profit_currency=cast(Literal["USD"], profit),
                            exact_name=name.upper() == "XAUUSD",
                            visible=_required_bool(raw, "visible"),
                        )
                    )
                except (TypeError, ValueError) as error:
                    raise self._failure(
                        Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE,
                        "A qualifying symbol candidate could not be normalized safely.",
                    ) from error
            return candidates

    def get_symbol_specification(
        self, broker_symbol: str, *, trace_id: str
    ) -> BrokerSymbolObservation:
        with self._process_lock:
            module = self._require_connected()
            raw = module.symbol_info(broker_symbol)
            if raw is None:
                raise self._failure(
                    Mt5ReasonCode.SYMBOL_NOT_FOUND,
                    "Configured broker symbol was not found.",
                )
            try:
                visible = _required_bool(raw, "visible")
                trade_mode_code = int(cast(int | str, _required(raw, "trade_mode")))
                trade_mode = {
                    0: SymbolTradeMode.DISABLED,
                    1: SymbolTradeMode.LONG_ONLY,
                    2: SymbolTradeMode.SHORT_ONLY,
                    3: SymbolTradeMode.CLOSE_ONLY,
                    4: SymbolTradeMode.FULL,
                }.get(trade_mode_code, SymbolTradeMode.UNKNOWN)
                base_currency = str(_required(raw, "currency_base")).strip()
                profit_currency = str(_required(raw, "currency_profit")).strip()
                if not is_canonical_xauusd("XAUUSD", base_currency, profit_currency):
                    raise self._failure(
                        Mt5ReasonCode.SYMBOL_CANONICAL_MISMATCH,
                        "Configured broker symbol is not canonical XAU/USD.",
                    )
                material: dict[str, object] = {
                    "canonical_symbol": "XAUUSD",
                    "broker_symbol": broker_symbol,
                    "symbol_path": sanitize_comment(_required(raw, "path")),
                    "description": sanitize_comment(_required(raw, "description")),
                    "base_currency": base_currency,
                    "profit_currency": profit_currency,
                    "margin_currency": str(_required(raw, "currency_margin")).strip(),
                    "digits": int(cast(int | str, _required(raw, "digits"))),
                    "point": decimal_from_native(
                        _required(raw, "point"), positive=True
                    ),
                    "tick_size": decimal_from_native(
                        _required(raw, "trade_tick_size"), positive=True
                    ),
                    "tick_value": decimal_from_native(
                        _required(raw, "trade_tick_value")
                    ),
                    "tick_value_profit": decimal_from_native(
                        _required(raw, "trade_tick_value_profit")
                    ),
                    "tick_value_loss": decimal_from_native(
                        _required(raw, "trade_tick_value_loss")
                    ),
                    "contract_size": decimal_from_native(
                        _required(raw, "trade_contract_size"), positive=True
                    ),
                    "minimum_volume": decimal_from_native(
                        _required(raw, "volume_min"), positive=True
                    ),
                    "maximum_volume": decimal_from_native(
                        _required(raw, "volume_max"), positive=True
                    ),
                    "volume_step": decimal_from_native(
                        _required(raw, "volume_step"), positive=True
                    ),
                    "stops_level": int(
                        cast(int | str, _required(raw, "trade_stops_level"))
                    ),
                    "freeze_level": int(
                        cast(int | str, _required(raw, "trade_freeze_level"))
                    ),
                    "trade_calculation_mode": _stable_code(
                        "calc", _required(raw, "trade_calc_mode")
                    ),
                    "trade_mode": trade_mode,
                    "filling_mode": _stable_code(
                        "fill", _required(raw, "filling_mode")
                    ),
                    "expiration_mode": _stable_code(
                        "expiration", _required(raw, "expiration_mode")
                    ),
                    "order_mode": _stable_code("order", _required(raw, "order_mode")),
                }
                fingerprint_material = {
                    key: str(value) if hasattr(value, "as_tuple") else value
                    for key, value in material.items()
                }
                usability = (
                    SymbolUsabilityState.USABLE
                    if visible
                    else SymbolUsabilityState.NOT_VISIBLE
                )
                return BrokerSymbolObservation.model_validate(
                    {
                        "observed_at": self._clock(),
                        "source": "mt5",
                        "adapter_version": ADAPTER_VERSION,
                        "trace_id": trace_id,
                        **material,
                        "specification_fingerprint": specification_fingerprint(
                            fingerprint_material
                        ),
                        "usability_state": usability,
                        "unusable_reason": (
                            None if visible else Mt5ReasonCode.SYMBOL_NOT_VISIBLE
                        ),
                        "raw_diagnostic_codes": {
                            "trade_calc_mode": int(
                                cast(int | str, _required(raw, "trade_calc_mode"))
                            ),
                            "trade_mode": trade_mode_code,
                        },
                    }
                )
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE,
                    "Broker symbol specification is incomplete or invalid.",
                ) from error

    def get_latest_tick(
        self, broker_symbol: str, *, trace_id: str
    ) -> LatestTickObservation:
        with self._process_lock:
            module = self._require_connected()
            raw = module.symbol_info_tick(broker_symbol)
            symbol = module.symbol_info(broker_symbol)
            if raw is None:
                raise self._failure(
                    Mt5ReasonCode.TICK_UNAVAILABLE,
                    "Latest tick is unavailable.",
                    retryable=True,
                )
            try:
                bid = decimal_from_native(_required(raw, "bid"), positive=True)
                ask = decimal_from_native(_required(raw, "ask"), positive=True)
                if ask < bid:
                    raise ValueError("ask below bid")
                point = decimal_from_native(_required(symbol, "point"), positive=True)
                time_msc = _field(raw, "time_msc")
                tick_at = (
                    utc_from_epoch_milliseconds(int(cast(int | str, time_msc)))
                    if time_msc
                    else utc_from_epoch(cast(int | float, _required(raw, "time")))
                )
                now = self._clock()
                signed_age = (now - tick_at).total_seconds()
                if signed_age < -self._config.max_clock_drift_seconds:
                    freshness = TickFreshness.FUTURE_INVALID
                    age = decimal_from_native(abs(signed_age))
                elif signed_age > self._config.max_tick_age_seconds:
                    freshness = TickFreshness.STALE
                    age = decimal_from_native(signed_age)
                elif signed_age > self._config.max_tick_age_seconds / 2:
                    freshness = TickFreshness.DELAYED
                    age = decimal_from_native(signed_age)
                else:
                    freshness = TickFreshness.LIVE
                    age = decimal_from_native(max(signed_age, 0))
                spread = ask - bid
                return LatestTickObservation(
                    observed_at=now,
                    source="mt5",
                    adapter_version=ADAPTER_VERSION,
                    trace_id=trace_id,
                    symbol=broker_symbol,
                    bid=bid,
                    ask=ask,
                    spread_price=spread,
                    spread_points=spread / point,
                    tick_at=tick_at,
                    age_seconds=age,
                    freshness=freshness,
                )
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.TICK_INVALID,
                    "Latest tick could not be normalized safely.",
                ) from error

    def _timeframe_code(self, module: NativeMt5Module, timeframe: Timeframe) -> int:
        try:
            return {
                Timeframe.M1: module.TIMEFRAME_M1,
                Timeframe.M5: module.TIMEFRAME_M5,
                Timeframe.M15: module.TIMEFRAME_M15,
                Timeframe.H1: module.TIMEFRAME_H1,
            }[timeframe]
        except KeyError as error:
            raise self._failure(
                Mt5ReasonCode.CANDLE_DATA_INVALID,
                "Requested candle timeframe is not supported.",
            ) from error

    def get_candles(
        self,
        broker_symbol: str,
        timeframe: Timeframe,
        request: CandleRequest,
        *,
        trace_id: str,
    ) -> CandleSeries:
        if request.count > self._config.candle_limit:
            raise self._failure(
                Mt5ReasonCode.CANDLE_DATA_INVALID,
                "Candle count exceeds configured limit.",
            )
        if request.range_end and request.range_end > self._clock() + timedelta(
            seconds=self._config.max_clock_drift_seconds
        ):
            raise self._failure(
                Mt5ReasonCode.CANDLE_DATA_INVALID,
                "Candle range extends beyond the allowed clock drift.",
            )
        with self._process_lock:
            module = self._require_connected()
            code = self._timeframe_code(module, timeframe)
            if request.range_start and request.range_end:
                raw_rates = module.copy_rates_range(
                    broker_symbol, code, request.range_start, request.range_end
                )
            else:
                raw_rates = module.copy_rates_from_pos(
                    broker_symbol, code, request.start_position, request.count
                )
            if raw_rates is None:
                raise self._failure(
                    Mt5ReasonCode.CANDLE_DATA_INVALID,
                    "Candle query failed.",
                    retryable=True,
                )
            rows = list(cast(Iterable[object], raw_rates))
            if len(rows) > self._config.candle_limit:
                raise self._failure(
                    Mt5ReasonCode.CANDLE_DATA_INVALID,
                    "Candle query returned more rows than the configured limit.",
                )
            try:
                observed_at = self._clock()
                normalized = tuple(
                    self._candle_observation(
                        row,
                        broker_symbol=broker_symbol,
                        timeframe=timeframe,
                        trace_id=trace_id,
                        observed_at=observed_at,
                    )
                    for row in rows
                )
                CandleSeries(candles=normalized)
                candles = (
                    normalized
                    if request.include_current
                    else tuple(candle for candle in normalized if candle.is_complete)
                )
                return CandleSeries(
                    candles=candles,
                    gaps=candle_gaps(candles, timeframe),
                )
            except (OSError, OverflowError, TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.CANDLE_DATA_INVALID,
                    "Candle data is inconsistent.",
                ) from error

    def _candle_observation(
        self,
        row: object,
        *,
        broker_symbol: str,
        timeframe: Timeframe,
        trace_id: str,
        observed_at: datetime,
    ) -> CandleObservation:
        open_at = utc_from_epoch(cast(int | float, _required(row, "time")))
        return CandleObservation(
            observed_at=observed_at,
            source="mt5",
            adapter_version=ADAPTER_VERSION,
            trace_id=trace_id,
            symbol=broker_symbol,
            timeframe=timeframe,
            open_at=open_at,
            open=decimal_from_native(_required(row, "open"), positive=True),
            high=decimal_from_native(_required(row, "high"), positive=True),
            low=decimal_from_native(_required(row, "low"), positive=True),
            close=decimal_from_native(_required(row, "close"), positive=True),
            tick_volume=decimal_from_native(_required(row, "tick_volume")),
            spread=decimal_from_native(_required(row, "spread")),
            real_volume=decimal_from_native(_required(row, "real_volume")),
            is_complete=candle_is_complete(open_at, timeframe, observed_at),
        )

    def get_open_positions(self, *, trace_id: str) -> list[OpenPositionObservation]:
        with self._process_lock:
            module = self._require_connected()
            rows = module.positions_get()
            if rows is None:
                raise self._failure(
                    Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                    "Open Position query failed.",
                    retryable=True,
                )
            try:
                return [
                    OpenPositionObservation(
                        observed_at=self._clock(),
                        source="mt5",
                        adapter_version=ADAPTER_VERSION,
                        trace_id=trace_id,
                        ticket=_ticket(_required(row, "ticket")),
                        symbol=str(_required(row, "symbol")),
                        direction={
                            0: PositionDirection.BUY,
                            1: PositionDirection.SELL,
                        }.get(
                            int(cast(int | str, _required(row, "type"))),
                            PositionDirection.UNKNOWN,
                        ),
                        volume=decimal_from_native(_required(row, "volume")),
                        entry_price=decimal_from_native(
                            _required(row, "price_open"), positive=True
                        ),
                        current_price=decimal_from_native(
                            _required(row, "price_current"), positive=True
                        ),
                        stop_loss=decimal_from_native(_required(row, "sl")),
                        take_profit=decimal_from_native(_required(row, "tp")),
                        unrealized_profit=signed_decimal_from_native(
                            _required(row, "profit")
                        ),
                        swap=signed_decimal_from_native(_required(row, "swap")),
                        magic_number=(
                            str(_field(row, "magic")) if _field(row, "magic") else None
                        ),
                        opened_at=utc_from_epoch(
                            cast(int | float, _required(row, "time"))
                        ),
                    )
                    for row in cast(Iterable[object], rows)
                ]
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                    "Open Position data is invalid.",
                ) from error

    def get_active_orders(self, *, trace_id: str) -> list[ActiveOrderObservation]:
        with self._process_lock:
            module = self._require_connected()
            rows = module.orders_get()
            if rows is None:
                raise self._failure(
                    Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                    "Active Order query failed.",
                    retryable=True,
                )
            try:
                return [
                    self._active_order(row, trace_id)
                    for row in cast(Iterable[object], rows)
                ]
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                    "Active Order data is invalid.",
                ) from error

    def _active_order(self, row: object, trace_id: str) -> ActiveOrderObservation:
        expiration = _field(row, "time_expiration")
        return ActiveOrderObservation(
            observed_at=self._clock(),
            source="mt5",
            adapter_version=ADAPTER_VERSION,
            trace_id=trace_id,
            ticket=_ticket(_required(row, "ticket")),
            symbol=str(_required(row, "symbol")),
            order_type=_stable_code("order_type", _required(row, "type")),
            state=_stable_code("order_state", _required(row, "state")),
            volume_initial=decimal_from_native(_required(row, "volume_initial")),
            volume_current=decimal_from_native(_required(row, "volume_current")),
            requested_price=decimal_from_native(_required(row, "price_open")),
            stop_loss=decimal_from_native(_required(row, "sl")),
            take_profit=decimal_from_native(_required(row, "tp")),
            setup_at=utc_from_epoch(cast(int | float, _required(row, "time_setup"))),
            expiration_at=(
                utc_from_epoch(cast(int | float, expiration)) if expiration else None
            ),
        )

    def get_order_history(
        self, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalOrderObservation]:
        with self._process_lock:
            module = self._require_connected()
            rows = module.history_orders_get(request.start_at, request.end_at)
            if rows is None:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Order history query failed.",
                    retryable=True,
                )
            try:
                return [
                    HistoricalOrderObservation(
                        observed_at=self._clock(),
                        source="mt5",
                        adapter_version=ADAPTER_VERSION,
                        trace_id=trace_id,
                        ticket=_ticket(_required(row, "ticket")),
                        position_ticket=(
                            _ticket(_field(row, "position_id"))
                            if _field(row, "position_id")
                            else None
                        ),
                        symbol=str(_required(row, "symbol")),
                        order_type=_stable_code("order_type", _required(row, "type")),
                        state=_stable_code("order_state", _required(row, "state")),
                        volume_initial=decimal_from_native(
                            _required(row, "volume_initial")
                        ),
                        volume_current=decimal_from_native(
                            _required(row, "volume_current")
                        ),
                        requested_price=decimal_from_native(
                            _required(row, "price_open")
                        ),
                        stop_loss=decimal_from_native(_required(row, "sl")),
                        take_profit=decimal_from_native(_required(row, "tp")),
                        setup_at=utc_from_epoch(
                            cast(int | float, _required(row, "time_setup"))
                        ),
                        completed_at=(
                            utc_from_epoch(cast(int | float, _field(row, "time_done")))
                            if _field(row, "time_done")
                            else None
                        ),
                        safe_comment=sanitize_comment(_field(row, "comment", "")),
                    )
                    for row in cast(Iterable[object], rows)
                ]
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Order history data is invalid.",
                ) from error

    def get_deal_history(
        self, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalDealObservation]:
        with self._process_lock:
            module = self._require_connected()
            rows = module.history_deals_get(request.start_at, request.end_at)
            if rows is None:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Deal history query failed.",
                    retryable=True,
                )
            try:
                return [
                    HistoricalDealObservation(
                        observed_at=self._clock(),
                        source="mt5",
                        adapter_version=ADAPTER_VERSION,
                        trace_id=trace_id,
                        ticket=_ticket(_required(row, "ticket")),
                        order_ticket=_ticket(_required(row, "order")),
                        position_ticket=_ticket(_required(row, "position_id")),
                        symbol=str(_required(row, "symbol")),
                        direction={
                            0: PositionDirection.BUY,
                            1: PositionDirection.SELL,
                        }.get(
                            int(cast(int | str, _required(row, "type"))),
                            PositionDirection.UNKNOWN,
                        ),
                        volume=decimal_from_native(_required(row, "volume")),
                        price=decimal_from_native(
                            _required(row, "price"), positive=True
                        ),
                        profit=signed_decimal_from_native(_required(row, "profit")),
                        commission=signed_decimal_from_native(
                            _required(row, "commission")
                        ),
                        swap=signed_decimal_from_native(_required(row, "swap")),
                        occurred_at=utc_from_epoch(
                            cast(int | float, _required(row, "time"))
                        ),
                        safe_comment=sanitize_comment(_field(row, "comment", "")),
                    )
                    for row in cast(Iterable[object], rows)
                ]
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Deal history data is invalid.",
                ) from error
