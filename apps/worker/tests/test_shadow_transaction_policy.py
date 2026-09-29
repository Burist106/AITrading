"""Fake-only Shadow provenance checks; no native acceptance is implied."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

import pytest
from mt5_factories import NOW, account, active_order, confirmed_binding, position
from test_shadow_market import read_port

from aurum_worker.adapters.fake_mt5 import FakeMt5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    CandleSeries,
    DatabaseReconciliationState,
    Mt5WorkerConfig,
    Timeframe,
)
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY, UTC_POLICY
from aurum_worker.mt5_transaction_time import PEPPERSTONE_TRANSACTION_POLICY
from aurum_worker.reconciliation import ReadOnlyReconciliationService
from aurum_worker.shadow.market import (
    MarketBlockCode,
    MarketBlocked,
    MarketFeatures,
    ShadowMarketService,
)

Collection = Literal["positions", "orders", "both"]
Selection = Literal["utc", "market_only", "transactions"]


def _configured_service(
    collection: Collection,
    selection: Selection = "transactions",
    *,
    row_version: str | None = None,
) -> tuple[ShadowMarketService, FakeMt5ReadAdapter]:
    adapter = read_port()
    base = adapter.accounts[0].adapter_version
    market_policy = UTC_POLICY if selection == "utc" else PEPPERSTONE_POLICY
    transaction_policy = (
        PEPPERSTONE_TRANSACTION_POLICY if selection == "transactions" else None
    )
    expected_version = (
        base if transaction_policy is None else f"{base}:{transaction_policy}"
    )
    version = expected_version if row_version is None else row_version
    if collection in {"positions", "both"}:
        adapter.positions = (
            position().model_copy(update={"source": "mt5", "adapter_version": version}),
        )
    if collection in {"orders", "both"}:
        adapter.orders = (
            active_order().model_copy(
                update={"source": "mt5", "adapter_version": version}
            ),
        )
    if market_policy != UTC_POLICY:
        market_version = f"{base}:{market_policy}"
        adapter.ticks["XAUUSD"] = adapter.ticks["XAUUSD"].model_copy(
            update={"adapter_version": market_version}
        )
        adapter.candles[("XAUUSD", Timeframe.M1)] = CandleSeries(
            candles=tuple(
                bar.model_copy(update={"adapter_version": market_version})
                for bar in adapter.candles[("XAUUSD", Timeframe.M1)].candles
            )
        )
    config = Mt5WorkerConfig(
        market_time_policy=market_policy,
        transaction_time_policy=transaction_policy,
        broker_symbol="XAUUSD",
        expected_account_fingerprint=account().account_fingerprint,
        smoke_confirmed_specification_fingerprint=(
            confirmed_binding().confirmed_specification_fingerprint
        ),
    )
    persistence = InMemoryMt5ObservationPersistence(
        database_state=DatabaseReconciliationState(
            account_fingerprint=account().account_fingerprint,
            server_fingerprint=account().server_fingerprint,
            confirmed_symbol_binding=confirmed_binding(),
            position_tickets=frozenset(item.ticket for item in adapter.positions),
            active_order_tickets=frozenset(item.ticket for item in adapter.orders),
        )
    )
    reconciler = ReadOnlyReconciliationService(
        adapter,
        persistence,
        config,
        clock=lambda: NOW,
        identifier_factory=lambda: "00000000-0000-4000-8000-000000000001",
    )
    return (
        ShadowMarketService(
            adapter, persistence, reconciler, config, clock=lambda: NOW
        ),
        adapter,
    )


@pytest.mark.parametrize("collection", ["positions", "orders", "both"])
@pytest.mark.parametrize("selection", ["utc", "market_only", "transactions"])
def test_nonempty_collections_require_the_selected_transaction_provenance(
    collection: Collection, selection: Selection
) -> None:
    service, adapter = _configured_service(collection, selection)
    result = service.capture(trace_id="transaction-provenance")
    assert isinstance(result, MarketFeatures)
    assert result.adapter_version == adapter.accounts[0].adapter_version
    assert result.environment == "DEMO_ONLY"
    assert result.runtime_mode == "SHADOW"
    assert result.grants_eligibility is False


@pytest.mark.parametrize("collection", ["positions", "orders", "both"])
@pytest.mark.parametrize(
    "row_version",
    ["fake-v1", f"fake-v1:{PEPPERSTONE_POLICY}", "fake-v1:unsupported-policy"],
)
def test_selected_transaction_policy_rejects_missing_market_or_wrong_tag(
    collection: Collection, row_version: str
) -> None:
    service, _ = _configured_service(collection, row_version=row_version)
    result = service.capture(trace_id="wrong-transaction-provenance")
    assert isinstance(result, MarketBlocked)
    assert result.reason is MarketBlockCode.SOURCE_MISMATCH


@pytest.mark.parametrize("selection", ["utc", "market_only"])
@pytest.mark.parametrize("collection", ["positions", "orders", "both"])
def test_unselected_policy_does_not_accept_transaction_tag(
    selection: Selection, collection: Collection
) -> None:
    service, _ = _configured_service(
        collection,
        selection,
        row_version=f"fake-v1:{PEPPERSTONE_TRANSACTION_POLICY}",
    )
    result = service.capture(trace_id="unselected-transaction-policy")
    assert isinstance(result, MarketBlocked)
    assert result.reason is MarketBlockCode.SOURCE_MISMATCH


@pytest.mark.parametrize("collection", ["positions", "orders"])
@pytest.mark.parametrize("mutation", ["source", "stale", "future", "mixed_tag"])
def test_policy_tag_never_bypasses_source_freshness_or_per_row_checks(
    collection: Collection, mutation: str
) -> None:
    service, adapter = _configured_service("both")
    updates: dict[str, object] = {
        "source": "fake_mt5",
        "observed_at": NOW,
    }
    if mutation == "stale":
        updates = {"observed_at": NOW - timedelta(seconds=6)}
    elif mutation == "future":
        updates = {"observed_at": NOW + timedelta(microseconds=1)}
    elif mutation == "mixed_tag":
        updates = {"adapter_version": adapter.accounts[0].adapter_version}
    if collection == "positions":
        adapter.positions = (adapter.positions[0].model_copy(update=updates),)
    else:
        adapter.orders = (adapter.orders[0].model_copy(update=updates),)
    result = service.capture(trace_id="invalid-transaction-observation")
    assert isinstance(result, MarketBlocked)
    assert result.reason is MarketBlockCode.SOURCE_MISMATCH
