from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from aurum_worker.adapters.windows_protection import (
    ProtectionError,
    WindowsDataProtection,
)
from aurum_worker.local_mt5_profile import LocalMt5Profile, ProfileError, ProfileStore


class FakeProtection:
    def protect(self, data: bytes) -> bytes:
        return b"fake-only:" + data[::-1]

    def unprotect(self, data: bytes) -> bytes:
        if not data.startswith(b"fake-only:"):
            raise ValueError("private detail")
        return data[10:][::-1]


def profile() -> LocalMt5Profile:
    return LocalMt5Profile(
        terminal_path="C:\\Synthetic Terminal\\terminal64.exe",
        broker_symbol="XAUUSD",
        account_fingerprint="mt5-account-v1:" + "a" * 64,
        specification_fingerprint="mt5-spec-v1:" + "b" * 64,
        account_confirmed_at=datetime.now(UTC),
        specification_confirmed_at=datetime.now(UTC),
    )


def test_saved_profile_survives_new_store_without_plaintext(tmp_path: Path) -> None:
    path = tmp_path / "state" / "mt5-profile.dpapi"
    saved = profile()
    ProfileStore(path, protection=FakeProtection()).save(saved, expected_revision=None)
    assert ProfileStore(path, protection=FakeProtection()).load() == saved
    assert saved.account_fingerprint.encode() not in path.read_bytes()
    assert saved.terminal_path.encode() not in path.read_bytes()
    assert saved.account_fingerprint not in repr(saved)


def test_no_silent_overwrite(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    store.save(profile(), expected_revision=None)
    original = store.path.read_bytes()
    with pytest.raises(ProfileError, match="PROFILE_CHANGED"):
        store.save(profile(), expected_revision=None)
    assert store.path.read_bytes() == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("password", "synthetic-do-not-store"),
        ("readonly_smoke", True),
        ("max_clock_drift_seconds", 300),
        ("schema_version", 2),
        ("environment", "LIVE"),
        ("runtime_mode", "AUTO"),
        ("terminal_path", "relative/terminal64.exe"),
        ("terminal_path", "\\\\server\\share\\terminal64.exe"),
        ("terminal_path", "C:\\test\\other.exe"),
        ("terminal_path", "C:\\test\\terminal64.exe:stream"),
        ("account_fingerprint", "not-a-fingerprint"),
        ("specification_fingerprint", "mt5-spec-v1:short"),
        ("broker_symbol", " XAUUSD"),
        ("broker_symbol", "XAU\nUSD"),
    ],
)
def test_profile_rejects_unsafe_or_unknown_fields(field: str, value: object) -> None:
    data = profile().model_dump()
    data[field] = value
    with pytest.raises(ValidationError) as error:
        LocalMt5Profile.model_validate(data)
    assert "synthetic-do-not-store" not in str(error.value)


def test_profile_has_no_cached_health_smoke_or_limits() -> None:
    config = profile().worker_config()
    assert not config.readonly_smoke
    assert config.max_tick_age_seconds == 10
    assert config.max_clock_drift_seconds == 30
    assert not {"healthy", "readonly_smoke", "password"}.intersection(
        profile().model_dump()
    )


def test_missing_corrupt_and_tampered_profile_fail_closed(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    with pytest.raises(ProfileError, match="PROFILE_NOT_CONFIGURED"):
        store.load()
    store.path.write_bytes(b"corrupt")
    with pytest.raises(ProfileError, match="PROFILE_UNREADABLE") as error:
        store.load()
    assert "private detail" not in str(error.value)
    store.save(profile(), expected_revision=store.revision())
    cipher = bytearray(store.path.read_bytes())
    cipher[-1] ^= 1
    store.path.write_bytes(cipher)
    with pytest.raises(ProfileError):
        store.load()


def test_atomic_replace_requires_current_revision(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    store.save(profile(), expected_revision=None)
    before = store.revision()
    replacement = profile().model_copy(update={"broker_symbol": "XAUUSD.a"})
    store.save(replacement, expected_revision=before)
    assert store.load() == replacement
    with pytest.raises(ProfileError, match="PROFILE_CHANGED"):
        store.save(profile(), expected_revision=before)
    assert [p.name for p in tmp_path.iterdir()] == ["mt5-profile.dpapi"]


def test_encrypt_failure_preserves_previous_profile(tmp_path: Path) -> None:
    class BrokenProtection(FakeProtection):
        def protect(self, data: bytes) -> bytes:
            raise RuntimeError("private value")

    path = tmp_path / "mt5-profile.dpapi"
    store = ProfileStore(path, protection=FakeProtection())
    store.save(profile(), expected_revision=None)
    before = path.read_bytes()
    with pytest.raises(ProfileError, match="PROFILE_WRITE_FAILED"):
        ProfileStore(path, protection=BrokenProtection()).save(
            profile(), expected_revision=store.revision()
        )
    assert path.read_bytes() == before


def test_replace_failure_preserves_profile_and_cleans_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi", protection=FakeProtection())
    store.save(profile(), expected_revision=None)
    before = store.path.read_bytes()

    def fail_replace(source: object, target: object) -> None:
        raise OSError("private filesystem detail")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(ProfileError, match="^PROFILE_WRITE_FAILED$"):
        store.save(profile(), expected_revision=store.revision())
    assert store.path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["mt5-profile.dpapi"]


def test_repo_location_and_existing_lock_block(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    store = ProfileStore(
        tmp_path / "state" / "mt5-profile.dpapi", protection=FakeProtection()
    )
    with pytest.raises(ProfileError, match="PROFILE_LOCATION_INVALID"):
        store.save(profile(), expected_revision=None)
    (tmp_path / ".git").rmdir()
    store.path.parent.mkdir()
    store.path.with_suffix(".lock").write_bytes(b"")
    with pytest.raises(ProfileError, match="PROFILE_BUSY"):
        store.save(profile(), expected_revision=None)
    assert store.path.with_suffix(".lock").exists()
    assert not store.path.exists()


def test_hardlink_location_is_rejected(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.write_bytes(b"not-a-profile")
    target = tmp_path / "mt5-profile.dpapi"
    os.link(original, target)
    with pytest.raises(ProfileError, match="PROFILE_LOCATION_INVALID"):
        ProfileStore(target, protection=FakeProtection()).load()


@pytest.mark.skipif(
    sys.platform != "win32", reason="Real current-user DPAPI is Windows-only"
)
def test_real_dpapi_restart_roundtrip_and_tamper(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "mt5-profile.dpapi")
    saved = profile()
    store.save(saved, expected_revision=None)
    ciphertext = store.path.read_bytes()
    assert saved.account_fingerprint.encode() not in ciphertext
    assert saved.terminal_path.encode() not in ciphertext
    assert store.load() == saved
    # A second Python process proves persistence beyond the original process lifetime.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; "
            "from aurum_worker.local_mt5_profile import ProfileStore; "
            "p=ProfileStore(Path(sys.argv[1])).load(); "
            "print(p.environment == 'DEMO_ONLY' "
            "and not p.worker_config().readonly_smoke)",
            str(store.path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "True"
    assert not result.stderr
    store.path.write_bytes(ciphertext[:-8] + b"damaged!")
    with pytest.raises(ProfileError):
        store.load()


def test_protection_has_no_non_windows_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aurum_worker.adapters import windows_protection

    monkeypatch.setattr(windows_protection.sys, "platform", "linux")
    with pytest.raises(ProtectionError):
        WindowsDataProtection().protect(b"synthetic")
