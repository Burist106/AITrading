from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, timedelta
from decimal import Decimal

import pytest
from mt5_factories import NOW
from test_shadow_market import read_port, service

from aurum_worker.models.mt5 import Timeframe
from aurum_worker.shadow.market import MarketBlocked, MarketCapture


def test_capture_bundle_retains_exact_digest_inputs_and_is_frozen() -> None:
    adapter = read_port()
    capture = service(adapter).capture_bundle(trace_id="source-test")
    assert isinstance(capture, MarketCapture)
    for actual, original in zip(
        capture.series.candles,
        adapter.candles[("XAUUSD", Timeframe.M1)].candles,
        strict=True,
    ):
        assert actual == original.model_copy(update={"trace_id": "source-test"})
    assert capture.tick == adapter.ticks["XAUUSD"].model_copy(
        update={"trace_id": "source-test"}
    )
    assert capture.account == adapter.accounts[0].model_copy(
        update={"trace_id": "source-test"}
    )
    assert capture.specification == adapter.specifications["XAUUSD"].model_copy(
        update={"trace_id": "source-test"}
    )
    assert (
        capture.reconciliation.report.reconciliation_id
        == capture.features.reconciliation_id
    )

    def number(value: Decimal) -> str:
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    payload = {
        "normalization": "completed-m1-v1",
        "source": capture.tick.source,
        "adapter": capture.tick.adapter_version,
        "account": capture.account.account_fingerprint,
        "server": capture.account.server_fingerprint,
        "specification": capture.specification.specification_fingerprint,
        "symbol": capture.specification.broker_symbol,
        "point": number(capture.specification.point),
        "tick_size": number(capture.specification.tick_size),
        "tick_at": capture.tick.tick_at.astimezone(UTC).isoformat(),
        "bid": number(capture.tick.bid),
        "ask": number(capture.tick.ask),
        "bars": [
            [bar.open_at.astimezone(UTC).isoformat()]
            + [number(value) for value in (bar.open, bar.high, bar.low, bar.close)]
            for bar in capture.series.candles
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == capture.features.input_digest
    assert service(read_port()).capture(trace_id="legacy") == capture.features
    with pytest.raises(FrozenInstanceError):
        setattr(capture, "tick", None)  # noqa: B010 - exercise frozen runtime guard.


def test_supplied_full_result_avoids_duplicate_history_queries() -> None:
    adapter = read_port()
    target = service(adapter)
    capture = target.capture_bundle(trace_id="full-first")
    assert isinstance(capture, MarketCapture)
    adapter.call_log.clear()
    again = target.capture_bundle(
        trace_id="full-reuse", reconciliation_result=capture.reconciliation
    )
    assert isinstance(again, MarketCapture)
    assert again.features == capture.features
    assert "get_order_history" not in adapter.call_log
    assert "get_deal_history" not in adapter.call_log
    assert "get_open_positions" in adapter.call_log
    assert "get_active_orders" in adapter.call_log


def test_supplied_result_still_requires_current_reconciliation() -> None:
    adapter = read_port()
    target = service(adapter)
    capture = target.capture_bundle(trace_id="source")
    assert isinstance(capture, MarketCapture)
    from dataclasses import replace

    stale = replace(
        capture.reconciliation,
        report=capture.reconciliation.report.model_copy(
            update={"completed_at": NOW - timedelta(seconds=6)}
        ),
    )
    assert isinstance(
        target.capture_bundle(trace_id="stale", reconciliation_result=stale),
        MarketBlocked,
    )
