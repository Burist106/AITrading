"""Bounded identity-link observations; never transaction-time or execution proof."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from numbers import Integral
from typing import Literal, Self, cast, overload

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_LINK_ROWS = 1000
MAX_POSITION_REFERENCES = 10
_MAX_IDENTIFIER = 2**63 - 1
_EPOCH = datetime(1970, 1, 1)
LinkKind = Literal["positions", "orders", "deals"]
PositionLinkUnavailableCode = Literal[
    "LINK_REFERENCE_INVALID",
    "LINK_POSITION_NOT_FOUND",
    "LINK_ORDER_UNAVAILABLE",
    "LINK_DEAL_UNAVAILABLE",
    "LINK_CHAIN_UNSUPPORTED",
    "LINK_SNAPSHOT_INVALID",
]
LINK_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "LINK_REFERENCE_INVALID",
        "LINK_POSITION_NOT_FOUND",
        "LINK_ORDER_UNAVAILABLE",
        "LINK_DEAL_UNAVAILABLE",
        "LINK_CHAIN_UNSUPPORTED",
        "LINK_SNAPSHOT_INVALID",
    }
)


def _validated_link_failure_code(code: object) -> PositionLinkUnavailableCode:
    if type(code) is not str or code not in LINK_FAILURE_CODES:
        raise ValueError("Position link observation unavailable.") from None
    return cast(PositionLinkUnavailableCode, code)


class PositionLinkUnavailable(ValueError):
    """A closed diagnostic code, never native details or operator input."""

    _code: PositionLinkUnavailableCode

    def __init__(self, code: PositionLinkUnavailableCode) -> None:
        self._code = _validated_link_failure_code(code)
        super().__init__("Position link observation unavailable.")

    @property
    def code(self) -> PositionLinkUnavailableCode:
        return self._code


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, hide_input_in_errors=True
    )


class PositionReference(_StrictModel):
    """Transient operator-visible opening label and current position ticket."""

    ticket: int = Field(gt=0, le=_MAX_IDENTIFIER, repr=False)
    opening_label: datetime = Field(repr=False)

    @field_validator("opening_label")
    @classmethod
    def _naive_whole_second(cls, value: datetime) -> datetime:
        if value.tzinfo is not None or value.microsecond != 0:
            raise ValueError("Position reference invalid.")
        return value


@dataclass(frozen=True, repr=False)
class PositionRow:
    """Internal snapshot; identifiers and raw time labels must not be exported."""

    ticket: int
    identifier: int
    time: int
    time_msc: int
    time_update: int
    time_update_msc: int
    type: int


@dataclass(frozen=True, repr=False)
class OrderRow:
    ticket: int
    position_id: int
    time_setup: int
    time_setup_msc: int
    time_done: int
    time_done_msc: int
    type: int


@dataclass(frozen=True, repr=False)
class DealRow:
    ticket: int
    position_id: int
    order: int
    time: int
    time_msc: int
    entry: int
    type: int


type LinkRow = PositionRow | OrderRow | DealRow


class PositionLinkProbe(_StrictModel):
    status: Literal["position_links_observed"] = "position_links_observed"
    grants_eligibility: Literal[False] = False
    smoke_invoked: Literal[False] = False
    transaction_time_contract: Literal["unverified"] = "unverified"
    collection_read_count: Literal[6] = 6
    stable_snapshots: Literal[True] = True
    positions_observed: int = Field(ge=1, le=MAX_LINK_ROWS)
    references_checked: int = Field(ge=1, le=MAX_POSITION_REFERENCES)
    linked_positions: int = Field(ge=1, le=MAX_POSITION_REFERENCES)
    display_second_matches: int = Field(ge=0, le=MAX_POSITION_REFERENCES)
    position_deal_second_matches: int = Field(ge=0, le=MAX_POSITION_REFERENCES)
    position_deal_millisecond_matches: int = Field(ge=0, le=MAX_POSITION_REFERENCES)
    order_setup_done_distinguishable: int = Field(ge=0, le=MAX_POSITION_REFERENCES)
    order_deal_time_order_matches: int = Field(ge=0, le=MAX_POSITION_REFERENCES)

    @field_validator("grants_eligibility", "smoke_invoked", mode="before")
    @classmethod
    def _strict_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("Position link outcome invalid.")
        return value

    @field_validator("stable_snapshots", mode="before")
    @classmethod
    def _strict_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Position link outcome invalid.")
        return value

    @field_validator("collection_read_count", mode="before")
    @classmethod
    def _strict_six(cls, value: object) -> object:
        if type(value) is not int or value != 6:
            raise ValueError("Position link outcome invalid.")
        return value

    @model_validator(mode="after")
    def _count_relationships(self) -> Self:
        if (
            self.linked_positions != self.references_checked
            or self.positions_observed < self.linked_positions
            or any(
                count > self.references_checked
                for count in (
                    self.display_second_matches,
                    self.position_deal_second_matches,
                    self.position_deal_millisecond_matches,
                    self.order_setup_done_distinguishable,
                    self.order_deal_time_order_matches,
                )
            )
            or self.position_deal_millisecond_matches
            > self.position_deal_second_matches
        ):
            raise ValueError("Position link outcome invalid.")
        return self


def _integer(value: object, *, minimum: int = 1, maximum: int = _MAX_IDENTIFIER) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("Position link rows invalid.")
    checked = int(value)
    if not minimum <= checked <= maximum:
        raise ValueError("Position link rows invalid.")
    return checked


def _time_pair(seconds: object, milliseconds: object) -> tuple[int, int]:
    checked_seconds = _integer(seconds)
    checked_milliseconds = _integer(milliseconds)
    if checked_milliseconds // 1000 != checked_seconds:
        raise ValueError("Position link rows invalid.")
    try:
        _EPOCH + timedelta(milliseconds=checked_milliseconds)
    except (OverflowError, ValueError):
        raise ValueError("Position link rows invalid.") from None
    return checked_seconds, checked_milliseconds


def _parse_position(row: object, field: Callable[[object, str], object]) -> PositionRow:
    seconds, milliseconds = _time_pair(field(row, "time"), field(row, "time_msc"))
    update_seconds, update_milliseconds = _time_pair(
        field(row, "time_update"), field(row, "time_update_msc")
    )
    if update_milliseconds < milliseconds:
        raise ValueError("Position link rows invalid.")
    return PositionRow(
        _integer(field(row, "ticket")),
        _integer(field(row, "identifier")),
        seconds,
        milliseconds,
        update_seconds,
        update_milliseconds,
        _integer(field(row, "type"), minimum=0, maximum=1),
    )


def _parse_order(row: object, field: Callable[[object, str], object]) -> OrderRow:
    setup_seconds, setup_milliseconds = _time_pair(
        field(row, "time_setup"), field(row, "time_setup_msc")
    )
    done_seconds, done_milliseconds = _time_pair(
        field(row, "time_done"), field(row, "time_done_msc")
    )
    if done_milliseconds < setup_milliseconds:
        raise ValueError("Position link rows invalid.")
    return OrderRow(
        _integer(field(row, "ticket")),
        _integer(field(row, "position_id"), minimum=0),
        setup_seconds,
        setup_milliseconds,
        done_seconds,
        done_milliseconds,
        _integer(field(row, "type"), minimum=0, maximum=8),
    )


def _parse_deal(row: object, field: Callable[[object, str], object]) -> DealRow:
    seconds, milliseconds = _time_pair(field(row, "time"), field(row, "time_msc"))
    return DealRow(
        _integer(field(row, "ticket")),
        _integer(field(row, "position_id")),
        _integer(field(row, "order")),
        seconds,
        milliseconds,
        _integer(field(row, "entry"), minimum=0, maximum=3),
        _integer(field(row, "type"), minimum=0, maximum=1),
    )


@overload
def parse_link_rows(
    rows: object,
    *,
    kind: Literal["positions"],
    symbol: str,
    field: Callable[[object, str], object],
) -> tuple[PositionRow, ...]: ...


@overload
def parse_link_rows(
    rows: object,
    *,
    kind: Literal["orders"],
    symbol: str,
    field: Callable[[object, str], object],
) -> tuple[OrderRow, ...]: ...


@overload
def parse_link_rows(
    rows: object,
    *,
    kind: Literal["deals"],
    symbol: str,
    field: Callable[[object, str], object],
) -> tuple[DealRow, ...]: ...


@overload
def parse_link_rows(
    rows: object,
    *,
    kind: LinkKind,
    symbol: str,
    field: Callable[[object, str], object],
) -> tuple[LinkRow, ...]: ...


def parse_link_rows(
    rows: object,
    *,
    kind: LinkKind,
    symbol: str,
    field: Callable[[object, str], object],
) -> tuple[LinkRow, ...]:
    """Parse bounded exact-symbol snapshots using only identity/time fields."""
    try:
        if (
            kind not in {"positions", "orders", "deals"}
            or type(symbol) is not str
            or not symbol
            or type(rows) not in {tuple, list}
        ):
            raise ValueError("Position link rows invalid.")
        checked_rows = cast(tuple[object, ...] | list[object], rows)
        if len(checked_rows) > MAX_LINK_ROWS:
            raise ValueError("Position link rows invalid.")
        parsed: list[LinkRow] = []
        tickets: set[int] = set()
        identifiers: set[int] = set()
        for row in checked_rows:
            reported_symbol = field(row, "symbol")
            if type(reported_symbol) is not str:
                raise ValueError("Position link rows invalid.")
            if reported_symbol != symbol:
                continue
            parsed_row: LinkRow
            if kind == "positions":
                parsed_row = _parse_position(row, field)
                if parsed_row.identifier in identifiers:
                    raise ValueError("Position link rows invalid.")
                identifiers.add(parsed_row.identifier)
            elif kind == "orders":
                parsed_row = _parse_order(row, field)
            else:
                parsed_row = _parse_deal(row, field)
            if parsed_row.ticket in tickets:
                raise ValueError("Position link rows invalid.")
            tickets.add(parsed_row.ticket)
            parsed.append(parsed_row)
        return tuple(sorted(parsed, key=lambda item: item.ticket))
    except Exception:
        # Native callbacks may include account details in exception messages.
        raise ValueError("Position link rows invalid.") from None


def _field(row: object, name: str) -> object:
    return getattr(row, name)


def _checked_snapshot[Row: LinkRow](
    rows: tuple[Row, ...],
    row_type: type[Row],
    parser: Callable[[object, Callable[[object, str], object]], Row],
) -> tuple[Row, ...]:
    if type(rows) not in {tuple, list} or len(rows) > MAX_LINK_ROWS:
        raise ValueError("Position link snapshot invalid.")
    tickets: set[int] = set()
    checked: list[Row] = []
    for row in rows:
        if type(row) is not row_type:
            raise ValueError("Position link snapshot invalid.")
        normalized = parser(row, _field)
        if normalized.ticket in tickets:
            raise ValueError("Position link snapshot invalid.")
        tickets.add(normalized.ticket)
        checked.append(normalized)
    return tuple(checked)


def analyze_position_links(
    positions: tuple[PositionRow, ...],
    orders: tuple[OrderRow, ...],
    deals: tuple[DealRow, ...],
    references: tuple[PositionReference, ...],
) -> PositionLinkProbe:
    """Observe a simple original opening chain for every requested current ticket.

    The coordinator owns six stable bounded collection reads. Matching labels
    merely count observations; they cannot establish the native time contract.
    Additional fills, changes of direction, and partial closes are unsupported.
    """
    failure_code: PositionLinkUnavailableCode = "LINK_SNAPSHOT_INVALID"
    try:
        checked_positions = _checked_snapshot(positions, PositionRow, _parse_position)
        checked_orders = _checked_snapshot(orders, OrderRow, _parse_order)
        checked_deals = _checked_snapshot(deals, DealRow, _parse_deal)
        if len({position.identifier for position in checked_positions}) != len(
            checked_positions
        ):
            raise PositionLinkUnavailable("LINK_SNAPSHOT_INVALID")
        failure_code = "LINK_REFERENCE_INVALID"
        if (
            type(references) not in {tuple, list}
            or not 1 <= len(references) <= MAX_POSITION_REFERENCES
        ):
            raise PositionLinkUnavailable("LINK_REFERENCE_INVALID")
        references_checked: list[PositionReference] = []
        tickets: set[int] = set()
        for reference in references:
            if type(reference) is not PositionReference:
                raise PositionLinkUnavailable("LINK_REFERENCE_INVALID")
            checked_reference = PositionReference.model_validate(
                reference.model_dump(warnings="error")
            )
            if checked_reference.ticket in tickets:
                raise PositionLinkUnavailable("LINK_REFERENCE_INVALID")
            tickets.add(checked_reference.ticket)
            references_checked.append(checked_reference)
        failure_code = "LINK_SNAPSHOT_INVALID"
        by_ticket = {position.ticket: position for position in checked_positions}
        display_matches = second_matches = millisecond_matches = 0
        order_distinguishable = order_time_matches = 0
        used_orders: set[int] = set()
        used_deals: set[int] = set()
        for reference in references_checked:
            position = by_ticket.get(reference.ticket)
            if position is None:
                raise PositionLinkUnavailable("LINK_POSITION_NOT_FOUND")
            linked_orders = tuple(
                order
                for order in checked_orders
                if order.position_id == position.identifier
                or order.ticket == position.identifier
            )
            if len(linked_orders) != 1:
                raise PositionLinkUnavailable("LINK_ORDER_UNAVAILABLE")
            order = linked_orders[0]
            linked_deals = tuple(
                deal
                for deal in checked_deals
                if deal.position_id == position.identifier or deal.order == order.ticket
            )
            if len(linked_deals) != 1:
                raise PositionLinkUnavailable("LINK_DEAL_UNAVAILABLE")
            deal = linked_deals[0]
            if (
                order.ticket != position.identifier
                or order.position_id != position.identifier
                or deal.position_id != position.identifier
                or deal.order != order.ticket
                or deal.entry != 0
                or not order.type == deal.type == position.type
                or order.ticket in used_orders
                or deal.ticket in used_deals
            ):
                raise PositionLinkUnavailable("LINK_CHAIN_UNSUPPORTED")
            used_orders.add(order.ticket)
            used_deals.add(deal.ticket)
            display_matches += int(
                reference.opening_label == _EPOCH + timedelta(seconds=position.time)
            )
            second_matches += int(position.time == deal.time)
            millisecond_matches += int(position.time_msc == deal.time_msc)
            order_distinguishable += int(order.time_setup != order.time_done)
            order_time_matches += int(
                order.time_setup_msc <= deal.time_msc <= order.time_done_msc
            )
        return PositionLinkProbe(
            positions_observed=len(checked_positions),
            references_checked=len(references_checked),
            linked_positions=len(references_checked),
            display_second_matches=display_matches,
            position_deal_second_matches=second_matches,
            position_deal_millisecond_matches=millisecond_matches,
            order_setup_done_distinguishable=order_distinguishable,
            order_deal_time_order_matches=order_time_matches,
        )
    except PositionLinkUnavailable as exc:
        # Reconstruct through the closed-code validator; never carry raw messages.
        raise PositionLinkUnavailable(exc.code) from None
    except Exception:
        raise PositionLinkUnavailable(failure_code) from None
