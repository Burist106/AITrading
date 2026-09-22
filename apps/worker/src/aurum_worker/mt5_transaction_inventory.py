"""Count-only evidence availability, never normalized transaction observations."""

from __future__ import annotations

from collections.abc import Callable
from numbers import Integral
from typing import Literal, TypeGuard, cast

from pydantic import BaseModel, ConfigDict

MAX_INVENTORY_ROWS = 1000
InventoryLookback = Literal[7, 30]
TRANSACTION_FIELDS: dict[str, tuple[tuple[str, str | None], ...]] = {
    "positions": (("time", "time_msc"),),
    "active_orders": (("time_setup", "time_setup_msc"), ("time_expiration", None)),
    "historical_orders": (
        ("time_setup", "time_setup_msc"),
        ("time_done", "time_done_msc"),
    ),
    "historical_deals": (("time", "time_msc"),),
}


class FieldInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    nonzero: int = 0
    zero: int = 0
    missing: int = 0
    invalid: int = 0
    milliseconds_agree: int = 0
    milliseconds_missing_or_zero: int = 0
    milliseconds_invalid_or_disagree: int = 0


class RowInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    matching_symbol_rows: int
    other_symbol_rows: int
    fields: dict[str, FieldInventory]


class TransactionInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    status: Literal["inventory_observed"] = "inventory_observed"
    grants_eligibility: Literal[False] = False
    smoke_invoked: Literal[False] = False
    transaction_time_contract: Literal["unverified"] = "unverified"
    query_interpretation: Literal["unverified_utc_or_server_label_envelope"] = (
        "unverified_utc_or_server_label_envelope"
    )
    lookback_days: InventoryLookback = 7
    positions: RowInventory
    active_orders: RowInventory
    historical_orders: RowInventory
    historical_deals: RowInventory


def _valid_integer(value: object) -> TypeGuard[Integral]:
    # Validate shape only. A valid integer does not establish event time or UTC.
    return (
        isinstance(value, Integral) and not isinstance(value, bool) and int(value) >= 0
    )


def summarize_rows(
    rows: object,
    *,
    symbol: str,
    kind: str,
    field: Callable[[object, str], object],
) -> RowInventory:
    # Native MT5 returns tuples, not a streaming iterator. Reject unbounded input.
    if type(rows) not in {tuple, list}:
        raise ValueError("Inventory rows unavailable or over limit.")
    checked_rows = cast(tuple[object, ...] | list[object], rows)
    if len(checked_rows) > MAX_INVENTORY_ROWS:
        raise ValueError("Inventory rows unavailable or over limit.")
    counters = {
        name: FieldInventory().model_dump() for name, _ in TRANSACTION_FIELDS[kind]
    }
    matching = 0
    other = 0
    for row in checked_rows:
        reported_symbol = field(row, "symbol")
        if type(reported_symbol) is not str:
            raise ValueError("Inventory symbol shape invalid.")
        if reported_symbol != symbol:
            other += 1
            continue
        matching += 1
        for name, msc_name in TRANSACTION_FIELDS[kind]:
            value = field(row, name)
            counts = counters[name]
            if value is None:
                counts["missing"] += 1
            elif not _valid_integer(value):
                counts["invalid"] += 1
            elif value == 0:
                counts["zero"] += 1
            else:
                counts["nonzero"] += 1
            if msc_name is not None:
                msc = field(row, msc_name)
                if msc is None or (_valid_integer(msc) and int(msc) == 0):
                    counts["milliseconds_missing_or_zero"] += 1
                elif (
                    _valid_integer(value)
                    and _valid_integer(msc)
                    and int(msc) // 1000 == int(value)
                ):
                    counts["milliseconds_agree"] += 1
                else:
                    counts["milliseconds_invalid_or_disagree"] += 1
    return RowInventory(
        matching_symbol_rows=matching,
        other_symbol_rows=other,
        fields={name: FieldInventory(**counts) for name, counts in counters.items()},
    )
