from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from mt5_factories import NOW

from aurum_worker.adapters.persistence_mt5 import WorkerRpcMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    HealthState,
    Mt5HealthSnapshot,
    Mt5ReadFailure,
    Mt5ReasonCode,
)


@dataclass
class RecordingClient:
    responses: dict[str, dict[str, object]] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def call(self, function: str, parameters: dict[str, object]) -> dict[str, object]:
        self.calls.append((function, parameters))
        default_codes = {
            "worker_record_heartbeat": "HEARTBEAT_RECORDED",
            "worker_record_incident": "CREATED",
        }
        return self.responses.get(
            function, {"result_code": default_codes.get(function, "IDEMPOTENT_REPLAY")}
        )


def test_reconciliation_state_rpc_is_narrowed_before_strict_validation() -> None:
    client = RecordingClient(
        responses={
            "worker_read_mt5_reconciliation_state": {
                "position_tickets": ["1001"],
                "active_order_tickets": ["2001"],
                "executing_command_ids": ["command-1"],
                "account_fingerprint": "mt5-account-v1:fixture",
                "server_fingerprint": "mt5-server-v1:fixture",
                "broker_symbol": "XAUUSD",
                "symbol_specification_fingerprint": "mt5-spec-v1:fixture",
                "history_window_complete": True,
            }
        }
    )
    state = WorkerRpcMt5ObservationPersistence(client).load_reconciliation_state()
    assert state.position_tickets == frozenset({"1001"})
    assert state.broker_symbol == "XAUUSD"


def test_invalid_reconciliation_rpc_envelope_fails_closed() -> None:
    client = RecordingClient(
        responses={
            "worker_read_mt5_reconciliation_state": {"position_tickets": "not-a-list"}
        }
    )
    with pytest.raises(Mt5ReadFailure) as raised:
        WorkerRpcMt5ObservationPersistence(client).load_reconciliation_state()
    assert raised.value.error.reason_code is Mt5ReasonCode.DATABASE_REPORT_FAILED


def test_missing_reconciliation_completeness_flag_fails_closed() -> None:
    client = RecordingClient(
        responses={
            "worker_read_mt5_reconciliation_state": {
                "position_tickets": [],
                "active_order_tickets": [],
                "executing_command_ids": [],
            }
        }
    )

    with pytest.raises(Mt5ReadFailure) as raised:
        WorkerRpcMt5ObservationPersistence(client).load_reconciliation_state()

    assert raised.value.error.reason_code is Mt5ReasonCode.DATABASE_REPORT_FAILED


def test_denied_write_rpc_result_fails_closed_without_echoing_server_code() -> None:
    client = RecordingClient(
        responses={"worker_record_heartbeat": {"result_code": "WORKER_UNAUTHORIZED"}}
    )
    persistence = WorkerRpcMt5ObservationPersistence(client)
    snapshot = Mt5HealthSnapshot(
        observed_at=NOW,
        source="mt5",
        adapter_version="test",
        trace_id="trace",
        state=HealthState.UNAVAILABLE,
        reason_code=Mt5ReasonCode.TERMINAL_DISCONNECTED,
        package_available=True,
        platform="windows",
        terminal_connected=False,
    )

    with pytest.raises(Mt5ReadFailure) as raised:
        persistence.record_heartbeat(snapshot)

    assert raised.value.error.reason_code is Mt5ReasonCode.DATABASE_REPORT_FAILED
    assert "WORKER_UNAUTHORIZED" not in raised.value.error.safe_detail


def test_heartbeat_and_incident_reuse_existing_safe_rpc_shapes() -> None:
    client = RecordingClient()
    persistence = WorkerRpcMt5ObservationPersistence(client)
    snapshot = Mt5HealthSnapshot(
        observed_at=NOW,
        source="mt5",
        adapter_version="test",
        trace_id="trace",
        state=HealthState.UNAVAILABLE,
        reason_code=Mt5ReasonCode.TERMINAL_DISCONNECTED,
        package_available=True,
        platform="windows",
        terminal_connected=False,
    )
    persistence.record_heartbeat(snapshot)
    persistence.record_incident(
        "TERMINAL_DISCONNECTED",
        "warning",
        "MT5 polling failure",
        "Terminal is unavailable.",
        "trace",
        NOW,
    )

    heartbeat = client.calls[0]
    assert heartbeat[0] == "worker_record_heartbeat"
    assert heartbeat[1]["component_code"] == "execution.worker"
    assert heartbeat[1]["state"] == "failed"
    incident = client.calls[1]
    assert incident[0] == "worker_record_incident"
    assert "trace_id" not in incident[1]
    assert incident[1]["occurred_at"] == NOW.isoformat()
    assert isinstance(incident[1]["request_id"], str)
