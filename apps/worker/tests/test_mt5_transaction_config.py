from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_local_mt5_profile import profile

from aurum_worker import local_mt5_profile, mt5_profile_cli, shadow_cli
from aurum_worker.local_mt5_profile import LocalMt5Profile, ProfileStore
from aurum_worker.models.mt5 import Mt5WorkerConfig
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY, UTC_POLICY
from aurum_worker.mt5_transaction_time import PEPPERSTONE_TRANSACTION_POLICY

POLICY_ENV = "AURUM_MT5_TRANSACTION_TIME_POLICY"
POLICY = PEPPERSTONE_TRANSACTION_POLICY


def bound_environment() -> dict[str, str]:
    saved = profile()
    return {
        "AURUM_MT5_TERMINAL_PATH": saved.terminal_path,
        "AURUM_MT5_BROKER_SYMBOL": saved.broker_symbol,
        "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT": saved.account_fingerprint,
        "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT": (
            saved.specification_fingerprint
        ),
    }


def bound_data() -> dict[str, object]:
    return dict(profile().worker_config().model_dump())


@pytest.mark.parametrize("selection", [None, ""])
def test_environment_absent_or_empty_selection_keeps_legacy_defaults(
    selection: str | None,
) -> None:
    values = bound_environment()
    if selection is not None:
        values[POLICY_ENV] = selection
    config = Mt5WorkerConfig.from_environ(values)
    assert config.market_time_policy == UTC_POLICY
    assert config.transaction_time_policy is None
    assert not config.readonly_smoke
    assert config.max_tick_age_seconds == 10
    assert config.max_clock_drift_seconds == 30


def test_explicit_exact_environment_selection_sets_both_policies() -> None:
    values = {**bound_environment(), POLICY_ENV: POLICY}
    original = values.copy()
    config = Mt5WorkerConfig.from_environ(values)
    assert values == original
    assert config.market_time_policy == PEPPERSTONE_POLICY
    assert config.transaction_time_policy == POLICY
    assert config.terminal_path == Path(values["AURUM_MT5_TERMINAL_PATH"])
    assert config.max_tick_age_seconds == 10
    assert config.max_clock_drift_seconds == 30
    assert not config.readonly_smoke


@pytest.mark.parametrize(
    "selection",
    [
        " ",
        "\t",
        "\n",
        "true",
        "false",
        "1",
        "0",
        "utc_epoch_v1",
        PEPPERSTONE_POLICY,
        POLICY.upper(),
        " " + POLICY,
        POLICY + " ",
        "unknown-private-selection",
    ],
)
def test_environment_selection_is_exact_and_never_coerced(selection: str) -> None:
    with pytest.raises(ValueError):
        Mt5WorkerConfig.from_environ({**bound_environment(), POLICY_ENV: selection})


@pytest.mark.parametrize(
    "field",
    [
        "AURUM_MT5_BROKER_SYMBOL",
        "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT",
        "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT",
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_selection_never_substitutes_for_confirmed_binding(
    field: str, empty: bool
) -> None:
    values = {**bound_environment(), POLICY_ENV: POLICY}
    if empty:
        values[field] = ""
    else:
        del values[field]
    with pytest.raises(ValidationError):
        Mt5WorkerConfig.from_environ(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("AURUM_MT5_MAX_TICK_AGE_SECONDS", "9"),
        ("AURUM_MT5_MAX_TICK_AGE_SECONDS", "11"),
        ("AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS", "29"),
        ("AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS", "31"),
    ],
)
def test_environment_selection_preserves_exact_ten_thirty_limits(
    field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        Mt5WorkerConfig.from_environ(
            {**bound_environment(), POLICY_ENV: POLICY, field: value}
        )


def test_direct_configuration_requires_explicit_paired_market_policy() -> None:
    data = {**bound_data(), "transaction_time_policy": POLICY}
    with pytest.raises(ValidationError):
        Mt5WorkerConfig.model_validate(data)
    data["market_time_policy"] = PEPPERSTONE_POLICY
    config = Mt5WorkerConfig.model_validate(data)
    assert config.transaction_time_policy == POLICY
    assert config.market_time_policy == PEPPERSTONE_POLICY


@pytest.mark.parametrize("invalid", [True, False, 1, 0, "", "unknown", UTC_POLICY])
def test_direct_configuration_rejects_unrecognized_transaction_policy(
    invalid: object,
) -> None:
    with pytest.raises(ValidationError):
        Mt5WorkerConfig.model_validate(
            {
                **bound_data(),
                "market_time_policy": PEPPERSTONE_POLICY,
                "transaction_time_policy": invalid,
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_tick_age_seconds", 11),
        ("max_clock_drift_seconds", 31),
        ("max_tick_age_seconds", "10"),
        ("max_clock_drift_seconds", "30"),
        ("max_tick_age_seconds", True),
        ("max_clock_drift_seconds", True),
        ("max_tick_age_seconds", 10.0),
        ("max_clock_drift_seconds", Decimal("30")),
        ("transaction_time_offset_seconds", 10800),
        ("transaction_time_verified", True),
    ],
)
def test_paired_config_rejects_coercion_relaxed_limits_and_extra_overrides(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        Mt5WorkerConfig.model_validate(
            {
                **bound_data(),
                "market_time_policy": PEPPERSTONE_POLICY,
                "transaction_time_policy": POLICY,
                field: value,
            }
        )


def test_selected_transaction_policy_is_immutable() -> None:
    config = Mt5WorkerConfig.from_environ({**bound_environment(), POLICY_ENV: POLICY})
    with pytest.raises(ValidationError, match="frozen"):
        config.transaction_time_policy = None


@pytest.mark.parametrize("smoke", [False, True])
def test_saved_profile_conversion_never_silently_upgrades_policy(smoke: bool) -> None:
    saved = profile()
    original = saved.model_dump()
    config = saved.worker_config(smoke=smoke)
    assert saved.model_dump() == original
    assert config.market_time_policy == UTC_POLICY
    assert config.transaction_time_policy is None
    assert config.readonly_smoke is smoke


@pytest.mark.parametrize("action", ["status", "check", "tick-time", "smoke"])
@pytest.mark.parametrize("selection", [POLICY, "unknown", " "])
def test_saved_commands_block_environment_policy_before_loading_profile(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
    selection: str,
) -> None:
    # Replace only the process test view; never read a real profile or native SDK.
    monkeypatch.setattr(
        os,
        "environ",
        {
            POLICY_ENV: selection,
            "AURUM_MT5_READONLY_SMOKE": "1" if action == "smoke" else "0",
        },
    )

    def forbidden_store() -> ProfileStore:
        raise AssertionError("conflicting policy must be rejected before profile load")

    def forbidden_verification(saved: LocalMt5Profile) -> None:
        raise AssertionError("conflicting policy must not reach native verification")

    monkeypatch.setattr(mt5_profile_cli, "ProfileStore", forbidden_store)
    monkeypatch.setattr(mt5_profile_cli, "verify_saved_binding", forbidden_verification)
    assert mt5_profile_cli.run_saved(action) == 2
    output = capsys.readouterr().out
    assert "PROFILE_ENV_CONFLICT" in output
    assert POLICY not in output
    assert "unknown" not in output


@pytest.mark.parametrize("selection", [None, ""])
def test_empty_environment_selection_does_not_conflict_with_profile(
    monkeypatch: pytest.MonkeyPatch, selection: str | None
) -> None:
    values = {} if selection is None else {POLICY_ENV: selection}
    monkeypatch.setattr(os, "environ", values)
    local_mt5_profile.reject_binding_environment()


def test_shadow_composition_preserves_opt_in_policy_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        **bound_environment(),
        POLICY_ENV: POLICY,
        "AURUM_SHADOW_OWNER_ID": "11111111-1111-4111-8111-111111111111",
        "AURUM_SHADOW_ACCOUNT_ID": "22222222-2222-4222-8222-222222222222",
        "AURUM_SHADOW_REPLAY_PATH": "C:/synthetic/archive.sqlite3",
        "AURUM_SHADOW_SUPABASE_URL": "https://synthetic.invalid",
        "AURUM_SHADOW_WORKER_TOKEN": "synthetic-only",
        "AURUM_SHADOW_PUBLISHABLE_KEY": "synthetic-only",
    }
    created_configs: list[Mt5WorkerConfig] = []
    composed_configs: list[Mt5WorkerConfig] = []
    native, rpc, archive, runtime = object(), object(), object(), object()

    def fake_native(config: Mt5WorkerConfig) -> object:
        created_configs.append(config)
        return native

    def fake_rpc(*args: object, **kwargs: object) -> object:
        return rpc

    def fake_archive(*args: object, **kwargs: object) -> object:
        return archive

    def fake_runtime(
        mt5: object, transport: object, config: Mt5WorkerConfig, **kwargs: object
    ) -> object:
        assert mt5 is native
        assert transport is rpc
        assert kwargs["replay_archive"] is archive
        composed_configs.append(config)
        return runtime

    monkeypatch.setattr(shadow_cli, "MetaTrader5ReadAdapter", fake_native)
    monkeypatch.setattr(shadow_cli, "HttpsWorkerRpcClient", fake_rpc)
    monkeypatch.setattr(shadow_cli, "SqliteReplayArchive", fake_archive)
    monkeypatch.setattr(shadow_cli, "ShadowRuntime", fake_runtime)
    assert shadow_cli.configured_runtime(values) is runtime
    assert len(created_configs) == 1
    assert composed_configs == created_configs
    config = created_configs[0]
    assert config.market_time_policy == PEPPERSTONE_POLICY
    assert config.transaction_time_policy == POLICY
    assert config.tick_poll_seconds == Decimal("1")
    assert config.full_reconciliation_seconds == Decimal("60")
    assert config.max_tick_age_seconds == 10
    assert config.max_clock_drift_seconds == 30
    assert not config.readonly_smoke
