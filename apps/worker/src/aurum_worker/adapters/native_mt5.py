"""Windows-only, lazy, serialized adapter for the official MT5 Python package."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from numbers import Integral
from threading import RLock
from time import monotonic
from types import TracebackType
from typing import Literal, Protocol, Self, cast

from aurum_worker.adapters.protocols import Mt5ReadPort
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountTradeMode,
    AccountVerificationState,
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
    TickTimeDiagnostic,
    Timeframe,
)
from aurum_worker.mt5_market_provider import provider_failure_detail
from aurum_worker.mt5_market_time import (
    PEPPERSTONE_POLICY,
    UTC_POLICY,
    decode_market_epoch,
    encode_market_range,
)
from aurum_worker.mt5_position_link import (
    LINK_FAILURE_CODES,
    MAX_POSITION_REFERENCES,
    PositionLinkProbe,
    PositionLinkUnavailable,
    PositionReference,
    analyze_position_links,
    parse_link_rows,
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
    timeframe_duration_seconds,
    utc_from_epoch,
    utc_from_epoch_milliseconds,
    verify_account,
)
from aurum_worker.mt5_transaction_inventory import (
    InventoryLookback,
    RowInventory,
    TransactionInventory,
    summarize_rows,
)
from aurum_worker.mt5_transaction_probe import (
    CollectionTimeProbe,
    OperatorTimeWindow,
    ProbeRow,
    QueryProbeResult,
    TransactionTimeProbe,
    build_probe_queries,
    parse_probe_rows,
    reference_match_counts,
    select_anchor,
)
from aurum_worker.mt5_transaction_time import (
    PEPPERSTONE_TRANSACTION_POLICY,
    decode_transaction_label,
    encode_transaction_range,
)

ADAPTER_VERSION = "aurum-mt5-read-v1"
POSITION_LINK_STAGE_CODES = frozenset(
    {
        "LINK_STAGE_REFERENCES",
        "LINK_STAGE_COVERAGE",
        "LINK_STAGE_INITIAL_POSITIONS",
        "LINK_STAGE_INITIAL_ORDERS",
        "LINK_STAGE_INITIAL_DEALS",
        "LINK_STAGE_FINAL_ORDERS",
        "LINK_STAGE_FINAL_DEALS",
        "LINK_STAGE_FINAL_POSITIONS",
        "LINK_STAGE_SNAPSHOTS",
        "LINK_STAGE_EVENT_COVERAGE",
        "LINK_STAGE_IDENTITY",
    }
)


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

    def history_orders_get(
        self, start: datetime | int, end: datetime | int
    ) -> object: ...

    def history_deals_get(
        self, start: datetime | int, end: datetime | int
    ) -> object: ...


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


def _native_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("native integer field is invalid")
    return int(value)


def _tick_time_pair(raw: object) -> tuple[int, int | None]:
    seconds = _native_integer(_required(raw, "time"))
    raw_milliseconds = _field(raw, "time_msc")
    milliseconds = (
        None if raw_milliseconds is None else _native_integer(raw_milliseconds)
    )
    if seconds <= 0 or (
        milliseconds is not None
        and (
            milliseconds < 0 or (milliseconds != 0 and milliseconds // 1_000 != seconds)
        )
    ):
        raise ValueError("native tick timestamp pair is inconsistent")
    return seconds, milliseconds


def _transaction_epoch(milliseconds: int) -> datetime:
    """Preserve integer milliseconds without an intermediate floating epoch."""
    if milliseconds <= 0:
        raise ValueError("native transaction timestamp is invalid")
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=milliseconds)
    except OverflowError as error:
        raise ValueError("native transaction timestamp is invalid") from error


def _transaction_time_pair(raw: object, field: str) -> datetime:
    seconds = _native_integer(_required(raw, field))
    milliseconds = _native_integer(_required(raw, f"{field}_msc"))
    if seconds <= 0 or milliseconds <= 0 or milliseconds // 1_000 != seconds:
        raise ValueError("native transaction timestamp pair is inconsistent")
    return _transaction_epoch(milliseconds)


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
                mode_code = _native_integer(_required(raw, "trade_mode"))
                mode = {
                    0: AccountTradeMode.DEMO,
                    1: AccountTradeMode.CONTEST,
                    2: AccountTradeMode.REAL,
                }.get(mode_code, AccountTradeMode.UNKNOWN)
                if (
                    self._config.market_time_policy != UTC_POLICY
                    and mode is AccountTradeMode.DEMO
                ):
                    # Public provider guard is additional to manual account/spec
                    # binding, never a substitute for it or an automatic selector.
                    provider_detail = provider_failure_detail(_field(raw, "company"))
                    if provider_detail is not None:
                        raise self._failure(
                            Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH,
                            provider_detail,
                        )
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

    def get_tick_time_diagnostic(
        self, broker_symbol: str, *, trace_id: str
    ) -> TickTimeDiagnostic:
        """Inspect one native tick's time fields without changing runtime policy.

        This separate local diagnostic capability is not part of the polling or
        persistence port. It requires an already confirmed bound Demo symbol.
        """
        with self._process_lock:
            module = self._require_connected()
            if self._config.broker_symbol != broker_symbol:
                raise self._failure(
                    Mt5ReasonCode.SYMBOL_NOT_CONFIGURED,
                    "Diagnostic requires the explicitly configured broker symbol.",
                )
            account = self.get_account_info(trace_id=trace_id)
            verification = verify_account(
                account, self._config.expected_account_fingerprint
            )
            if verification.state is not AccountVerificationState.VERIFIED_DEMO_BOUND:
                raise self._failure(
                    verification.reason_code,
                    "Diagnostic Demo binding was not satisfied.",
                )
            confirmed = self._config.smoke_confirmed_specification_fingerprint
            if confirmed is None:
                raise self._failure(
                    Mt5ReasonCode.SYMBOL_SPEC_CONFIRMATION_REQUIRED,
                    "Diagnostic requires a separately confirmed specification.",
                )
            specification = self.get_symbol_specification(
                broker_symbol, trace_id=trace_id
            )
            if specification.usability_state is not SymbolUsabilityState.USABLE:
                raise self._failure(
                    specification.unusable_reason
                    or Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE,
                    "Diagnostic symbol is not usable.",
                )
            if specification.specification_fingerprint != confirmed:
                raise self._failure(
                    Mt5ReasonCode.SYMBOL_SPEC_CHANGED,
                    "Diagnostic specification differs from prior confirmation.",
                )
            raw = module.symbol_info_tick(broker_symbol)
            if raw is None:
                raise self._failure(
                    Mt5ReasonCode.TICK_UNAVAILABLE, "Diagnostic tick is unavailable."
                )
            try:
                evidence = TickTimeDiagnostic(
                    observed_at=self._clock(),
                    native_time=cast(int, _required(raw, "time")),
                    native_time_msc=cast(int | None, _field(raw, "time_msc")),
                )
                # Validate representability, but do not rewrite either native value.
                utc_from_epoch(evidence.native_time)
                if evidence.native_time_msc:
                    utc_from_epoch_milliseconds(evidence.native_time_msc)
                return evidence
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.TICK_INVALID,
                    "Diagnostic timestamp fields are invalid or unavailable.",
                ) from error

    def get_latest_tick(
        self, broker_symbol: str, *, trace_id: str
    ) -> LatestTickObservation:
        with self._process_lock:
            module = self._require_connected()
            self._check_market_time_binding(
                broker_symbol, trace_id, Mt5ReasonCode.TICK_INVALID
            )
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
                seconds, time_msc = _tick_time_pair(raw)
                # Revalidate after all market reads, before the final freshness
                # clock. Slow binding checks must not return a cached LIVE state.
                self._check_market_time_binding(
                    broker_symbol, trace_id, Mt5ReasonCode.TICK_INVALID
                )
                now = self._clock()
                if self._config.market_time_policy == UTC_POLICY:
                    tick_at = (
                        utc_from_epoch_milliseconds(time_msc)
                        if time_msc
                        else utc_from_epoch(seconds)
                    )
                else:
                    tick_at = decode_market_epoch(
                        time_msc if time_msc else seconds,
                        policy=self._config.market_time_policy,
                        observed_at=now,
                        milliseconds=bool(time_msc),
                    )
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
                observation = LatestTickObservation(
                    observed_at=now,
                    source="mt5",
                    adapter_version=self._market_adapter_version(),
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
                return observation
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.TICK_INVALID,
                    "Latest tick could not be normalized safely.",
                ) from error

    def _market_adapter_version(self) -> str:
        if self._config.market_time_policy == UTC_POLICY:
            return ADAPTER_VERSION
        return f"{ADAPTER_VERSION}:{self._config.market_time_policy}"

    def _check_market_time_binding(
        self, symbol: str, trace_id: str, reason: Mt5ReasonCode
    ) -> None:
        if self._config.market_time_policy == UTC_POLICY:
            return
        if (
            self._config.max_tick_age_seconds != 10
            or self._config.max_clock_drift_seconds != 30
        ):
            raise self._failure(reason, "Market time safety limits must remain fixed.")
        try:
            # Also reject expired capture coverage before issuing a market read.
            now = self._clock()
            encode_market_range(
                now, now, policy=self._config.market_time_policy, observed_at=now
            )
        except ValueError as error:
            raise self._failure(
                reason, "Market time policy coverage is unavailable."
            ) from error
        if symbol != self._config.broker_symbol:
            raise self._failure(
                Mt5ReasonCode.SYMBOL_NOT_CONFIGURED,
                "Time policy requires the configured symbol.",
            )
        self.get_terminal_info(trace_id=trace_id)
        account = self.get_account_info(trace_id=trace_id)
        verified = verify_account(account, self._config.expected_account_fingerprint)
        if verified.state is not AccountVerificationState.VERIFIED_DEMO_BOUND:
            raise self._failure(
                verified.reason_code, "Time policy Demo binding failed."
            )
        confirmed = self._config.smoke_confirmed_specification_fingerprint
        if confirmed is None:
            raise self._failure(
                Mt5ReasonCode.SYMBOL_SPEC_CONFIRMATION_REQUIRED,
                "Time policy needs a separately confirmed specification.",
            )
        specification = self.get_symbol_specification(symbol, trace_id=trace_id)
        if specification.usability_state is not SymbolUsabilityState.USABLE:
            raise self._failure(
                specification.unusable_reason or Mt5ReasonCode.SYMBOL_SPEC_INCOMPLETE,
                "Time policy symbol is unusable.",
            )
        if specification.specification_fingerprint != confirmed:
            raise self._failure(
                Mt5ReasonCode.SYMBOL_SPEC_CHANGED, "Time policy specification changed."
            )

    def _require_transaction_time_contract(self) -> None:
        # Runtime validation also covers configs created through model_copy.
        policy: object = self._config.transaction_time_policy
        if self._config.market_time_policy == UTC_POLICY and policy is None:
            return
        if (
            self._config.market_time_policy == PEPPERSTONE_POLICY
            and type(policy) is str
            and policy == PEPPERSTONE_TRANSACTION_POLICY
        ):
            return
        raise self._failure(
            Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
            "An explicitly supported transaction time policy is required.",
        )

    def _transaction_adapter_version(self) -> str:
        policy = self._config.transaction_time_policy
        return ADAPTER_VERSION if policy is None else f"{ADAPTER_VERSION}:{policy}"

    def _check_transaction_binding(self, trace_id: str, reason: Mt5ReasonCode) -> None:
        self._require_transaction_time_contract()
        self._check_market_time_binding(
            self._config.broker_symbol or "", trace_id, reason
        )

    def _transaction_rows(self, rows: object) -> Iterable[object]:
        if self._config.transaction_time_policy is not None:
            if not isinstance(rows, (tuple, list)) or len(rows) > 1_000:
                raise ValueError("bounded transaction collection is invalid")
            tickets = [_ticket(_required(row, "ticket")) for row in rows]
            if len(set(tickets)) != len(tickets):
                raise ValueError("transaction collection contains duplicate tickets")
        # Keep account-wide observations, including other symbols/exposure.
        return cast(Iterable[object], rows)

    def _decode_transaction_time(
        self, label: datetime, observed_at: datetime
    ) -> datetime:
        policy = self._config.transaction_time_policy
        if policy is None:
            return label
        return decode_transaction_label(label, policy=policy, observed_at=observed_at)

    def _transaction_history_arguments(
        self, request: HistoryRequest
    ) -> tuple[datetime | int, datetime | int]:
        policy = self._config.transaction_time_policy
        if policy is None:
            return request.start_at, request.end_at
        now = self._clock()
        if request.end_at - now > timedelta(
            seconds=self._config.max_clock_drift_seconds
        ):
            raise ValueError("transaction history request exceeds allowed clock drift")
        return encode_transaction_range(
            request.start_at, request.end_at, policy=policy, observed_at=now
        )

    def _in_transaction_history_window(
        self, event_at: datetime | None, request: HistoryRequest
    ) -> bool:
        if self._config.transaction_time_policy is None or event_at is None:
            # Missing completion must reach reconciliation as incomplete evidence.
            return True
        transport_start = request.start_at.astimezone(UTC).replace(microsecond=0)
        transport_end = request.end_at.astimezone(UTC).replace(
            microsecond=0
        ) + timedelta(seconds=1)
        if not transport_start <= event_at < transport_end:
            raise ValueError("transaction history escaped its transport envelope")
        # Integer-second native selection can overfetch only at the two edges.
        # The entire collection is validated before this precise UTC selection.
        return request.start_at <= event_at <= request.end_at

    def inspect_transaction_inventory(
        self, *, trace_id: str, lookback_days: InventoryLookback = 7
    ) -> TransactionInventory:
        """Diagnostic only: no UTC interpretation, runtime reconciliation or writes.

        The history envelope includes both hypotheses for a bounded interval.
        Its shifted upper bound is a transport label, NOT a future UTC event.
        Counts cannot prove completeness, timezone, or query endpoint semantics.
        """
        requested_lookback: object = lookback_days
        if type(requested_lookback) is not int or requested_lookback not in {7, 30}:
            raise self._failure(
                Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                "Inventory lookback must be exactly seven or thirty days.",
            )
        if self._config.market_time_policy != PEPPERSTONE_POLICY:
            raise self._failure(
                Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                "Inventory needs the explicitly selected Demo source policy.",
            )
        with self._process_lock:
            module = self._require_connected()
            symbol = self._config.broker_symbol or ""
            reason = Mt5ReasonCode.RECONCILIATION_INCOMPLETE

            def read(kind: str, operation: Callable[[], object]) -> RowInventory:
                self._check_market_time_binding(symbol, trace_id, reason)
                rows = operation()
                self._check_market_time_binding(symbol, trace_id, reason)
                return summarize_rows(rows, symbol=symbol, kind=kind, field=_field)

            try:
                self._check_market_time_binding(symbol, trace_id, reason)
                now = self._clock()
                start = now - timedelta(days=lookback_days)
                # Validate the whole hypothetical event window against coverage.
                _, end = encode_market_range(
                    start, now, policy=PEPPERSTONE_POLICY, observed_at=now
                )
                positions = read("positions", module.positions_get)
                orders = read("active_orders", module.orders_get)
                order_history = read(
                    "historical_orders", lambda: module.history_orders_get(start, end)
                )
                deals = read(
                    "historical_deals", lambda: module.history_deals_get(start, end)
                )
                return TransactionInventory(
                    lookback_days=lookback_days,
                    positions=positions,
                    active_orders=orders,
                    historical_orders=order_history,
                    historical_deals=deals,
                )
            except Mt5ReadFailure:
                raise
            except Exception as error:
                raise self._failure(
                    reason, "Transaction inventory unavailable."
                ) from error

    def inspect_position_time_links(
        self, *, trace_id: str, references: tuple[PositionReference, ...]
    ) -> PositionLinkProbe:
        """Observe bounded existing links, never normalize or enable transactions.

        Only selected identity, direction and time fields enter the snapshot.
        This is not an atomic broker snapshot or an execution/risk assessment.
        """
        reason = Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        if self._config.market_time_policy != PEPPERSTONE_POLICY:
            raise self._failure(reason, "Link probe requires the explicit Demo source.")
        with self._process_lock:
            module = self._require_connected()
            symbol = self._config.broker_symbol or ""
            reads = 0
            began = monotonic()
            capture = self._clock()
            epoch = datetime(1970, 1, 1, tzinfo=UTC)
            stage = "LINK_STAGE_REFERENCES"

            def budget() -> None:
                elapsed = (self._clock() - capture).total_seconds()
                if not 0 <= elapsed <= 30 or monotonic() - began > 30:
                    raise ValueError("Link probe budget unavailable.")

            def read(operation: Callable[[], object]) -> object:
                nonlocal reads
                budget()
                self._check_market_time_binding(symbol, trace_id, reason)
                budget()
                if reads >= 6:
                    raise ValueError("Link probe read budget exceeded.")
                reads += 1
                result = operation()
                budget()
                self._check_market_time_binding(symbol, trace_id, reason)
                budget()
                return result

            try:
                if type(references) is not tuple or not (
                    1 <= len(references) <= MAX_POSITION_REFERENCES
                ):
                    raise ValueError("Link references unavailable.")
                checked = tuple(
                    PositionReference.model_validate(item.model_dump(warnings="error"))
                    for item in references
                )
                if len({item.ticket for item in checked}) != len(checked):
                    raise ValueError("Link references unavailable.")
                stage = "LINK_STAGE_COVERAGE"
                start = capture - timedelta(days=7)
                _, end = encode_market_range(
                    start, capture, policy=PEPPERSTONE_POLICY, observed_at=capture
                )
                for item in checked:
                    label = item.opening_label.replace(tzinfo=UTC)
                    if not start <= label <= end:
                        raise ValueError("Link reference outside bounded envelope.")
                stage = "LINK_STAGE_INITIAL_POSITIONS"
                positions = parse_link_rows(
                    read(module.positions_get),
                    kind="positions",
                    symbol=symbol,
                    field=_field,
                )
                stage = "LINK_STAGE_INITIAL_ORDERS"
                orders = parse_link_rows(
                    read(lambda: module.history_orders_get(start, end)),
                    kind="orders",
                    symbol=symbol,
                    field=_field,
                )
                stage = "LINK_STAGE_INITIAL_DEALS"
                deals = parse_link_rows(
                    read(lambda: module.history_deals_get(start, end)),
                    kind="deals",
                    symbol=symbol,
                    field=_field,
                )
                # Reuse the exact history window; do not widen for a missing link.
                stage = "LINK_STAGE_FINAL_ORDERS"
                final_orders = parse_link_rows(
                    read(lambda: module.history_orders_get(start, end)),
                    kind="orders",
                    symbol=symbol,
                    field=_field,
                )
                stage = "LINK_STAGE_FINAL_DEALS"
                final_deals = parse_link_rows(
                    read(lambda: module.history_deals_get(start, end)),
                    kind="deals",
                    symbol=symbol,
                    field=_field,
                )
                stage = "LINK_STAGE_FINAL_POSITIONS"
                final_positions = parse_link_rows(
                    read(module.positions_get),
                    kind="positions",
                    symbol=symbol,
                    field=_field,
                )
                stage = "LINK_STAGE_SNAPSHOTS"
                if reads != 6 or (
                    positions != final_positions
                    or orders != final_orders
                    or deals != final_deals
                ):
                    raise ValueError("Link probe snapshots changed.")
                stage = "LINK_STAGE_EVENT_COVERAGE"
                selected_tickets = {item.ticket for item in checked}
                selected_positions = tuple(
                    row for row in positions if row.ticket in selected_tickets
                )
                identifiers = {row.identifier for row in selected_positions}
                times = [
                    value
                    for row in selected_positions
                    for value in (row.time_msc, row.time_update_msc)
                ]
                times.extend(
                    value
                    for order in orders
                    if order.position_id in identifiers
                    for value in (order.time_setup_msc, order.time_done_msc)
                )
                times.extend(
                    deal.time_msc for deal in deals if deal.position_id in identifiers
                )
                for value in times:
                    label = epoch + timedelta(milliseconds=value)
                    if not start <= label <= end:
                        raise ValueError("Link event outside bounded envelope.")
                    for offset in (timedelta(0), timedelta(hours=3)):
                        encode_market_range(
                            label - offset,
                            label - offset,
                            policy=PEPPERSTONE_POLICY,
                            observed_at=capture,
                        )
                stage = "LINK_STAGE_IDENTITY"
                result = analyze_position_links(positions, orders, deals, checked)
                budget()
                return result
            except Mt5ReadFailure:
                raise
            except PositionLinkUnavailable as error:
                detail = error.code if error.code in LINK_FAILURE_CODES else stage
                raise self._failure(reason, detail) from None
            except Exception as error:
                raise self._failure(reason, stage) from error

    def inspect_transaction_time_probe(
        self, *, trace_id: str, reference: OperatorTimeWindow | None = None
    ) -> TransactionTimeProbe:
        """Observe query behavior only; never normalize or enable transactions.

        Fixed at two envelopes plus ten probes per collection and two final
        envelopes. The 30-second budget is checked between blocking SDK calls;
        this API offers no safe cancellation of an individual native call.
        """
        reason = Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        if self._config.market_time_policy != PEPPERSTONE_POLICY:
            raise self._failure(reason, "Probe requires the explicit Demo source.")
        with self._process_lock:
            module = self._require_connected()
            symbol = self._config.broker_symbol or ""
            capture = self._clock()
            began = monotonic()
            queries = 0
            epoch = datetime(1970, 1, 1, tzinfo=UTC)
            kinds: tuple[Literal["orders", "deals"], ...] = ("orders", "deals")

            def budget() -> None:
                elapsed = (self._clock() - capture).total_seconds()
                if not 0 <= elapsed <= 30 or monotonic() - began > 30:
                    raise ValueError("Probe time budget or clock invalid.")

            def read(
                kind: Literal["orders", "deals"],
                start: datetime | int,
                end: datetime | int,
            ) -> tuple[ProbeRow, ...]:
                nonlocal queries
                budget()
                self._check_market_time_binding(symbol, trace_id, reason)
                budget()
                if queries >= 24:
                    raise ValueError("Probe query budget exceeded.")
                queries += 1
                if kind == "orders":
                    rows = module.history_orders_get(start, end)
                else:
                    rows = module.history_deals_get(start, end)
                budget()
                self._check_market_time_binding(symbol, trace_id, reason)
                budget()
                return parse_probe_rows(rows, kind=kind, symbol=symbol, field=_field)

            try:
                start = capture - timedelta(days=7)
                _, end = encode_market_range(
                    start, capture, policy=PEPPERSTONE_POLICY, observed_at=capture
                )
                if reference is not None:
                    reference = OperatorTimeWindow.model_validate(
                        reference.model_dump()
                    )
                    if reference.start_at < start or reference.end_at > capture:
                        raise ValueError(
                            "Reference must be an existing recent interval."
                        )
                initial = {kind: read(kind, start, end) for kind in kinds}
                if any(not rows for rows in initial.values()):
                    raise ValueError("Existing matching history samples unavailable.")
                reports: dict[str, CollectionTimeProbe] = {}
                for kind in kinds:
                    rows = initial[kind]
                    known = {row.ticket: row for row in rows}
                    anchor = select_anchor(rows, kind=kind)
                    plan = build_probe_queries(anchor, kind=kind)
                    if len(plan) != 10:
                        raise ValueError("Probe plan is invalid.")
                    checks: list[QueryProbeResult] = []
                    for query in plan:
                        lower = (
                            epoch + timedelta(seconds=query.start)
                            if isinstance(query.start, int)
                            else query.start
                        )
                        upper = (
                            epoch + timedelta(seconds=query.end)
                            if isinstance(query.end, int)
                            else query.end
                        )
                        if not start <= lower <= upper <= end:
                            raise ValueError(
                                "Probe exceeds the fixed history envelope."
                            )
                        # Both candidate interpretations must stay inside known
                        # seasonal coverage; neither becomes a runtime mapping.
                        for offset in (timedelta(0), timedelta(hours=3)):
                            encode_market_range(
                                lower - offset,
                                upper - offset,
                                policy=PEPPERSTONE_POLICY,
                                observed_at=capture,
                            )
                        selected = read(kind, query.start, query.end)
                        if any(known.get(row.ticket) != row for row in selected):
                            raise ValueError("Probe history changed during inspection.")
                        checks.append(
                            QueryProbeResult(
                                code=query.code,
                                target_present=any(
                                    row.ticket == anchor.ticket for row in selected
                                ),
                                matching_rows=len(selected),
                            )
                        )
                    as_utc, shifted = reference_match_counts(rows, reference)
                    reports[kind] = CollectionTimeProbe(
                        matching_rows=len(rows),
                        selected_event_has_subsecond=bool(
                            anchor.event_milliseconds % 1000
                        ),
                        setup_done_distinguishable=(
                            kind == "orders"
                            and anchor.setup_seconds is not None
                            and anchor.setup_seconds != anchor.event_seconds
                        ),
                        as_utc_reference_matches=as_utc,
                        minus_three_hours_reference_matches=shifted,
                        queries=tuple(checks),
                    )
                for kind in kinds:
                    final = read(kind, start, end)
                    if {row.ticket: row for row in final} != {
                        row.ticket: row for row in initial[kind]
                    }:
                        raise ValueError("Probe history changed during inspection.")
                budget()
                return TransactionTimeProbe(
                    history_query_count=queries,
                    reference_supplied=reference is not None,
                    stable_snapshots=True,
                    orders=reports["orders"],
                    deals=reports["deals"],
                )
            except Mt5ReadFailure:
                raise
            except Exception:
                raise self._failure(
                    reason, "Transaction time probe unavailable or inconsistent."
                ) from None

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
            self._check_market_time_binding(
                broker_symbol, trace_id, Mt5ReasonCode.CANDLE_DATA_INVALID
            )
            code = self._timeframe_code(module, timeframe)
            if request.range_start and request.range_end:
                start, end = request.range_start, request.range_end
                try:
                    if self._config.market_time_policy != UTC_POLICY:
                        start, end = encode_market_range(
                            request.range_start,
                            request.range_end,
                            policy=self._config.market_time_policy,
                            observed_at=self._clock(),
                        )
                except ValueError as error:
                    raise self._failure(
                        Mt5ReasonCode.CANDLE_DATA_INVALID,
                        "Candle request has no supported time mapping.",
                    ) from error
                raw_rates = module.copy_rates_range(broker_symbol, code, start, end)
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
                if (
                    self._config.market_time_policy != UTC_POLICY
                    and (
                        request.range_start is not None
                        and request.range_end is not None
                    )
                    and any(
                        candle.open_at < request.range_start
                        or candle.open_at > request.range_end
                        for candle in normalized
                    )
                ):
                    raise ValueError(
                        "Candle result falls outside the requested interval."
                    )
                candles = (
                    normalized
                    if request.include_current
                    else tuple(candle for candle in normalized if candle.is_complete)
                )
                result = CandleSeries(
                    candles=candles,
                    gaps=candle_gaps(candles, timeframe),
                )
                self._check_market_time_binding(
                    broker_symbol, trace_id, Mt5ReasonCode.CANDLE_DATA_INVALID
                )
                return result
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
        if self._config.market_time_policy == UTC_POLICY:
            open_at = utc_from_epoch(cast(int | float, _required(row, "time")))
        else:
            open_at = decode_market_epoch(
                cast(int | float, _required(row, "time")),
                policy=self._config.market_time_policy,
                observed_at=observed_at,
            )
            encode_market_range(
                open_at,
                open_at + timedelta(seconds=timeframe_duration_seconds(timeframe)),
                policy=self._config.market_time_policy,
                observed_at=observed_at,
            )
        return CandleObservation(
            observed_at=observed_at,
            source="mt5",
            adapter_version=self._market_adapter_version(),
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

    def _transaction_event_at(
        self, row: object, field: str, observed_at: datetime
    ) -> datetime:
        event_at = self._decode_transaction_time(
            _transaction_time_pair(row, field), observed_at
        )
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("transaction observation clock is invalid")
        if event_at - observed_at > timedelta(
            seconds=self._config.max_clock_drift_seconds
        ):
            raise ValueError("transaction event exceeds allowed clock drift")
        return event_at

    def _open_position(self, row: object, trace_id: str) -> OpenPositionObservation:
        observed_at = self._clock()
        return OpenPositionObservation(
            observed_at=observed_at,
            source="mt5",
            adapter_version=self._transaction_adapter_version(),
            trace_id=trace_id,
            ticket=_ticket(_required(row, "ticket")),
            symbol=str(_required(row, "symbol")),
            direction={0: PositionDirection.BUY, 1: PositionDirection.SELL}.get(
                _native_integer(_required(row, "type")), PositionDirection.UNKNOWN
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
            unrealized_profit=signed_decimal_from_native(_required(row, "profit")),
            swap=signed_decimal_from_native(_required(row, "swap")),
            magic_number=str(_field(row, "magic")) if _field(row, "magic") else None,
            opened_at=self._transaction_event_at(row, "time", observed_at),
        )

    def get_open_positions(self, *, trace_id: str) -> list[OpenPositionObservation]:
        self._require_transaction_time_contract()
        with self._process_lock:
            module = self._require_connected()
            self._check_transaction_binding(
                trace_id, Mt5ReasonCode.RECONCILIATION_INCOMPLETE
            )
            rows = module.positions_get()
            self._check_transaction_binding(
                trace_id, Mt5ReasonCode.RECONCILIATION_INCOMPLETE
            )
            if rows is None:
                raise self._failure(
                    Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                    "Open Position query failed.",
                    retryable=True,
                )
            try:
                return [
                    self._open_position(row, trace_id)
                    for row in self._transaction_rows(rows)
                ]
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                    "Open Position data is invalid.",
                ) from error

    def get_active_orders(self, *, trace_id: str) -> list[ActiveOrderObservation]:
        self._require_transaction_time_contract()
        with self._process_lock:
            module = self._require_connected()
            self._check_transaction_binding(
                trace_id, Mt5ReasonCode.RECONCILIATION_INCOMPLETE
            )
            rows = module.orders_get()
            self._check_transaction_binding(
                trace_id, Mt5ReasonCode.RECONCILIATION_INCOMPLETE
            )
            if rows is None:
                raise self._failure(
                    Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                    "Active Order query failed.",
                    retryable=True,
                )
            try:
                return [
                    self._active_order(row, trace_id)
                    for row in self._transaction_rows(rows)
                ]
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                    "Active Order data is invalid.",
                ) from error

    def _active_order(self, row: object, trace_id: str) -> ActiveOrderObservation:
        observed_at = self._clock()
        setup_at = self._transaction_event_at(row, "time_setup", observed_at)
        expiration = _native_integer(_required(row, "time_expiration"))
        expiration_mode = _native_integer(_required(row, "type_time"))
        if expiration_mode == 0 and expiration == 0:
            # Absent explicit expiry is not a guarantee of infinite broker lifetime.
            expiration_at = None
        elif expiration_mode == 2 and expiration > 0:
            expiration_at = self._decode_transaction_time(
                _transaction_epoch(expiration * 1_000), observed_at
            )
            if expiration_at < setup_at:
                raise ValueError("active Order expiration precedes setup")
        else:
            # DAY / SPECIFIED_DAY need session semantics this observation cannot carry.
            raise ValueError("active Order expiration mode or sentinel is unsupported")
        return ActiveOrderObservation(
            observed_at=observed_at,
            source="mt5",
            adapter_version=self._transaction_adapter_version(),
            trace_id=trace_id,
            ticket=_ticket(_required(row, "ticket")),
            symbol=str(_required(row, "symbol")),
            order_type=_stable_code(
                "order_type", _native_integer(_required(row, "type"))
            ),
            state=_stable_code("order_state", _native_integer(_required(row, "state"))),
            volume_initial=decimal_from_native(_required(row, "volume_initial")),
            volume_current=decimal_from_native(_required(row, "volume_current")),
            requested_price=decimal_from_native(_required(row, "price_open")),
            stop_loss=decimal_from_native(_required(row, "sl")),
            take_profit=decimal_from_native(_required(row, "tp")),
            setup_at=setup_at,
            expiration_at=expiration_at,
        )

    def _historical_order(
        self, row: object, trace_id: str
    ) -> HistoricalOrderObservation:
        observed_at = self._clock()
        setup_at = self._transaction_event_at(row, "time_setup", observed_at)
        done_seconds = _native_integer(_required(row, "time_done"))
        done_milliseconds = _native_integer(_required(row, "time_done_msc"))
        completed_at = (
            None
            if done_seconds == 0 and done_milliseconds == 0
            else self._transaction_event_at(row, "time_done", observed_at)
        )
        if completed_at is not None and completed_at < setup_at:
            raise ValueError("historical Order completion precedes setup")
        return HistoricalOrderObservation(
            observed_at=observed_at,
            source="mt5",
            adapter_version=self._transaction_adapter_version(),
            trace_id=trace_id,
            ticket=_ticket(_required(row, "ticket")),
            position_ticket=(
                _ticket(_field(row, "position_id"))
                if _field(row, "position_id")
                else None
            ),
            symbol=str(_required(row, "symbol")),
            order_type=_stable_code(
                "order_type", _native_integer(_required(row, "type"))
            ),
            state=_stable_code("order_state", _native_integer(_required(row, "state"))),
            volume_initial=decimal_from_native(_required(row, "volume_initial")),
            volume_current=decimal_from_native(_required(row, "volume_current")),
            requested_price=decimal_from_native(_required(row, "price_open")),
            stop_loss=decimal_from_native(_required(row, "sl")),
            take_profit=decimal_from_native(_required(row, "tp")),
            setup_at=setup_at,
            completed_at=completed_at,
            safe_comment=sanitize_comment(_field(row, "comment", "")),
        )

    def get_order_history(
        self, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalOrderObservation]:
        self._require_transaction_time_contract()
        with self._process_lock:
            module = self._require_connected()
            try:
                start, end = self._transaction_history_arguments(request)
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Order history request is unsupported.",
                ) from error
            self._check_transaction_binding(
                trace_id, Mt5ReasonCode.HISTORY_QUERY_FAILED
            )
            rows = module.history_orders_get(start, end)
            self._check_transaction_binding(
                trace_id, Mt5ReasonCode.HISTORY_QUERY_FAILED
            )
            if rows is None:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Order history query failed.",
                    retryable=True,
                )
            try:
                observations = [
                    self._historical_order(row, trace_id)
                    for row in self._transaction_rows(rows)
                ]
                return [
                    row
                    for row in observations
                    if self._in_transaction_history_window(row.completed_at, request)
                ]
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Order history data is invalid.",
                ) from error

    def _historical_deal(self, row: object, trace_id: str) -> HistoricalDealObservation:
        observed_at = self._clock()
        return HistoricalDealObservation(
            observed_at=observed_at,
            source="mt5",
            adapter_version=self._transaction_adapter_version(),
            trace_id=trace_id,
            ticket=_ticket(_required(row, "ticket")),
            order_ticket=_ticket(_required(row, "order")),
            position_ticket=_ticket(_required(row, "position_id")),
            symbol=str(_required(row, "symbol")),
            direction={0: PositionDirection.BUY, 1: PositionDirection.SELL}.get(
                _native_integer(_required(row, "type")), PositionDirection.UNKNOWN
            ),
            volume=decimal_from_native(_required(row, "volume")),
            price=decimal_from_native(_required(row, "price"), positive=True),
            profit=signed_decimal_from_native(_required(row, "profit")),
            commission=signed_decimal_from_native(_required(row, "commission")),
            swap=signed_decimal_from_native(_required(row, "swap")),
            occurred_at=self._transaction_event_at(row, "time", observed_at),
            safe_comment=sanitize_comment(_field(row, "comment", "")),
        )

    def get_deal_history(
        self, request: HistoryRequest, *, trace_id: str
    ) -> list[HistoricalDealObservation]:
        self._require_transaction_time_contract()
        with self._process_lock:
            module = self._require_connected()
            try:
                start, end = self._transaction_history_arguments(request)
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Deal history request is unsupported.",
                ) from error
            self._check_transaction_binding(
                trace_id, Mt5ReasonCode.HISTORY_QUERY_FAILED
            )
            rows = module.history_deals_get(start, end)
            self._check_transaction_binding(
                trace_id, Mt5ReasonCode.HISTORY_QUERY_FAILED
            )
            if rows is None:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Deal history query failed.",
                    retryable=True,
                )
            try:
                observations = [
                    self._historical_deal(row, trace_id)
                    for row in self._transaction_rows(rows)
                ]
                return [
                    row
                    for row in observations
                    if self._in_transaction_history_window(row.occurred_at, request)
                ]
            except (TypeError, ValueError) as error:
                raise self._failure(
                    Mt5ReasonCode.HISTORY_QUERY_FAILED,
                    "Deal history data is invalid.",
                ) from error
