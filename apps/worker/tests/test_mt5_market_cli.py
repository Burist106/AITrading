from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import NoReturn

import pytest
from mt5_factories import NOW, candle_series, tick

from aurum_worker import mt5_market_cli as cli
from aurum_worker.local_mt5_profile import LocalMt5Profile, ProfileError
from aurum_worker.models.mt5 import (
    CandleGap,
    CandleRequest,
    CandleSeries,
    LatestTickObservation,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    SafeMt5Error,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY, UTC_POLICY
from aurum_worker.mt5_transaction_inventory import (
    InventoryLookback,
    RowInventory,
    TransactionInventory,
)

CONFIRM = "--confirm-pepperstone-demo"
ENVIRONMENT_FIELDS = (
    "AURUM_MT5_TERMINAL_PATH",
    "AURUM_MT5_BROKER_SYMBOL",
    "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT",
    "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT",
    "AURUM_MT5_MAX_TICK_AGE_SECONDS",
    "AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS",
    "AURUM_MT5_READONLY_SMOKE",
)


def synthetic_profile() -> LocalMt5Profile:
    return LocalMt5Profile(
        terminal_path="C:\\Synthetic Market Test\\terminal64.exe",
        broker_symbol="XAUUSD",
        account_fingerprint="mt5-account-v1:" + "a" * 64,
        specification_fingerprint="mt5-spec-v1:" + "b" * 64,
        account_confirmed_at=NOW,
        specification_confirmed_at=NOW,
    )


def completed_candles() -> CandleSeries:
    template = candle_series().candles[0]
    return CandleSeries(
        candles=tuple(
            template.model_copy(update={"open_at": NOW - timedelta(minutes=5 - i)})
            for i in range(5)
        )
    )


class MemoryStore:
    def __init__(self) -> None:
        self.profile = synthetic_profile()
        self.loads = 0
        self.failure: Exception | None = None

    def load(self) -> LocalMt5Profile:
        self.loads += 1
        if self.failure:
            raise self.failure
        return self.profile


class MarketAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.ticks = [tick(), tick()]
        self.series = [completed_candles(), completed_candles()]
        self.requests: list[CandleRequest] = []
        self.failure: Exception | None = None
        self.shutdown_failure = False

    def connect(self, *, trace_id: str) -> None:
        self.calls.append("connect")
        if self.failure:
            raise self.failure

    def get_latest_tick(self, symbol: str, *, trace_id: str) -> LatestTickObservation:
        assert symbol == "XAUUSD"
        self.calls.append("tick")
        return self.ticks.pop(0)

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        request: CandleRequest,
        *,
        trace_id: str,
    ) -> CandleSeries:
        assert symbol == "XAUUSD"
        assert timeframe is Timeframe.M1
        self.calls.append("candles")
        self.requests.append(request)
        return self.series.pop(0)

    def disconnect(self) -> None:
        self.calls.append("disconnect")
        if self.shutdown_failure:
            raise RuntimeError("synthetic-private-shutdown-detail")

    def inspect_transaction_inventory(
        self, *, trace_id: str, lookback_days: InventoryLookback = 7
    ) -> TransactionInventory:
        self.calls.append("inventory")
        rows = RowInventory(matching_symbol_rows=0, other_symbol_rows=0, fields={})
        return TransactionInventory(
            lookback_days=lookback_days,
            positions=rows,
            active_orders=rows,
            historical_orders=rows,
            historical_deals=rows,
        )


@pytest.fixture(autouse=True)
def isolate_all_native_and_profile_access(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENVIRONMENT_FIELDS:
        monkeypatch.delenv(name, raising=False)

    def no_profile() -> NoReturn:
        raise AssertionError("Test must explicitly provide an in-memory profile.")

    def no_native(config: Mt5WorkerConfig) -> NoReturn:
        raise AssertionError("Test must explicitly provide a fake adapter.")

    def no_smoke(config: Mt5WorkerConfig) -> NoReturn:
        raise AssertionError("Test must explicitly provide a fake smoke delegate.")

    monkeypatch.setattr(cli, "ProfileStore", no_profile)
    monkeypatch.setattr(cli, "MetaTrader5ReadAdapter", no_native)
    monkeypatch.setattr(cli.mt5_cli, "_smoke", no_smoke)


@pytest.fixture
def memory_store(monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    store = MemoryStore()
    monkeypatch.setattr(cli, "ProfileStore", lambda: store)
    return store


@pytest.fixture
def market_adapter(monkeypatch: pytest.MonkeyPatch) -> MarketAdapter:
    adapter = MarketAdapter()
    monkeypatch.setattr(cli, "MetaTrader5ReadAdapter", lambda config: adapter)
    return adapter


def selected_config() -> Mt5WorkerConfig:
    return Mt5WorkerConfig(
        **{
            **synthetic_profile().worker_config().model_dump(),
            "market_time_policy": PEPPERSTONE_POLICY,
        }
    )


def test_transaction_inventory_is_separate_from_market_check_and_smoke(
    memory_store: MemoryStore,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["inventory", CONFIRM]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "inventory_observed"
    assert payload["grants_eligibility"] is False
    assert payload["smoke_invoked"] is False
    assert payload["transaction_time_contract"] == "unverified"
    assert market_adapter.calls == ["connect", "inventory", "disconnect"]
    assert memory_store.loads == 1


def test_inventory_shutdown_failure_discards_observation(
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    market_adapter.shutdown_failure = True
    assert cli._transaction_inventory(selected_config()) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "SHUTDOWN_FAILED"
    assert "positions" not in payload


def test_thirty_day_inventory_requires_exact_explicit_option(
    memory_store: MemoryStore,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["inventory", CONFIRM, "--lookback-days=30"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["lookback_days"] == 30
    assert payload["transaction_time_contract"] == "unverified"
    assert payload["grants_eligibility"] is False
    assert memory_store.loads == 1
    assert market_adapter.calls == ["connect", "inventory", "disconnect"]


@pytest.mark.parametrize(
    "args",
    [
        ["inventory", CONFIRM, "--lookback-days=31"],
        ["inventory", CONFIRM, "--lookback-days=-1"],
        ["inventory", CONFIRM, "--lookback-days=30", "extra"],
        ["inventory", "--lookback-days=30"],
        ["check", CONFIRM, "--lookback-days=30"],
        ["smoke", CONFIRM, "--lookback-days=30"],
    ],
)
def test_lookback_option_cannot_extend_other_commands_or_skip_confirmation(
    args: list[str],
    memory_store: MemoryStore,
    market_adapter: MarketAdapter,
) -> None:
    assert cli.main(args) == 2
    assert memory_store.loads == 0
    assert market_adapter.calls == []


@pytest.mark.parametrize("structured", [False, True])
def test_inventory_failure_output_is_sanitized(
    structured: bool,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    market_adapter.failure = (
        Mt5ReadFailure(
            SafeMt5Error(
                reason_code=Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
                safe_detail="synthetic-private-detail",
            )
        )
        if structured
        else RuntimeError("synthetic-private-detail")
    )
    assert cli._transaction_inventory(selected_config()) == (2 if structured else 3)
    output = capsys.readouterr().out
    assert "synthetic-private-detail" not in output
    assert "positions" not in json.loads(output)
    assert market_adapter.calls == ["connect", "disconnect"]


def test_inventory_rejects_smoke_consent_before_profile_or_native_access(
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    market_adapter: MarketAdapter,
) -> None:
    monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", "1")
    assert cli.main(["inventory", CONFIRM]) == 2
    assert memory_store.loads == 0
    assert market_adapter.calls == []


@pytest.mark.parametrize(
    "detail",
    [
        "PUBLIC_PROVIDER_MISSING",
        "PUBLIC_PROVIDER_INVALID",
        "PUBLIC_PROVIDER_EMPTY",
        "PUBLIC_PROVIDER_METAQUOTES",
        "PUBLIC_PROVIDER_UNSUPPORTED",
    ],
)
def test_bounded_provider_evidence_is_reported_but_never_grants_eligibility(
    detail: str,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    market_adapter.failure = Mt5ReadFailure(
        SafeMt5Error(
            reason_code=Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH, safe_detail=detail
        )
    )
    assert cli._market_check(selected_config()) == 2
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "status": "blocked",
        "reason": "ACCOUNT_BINDING_MISMATCH",
        "provider_evidence": detail,
        "grants_eligibility": False,
        "smoke_invoked": False,
    }
    assert market_adapter.calls == ["connect", "disconnect"]


@pytest.mark.parametrize(
    ("reason", "detail"),
    [
        (Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH, "synthetic-private-detail"),
        (
            Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH,
            "PUBLIC_PROVIDER_METAQUOTES synthetic-private-detail",
        ),
        (Mt5ReasonCode.REAL_ACCOUNT_BLOCKED, "PUBLIC_PROVIDER_METAQUOTES"),
    ],
)
def test_unrecognized_or_wrong_reason_provider_detail_never_leaks(
    reason: Mt5ReasonCode,
    detail: str,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    market_adapter.failure = Mt5ReadFailure(
        SafeMt5Error(reason_code=reason, safe_detail=detail)
    )
    assert cli._market_check(selected_config()) == 2
    output = capsys.readouterr().out
    assert "synthetic-private" not in output
    assert "provider_evidence" not in json.loads(output)
    assert market_adapter.calls == ["connect", "disconnect"]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["check"],
        ["smoke"],
        ["check", "yes"],
        ["other", CONFIRM],
        ["check", CONFIRM, "extra"],
    ],
)
def test_explicit_source_confirmation_required_before_profile_load(
    args: list[str], memory_store: MemoryStore, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(args) == 2
    assert memory_store.loads == 0
    assert (
        "Explicit Pepperstone Demo source confirmation required"
        in capsys.readouterr().out
    )


@pytest.mark.parametrize("value", [None, "", "0", "true", "2"])
def test_smoke_needs_exact_process_opt_in_before_profile_load(
    value: str | None,
    memory_store: MemoryStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if value is not None:
        monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", value)
    assert cli.main(["smoke", CONFIRM]) == 0
    assert memory_store.loads == 0
    assert capsys.readouterr().out.startswith("NOT RUN")


@pytest.mark.parametrize("name", ENVIRONMENT_FIELDS[:-1])
def test_binding_and_limit_environment_conflicts_precede_profile_load(
    name: str,
    memory_store: MemoryStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(name, "synthetic-private-environment")
    assert cli.main(["check", CONFIRM]) == 2
    assert memory_store.loads == 0
    output = capsys.readouterr().out
    expected = "PROFILE_LIMIT_CONFLICT" if "SECONDS" in name else "PROFILE_ENV_CONFLICT"
    assert expected in output
    assert "synthetic-private-environment" not in output


@pytest.mark.parametrize("value", ["1", "true", "invalid"])
def test_check_rejects_smoke_environment_conflict(
    value: str,
    memory_store: MemoryStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", value)
    assert cli.main(["check", CONFIRM]) == 2
    assert memory_store.loads == 0
    assert "PROFILE_SMOKE_CONFLICT" in capsys.readouterr().out


@pytest.mark.parametrize("action", ["check", "smoke"])
def test_process_policy_selection_never_mutates_saved_profile(
    action: str,
    memory_store: MemoryStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Mt5WorkerConfig] = []
    before = memory_store.profile.model_dump_json()

    def delegate(config: Mt5WorkerConfig) -> int:
        captured.append(config)
        return 2

    if action == "smoke":
        monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", "1")
        monkeypatch.setattr(cli.mt5_cli, "_smoke", delegate)
    else:
        monkeypatch.setattr(cli, "_market_check", delegate)
    assert cli.main([action, CONFIRM]) == 2
    assert memory_store.loads == 1
    assert len(captured) == 1
    assert captured[0].market_time_policy == PEPPERSTONE_POLICY
    assert captured[0].readonly_smoke is (action == "smoke")
    assert captured[0].max_tick_age_seconds == 10
    assert captured[0].max_clock_drift_seconds == 30
    assert (
        captured[0].expected_account_fingerprint
        == memory_store.profile.account_fingerprint
    )
    assert (
        captured[0].smoke_confirmed_specification_fingerprint
        == memory_store.profile.specification_fingerprint
    )
    assert memory_store.profile.model_dump_json() == before
    assert memory_store.profile.worker_config().market_time_policy == UTC_POLICY
    assert not memory_store.profile.worker_config().readonly_smoke


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (ProfileError("PROFILE_UNREADABLE"), "PROFILE_UNREADABLE"),
        (ProfileError("synthetic-private-profile"), "PROFILE_FAILED"),
        (RuntimeError("synthetic-private-profile"), "PROFILE_FAILED"),
    ],
)
def test_profile_failures_have_only_safe_codes(
    failure: Exception,
    reason: str,
    memory_store: MemoryStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    memory_store.failure = failure
    assert cli.main(["check", CONFIRM]) == 2
    output = capsys.readouterr().out
    assert reason in output
    assert "synthetic-private-profile" not in output


def test_complete_market_check_reports_only_safe_evidence_not_smoke_or_eligibility(
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = selected_config()
    assert cli._market_check(config) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "market_check_passed"
    assert payload["grants_eligibility"] is False
    assert payload["smoke_invoked"] is False
    assert payload["transaction_time_contract"] == "unverified"
    assert payload["completed_m1_count"] == 5
    assert payload["range_roundtrip_matched"] is True
    assert payload["observed_at"] == NOW.isoformat()
    assert market_adapter.calls == [
        "connect",
        "tick",
        "candles",
        "candles",
        "tick",
        "disconnect",
    ]
    first, repeated = market_adapter.requests
    assert first.start_position == 1 and first.count == 5
    assert not first.include_current
    assert first.range_start is None and first.range_end is None
    assert repeated.count == 5 and not repeated.include_current
    assert repeated.range_start == NOW - timedelta(minutes=5)
    assert repeated.range_end == NOW - timedelta(minutes=1)
    saved = synthetic_profile()
    for private in (
        saved.terminal_path,
        saved.account_fingerprint,
        saved.specification_fingerprint,
        "2345.00",
    ):
        assert private not in output


@pytest.mark.parametrize(
    ("freshness", "reason"),
    [
        (TickFreshness.DELAYED, "TICK_DELAYED"),
        (TickFreshness.STALE, "TICK_STALE"),
        (TickFreshness.FUTURE_INVALID, "TICK_FROM_FUTURE"),
        (TickFreshness.UNAVAILABLE, "TICK_UNAVAILABLE"),
    ],
)
@pytest.mark.parametrize("read_index", [0, 1])
def test_non_live_tick_blocks_before_read_or_after_roundtrip(
    freshness: TickFreshness,
    reason: str,
    read_index: int,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    market_adapter.ticks[read_index] = tick(freshness)
    assert cli._market_check(selected_config()) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["reason"] == reason
    assert payload["grants_eligibility"] is False
    assert "range_roundtrip_matched" not in payload
    assert market_adapter.calls[-1] == "disconnect"
    assert market_adapter.calls.count("tick") == read_index + 1
    assert market_adapter.calls.count("candles") == read_index * 2


@pytest.mark.parametrize("variant", ["count", "incomplete", "gap"])
def test_incomplete_or_gapped_market_window_cannot_pass(
    variant: str,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = completed_candles()
    if variant == "count":
        changed = CandleSeries(candles=original.candles[:4])
    elif variant == "incomplete":
        changed = CandleSeries(
            candles=original.candles[:-1]
            + (original.candles[-1].model_copy(update={"is_complete": False}),)
        )
    else:
        changed = original.model_copy(
            update={
                "gaps": (
                    CandleGap(
                        after_open_at=NOW - timedelta(minutes=3),
                        before_open_at=NOW - timedelta(minutes=1),
                        missing_intervals=1,
                    ),
                )
            }
        )
    market_adapter.series[0] = changed
    assert cli._market_check(selected_config()) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "CANDLE_DATA_INVALID"
    assert payload["status"] == "blocked"
    assert market_adapter.calls[-1] == "disconnect"


@pytest.mark.parametrize(
    "field",
    ["open", "high", "low", "close", "tick_volume", "spread", "real_volume", "open_at"],
)
def test_roundtrip_requires_content_match_not_only_candle_count(
    field: str,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = completed_candles()
    values: dict[str, object] = {
        "open_at": NOW - timedelta(minutes=6),
        "open": Decimal("2345.25"),
        "high": Decimal("2346.25"),
        "low": Decimal("2343.75"),
        "close": Decimal("2345.25"),
    }
    value = values.get(field, Decimal("1234.56"))
    changed = original.candles[0].model_copy(update={field: value})
    market_adapter.series[1] = CandleSeries(candles=(changed, *original.candles[1:]))
    assert cli._market_check(selected_config()) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "CANDLE_DATA_INVALID"
    assert payload["status"] == "blocked"
    assert "1234.56" not in json.dumps(payload)


@pytest.mark.parametrize("age_seconds", [-1, 61, 3600])
def test_final_tick_observation_rejects_future_or_old_completed_candle_window(
    age_seconds: int,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    final_time = NOW + timedelta(seconds=age_seconds)
    market_adapter.ticks[1] = tick().model_copy(
        update={"observed_at": final_time, "tick_at": final_time - timedelta(seconds=1)}
    )
    assert cli._market_check(selected_config()) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "CANDLE_DATA_INVALID"
    assert payload["status"] == "blocked"
    assert market_adapter.calls[-1] == "disconnect"


@pytest.mark.parametrize("age_seconds", [0, 60])
def test_final_tick_observation_accepts_inclusive_candle_close_age_boundary(
    age_seconds: int,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    final_time = NOW + timedelta(seconds=age_seconds)
    market_adapter.ticks[1] = tick().model_copy(
        update={"observed_at": final_time, "tick_at": final_time - timedelta(seconds=1)}
    )
    assert cli._market_check(selected_config()) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["observed_at"] == final_time.isoformat()


def test_shutdown_failure_discards_every_success_field(
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    market_adapter.shutdown_failure = True
    assert cli._market_check(selected_config()) == 3
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "grants_eligibility": False,
        "smoke_invoked": False,
        "status": "failed",
        "reason": "SHUTDOWN_FAILED",
    }
    assert "synthetic-private-shutdown-detail" not in output


@pytest.mark.parametrize("structured", [False, True])
def test_adapter_failure_cannot_expose_native_detail(
    structured: bool,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    market_adapter.failure = (
        Mt5ReadFailure(
            SafeMt5Error(
                reason_code=Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH,
                safe_detail="synthetic-private-native-detail",
            )
        )
        if structured
        else RuntimeError("synthetic-private-native-detail")
    )
    assert cli._market_check(selected_config()) == (2 if structured else 3)
    output = capsys.readouterr().out
    assert "synthetic-private-native-detail" not in output
    payload = json.loads(output)
    assert payload["reason"] == (
        "ACCOUNT_BINDING_MISMATCH" if structured else "MARKET_CHECK_FAILED"
    )
    assert market_adapter.calls == ["connect", "disconnect"]


@pytest.mark.parametrize("variant", ["incomplete", "gap"])
def test_roundtrip_metadata_must_still_establish_complete_contiguous_candles(
    variant: str,
    market_adapter: MarketAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repeated = completed_candles()
    if variant == "incomplete":
        changed_last = repeated.candles[-1].model_copy(update={"is_complete": False})
        repeated = CandleSeries(candles=(*repeated.candles[:-1], changed_last))
    else:
        repeated = repeated.model_copy(
            update={
                "gaps": (
                    CandleGap(
                        after_open_at=NOW - timedelta(minutes=3),
                        before_open_at=NOW - timedelta(minutes=1),
                        missing_intervals=1,
                    ),
                )
            }
        )
    market_adapter.series[1] = repeated
    assert cli._market_check(selected_config()) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["reason"] == "CANDLE_DATA_INVALID"
    assert "range_roundtrip_matched" not in payload
    assert market_adapter.calls[-1] == "disconnect"
