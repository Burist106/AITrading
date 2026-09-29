"""Separate manual setup transaction. Observations never confirm themselves."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Protocol

from aurum_worker.adapters.native_mt5 import MetaTrader5ReadAdapter
from aurum_worker.adapters.protocols import Mt5ReadPort
from aurum_worker.local_mt5_profile import LocalMt5Profile, ProfileError, ProfileStore
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountVerificationState,
    BrokerSymbolCandidate,
    BrokerSymbolObservation,
    Mt5WorkerConfig,
    SymbolUsabilityState,
)
from aurum_worker.mt5_safety import is_canonical_xauusd, verify_account

AdapterFactory = Callable[[Mt5WorkerConfig], Mt5ReadPort]


class SetupDialogs(Protocol):
    def confirm_replace(self) -> bool: ...
    def choose_terminal(self) -> str | None: ...
    def confirm_account(self, account: AccountObservation) -> bool: ...
    def choose_symbol(self, candidates: list[BrokerSymbolCandidate]) -> str | None: ...
    def confirm_specification(self, specification: BrokerSymbolObservation) -> bool: ...


def _verified_account(
    adapter: Mt5ReadPort, config: Mt5WorkerConfig, *, allow_unbound: bool = False
) -> AccountObservation:
    account = adapter.get_account_info(trace_id="local-profile")
    verification = verify_account(account, config.expected_account_fingerprint)
    allowed = {AccountVerificationState.VERIFIED_DEMO_BOUND}
    if allow_unbound:
        allowed.add(AccountVerificationState.VERIFIED_DEMO_UNBOUND)
    if verification.state not in allowed:
        raise ProfileError(verification.reason_code.value)
    return account


def _usable_specification(adapter: Mt5ReadPort, symbol: str) -> BrokerSymbolObservation:
    observation = adapter.get_symbol_specification(symbol, trace_id="local-profile")
    if not is_canonical_xauusd(
        observation.canonical_symbol,
        observation.base_currency,
        observation.profit_currency,
    ):
        raise ProfileError("SYMBOL_CANONICAL_MISMATCH")
    if observation.usability_state is not SymbolUsabilityState.USABLE:
        raise ProfileError("SYMBOL_SPEC_INCOMPLETE")
    if observation.broker_symbol != symbol:
        raise ProfileError("SYMBOL_CANONICAL_MISMATCH")
    return observation


def verify_saved_binding(
    profile: LocalMt5Profile, factory: AdapterFactory = MetaTrader5ReadAdapter
) -> None:
    config = profile.worker_config()
    adapter = factory(config)
    try:
        adapter.connect(trace_id="local-profile")
        _verified_account(adapter, config)
        specification = _usable_specification(adapter, profile.broker_symbol)
        if specification.specification_fingerprint != profile.specification_fingerprint:
            raise ProfileError("SYMBOL_SPEC_CHANGED")
    finally:
        adapter.disconnect()


def terminal_file_is_valid(value: str) -> bool:
    path = PureWindowsPath(value)
    return (
        path.is_absolute()
        and len(path.drive) == 2
        and path.name.lower() == "terminal64.exe"
        and Path(value).is_file()
    )


def setup_profile(
    store: ProfileStore,
    dialogs: SetupDialogs,
    factory: AdapterFactory = MetaTrader5ReadAdapter,
) -> None:
    revision = store.revision()
    if revision is not None and not dialogs.confirm_replace():
        raise ProfileError("PROFILE_CANCELLED")
    terminal_path = dialogs.choose_terminal()
    if terminal_path is None:
        raise ProfileError("PROFILE_CANCELLED")
    if not terminal_file_is_valid(terminal_path):
        raise ProfileError("TERMINAL_NOT_FOUND")
    config = Mt5WorkerConfig(terminal_path=Path(terminal_path))
    adapter = factory(config)
    try:
        adapter.connect(trace_id="local-profile")
        account = _verified_account(adapter, config, allow_unbound=True)
    finally:
        adapter.disconnect()
    if not dialogs.confirm_account(account):
        raise ProfileError("PROFILE_CANCELLED")
    account_confirmed_at = datetime.now(UTC)
    config = config.model_copy(
        update={"expected_account_fingerprint": account.account_fingerprint}
    )
    adapter = factory(config)
    try:
        adapter.connect(trace_id="local-profile")
        _verified_account(adapter, config)
        candidates = adapter.list_symbol_candidates(trace_id="local-profile")
    finally:
        adapter.disconnect()
    eligible = [
        candidate
        for candidate in candidates
        if candidate.base_currency == "XAU"
        and candidate.profit_currency == "USD"
        and candidate.visible
    ]
    if not eligible:
        raise ProfileError("SYMBOL_NOT_VISIBLE")
    symbol = dialogs.choose_symbol(eligible)
    if symbol is None:
        raise ProfileError("PROFILE_CANCELLED")
    if symbol not in {candidate.broker_symbol for candidate in eligible}:
        raise ProfileError("SYMBOL_NOT_CONFIGURED")
    config = config.model_copy(update={"broker_symbol": symbol})
    adapter = factory(config)
    try:
        adapter.connect(trace_id="local-profile")
        _verified_account(adapter, config)
        specification = _usable_specification(adapter, symbol)
    finally:
        adapter.disconnect()
    if not dialogs.confirm_specification(specification):
        raise ProfileError("PROFILE_CANCELLED")
    profile = LocalMt5Profile(
        terminal_path=terminal_path,
        broker_symbol=symbol,
        account_fingerprint=account.account_fingerprint,
        specification_fingerprint=specification.specification_fingerprint,
        account_confirmed_at=account_confirmed_at,
        specification_confirmed_at=datetime.now(UTC),
    )
    # A separate connection rechecks the approved values after both manual actions.
    # No write occurs if account/specification drifted or any shutdown failed.
    verify_saved_binding(profile, factory)
    store.save(profile, expected_revision=revision)
