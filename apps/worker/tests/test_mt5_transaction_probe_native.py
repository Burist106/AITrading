"""The time probe is a bounded diagnostic, not a transaction gate override."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from mt5_factories import NOW
from test_mt5_market_policy import change_binding, market_adapter
from test_mt5_native import NativeModuleFake

from aurum_worker.models.mt5 import Mt5ReadFailure


class ProbeNativeFake(NativeModuleFake):
    def __init__(self) -> None:
        super().__init__()
        event = int((NOW + timedelta(hours=3, minutes=-1)).timestamp())
        self.samples: dict[str, tuple[SimpleNamespace, ...]] = {
            "orders": (
                SimpleNamespace(
                    symbol="XAUUSD",
                    ticket=100001,
                    time_setup=event - 2,
                    time_setup_msc=(event - 2) * 1000 + 10,
                    time_done=event,
                    time_done_msc=event * 1000 + 250,
                    comment="private-order-comment",
                ),
            ),
            "deals": (
                SimpleNamespace(
                    symbol="XAUUSD",
                    ticket=200001,
                    order=100001,
                    time=event,
                    time_msc=event * 1000 + 250,
                    comment="private-deal-comment",
                ),
            ),
        }
        self.history_calls = 0
        self.change_at: int | None = None
        self.change_kind = "account"
        self.fail_at: int | None = None
        self.mutate_at: int | None = None

    def read(self, kind: str, start: datetime | int, end: datetime | int) -> object:
        self.history_calls += 1
        self.calls.append(f"history_{kind}_get")
        if self.history_calls == self.fail_at:
            return None
        if self.history_calls == self.change_at:
            change_binding(self, self.change_kind)
        if self.history_calls == self.mutate_at:
            self.samples["deals"][0].time_msc += 1
        lower = int(start.timestamp()) if isinstance(start, datetime) else start
        upper = int(end.timestamp()) if isinstance(end, datetime) else end
        return tuple(
            row
            for row in self.samples[kind]
            if lower <= (row.time_done if kind == "orders" else row.time) <= upper
        )

    def history_orders_get(self, start: datetime | int, end: datetime | int) -> object:
        return self.read("orders", start, end)

    def history_deals_get(self, start: datetime | int, end: datetime | int) -> object:
        return self.read("deals", start, end)


def test_probe_observes_bounded_patterns_without_unlocking_production(
    tmp_path: Path,
) -> None:
    module = ProbeNativeFake()
    with market_adapter(tmp_path, module) as adapter:
        result = adapter.inspect_transaction_time_probe(trace_id="probe-test")
        assert result.status == "probe_observed"
        assert result.transaction_time_contract == "unverified"
        assert result.grants_eligibility is False
        assert result.reference_supplied is False
        assert result.stable_snapshots is True
        assert result.history_query_count == module.history_calls == 24
        assert len(result.orders.queries) == len(result.deals.queries) == 10
        assert result.orders.setup_done_distinguishable is True
        patterns = {query.code: query.target_present for query in result.orders.queries}
        assert patterns["integer_event_window"] is True
        assert patterns["datetime_event_window"] is True
        assert patterns["integer_minus_three_hours_window"] is False
        assert patterns["integer_setup_exact"] is False
        assert patterns["integer_exact_second"] is True
        assert patterns["integer_after_second"] is False
        assert patterns["datetime_before_millisecond"] is True
        assert patterns["datetime_exact_millisecond"] is True
        for value in ("100001", "200001", "private-", "XAUUSD"):
            assert value not in result.model_dump_json()
        with pytest.raises(Mt5ReadFailure):
            adapter.get_open_positions(trace_id="still-blocked")
        assert "positions_get" not in module.calls
        assert "orders_get" not in module.calls


@pytest.mark.parametrize("kind", ["account", "provider", "specification"])
@pytest.mark.parametrize("stage", [1, 5, 24])
def test_probe_discards_partial_results_when_binding_changes(
    tmp_path: Path, kind: str, stage: int
) -> None:
    module = ProbeNativeFake()
    module.change_kind = kind
    module.change_at = stage
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_time_probe(trace_id="probe-test")
        assert module.history_calls == stage


@pytest.mark.parametrize("stage", [1, 2, 5, 23, 24])
def test_probe_does_not_treat_query_failure_as_exclusion(
    tmp_path: Path, stage: int
) -> None:
    module = ProbeNativeFake()
    module.fail_at = stage
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_time_probe(trace_id="probe-test")
        assert module.history_calls == stage


def test_probe_requires_stable_final_history(tmp_path: Path) -> None:
    module = ProbeNativeFake()
    module.mutate_at = 24
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_time_probe(trace_id="probe-test")
        assert module.history_calls == 24


@pytest.mark.parametrize("kind", ["orders", "deals"])
def test_probe_requires_nonempty_matching_existing_samples(
    tmp_path: Path, kind: str
) -> None:
    module = ProbeNativeFake()
    module.samples[kind] = ()
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_time_probe(trace_id="probe-test")
        assert module.history_calls <= 2


def test_probe_wrong_policy_blocks_before_history(tmp_path: Path) -> None:
    module = ProbeNativeFake()
    with market_adapter(tmp_path, module, policy="utc_epoch_v1") as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_time_probe(trace_id="probe-test")
        assert module.history_calls == 0


@pytest.mark.parametrize("elapsed", [-1, 31])
def test_probe_clock_regression_or_budget_expiry_stops_between_reads(
    tmp_path: Path, elapsed: int
) -> None:
    module = ProbeNativeFake()
    with market_adapter(tmp_path, module) as adapter:
        adapter._clock = lambda: (
            NOW + timedelta(seconds=elapsed) if module.history_calls else NOW
        )
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_transaction_time_probe(trace_id="probe-test")
        assert module.history_calls == 1
