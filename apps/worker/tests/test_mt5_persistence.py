from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from mt5_factories import NOW

from aurum_worker.adapters.persistence_mt5 import WorkerRpcMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    HealthState,
    HistoryQueryEvidence,
    HistoryQueryResultState,
    Mt5HealthSnapshot,
    Mt5ReadFailure,
    Mt5ReasonCode,
    ReconciliationOutcome,
    ReconciliationReport,
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


def reconciliation_report(broker_symbol: str | None) -> ReconciliationReport:
    def evidence(history_kind: str) -> HistoryQueryEvidence:
        return HistoryQueryEvidence(
            history_kind="orders" if history_kind == "orders" else "deals",
            requested_start_at=NOW - timedelta(hours=1),
            requested_end_at=NOW,
            query_completed_at=NOW,
            returned_count=0,
            result_state=HistoryQueryResultState.EMPTY_VALID_RESULT,
            reason_code=Mt5ReasonCode.HISTORY_EMPTY_VALID_RESULT,
        )

    matched = broker_symbol is not None
    return ReconciliationReport(
        observed_at=NOW,
        source="mt5",
        adapter_version="test",
        trace_id="trace",
        reconciliation_id="00000000-0000-4000-8000-000000000001",
        started_at=NOW - timedelta(minutes=1),
        completed_at=NOW,
        outcome=(
            ReconciliationOutcome.MATCHED
            if matched
            else ReconciliationOutcome.INCOMPLETE
        ),
        reason_code=(
            Mt5ReasonCode.HEALTHY
            if matched
            else Mt5ReasonCode.RECONCILIATION_INCOMPLETE
        ),
        account_fingerprint="mt5-account-v1:fixture",
        server_fingerprint="mt5-server-v1:fixture",
        broker_symbol=broker_symbol,
        symbol_specification_fingerprint="mt5-spec-v1:fixture",
        open_position_count=0,
        active_order_count=0,
        order_history_count=0,
        deal_history_count=0,
        order_history_evidence=evidence("orders"),
        deal_history_evidence=evidence("deals"),
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
                "confirmed_symbol_binding": {
                    "owner_id": "00000000-0000-4000-8000-000000000201",
                    "trading_account_id": "00000000-0000-4000-8000-000000000301",
                    "canonical_symbol": "XAUUSD",
                    "broker_symbol": "XAUUSD",
                    "confirmed_specification_fingerprint": "mt5-spec-v1:fixture",
                    "confirmation_status": "confirmed",
                    "confirmed_at": NOW.isoformat(),
                    "confirmed_by": "00000000-0000-4000-8000-000000000201",
                    "version": 1,
                },
            }
        }
    )
    state = WorkerRpcMt5ObservationPersistence(client).load_reconciliation_state()
    assert state.position_tickets == frozenset({"1001"})
    assert state.confirmed_symbol_binding is not None
    assert state.confirmed_symbol_binding.broker_symbol == "XAUUSD"


def test_invalid_reconciliation_rpc_envelope_fails_closed() -> None:
    client = RecordingClient(
        responses={
            "worker_read_mt5_reconciliation_state": {"position_tickets": "not-a-list"}
        }
    )
    with pytest.raises(Mt5ReadFailure) as raised:
        WorkerRpcMt5ObservationPersistence(client).load_reconciliation_state()
    assert raised.value.error.reason_code is Mt5ReasonCode.DATABASE_REPORT_FAILED


def test_missing_confirmed_binding_envelope_fails_closed() -> None:
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


def test_explicit_absent_confirmed_binding_is_preserved() -> None:
    client = RecordingClient(
        responses={
            "worker_read_mt5_reconciliation_state": {
                "position_tickets": [],
                "active_order_tickets": [],
                "executing_command_ids": [],
                "account_fingerprint": None,
                "server_fingerprint": None,
                "confirmed_symbol_binding": None,
            }
        }
    )

    state = WorkerRpcMt5ObservationPersistence(client).load_reconciliation_state()

    assert state.confirmed_symbol_binding is None


@pytest.mark.parametrize("broker_symbol", ["XAUUSD", None])
def test_reconciliation_rpcs_include_optional_broker_symbol(
    broker_symbol: str | None,
) -> None:
    client = RecordingClient()
    persistence = WorkerRpcMt5ObservationPersistence(client)
    report = reconciliation_report(broker_symbol)

    persistence.begin_reconciliation(report)
    persistence.complete_reconciliation(report)

    assert [call[0] for call in client.calls] == [
        "worker_begin_reconciliation",
        "worker_complete_reconciliation",
    ]
    for _, parameters in client.calls:
        payload = parameters["report"]
        assert isinstance(payload, dict)
        assert "broker_symbol" in payload
        assert payload["broker_symbol"] == broker_symbol


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
