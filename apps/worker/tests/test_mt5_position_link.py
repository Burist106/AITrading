from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from warnings import catch_warnings

import pytest

from aurum_worker.mt5_position_link import (
    DealRow,
    LinkKind,
    OrderRow,
    PositionLinkProbe,
    PositionLinkUnavailable,
    PositionReference,
    PositionRow,
    analyze_position_links,
    parse_link_rows,
)

SECONDS = 1_800_000_000
EPOCH = datetime(1970, 1, 1)


def native_row(**changes: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "symbol": "XAUUSD.demo",
        "ticket": 71,
        "identifier": 72,
        "position_id": 72,
        "order": 72,
        "time": SECONDS,
        "time_msc": SECONDS * 1000 + 123,
        "time_update": SECONDS,
        "time_update_msc": SECONDS * 1000 + 123,
        "time_setup": SECONDS - 10,
        "time_setup_msc": (SECONDS - 10) * 1000 + 100,
        "time_done": SECONDS,
        "time_done_msc": SECONDS * 1000 + 123,
        "entry": 0,
        "type": 0,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def field(row: object, name: str) -> object:
    return getattr(row, name, None)


def reference(ticket: int = 71) -> PositionReference:
    return PositionReference(
        ticket=ticket, opening_label=EPOCH + timedelta(seconds=SECONDS)
    )


def position(**changes: object) -> PositionRow:
    return parse_link_rows(
        (native_row(**changes),), kind="positions", symbol="XAUUSD.demo", field=field
    )[0]


def order(**changes: object) -> OrderRow:
    return parse_link_rows(
        (native_row(**({"ticket": 72} | changes)),),
        kind="orders",
        symbol="XAUUSD.demo",
        field=field,
    )[0]


def deal(**changes: object) -> DealRow:
    return parse_link_rows(
        (native_row(**({"ticket": 73} | changes)),),
        kind="deals",
        symbol="XAUUSD.demo",
        field=field,
    )[0]


def test_identifier_links_when_current_ticket_differs_and_report_is_safe() -> None:
    result = analyze_position_links(
        (position(),), (order(),), (deal(),), (reference(),)
    )
    assert result.status == "position_links_observed"
    assert (
        result.positions_observed
        == result.references_checked
        == result.linked_positions
        == 1
    )
    assert result.display_second_matches == result.position_deal_second_matches == 1
    assert result.position_deal_millisecond_matches == 1
    assert (
        result.order_setup_done_distinguishable
        == result.order_deal_time_order_matches
        == 1
    )
    assert result.collection_read_count == 6
    assert result.stable_snapshots is True
    assert result.transaction_time_contract == "unverified"
    assert result.grants_eligibility is result.smoke_invoked is False
    serialized = result.model_dump_json()
    for raw in ("1800000000", "XAUUSD", "identifier", "opening_label", "ticket"):
        assert raw not in serialized


def test_disagreeing_time_observations_are_counts_not_time_contract_proof() -> None:
    result = analyze_position_links(
        (
            position(
                time=SECONDS + 1,
                time_msc=(SECONDS + 1) * 1000,
                time_update=SECONDS + 1,
                time_update_msc=(SECONDS + 1) * 1000,
            ),
        ),
        (order(time_done_msc=SECONDS * 1000 + 100),),
        (deal(),),
        (reference(),),
    )
    assert result.display_second_matches == 0
    assert result.position_deal_second_matches == 0
    assert result.position_deal_millisecond_matches == 0
    assert result.order_deal_time_order_matches == 0


@pytest.mark.parametrize("side", [0, 1])
def test_simple_buy_and_sell_chains(side: int) -> None:
    result = analyze_position_links(
        (position(type=side),), (order(type=side),), (deal(type=side),), (reference(),)
    )
    assert result.linked_positions == 1


def test_same_second_milliseconds_do_not_distinguish_order_query_boundaries() -> None:
    result = analyze_position_links(
        (position(),),
        (order(time_setup=SECONDS, time_setup_msc=SECONDS * 1000 + 100),),
        (deal(),),
        (reference(),),
    )
    assert result.order_setup_done_distinguishable == 0
    assert result.order_deal_time_order_matches == 1


def test_display_label_compares_exact_raw_second_without_timezone_shift() -> None:
    shifted_reference = PositionReference(
        ticket=71, opening_label=reference().opening_label - timedelta(hours=3)
    )
    result = analyze_position_links(
        (position(),), (order(),), (deal(),), (shifted_reference,)
    )
    assert result.display_second_matches == 0
    assert result.position_deal_second_matches == 1


def test_ten_unique_references_and_chains_are_counted_independently() -> None:
    positions = tuple(
        position(ticket=101 + index, identifier=201 + index) for index in range(10)
    )
    orders = tuple(
        order(ticket=201 + index, position_id=201 + index) for index in range(10)
    )
    deals = tuple(
        deal(ticket=301 + index, order=201 + index, position_id=201 + index)
        for index in range(10)
    )
    references = tuple(reference(101 + index) for index in range(10))
    result = analyze_position_links(positions, orders, deals, references)
    assert (
        result.references_checked
        == result.linked_positions
        == result.display_second_matches
        == 10
    )


def test_same_second_but_different_position_deal_milliseconds_is_observable() -> None:
    result = analyze_position_links(
        (position(),),
        (order(),),
        (deal(time_msc=SECONDS * 1000 + 122),),
        (reference(),),
    )
    assert result.position_deal_second_matches == 1
    assert result.position_deal_millisecond_matches == 0


@pytest.mark.parametrize(
    "scenario",
    [
        "missing_position",
        "missing_order",
        "missing_deal",
        "wrong_position_key",
        "wrong_order_key",
        "addition_not_origin",
        "partial_fill",
        "second_opening",
        "close",
        "reversal",
        "close_by",
        "order_direction",
        "deal_direction",
        "duplicate_reference",
        "duplicate_identifier",
        "additional_order",
        "orphan_order",
    ],
)
def test_missing_ambiguous_or_unsupported_chains_fail_closed(scenario: str) -> None:
    positions: tuple[PositionRow, ...] = (position(),)
    orders: tuple[OrderRow, ...] = (order(),)
    deals: tuple[DealRow, ...] = (deal(),)
    references: tuple[PositionReference, ...] = (reference(),)
    if scenario == "missing_position":
        positions = ()
    elif scenario == "missing_order":
        orders = ()
    elif scenario == "missing_deal":
        deals = ()
    elif scenario == "wrong_position_key":
        orders, deals = (order(position_id=71),), (deal(position_id=71),)
    elif scenario == "wrong_order_key":
        deals = (deal(order=74),)
    elif scenario == "addition_not_origin":
        orders, deals = (order(ticket=74),), (deal(order=74),)
    elif scenario in {"partial_fill", "second_opening"}:
        deals += (deal(ticket=74),)
    elif scenario in {"close", "reversal", "close_by"}:
        deals += (
            deal(ticket=74, entry={"close": 1, "reversal": 2, "close_by": 3}[scenario]),
        )
    elif scenario == "order_direction":
        orders = (order(type=1),)
    elif scenario == "deal_direction":
        deals = (deal(type=1),)
    elif scenario == "duplicate_reference":
        references += references
    elif scenario == "duplicate_identifier":
        positions += (position(ticket=74),)
    elif scenario == "additional_order":
        orders += (order(ticket=74),)
    elif scenario == "orphan_order":
        deals += (deal(ticket=74, position_id=75),)
    with pytest.raises(PositionLinkUnavailable) as failure:
        analyze_position_links(positions, orders, deals, references)
    expected = {
        "missing_position": "LINK_POSITION_NOT_FOUND",
        "missing_order": "LINK_ORDER_UNAVAILABLE",
        "missing_deal": "LINK_DEAL_UNAVAILABLE",
        "partial_fill": "LINK_DEAL_UNAVAILABLE",
        "second_opening": "LINK_DEAL_UNAVAILABLE",
        "close": "LINK_DEAL_UNAVAILABLE",
        "reversal": "LINK_DEAL_UNAVAILABLE",
        "close_by": "LINK_DEAL_UNAVAILABLE",
        "duplicate_reference": "LINK_REFERENCE_INVALID",
        "duplicate_identifier": "LINK_SNAPSHOT_INVALID",
        "additional_order": "LINK_ORDER_UNAVAILABLE",
        "orphan_order": "LINK_DEAL_UNAVAILABLE",
    }.get(scenario, "LINK_CHAIN_UNSUPPORTED")
    assert failure.value.code == expected
    assert str(failure.value) == "Position link observation unavailable."


def test_unrelated_canceled_order_without_position_is_permitted() -> None:
    result = analyze_position_links(
        (position(),),
        (order(), order(ticket=74, position_id=0)),
        (deal(),),
        (reference(),),
    )
    assert result.linked_positions == 1


@pytest.mark.parametrize("kind", ["positions", "orders", "deals"])
@pytest.mark.parametrize("bad", [None, True, False, 0, -1, 1.0, "1", 2**63])
def test_identity_requires_bounded_nonboolean_integers(
    kind: LinkKind, bad: object
) -> None:
    with pytest.raises(ValueError, match="Position link rows invalid"):
        parse_link_rows(
            (native_row(ticket=bad),), kind=kind, symbol="XAUUSD.demo", field=field
        )


@pytest.mark.parametrize(
    "kind,name",
    [
        ("positions", "identifier"),
        ("positions", "time"),
        ("positions", "time_msc"),
        ("positions", "time_update"),
        ("positions", "time_update_msc"),
        ("positions", "type"),
        ("orders", "position_id"),
        ("orders", "time_setup"),
        ("orders", "time_setup_msc"),
        ("orders", "time_done"),
        ("orders", "time_done_msc"),
        ("orders", "type"),
        ("deals", "position_id"),
        ("deals", "order"),
        ("deals", "time"),
        ("deals", "time_msc"),
        ("deals", "entry"),
        ("deals", "type"),
    ],
)
@pytest.mark.parametrize("bad", [None, True, False, -1, 1.0, "1", 2**63])
def test_every_numeric_field_rejects_invalid_scalars(
    kind: LinkKind, name: str, bad: object
) -> None:
    with pytest.raises(ValueError):
        parse_link_rows(
            (native_row(**{name: bad}),), kind=kind, symbol="XAUUSD.demo", field=field
        )


@pytest.mark.parametrize(
    "kind,changes",
    [
        ("positions", {"identifier": 0}),
        ("positions", {"type": 2}),
        ("positions", {"time_msc": SECONDS * 1000 - 1}),
        ("positions", {"time_update_msc": SECONDS * 1000 + 122}),
        ("positions", {"time_update": True}),
        ("positions", {"time": 2**60, "time_msc": 2**60 * 1000}),
        ("orders", {"position_id": -1}),
        ("orders", {"type": 9}),
        ("orders", {"time_done": SECONDS - 11, "time_done_msc": (SECONDS - 11) * 1000}),
        ("orders", {"time_setup_msc": (SECONDS - 9) * 1000}),
        ("deals", {"position_id": 0}),
        ("deals", {"order": 0}),
        ("deals", {"entry": 4}),
        ("deals", {"entry": True}),
        ("deals", {"type": 2}),
        ("deals", {"type": False}),
        ("deals", {"time": "1800000000"}),
    ],
)
def test_invalid_fields_and_time_pairs_fail(
    kind: LinkKind, changes: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        parse_link_rows(
            (native_row(**changes),), kind=kind, symbol="XAUUSD.demo", field=field
        )


def test_parser_filters_exact_symbol_sorts_and_bounds_snapshot() -> None:
    rows = parse_link_rows(
        (
            native_row(ticket=75),
            SimpleNamespace(symbol="XAUUSD"),
            native_row(ticket=73),
        ),
        kind="deals",
        symbol="XAUUSD.demo",
        field=field,
    )
    assert [row.ticket for row in rows] == [73, 75]
    invalid_collections: tuple[object, ...] = (
        None,
        {},
        "secret",
        iter([1]),
        (native_row(), native_row()),
    )
    for value in invalid_collections:
        with pytest.raises(ValueError):
            parse_link_rows(value, kind="deals", symbol="XAUUSD.demo", field=field)
    thousand = [native_row(ticket=index + 1) for index in range(1000)]
    assert (
        len(parse_link_rows(thousand, kind="deals", symbol="XAUUSD.demo", field=field))
        == 1000
    )
    with pytest.raises(ValueError):
        parse_link_rows(
            thousand + [native_row(ticket=1001)],
            kind="deals",
            symbol="XAUUSD.demo",
            field=field,
        )


def test_parser_rejects_duplicate_lifetime_identifiers_and_invalid_symbols() -> None:
    with pytest.raises(ValueError):
        parse_link_rows(
            (native_row(), native_row(ticket=74)),
            kind="positions",
            symbol="XAUUSD.demo",
            field=field,
        )
    for rows, symbol in (((native_row(symbol=None),), "XAUUSD.demo"), ((), "")):
        with pytest.raises(ValueError):
            parse_link_rows(rows, kind="positions", symbol=symbol, field=field)


def test_parser_reads_only_allowlisted_fields() -> None:
    observed: list[str] = []

    def tracking_field(row: object, name: str) -> object:
        observed.append(name)
        return field(row, name)

    parse_link_rows(
        (native_row(),), kind="positions", symbol="XAUUSD.demo", field=tracking_field
    )
    assert set(observed) == {
        "symbol",
        "ticket",
        "identifier",
        "time",
        "time_msc",
        "time_update",
        "time_update_msc",
        "type",
    }


def test_native_accessor_failure_and_internal_representations_hide_input() -> None:
    def broken(row: object, name: str) -> object:
        raise RuntimeError("private-input-value")

    with pytest.raises(ValueError) as failure:
        parse_link_rows(
            (native_row(),), kind="positions", symbol="XAUUSD.demo", field=broken
        )
    assert str(failure.value) == "Position link rows invalid."
    assert failure.value.__suppress_context__ is True
    for row in (position(), order(), deal(), reference()):
        assert "1800000000" not in repr(row)
        assert "ticket=" not in repr(row)
    with pytest.raises(FrozenInstanceError):
        position().ticket = 5  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"ticket": True},
        {"ticket": 0},
        {"ticket": 2**63},
        {"ticket": "71"},
        {"opening_label": EPOCH.replace(tzinfo=UTC)},
        {"opening_label": EPOCH.replace(microsecond=1)},
        {"opening_label": "private-reference-value"},
    ],
)
def test_reference_is_strict_naive_whole_second_and_private(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError) as failure:
        PositionReference.model_validate(reference().model_dump() | changes)
    assert "private-reference-value" not in str(failure.value)


def test_report_relationships_strict_literals_and_no_extra_data() -> None:
    result = analyze_position_links(
        (position(),), (order(),), (deal(),), (reference(),)
    )
    for changes in (
        {"grants_eligibility": True},
        {"grants_eligibility": 0},
        {"smoke_invoked": 0},
        {"stable_snapshots": False},
        {"stable_snapshots": 1},
        {"collection_read_count": True},
        {"collection_read_count": 5},
        {"references_checked": 0},
        {"references_checked": 11},
        {"linked_positions": 0},
        {"positions_observed": 0},
        {"display_second_matches": 2},
        {"position_deal_second_matches": True},
        {"order_deal_time_order_matches": -1},
        {"ticket": 71},
        {"transaction_time_contract": "verified"},
    ):
        with pytest.raises(ValueError):
            PositionLinkProbe.model_validate(result.model_dump() | changes)
    with pytest.raises(ValueError):
        result.linked_positions = 2


def test_reference_bounds_and_direct_row_tampering_fail_closed() -> None:
    for references in ((), (reference(),) * 11):
        with pytest.raises(ValueError):
            analyze_position_links((position(),), (order(),), (deal(),), references)
    with pytest.raises(ValueError):
        analyze_position_links(
            (replace(position(), identifier=0),), (order(),), (deal(),), (reference(),)
        )


def test_malformed_reference_cannot_leak_through_serialization_warnings() -> None:
    malformed = PositionReference.model_construct(
        ticket="fictional-private-reference", opening_label=EPOCH
    )
    with catch_warnings(record=True) as emitted:
        with pytest.raises(PositionLinkUnavailable) as failure:
            analyze_position_links((position(),), (order(),), (deal(),), (malformed,))
    assert emitted == []
    assert str(failure.value) == "Position link observation unavailable."
    assert failure.value.code == "LINK_REFERENCE_INVALID"


@pytest.mark.parametrize("code", [None, True, 1, [], "fictional-private-code"])
def test_unavailable_code_rejects_nonallowlisted_values_without_input(
    code: object,
) -> None:
    with pytest.raises(ValueError) as failure:
        PositionLinkUnavailable(code)  # type: ignore[arg-type]
    assert str(failure.value) == "Position link observation unavailable."
    assert "fictional-private-code" not in repr(failure.value)


def test_direct_invalid_snapshot_has_only_safe_classification() -> None:
    with pytest.raises(PositionLinkUnavailable) as failure:
        analyze_position_links(
            (replace(position(), identifier=0),), (order(),), (deal(),), (reference(),)
        )
    assert failure.value.code == "LINK_SNAPSHOT_INVALID"
    assert failure.value.args == ("Position link observation unavailable.",)
