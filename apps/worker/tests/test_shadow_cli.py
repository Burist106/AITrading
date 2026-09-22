from __future__ import annotations

import pytest

from aurum_worker import shadow_cli


def test_no_opt_in_never_builds_runtime(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object) -> None:
        raise AssertionError("configuration must not be read")

    monkeypatch.setattr(shadow_cli, "configured_runtime", forbidden)
    assert shadow_cli.main(["run"]) == 2
    assert "EXPLICIT_READ_ONLY_CONFIRMATION_REQUIRED" in capsys.readouterr().out


@pytest.mark.parametrize("duration", ["0", "-1", "3601"])
def test_duration_bound_precedes_configuration(
    duration: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        shadow_cli.main(
            ["run", "--confirm-demo-read-only", "--duration-seconds", duration]
        )
        == 2
    )
    assert "EXPLICIT_READ_ONLY_CONFIRMATION_REQUIRED" in capsys.readouterr().out


def test_configuration_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable(*args: object) -> None:
        raise ValueError("private test transport detail")

    monkeypatch.setattr(shadow_cli, "configured_runtime", unavailable)
    assert shadow_cli.main(["run", "--confirm-demo-read-only"]) == 2
    output = capsys.readouterr().out
    assert "SHADOW_CONFIGURATION_UNAVAILABLE" in output
    assert "private test" not in output


def test_shutdown_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from types import SimpleNamespace

    def shutdown() -> None:
        raise RuntimeError("private shutdown detail")

    host = SimpleNamespace(
        start=lambda: None,
        stop=shutdown,
        last_result=None,
        poller=SimpleNamespace(state=SimpleNamespace(running=False)),
    )
    monkeypatch.setattr(shadow_cli, "configured_runtime", lambda _values: host)
    assert (
        shadow_cli.main(["run", "--confirm-demo-read-only", "--duration-seconds", "1"])
        == 2
    )
    output = capsys.readouterr().out
    assert (
        "SHADOW_SHUTDOWN_UNAVAILABLE" in output
        and "private shutdown detail" not in output
    )


def test_empty_configuration_never_discovers_profile_or_native_adapter() -> None:
    with pytest.raises(ValueError, match="confirmed Demo binding"):
        shadow_cli.configured_runtime({})


def test_explicit_archive_path_required_before_transport_or_native_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    from shadow_factories import control, market_service

    _, config = market_service()
    config = config.model_copy(update={"terminal_path": Path("C:/test/terminal64.exe")})
    monkeypatch.setattr(
        shadow_cli.Mt5WorkerConfig, "from_environ", lambda _values: config
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("no native/transport without an archive path")

    monkeypatch.setattr(shadow_cli, "MetaTrader5ReadAdapter", forbidden)
    monkeypatch.setattr(shadow_cli, "HttpsWorkerRpcClient", forbidden)
    ctx = control()
    with pytest.raises(KeyError, match="AURUM_SHADOW_REPLAY_PATH"):
        shadow_cli.configured_runtime(
            {
                "AURUM_SHADOW_OWNER_ID": str(ctx.owner_id),
                "AURUM_SHADOW_ACCOUNT_ID": str(ctx.trading_account_id),
            }
        )
