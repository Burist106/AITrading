from __future__ import annotations

import json
from datetime import UTC, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from mt5_factories import NOW, RAW_LOGIN, RAW_SERVER
from test_mt5_native import NativeModuleFake, native_adapter

from aurum_worker import mt5_cli
from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.models.mt5 import (
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    TickFreshness,
)
from aurum_worker.mt5_safety import account_fingerprint


def diagnostic_setup(
    tmp_path: Path, module: NativeModuleFake
) -> tuple[MetaTrader5ReadAdapter, Mt5WorkerConfig]:
    # Separate synthetic fixture inspection, never a real terminal confirmation.
    fixture = native_adapter(tmp_path, module)
    fixture.connect(trace_id="fixture")
    try:
        confirmed = fixture.get_symbol_specification("XAUUSD", trace_id="fixture")
    finally:
        fixture.disconnect()
    config = Mt5WorkerConfig(
        terminal_path=tmp_path / "terminal64.exe",
        broker_symbol="XAUUSD",
        expected_account_fingerprint=account_fingerprint(RAW_LOGIN, RAW_SERVER),
        smoke_confirmed_specification_fingerprint=confirmed.specification_fingerprint,
    )
    module.calls.clear()
    return (
        MetaTrader5ReadAdapter(
            config, module=module, platform="win32", clock=lambda: NOW
        ),
        config,
    )


def test_diagnostic_exposes_only_time_scalars_and_preserves_future_block(
    tmp_path: Path,
) -> None:
    module = NativeModuleFake()
    adapter, _ = diagnostic_setup(tmp_path, module)
    future = int(NOW.timestamp()) + 10800
    module.tick_result = SimpleNamespace(
        time=future,
        time_msc=future * 1000 + 123,
        bid=2345.1,
        ask=2345.3,
        account_name="must-not-cross-boundary",
    )
    adapter.connect(trace_id="test")
    try:
        observation = adapter.get_tick_time_diagnostic("XAUUSD", trace_id="test")
        assert observation.native_time == future
        assert observation.native_time_msc == future * 1000 + 123
        assert set(observation.model_dump()) == {
            "observed_at",
            "native_time",
            "native_time_msc",
        }
        assert "must-not-cross-boundary" not in observation.model_dump_json()
        assert module.calls.count("symbol_info_tick") == 1
        assert module.calls.index("account_info") < module.calls.index("symbol_info")
        assert module.calls.index("symbol_info") < module.calls.index(
            "symbol_info_tick"
        )
        assert adapter.get_latest_tick("XAUUSD", trace_id="test").freshness is (
            TickFreshness.FUTURE_INVALID
        )
    finally:
        adapter.disconnect()


@pytest.mark.parametrize("mode", [1, 2, 99])
def test_diagnostic_rejects_non_demo_before_symbol_reads(
    tmp_path: Path, mode: int
) -> None:
    module = NativeModuleFake()
    adapter, _ = diagnostic_setup(tmp_path, module)
    cast(SimpleNamespace, module.account_result).trade_mode = mode
    adapter.connect(trace_id="test")
    try:
        with pytest.raises(Mt5ReadFailure):
            adapter.get_tick_time_diagnostic("XAUUSD", trace_id="test")
        assert "symbol_info" not in module.calls
        assert "symbol_info_tick" not in module.calls
    finally:
        adapter.disconnect()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("expected_account_fingerprint", None, Mt5ReasonCode.DEMO_ACCOUNT_UNBOUND),
        (
            "expected_account_fingerprint",
            "different",
            Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH,
        ),
        (
            "smoke_confirmed_specification_fingerprint",
            None,
            Mt5ReasonCode.SYMBOL_SPEC_CONFIRMATION_REQUIRED,
        ),
        (
            "smoke_confirmed_specification_fingerprint",
            "mt5-spec-v1:different",
            Mt5ReasonCode.SYMBOL_SPEC_CHANGED,
        ),
        ("broker_symbol", None, Mt5ReasonCode.SYMBOL_NOT_CONFIGURED),
    ],
)
def test_diagnostic_requires_existing_bindings(
    tmp_path: Path, field: str, value: str | None, reason: Mt5ReasonCode
) -> None:
    module = NativeModuleFake()
    _, config = diagnostic_setup(tmp_path, module)
    adapter = MetaTrader5ReadAdapter(
        config.model_copy(update={field: value}),
        module=module,
        platform="win32",
        clock=lambda: NOW,
    )
    adapter.connect(trace_id="test")
    try:
        with pytest.raises(Mt5ReadFailure) as error:
            adapter.get_tick_time_diagnostic("XAUUSD", trace_id="test")
        assert error.value.error.reason_code is reason
        assert "symbol_info_tick" not in module.calls
    finally:
        adapter.disconnect()


@pytest.mark.parametrize("value", [True, "123", 1.5, -1, 10**40])
@pytest.mark.parametrize("field", ["time", "time_msc"])
def test_diagnostic_rejects_invalid_time_scalars(
    tmp_path: Path, field: str, value: object
) -> None:
    module = NativeModuleFake()
    adapter, _ = diagnostic_setup(tmp_path, module)
    setattr(module.tick_result, field, value)
    adapter.connect(trace_id="test")
    try:
        with pytest.raises(Mt5ReadFailure) as error:
            adapter.get_tick_time_diagnostic("XAUUSD", trace_id="test")
        assert error.value.error.reason_code is Mt5ReasonCode.TICK_INVALID
    finally:
        adapter.disconnect()


@pytest.mark.parametrize("milliseconds", [None, 0])
def test_diagnostic_keeps_missing_or_zero_milliseconds_explicit(
    tmp_path: Path, milliseconds: int | None
) -> None:
    module = NativeModuleFake()
    adapter, _ = diagnostic_setup(tmp_path, module)
    cast(SimpleNamespace, module.tick_result).time_msc = milliseconds
    adapter.connect(trace_id="test")
    try:
        result = adapter.get_tick_time_diagnostic("XAUUSD", trace_id="test")
        assert result.native_time_msc == milliseconds
    finally:
        adapter.disconnect()


def test_diagnostic_cli_success_is_observation_not_smoke_or_eligibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = NativeModuleFake()
    adapter, config = diagnostic_setup(tmp_path, module)
    cast(SimpleNamespace, module.tick_result).time_msc += 10800123
    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", lambda config: adapter)
    assert mt5_cli._tick_time(config) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "observed"
    assert output["grants_eligibility"] is False
    assert output["smoke_invoked"] is False
    assert output["whole_seconds_agree"] is False
    assert output["future_limit_exceeded"] is True
    assert output["selected_field"] == "time_msc"
    assert output["selected_as_utc"].endswith("00:00")
    assert output["signed_age_seconds"] == "-10800.123"
    assert module.calls[-1] == "shutdown"
    assert module.calls.count("symbol_info_tick") == 1
    assert not {
        "positions_get",
        "orders_get",
        "history_orders_get",
        "copy_rates_from_pos",
    }.intersection(module.calls)
    assert str(RAW_LOGIN) not in json.dumps(output)
    assert RAW_SERVER not in json.dumps(output)
    assert config.expected_account_fingerprint is not None
    assert config.expected_account_fingerprint not in json.dumps(output)


def test_cli_shutdown_failure_discards_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = NativeModuleFake()
    adapter, config = diagnostic_setup(tmp_path, module)
    real_disconnect = adapter.disconnect

    def failing_shutdown() -> None:
        real_disconnect()
        raise RuntimeError("sensitive native detail")

    monkeypatch.setattr(adapter, "disconnect", failing_shutdown)
    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", lambda config: adapter)
    assert mt5_cli._tick_time(config) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["reason"] == "SHUTDOWN_FAILED"
    assert "native_time" not in output
    assert "sensitive" not in json.dumps(output)


def test_cli_requires_bindings_before_constructing_adapter(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected(config: Mt5WorkerConfig) -> MetaTrader5ReadAdapter:
        raise AssertionError("must not construct adapter")

    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", unexpected)
    assert mt5_cli._tick_time(Mt5WorkerConfig()) == 2
    assert (
        json.loads(capsys.readouterr().out)["reason"] == "TERMINAL_PATH_NOT_CONFIGURED"
    )


@pytest.mark.parametrize("offset", [0, 7, -5])
def test_cli_serializes_utc_without_locale_or_offset_shift(
    tmp_path: Path,
    offset: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = NativeModuleFake()
    _, config = diagnostic_setup(tmp_path, module)
    adapter = MetaTrader5ReadAdapter(
        config,
        module=module,
        platform="win32",
        clock=lambda: NOW.astimezone(timezone(timedelta(hours=offset))),
    )
    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", lambda config: adapter)
    assert mt5_cli._tick_time(config) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["worker_utc"] == NOW.astimezone(UTC).isoformat()
    assert output["signed_age_seconds"] == "0.0"


@pytest.mark.parametrize("field", ["visible", "currency_base"])
def test_changed_native_symbol_blocks_diagnostic_tick(
    tmp_path: Path, field: str
) -> None:
    module = NativeModuleFake()
    adapter, _ = diagnostic_setup(tmp_path, module)
    setattr(module.symbol_result, field, False if field == "visible" else "EUR")
    adapter.connect(trace_id="test")
    try:
        with pytest.raises(Mt5ReadFailure):
            adapter.get_tick_time_diagnostic("XAUUSD", trace_id="test")
        assert "symbol_info_tick" not in module.calls
    finally:
        adapter.disconnect()


def test_diagnostic_cannot_read_after_disconnect(tmp_path: Path) -> None:
    module = NativeModuleFake()
    adapter, _ = diagnostic_setup(tmp_path, module)
    adapter.connect(trace_id="test")
    adapter.disconnect()
    calls = module.calls.copy()
    with pytest.raises(Mt5ReadFailure) as error:
        adapter.get_tick_time_diagnostic("XAUUSD", trace_id="test")
    assert error.value.error.reason_code is Mt5ReasonCode.TERMINAL_DISCONNECTED
    assert module.calls == calls


@pytest.mark.parametrize(
    "field", ["max_tick_age_seconds", "max_clock_drift_seconds", "readonly_smoke"]
)
def test_cli_rejects_relaxed_limits_or_smoke_opt_in(
    tmp_path: Path,
    field: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = NativeModuleFake()
    _, config = diagnostic_setup(tmp_path, module)

    def unexpected(config: Mt5WorkerConfig) -> MetaTrader5ReadAdapter:
        raise AssertionError("adapter must not be constructed")

    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", unexpected)
    changed = config.model_copy(
        update={field: True if field == "readonly_smoke" else 300}
    )
    assert mt5_cli._tick_time(changed) == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "CONFIG_INVALID"


def test_main_routes_diagnostic_and_sanitizes_bad_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def invalid_config() -> Mt5WorkerConfig:
        raise ValueError("sensitive raw configuration")

    monkeypatch.setattr(Mt5WorkerConfig, "from_environ", invalid_config)
    assert mt5_cli.main(["tick-time"]) == 3
    output = capsys.readouterr().out
    assert json.loads(output)["reason"] == "CONFIG_INVALID"
    assert "sensitive" not in output


def test_cli_tick_unavailable_shuts_down_and_reports_no_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = NativeModuleFake()
    adapter, config = diagnostic_setup(tmp_path, module)
    module.tick_result = None
    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", lambda config: adapter)
    assert mt5_cli._tick_time(config) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["reason"] == "TICK_UNAVAILABLE"
    assert "native_time" not in output
    assert module.calls[-1] == "shutdown"
