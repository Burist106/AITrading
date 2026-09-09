from __future__ import annotations

from pathlib import Path

import pytest
from mt5_factories import account, fake_adapter, specification
from test_local_mt5_profile import FakeProtection

from aurum_worker import mt5_profile_setup as setup
from aurum_worker.adapters.fake_mt5 import FakeMt5ReadAdapter
from aurum_worker.local_mt5_profile import ProfileError, ProfileStore
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountTradeMode,
    BrokerSymbolCandidate,
    BrokerSymbolObservation,
    Mt5WorkerConfig,
)


class Dialogs:
    def __init__(self, cancel: str = "") -> None:
        self.cancel = cancel
        self.events: list[str] = []

    def confirm_replace(self) -> bool:
        self.events.append("replace")
        return self.cancel != "replace"

    def choose_terminal(self) -> str | None:
        self.events.append("terminal")
        return None if self.cancel == "terminal" else "C:\\Synthetic\\terminal64.exe"

    def confirm_account(self, observation: AccountObservation) -> bool:
        self.events.append("account")
        assert observation.trade_mode is AccountTradeMode.DEMO
        return self.cancel != "account"

    def choose_symbol(self, candidates: list[BrokerSymbolCandidate]) -> str | None:
        self.events.append("symbol")
        assert candidates[0].broker_symbol == "XAUUSD"
        return None if self.cancel == "symbol" else "XAUUSD"

    def confirm_specification(self, observation: BrokerSymbolObservation) -> bool:
        self.events.append("specification")
        return self.cancel != "specification"


class Adapters:
    def __init__(
        self, *, changed_session: int = 0, real: bool = False, shutdown_failure: int = 0
    ) -> None:
        self.instances: list[FakeMt5ReadAdapter] = []
        self.configs: list[Mt5WorkerConfig] = []
        self.changed_session = changed_session
        self.real = real
        self.shutdown_failure = shutdown_failure

    def __call__(self, config: Mt5WorkerConfig) -> FakeMt5ReadAdapter:
        instance = fake_adapter(
            account_modes=(AccountTradeMode.REAL,)
            if self.real
            else (AccountTradeMode.DEMO,)
        )
        instance.specifications["XAUUSD"] = specification("mt5-spec-v1:" + "b" * 64)
        self.instances.append(instance)
        self.configs.append(config)
        if len(self.instances) == self.changed_session:
            instance.specifications["XAUUSD"] = specification("mt5-spec-v1:" + "c" * 64)
        if len(self.instances) == self.shutdown_failure:

            def broken() -> None:
                raise RuntimeError("private shutdown detail")

            instance.disconnect = broken  # type: ignore[method-assign]
        return instance


@pytest.fixture
def valid_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup, "terminal_file_is_valid", lambda value: True)


@pytest.mark.usefixtures("valid_terminal")
def test_setup_requires_two_manual_confirmations_then_fresh_recheck(
    tmp_path: Path,
) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    dialogs = Dialogs()
    adapters = Adapters()
    setup.setup_profile(store, dialogs, adapters)
    assert dialogs.events == ["terminal", "account", "symbol", "specification"]
    assert len(adapters.instances) == 4
    assert adapters.configs[0].expected_account_fingerprint is None
    assert (
        adapters.configs[1].expected_account_fingerprint
        == account().account_fingerprint
    )
    assert (
        adapters.configs[3].smoke_confirmed_specification_fingerprint
        == store.load().specification_fingerprint
    )
    assert all(instance.call_log[-1] == "disconnect" for instance in adapters.instances)
    assert all(
        "get_latest_tick" not in instance.call_log for instance in adapters.instances
    )
    assert not store.load().worker_config().readonly_smoke


@pytest.mark.usefixtures("valid_terminal")
@pytest.mark.parametrize("stage", ["terminal", "account", "symbol", "specification"])
def test_cancel_any_step_never_saves(tmp_path: Path, stage: str) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    adapters = Adapters()
    with pytest.raises(ProfileError, match="PROFILE_CANCELLED"):
        setup.setup_profile(store, Dialogs(stage), adapters)
    assert not store.path.exists()
    assert all(instance.call_log[-1] == "disconnect" for instance in adapters.instances)


@pytest.mark.usefixtures("valid_terminal")
def test_real_account_never_reaches_confirmation_or_symbol(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    dialogs = Dialogs()
    adapters = Adapters(real=True)
    with pytest.raises(ProfileError, match="REAL_ACCOUNT_BLOCKED"):
        setup.setup_profile(store, dialogs, adapters)
    assert dialogs.events == ["terminal"]
    assert not store.path.exists()
    assert "list_symbol_candidates" not in adapters.instances[0].call_log


@pytest.mark.usefixtures("valid_terminal")
def test_changed_spec_after_confirmation_does_not_save(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    with pytest.raises(ProfileError, match="SYMBOL_SPEC_CHANGED"):
        setup.setup_profile(store, Dialogs(), Adapters(changed_session=4))
    assert not store.path.exists()


@pytest.mark.usefixtures("valid_terminal")
@pytest.mark.parametrize("session", [1, 2, 3, 4])
def test_shutdown_failure_prevents_save(tmp_path: Path, session: int) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    with pytest.raises(RuntimeError):
        setup.setup_profile(store, Dialogs(), Adapters(shutdown_failure=session))
    assert not store.path.exists()


@pytest.mark.usefixtures("valid_terminal")
def test_cancelling_replacement_keeps_previous_file(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    setup.setup_profile(store, Dialogs(), Adapters())
    previous = store.path.read_bytes()
    with pytest.raises(ProfileError, match="PROFILE_CANCELLED"):
        setup.setup_profile(store, Dialogs("replace"), Adapters())
    assert store.path.read_bytes() == previous
