"""Bounded, immutable local replay storage. No network or native dependencies.

The archive is financial research data, not encrypted storage or independently
authenticated source evidence. The caller supplies an explicit local path outside
the checkout. SQLite commits are local only; no remote transaction is implied.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from .replay import ReplayEnvelope, canonical_replay_json, parse_replay_json

MAX_ARCHIVE_ROWS = 10_000
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ENVELOPE_BYTES = 262_144
_APPLICATION_ID = 0x41555233
_SCHEMA_VERSION = 1
_SCHEMA_NAME = "shadow-replay-archive-v1"
_SUFFIX = ".aurum-replay.sqlite3"

type ReplayArchiveCode = Literal[
    "REPLAY_ARCHIVE_UNAVAILABLE",
    "REPLAY_ARCHIVE_INVALID",
    "REPLAY_ARCHIVE_CONFLICT",
    "REPLAY_ARCHIVE_FULL",
]


class ReplayArchiveError(RuntimeError):
    """Only a bounded public code may cross the storage boundary."""

    def __init__(self, code: ReplayArchiveCode) -> None:
        self.code = code
        super().__init__(code)


_METADATA_SQL = """CREATE TABLE archive_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version TEXT NOT NULL CHECK (schema_version = 'shadow-replay-archive-v1'),
    owner_id TEXT NOT NULL,
    trading_account_id TEXT NOT NULL
) STRICT"""
_ENVELOPES_SQL = """CREATE TABLE replay_envelopes (
    cycle_id TEXT PRIMARY KEY NOT NULL,
    cycle_key TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL,
    trading_account_id TEXT NOT NULL,
    envelope_json TEXT NOT NULL CHECK (
        length(CAST(envelope_json AS BLOB)) <= 262144
    ),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64)
) STRICT, WITHOUT ROWID"""
_EXPECTED_SCHEMA = (
    ("table", "archive_metadata", "archive_metadata", _METADATA_SQL),
    ("table", "replay_envelopes", "replay_envelopes", _ENVELOPES_SQL),
    (
        "index",
        "sqlite_autoindex_replay_envelopes_2",
        "replay_envelopes",
        None,
    ),
)
_SELECT_ENVELOPE = (
    "SELECT cycle_id, cycle_key, owner_id, trading_account_id, "
    "envelope_json, payload_sha256 FROM replay_envelopes "
)


def _valid_uuid(value: object) -> bool:
    return (
        isinstance(value, UUID)
        and value.version is not None
        and 1 <= value.version <= 8
    )


def _metadata(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


class SqliteReplayArchive:
    """One owner/account, append-only envelopes, one short connection per operation.

    Construction performs path metadata checks only. A writer creates the archive
    lazily on its first record; directories are never created. Reading never
    creates a file or runs recovery. Concurrent writers are bounded by SQLite's
    short busy timeout, with no application retry or eviction.
    """

    def __init__(
        self,
        path: Path,
        *,
        owner_id: UUID,
        trading_account_id: UUID,
        read_only: bool = False,
    ) -> None:
        if (
            not isinstance(path, Path)
            or not _valid_uuid(owner_id)
            or not _valid_uuid(trading_account_id)
            or type(read_only) is not bool
        ):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        self._path = path
        self._owner_id = owner_id
        self._account_id = trading_account_id
        self._read_only = read_only
        with self._safe_operation():
            self._validate_path(allow_missing=not read_only)

    @staticmethod
    @contextmanager
    def _safe_operation() -> Iterator[None]:
        try:
            yield
        except ReplayArchiveError:
            raise
        except Exception:
            # Filesystem, SQLite and validation details may contain sensitive data.
            raise ReplayArchiveError("REPLAY_ARCHIVE_UNAVAILABLE") from None

    def _validate_path(self, *, allow_missing: bool) -> bool:
        path = self._path
        if (
            not path.is_absolute()
            or ".." in path.parts
            or not path.name.endswith(_SUFFIX)
            or path.name == _SUFFIX
            or ":" in path.name
            or path.anchor.startswith(("\\\\", "//"))
        ):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        for parent in path.parents:
            info = _metadata(parent)
            if info is None or _link(info) or not stat.S_ISDIR(info.st_mode):
                raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
            # Metadata only: no Git commands, file content, or credential discovery.
            if (
                _metadata(parent / ".git") is not None
                or (
                    _metadata(parent / "AGENTS.md") is not None
                    and _metadata(parent / "README_FIRST.md") is not None
                )
                or (
                    _metadata(parent / "package.json") is not None
                    and _metadata(parent / "pnpm-workspace.yaml") is not None
                )
            ):
                raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        for suffix in ("-wal", "-shm", "-journal"):
            if _metadata(path.with_name(path.name + suffix)) is not None:
                # A verifier must not create WAL shared memory or recover journals.
                raise ReplayArchiveError("REPLAY_ARCHIVE_UNAVAILABLE")
        info = _metadata(path)
        if info is None:
            if allow_missing:
                return False
            raise ReplayArchiveError("REPLAY_ARCHIVE_UNAVAILABLE")
        if _link(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        if info.st_size > MAX_ARCHIVE_BYTES:
            raise ReplayArchiveError("REPLAY_ARCHIVE_FULL")
        return True

    def _validate_header(self) -> None:
        with self._path.open("rb") as archive:
            header = archive.read(100)
        if (
            len(header) != 100
            or header[:16] != b"SQLite format 3\x00"
            or header[18:20] != b"\x01\x01"
            or int.from_bytes(header[60:64], "big") != _SCHEMA_VERSION
            or int.from_bytes(header[68:72], "big") != _APPLICATION_ID
        ):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")

    @staticmethod
    def _configure(connection: sqlite3.Connection, *, read_only: bool) -> None:
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_ENVELOPE_BYTES * 2)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 16_384)
        connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 16)
        connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 32)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 8)
        try:
            connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        except sqlite3.NotSupportedError:
            # Older linked SQLite builds still use strict schema/SQL validation.
            pass
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA cache_size = -2048")
        if read_only:
            connection.execute("PRAGMA query_only = ON")
        deadline = time.monotonic() + 2
        steps = 0

        def bounded_progress() -> int:
            nonlocal steps
            steps += 1
            return int(steps > 5_000 or time.monotonic() > deadline)

        connection.set_progress_handler(bounded_progress, 1_000)

    @contextmanager
    def _connection(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        exists = self._validate_path(allow_missing=write)
        created = False
        if not exists:
            # Exclusive creation prevents overwriting even an empty existing file.
            descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(descriptor)
            created = True
            self._validate_path(allow_missing=False)
        else:
            self._validate_header()
        connection = sqlite3.connect(
            self._path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
            uri=True,
            timeout=0.5,
            isolation_level=None,
        )
        try:
            self._configure(connection, read_only=not write)
            if created:
                self._initialize(connection)
            yield connection
        finally:
            # Closing an uncommitted transaction rolls it back, never commits it.
            connection.close()

    def _initialize(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        connection.execute(_METADATA_SQL)
        connection.execute(_ENVELOPES_SQL)
        connection.execute(
            "INSERT INTO archive_metadata VALUES (1, ?, ?, ?)",
            (_SCHEMA_NAME, str(self._owner_id), str(self._account_id)),
        )
        connection.execute("COMMIT")

    def _validate_database(self, connection: sqlite3.Connection) -> int:
        if (
            tuple(
                sorted(
                    connection.execute(
                        "SELECT type, name, tbl_name, sql FROM sqlite_schema LIMIT 4"
                    ),
                    key=lambda row: row[1],
                )
            )
            != _EXPECTED_SCHEMA
            or connection.execute("PRAGMA application_id").fetchone()
            != (_APPLICATION_ID,)
            or connection.execute("PRAGMA user_version").fetchone()
            != (_SCHEMA_VERSION,)
            or connection.execute("PRAGMA journal_mode").fetchone() != ("delete",)
            or tuple(connection.execute("SELECT * FROM archive_metadata LIMIT 2"))
            != ((1, _SCHEMA_NAME, str(self._owner_id), str(self._account_id)),)
        ):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        count, largest = connection.execute(
            "SELECT count(*), max(length(CAST(envelope_json AS BLOB))) "
            "FROM replay_envelopes"
        ).fetchone()
        if count > MAX_ARCHIVE_ROWS:
            raise ReplayArchiveError("REPLAY_ARCHIVE_FULL")
        if largest is not None and largest > MAX_ENVELOPE_BYTES:
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        if (
            connection.execute(
                "SELECT 1 FROM replay_envelopes WHERE owner_id <> ? "
                "OR trading_account_id <> ? LIMIT 1",
                (str(self._owner_id), str(self._account_id)),
            ).fetchone()
            is not None
        ):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        return int(count)

    def _decode(self, row: tuple[object, ...]) -> ReplayEnvelope:
        if len(row) != 6 or any(not isinstance(value, str) for value in row):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        cycle_id, cycle_key, owner_id, account_id, payload, digest = row
        assert isinstance(payload, str)
        encoded = payload.encode("utf-8")
        if (
            len(encoded) > MAX_ENVELOPE_BYTES
            or hashlib.sha256(encoded).hexdigest() != digest
        ):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        try:
            envelope = parse_replay_json(payload)
            if canonical_replay_json(envelope) != payload:
                raise ValueError("noncanonical envelope")
        except Exception:
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID") from None
        cycle = envelope.cycle
        if (
            cycle_id != str(cycle.id)
            or cycle_key != cycle.cycle_key
            or owner_id != str(cycle.owner_id)
            or account_id != str(cycle.trading_account_id)
            or cycle.owner_id != self._owner_id
            or cycle.trading_account_id != self._account_id
        ):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        return envelope

    def record(
        self, envelope: ReplayEnvelope
    ) -> Literal["ARCHIVED", "IDEMPOTENT_REPLAY"]:
        if self._read_only:
            raise ReplayArchiveError("REPLAY_ARCHIVE_UNAVAILABLE")
        with self._safe_operation():
            try:
                payload = canonical_replay_json(envelope)
                encoded = payload.encode("utf-8")
                if len(encoded) > MAX_ENVELOPE_BYTES:
                    raise ValueError("oversize envelope")
                validated = parse_replay_json(payload)
            except Exception:
                raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID") from None
            cycle = validated.cycle
            if (
                cycle.owner_id != self._owner_id
                or cycle.trading_account_id != self._account_id
            ):
                raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
            with self._connection(write=True) as connection:
                connection.execute("PRAGMA synchronous = FULL")
                page_size = connection.execute("PRAGMA page_size").fetchone()[0]
                max_pages = MAX_ARCHIVE_BYTES // page_size
                connection.execute(f"PRAGMA max_page_count = {max_pages}")
                connection.execute("BEGIN IMMEDIATE")
                count = self._validate_database(connection)
                previous = tuple(
                    connection.execute(
                        _SELECT_ENVELOPE
                        + "WHERE cycle_id = ? OR cycle_key = ? LIMIT 2",
                        (str(cycle.id), cycle.cycle_key),
                    )
                )
                if previous:
                    for row in previous:
                        self._decode(row)
                    if len(previous) != 1 or previous[0][4] != payload:
                        raise ReplayArchiveError("REPLAY_ARCHIVE_CONFLICT")
                    connection.execute("ROLLBACK")
                    return "IDEMPOTENT_REPLAY"
                if count >= MAX_ARCHIVE_ROWS:
                    raise ReplayArchiveError("REPLAY_ARCHIVE_FULL")
                connection.execute(
                    "INSERT INTO replay_envelopes VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(cycle.id),
                        cycle.cycle_key,
                        str(cycle.owner_id),
                        str(cycle.trading_account_id),
                        payload,
                        hashlib.sha256(encoded).hexdigest(),
                    ),
                )
                connection.execute("COMMIT")
                return "ARCHIVED"

    def read(self, cycle_id: UUID) -> ReplayEnvelope | None:
        if not _valid_uuid(cycle_id):
            raise ReplayArchiveError("REPLAY_ARCHIVE_INVALID")
        with self._safe_operation():
            if not self._validate_path(allow_missing=not self._read_only):
                return None
            with self._connection(write=False) as connection:
                connection.execute("BEGIN")
                self._validate_database(connection)
                row = connection.execute(
                    _SELECT_ENVELOPE + "WHERE cycle_id = ? LIMIT 1", (str(cycle_id),)
                ).fetchone()
                return None if row is None else self._decode(row)

    def close(self) -> None:
        """Connections are per operation; there is no persistent handle to close."""
