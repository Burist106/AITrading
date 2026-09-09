from __future__ import annotations

from pathlib import Path

import pytest
from mt5_factories import account
from test_local_mt5_profile import FakeProtection, profile
from test_mt5_profile_setup import Adapters

from aurum_worker import mt5_cli
from aurum_worker import mt5_profile_cli as cli
from aurum_worker.local_mt5_profile import LocalMt5Profile, ProfileError, ProfileStore
from aurum_worker.models.mt5 import AccountTradeMode, Mt5WorkerConfig
from aurum_worker.mt5_profile_setup import verify_saved_binding


@pytest.fixture(autouse=True)
def clean_profile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AURUM_MT5_TERMINAL_PATH",
        "AURUM_MT5_BROKER_SYMBOL",
        "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT",
        "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT",
        "AURUM_MT5_MAX_TICK_AGE_SECONDS",
        "AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS",
        "AURUM_MT5_READONLY_SMOKE",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def saved_store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    saved = profile().model_copy(
        update={"account_fingerprint": account().account_fingerprint}
    )
    store.save(saved, expected_revision=None)
    return store


def test_saved_check_after_restart_is_not_smoke(
    saved_store: ProfileStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapters = Adapters()
    monkeypatch.setattr(
        cli, "verify_saved_binding", lambda saved: verify_saved_binding(saved, adapters)
    )
    assert cli.run_saved("check", saved_store) == 0
    assert "NOT SMOKE" in capsys.readouterr().out
    assert adapters.instances[0].call_log == [
        "connect",
        "get_account_info",
        "get_symbol_specification",
        "disconnect",
    ]


@pytest.mark.parametrize(
    "mode", [AccountTradeMode.REAL, AccountTradeMode.CONTEST, AccountTradeMode.UNKNOWN]
)
def test_saved_profile_never_allows_non_demo(
    saved_store: ProfileStore, monkeypatch: pytest.MonkeyPatch, mode: AccountTradeMode
) -> None:
    adapters = Adapters()
    adapter = adapters(saved_store.load().worker_config())
    adapter.accounts = (account(mode),)
    monkeypatch.setattr(
        cli,
        "verify_saved_binding",
        lambda saved: verify_saved_binding(saved, lambda config: adapter),
    )
    before = saved_store.path.read_bytes()
    assert cli.run_saved("check", saved_store) == 2
    assert "get_symbol_specification" not in adapter.call_log
    assert saved_store.path.read_bytes() == before


@pytest.mark.parametrize("changed", ["account", "specification"])
def test_mismatch_never_rebinds(
    saved_store: ProfileStore, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    adapters = Adapters(changed_session=1 if changed == "specification" else 0)
    adapter = adapters(saved_store.load().worker_config())
    if changed == "account":
        adapter.accounts = (
            account().model_copy(
                update={"account_fingerprint": "mt5-account-v1:" + "d" * 64}
            ),
        )
    monkeypatch.setattr(
        cli,
        "verify_saved_binding",
        lambda saved: verify_saved_binding(saved, lambda config: adapter),
    )
    before = saved_store.path.read_bytes()
    assert cli.run_saved("check", saved_store) == 2
    assert saved_store.path.read_bytes() == before
    assert "get_latest_tick" not in adapter.call_log


@pytest.mark.parametrize(
    "name",
    [
        "AURUM_MT5_TERMINAL_PATH",
        "AURUM_MT5_BROKER_SYMBOL",
        "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT",
        "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT",
        "AURUM_MT5_MAX_TICK_AGE_SECONDS",
        "AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS",
        "AURUM_MT5_READONLY_SMOKE",
    ],
)
def test_no_environment_profile_blending_or_relaxed_limits(
    saved_store: ProfileStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    monkeypatch.setenv(name, "private-invalid-value")
    calls: list[LocalMt5Profile] = []
    monkeypatch.setattr(cli, "verify_saved_binding", calls.append)
    assert cli.run_saved("check", saved_store) == 2
    assert not calls
    assert "private-invalid-value" not in capsys.readouterr().out


def test_profile_cannot_enable_smoke_by_existence(
    saved_store: ProfileStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected() -> LocalMt5Profile:
        raise AssertionError("profile must not be read without opt-in")

    monkeypatch.setattr(saved_store, "load", unexpected)
    assert cli.run_saved("smoke", saved_store) == 0
    assert capsys.readouterr().out.startswith("NOT RUN")


def test_tick_diagnostic_receives_only_remembered_binding_defaults(
    saved_store: ProfileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Mt5WorkerConfig] = []

    def diagnostic(config: Mt5WorkerConfig) -> int:
        calls.append(config)
        return 2

    monkeypatch.setattr(mt5_cli, "_tick_time", diagnostic)
    assert cli.run_saved("tick-time", saved_store) == 2
    assert len(calls) == 1
    assert calls[0] == saved_store.load().worker_config()
    assert not calls[0].readonly_smoke


def test_explicit_smoke_rechecks_profile_before_workflow(
    saved_store: ProfileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", "1")
    events: list[str] = []

    def verified(saved: LocalMt5Profile) -> None:
        events.append("verified")

    def smoke(config: Mt5WorkerConfig) -> int:
        assert config.readonly_smoke
        events.append("smoke")
        return 2

    monkeypatch.setattr(cli, "verify_saved_binding", verified)
    monkeypatch.setattr(mt5_cli, "_smoke", smoke)
    assert cli.run_saved("smoke", saved_store) == 2
    assert events == ["verified", "smoke"]
    assert not saved_store.load().worker_config().readonly_smoke


def test_corrupt_profile_does_not_fall_back_to_native(
    saved_store: ProfileStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    saved_store.path.write_bytes(b"damaged")
    calls: list[LocalMt5Profile] = []
    monkeypatch.setattr(cli, "verify_saved_binding", calls.append)
    assert cli.run_saved("check", saved_store) == 3
    assert "PROFILE_UNREADABLE" in capsys.readouterr().out
    assert not calls


def test_status_is_not_current_verification(
    saved_store: ProfileStore, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.run_saved("status", saved_store) == 0
    assert "NOT VERIFIED; NOT SMOKE" in capsys.readouterr().out


def test_unknown_exception_details_are_not_exposed() -> None:
    assert cli.safe_reason(RuntimeError("private detail")) == "PROFILE_FAILED"
    assert cli.safe_reason(ProfileError("private detail")) == "PROFILE_FAILED"
