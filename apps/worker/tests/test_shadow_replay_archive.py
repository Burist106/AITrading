"""Local replay storage tests use only disposable constructed research evidence."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from mt5_factories import NOW
from shadow_factories import (
    CompleteTestEvidence,
    MemoryJournal,
    control,
    market_service,
)

from aurum_worker.shadow import replay_archive as module
from aurum_worker.shadow.context import risk_input_digest
from aurum_worker.shadow.pipeline import ShadowPipeline
from aurum_worker.shadow.replay import (
    ReplayEnvelope,
    canonical_replay_json,
    make_replay_envelope,
)
from aurum_worker.shadow.replay_archive import ReplayArchiveError, SqliteReplayArchive


@dataclass
class CaptureArchive:
    envelopes: list[ReplayEnvelope] = field(default_factory=list)

    def record(self, envelope: ReplayEnvelope) -> str:
        self.envelopes.append(envelope)
        return "ARCHIVED"


@pytest.fixture
def envelope() -> ReplayEnvelope:
    market, config = market_service()
    context = control()
    archive = CaptureArchive()
    host = ShadowPipeline(
        market,
        MemoryJournal(),
        CompleteTestEvidence(),
        config,
        owner_id=context.owner_id,
        trading_account_id=context.trading_account_id,
        replay_archive=archive,
        clock=lambda: NOW,
    )
    result = host.run_cycle()
    assert result.persistence_code == "CYCLE_RECORDED", result
    assert len(archive.envelopes) == 1
    return archive.envelopes[0]


def archive_at(
    path: Path, envelope: ReplayEnvelope, *, read_only: bool = False
) -> SqliteReplayArchive:
    return SqliteReplayArchive(
        path,
        owner_id=envelope.cycle.owner_id,
        trading_account_id=envelope.cycle.trading_account_id,
        read_only=read_only,
    )


def test_lazy_creation_round_trip_reopen_and_idempotency(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    assert not path.exists()
    assert archive.read(envelope.cycle.id) is None
    assert not path.exists()
    assert archive.record(envelope) == "ARCHIVED"
    archive.close()
    reopened = archive_at(path, envelope)
    assert reopened.read(envelope.cycle.id) == envelope
    assert reopened.record(envelope) == "IDEMPOTENT_REPLAY"
    assert reopened.read(UUID(int=999, version=4)) is None
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM replay_envelopes"
        ).fetchone() == (1,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_changed_content_never_overwrites_existing_envelope(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    archive.record(envelope)
    changed = make_replay_envelope(
        envelope.cycle.model_copy(update={"reason_codes": ("ALTERED_RESEARCH_CLAIM",)}),
        envelope.risk_input,
    )
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_CONFLICT$"):
        archive.record(changed)
    assert archive.read(envelope.cycle.id) == envelope


def test_cycle_key_has_a_separate_unique_constraint(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive_at(path, envelope).record(envelope)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO replay_envelopes SELECT ?, cycle_key, owner_id, "
                "trading_account_id, envelope_json, payload_sha256 "
                "FROM replay_envelopes",
                (str(UUID(int=888, version=4)),),
            )


def test_read_only_is_byte_preserving_and_cannot_record(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive_at(path, envelope).record(envelope)
    before = path.read_bytes()
    before_modified = path.stat().st_mtime_ns
    reader = archive_at(path, envelope, read_only=True)
    assert reader.read(envelope.cycle.id) == envelope
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_UNAVAILABLE$"):
        reader.record(envelope)
    reader.close()
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == before_modified
    assert list(tmp_path.iterdir()) == [path]


def test_read_only_missing_archive_and_parent_never_created(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    missing = tmp_path / "missing.aurum-replay.sqlite3"
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_UNAVAILABLE$"):
        archive_at(missing, envelope, read_only=True)
    absent_parent = tmp_path / "not-created"
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive_at(absent_parent / missing.name, envelope)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "name",
    ["ordinary.sqlite3", ".aurum-replay.sqlite3", "x.aurum-replay.sqlite3-journal"],
)
def test_requires_dedicated_archive_basename(
    tmp_path: Path, envelope: ReplayEnvelope, name: str
) -> None:
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive_at(tmp_path / name, envelope)
    assert not list(tmp_path.iterdir())


def test_relative_and_parent_traversal_paths_rejected(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    for path in (
        Path("local.aurum-replay.sqlite3"),
        tmp_path / ".." / "local.aurum-replay.sqlite3",
    ):
        with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
            archive_at(path, envelope)


@pytest.mark.parametrize(
    "markers",
    [
        (".git",),
        ("AGENTS.md", "README_FIRST.md"),
        ("package.json", "pnpm-workspace.yaml"),
    ],
)
def test_checkout_and_extracted_project_ancestors_rejected(
    tmp_path: Path, envelope: ReplayEnvelope, markers: tuple[str, ...]
) -> None:
    for marker in markers:
        (tmp_path / marker).touch()
    child = tmp_path / "child"
    child.mkdir()
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive_at(child / "test.aurum-replay.sqlite3", envelope)
    assert not list(child.iterdir())


@pytest.mark.parametrize("target", ["parent", "file"])
def test_reparse_metadata_rejected_without_following_target(
    tmp_path: Path,
    envelope: ReplayEnvelope,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    selected = tmp_path if target == "parent" else path
    original = module._metadata

    def reparse(candidate: Path) -> os.stat_result | None:
        if candidate == selected:
            return cast(
                os.stat_result,
                SimpleNamespace(
                    st_mode=stat.S_IFDIR if target == "parent" else stat.S_IFREG,
                    st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                ),
            )
        return original(candidate)

    monkeypatch.setattr(module, "_metadata", reparse)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive_at(path, envelope)
    assert not path.exists()


def test_hardlinked_archive_is_rejected(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive_at(path, envelope).record(envelope)
    alias = tmp_path / "alias.aurum-replay.sqlite3"
    os.link(path, alias)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive_at(alias, envelope)


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
def test_reader_refuses_sidecars_without_recovery(
    tmp_path: Path, envelope: ReplayEnvelope, suffix: str
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive_at(path, envelope).record(envelope)
    sidecar = path.with_name(path.name + suffix)
    sidecar.touch()
    before = path.read_bytes()
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_UNAVAILABLE$"):
        archive_at(path, envelope, read_only=True)
    assert path.read_bytes() == before
    assert sidecar.exists()


@pytest.mark.parametrize("field", ["owner_id", "trading_account_id"])
def test_archive_binding_checked_on_read_and_write(
    tmp_path: Path, envelope: ReplayEnvelope, field: str
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive_at(path, envelope).record(envelope)
    wrong = UUID(int=555, version=4)
    archive = SqliteReplayArchive(
        path,
        owner_id=wrong if field == "owner_id" else envelope.cycle.owner_id,
        trading_account_id=wrong
        if field == "trading_account_id"
        else envelope.cycle.trading_account_id,
    )
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.read(envelope.cycle.id)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.record(envelope)
    assert archive_at(path, envelope).read(envelope.cycle.id) == envelope


@pytest.mark.parametrize(
    "field", ["cycle_key", "cycle_id", "owner_id", "payload_sha256"]
)
def test_corrupt_identity_index_or_digest_rejected(
    tmp_path: Path, envelope: ReplayEnvelope, field: str
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    archive.record(envelope)
    replacement = (
        "c" * 64
        if field in {"cycle_key", "payload_sha256"}
        else str(UUID(int=654, version=4))
    )
    with sqlite3.connect(path) as connection:
        connection.execute(f"UPDATE replay_envelopes SET {field} = ?", (replacement,))
    requested = UUID(replacement) if field == "cycle_id" else envelope.cycle.id
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.read(requested)


def test_valid_json_with_changed_content_and_old_digest_is_rejected(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    archive.record(envelope)
    original = canonical_replay_json(envelope)
    changed = original.replace(envelope.cycle.reason_codes[0], "ALTERED_NOTE")
    assert changed != original
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE replay_envelopes SET envelope_json = ?", (changed,))
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.read(envelope.cycle.id)


def test_whitespace_is_not_an_idempotent_canonical_envelope(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    archive.record(envelope)
    changed = canonical_replay_json(envelope) + " "
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE replay_envelopes SET envelope_json = ?, payload_sha256 = ?",
            (changed, hashlib.sha256(changed.encode()).hexdigest()),
        )
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.read(envelope.cycle.id)


def test_unknown_schema_is_never_migrated_or_written(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive_at(path, envelope).record(envelope)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
    before = path.read_bytes()
    archive = archive_at(path, envelope)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.record(envelope)
    assert path.read_bytes() == before


def test_non_sqlite_existing_file_is_not_replaced(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    path.write_bytes(b"constructed non-database file")
    archive = archive_at(path, envelope)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.record(envelope)
    assert path.read_bytes() == b"constructed non-database file"


def test_row_cap_never_purges_and_exact_replay_is_allowed_at_capacity(
    tmp_path: Path, envelope: ReplayEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    monkeypatch.setattr(module, "MAX_ARCHIVE_ROWS", 0)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_FULL$"):
        archive.record(envelope)
    assert archive.read(envelope.cycle.id) is None
    monkeypatch.setattr(module, "MAX_ARCHIVE_ROWS", 1)
    assert archive.record(envelope) == "ARCHIVED"
    assert archive.record(envelope) == "IDEMPOTENT_REPLAY"
    monkeypatch.setattr(module, "MAX_ARCHIVE_ROWS", 0)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_FULL$"):
        archive.read(envelope.cycle.id)


def test_second_valid_envelope_is_rejected_when_storage_is_full(
    tmp_path: Path, envelope: ReplayEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    assert archive.record(envelope) == "ARCHIVED"
    key = "d" * 64
    identifier = uuid5(NAMESPACE_URL, "aurum:shadow-cycle:" + key)
    candidate_id = uuid5(NAMESPACE_URL, f"aurum:shadow-candidate:{identifier}")
    value = envelope.risk_input.model_copy(
        update={
            "candidate": envelope.risk_input.candidate.model_copy(
                update={"candidate_id": candidate_id}
            )
        }
    )
    candidate, risk = envelope.cycle.candidate, envelope.cycle.risk
    assert candidate is not None and risk is not None
    changed = make_replay_envelope(
        envelope.cycle.model_copy(
            update={
                "id": identifier,
                "cycle_key": key,
                "trace_id": uuid5(NAMESPACE_URL, f"aurum:shadow-trace:{identifier}"),
                "candidate": candidate.model_copy(update={"id": candidate_id}),
                "risk": risk.model_copy(
                    update={"input_digest": risk_input_digest(value)}
                ),
            }
        ),
        value,
    )
    monkeypatch.setattr(module, "MAX_ARCHIVE_ROWS", 1)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_FULL$"):
        archive.record(changed)
    assert archive.read(envelope.cycle.id) == envelope
    assert archive.read(changed.cycle.id) is None


def test_byte_cap_checked_before_opening_or_writing(
    tmp_path: Path, envelope: ReplayEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive_at(path, envelope).record(envelope)
    before = path.read_bytes()
    monkeypatch.setattr(module, "MAX_ARCHIVE_BYTES", 100)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_FULL$"):
        archive_at(path, envelope)
    assert path.read_bytes() == before


def test_oversize_input_fails_before_creating_storage(
    tmp_path: Path, envelope: ReplayEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    monkeypatch.setattr(module, "MAX_ENVELOPE_BYTES", 20)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.record(envelope)
    assert not path.exists()


def test_oversize_existing_payload_fails_without_loading_full_json(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    archive.record(envelope)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE replay_envelopes SET envelope_json = ?",
            ("x" * (module.MAX_ENVELOPE_BYTES + 1),),
        )
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        archive.read(envelope.cycle.id)


def test_wal_header_rejected_before_a_read_can_create_shared_memory(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive_at(path, envelope).record(envelope)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.close()
    assert list(tmp_path.iterdir()) == [path]
    before = path.read_bytes()
    reader = archive_at(path, envelope, read_only=True)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_INVALID$"):
        reader.read(envelope.cycle.id)
    assert list(tmp_path.iterdir()) == [path]
    assert path.read_bytes() == before


def test_commit_failure_rolls_back_complete_envelope_and_reopen_can_retry(
    tmp_path: Path, envelope: ReplayEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    original = archive._validate_database

    def prohibit_commit(
        action: int,
        first: str | None,
        second: str | None,
        database: str | None,
        source: str | None,
    ) -> int:
        return (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT"
            else sqlite3.SQLITE_OK
        )

    def fail_commit(connection: sqlite3.Connection) -> int:
        count = original(connection)
        connection.set_authorizer(prohibit_commit)
        return count

    monkeypatch.setattr(archive, "_validate_database", fail_commit)
    with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_UNAVAILABLE$"):
        archive.record(envelope)
    reopened = archive_at(path, envelope)
    assert reopened.read(envelope.cycle.id) is None
    assert reopened.record(envelope) == "ARCHIVED"
    assert reopened.read(envelope.cycle.id) == envelope


def test_permission_failure_exposes_only_bounded_code_and_never_creates_file(
    tmp_path: Path, envelope: ReplayEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)

    def denied(*args: object, **kwargs: object) -> int:
        raise PermissionError("injected-private-storage-detail")

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(ReplayArchiveError) as caught:
        archive.record(envelope)
    assert str(caught.value) == caught.value.code == "REPLAY_ARCHIVE_UNAVAILABLE"
    assert caught.value.__suppress_context__
    assert not path.exists()


def test_another_writer_has_a_bounded_lock_failure(
    tmp_path: Path, envelope: ReplayEnvelope
) -> None:
    path = tmp_path / "test.aurum-replay.sqlite3"
    archive = archive_at(path, envelope)
    archive.record(envelope)
    with sqlite3.connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(ReplayArchiveError, match="^REPLAY_ARCHIVE_UNAVAILABLE$"):
            archive.record(envelope)
        connection.rollback()
    assert archive.record(envelope) == "IDEMPOTENT_REPLAY"
