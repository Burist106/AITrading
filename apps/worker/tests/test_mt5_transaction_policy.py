"""Bounded Pepperstone transaction-policy integration, using synthetic rows only."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from mt5_factories import NOW
from test_mt5_market_policy import change_binding, market_adapter, native_tick
from test_mt5_native import NativeModuleFake, native_adapter
from test_mt5_tick_time import diagnostic_setup
from test_mt5_transaction_normalization import (
    KINDS,
    REQUEST,
    SECOND,
    Kind,
    _native_services,
    _raw_row,
    _set_rows,
)

from aurum_worker.adapters.native_mt5 import ADAPTER_VERSION, MetaTrader5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    ActiveOrderObservation,
    HealthState,
    HistoricalDealObservation,
    HistoricalOrderObservation,
    HistoryQueryResultState,
    HistoryRequest,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    OpenPositionObservation,
)
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY
from aurum_worker.mt5_transaction_time import PEPPERSTONE_TRANSACTION_POLICY
from aurum_worker.reconciliation import ReadOnlyReconciliationService

OFFSET_SECONDS = 10_800
OFFSET = timedelta(seconds=OFFSET_SECONDS)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
CALLS = {
    "positions": "positions_get",
    "orders": "orders_get",
    "order_history": "history_orders_get",
    "deals": "history_deals_get",
}
HISTORY_KINDS: tuple[Kind, ...] = ("order_history", "deals")
type TransactionObservation = (
    OpenPositionObservation
    | ActiveOrderObservation
    | HistoricalOrderObservation
    | HistoricalDealObservation
)


def _label_row(**updates: object) -> SimpleNamespace:
    """Encode constructed UTC fixture times as synthetic server epoch labels."""
    row = _raw_row(**updates)
    for name, value in vars(row).items():
        if name == "time" or name.startswith("time_"):
            if type(value) is int and value > 0:
                multiplier = 1_000 if name.endswith("_msc") else 1
                setattr(row, name, value + OFFSET_SECONDS * multiplier)
    return row


def _event_row(event_at: datetime, *, ticket: int = 1101) -> SimpleNamespace:
    milliseconds = (event_at - EPOCH) // timedelta(milliseconds=1)
    seconds = milliseconds // 1_000
    return _label_row(
        ticket=ticket,
        time=seconds,
        time_msc=milliseconds,
        time_setup=seconds - 30,
        time_setup_msc=milliseconds - 30_000,
        time_done=seconds,
        time_done_msc=milliseconds,
    )


def _read(
    adapter: MetaTrader5ReadAdapter,
    kind: Kind,
    request: HistoryRequest = REQUEST,
) -> Sequence[TransactionObservation]:
    if kind == "positions":
        return adapter.get_open_positions(trace_id="transaction-policy")
    if kind == "orders":
        return adapter.get_active_orders(trace_id="transaction-policy")
    if kind == "order_history":
        return adapter.get_order_history(request, trace_id="transaction-policy")
    return adapter.get_deal_history(request, trace_id="transaction-policy")


class TransactionFake(NativeModuleFake):
    def __init__(self) -> None:
        super().__init__()
        self.history_arguments: list[tuple[datetime | int, datetime | int]] = []
        self.change_after: str | None = None

    def change_context(self, change: str) -> None:
        if change == "terminal":
            cast(SimpleNamespace, self.terminal_result).connected = False
        elif change == "live":
            cast(SimpleNamespace, self.account_result).trade_mode = 2
        else:
            change_binding(self, change)

    def _after(self, result: object) -> object:
        if self.change_after is not None:
            self.change_context(self.change_after)
        return result

    def positions_get(self) -> object:
        return self._after(super().positions_get())

    def orders_get(self) -> object:
        return self._after(super().orders_get())

    def history_orders_get(self, start: datetime | int, end: datetime | int) -> object:
        self.history_arguments.append((start, end))
        return self._after(super().history_orders_get(start, end))

    def history_deals_get(self, start: datetime | int, end: datetime | int) -> object:
        self.history_arguments.append((start, end))
        return self._after(super().history_deals_get(start, end))


@contextmanager
def transaction_adapter(
    tmp_path: Path,
    module: NativeModuleFake,
    *,
    now: datetime = NOW,
) -> Iterator[MetaTrader5ReadAdapter]:
    # Independent confirmation is constructed entirely from a fake account/spec.
    _, config = diagnostic_setup(tmp_path, module)
    cast(SimpleNamespace, module.account_result).company = "Pepperstone Test"
    selected = Mt5WorkerConfig.model_validate(
        {
            **config.model_dump(),
            "market_time_policy": PEPPERSTONE_POLICY,
            "transaction_time_policy": PEPPERSTONE_TRANSACTION_POLICY,
        }
    )
    adapter = MetaTrader5ReadAdapter(
        selected, module=module, platform="win32", clock=lambda: now
    )
    adapter.connect(trace_id="synthetic-transaction-policy")
    module.calls.clear()
    try:
        yield adapter
    finally:
        adapter.disconnect()


@pytest.mark.parametrize(
    ("kind", "field", "expected"),
    [
        ("positions", "opened_at", EPOCH + timedelta(seconds=SECOND, milliseconds=123)),
        ("orders", "setup_at", EPOCH + timedelta(seconds=SECOND - 30, milliseconds=17)),
        (
            "order_history",
            "setup_at",
            EPOCH + timedelta(seconds=SECOND - 30, milliseconds=17),
        ),
        (
            "order_history",
            "completed_at",
            EPOCH + timedelta(seconds=SECOND, milliseconds=123),
        ),
        ("deals", "occurred_at", EPOCH + timedelta(seconds=SECOND, milliseconds=123)),
    ],
)
def test_policy_decodes_server_labels_once_and_preserves_milliseconds(
    tmp_path: Path, kind: Kind, field: str, expected: datetime
) -> None:
    module = TransactionFake()
    _set_rows(module, kind, _label_row())
    with transaction_adapter(tmp_path, module) as adapter:
        result = _read(adapter, kind)[0]
        assert getattr(result, field) == expected
        assert result.observed_at == NOW
        assert result.adapter_version == (
            f"{ADAPTER_VERSION}:{PEPPERSTONE_TRANSACTION_POLICY}"
        )
        assert module.calls.count(CALLS[kind]) == 1
        assert module.calls.count("account_info") == 2
        assert module.calls.count("symbol_info") == 2


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize(
    "change", ["terminal", "live", "account", "provider", "specification"]
)
def test_policy_checks_binding_before_even_empty_native_reads(
    tmp_path: Path, kind: Kind, empty: bool, change: str
) -> None:
    module = TransactionFake()
    if not empty:
        _set_rows(module, kind, _label_row())
    with transaction_adapter(tmp_path, module) as adapter:
        module.change_context(change)
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)
        assert CALLS[kind] not in module.calls


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize(
    "change", ["terminal", "live", "account", "provider", "specification"]
)
def test_policy_discards_results_if_binding_changes_during_read(
    tmp_path: Path, kind: Kind, empty: bool, change: str
) -> None:
    module = TransactionFake()
    if not empty:
        _set_rows(module, kind, _label_row())
    with transaction_adapter(tmp_path, module) as adapter:
        module.change_after = change
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)
        assert module.calls.count(CALLS[kind]) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_policy_accepts_guarded_empty_collection(tmp_path: Path, kind: Kind) -> None:
    module = TransactionFake()
    with transaction_adapter(tmp_path, module) as adapter:
        assert list(_read(adapter, kind)) == []
        assert module.calls.count("account_info") == 2
        assert module.calls.count("symbol_info") == 2


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "now",
    [datetime(2026, 3, 8, 23, 59, 59, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)],
)
def test_capture_outside_policy_season_blocks_before_reads(
    tmp_path: Path, kind: Kind, now: datetime
) -> None:
    module = TransactionFake()
    with transaction_adapter(tmp_path, module, now=now) as adapter:
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)
        assert CALLS[kind] not in module.calls


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("milliseconds", [30_000, 30_001])
def test_event_future_limit_is_applied_after_server_label_conversion(
    tmp_path: Path, kind: Kind, milliseconds: int
) -> None:
    module = TransactionFake()
    event_at = NOW + timedelta(milliseconds=milliseconds)
    row = _event_row(event_at)
    if kind == "orders":
        row.time_setup = row.time
        row.time_setup_msc = row.time_msc
    _set_rows(module, kind, row)
    request = HistoryRequest(
        start_at=REQUEST.start_at, end_at=NOW + timedelta(seconds=30)
    )
    with transaction_adapter(tmp_path, module) as adapter:
        if milliseconds == 30_000:
            assert len(_read(adapter, kind, request)) == 1
        else:
            with pytest.raises(Mt5ReadFailure):
                _read(adapter, kind, request)


@pytest.mark.parametrize("kind", KINDS)
def test_policy_keeps_all_account_symbols_instead_of_hiding_exposure(
    tmp_path: Path, kind: Kind
) -> None:
    module = TransactionFake()
    _set_rows(module, kind, _label_row(symbol="EURUSD"))
    with transaction_adapter(tmp_path, module) as adapter:
        result = _read(adapter, kind)
        assert len(result) == 1
        assert result[0].symbol == "EURUSD"


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("value", [None, "not-a-collection", {}, 12])
def test_policy_invalid_collection_is_not_an_empty_success(
    tmp_path: Path, kind: Kind, value: object
) -> None:
    module = TransactionFake()
    field = {
        "positions": "position_result",
        "orders": "order_result",
        "order_history": "order_history_result",
        "deals": "deal_history_result",
    }[kind]
    setattr(module, field, value)
    with transaction_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("count", [1_000, 1_001])
def test_policy_collection_bound_never_silently_truncates(
    tmp_path: Path, kind: Kind, count: int
) -> None:
    module = TransactionFake()
    field = {
        "positions": "position_result",
        "orders": "order_result",
        "order_history": "order_history_result",
        "deals": "deal_history_result",
    }[kind]
    setattr(module, field, tuple(_label_row(ticket=2_000 + i) for i in range(count)))
    with transaction_adapter(tmp_path, module) as adapter:
        if count == 1_000:
            assert len(_read(adapter, kind)) == count
        else:
            with pytest.raises(Mt5ReadFailure):
                _read(adapter, kind)


@pytest.mark.parametrize("kind", KINDS)
def test_duplicate_ticket_rejects_whole_collection(tmp_path: Path, kind: Kind) -> None:
    module = TransactionFake()
    field = {
        "positions": "position_result",
        "orders": "order_result",
        "order_history": "order_history_result",
        "deals": "deal_history_result",
    }[kind]
    setattr(module, field, (_label_row(), _label_row(symbol="EURUSD")))
    with transaction_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)


@pytest.mark.parametrize("kind", HISTORY_KINDS)
@pytest.mark.parametrize("local_offset", [-5, 0, 7])
def test_history_encodes_explicit_second_arguments_and_preserves_utc_request(
    tmp_path: Path, kind: Kind, local_offset: int
) -> None:
    module = TransactionFake()
    zone = timezone(timedelta(hours=local_offset))
    start = (NOW - timedelta(minutes=3) + timedelta(microseconds=123_456)).astimezone(
        zone
    )
    end = (NOW - timedelta(minutes=1) + timedelta(microseconds=789_123)).astimezone(
        zone
    )
    request = HistoryRequest(start_at=start, end_at=end)
    original = request.model_dump()
    _set_rows(module, kind, _event_row(NOW - timedelta(minutes=2)))
    with transaction_adapter(tmp_path, module) as adapter:
        assert len(_read(adapter, kind, request)) == 1
        expected = (int((start + OFFSET).timestamp()), int((end + OFFSET).timestamp()))
        assert module.history_arguments == [expected]
        assert all(type(value) is int for value in module.history_arguments[0])
        assert request.model_dump() == original


@pytest.mark.parametrize("kind", HISTORY_KINDS)
def test_history_filters_only_valid_fractional_edge_padding(
    tmp_path: Path, kind: Kind
) -> None:
    module = TransactionFake()
    base = NOW - timedelta(minutes=3)
    request = HistoryRequest(
        start_at=base + timedelta(milliseconds=250),
        end_at=base + timedelta(seconds=2, milliseconds=750),
    )
    events = [
        base,
        request.start_at,
        base + timedelta(seconds=1),
        request.end_at,
        base + timedelta(seconds=2, milliseconds=999),
    ]
    rows = tuple(_event_row(event, ticket=3_000 + i) for i, event in enumerate(events))
    field = "order_history_result" if kind == "order_history" else "deal_history_result"
    setattr(module, field, rows)
    with transaction_adapter(tmp_path, module) as adapter:
        result = _read(adapter, kind, request)
        assert [row.ticket for row in result] == ["3001", "3002", "3003"]
        event_field = "completed_at" if kind == "order_history" else "occurred_at"
        assert [getattr(row, event_field) for row in result] == events[1:4]


@pytest.mark.parametrize("kind", HISTORY_KINDS)
@pytest.mark.parametrize("offset", [-1, 3_000])
def test_history_outside_encoded_whole_second_envelope_fails_closed(
    tmp_path: Path, kind: Kind, offset: int
) -> None:
    module = TransactionFake()
    base = NOW - timedelta(minutes=3)
    request = HistoryRequest(
        start_at=base + timedelta(milliseconds=250),
        end_at=base + timedelta(seconds=2, milliseconds=750),
    )
    _set_rows(module, kind, _event_row(base + timedelta(milliseconds=offset)))
    with transaction_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure) as error:
            _read(adapter, kind, request)
        assert error.value.error.reason_code is Mt5ReasonCode.HISTORY_QUERY_FAILED


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("order_history", "time_done_msc"),
        ("order_history", "ticket"),
        ("deals", "time_msc"),
        ("deals", "ticket"),
        ("deals", "volume"),
    ],
)
def test_invalid_padding_row_is_not_discarded_before_validation(
    tmp_path: Path, kind: Kind, field: str
) -> None:
    module = TransactionFake()
    base = NOW - timedelta(minutes=3)
    request = HistoryRequest(
        start_at=base + timedelta(milliseconds=500), end_at=base + timedelta(seconds=1)
    )
    row = _event_row(base)
    setattr(row, field, False)
    _set_rows(module, kind, row)
    with transaction_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind, request)


def test_historical_zero_completion_remains_window_incomplete(tmp_path: Path) -> None:
    module = TransactionFake()
    _set_rows(module, "order_history", _label_row(time_done=0, time_done_msc=0))
    with transaction_adapter(tmp_path, module) as adapter:
        service = ReadOnlyReconciliationService(
            adapter,
            InMemoryMt5ObservationPersistence(),
            adapter._config,
            clock=lambda: NOW,
        )
        rows, evidence = service._order_history(REQUEST, "missing-completion")
        assert len(rows) == 1
        assert rows[0].completed_at is None
        assert evidence.result_state is HistoryQueryResultState.WINDOW_INCOMPLETE
        assert evidence.returned_count == 1


@pytest.mark.parametrize("mode", [1, 3])
def test_unrepresented_day_expiration_modes_remain_blocked(
    tmp_path: Path, mode: int
) -> None:
    module = TransactionFake()
    _set_rows(module, "orders", _label_row(type_time=mode, time_expiration=0))
    with transaction_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, "orders")


@pytest.mark.parametrize("mode", [0, 2])
def test_supported_active_expiration_is_explicit_and_converted(
    tmp_path: Path, mode: int
) -> None:
    module = TransactionFake()
    expiration = NOW + timedelta(hours=1)
    _set_rows(
        module,
        "orders",
        _label_row(
            type_time=mode,
            time_expiration=int(expiration.timestamp()) if mode == 2 else 0,
        ),
    )
    with transaction_adapter(tmp_path, module) as adapter:
        row = adapter.get_active_orders(trace_id="expiration")[0]
        assert row.expiration_at == (expiration if mode == 2 else None)


@pytest.mark.parametrize("kind", KINDS)
def test_market_policy_without_transaction_opt_in_remains_blocked(
    tmp_path: Path, kind: Kind
) -> None:
    module = TransactionFake()
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)
        assert CALLS[kind] not in module.calls


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("field", ["max_tick_age_seconds", "max_clock_drift_seconds"])
def test_bypassed_config_validation_cannot_relax_transaction_limits(
    tmp_path: Path, kind: Kind, field: str
) -> None:
    module = TransactionFake()
    with transaction_adapter(tmp_path, module) as adapter:
        adapter._config = adapter._config.model_copy(update={field: 300})
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)
        assert CALLS[kind] not in module.calls


@pytest.mark.parametrize("kind", KINDS)
def test_fake_full_reconciliation_consumes_policy_normalized_rows(
    tmp_path: Path, kind: Kind
) -> None:
    module = TransactionFake()
    module.tick_result = native_tick(NOW)
    _set_rows(module, kind, _label_row())
    with transaction_adapter(tmp_path, module) as adapter:
        service, _, _ = _native_services(adapter, kind)
        result = service.run(trace_id="constructed-policy-reconciliation")
        assert result.health.state is HealthState.HEALTHY
        evidence = (
            result.report.order_history_evidence
            if kind == "order_history"
            else result.report.deal_history_evidence
        )
        if kind in HISTORY_KINDS:
            assert evidence.result_state is HistoryQueryResultState.QUERY_SUCCEEDED
            assert evidence.latest_returned_at == EPOCH + timedelta(
                seconds=SECOND, milliseconds=123
            )


@pytest.mark.parametrize("kind", KINDS)
def test_legacy_default_does_not_infer_offset_from_future_transaction_labels(
    tmp_path: Path, kind: Kind
) -> None:
    module = TransactionFake()
    _set_rows(module, kind, _label_row())
    adapter = native_adapter(tmp_path, module)
    adapter.connect(trace_id="default-policy")
    try:
        assert adapter._config.transaction_time_policy is None
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)
    finally:
        adapter.disconnect()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("phase", ["old-event", "unknown-policy"])
def test_policy_does_not_guess_winter_or_unknown_configuration(
    tmp_path: Path, kind: Kind, phase: str
) -> None:
    module = TransactionFake()
    _set_rows(module, kind, _event_row(datetime(2026, 3, 8, 12, tzinfo=UTC)))
    with transaction_adapter(tmp_path, module) as adapter:
        if phase == "unknown-policy":
            adapter._config = adapter._config.model_copy(
                update={"transaction_time_policy": "unrecognized"}
            )
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind)
        if phase == "unknown-policy":
            assert CALLS[kind] not in module.calls


@pytest.mark.parametrize("kind", KINDS)
def test_capture_leaving_season_during_read_discards_even_empty_result(
    tmp_path: Path, kind: Kind, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = TransactionFake()
    end = datetime(2026, 11, 1, tzinfo=UTC)
    now = [end - timedelta(seconds=1)]

    def after_read(result: object) -> object:
        now[0] = end
        return result

    with transaction_adapter(tmp_path, module, now=now[0]) as adapter:
        adapter._clock = lambda: now[0]
        monkeypatch.setattr(module, "_after", after_read)
        request = HistoryRequest(start_at=end - timedelta(hours=1), end_at=now[0])
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind, request)
        assert module.calls.count(CALLS[kind]) == 1


@pytest.mark.parametrize("kind", HISTORY_KINDS)
@pytest.mark.parametrize("case", ["before-season", "after-season", "future-drift"])
def test_unsupported_history_request_never_reaches_native_selection(
    tmp_path: Path, kind: Kind, case: str
) -> None:
    if case == "before-season":
        start = datetime(2026, 3, 8, 23, 59, tzinfo=UTC)
        end = start + timedelta(minutes=2)
    elif case == "after-season":
        end = datetime(2026, 11, 1, tzinfo=UTC)
        start = end - timedelta(minutes=1)
    else:
        start, end = NOW, NOW + timedelta(seconds=30, milliseconds=1)
    request = HistoryRequest(start_at=start, end_at=end)
    module = TransactionFake()
    with transaction_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, kind, request)
        assert CALLS[kind] not in module.calls


@pytest.mark.parametrize(
    "expiration",
    [datetime(2026, 3, 8, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)],
)
def test_specified_expiration_outside_supported_season_is_not_interpreted(
    tmp_path: Path, expiration: datetime
) -> None:
    module = TransactionFake()
    _set_rows(
        module,
        "orders",
        _label_row(type_time=2, time_expiration=int(expiration.timestamp())),
    )
    with transaction_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            _read(adapter, "orders")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market_time_policy", "utc_epoch_v1"),
        ("transaction_time_policy", "unknown"),
        ("expected_account_fingerprint", None),
        ("smoke_confirmed_specification_fingerprint", None),
        ("broker_symbol", None),
        ("max_tick_age_seconds", 300),
        ("max_clock_drift_seconds", 300),
    ],
)
def test_policy_configuration_requires_explicit_supported_bound_context(
    tmp_path: Path, field: str, value: object
) -> None:
    module = TransactionFake()
    with transaction_adapter(tmp_path, module) as adapter:
        with pytest.raises(ValueError):
            Mt5WorkerConfig.model_validate(
                {**adapter._config.model_dump(), field: value}
            )
