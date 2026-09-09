"""Explicitly confirmed local binding. Never credentials or a cached health result."""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
import sys
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from aurum_worker.adapters.windows_protection import (
    MAX_PROTECTED_BYTES,
    WindowsDataProtection,
)
from aurum_worker.models.mt5 import Mt5WorkerConfig

_MAGIC = b"AURUM-DEMO-PROFILE-V1\x00"
_BINDING_ENV = (
    "AURUM_MT5_TERMINAL_PATH",
    "AURUM_MT5_BROKER_SYMBOL",
    "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT",
    "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT",
)


class ProfileError(Exception):
    """Only bounded codes supplied by this module cross the CLI boundary."""


class Protection(Protocol):
    def protect(self, data: bytes) -> bytes: ...
    def unprotect(self, data: bytes) -> bytes: ...


class LocalMt5Profile(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    schema_version: Literal[1] = 1
    environment: Literal["DEMO_ONLY"] = "DEMO_ONLY"
    runtime_mode: Literal["SHADOW"] = "SHADOW"
    terminal_path: Annotated[str, Field(min_length=1, max_length=1024, repr=False)]
    broker_symbol: Annotated[
        str,
        Field(min_length=1, max_length=160, pattern=r"^[^\x00-\x1f\x7f]+$", repr=False),
    ]
    account_fingerprint: Annotated[
        str, Field(pattern=r"^mt5-account-v1:[a-f0-9]{64}$", repr=False)
    ]
    specification_fingerprint: Annotated[
        str, Field(pattern=r"^mt5-spec-v1:[a-f0-9]{64}$", repr=False)
    ]
    account_confirmed_at: AwareDatetime
    specification_confirmed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        path = PureWindowsPath(self.terminal_path)
        if (
            not path.is_absolute()
            or len(path.drive) != 2
            or path.name.lower() != "terminal64.exe"
            or any(ord(char) < 32 for char in self.terminal_path)
            or ":" in self.terminal_path[2:]
            or self.broker_symbol != self.broker_symbol.strip()
            or self.specification_confirmed_at < self.account_confirmed_at
        ):
            raise ValueError("PROFILE_INVALID")
        return self

    def worker_config(self, *, smoke: bool = False) -> Mt5WorkerConfig:
        return Mt5WorkerConfig(
            terminal_path=Path(self.terminal_path),
            broker_symbol=self.broker_symbol,
            expected_account_fingerprint=self.account_fingerprint,
            smoke_confirmed_specification_fingerprint=self.specification_fingerprint,
            readonly_smoke=smoke,
        )


def default_profile_path() -> Path:
    if sys.platform != "win32":
        raise ProfileError("PROFILE_WINDOWS_ONLY")
    base = os.environ.get("LOCALAPPDATA", "")
    path = Path(base)
    if not base or not path.is_absolute() or len(path.drive) != 2:
        raise ProfileError("PROFILE_LOCATION_INVALID")
    return path / "Aurum" / "LocalDemo" / "mt5-profile.dpapi"


def reject_binding_environment() -> None:
    # Do not blend a remembered identity with partial or unrelated environment values.
    if any(os.environ.get(name) for name in _BINDING_ENV):
        raise ProfileError("PROFILE_ENV_CONFLICT")
    if any(
        os.environ.get(name, default) != default
        for name, default in (
            ("AURUM_MT5_MAX_TICK_AGE_SECONDS", "10"),
            ("AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS", "30"),
        )
    ):
        raise ProfileError("PROFILE_LIMIT_CONFLICT")


class ProfileStore:
    def __init__(
        self, path: Path | None = None, *, protection: Protection | None = None
    ) -> None:
        self.path = path if path is not None else default_profile_path()
        self._protection = (
            protection if protection is not None else WindowsDataProtection()
        )

    def _validate_location(self) -> None:
        if not self.path.is_absolute() or self.path.name != "mt5-profile.dpapi":
            raise ProfileError("PROFILE_LOCATION_INVALID")
        for part in (self.path, *self.path.parents):
            if part.is_symlink() or part.is_junction():
                raise ProfileError("PROFILE_LOCATION_INVALID")
            if part.is_dir() and (part / ".git").exists():
                raise ProfileError("PROFILE_LOCATION_INVALID")
        if self.path.exists():
            info = self.path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ProfileError("PROFILE_LOCATION_INVALID")

    def _read(self) -> bytes | None:
        self._validate_location()
        try:
            with self.path.open("rb") as source:
                data = source.read(MAX_PROTECTED_BYTES + 1)
        except FileNotFoundError:
            return None
        if not 0 < len(data) <= MAX_PROTECTED_BYTES:
            raise ProfileError("PROFILE_INVALID")
        return data

    def revision(self) -> str | None:
        try:
            data = self._read()
            return hashlib.sha256(data).hexdigest() if data is not None else None
        except ProfileError:
            raise
        except Exception:
            raise ProfileError("PROFILE_READ_FAILED") from None

    def load(self) -> LocalMt5Profile:
        try:
            data = self._read()
            if data is None:
                raise ProfileError("PROFILE_NOT_CONFIGURED")
            plain = self._protection.unprotect(data)
            if not plain.startswith(_MAGIC) or len(plain) > MAX_PROTECTED_BYTES:
                raise ProfileError("PROFILE_INVALID")
            digest = plain[len(_MAGIC) : len(_MAGIC) + 32]
            payload = plain[len(_MAGIC) + 32 :]
            if not hmac.compare_digest(digest, hashlib.sha256(payload).digest()):
                raise ProfileError("PROFILE_INVALID")
            return LocalMt5Profile.model_validate_json(payload)
        except ProfileError:
            raise
        except Exception:
            raise ProfileError("PROFILE_UNREADABLE") from None

    def save(self, profile: LocalMt5Profile, *, expected_revision: str | None) -> None:
        temporary: Path | None = None
        lock_fd: int | None = None
        lock = self.path.with_suffix(".lock")
        try:
            self._validate_location()
            # Revalidate even an object supplied via model_copy/model_construct.
            validated = LocalMt5Profile.model_validate_json(profile.model_dump_json())
            payload = validated.model_dump_json().encode("utf-8")
            ciphertext = self._protection.protect(
                _MAGIC + hashlib.sha256(payload).digest() + payload
            )
            if not 0 < len(ciphertext) <= MAX_PROTECTED_BYTES:
                raise ProfileError("PROFILE_WRITE_FAILED")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._validate_location()
            try:
                lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                raise ProfileError("PROFILE_BUSY") from None
            if self.revision() != expected_revision:
                raise ProfileError("PROFILE_CHANGED")
            fd, name = tempfile.mkstemp(
                prefix=".aurum-", suffix=".dpapi.tmp", dir=self.path.parent
            )
            temporary = Path(name)
            with os.fdopen(fd, "wb") as output:
                output.write(ciphertext)
                output.flush()
                os.fsync(output.fileno())
            self._validate_location()
            os.replace(temporary, self.path)
            temporary = None
        except ProfileError:
            raise
        except Exception:
            raise ProfileError("PROFILE_WRITE_FAILED") from None
        finally:
            try:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            finally:
                if lock_fd is not None:
                    os.close(lock_fd)
                    try:
                        lock.unlink(missing_ok=True)
                    except OSError:
                        raise ProfileError("PROFILE_CLEANUP_FAILED") from None
