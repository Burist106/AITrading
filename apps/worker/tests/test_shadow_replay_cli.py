from __future__ import annotations

import builtins
import importlib
from pathlib import Path
from typing import Any

import pytest
from shadow_factories import MemoryReplayArchive, control
from test_shadow_pipeline import pipeline

from aurum_worker import shadow_replay_cli
from aurum_worker.shadow.replay_archive import SqliteReplayArchive


def arguments(path: Path) -> list[str]:
    ctx = control()
    host, _ = pipeline()
    cycle = host.run_cycle().cycle
    assert cycle is not None
    return [
        "--archive",
        str(path),
        "--owner-id",
        str(ctx.owner_id),
        "--account-id",
        str(ctx.trading_account_id),
        "--cycle-id",
        str(cycle.id),
    ]


def test_replay_cli_checks_saved_input_without_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    host, _ = pipeline()
    cycle = host.run_cycle().cycle
    assert cycle is not None and isinstance(host.replay_archive, MemoryReplayArchive)
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = SqliteReplayArchive(
        path, owner_id=cycle.owner_id, trading_account_id=cycle.trading_account_id
    )
    archive.record(host.replay_archive.envelopes[cycle.id])

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("no environment access")

    # Replay composition does not even need the runtime's environment config.
    monkeypatch.setattr("os.getenv", forbidden)
    assert shadow_replay_cli.main(arguments(path)) == 0
    output = capsys.readouterr().out
    assert "REPLAY: MATCH" in output and "LOCAL HISTORICAL CHECK ONLY" in output
    assert str(cycle.owner_id) not in output and str(path) not in output


def test_missing_archive_is_unavailable_and_never_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "missing.aurum-replay.sqlite3"
    assert shadow_replay_cli.main(arguments(path)) == 2
    assert "UNAVAILABLE" in capsys.readouterr().out
    assert not path.exists()


def test_cli_import_does_not_load_native_network_or_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in {"MetaTrader5", "socket", "http.client"} or any(
            part in name for part in ("native_mt5", "worker_http", "local_mt5_profile")
        ):
            raise AssertionError("replay cannot import native/network/profile")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(shadow_replay_cli)


def test_cli_failure_does_not_echo_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable(*args: object, **kwargs: object) -> None:
        raise RuntimeError("private financial evidence test detail")

    monkeypatch.setattr(shadow_replay_cli, "SqliteReplayArchive", unavailable)
    assert (
        shadow_replay_cli.main(arguments(tmp_path / "test.aurum-replay.sqlite3")) == 2
    )
    output = capsys.readouterr().out
    assert "UNAVAILABLE" in output and "private financial" not in output


@pytest.mark.parametrize("status,expected", [("MISMATCH", 1), ("UNAVAILABLE", 2)])
def test_cli_nonmatching_verification_exit_codes(
    status: str,
    expected: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from types import SimpleNamespace

    host, _ = pipeline()
    cycle = host.run_cycle().cycle
    assert cycle is not None and isinstance(host.replay_archive, MemoryReplayArchive)
    envelope = host.replay_archive.envelopes[cycle.id]
    monkeypatch.setattr(
        shadow_replay_cli,
        "SqliteReplayArchive",
        lambda *args, **kwargs: SimpleNamespace(read=lambda _cycle: envelope),
    )
    monkeypatch.setattr(
        shadow_replay_cli,
        "verify_replay",
        lambda *args, **kwargs: SimpleNamespace(status=status, code="REPLAY_INVALID"),
    )
    assert (
        shadow_replay_cli.main(arguments(tmp_path / "test.aurum-replay.sqlite3"))
        == expected
    )
    assert f"REPLAY: {status}" in capsys.readouterr().out
