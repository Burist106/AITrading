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
SpecificationFingerprint = Annotated[
    str,
    StringConstraints(pattern=r"^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$"),
]
UuidIdentifier = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
    ),
]


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


class Mt5ComponentCode(StrEnum):
    WORKER = "execution.worker"
    MT5_ADAPTER = "execution.mt5_adapter"
    MARKET_DATA = "execution.market_data"


class ComponentHeartbeatState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


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
    SYMBOL_CANONICAL_MISMATCH = "SYMBOL_CANONICAL_MISMATCH"
    SYMBOL_SPEC_INCOMPLETE = "SYMBOL_SPEC_INCOMPLETE"
    SYMBOL_SPEC_CONFIRMATION_REQUIRED = "SYMBOL_SPEC_CONFIRMATION_REQUIRED"
    SYMBOL_SPEC_CHANGED = "SYMBOL_SPEC_CHANGED"
    TICK_UNAVAILABLE = "TICK_UNAVAILABLE"
    TICK_INVALID = "TICK_INVALID"
    TICK_DELAYED = "TICK_DELAYED"
    TICK_STALE = "TICK_STALE"
    TICK_FROM_FUTURE = "TICK_FROM_FUTURE"
    CLOCK_DRIFT_EXCEEDED = "CLOCK_DRIFT_EXCEEDED"
    CANDLE_DATA_INVALID = "CANDLE_DATA_INVALID"
    CANDLE_DATA_STALE = "CANDLE_DATA_STALE"
    HISTORY_EMPTY_VALID_RESULT = "HISTORY_EMPTY_VALID_RESULT"
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


_MARKET_DATA_FAILURE_DETAILS = frozenset(
    {
        Mt5ReasonCode.TICK_INVALID,
        Mt5ReasonCode.TICK_STALE,
        Mt5ReasonCode.TICK_FROM_FUTURE,
        Mt5ReasonCode.TICK_UNAVAILABLE,
    }
)


class ComponentHeartbeat(Mt5Model):
    component_code: Mt5ComponentCode
    state: ComponentHeartbeatState
    detail: Mt5ReasonCode
    observed_at: AwareDatetime
    valid_for_seconds: Annotated[int, Field(ge=15, le=300)]
    trace_id: SafeIdentifier

    @model_validator(mode="after")
    def validate_state_detail_pair(self) -> Self:
        if (self.state is ComponentHeartbeatState.HEALTHY) is not (
            self.detail is Mt5ReasonCode.HEALTHY
        ):
            raise ValueError(
                "Healthy component state and HEALTHY detail must be reported together."
            )
        if (
            self.component_code is Mt5ComponentCode.MARKET_DATA
            and self.state is ComponentHeartbeatState.DEGRADED
            and self.detail is not Mt5ReasonCode.TICK_DELAYED
        ):
            raise ValueError("Degraded market data requires TICK_DELAYED detail.")
        if (
            self.component_code is Mt5ComponentCode.MARKET_DATA
            and self.state is ComponentHeartbeatState.FAILED
            and self.detail not in _MARKET_DATA_FAILURE_DETAILS
        ):
            raise ValueError("Failed market data requires a tick failure detail.")
        return self


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
    SYMBOL_SPEC_CONFIRMATION_REQUIRED = "SYMBOL_SPEC_CONFIRMATION_REQUIRED"
    SYMBOL_SPEC_CHANGED = "SYMBOL_SPEC_CHANGED"
    HISTORY_QUERY_FAILED = "HISTORY_QUERY_FAILED"
    HISTORY_WINDOW_INCOMPLETE = "HISTORY_WINDOW_INCOMPLETE"
    CLOCK_INCONSISTENCY = "CLOCK_INCONSISTENCY"


class HistoryQueryResultState(StrEnum):
    QUERY_SUCCEEDED = "query_succeeded"
    EMPTY_VALID_RESULT = "empty_valid_result"
    QUERY_FAILED = "query_failed"
    WINDOW_INCOMPLETE = "window_incomplete"
    WINDOW_UNKNOWN = "window_unknown"


class Mt5WorkerConfig(Mt5Model):
    terminal_path: Path | None = None
    broker_symbol: str | None = None
    expected_account_fingerprint: str | None = None
    smoke_confirmed_specification_fingerprint: SpecificationFingerprint | None = None
    max_tick_age_seconds: Annotated[int, Field(ge=1, le=300)] = 10
    max_clock_drift_seconds: Annotated[int, Field(ge=1, le=300)] = 30
    candle_limit: Annotated[int, Field(ge=1, le=2_000)] = 500
    history_window_hours: Annotated[int, Field(ge=1, le=168)] = 24
    tick_poll_seconds: Annotated[Decimal, Field(ge=Decimal("1"), le=Decimal("30"))] = (
        Decimal("5")
    )
    heartbeat_valid_for_seconds: Annotated[int, Field(ge=15, le=300)] = 30
    position_poll_seconds: Annotated[
        Decimal, Field(ge=Decimal("5"), le=Decimal("300"))
    ] = Decimal("15")
    full_reconciliation_seconds: Annotated[
        Decimal, Field(ge=Decimal("60"), le=Decimal("3600"))
    ] = Decimal("600")
    reconnect_max_seconds: Annotated[
        Decimal, Field(ge=Decimal("1"), le=Decimal("300"))
    ] = Decimal("60")
    readonly_smoke: bool = False

    @model_validator(mode="after")
    def validate_heartbeat_cadence(self) -> Self:
        minimum_ttl = self.tick_poll_seconds * Decimal(3)
        if Decimal(self.heartbeat_valid_for_seconds) < minimum_ttl:
            raise ValueError(
                "heartbeat TTL must be at least three tick polling intervals"
            )
        return self

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
            smoke_confirmed_specification_fingerprint=values.get(
                "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT"
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
            tick_poll_seconds=Decimal(values.get("AURUM_MT5_TICK_POLL_SECONDS") or "5"),
            heartbeat_valid_for_seconds=int(
                values.get("AURUM_MT5_HEARTBEAT_VALID_FOR_SECONDS") or "30"
            ),
            position_poll_seconds=Decimal(
                values.get("AURUM_MT5_POSITION_POLL_SECONDS") or "15"
            ),
            full_reconciliation_seconds=Decimal(
                values.get("AURUM_MT5_FULL_RECONCILIATION_SECONDS") or "600"
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
    base_currency: Literal["XAU"]
    profit_currency: Literal["USD"]
    exact_name: bool
    visible: bool


class BrokerSymbolObservation(ObservationModel):
    canonical_symbol: Literal["XAUUSD"] = "XAUUSD"
    broker_symbol: SafeIdentifier
    symbol_path: str
    description: str
    base_currency: Literal["XAU"]
    profit_currency: Literal["USD"]
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
        if self.end_at <= self.start_at:
            raise ValueError("history start must precede end")
        if (self.end_at - self.start_at).total_seconds() > 7 * 24 * 60 * 60:
            raise ValueError("history window exceeds seven days")
        return self


class HistoryQueryEvidence(Mt5Model):
    history_kind: Literal["orders", "deals"]
    requested_start_at: AwareDatetime
    requested_end_at: AwareDatetime
    query_completed_at: AwareDatetime | None = None
    returned_count: int = Field(ge=0)
    earliest_returned_at: AwareDatetime | None = None
    latest_returned_at: AwareDatetime | None = None
    result_state: HistoryQueryResultState
    reason_code: Mt5ReasonCode

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if self.requested_end_at <= self.requested_start_at:
            raise ValueError("history evidence start must precede end")
        if (
            self.query_completed_at is not None
            and self.query_completed_at < self.requested_end_at
        ):
            raise ValueError("history evidence completion must not precede request end")
        if (self.earliest_returned_at is None) is not (self.latest_returned_at is None):
            raise ValueError("history evidence boundaries must be paired")
        if (
            self.earliest_returned_at is not None
            and self.latest_returned_at is not None
            and self.latest_returned_at < self.earliest_returned_at
        ):
            raise ValueError("history evidence boundaries are inconsistent")

        successful = self.result_state in {
            HistoryQueryResultState.QUERY_SUCCEEDED,
            HistoryQueryResultState.EMPTY_VALID_RESULT,
        }
        if successful and self.query_completed_at is None:
            raise ValueError("successful history evidence requires completion time")
        if self.result_state is HistoryQueryResultState.QUERY_SUCCEEDED:
            if self.reason_code is not Mt5ReasonCode.HEALTHY:
                raise ValueError("non-empty history evidence requires healthy reason")
            if self.returned_count == 0 or self.earliest_returned_at is None:
                raise ValueError("non-empty history evidence requires row boundaries")
        elif self.result_state is HistoryQueryResultState.EMPTY_VALID_RESULT:
            if self.reason_code is not Mt5ReasonCode.HISTORY_EMPTY_VALID_RESULT:
                raise ValueError("empty history evidence requires empty-result reason")
            if self.returned_count != 0 or self.earliest_returned_at is not None:
                raise ValueError("empty history evidence cannot contain row boundaries")
        elif self.result_state is HistoryQueryResultState.QUERY_FAILED:
            if self.query_completed_at is None:
                raise ValueError("failed history evidence requires completion time")
            if self.returned_count != 0 or self.earliest_returned_at is not None:
                raise ValueError("failed history evidence cannot claim returned rows")
            if self.reason_code is not Mt5ReasonCode.HISTORY_QUERY_FAILED:
                raise ValueError("failed history evidence requires failure reason")
        elif self.result_state is HistoryQueryResultState.WINDOW_UNKNOWN:
            if self.query_completed_at is not None:
                raise ValueError("unknown history evidence cannot claim completion")
            if self.returned_count != 0 or self.earliest_returned_at is not None:
                raise ValueError("unknown history evidence cannot claim returned rows")
            if self.reason_code is not Mt5ReasonCode.HISTORY_WINDOW_INCOMPLETE:
                raise ValueError("unknown history evidence requires incomplete reason")
        elif (
            self.result_state is HistoryQueryResultState.WINDOW_INCOMPLETE
            and self.reason_code is not Mt5ReasonCode.HISTORY_WINDOW_INCOMPLETE
        ):
            raise ValueError("incomplete history evidence requires incomplete reason")
        return self


class ConfirmedSymbolBinding(Mt5Model):
    owner_id: UuidIdentifier
    trading_account_id: UuidIdentifier
    canonical_symbol: Literal["XAUUSD"]
    broker_symbol: SafeIdentifier
    confirmed_specification_fingerprint: SpecificationFingerprint
    confirmation_status: Literal["confirmed"]
    confirmed_at: AwareDatetime
    confirmed_by: UuidIdentifier
    version: int = Field(ge=1)


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
    broker_symbol: SafeIdentifier | None = None
    symbol_specification_fingerprint: str | None = None
    open_position_count: int = Field(ge=0)
    active_order_count: int = Field(ge=0)
    order_history_count: int = Field(ge=0)
    deal_history_count: int = Field(ge=0)
    order_history_evidence: HistoryQueryEvidence
    deal_history_evidence: HistoryQueryEvidence
    mismatches: tuple[ReconciliationMismatch, ...] = ()

    @model_validator(mode="after")
    def validate_history_evidence(self) -> Self:
        if self.order_history_evidence.history_kind != "orders":
            raise ValueError("order history evidence kind must be orders")
        if self.deal_history_evidence.history_kind != "deals":
            raise ValueError("deal history evidence kind must be deals")
        if self.order_history_count != self.order_history_evidence.returned_count:
            raise ValueError("order history count must match current evidence")
        if self.deal_history_count != self.deal_history_evidence.returned_count:
            raise ValueError("deal history count must match current evidence")
        if self.outcome is ReconciliationOutcome.MATCHED:
            if self.reason_code is not Mt5ReasonCode.HEALTHY:
                raise ValueError("matched reconciliation requires healthy reason")
            if any(
                value is None
                for value in (
                    self.account_fingerprint,
                    self.server_fingerprint,
                    self.broker_symbol,
                    self.symbol_specification_fingerprint,
                )
            ):
                raise ValueError("matched reconciliation requires complete identity")
            successful_states = {
                HistoryQueryResultState.QUERY_SUCCEEDED,
                HistoryQueryResultState.EMPTY_VALID_RESULT,
            }
            if (
                self.order_history_evidence.result_state not in successful_states
                or self.deal_history_evidence.result_state not in successful_states
            ):
                raise ValueError("matched reconciliation requires successful history")
            if self.mismatches:
                raise ValueError("matched reconciliation cannot contain mismatches")
        return self


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
    health_state: HealthState | None = None
    reason_code: Mt5ReasonCode | None = None
    stopped_at: AwareDatetime | None = None


class DatabaseReconciliationState(Mt5Model):
    position_tickets: frozenset[TicketIdentifier] = frozenset()
    active_order_tickets: frozenset[TicketIdentifier] = frozenset()
    executing_command_ids: frozenset[SafeIdentifier] = frozenset()
    account_fingerprint: str | None = None
    server_fingerprint: str | None = None
    confirmed_symbol_binding: ConfirmedSymbolBinding | None = None


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
