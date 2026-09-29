"""Synthetic native-boundary checks for the non-executable link diagnostic."""

import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from mt5_factories import NOW
from test_mt5_market_policy import change_binding, market_adapter
from test_mt5_native import NativeModuleFake

from aurum_worker.models.mt5 import Mt5ReadFailure
from aurum_worker.mt5_position_link import PositionReference


class LinkNativeFake(NativeModuleFake):
    def __init__(self) -> None:
        super().__init__()
        self.event = int((NOW + timedelta(hours=3, minutes=-2)).timestamp())
        self.position = SimpleNamespace(
            symbol="XAUUSD",
            ticket=410001,
            identifier=310001,
            time=self.event,
            time_msc=self.event * 1000 + 250,
            time_update=self.event,
            time_update_msc=self.event * 1000 + 250,
            type=1,
        )
        self.order = SimpleNamespace(
            symbol="XAUUSD",
            ticket=310001,
            position_id=310001,
            time_setup=self.event - 1,
            time_setup_msc=(self.event - 1) * 1000 + 50,
            time_done=self.event,
            time_done_msc=self.event * 1000 + 300,
            type=1,
        )
        self.deal = SimpleNamespace(
            symbol="XAUUSD",
            ticket=510001,
            position_id=310001,
            order=310001,
            time=self.event,
            time_msc=self.event * 1000 + 250,
            entry=0,
            type=1,
        )
        self.collection_calls = 0
        self.change_at: int | None = None
        self.change_kind = "account"
        self.fail_at: int | None = None
        self.mutate_kind: str | None = None
        self.arguments: list[tuple[str, datetime | int, datetime | int]] = []

    def read(self, kind: str, row: SimpleNamespace) -> object:
        self.collection_calls += 1
        self.calls.append(kind)
        if self.collection_calls == self.change_at:
            change_binding(self, self.change_kind)
        if self.collection_calls == self.fail_at:
            return None
        if self.collection_calls > 3 and kind == self.mutate_kind:
            if kind == "positions_get":
                row.time_update_msc += 1
            elif kind == "history_orders_get":
                row.time_done_msc += 1
            else:
                row.time_msc += 1
        return (row,)

    def positions_get(self) -> object:
        return self.read("positions_get", self.position)

    def history_orders_get(self, start: datetime | int, end: datetime | int) -> object:
        self.arguments.append(("orders", start, end))
        return self.read("history_orders_get", self.order)

    def history_deals_get(self, start: datetime | int, end: datetime | int) -> object:
        self.arguments.append(("deals", start, end))
        return self.read("history_deals_get", self.deal)

    def references(self) -> tuple[PositionReference, ...]:
        return (
            PositionReference(
                ticket=self.position.ticket,
                opening_label=(datetime(1970, 1, 1) + timedelta(seconds=self.event)),
            ),
        )


def test_link_probe_observes_identity_and_time_without_runtime_unlock(
    tmp_path: Path,
) -> None:
    module = LinkNativeFake()
    with market_adapter(tmp_path, module) as adapter:
        result = adapter.inspect_position_time_links(
            trace_id="link-test", references=module.references()
        )
        assert result.status == "position_links_observed"
        assert result.collection_read_count == module.collection_calls == 6
        assert result.stable_snapshots is True
        assert result.linked_positions == result.references_checked == 1
        assert result.display_second_matches == 1
        assert result.position_deal_second_matches == 1
        assert result.position_deal_millisecond_matches == 1
        assert result.order_setup_done_distinguishable == 1
        assert result.order_deal_time_order_matches == 1
        assert result.grants_eligibility is False
        assert result.smoke_invoked is False
        assert result.transaction_time_contract == "unverified"
        assert module.arguments == [
            (kind, NOW - timedelta(days=7), NOW + timedelta(hours=3))
            for kind in ("orders", "deals", "orders", "deals")
        ]
        for forbidden in ("410001", "310001", "510001", "XAUUSD", str(module.event)):
            assert forbidden not in result.model_dump_json()
        with pytest.raises(Mt5ReadFailure):
            adapter.get_open_positions(trace_id="still-blocked")
        assert module.collection_calls == 6
        assert "orders_get" not in module.calls


@pytest.mark.parametrize("stage", range(1, 7))
@pytest.mark.parametrize("kind", ["account", "provider", "specification"])
def test_link_probe_rejects_changed_bindings_at_every_read(
    tmp_path: Path, stage: int, kind: str
) -> None:
    module = LinkNativeFake()
    module.change_at, module.change_kind = stage, kind
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references()
            )
        assert module.collection_calls == stage


@pytest.mark.parametrize("stage", range(1, 7))
def test_link_probe_none_is_failure_not_empty_evidence(
    tmp_path: Path, stage: int
) -> None:
    module = LinkNativeFake()
    module.fail_at = stage
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references()
            )
        assert module.collection_calls == stage


@pytest.mark.parametrize(
    "kind", ["positions_get", "history_orders_get", "history_deals_get"]
)
def test_link_probe_rejects_changed_filtered_snapshot(
    tmp_path: Path, kind: str
) -> None:
    module = LinkNativeFake()
    module.mutate_kind = kind
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references()
            )


@pytest.mark.parametrize("elapsed", [-1, 31])
def test_link_probe_clock_or_budget_failure_stops_reads(
    tmp_path: Path, elapsed: int
) -> None:
    module = LinkNativeFake()
    with market_adapter(tmp_path, module) as adapter:
        adapter._clock = lambda: (
            NOW + timedelta(seconds=elapsed) if module.collection_calls else NOW
        )
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references()
            )
        assert module.collection_calls == 1


def test_link_probe_wrong_policy_never_reads_collections(tmp_path: Path) -> None:
    module = LinkNativeFake()
    with market_adapter(tmp_path, module, policy="utc_epoch_v1") as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references()
            )
        assert module.collection_calls == 0


def test_link_probe_expired_policy_never_reads_collections(tmp_path: Path) -> None:
    module = LinkNativeFake()
    with market_adapter(
        tmp_path, module, now=datetime(2026, 11, 2, tzinfo=UTC)
    ) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references()
            )
        assert module.collection_calls == 0


def test_link_probe_missing_reference_never_reads_collections(tmp_path: Path) -> None:
    module = LinkNativeFake()
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(trace_id="link-test", references=())
        assert module.collection_calls == 0


def test_link_probe_old_selected_position_is_not_silently_reinterpreted(
    tmp_path: Path,
) -> None:
    module = LinkNativeFake()
    module.position.time -= 8 * 86400
    module.position.time_msc -= 8 * 86400 * 1000
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references()
            )


def test_link_probe_monotonic_budget_expiry_stops_after_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = LinkNativeFake()
    monkeypatch.setattr(
        "aurum_worker.adapters.native_mt5.monotonic",
        lambda: 31.0 if module.collection_calls else 0.0,
    )
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references()
            )
        assert module.collection_calls == 1


def test_link_probe_reference_revalidation_leaks_no_warning(tmp_path: Path) -> None:
    module = LinkNativeFake()
    malformed = PositionReference.model_construct(
        ticket="fictional-private-reference", opening_label=datetime(2026, 6, 1)
    )
    with market_adapter(tmp_path, module) as adapter:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            with pytest.raises(Mt5ReadFailure):
                adapter.inspect_position_time_links(
                    trace_id="link-test", references=(malformed,)
                )
        assert not captured
        assert module.collection_calls == 0


def test_link_probe_duplicate_references_never_read_collections(tmp_path: Path) -> None:
    module = LinkNativeFake()
    with market_adapter(tmp_path, module) as adapter:
        with pytest.raises(Mt5ReadFailure):
            adapter.inspect_position_time_links(
                trace_id="link-test", references=module.references() * 2
            )
        assert module.collection_calls == 0
