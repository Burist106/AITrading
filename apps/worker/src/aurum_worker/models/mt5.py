"""Immutable read-only MT5 domain models and local configuration."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

DecimalValue = Annotated[Decimal, Field(allow_inf_nan=False)]
PositiveDecimal = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
SafeIdentifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
TicketIdentifier = Annotated[str, StringConstraints(pattern=r"^[0-9]+$", max_length=32)]


class Mt5Model(BaseModel):
    """Strict immutable model used inside the Worker read-only boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ObservationModel(Mt5Model):
    observed_at: AwareDatetime
    source: Literal["mt5", "fake_mt5"]
    adapter_version: SafeIdentifier
    trace_id: SafeIdentifier
    schema_version: Literal["1"] = "1"


class AccountTradeMode(StrEnum):
    DEMO = "demo"
    CONTEST = "contest"
    REAL = "real"
    UNKNOWN = "unknown"


class AccountVerificationState(StrEnum):
    VERIFIED_DEMO_BOUND = "verified_demo_bound"
    VERIFIED_DEMO_UNBOUND = "verified_demo_unbound"
    ACCOUNT_INFO_UNAVAILABLE = "account_info_unavailable"
    TRADE_MODE_UNKNOWN = "trade_mode_unknown"
    CONTEST_ACCOUNT_BLOCKED = "contest_account_blocked"
    REAL_ACCOUNT_BLOCKED = "real_account_blocked"
    ACCOUNT_BINDING_MISMATCH = "account_binding_mismatch"


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class Mt5ReasonCode(StrEnum):
    HEALTHY = "HEALTHY"
    MT5_PACKAGE_NOT_INSTALLED = "MT5_PACKAGE_NOT_INSTALLED"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    TERMINAL_PATH_NOT_CONFIGURED = "TERMINAL_PATH_NOT_CONFIGURED"
    TERMINAL_NOT_FOUND = "TERMINAL_NOT_FOUND"
    INITIALIZE_FAILED = "INITIALIZE_FAILED"
    TERMINAL_INFO_UNAVAILABLE = "TERMINAL_INFO_UNAVAILABLE"
    TERMINAL_DISCONNECTED = "TERMINAL_DISCONNECTED"
    ACCOUNT_INFO_UNAVAILABLE = "ACCOUNT_INFO_UNAVAILABLE"
    TRADE_MODE_UNKNOWN = "TRADE_MODE_UNKNOWN"
    CONTEST_ACCOUNT_BLOCKED = "CONTEST_ACCOUNT_BLOCKED"
    REAL_ACCOUNT_BLOCKED = "REAL_ACCOUNT_BLOCKED"
    ACCOUNT_BINDING_MISMATCH = "ACCOUNT_BINDING_MISMATCH"
    DEMO_ACCOUNT_UNBOUND = "DEMO_ACCOUNT_UNBOUND"
    SYMBOL_NOT_CONFIGURED = "SYMBOL_NOT_CONFIGURED"
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    SYMBOL_AMBIGUOUS = "SYMBOL_AMBIGUOUS"
    SYMBOL_NOT_VISIBLE = "SYMBOL_NOT_VISIBLE"
    SYMBOL_SPEC_INCOMPLETE = "SYMBOL_SPEC_INCOMPLETE"
    SYMBOL_SPEC_CHANGED = "SYMBOL_SPEC_CHANGED"
    TICK_UNAVAILABLE = "TICK_UNAVAILABLE"
    TICK_INVALID = "TICK_INVALID"
    TICK_STALE = "TICK_STALE"
    TICK_FROM_FUTURE = "TICK_FROM_FUTURE"
    CLOCK_DRIFT_EXCEEDED = "CLOCK_DRIFT_EXCEEDED"
    CANDLE_DATA_INVALID = "CANDLE_DATA_INVALID"
    CANDLE_DATA_STALE = "CANDLE_DATA_STALE"
    HISTORY_QUERY_FAILED = "HISTORY_QUERY_FAILED"
    HISTORY_WINDOW_INCOMPLETE = "HISTORY_WINDOW_INCOMPLETE"
    RECONCILIATION_INCOMPLETE = "RECONCILIATION_INCOMPLETE"
    DATABASE_REPORT_FAILED = "DATABASE_REPORT_FAILED"
    NATIVE_ACCESS_CONFLICT = "NATIVE_ACCESS_CONFLICT"


class TickFreshness(StrEnum):
    LIVE = "live"
    DELAYED = "delayed"
    STALE = "stale"
    FUTURE_INVALID = "future_invalid"
    UNAVAILABLE = "unavailable"


class Timeframe(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"


class PositionDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


class SymbolTradeMode(StrEnum):
    DISABLED = "disabled"
    LONG_ONLY = "long_only"
    SHORT_ONLY = "short_only"
    CLOSE_ONLY = "close_only"
    FULL = "full"
    UNKNOWN = "unknown"


class SymbolUsabilityState(StrEnum):
    USABLE = "usable"
    NOT_VISIBLE = "not_visible"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class ReconciliationOutcome(StrEnum):
    MATCHED = "matched"
    MISMATCH = "mismatch"
    INCOMPLETE = "incomplete"


class ReconciliationCategory(StrEnum):
    UNEXPECTED_BROKER_POSITION = "UNEXPECTED_BROKER_POSITION"
    DATABASE_POSITION_MISSING_AT_BROKER = "DATABASE_POSITION_MISSING_AT_BROKER"
    UNEXPECTED_ACTIVE_ORDER = "UNEXPECTED_ACTIVE_ORDER"
    DATABASE_ORDER_MISSING_AT_BROKER = "DATABASE_ORDER_MISSING_AT_BROKER"
    EXECUTION_RESULT_UNCERTAIN = "EXECUTION_RESULT_UNCERTAIN"
    ACCOUNT_CHANGED = "ACCOUNT_CHANGED"
    SERVER_CHANGED = "SERVER_CHANGED"
    SYMBOL_SPEC_CHANGED = "SYMBOL_SPEC_CHANGED"
    HISTORY_WINDOW_INCOMPLETE = "HISTORY_WINDOW_INCOMPLETE"
    CLOCK_INCONSISTENCY = "CLOCK_INCONSISTENCY"


class Mt5WorkerConfig(Mt5Model):
    terminal_path: Path | None = None
    broker_symbol: str | None = None
    expected_account_fingerprint: str | None = None
    max_tick_age_seconds: Annotated[int, Field(ge=1, le=300)] = 10
    max_clock_drift_seconds: Annotated[int, Field(ge=1, le=300)] = 30
    candle_limit: Annotated[int, Field(ge=1, le=2_000)] = 500
    history_window_hours: Annotated[int, Field(ge=1, le=168)] = 24
    poll_interval_seconds: Annotated[
        Decimal, Field(ge=Decimal("1"), le=Decimal("300"))
    ] = Decimal("5")
    reconnect_max_seconds: Annotated[
        Decimal, Field(ge=Decimal("1"), le=Decimal("300"))
    ] = Decimal("60")
    readonly_smoke: bool = False

    @classmethod
    def from_environ(cls, environ: dict[str, str] | None = None) -> Self:
        values = os.environ if environ is None else environ
        terminal = values.get("AURUM_MT5_TERMINAL_PATH") or None
        return cls(
            terminal_path=Path(terminal) if terminal else None,
            broker_symbol=values.get("AURUM_MT5_BROKER_SYMBOL") or None,
            expected_account_fingerprint=values.get(
                "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT"
            )
            or None,
            max_tick_age_seconds=int(
                values.get("AURUM_MT5_MAX_TICK_AGE_SECONDS", "10")
            ),
            max_clock_drift_seconds=int(
                values.get("AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS", "30")
            ),
            candle_limit=int(values.get("AURUM_MT5_CANDLE_LIMIT", "500")),
            history_window_hours=int(
                values.get("AURUM_MT5_HISTORY_WINDOW_HOURS", "24")
            ),
            poll_interval_seconds=Decimal(
                values.get("AURUM_MT5_POLL_INTERVAL_SECONDS", "5")
            ),
            reconnect_max_seconds=Decimal(
                values.get("AURUM_MT5_RECONNECT_MAX_SECONDS", "60")
            ),
            readonly_smoke=values.get("AURUM_MT5_READONLY_SMOKE", "0") == "1",
        )


class TerminalObservation(ObservationModel):
    connected: bool
    platform: SafeIdentifier
    terminal_version: SafeIdentifier
    terminal_build: str | None = None
    trade_allowed: bool | None = None


class AccountObservation(ObservationModel):
    trade_mode: AccountTradeMode
    masked_login: SafeIdentifier
    masked_server: SafeIdentifier
    account_fingerprint: SafeIdentifier
    server_fingerprint: SafeIdentifier
    currency: str | None = None
    leverage: int | None = Field(default=None, ge=1)


class AccountVerificationResult(Mt5Model):
    state: AccountVerificationState
    health_state: HealthState
    reason_code: Mt5ReasonCode
    market_data_eligible: bool
    masked_login: str | None = None
    masked_server: str | None = None
    account_fingerprint: str | None = None


class BrokerSymbolCandidate(ObservationModel):
    broker_symbol: SafeIdentifier
    symbol_path: str
    description: str
    base_currency: str | None = None
    profit_currency: str | None = None
    exact_name: bool
    visible: bool


class BrokerSymbolObservation(ObservationModel):
    canonical_symbol: Literal["XAUUSD"] = "XAUUSD"
    broker_symbol: SafeIdentifier
    symbol_path: str
    description: str
    base_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    profit_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    margin_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    digits: int = Field(ge=0)
    point: PositiveDecimal
    tick_size: PositiveDecimal
    tick_value: NonNegativeDecimal
    tick_value_profit: NonNegativeDecimal
    tick_value_loss: NonNegativeDecimal
    contract_size: PositiveDecimal
    minimum_volume: PositiveDecimal
    maximum_volume: PositiveDecimal
    volume_step: PositiveDecimal
    stops_level: int = Field(ge=0)
    freeze_level: int = Field(ge=0)
    trade_calculation_mode: SafeIdentifier
    trade_mode: SymbolTradeMode
    filling_mode: SafeIdentifier
    expiration_mode: SafeIdentifier
    order_mode: SafeIdentifier
    specification_fingerprint: SafeIdentifier
    usability_state: SymbolUsabilityState
    unusable_reason: Mt5ReasonCode | None = None
    raw_diagnostic_codes: dict[str, int] | None = None

    @model_validator(mode="after")
    def validate_volume_range(self) -> Self:
        if self.maximum_volume < self.minimum_volume:
            raise ValueError("maximum volume must be at least minimum volume")
        if self.usability_state is SymbolUsabilityState.USABLE and self.unusable_reason:
            raise ValueError("usable symbol cannot have an unusable reason")
        return self


class LatestTickObservation(ObservationModel):
    symbol: SafeIdentifier
    bid: PositiveDecimal
    ask: PositiveDecimal
    spread_price: NonNegativeDecimal
    spread_points: NonNegativeDecimal
    tick_at: AwareDatetime
    age_seconds: NonNegativeDecimal
    freshness: TickFreshness

    @model_validator(mode="after")
    def validate_market(self) -> Self:
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        if self.spread_price != self.ask - self.bid:
            raise ValueError("spread price must equal ask minus bid")
        return self


class CandleRequest(Mt5Model):
    start_position: int = Field(default=1, ge=0)
    count: int = Field(default=100, ge=1, le=2_000)
    include_current: bool = False
    range_start: AwareDatetime | None = None
    range_end: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if (self.range_start is None) is not (self.range_end is None):
            raise ValueError("range start and end must be provided together")
        if self.range_start and self.range_end and self.range_end < self.range_start:
            raise ValueError("range end must not precede range start")
        if (
            self.range_start
            and self.range_end
            and (self.range_end - self.range_start).total_seconds() > 7 * 24 * 60 * 60
        ):
            raise ValueError("candle range exceeds seven days")
        if not self.include_current and self.start_position == 0:
            raise ValueError("completed-candle requests must exclude bar zero")
        return self


class CandleObservation(ObservationModel):
    symbol: SafeIdentifier
    timeframe: Timeframe
    open_at: AwareDatetime
    open: PositiveDecimal
    high: PositiveDecimal
    low: PositiveDecimal
    close: PositiveDecimal
    tick_volume: NonNegativeDecimal
    spread: NonNegativeDecimal
    real_volume: NonNegativeDecimal
    is_complete: bool

    @model_validator(mode="after")
    def validate_ohlc(self) -> Self:
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("candle high is inconsistent")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("candle low is inconsistent")
        return self


class CandleGap(Mt5Model):
    after_open_at: AwareDatetime
    before_open_at: AwareDatetime
    missing_intervals: int = Field(ge=1)


class CandleSeries(Mt5Model):
    candles: tuple[CandleObservation, ...]
    gaps: tuple[CandleGap, ...] = ()

    @model_validator(mode="after")
    def validate_strict_time_order(self) -> Self:
        if any(
            current.open_at >= following.open_at
            for current, following in zip(self.candles, self.candles[1:], strict=False)
        ):
            raise ValueError("candle timestamps must be strictly increasing")
        return self


class OpenPositionObservation(ObservationModel):
    ticket: TicketIdentifier
    symbol: SafeIdentifier
    direction: PositionDirection
    volume: NonNegativeDecimal
    entry_price: PositiveDecimal
    current_price: PositiveDecimal
    stop_loss: NonNegativeDecimal
    take_profit: NonNegativeDecimal
    unrealized_profit: DecimalValue
    swap: DecimalValue
    magic_number: str | None = None
    opened_at: AwareDatetime


class ActiveOrderObservation(ObservationModel):
    ticket: TicketIdentifier
    symbol: SafeIdentifier
    order_type: SafeIdentifier
    state: SafeIdentifier
    volume_initial: NonNegativeDecimal
    volume_current: NonNegativeDecimal
    requested_price: NonNegativeDecimal
    stop_loss: NonNegativeDecimal
    take_profit: NonNegativeDecimal
    setup_at: AwareDatetime
    expiration_at: AwareDatetime | None = None


class HistoricalOrderObservation(ObservationModel):
    ticket: TicketIdentifier
    position_ticket: TicketIdentifier | None = None
    symbol: SafeIdentifier
    order_type: SafeIdentifier
    state: SafeIdentifier
    volume_initial: NonNegativeDecimal
    volume_current: NonNegativeDecimal
    requested_price: NonNegativeDecimal
    stop_loss: NonNegativeDecimal
    take_profit: NonNegativeDecimal
    setup_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    safe_comment: str = ""


class HistoricalDealObservation(ObservationModel):
    ticket: TicketIdentifier
    order_ticket: TicketIdentifier
    position_ticket: TicketIdentifier
    symbol: SafeIdentifier
    direction: PositionDirection
    volume: NonNegativeDecimal
    price: PositiveDecimal
    profit: DecimalValue
    commission: DecimalValue
    swap: DecimalValue
    occurred_at: AwareDatetime
    safe_comment: str = ""


class HistoryRequest(Mt5Model):
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.end_at < self.start_at:
            raise ValueError("history end must not precede start")
        if (self.end_at - self.start_at).total_seconds() > 7 * 24 * 60 * 60:
            raise ValueError("history window exceeds seven days")
        return self


class ReconciliationMismatch(Mt5Model):
    category: ReconciliationCategory
    severity: Literal["warning", "critical"]
    resource_type: SafeIdentifier
    resource_reference: SafeIdentifier
    reason_code: Mt5ReasonCode | None = None


class ReconciliationReport(ObservationModel):
    reconciliation_id: SafeIdentifier
    started_at: AwareDatetime
    completed_at: AwareDatetime
    outcome: ReconciliationOutcome
    reason_code: Mt5ReasonCode
    account_fingerprint: str | None = None
    server_fingerprint: str | None = None
    symbol_specification_fingerprint: str | None = None
    open_position_count: int = Field(ge=0)
    active_order_count: int = Field(ge=0)
    order_history_count: int = Field(ge=0)
    deal_history_count: int = Field(ge=0)
    mismatches: tuple[ReconciliationMismatch, ...] = ()


class Mt5HealthSnapshot(ObservationModel):
    state: HealthState
    reason_code: Mt5ReasonCode
    package_available: bool
    platform: SafeIdentifier
    terminal_connected: bool
    terminal_version: str | None = None
    account_verification_state: AccountVerificationState | None = None
    masked_account: str | None = None
    masked_server: str | None = None
    broker_symbol: str | None = None
    specification_fingerprint: str | None = None
    tick_age_seconds: Decimal | None = None
    last_completed_candle_at: AwareDatetime | None = None
    last_successful_observation_at: AwareDatetime | None = None
    reconciliation_outcome: ReconciliationOutcome | None = None
    open_position_count: int | None = Field(default=None, ge=0)
    active_order_count: int | None = Field(default=None, ge=0)


class ReadOnlyPollingState(Mt5Model):
    running: bool
    connected: bool
    reconnect_attempt: int = Field(ge=0)
    next_reconnect_seconds: NonNegativeDecimal
    last_successful_observation_at: AwareDatetime | None = None
    reconciliation_required: bool
    stopped_at: AwareDatetime | None = None


class DatabaseReconciliationState(Mt5Model):
    position_tickets: frozenset[TicketIdentifier] = frozenset()
    active_order_tickets: frozenset[TicketIdentifier] = frozenset()
    executing_command_ids: frozenset[SafeIdentifier] = frozenset()
    account_fingerprint: str | None = None
    server_fingerprint: str | None = None
    broker_symbol: str | None = None
    symbol_specification_fingerprint: str | None = None
    history_window_complete: bool = True


class SafeMt5Error(Mt5Model):
    reason_code: Mt5ReasonCode
    safe_detail: Annotated[str, StringConstraints(max_length=240)]
    retryable: bool = False


class Mt5ReadFailure(RuntimeError):
    """Exception carrying only a bounded, browser-safe MT5 error model."""

    def __init__(self, error: SafeMt5Error) -> None:
        self.error = error
        super().__init__(f"{error.reason_code}: {error.safe_detail}")


def observation_time(value: datetime) -> datetime:
    """Narrow typing helper used by fakes and tests."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observation time must be timezone-aware")
    return value
