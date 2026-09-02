from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from mt5_factories import account, fake_adapter, specification

from aurum_worker import mt5_cli
from aurum_worker.adapters.fake_mt5 import FakeMt5ReadAdapter
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    HealthState,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReconciliationOutcome,
    TickFreshness,
)


class ReconciliationStub:
    def __init__(
        self,
        *,
        outcome: ReconciliationOutcome = ReconciliationOutcome.MATCHED,
        health_state: HealthState = HealthState.HEALTHY,
        reason: Mt5ReasonCode = Mt5ReasonCode.HEALTHY,
    ) -> None:
        self._result = SimpleNamespace(
            report=SimpleNamespace(outcome=outcome),
            health=SimpleNamespace(state=health_state, reason_code=reason),
        )

    def run(self, *, trace_id: str) -> SimpleNamespace:
        assert trace_id == "local-readonly-smoke"
        return self._result


def smoke_config(
    terminal_path: Path | None,
    *,
    enabled: bool = True,
    broker_symbol: str | None = "XAUUSD",
    mode: AccountTradeMode = AccountTradeMode.DEMO,
    bound: bool = True,
    confirmed_specification_fingerprint: str | None = "mt5-spec-v1:fixture",
) -> Mt5WorkerConfig:
    return Mt5WorkerConfig(
        terminal_path=terminal_path,
        broker_symbol=broker_symbol,
        expected_account_fingerprint=(
            account(mode).account_fingerprint if bound else None
        ),
        smoke_confirmed_specification_fingerprint=(confirmed_specification_fingerprint),
        readonly_smoke=enabled,
    )


def install_smoke_doubles(
    monkeypatch: pytest.MonkeyPatch,
    adapter: FakeMt5ReadAdapter,
    reconciliation: ReconciliationStub | None = None,
) -> None:
    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", lambda config: adapter)
    stub = reconciliation or ReconciliationStub()
    monkeypatch.setattr(
        mt5_cli,
        "ReadOnlyReconciliationService",
        lambda adapter, persistence, config: stub,
    )


@pytest.mark.parametrize(
    ("enabled", "has_path"),
    [(False, True), (True, False)],
)
def test_smoke_is_not_run_only_before_start_when_flag_or_path_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    enabled: bool,
    has_path: bool,
) -> None:
    def unexpected_adapter(config: Mt5WorkerConfig) -> object:
        raise AssertionError(f"adapter must not start: {config.readonly_smoke}")

    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", unexpected_adapter)
    path = tmp_path / "terminal64.exe" if has_path else None

    result = mt5_cli._smoke(smoke_config(path, enabled=enabled))

    assert result == 0
    assert capsys.readouterr().out.strip() == (
        "NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET"
    )


@pytest.mark.parametrize(
    ("flag", "path"),
    [(None, "C:/MT5/terminal64.exe"), ("0", "C:/MT5/terminal64.exe"), ("1", None)],
)
def test_main_smoke_not_run_preconditions_bypass_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag: str | None,
    path: str | None,
) -> None:
    if flag is None:
        monkeypatch.delenv("AURUM_MT5_READONLY_SMOKE", raising=False)
    else:
        monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", flag)
    if path is None:
        monkeypatch.delenv("AURUM_MT5_TERMINAL_PATH", raising=False)
    else:
        monkeypatch.setenv("AURUM_MT5_TERMINAL_PATH", path)

    def invalid_config() -> Mt5WorkerConfig:
        raise AssertionError("configuration must not be parsed before NOT RUN")

    monkeypatch.setattr(Mt5WorkerConfig, "from_environ", invalid_config)

    assert mt5_cli.main(["smoke"]) == 0
    assert capsys.readouterr().out.strip() == (
        "NOT RUN — REAL MT5 READ-ONLY SMOKE PRECONDITIONS NOT MET"
    )


def test_smoke_missing_symbol_is_blocked_not_not_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = mt5_cli._smoke(
        smoke_config(tmp_path / "terminal64.exe", broker_symbol=None)
    )

    assert result == 2
    assert capsys.readouterr().out.strip() == "BLOCKED — SYMBOL_NOT_CONFIGURED"


@pytest.mark.parametrize(
    "reason",
    [
        Mt5ReasonCode.MT5_PACKAGE_NOT_INSTALLED,
        Mt5ReasonCode.INITIALIZE_FAILED,
    ],
)
def test_opted_in_smoke_startup_failure_is_technical_and_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reason: Mt5ReasonCode,
) -> None:
    adapter = fake_adapter()
    adapter.failures["connect"] = reason
    install_smoke_doubles(monkeypatch, adapter)

    result = mt5_cli._smoke(smoke_config(tmp_path / "terminal64.exe"))

    assert result == 3
    assert capsys.readouterr().out.strip() == f"FAILED — {reason.value}"
    assert adapter.call_log[-1] == "disconnect"


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        (AccountTradeMode.REAL, Mt5ReasonCode.REAL_ACCOUNT_BLOCKED),
        (AccountTradeMode.CONTEST, Mt5ReasonCode.CONTEST_ACCOUNT_BLOCKED),
    ],
)
def test_opted_in_smoke_non_demo_account_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: AccountTradeMode,
    reason: Mt5ReasonCode,
) -> None:
    adapter = fake_adapter(account_modes=(mode,))
    install_smoke_doubles(monkeypatch, adapter)

    result = mt5_cli._smoke(smoke_config(tmp_path / "terminal64.exe", mode=mode))

    assert result == 2
    assert capsys.readouterr().out.strip() == f"BLOCKED — {reason.value}"
    assert "get_symbol_specification" not in adapter.call_log
    assert adapter.call_log[-1] == "disconnect"


def test_opted_in_smoke_requires_demo_account_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = fake_adapter()
    install_smoke_doubles(monkeypatch, adapter)

    result = mt5_cli._smoke(smoke_config(tmp_path / "terminal64.exe", bound=False))

    assert result == 2
    assert capsys.readouterr().out.strip() == "BLOCKED — DEMO_ACCOUNT_UNBOUND"
    assert adapter.call_log[-1] == "disconnect"


def test_opted_in_smoke_wrong_symbol_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = fake_adapter()
    adapter.failures["get_symbol_specification"] = (
        Mt5ReasonCode.SYMBOL_CANONICAL_MISMATCH
    )
    install_smoke_doubles(monkeypatch, adapter)

    result = mt5_cli._smoke(smoke_config(tmp_path / "terminal64.exe"))

    assert result == 2
    assert capsys.readouterr().out.strip() == ("BLOCKED — SYMBOL_CANONICAL_MISMATCH")
    assert adapter.call_log[-1] == "disconnect"


@pytest.mark.parametrize(
    ("freshness", "reason"),
    [
        (TickFreshness.DELAYED, Mt5ReasonCode.TICK_DELAYED),
        (TickFreshness.STALE, Mt5ReasonCode.TICK_STALE),
        (TickFreshness.FUTURE_INVALID, Mt5ReasonCode.TICK_FROM_FUTURE),
    ],
)
def test_opted_in_smoke_non_live_tick_is_blocked_with_exact_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    freshness: TickFreshness,
    reason: Mt5ReasonCode,
) -> None:
    adapter = fake_adapter(freshness=freshness)
    install_smoke_doubles(monkeypatch, adapter)

    result = mt5_cli._smoke(smoke_config(tmp_path / "terminal64.exe"))

    assert result == 2
    assert capsys.readouterr().out.strip() == f"BLOCKED — {reason.value}"
    assert adapter.call_log[-1] == "disconnect"


def test_opted_in_smoke_reconciliation_mismatch_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = fake_adapter()
    reconciliation = ReconciliationStub(
        outcome=ReconciliationOutcome.MISMATCH,
        health_state=HealthState.BLOCKED,
        reason=Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
    )
    install_smoke_doubles(monkeypatch, adapter, reconciliation)

    result = mt5_cli._smoke(smoke_config(tmp_path / "terminal64.exe"))

    assert result == 2
    assert capsys.readouterr().out.strip() == ("BLOCKED — RECONCILIATION_INCOMPLETE")
    assert adapter.call_log[-1] == "disconnect"


def test_healthy_opted_in_smoke_passes_only_after_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = fake_adapter()
    install_smoke_doubles(monkeypatch, adapter)

    result = mt5_cli._smoke(smoke_config(tmp_path / "terminal64.exe"))

    assert result == 0
    assert capsys.readouterr().out.strip() == "PASSED — REAL MT5 READ-ONLY SMOKE"
    assert adapter.call_log[-1] == "disconnect"
    assert {
        "connect",
        "get_account_info",
        "get_symbol_specification",
        "get_latest_tick",
        "get_candles",
        "get_open_positions",
        "get_active_orders",
        "get_order_history",
        "get_deal_history",
        "disconnect",
    }.issubset(adapter.call_log)


def test_real_reconciler_accepts_only_explicit_smoke_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = fake_adapter()
    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", lambda config: adapter)

    result = mt5_cli._smoke(
        smoke_config(
            tmp_path / "terminal64.exe",
            confirmed_specification_fingerprint=(
                specification().specification_fingerprint
            ),
        )
    )

    assert result == 0
    assert capsys.readouterr().out.strip() == "PASSED — REAL MT5 READ-ONLY SMOKE"
    assert adapter.call_log.count("get_order_history") == 2
    assert adapter.call_log.count("get_deal_history") == 2
    assert adapter.call_log[-1] == "disconnect"


def test_real_reconciler_blocks_when_smoke_confirmation_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = fake_adapter()
    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", lambda config: adapter)

    result = mt5_cli._smoke(
        smoke_config(
            tmp_path / "terminal64.exe",
            confirmed_specification_fingerprint=None,
        )
    )

    assert result == 2
    assert capsys.readouterr().out.strip() == (
        "BLOCKED — SYMBOL_SPEC_CONFIRMATION_REQUIRED"
    )
    assert adapter.call_log[-1] == "disconnect"


def test_smoke_configuration_failure_is_safe_and_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", "1")
    monkeypatch.setenv("AURUM_MT5_TERMINAL_PATH", "C:/MT5/terminal64.exe")

    def invalid_config() -> Mt5WorkerConfig:
        raise ValueError("sensitive raw configuration detail")

    monkeypatch.setattr(Mt5WorkerConfig, "from_environ", invalid_config)

    result = mt5_cli.main(["smoke"])

    assert result == 3
    output = capsys.readouterr().out.strip()
    assert output == "FAILED — CONFIG_INVALID"
    assert "sensitive" not in output


def test_smoke_setup_failure_is_safe_and_conditionally_disconnects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter = fake_adapter()
    monkeypatch.setattr(mt5_cli, "MetaTrader5ReadAdapter", lambda config: adapter)

    def persistence_failure(*args: object, **kwargs: object) -> object:
        raise RuntimeError("sensitive raw setup detail")

    monkeypatch.setattr(
        mt5_cli, "InMemoryMt5ObservationPersistence", persistence_failure
    )

    result = mt5_cli._smoke(smoke_config(tmp_path / "terminal64.exe"))

    assert result == 3
    output = capsys.readouterr().out.strip()
    assert output == "FAILED — UNEXPECTED_ERROR"
    assert "sensitive" not in output
    assert adapter.call_log == ["disconnect"]
