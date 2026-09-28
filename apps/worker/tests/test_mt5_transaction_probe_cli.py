from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import NoReturn

import pytest
from mt5_factories import NOW

from aurum_worker import mt5_cli
from aurum_worker import mt5_transaction_probe_cli as cli
from aurum_worker.local_mt5_profile import LocalMt5Profile, ProfileError
from aurum_worker.models.mt5 import (
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    SafeMt5Error,
)
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY, UTC_POLICY
from aurum_worker.mt5_transaction_probe import (
    CollectionTimeProbe,
    OperatorTimeWindow,
    TransactionTimeProbe,
)

CONFIRM = "--confirm-pepperstone-demo"
START = "--reference-start=2026-08-27T19:00:00+07:00"
END = "--reference-end=2026-08-27T19:10:00+07:00"
ENVIRONMENT_FIELDS = (
    "AURUM_MT5_TERMINAL_PATH",
    "AURUM_MT5_BROKER_SYMBOL",
    "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT",
    "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT",
    "AURUM_MT5_MAX_TICK_AGE_SECONDS",
    "AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS",
    "AURUM_MT5_READONLY_SMOKE",
)
SAFETY_FIELDS = {
    "grants_eligibility": False,
    "smoke_invoked": False,
    "transaction_time_contract": "unverified",
}


def synthetic_profile() -> LocalMt5Profile:
    return LocalMt5Profile(
        terminal_path="C:\\Synthetic Probe Test\\terminal64.exe",
        broker_symbol="XAUUSD",
        account_fingerprint="mt5-account-v1:" + "a" * 64,
        specification_fingerprint="mt5-spec-v1:" + "b" * 64,
        account_confirmed_at=NOW,
        specification_confirmed_at=NOW,
    )


def probe_report() -> TransactionTimeProbe:
    collection = CollectionTimeProbe(
        matching_rows=4,
        selected_event_has_subsecond=False,
        setup_done_distinguishable=False,
        as_utc_reference_matches=None,
        minus_three_hours_reference_matches=None,
        queries=(),
    )
    return TransactionTimeProbe(
        history_query_count=4,
        reference_supplied=False,
        stable_snapshots=True,
        orders=collection,
        deals=collection,
    )


class MemoryStore:
    def __init__(self) -> None:
        self.profile = synthetic_profile()
        self.loads = 0
        self.failure: Exception | None = None

    def load(self) -> LocalMt5Profile:
        self.loads += 1
        if self.failure:
            raise self.failure
        return self.profile


class ProbeAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.trace_ids: list[str] = []
        self.references: list[OperatorTimeWindow | None] = []
        self.configs: list[Mt5WorkerConfig] = []
        self.result = probe_report()
        self.failure: Exception | None = None
        self.failure_stage = "connect"
        self.shutdown_failure = False

    def connect(self, *, trace_id: str) -> None:
        self.calls.append("connect")
        self.trace_ids.append(trace_id)
        if self.failure and self.failure_stage == "connect":
            raise self.failure

    def inspect_transaction_time_probe(
        self, *, trace_id: str, reference: OperatorTimeWindow | None = None
    ) -> TransactionTimeProbe:
        self.calls.append("probe")
        self.trace_ids.append(trace_id)
        self.references.append(reference)
        if self.failure and self.failure_stage == "probe":
            raise self.failure
        return self.result

    def disconnect(self) -> None:
        self.calls.append("disconnect")
        if self.shutdown_failure:
            raise RuntimeError("synthetic-private-shutdown")


@pytest.fixture(autouse=True)
def isolate_native_profile_and_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENVIRONMENT_FIELDS:
        monkeypatch.delenv(name, raising=False)

    def no_profile() -> NoReturn:
        raise AssertionError("Only an in-memory test profile may be loaded.")

    def no_native(config: Mt5WorkerConfig) -> NoReturn:
        raise AssertionError("Only a fake adapter may be constructed.")

    def no_smoke(config: Mt5WorkerConfig) -> NoReturn:
        raise AssertionError("Transaction evidence must never invoke smoke.")

    monkeypatch.setattr(cli, "ProfileStore", no_profile)
    monkeypatch.setattr(cli, "MetaTrader5ReadAdapter", no_native)
    monkeypatch.setattr(mt5_cli, "_smoke", no_smoke)


@pytest.fixture
def memory_store(monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    store = MemoryStore()
    monkeypatch.setattr(cli, "ProfileStore", lambda: store)
    return store


@pytest.fixture
def probe_adapter(monkeypatch: pytest.MonkeyPatch) -> ProbeAdapter:
    adapter = ProbeAdapter()

    def construct(config: Mt5WorkerConfig) -> ProbeAdapter:
        adapter.configs.append(config)
        return adapter

    monkeypatch.setattr(cli, "MetaTrader5ReadAdapter", construct)
    return adapter


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["probe"],
        ["probe", CONFIRM],
        ["--confirm-pepperstone-demo=true"],
        [CONFIRM, CONFIRM],
        [CONFIRM, "extra"],
        [CONFIRM, "--smoke"],
        [CONFIRM, "--offset=3"],
        [CONFIRM, "--lookback-days=30"],
        [CONFIRM, START],
        [CONFIRM, END],
        [CONFIRM, START, START],
        [CONFIRM, END, END],
        [CONFIRM, START, END, "extra"],
        [CONFIRM, START, END, CONFIRM],
        [START, END],
        [CONFIRM, "--reference-start=", END],
        [CONFIRM, "--reference-start=synthetic-private-input", END],
        [CONFIRM, "--reference-start=2026-08-27T12:00:00", END],
        [CONFIRM, START, "--reference-end=2026-08-27T12:10:00"],
        [CONFIRM, START, "--reference-end=2026-08-27T11:59:00Z"],
        [CONFIRM, START, "--reference-end=2026-08-27T14:00:00Z"],
        [CONFIRM, "--reference-start", "2026-08-27T12:00:00Z"],
    ],
)
def test_invalid_arguments_block_before_profile_and_native_access(
    arguments: list[str],
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(arguments) == 2
    assert memory_store.loads == 0
    assert probe_adapter.configs == []
    assert probe_adapter.calls == []
    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked",
        "reason": "PROBE_ARGUMENTS_INVALID",
        **SAFETY_FIELDS,
    }


@pytest.mark.parametrize("name", ENVIRONMENT_FIELDS[:-1])
def test_binding_and_limit_conflicts_block_before_profile_or_adapter(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(name, "synthetic-private-environment")
    assert cli.main([CONFIRM]) == 2
    assert memory_store.loads == 0
    assert probe_adapter.configs == []
    reason = "PROFILE_LIMIT_CONFLICT" if "SECONDS" in name else "PROFILE_ENV_CONFLICT"
    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked",
        "reason": reason,
        **SAFETY_FIELDS,
    }


@pytest.mark.parametrize("value", ["1", "true", "invalid", " 0"])
def test_smoke_environment_conflict_precedes_profile_access(
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", value)
    assert cli.main([CONFIRM]) == 2
    assert memory_store.loads == 0
    assert probe_adapter.configs == []
    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked",
        "reason": "PROFILE_SMOKE_CONFLICT",
        **SAFETY_FIELDS,
    }


@pytest.mark.parametrize("smoke_value", [None, "", "0"])
def test_success_reads_once_and_preserves_saved_profile_and_runtime_guards(
    smoke_value: str | None,
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if smoke_value is not None:
        monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", smoke_value)
    original_profile = memory_store.profile.model_dump_json()
    assert cli.main([CONFIRM]) == 0
    assert memory_store.loads == 1
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    assert probe_adapter.trace_ids == ["local-transaction-time-probe"] * 2
    assert probe_adapter.references == [None]
    assert len(probe_adapter.configs) == 1
    config = probe_adapter.configs[0]
    assert config.market_time_policy == PEPPERSTONE_POLICY
    assert config.readonly_smoke is False
    assert config.max_tick_age_seconds == 10
    assert config.max_clock_drift_seconds == 30
    assert (
        config.expected_account_fingerprint == memory_store.profile.account_fingerprint
    )
    assert (
        config.smoke_confirmed_specification_fingerprint
        == memory_store.profile.specification_fingerprint
    )
    assert memory_store.profile.model_dump_json() == original_profile
    assert memory_store.profile.worker_config().market_time_policy == UTC_POLICY
    output = capsys.readouterr().out
    assert json.loads(output) == probe_adapter.result.model_dump(mode="json")
    for private in (
        memory_store.profile.terminal_path,
        memory_store.profile.account_fingerprint,
        memory_store.profile.specification_fingerprint,
    ):
        assert private not in output


@pytest.mark.parametrize(
    "arguments", [[CONFIRM, START, END], [END, CONFIRM, START], [START, END, CONFIRM]]
)
def test_optional_independent_reference_is_normalized_to_utc_before_probe(
    arguments: list[str], memory_store: MemoryStore, probe_adapter: ProbeAdapter
) -> None:
    assert cli.main(arguments) == 0
    assert len(probe_adapter.references) == 1
    reference = probe_adapter.references[0]
    assert reference is not None
    assert reference.start_at == datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    assert reference.end_at == datetime(2026, 8, 27, 12, 10, tzinfo=UTC)
    assert reference.start_at.tzinfo is UTC
    assert reference.end_at.tzinfo is UTC


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (ProfileError("PROFILE_UNREADABLE"), "PROFILE_UNREADABLE"),
        (ProfileError("synthetic-private-profile"), "PROFILE_FAILED"),
        (RuntimeError("synthetic-private-profile"), "PROFILE_FAILED"),
    ],
)
def test_profile_failures_never_reveal_details_or_create_adapter(
    failure: Exception,
    reason: str,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    memory_store.failure = failure
    assert cli.main([CONFIRM]) == 2
    assert probe_adapter.configs == []
    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked",
        "reason": reason,
        **SAFETY_FIELDS,
    }


@pytest.mark.parametrize("stage", ["connect", "probe"])
@pytest.mark.parametrize("structured", [False, True])
def test_native_failure_discards_evidence_and_disconnects_once(
    stage: str,
    structured: bool,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_adapter.failure_stage = stage
    probe_adapter.failure = (
        Mt5ReadFailure(
            SafeMt5Error(
                reason_code=Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH,
                safe_detail="synthetic-private-native-detail",
            )
        )
        if structured
        else RuntimeError("synthetic-private-native-detail")
    )
    assert cli.main([CONFIRM]) == (2 if structured else 3)
    assert probe_adapter.calls == (
        ["connect", "disconnect"]
        if stage == "connect"
        else ["connect", "probe", "disconnect"]
    )
    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked" if structured else "failed",
        "reason": "ACCOUNT_BINDING_MISMATCH" if structured else "PROFILE_FAILED",
        **SAFETY_FIELDS,
    }


@pytest.mark.parametrize("initial_failure", [False, True])
def test_shutdown_failure_discards_success_or_partial_failure(
    initial_failure: bool,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if initial_failure:
        probe_adapter.failure_stage = "probe"
        probe_adapter.failure = RuntimeError("synthetic-private-partial-failure")
    probe_adapter.shutdown_failure = True
    assert cli.main([CONFIRM]) == 3
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    assert json.loads(capsys.readouterr().out) == {
        "status": "failed",
        "reason": "SHUTDOWN_FAILED",
        **SAFETY_FIELDS,
    }


def test_adapter_construction_failure_has_safe_json_without_native_calls(
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unavailable(config: Mt5WorkerConfig) -> NoReturn:
        raise RuntimeError("synthetic-private-constructor")

    monkeypatch.setattr(cli, "MetaTrader5ReadAdapter", unavailable)
    assert cli.main([CONFIRM]) == 3
    assert json.loads(capsys.readouterr().out) == {
        "status": "failed",
        "reason": "PROFILE_FAILED",
        **SAFETY_FIELDS,
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("status", "synthetic-private-status"),
        ("grants_eligibility", True),
        ("smoke_invoked", True),
        ("transaction_time_contract", "verified"),
    ],
)
def test_cli_revalidates_report_before_output(
    name: str,
    value: object,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_adapter.result = probe_adapter.result.model_copy(update={name: value})
    assert cli.main([CONFIRM]) == 3
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "failed",
        "reason": "PROFILE_FAILED",
        **SAFETY_FIELDS,
    }


def test_default_entrypoint_reads_process_arguments(
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
) -> None:
    monkeypatch.setattr(sys, "argv", ["aurum-probe", CONFIRM])
    assert cli.main() == 0
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]


def test_unexpected_report_fields_are_not_printed(
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ReportWithPrivateField(TransactionTimeProbe):
        private_detail: str

    probe_adapter.result = ReportWithPrivateField(
        **probe_report().model_dump(), private_detail="synthetic-private-report-field"
    )
    assert cli.main([CONFIRM]) == 3
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "failed",
        "reason": "PROFILE_FAILED",
        **SAFETY_FIELDS,
    }
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
