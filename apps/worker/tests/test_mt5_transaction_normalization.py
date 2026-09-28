"""Constructed native-row regressions; never connects to a real terminal."""

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest
from mt5_factories import NOW, confirmed_binding
from test_mt5_market_policy import market_adapter
from test_mt5_native import NativeModuleFake, native_adapter
from test_mt5_reconciliation import confirmed_state

from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    HealthState,
    HistoryQueryResultState,
    HistoryRequest,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ObservationModel,
)
from aurum_worker.polling import ReadOnlyPollingService
from aurum_worker.reconciliation import ReadOnlyReconciliationService

Kind = Literal["positions", "orders", "order_history", "deals"]
NativeFixture = tuple[MetaTrader5ReadAdapter, NativeModuleFake]
KINDS: tuple[Kind, ...] = ("positions", "orders", "order_history", "deals")
SECOND = int(NOW.timestamp()) - 120
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
REQUEST = HistoryRequest(start_at=NOW - timedelta(hours=1), end_at=NOW)
TIME_PAIRS: tuple[tuple[Kind, str, str], ...] = (
    ("positions", "time", "time_msc"),
    ("orders", "time_setup", "time_setup_msc"),
    ("order_history", "time_setup", "time_setup_msc"),
    ("order_history", "time_done", "time_done_msc"),
    ("deals", "time", "time_msc"),
)


def _raw_row(**updates: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "ticket": 1101,
        "position_id": 1201,
        "order": 1101,
        "symbol": "XAUUSD",
        "type": 0,
        "state": 1,
        "type_time": 0,
        "volume_initial": 0.01,
        "volume_current": 0.01,
        "volume": 0.01,
        "price_open": 2345.1,
        "price_current": 2346.1,
        "price": 2345.1,
        "sl": 2335.1,
        "tp": 2365.1,
        "profit": 0,
        "commission": 0,
        "swap": 0,
        "time": SECOND,
        "time_msc": SECOND * 1_000 + 123,
        "time_setup": SECOND - 30,
        "time_setup_msc": (SECOND - 30) * 1_000 + 17,
        "time_done": SECOND,
        "time_done_msc": SECOND * 1_000 + 123,
        "time_expiration": 0,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _set_rows(module: NativeModuleFake, kind: Kind, row: SimpleNamespace) -> None:
    if kind == "positions":
        module.position_result = (row,)
    elif kind == "orders":
        module.order_result = (row,)
    elif kind == "order_history":
        module.order_history_result = (row,)
    else:
        module.deal_history_result = (row,)


def _read(adapter: MetaTrader5ReadAdapter, kind: Kind) -> Sequence[ObservationModel]:
    if kind == "positions":
        return adapter.get_open_positions(trace_id="transaction-normalization")
    if kind == "orders":
        return adapter.get_active_orders(trace_id="transaction-normalization")
    if kind == "order_history":
        return adapter.get_order_history(REQUEST, trace_id="transaction-normalization")
    return adapter.get_deal_history(REQUEST, trace_id="transaction-normalization")


def _assert_invalid(adapter: MetaTrader5ReadAdapter, kind: Kind) -> None:
    with pytest.raises(Mt5ReadFailure) as raised:
        _read(adapter, kind)
    expected = (
        Mt5ReasonCode.HISTORY_QUERY_FAILED
        if kind in {"order_history", "deals"}
        else Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    )
    assert raised.value.error.reason_code is expected


@pytest.fixture
def connected_native(tmp_path: Path) -> Iterator[NativeFixture]:
    module = NativeModuleFake()
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="transaction-normalization")
    try:
        yield adapter, module
    finally:
        adapter.disconnect()


@pytest.mark.parametrize(
    ("kind", "event_field", "expected_milliseconds"),
    [
        ("positions", "opened_at", SECOND * 1_000 + 123),
        ("orders", "setup_at", (SECOND - 30) * 1_000 + 17),
        ("order_history", "setup_at", (SECOND - 30) * 1_000 + 17),
        ("order_history", "completed_at", SECOND * 1_000 + 123),
        ("deals", "occurred_at", SECOND * 1_000 + 123),
    ],
)
def test_transaction_event_retains_exact_milliseconds(
    connected_native: NativeFixture,
    kind: Kind,
    event_field: str,
    expected_milliseconds: int,
) -> None:
    adapter, module = connected_native
    _set_rows(module, kind, _raw_row())
    result = _read(adapter, kind)[0]
    assert getattr(result, event_field) == EPOCH + timedelta(
        milliseconds=expected_milliseconds
    )


@pytest.mark.parametrize(("kind", "seconds_field", "milliseconds_field"), TIME_PAIRS)
@pytest.mark.parametrize("milliseconds", [False, True])
@pytest.mark.parametrize("value", [None, False, True, "1700000000", 1700000000.0])
def test_transaction_time_fields_do_not_coerce_invalid_scalars(
    connected_native: NativeFixture,
    kind: Kind,
    seconds_field: str,
    milliseconds_field: str,
    milliseconds: bool,
    value: object,
) -> None:
    adapter, module = connected_native
    field = milliseconds_field if milliseconds else seconds_field
    _set_rows(module, kind, _raw_row(**{field: value}))
    _assert_invalid(adapter, kind)


@pytest.mark.parametrize(("kind", "seconds_field", "milliseconds_field"), TIME_PAIRS)
@pytest.mark.parametrize("milliseconds", [False, True])
def test_transaction_time_fields_must_be_present(
    connected_native: NativeFixture,
    kind: Kind,
    seconds_field: str,
    milliseconds_field: str,
    milliseconds: bool,
) -> None:
    adapter, module = connected_native
    row = _raw_row()
    delattr(row, milliseconds_field if milliseconds else seconds_field)
    _set_rows(module, kind, row)
    _assert_invalid(adapter, kind)


@pytest.mark.parametrize(("kind", "seconds_field", "milliseconds_field"), TIME_PAIRS)
@pytest.mark.parametrize(
    ("seconds", "milliseconds"),
    [
        (SECOND, SECOND * 1_000 - 1),
        (SECOND, (SECOND + 1) * 1_000),
        (SECOND, 0),
        (0, SECOND * 1_000),
        (-1, -1_000),
        (2**63, 2**63 * 1_000),
    ],
)
def test_transaction_pair_must_agree_and_be_representable(
    connected_native: NativeFixture,
    kind: Kind,
    seconds_field: str,
    milliseconds_field: str,
    seconds: int,
    milliseconds: int,
) -> None:
    adapter, module = connected_native
    _set_rows(
        module,
        kind,
        _raw_row(**{seconds_field: seconds, milliseconds_field: milliseconds}),
    )
    _assert_invalid(adapter, kind)


@pytest.mark.parametrize(("kind", "seconds_field", "milliseconds_field"), TIME_PAIRS)
@pytest.mark.parametrize("delta_milliseconds", [30_000, 30_001])
def test_transaction_event_uses_existing_future_drift_boundary(
    connected_native: NativeFixture,
    kind: Kind,
    seconds_field: str,
    milliseconds_field: str,
    delta_milliseconds: int,
) -> None:
    adapter, module = connected_native
    event_milliseconds = int(NOW.timestamp()) * 1_000 + delta_milliseconds
    row = _raw_row(
        **{
            seconds_field: event_milliseconds // 1_000,
            milliseconds_field: event_milliseconds,
        }
    )
    if kind == "order_history" and seconds_field == "time_setup":
        row.time_done = 0
        row.time_done_msc = 0
    _set_rows(module, kind, row)
    if delta_milliseconds == 30_000:
        assert len(_read(adapter, kind)) == 1
    else:
        _assert_invalid(adapter, kind)


@pytest.mark.parametrize("value", [None, False, "", [], {}, "0", 0.0, -1])
def test_active_expiration_does_not_treat_invalid_values_as_gtc(
    connected_native: NativeFixture, value: object
) -> None:
    adapter, module = connected_native
    _set_rows(module, "orders", _raw_row(time_expiration=value))
    _assert_invalid(adapter, "orders")


@pytest.mark.parametrize("field", ["time_expiration", "type_time"])
def test_active_expiration_requires_explicit_native_fields(
    connected_native: NativeFixture, field: str
) -> None:
    adapter, module = connected_native
    row = _raw_row()
    delattr(row, field)
    _set_rows(module, "orders", row)
    _assert_invalid(adapter, "orders")


@pytest.mark.parametrize("type_time", [None, False, "0", 0.0, 1, 3, 4, -1])
def test_active_expiration_rejects_invalid_or_unrepresented_modes(
    connected_native: NativeFixture, type_time: object
) -> None:
    adapter, module = connected_native
    _set_rows(module, "orders", _raw_row(type_time=type_time))
    _assert_invalid(adapter, "orders")


def test_active_gtc_accepts_only_explicit_zero_expiration(
    connected_native: NativeFixture,
) -> None:
    adapter, module = connected_native
    _set_rows(module, "orders", _raw_row(type_time=0, time_expiration=0))
    assert adapter.get_active_orders(trace_id="gtc")[0].expiration_at is None
    _set_rows(module, "orders", _raw_row(type_time=0, time_expiration=SECOND))
    _assert_invalid(adapter, "orders")


def test_active_specified_expiration_can_be_future(
    connected_native: NativeFixture,
) -> None:
    adapter, module = connected_native
    expiration = int(NOW.timestamp()) + 86_400
    _set_rows(module, "orders", _raw_row(type_time=2, time_expiration=expiration))
    result = adapter.get_active_orders(trace_id="specified")[0]
    assert result.expiration_at == NOW + timedelta(days=1)


@pytest.mark.parametrize("expiration", [0, SECOND - 31, SECOND - 30])
def test_active_specified_expiration_cannot_precede_precise_setup(
    connected_native: NativeFixture, expiration: int
) -> None:
    adapter, module = connected_native
    _set_rows(module, "orders", _raw_row(type_time=2, time_expiration=expiration))
    _assert_invalid(adapter, "orders")


@pytest.mark.parametrize("completion_offset", [-1, 0, 1])
def test_historical_completion_ordering_uses_milliseconds(
    connected_native: NativeFixture, completion_offset: int
) -> None:
    adapter, module = connected_native
    _set_rows(
        module,
        "order_history",
        _raw_row(
            time_setup=SECOND,
            time_setup_msc=SECOND * 1_000 + 123,
            time_done=SECOND,
            time_done_msc=SECOND * 1_000 + 123 + completion_offset,
        ),
    )
    if completion_offset < 0:
        _assert_invalid(adapter, "order_history")
    else:
        assert len(_read(adapter, "order_history")) == 1


def test_historical_completion_zero_pair_remains_explicitly_unavailable(
    connected_native: NativeFixture,
) -> None:
    adapter, module = connected_native
    _set_rows(module, "order_history", _raw_row(time_done=0, time_done_msc=0))
    result = adapter.get_order_history(REQUEST, trace_id="zero-completion")[0]
    assert result.completed_at is None
    service = ReadOnlyReconciliationService(
        adapter,
        InMemoryMt5ObservationPersistence(),
        Mt5WorkerConfig(),
        clock=lambda: NOW,
    )
    _, evidence = service._order_history(REQUEST, "zero-completion")
    assert evidence.result_state is HistoryQueryResultState.WINDOW_INCOMPLETE
    assert evidence.returned_count == 1
    assert evidence.earliest_returned_at is None
    assert evidence.latest_returned_at is None


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("positions", "type"),
        ("orders", "type"),
        ("orders", "state"),
        ("order_history", "type"),
        ("order_history", "state"),
        ("deals", "type"),
    ],
)
@pytest.mark.parametrize("value", [None, False, True, 0.0, "0"])
def test_transaction_codes_do_not_coerce_malformed_scalars(
    connected_native: NativeFixture, kind: Kind, field: str, value: object
) -> None:
    adapter, module = connected_native
    _set_rows(module, kind, _raw_row(**{field: value}))
    _assert_invalid(adapter, kind)


@pytest.mark.parametrize("kind", ["order_history", "deals"])
@pytest.mark.parametrize("offset_milliseconds", [0, 1])
def test_history_evidence_preserves_endpoint_milliseconds(
    connected_native: NativeFixture, kind: Kind, offset_milliseconds: int
) -> None:
    adapter, module = connected_native
    seconds = int(NOW.timestamp())
    _set_rows(
        module,
        kind,
        _raw_row(
            time=seconds,
            time_msc=seconds * 1_000 + offset_milliseconds,
            time_done=seconds,
            time_done_msc=seconds * 1_000 + offset_milliseconds,
        ),
    )
    service = ReadOnlyReconciliationService(
        adapter,
        InMemoryMt5ObservationPersistence(),
        Mt5WorkerConfig(),
        clock=lambda: NOW,
    )
    if kind == "order_history":
        _, evidence = service._order_history(REQUEST, "history-edge")
    else:
        _, evidence = service._deal_history(REQUEST, "history-edge")
    expected_state = (
        HistoryQueryResultState.QUERY_SUCCEEDED
        if offset_milliseconds == 0
        else HistoryQueryResultState.WINDOW_INCOMPLETE
    )
    assert evidence.result_state is expected_state
    assert evidence.returned_count == 1
    assert evidence.latest_returned_at == NOW + timedelta(
        milliseconds=offset_milliseconds
    )


@pytest.mark.parametrize("kind", KINDS)
def test_native_numpy_transaction_integers_preserve_exact_values(
    connected_native: NativeFixture, kind: Kind
) -> None:
    numpy = pytest.importorskip("numpy")
    adapter, module = connected_native
    row = _raw_row()
    for key, value in vars(row).items():
        if type(value) is int:
            setattr(row, key, numpy.int64(value))
    _set_rows(module, kind, row)
    result = _read(adapter, kind)[0]
    field = {
        "positions": "opened_at",
        "orders": "setup_at",
        "order_history": "completed_at",
        "deals": "occurred_at",
    }[kind]
    expected = (
        EPOCH + timedelta(seconds=SECOND - 30, milliseconds=17)
        if kind == "orders"
        else EPOCH + timedelta(seconds=SECOND, milliseconds=123)
    )
    assert getattr(result, field) == expected


@pytest.mark.parametrize("kind", KINDS)
def test_market_only_gate_precedes_nonempty_transaction_normalization(
    tmp_path: Path, kind: Kind
) -> None:
    module = NativeModuleFake()
    _set_rows(module, kind, _raw_row(time=False, time_setup=False))
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            _read(adapter, kind)
        assert raised.value.error.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        assert not set(module.calls) & {
            "positions_get",
            "orders_get",
            "history_orders_get",
            "history_deals_get",
        }


def _native_services(
    adapter: MetaTrader5ReadAdapter, kind: Kind
) -> tuple[
    ReadOnlyReconciliationService,
    ReadOnlyPollingService,
    InMemoryMt5ObservationPersistence,
]:
    # These observations come exclusively from NativeModuleFake. Confirmation
    # of constructed fixtures here is not a production binding workflow.
    account = adapter.get_account_info(trace_id="constructed-binding")
    specification = adapter.get_symbol_specification(
        "XAUUSD", trace_id="constructed-binding"
    )
    worker_config = Mt5WorkerConfig(
        broker_symbol="XAUUSD",
        expected_account_fingerprint=account.account_fingerprint,
    )
    store = InMemoryMt5ObservationPersistence(
        database_state=confirmed_state(
            confirmed_symbol_binding=confirmed_binding(
                specification.specification_fingerprint
            ),
            position_tickets=(
                frozenset({"1101"}) if kind == "positions" else frozenset()
            ),
            active_order_tickets=(
                frozenset({"1101"}) if kind == "orders" else frozenset()
            ),
        )
    )
    service = ReadOnlyReconciliationService(
        adapter, store, worker_config, clock=lambda: NOW
    )
    polling = ReadOnlyPollingService(
        adapter, store, service, worker_config, clock=lambda: NOW
    )
    return service, polling, store


def _future_row(kind: Kind) -> SimpleNamespace:
    seconds = int(NOW.timestamp()) + 86_400
    if kind == "orders":
        return _raw_row(time_setup=seconds, time_setup_msc=seconds * 1_000)
    if kind == "order_history":
        return _raw_row(time_done=seconds, time_done_msc=seconds * 1_000)
    return _raw_row(time=seconds, time_msc=seconds * 1_000)


@pytest.mark.parametrize("kind", KINDS)
def test_full_reconciliation_never_accepts_native_future_transaction(
    connected_native: NativeFixture, kind: Kind
) -> None:
    adapter, module = connected_native
    _set_rows(module, kind, _raw_row())
    service, _, store = _native_services(adapter, kind)
    baseline = service.run(trace_id="valid-transaction")
    assert baseline.health.state is HealthState.HEALTHY
    previous_tick = store.ticks["XAUUSD"]
    previous_reports = dict(store.reports)
    _set_rows(module, kind, _future_row(kind))

    if kind in {"positions", "orders"}:
        with pytest.raises(Mt5ReadFailure) as raised:
            service.run(trace_id="future-transaction")
        assert raised.value.error.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        assert store.ticks["XAUUSD"] is previous_tick
        assert store.reports == previous_reports
    else:
        result = service.run(trace_id="future-transaction")
        assert result.health.state is HealthState.BLOCKED
        assert result.health.reason_code is Mt5ReasonCode.HISTORY_QUERY_FAILED
        evidence = (
            result.report.order_history_evidence
            if kind == "order_history"
            else result.report.deal_history_evidence
        )
        assert evidence.result_state is HistoryQueryResultState.QUERY_FAILED


@pytest.mark.parametrize("kind", ["positions", "orders"])
def test_light_polling_never_renews_health_from_native_future_transaction(
    connected_native: NativeFixture, kind: Kind
) -> None:
    adapter, module = connected_native
    _set_rows(module, kind, _raw_row())
    _, polling, store = _native_services(adapter, kind)
    assert polling.run_once().health.state is HealthState.HEALTHY
    previous_heartbeats = dict(store.heartbeats)
    previous_reports = dict(store.reports)
    module.calls.clear()
    _set_rows(module, kind, _future_row(kind))

    with pytest.raises(Mt5ReadFailure) as raised:
        polling.run_position_once(trace_id="future-transaction")

    assert raised.value.error.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    assert polling.state.health_state is HealthState.UNAVAILABLE
    assert polling.state.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    assert polling.state.reconciliation_required is True
    assert polling.state.connected is False
    assert store.heartbeats == previous_heartbeats
    assert store.reports == previous_reports
    assert "history_orders_get" not in module.calls
    assert "history_deals_get" not in module.calls


@pytest.mark.parametrize("kind", ["positions", "orders"])
def test_manual_full_polling_invalidates_prior_health_on_native_failure(
    connected_native: NativeFixture, kind: Kind
) -> None:
    adapter, module = connected_native
    _set_rows(module, kind, _raw_row())
    _, polling, store = _native_services(adapter, kind)
    assert polling.run_once().health.state is HealthState.HEALTHY
    previous_heartbeats = dict(store.heartbeats)
    previous_reports = dict(store.reports)
    _set_rows(module, kind, _future_row(kind))

    with pytest.raises(Mt5ReadFailure) as raised:
        polling.run_once()

    assert raised.value.error.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    assert polling.state.health_state is HealthState.UNAVAILABLE
    assert polling.state.reason_code is Mt5ReasonCode.RECONCILIATION_INCOMPLETE
    assert polling.state.reconciliation_required is True
    assert polling.state.connected is False
    assert store.heartbeats == previous_heartbeats
    assert store.reports == previous_reports


def test_direct_tick_polling_invalidates_prior_health_on_native_pair_failure(
    connected_native: NativeFixture,
) -> None:
    adapter, module = connected_native
    _, polling, store = _native_services(adapter, "deals")
    assert polling.run_once().health.state is HealthState.HEALTHY
    previous_heartbeats = dict(store.heartbeats)
    previous_reports = dict(store.reports)
    previous_tick = store.ticks["XAUUSD"]
    assert isinstance(module.tick_result, SimpleNamespace)
    module.tick_result.time_msc = int(NOW.timestamp()) * 1_000 - 1
    module.calls.clear()

    with pytest.raises(Mt5ReadFailure) as raised:
        polling.run_tick_once(trace_id="invalid-tick-pair")

    assert raised.value.error.reason_code is Mt5ReasonCode.TICK_INVALID
    assert polling.state.health_state is HealthState.UNAVAILABLE
    assert polling.state.reason_code is Mt5ReasonCode.TICK_INVALID
    assert polling.state.reconciliation_required is True
    assert polling.state.connected is False
    assert store.heartbeats == previous_heartbeats
    assert store.reports == previous_reports
    assert store.ticks["XAUUSD"] is previous_tick
    assert "history_orders_get" not in module.calls
    assert "history_deals_get" not in module.calls
