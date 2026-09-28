"""Bounded, count-only transaction query experiments; never time-contract proof."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from numbers import Integral
from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_PROBE_ROWS = 1000
MAX_HISTORY_QUERY_COUNT = 24
ProbeKind = Literal["orders", "deals"]
ProbeCode = Literal[
    "integer_event_window",
    "datetime_event_window",
    "integer_minus_three_hours_window",
    "datetime_minus_three_hours_window",
    "integer_setup_exact",
    "integer_left_boundary",
    "integer_exact_second",
    "integer_right_boundary",
    "integer_after_second",
    "datetime_before_millisecond",
    "datetime_exact_millisecond",
]
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_THREE_HOURS = timedelta(hours=3)


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, hide_input_in_errors=True
    )


class OperatorTimeWindow(_StrictModel):
    """Independent operator recollection, not a broker-derived timestamp."""

    start_at: datetime = Field(repr=False)
    end_at: datetime = Field(repr=False)

    @field_validator("start_at", "end_at")
    @classmethod
    def _aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Reference window invalid.")
        try:
            return value.astimezone(UTC)
        except (OverflowError, ValueError):
            raise ValueError("Reference window invalid.") from None

    @model_validator(mode="after")
    def _bounded(self) -> Self:
        duration = self.end_at - self.start_at
        if not timedelta(0) < duration <= timedelta(hours=1):
            raise ValueError("Reference window invalid.")
        return self


@dataclass(frozen=True, repr=False)
class ProbeRow:
    """Transient native identifiers and raw epoch labels, never exported."""

    ticket: int
    event_seconds: int
    event_milliseconds: int
    setup_seconds: int | None
    linked_order: int | None
    setup_milliseconds: int | None = None


@dataclass(frozen=True, repr=False)
class QueryPlan:
    code: ProbeCode
    start: datetime | int
    end: datetime | int


class QueryProbeResult(_StrictModel):
    code: ProbeCode
    target_present: bool
    matching_rows: int = Field(ge=0, le=MAX_PROBE_ROWS)


class CollectionTimeProbe(_StrictModel):
    matching_rows: int = Field(ge=0, le=MAX_PROBE_ROWS)
    selected_event_has_subsecond: bool
    setup_done_distinguishable: bool
    as_utc_reference_matches: int | None = Field(ge=0, le=MAX_PROBE_ROWS)
    minus_three_hours_reference_matches: int | None = Field(ge=0, le=MAX_PROBE_ROWS)
    queries: tuple[QueryProbeResult, ...] = Field(max_length=10)


class TransactionTimeProbe(_StrictModel):
    status: Literal["probe_observed"] = "probe_observed"
    grants_eligibility: Literal[False] = False
    smoke_invoked: Literal[False] = False
    transaction_time_contract: Literal["unverified"] = "unverified"
    history_query_count: int = Field(ge=0, le=MAX_HISTORY_QUERY_COUNT)
    reference_supplied: bool
    stable_snapshots: bool
    orders: CollectionTimeProbe
    deals: CollectionTimeProbe

    @field_validator("grants_eligibility", "smoke_invoked", mode="before")
    @classmethod
    def _strict_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("Probe outcome invalid.")
        return value


def _positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError("Probe rows invalid.")
    return int(value)


def _milliseconds_datetime(value: int) -> datetime:
    try:
        return _EPOCH + timedelta(milliseconds=value)
    except (OverflowError, ValueError):
        raise ValueError("Probe time invalid.") from None


def _time_pair(seconds: object, milliseconds: object) -> tuple[int, int]:
    checked_seconds = _positive_integer(seconds)
    checked_milliseconds = _positive_integer(milliseconds)
    if checked_milliseconds // 1000 != checked_seconds:
        raise ValueError("Probe rows invalid.")
    _milliseconds_datetime(checked_milliseconds)
    return checked_seconds, checked_milliseconds


def parse_probe_rows(
    rows: object,
    *,
    kind: ProbeKind,
    symbol: str,
    field: Callable[[object, str], object],
) -> tuple[ProbeRow, ...]:
    """Read only allowlisted identity/time fields; reject partial observations."""
    try:
        if (
            kind not in {"orders", "deals"}
            or type(symbol) is not str
            or not symbol
            or type(rows) not in {tuple, list}
        ):
            raise ValueError("Probe rows invalid.")
        checked_rows = cast(tuple[object, ...] | list[object], rows)
        if len(checked_rows) > MAX_PROBE_ROWS:
            raise ValueError("Probe rows invalid.")
        parsed: list[ProbeRow] = []
        tickets: set[int] = set()
        for row in checked_rows:
            reported_symbol = field(row, "symbol")
            if type(reported_symbol) is not str:
                raise ValueError("Probe rows invalid.")
            if reported_symbol != symbol:
                continue
            ticket = _positive_integer(field(row, "ticket"))
            if ticket in tickets:
                raise ValueError("Probe rows invalid.")
            tickets.add(ticket)
            setup_seconds: int | None = None
            setup_milliseconds: int | None = None
            linked_order: int | None = None
            if kind == "orders":
                seconds, milliseconds = _time_pair(
                    field(row, "time_done"), field(row, "time_done_msc")
                )
                setup_seconds, setup_milliseconds = _time_pair(
                    field(row, "time_setup"), field(row, "time_setup_msc")
                )
                if milliseconds < setup_milliseconds:
                    raise ValueError("Probe rows invalid.")
            else:
                seconds, milliseconds = _time_pair(
                    field(row, "time"), field(row, "time_msc")
                )
                linked_order = _positive_integer(field(row, "order"))
            parsed.append(
                ProbeRow(
                    ticket,
                    seconds,
                    milliseconds,
                    setup_seconds,
                    linked_order,
                    setup_milliseconds,
                )
            )
        return tuple(parsed)
    except Exception:
        # Native field access errors must not carry raw row values into output.
        raise ValueError("Probe rows invalid.") from None


def select_anchor(rows: tuple[ProbeRow, ...], *, kind: ProbeKind) -> ProbeRow:
    if kind not in {"orders", "deals"} or not rows:
        raise ValueError("Probe anchor unavailable.")
    candidates = rows
    if kind == "orders":
        distinguishable = tuple(
            row
            for row in rows
            if row.setup_seconds is not None and row.setup_seconds != row.event_seconds
        )
        if distinguishable:
            candidates = distinguishable
    return max(candidates, key=lambda row: (row.event_milliseconds, row.ticket))


def build_probe_queries(anchor: ProbeRow, *, kind: ProbeKind) -> tuple[QueryPlan, ...]:
    """A fixed ten-query hypothesis matrix; no automatic interpretation."""
    if kind not in {"orders", "deals"}:
        raise ValueError("Probe query invalid.")
    seconds, milliseconds = _time_pair(anchor.event_seconds, anchor.event_milliseconds)
    raw_start = _milliseconds_datetime((seconds - 1) * 1000)
    raw_end = _milliseconds_datetime((seconds + 1) * 1000)
    shifted_start = _milliseconds_datetime((seconds - 10801) * 1000)
    shifted_end = _milliseconds_datetime((seconds - 10799) * 1000)
    fourth = QueryPlan("datetime_minus_three_hours_window", shifted_start, shifted_end)
    if kind == "orders":
        setup = _positive_integer(anchor.setup_seconds)
        if setup > seconds:
            raise ValueError("Probe query invalid.")
        if setup != seconds:
            fourth = QueryPlan("integer_setup_exact", setup, setup)
    before_millisecond = _milliseconds_datetime(milliseconds - 1)
    exact_millisecond = _milliseconds_datetime(milliseconds)
    return (
        QueryPlan("integer_event_window", seconds - 1, seconds + 1),
        QueryPlan("datetime_event_window", raw_start, raw_end),
        QueryPlan("integer_minus_three_hours_window", seconds - 10801, seconds - 10799),
        fourth,
        QueryPlan("integer_left_boundary", seconds - 1, seconds),
        QueryPlan("integer_exact_second", seconds, seconds),
        QueryPlan("integer_right_boundary", seconds, seconds + 1),
        QueryPlan("integer_after_second", seconds + 1, seconds + 2),
        QueryPlan(
            "datetime_before_millisecond", before_millisecond, before_millisecond
        ),
        QueryPlan("datetime_exact_millisecond", exact_millisecond, exact_millisecond),
    )


def reference_match_counts(
    rows: tuple[ProbeRow, ...], reference: OperatorTimeWindow | None
) -> tuple[int | None, int | None]:
    """Compare independent recollection with two labels, without choosing policy."""
    if reference is None:
        return None, None
    as_utc = 0
    minus_three_hours = 0
    for row in rows:
        raw = _milliseconds_datetime(row.event_milliseconds)
        shifted = raw - _THREE_HOURS
        as_utc += int(reference.start_at <= raw <= reference.end_at)
        minus_three_hours += int(reference.start_at <= shifted <= reference.end_at)
    return as_utc, minus_three_hours
