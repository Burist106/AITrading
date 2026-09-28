from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

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

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
SECONDS = 1_800_000_000


def native_row(**changes: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "symbol": "XAUUSD",
        "ticket": 71,
        "time": SECONDS,
        "time_msc": SECONDS * 1000 + 123,
        "order": 72,
        "time_setup": SECONDS - 10,
        "time_setup_msc": (SECONDS - 10) * 1000 + 100,
        "time_done": SECONDS,
        "time_done_msc": SECONDS * 1000 + 123,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def field(row: object, name: str) -> object:
    return getattr(row, name, None)


def parse(rows: object, kind: str = "deals") -> tuple[ProbeRow, ...]:
    return parse_probe_rows(rows, kind=kind, symbol="XAUUSD", field=field)  # type: ignore[arg-type]


def test_only_relevant_fields_are_read_and_other_symbols_filtered() -> None:
    fields: list[str] = []

    def tracking_field(row: object, name: str) -> object:
        fields.append(name)
        return field(row, name)

    result = parse_probe_rows(
        (native_row(), SimpleNamespace(symbol="OTHER")),
        kind="deals",
        symbol="XAUUSD",
        field=tracking_field,
    )
    assert result == (ProbeRow(71, SECONDS, SECONDS * 1000 + 123, None, 72),)
    assert set(fields) == {"symbol", "ticket", "time", "time_msc", "order"}
    assert "71" not in repr(result[0])


def test_order_rows_use_completion_and_validate_setup_pair() -> None:
    result = parse((native_row(),), "orders")
    assert result[0].event_seconds == SECONDS
    assert result[0].setup_seconds == SECONDS - 10
    assert result[0].linked_order is None
    assert result[0].setup_milliseconds == (SECONDS - 10) * 1000 + 100
    changed = parse((native_row(time_setup_msc=(SECONDS - 10) * 1000 + 101),), "orders")
    assert result != changed


@pytest.mark.parametrize("bad", [None, True, False, 0, -1, 1.0, "1"])
@pytest.mark.parametrize("name", ["ticket", "time", "time_msc", "order"])
def test_deal_fields_require_positive_nonboolean_integers(
    bad: object, name: str
) -> None:
    with pytest.raises(ValueError, match="Probe rows invalid"):
        parse((native_row(**{name: bad}),))


@pytest.mark.parametrize(
    "changes",
    [
        {"time_msc": SECONDS * 1000 - 1},
        {"time_setup": True},
        {"time_setup_msc": 0},
        {"time_setup_msc": (SECONDS - 9) * 1000},
        {"time_setup": SECONDS + 1, "time_setup_msc": (SECONDS + 1) * 1000},
        {"time_setup": SECONDS, "time_setup_msc": SECONDS * 1000 + 124},
        {"time_done_msc": SECONDS * 1000 - 1},
    ],
)
def test_inconsistent_or_reversed_time_pairs_rejected(
    changes: dict[str, object],
) -> None:
    kind = "deals" if "time_msc" in changes else "orders"
    with pytest.raises(ValueError, match="Probe rows invalid"):
        parse((native_row(**changes),), kind)


@pytest.mark.parametrize("rows", [None, {}, "private-value", (None,)])
def test_invalid_collection_shapes_rejected(rows: object) -> None:
    with pytest.raises(ValueError, match="Probe rows invalid"):
        parse(rows)


def test_iterator_not_consumed() -> None:
    consumed: list[bool] = []

    def rows() -> Iterator[object]:
        consumed.append(True)
        yield None

    with pytest.raises(ValueError, match="Probe rows invalid"):
        parse(rows())
    assert consumed == []


def test_exact_row_cap_accepted_over_cap_and_duplicates_rejected() -> None:
    rows = [native_row(ticket=index + 1) for index in range(1000)]
    assert len(parse(rows)) == 1000
    with pytest.raises(ValueError):
        parse(rows + [native_row(ticket=1001)])
    with pytest.raises(ValueError):
        parse((native_row(), native_row()))


def test_parser_hides_callback_error_and_rejects_invalid_symbol_kind() -> None:
    def bad_field(row: object, name: str) -> object:
        raise RuntimeError("private-value")

    with pytest.raises(ValueError) as raised:
        parse_probe_rows(
            (native_row(),), kind="deals", symbol="XAUUSD", field=bad_field
        )
    assert str(raised.value) == "Probe rows invalid."
    assert raised.value.__suppress_context__ is True
    for rows, kind in (((native_row(symbol=123),), "deals"), ((), "bad-kind")):
        with pytest.raises(ValueError):
            parse(rows, kind)


def test_selects_latest_deal_but_distinguishable_order_when_available() -> None:
    first = ProbeRow(1, SECONDS, SECONDS * 1000, SECONDS - 1, None)
    latest = ProbeRow(2, SECONDS + 1, (SECONDS + 1) * 1000, SECONDS + 1, None)
    assert select_anchor((latest, first), kind="orders") == first
    assert select_anchor((latest, first), kind="deals") == latest
    assert select_anchor((latest,), kind="orders") == latest
    with pytest.raises(ValueError):
        select_anchor((), kind="deals")


def test_query_matrix_has_exact_ten_integer_and_datetime_hypotheses() -> None:
    anchor = ProbeRow(71, SECONDS, SECONDS * 1000 + 123, None, 72)
    plans = build_probe_queries(anchor, kind="deals")
    assert len(plans) == 10
    assert len({plan.code for plan in plans}) == 10
    assert [(plans[i].start, plans[i].end) for i in (0, 2, 4, 5, 6, 7)] == [
        (SECONDS - 1, SECONDS + 1),
        (SECONDS - 10801, SECONDS - 10799),
        (SECONDS - 1, SECONDS),
        (SECONDS, SECONDS),
        (SECONDS, SECONDS + 1),
        (SECONDS + 1, SECONDS + 2),
    ]
    assert plans[1].start == EPOCH + timedelta(seconds=SECONDS - 1)
    assert plans[3].start == EPOCH + timedelta(seconds=SECONDS - 10801)
    assert plans[8].start == EPOCH + timedelta(milliseconds=SECONDS * 1000 + 122)
    assert plans[9].start == EPOCH + timedelta(milliseconds=SECONDS * 1000 + 123)
    assert plans[8].start == plans[8].end
    assert plans[9].start == plans[9].end
    assert str(SECONDS) not in repr(plans)


def test_order_setup_query_replaces_only_redundant_fourth_probe() -> None:
    distinguishable = ProbeRow(1, SECONDS, SECONDS * 1000 + 123, SECONDS - 5, None)
    plans = build_probe_queries(distinguishable, kind="orders")
    assert len(plans) == 10
    assert plans[3].code == "integer_setup_exact"
    assert plans[3].start == plans[3].end == SECONDS - 5
    same_second = ProbeRow(1, SECONDS, SECONDS * 1000 + 123, SECONDS, None)
    assert (
        build_probe_queries(same_second, kind="orders")[3].code
        == "datetime_minus_three_hours_window"
    )


def test_reference_requires_aware_narrow_interval_and_normalizes_utc() -> None:
    thai = timezone(timedelta(hours=7))
    start = datetime(2026, 9, 28, 12, tzinfo=thai)
    reference = OperatorTimeWindow(start_at=start, end_at=start + timedelta(hours=1))
    assert reference.start_at == datetime(2026, 9, 28, 5, tzinfo=UTC)
    assert reference.start_at.tzinfo == UTC
    assert "2026" not in repr(reference)
    for end in (
        start,
        start - timedelta(seconds=1),
        start + timedelta(hours=1, seconds=1),
    ):
        with pytest.raises(ValueError):
            OperatorTimeWindow(start_at=start, end_at=end)
    with pytest.raises(ValueError):
        OperatorTimeWindow(start_at=start.replace(tzinfo=None), end_at=start)
    with pytest.raises(ValueError):
        OperatorTimeWindow.model_validate(
            {"start_at": "2026-09-28T12:00:00+07:00", "end_at": start}
        )
    with pytest.raises(ValueError):
        reference.start_at = start


def test_reference_counts_compare_hypotheses_without_returning_raw_times() -> None:
    rows = (ProbeRow(71, SECONDS, SECONDS * 1000 + 123, None, 72),)
    raw = EPOCH + timedelta(seconds=SECONDS)
    assert reference_match_counts(rows, None) == (None, None)
    assert reference_match_counts(
        rows, OperatorTimeWindow(start_at=raw, end_at=raw + timedelta(seconds=1))
    ) == (1, 0)
    shifted = raw - timedelta(hours=3)
    assert reference_match_counts(
        rows,
        OperatorTimeWindow(start_at=shifted, end_at=shifted + timedelta(seconds=1)),
    ) == (0, 1)
    exact = raw + timedelta(milliseconds=123)
    assert reference_match_counts(
        rows,
        OperatorTimeWindow(start_at=exact, end_at=exact + timedelta(milliseconds=1)),
    ) == (1, 0)


def collection() -> CollectionTimeProbe:
    return CollectionTimeProbe(
        matching_rows=1,
        selected_event_has_subsecond=True,
        setup_done_distinguishable=False,
        as_utc_reference_matches=None,
        minus_three_hours_reference_matches=None,
        queries=(
            QueryProbeResult(
                code="integer_event_window", target_present=True, matching_rows=1
            ),
        ),
    )


def test_report_is_strict_count_only_frozen_and_cannot_unlock_eligibility() -> None:
    result = TransactionTimeProbe(
        history_query_count=24,
        reference_supplied=False,
        stable_snapshots=True,
        orders=collection(),
        deals=collection(),
    )
    assert result.transaction_time_contract == "unverified"
    assert result.grants_eligibility is False
    assert result.smoke_invoked is False
    assert str(SECONDS) not in result.model_dump_json()
    for changes in (
        {"grants_eligibility": True},
        {"grants_eligibility": 0},
        {"smoke_invoked": True},
        {"smoke_invoked": 0},
        {"transaction_time_contract": "verified"},
        {"history_query_count": 25},
        {"history_query_count": True},
        {"ticket": 71},
    ):
        with pytest.raises(ValueError):
            TransactionTimeProbe.model_validate(result.model_dump() | changes)
    with pytest.raises(ValueError):
        QueryProbeResult(code="private-raw-value", target_present=True, matching_rows=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        QueryProbeResult(
            code="integer_event_window", target_present=True, matching_rows=-1
        )
