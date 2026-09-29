from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import NoReturn

import pytest
from mt5_factories import NOW

from aurum_worker import mt5_cli
from aurum_worker import mt5_position_link_cli as cli
from aurum_worker.adapters.native_mt5 import POSITION_LINK_STAGE_CODES
from aurum_worker.local_mt5_profile import LocalMt5Profile, ProfileError
from aurum_worker.models.mt5 import (
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    SafeMt5Error,
)
from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY, UTC_POLICY
from aurum_worker.mt5_position_link import (
    LINK_FAILURE_CODES,
    PositionLinkProbe,
    PositionReference,
)

CONFIRM = "--confirm-pepperstone-demo"
POSITION = "--position=701@2025-02-03T04:05:06"
SECOND_POSITION = "--position=702@2025-02-03T04:06:07"
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


@pytest.mark.parametrize(
    "detail", sorted(LINK_FAILURE_CODES | POSITION_LINK_STAGE_CODES)
)
def test_closed_failure_stage_is_exported_without_partial_evidence(
    detail: str,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_adapter.failure_stage = "probe"
    probe_adapter.failure = Mt5ReadFailure(
        SafeMt5Error(
            reason_code=Mt5ReasonCode.RECONCILIATION_INCOMPLETE, safe_detail=detail
        )
    )
    assert cli.main([CONFIRM, POSITION]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "blocked",
        "reason": "RECONCILIATION_INCOMPLETE",
        "failure_stage": detail,
        **SAFETY_FIELDS,
    }
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]


@pytest.mark.parametrize(
    "detail",
    ["LINK_STAGE_private-marker", "private-marker", "LINK_POSITION_NOT_FOUND "],
)
def test_arbitrary_failure_detail_is_never_exported(
    detail: str,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_adapter.failure_stage = "probe"
    probe_adapter.failure = Mt5ReadFailure(
        SafeMt5Error(
            reason_code=Mt5ReasonCode.RECONCILIATION_INCOMPLETE, safe_detail=detail
        )
    )
    assert cli.main([CONFIRM, POSITION]) == 2
    assert_safe_output(capsys, status="blocked", reason="RECONCILIATION_INCOMPLETE")


def synthetic_profile() -> LocalMt5Profile:
    return LocalMt5Profile(
        terminal_path="C:\\Synthetic Position Test\\terminal64.exe",
        broker_symbol="XAUUSD",
        account_fingerprint="mt5-account-v1:" + "a" * 64,
        specification_fingerprint="mt5-spec-v1:" + "b" * 64,
        account_confirmed_at=NOW,
        specification_confirmed_at=NOW,
    )


def probe_report(count: int = 1) -> PositionLinkProbe:
    return PositionLinkProbe(
        collection_read_count=6,
        stable_snapshots=True,
        positions_observed=count,
        references_checked=count,
        linked_positions=count,
        display_second_matches=count,
        position_deal_second_matches=count,
        position_deal_millisecond_matches=count,
        order_setup_done_distinguishable=count,
        order_deal_time_order_matches=count,
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
        self.references: list[tuple[PositionReference, ...]] = []
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

    def inspect_position_time_links(
        self, *, trace_id: str, references: tuple[PositionReference, ...]
    ) -> PositionLinkProbe:
        self.calls.append("probe")
        self.trace_ids.append(trace_id)
        self.references.append(references)
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
        raise AssertionError("Position links must never invoke smoke.")

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


def assert_safe_output(
    capsys: pytest.CaptureFixture[str], *, status: str, reason: str
) -> None:
    captured = capsys.readouterr()
    assert captured.err == ""
    output = json.loads(captured.out)
    assert output == {"status": status, "reason": reason, **SAFETY_FIELDS}
    assert list(output)[-3:] == list(SAFETY_FIELDS)


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        [CONFIRM],
        [POSITION],
        ["probe", CONFIRM, POSITION],
        ["--confirm-pepperstone-demo=true", POSITION],
        [CONFIRM, CONFIRM, POSITION],
        [CONFIRM, POSITION, "extra"],
        [CONFIRM, POSITION, "--smoke"],
        [CONFIRM, POSITION, "--offset=3"],
        [CONFIRM, POSITION, "--lookback-days=30"],
        [CONFIRM, POSITION, "--reference-start=2025-02-03T04:00:00Z"],
        [CONFIRM, POSITION, "--reference-end=2025-02-03T04:10:00Z"],
        [CONFIRM, "--position", "701@2025-02-03T04:05:06"],
        [CONFIRM, "--position="],
        [CONFIRM, "--position=synthetic-private-input"],
        [CONFIRM, "--position=701@2025-02-03T04:05:06Z"],
        [CONFIRM, "--position=701@2025-02-03T04:05:06+00:00"],
        [CONFIRM, "--position=701@2025-02-03T04:05:06-03:00"],
        [CONFIRM, "--position=701@2025-02-03T04:05:06.000"],
        [CONFIRM, "--position=701@2025-02-03 04:05:06"],
        [CONFIRM, "--position=701@2025-02-03t04:05:06"],
        [CONFIRM, "--position=701@2025-2-03T04:05:06"],
        [CONFIRM, "--position=701@2025-02-03T04:05"],
        [CONFIRM, "--position=701@20250203T040506"],
        [CONFIRM, "--position=701@2025-W06-1T04:05:06"],
        [CONFIRM, "--position=701@2025-02-29T04:05:06"],
        [CONFIRM, "--position=701@0000-02-03T04:05:06"],
        [CONFIRM, "--position=701@2025-13-03T04:05:06"],
        [CONFIRM, "--position=701@2025-02-03T24:05:06"],
        [CONFIRM, "--position=701@2025-02-03T04:60:06"],
        [CONFIRM, "--position=701@2025-02-03T04:05:60"],
        [CONFIRM, "--position=701@2025-02-03T04:05:06\n"],
        [CONFIRM, "--position=0@2025-02-03T04:05:06"],
        [CONFIRM, "--position=-701@2025-02-03T04:05:06"],
        [CONFIRM, "--position=+701@2025-02-03T04:05:06"],
        [CONFIRM, "--position=0701@2025-02-03T04:05:06"],
        [CONFIRM, "--position=701.0@2025-02-03T04:05:06"],
        [CONFIRM, "--position= 701@2025-02-03T04:05:06"],
        [CONFIRM, "--position=\u0667\u0660\u0661@2025-02-03T04:05:06"],
        [CONFIRM, "--position=9223372036854775808@2025-02-03T04:05:06"],
        [CONFIRM, "--position=" + "9" * 1000 + "@2025-02-03T04:05:06"],
        [CONFIRM, POSITION, POSITION],
        [CONFIRM, POSITION, "--position=701@2025-02-03T04:06:07"],
        [CONFIRM]
        + [f"--position={ticket}@2025-02-03T04:05:06" for ticket in range(1, 12)],
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
    assert_safe_output(capsys, status="blocked", reason="PROBE_ARGUMENTS_INVALID")


@pytest.mark.parametrize("name", ENVIRONMENT_FIELDS[:-1])
def test_binding_and_limit_conflicts_block_before_profile_or_adapter(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(name, "synthetic-private-environment")
    assert cli.main([CONFIRM, POSITION]) == 2
    assert memory_store.loads == 0
    assert probe_adapter.configs == []
    reason = "PROFILE_LIMIT_CONFLICT" if "SECONDS" in name else "PROFILE_ENV_CONFLICT"
    assert_safe_output(capsys, status="blocked", reason=reason)


@pytest.mark.parametrize("value", ["1", "true", "invalid", " 0"])
def test_smoke_conflict_precedes_profile_access(
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", value)
    assert cli.main([CONFIRM, POSITION]) == 2
    assert memory_store.loads == 0
    assert probe_adapter.configs == []
    assert_safe_output(capsys, status="blocked", reason="PROFILE_SMOKE_CONFLICT")


@pytest.mark.parametrize("smoke_value", [None, "", "0"])
def test_success_uses_saved_profile_without_persisting_or_promoting_readiness(
    smoke_value: str | None,
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if smoke_value is not None:
        monkeypatch.setenv("AURUM_MT5_READONLY_SMOKE", smoke_value)
    original_profile = memory_store.profile.model_dump_json()
    assert cli.main([CONFIRM, POSITION]) == 0
    assert memory_store.loads == 1
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    assert probe_adapter.trace_ids == ["local-position-time-links"] * 2
    assert probe_adapter.references == [
        (PositionReference(ticket=701, opening_label=datetime(2025, 2, 3, 4, 5, 6)),)
    ]
    assert probe_adapter.references[0][0].opening_label.tzinfo is None
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
    captured = capsys.readouterr()
    assert captured.err == ""
    output = json.loads(captured.out)
    assert output == probe_adapter.result.model_dump(mode="json")
    assert list(output)[-3:] == list(SAFETY_FIELDS)
    for private in (
        memory_store.profile.terminal_path,
        memory_store.profile.account_fingerprint,
        memory_store.profile.specification_fingerprint,
        POSITION,
        "701",
        "2025-02-03",
        "04:05:06",
    ):
        assert private not in captured.out


@pytest.mark.parametrize(
    "arguments",
    [
        [CONFIRM, POSITION, SECOND_POSITION],
        [POSITION, CONFIRM, SECOND_POSITION],
        [POSITION, SECOND_POSITION, CONFIRM],
    ],
)
def test_repeated_references_preserve_order_and_naive_display_labels(
    arguments: list[str], memory_store: MemoryStore, probe_adapter: ProbeAdapter
) -> None:
    probe_adapter.result = probe_report(2)
    assert cli.main(arguments) == 0
    assert probe_adapter.references == [
        (
            PositionReference(ticket=701, opening_label=datetime(2025, 2, 3, 4, 5, 6)),
            PositionReference(ticket=702, opening_label=datetime(2025, 2, 3, 4, 6, 7)),
        )
    ]


@pytest.mark.parametrize("count", [1, 10])
def test_reference_count_and_ticket_bounds_accept_exact_limits(
    count: int, memory_store: MemoryStore, probe_adapter: ProbeAdapter
) -> None:
    tickets = [9223372036854775807, *range(1, count)]
    probe_adapter.result = probe_report(count)
    assert (
        cli.main(
            [CONFIRM]
            + [f"--position={ticket}@2024-02-29T23:59:59" for ticket in tickets]
        )
        == 0
    )
    assert [reference.ticket for reference in probe_adapter.references[0]] == tickets


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
    assert cli.main([CONFIRM, POSITION]) == 2
    assert probe_adapter.configs == []
    assert_safe_output(capsys, status="blocked", reason=reason)


def test_profile_store_construction_failure_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unavailable() -> NoReturn:
        raise RuntimeError("synthetic-private-profile-location")

    monkeypatch.setattr(cli, "ProfileStore", unavailable)
    assert cli.main([CONFIRM, POSITION]) == 2
    assert probe_adapter.configs == []
    assert_safe_output(capsys, status="blocked", reason="PROFILE_FAILED")


def test_profile_configuration_failure_is_redacted_before_native_access(
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid_config(self: LocalMt5Profile, *, smoke: bool = False) -> NoReturn:
        raise ValueError("synthetic-private-profile-configuration")

    monkeypatch.setattr(LocalMt5Profile, "worker_config", invalid_config)
    assert cli.main([CONFIRM, POSITION]) == 2
    assert probe_adapter.configs == []
    assert_safe_output(capsys, status="blocked", reason="PROFILE_FAILED")


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
    assert cli.main([CONFIRM, POSITION]) == (2 if structured else 3)
    assert probe_adapter.calls == (
        ["connect", "disconnect"]
        if stage == "connect"
        else ["connect", "probe", "disconnect"]
    )
    assert_safe_output(
        capsys,
        status="blocked" if structured else "failed",
        reason="ACCOUNT_BINDING_MISMATCH" if structured else "PROFILE_FAILED",
    )


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
    assert cli.main([CONFIRM, POSITION]) == 3
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    assert_safe_output(capsys, status="failed", reason="SHUTDOWN_FAILED")


def test_adapter_construction_failure_has_safe_json_without_native_calls(
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unavailable(config: Mt5WorkerConfig) -> NoReturn:
        raise RuntimeError("synthetic-private-constructor")

    monkeypatch.setattr(cli, "MetaTrader5ReadAdapter", unavailable)
    assert cli.main([CONFIRM, POSITION]) == 3
    assert_safe_output(capsys, status="failed", reason="PROFILE_FAILED")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("status", "synthetic-private-status"),
        ("grants_eligibility", True),
        ("smoke_invoked", True),
        ("transaction_time_contract", "verified"),
        ("collection_read_count", 5),
        ("stable_snapshots", False),
        ("positions_observed", "synthetic-private-observation"),
        ("references_checked", True),
        ("linked_positions", 0),
        ("display_second_matches", 2),
        ("position_deal_second_matches", -1),
        ("position_deal_millisecond_matches", "1"),
        ("order_setup_done_distinguishable", 2),
        ("order_deal_time_order_matches", False),
    ],
)
def test_cli_revalidates_report_before_output_without_warning_leaks(
    name: str,
    value: object,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_adapter.result = probe_adapter.result.model_copy(update={name: value})
    assert cli.main([CONFIRM, POSITION]) == 3
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    assert_safe_output(capsys, status="failed", reason="PROFILE_FAILED")


def test_cli_rejects_a_valid_report_for_a_different_reference_count(
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe_adapter.result = probe_report(2)
    assert cli.main([CONFIRM, POSITION]) == 3
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    assert_safe_output(capsys, status="failed", reason="PROFILE_FAILED")


def test_unexpected_report_fields_are_not_printed(
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ReportWithPrivateField(PositionLinkProbe):
        private_detail: str

    probe_adapter.result = ReportWithPrivateField(
        **probe_report().model_dump(), private_detail="synthetic-private-report-field"
    )
    assert cli.main([CONFIRM, POSITION]) == 3
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    assert_safe_output(capsys, status="failed", reason="PROFILE_FAILED")


def test_serialization_failure_discards_all_report_fields(
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_dump(self: PositionLinkProbe, **kwargs: object) -> NoReturn:
        raise RuntimeError("synthetic-private-report-serialization")

    monkeypatch.setattr(PositionLinkProbe, "model_dump", broken_dump)
    assert cli.main([CONFIRM, POSITION]) == 3
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]
    assert_safe_output(capsys, status="failed", reason="PROFILE_FAILED")


def test_default_entrypoint_reads_process_arguments(
    monkeypatch: pytest.MonkeyPatch,
    memory_store: MemoryStore,
    probe_adapter: ProbeAdapter,
) -> None:
    monkeypatch.setattr(sys, "argv", ["aurum-position-links", CONFIRM, POSITION])
    assert cli.main() == 0
    assert probe_adapter.calls == ["connect", "probe", "disconnect"]


def test_output_safety_assertions_override_payload_and_are_always_last(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli._print_result(
        {
            "grants_eligibility": True,
            "smoke_invoked": True,
            "transaction_time_contract": "verified",
            "status": "blocked",
            "reason": "PROBE_ARGUMENTS_INVALID",
        }
    )
    assert_safe_output(capsys, status="blocked", reason="PROBE_ARGUMENTS_INVALID")
