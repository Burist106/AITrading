from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from mt5_factories import NOW
from test_mt5_market_policy import change_binding, market_adapter
from test_mt5_native import NativeModuleFake

from aurum_worker.models.mt5 import HistoryRequest, Mt5ReadFailure


def test_empty_inventory_is_not_a_time_contract(tmp_path: Path) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        result = adapter.inspect_transaction_inventory(trace_id="test")
        payload = result.model_dump(mode="json")
        assert payload["transaction_time_contract"] == "unverified"
        assert payload["grants_eligibility"] is False
        assert payload["smoke_invoked"] is False
        assert payload["positions"]["matching_symbol_rows"] == 0
        assert payload["historical_deals"]["matching_symbol_rows"] == 0
        for call in (
            "positions_get",
            "orders_get",
            "history_orders_get",
            "history_deals_get",
        ):
            assert module.calls.count(call) == 1
        # Inventory does not enable even an empty production reconciliation.
        with pytest.raises(Mt5ReadFailure):
            adapter.get_open_positions(trace_id="test")
        with pytest.raises(Mt5ReadFailure):
            adapter.get_active_orders(trace_id="test")
        with pytest.raises(Mt5ReadFailure):
            adapter.get_order_history(
                HistoryRequest(start_at=NOW - timedelta(hours=1), end_at=NOW),
                trace_id="test",
            )
        with pytest.raises(Mt5ReadFailure):
            adapter.get_deal_history(
                HistoryRequest(start_at=NOW - timedelta(hours=1), end_at=NOW),
                trace_id="test",
            )


def test_inventory_exports_counts_not_native_values(tmp_path: Path) -> None:
    module = NativeModuleFake()
    seconds = int(NOW.timestamp())
    module.position_result = (
        SimpleNamespace(
            symbol="XAUUSD",
            time=seconds,
            time_msc=seconds * 1000 + 7,
            ticket="private-ticket",
            comment="private-comment",
        ),
        SimpleNamespace(symbol="private-other-symbol"),
    )
    module.order_result = (
        SimpleNamespace(
            symbol="XAUUSD", time_setup=seconds, time_setup_msc=0, time_expiration=0
        ),
    )
    with market_adapter(tmp_path, module) as adapter:
        result = adapter.inspect_transaction_inventory(trace_id="test")
        assert result.positions.matching_symbol_rows == 1
        assert result.positions.other_symbol_rows == 1
        assert result.positions.fields["time"].nonzero == 1
        assert result.positions.fields["time"].milliseconds_agree == 1
        assert result.active_orders.fields["time_expiration"].zero == 1
        assert (
            result.active_orders.fields["time_setup"].milliseconds_missing_or_zero == 1
        )
        exported = result.model_dump_json()
        for secret in (
            "private-ticket",
            "private-comment",
            "private-other-symbol",
            "XAUUSD",
            str(seconds),
        ):
            assert secret not in exported


@pytest.mark.parametrize("kind", ["account", "provider", "specification"])
def test_inventory_rejects_changed_binding_before_any_read(
    tmp_path: Path, kind: str
) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        change_binding(module, kind)
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test")
        assert "positions_get" not in module.calls


@pytest.mark.parametrize("kind", ["account", "provider", "specification"])
def test_inventory_discards_results_on_change_during_read(
    tmp_path: Path, kind: str
) -> None:
    class ChangedFake(NativeModuleFake):
        def positions_get(self) -> object:
            result = super().positions_get()
            change_binding(self, kind)
            return result

    module = ChangedFake()
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test")
        assert "orders_get" not in module.calls


@pytest.mark.parametrize("mode", [1, 2, 99])
def test_inventory_rejects_non_demo(tmp_path: Path, mode: int) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        cast(SimpleNamespace, module.account_result).trade_mode = mode
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test")
        assert "positions_get" not in module.calls


@pytest.mark.parametrize(
    "bad_rows",
    [
        None,
        {},
        "private-detail",
        (None,),
        tuple([SimpleNamespace(symbol="XAUUSD", time=1, time_msc=1000)] * 1001),
    ],
)
def test_inventory_rejects_invalid_or_oversized_results(
    tmp_path: Path, bad_rows: object
) -> None:
    module = NativeModuleFake()
    module.position_result = bad_rows
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test")
        assert "orders_get" not in module.calls


def test_inventory_query_is_an_explicit_hypothesis_envelope(tmp_path: Path) -> None:
    class CapturingFake(NativeModuleFake):
        def history_orders_get(self, start: datetime, end: datetime) -> object:
            assert start == NOW - timedelta(days=7)
            assert end == NOW + timedelta(hours=3)
            return super().history_orders_get(start, end)

        def history_deals_get(self, start: datetime, end: datetime) -> object:
            assert start == NOW - timedelta(days=7)
            assert end == NOW + timedelta(hours=3)
            return super().history_deals_get(start, end)

    with market_adapter(tmp_path, CapturingFake()) as adapter:
        payload = json.loads(
            adapter.inspect_transaction_inventory(trace_id="test").model_dump_json()
        )
        assert (
            payload["query_interpretation"] == "unverified_utc_or_server_label_envelope"
        )


def test_inventory_requires_explicit_source_policy(tmp_path: Path) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module, policy="utc_epoch_v1") as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test")
        assert "positions_get" not in module.calls


@pytest.mark.parametrize(
    "seconds,msc,bucket,ms_bucket",
    [
        (None, None, "missing", "milliseconds_missing_or_zero"),
        (0, 0, "zero", "milliseconds_missing_or_zero"),
        (True, True, "invalid", "milliseconds_invalid_or_disagree"),
        (-1, -1000, "invalid", "milliseconds_invalid_or_disagree"),
        (1.5, 1500, "invalid", "milliseconds_invalid_or_disagree"),
        ("1", "1000", "invalid", "milliseconds_invalid_or_disagree"),
        (1, 2000, "nonzero", "milliseconds_invalid_or_disagree"),
    ],
)
def test_bad_fields_are_counted_never_interpreted_as_times(
    tmp_path: Path,
    seconds: object,
    msc: object,
    bucket: str,
    ms_bucket: str,
) -> None:
    module = NativeModuleFake()
    module.position_result = (
        SimpleNamespace(symbol="XAUUSD", time=seconds, time_msc=msc),
    )
    with market_adapter(tmp_path, module) as adapter:
        fields = adapter.inspect_transaction_inventory(
            trace_id="test"
        ).positions.fields["time"]
        assert fields.model_dump()[bucket] == 1
        assert fields.model_dump()[ms_bucket] == 1


@pytest.mark.parametrize(
    "now", [datetime(2026, 3, 10, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)]
)
def test_entire_inventory_window_needs_coverage(tmp_path: Path, now: datetime) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module, now=now) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test")
        assert "positions_get" not in module.calls


@pytest.mark.parametrize(
    "stage", ["order_result", "order_history_result", "deal_history_result"]
)
def test_partial_inventory_is_discarded_on_failed_read(
    tmp_path: Path, stage: str
) -> None:
    module = NativeModuleFake()
    setattr(module, stage, None)
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test")


def test_inventory_accepts_exact_row_cap(tmp_path: Path) -> None:
    module = NativeModuleFake()
    module.position_result = tuple(
        [SimpleNamespace(symbol="XAUUSD", time=1, time_msc=1000)] * 1000
    )
    with market_adapter(tmp_path, module) as adapter:
        assert (
            adapter.inspect_transaction_inventory(
                trace_id="test"
            ).positions.matching_symbol_rows
            == 1000
        )


def test_explicit_thirty_day_inventory_keeps_unverified_contract(
    tmp_path: Path,
) -> None:
    class OlderHistoryFake(NativeModuleFake):
        def history_orders_get(self, start: datetime, end: datetime) -> object:
            assert start == NOW - timedelta(days=30)
            assert end == NOW + timedelta(hours=3)
            return super().history_orders_get(start, end)

        def history_deals_get(self, start: datetime, end: datetime) -> object:
            assert start == NOW - timedelta(days=30)
            assert end == NOW + timedelta(hours=3)
            return super().history_deals_get(start, end)

    with market_adapter(tmp_path, OlderHistoryFake()) as adapter:
        result = adapter.inspect_transaction_inventory(
            trace_id="test", lookback_days=30
        )
        assert result.lookback_days == 30
        assert result.transaction_time_contract == "unverified"
        assert result.grants_eligibility is False


@pytest.mark.parametrize("days", [True, 0, -1, 8, 31, 30.0, "30"])
def test_inventory_rejects_unbounded_or_malformed_lookback(
    tmp_path: Path, days: object
) -> None:
    module = NativeModuleFake()
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test", lookback_days=days)  # type: ignore[arg-type]
        assert "positions_get" not in module.calls


def test_thirty_day_inventory_cannot_cross_policy_start(tmp_path: Path) -> None:
    module = NativeModuleFake()
    with market_adapter(
        tmp_path, module, now=datetime(2026, 3, 20, tzinfo=UTC)
    ) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test", lookback_days=30)
        assert "positions_get" not in module.calls


def test_inventory_rejects_iterator_without_consuming_it(tmp_path: Path) -> None:
    def forbidden_iterator() -> Iterator[None]:
        raise AssertionError("Unbounded iterator must never be consumed")
        yield None

    module = NativeModuleFake()
    module.position_result = forbidden_iterator()
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure) as raised:
            adapter.inspect_transaction_inventory(trace_id="test")
        assert not isinstance(raised.value.__cause__, AssertionError)


@pytest.mark.parametrize("kind", ["account", "provider", "specification"])
def test_last_read_binding_change_discards_entire_inventory(
    tmp_path: Path, kind: str
) -> None:
    class ChangedLastFake(NativeModuleFake):
        def history_deals_get(self, start: datetime, end: datetime) -> object:
            result = super().history_deals_get(start, end)
            change_binding(self, kind)
            return result

    with market_adapter(tmp_path, ChangedLastFake()) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_inventory(trace_id="test")
