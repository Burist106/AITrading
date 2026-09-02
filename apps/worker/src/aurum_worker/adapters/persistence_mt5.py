"""Least-privilege persistence adapters for sanitized MT5 observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from aurum_worker.adapters.protocols import Mt5ObservationPersistencePort
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountVerificationState,
    BrokerSymbolObservation,
    ComponentHeartbeat,
    ConfirmedSymbolBinding,
    DatabaseReconciliationState,
    LatestTickObservation,
    Mt5ComponentCode,
    Mt5ReadFailure,
    Mt5ReasonCode,
    ReconciliationMismatch,
    ReconciliationReport,
    SafeMt5Error,
)


class WorkerRpcClient(Protocol):
    """Injected authenticated Worker RPC transport; no credential construction here."""

    def call(
        self, function: str, parameters: dict[str, object]
    ) -> dict[str, object]: ...


@dataclass(slots=True)
class InMemoryMt5ObservationPersistence(Mt5ObservationPersistencePort):
    database_state: DatabaseReconciliationState = field(
        default_factory=DatabaseReconciliationState
    )
    accounts: list[AccountObservation] = field(default_factory=list)
    symbols: list[BrokerSymbolObservation] = field(default_factory=list)
    ticks: dict[str, LatestTickObservation] = field(default_factory=dict)
    reports: dict[str, ReconciliationReport] = field(default_factory=dict)
    mismatches: list[tuple[str, ReconciliationMismatch]] = field(default_factory=list)
    heartbeats: dict[Mt5ComponentCode, ComponentHeartbeat] = field(default_factory=dict)
    incidents: list[tuple[str, str, str, str, str, datetime]] = field(
        default_factory=list
    )
    fail_operations: set[str] = field(default_factory=set)
    _last_symbol_states: dict[tuple[str, str], tuple[str, str, str | None]] = field(
        default_factory=dict, repr=False
    )

    def _result(self, operation: str) -> str:
        if operation in self.fail_operations:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail=f"Persistence operation {operation} failed.",
                    retryable=True,
                )
            )
        return "RECORDED"

    def record_account(
        self,
        observation: AccountObservation,
        verification_state: AccountVerificationState,
    ) -> str:
        result = self._result("record_account")
        self.accounts.append(observation)
        return result

    def record_symbol(
        self, observation: BrokerSymbolObservation, account_fingerprint: str
    ) -> str:
        result = self._result("record_symbol")
        identity = (account_fingerprint, observation.broker_symbol)
        state = (
            observation.specification_fingerprint,
            observation.usability_state.value,
            (
                observation.unusable_reason.value
                if observation.unusable_reason is not None
                else None
            ),
        )
        if self._last_symbol_states.get(identity) != state:
            self.symbols.append(observation)
            self._last_symbol_states[identity] = state
        return result

    def upsert_tick(
        self, observation: LatestTickObservation, account_fingerprint: str
    ) -> str:
        result = self._result("upsert_tick")
        self.ticks[observation.symbol] = observation
        return result

    def load_reconciliation_state(self) -> DatabaseReconciliationState:
        self._result("load_reconciliation_state")
        return self.database_state

    def begin_reconciliation(self, report: ReconciliationReport) -> str:
        result = self._result("begin_reconciliation")
        self.reports.setdefault(report.reconciliation_id, report)
        return result

    def record_mismatch(
        self, reconciliation_id: str, mismatch: ReconciliationMismatch
    ) -> str:
        result = self._result("record_mismatch")
        value = (reconciliation_id, mismatch)
        if value not in self.mismatches:
            self.mismatches.append(value)
        return result

    def complete_reconciliation(self, report: ReconciliationReport) -> str:
        result = self._result("complete_reconciliation")
        self.reports[report.reconciliation_id] = report
        return result

    def record_component_heartbeat(self, heartbeat: ComponentHeartbeat) -> str:
        result = self._result("record_component_heartbeat")
        self.heartbeats[heartbeat.component_code] = heartbeat
        return result

    def record_incident(
        self,
        code: str,
        severity: str,
        title: str,
        detail: str,
        trace_id: str,
        occurred_at: datetime,
    ) -> str:
        result = self._result("record_incident")
        value = (code, severity, title, detail, trace_id, occurred_at)
        if value not in self.incidents:
            self.incidents.append(value)
        return result


class WorkerRpcMt5ObservationPersistence(Mt5ObservationPersistencePort):
    """Explicit, statically visible, read/report-only RPC adapter."""

    _OBSERVATION_CODES = frozenset({"OBSERVATION_RECORDED", "IDEMPOTENT_REPLAY"})
    _TICK_CODES = frozenset({"TICK_RECORDED", "STALE_TICK_IGNORED"})
    _RECONCILIATION_START_CODES = frozenset(
        {"RECONCILIATION_STARTED", "IDEMPOTENT_REPLAY"}
    )
    _MISMATCH_CODES = frozenset({"MISMATCH_RECORDED", "IDEMPOTENT_REPLAY"})
    _RECONCILIATION_COMPLETE_CODES = frozenset(
        {"RECONCILIATION_COMPLETED", "IDEMPOTENT_REPLAY"}
    )
    _HEARTBEAT_CODES = frozenset({"HEARTBEAT_RECORDED", "STALE_HEARTBEAT"})
    _INCIDENT_CODES = frozenset({"CREATED", "IDEMPOTENT_REPLAY"})

    def __init__(self, client: WorkerRpcClient) -> None:
        self._client = client

    def _safe_transport_call(
        self, function: str, parameters: dict[str, object]
    ) -> dict[str, object]:
        try:
            return self._client.call(function, parameters)
        except Mt5ReadFailure:
            raise
        except Exception:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Worker persistence transport is unavailable.",
                    retryable=True,
                )
            ) from None

    @staticmethod
    def _code(response: dict[str, object], accepted_codes: frozenset[str]) -> str:
        value = response.get("result_code")
        if not isinstance(value, str) or value not in accepted_codes:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Persistence RPC did not confirm the requested report.",
                    retryable=True,
                )
            )
        return value

    @staticmethod
    def _string_set(response: dict[str, object], key: str) -> frozenset[str]:
        value = response.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Persistence RPC returned invalid reconciliation data.",
                    retryable=True,
                )
            )
        return frozenset(value)

    @staticmethod
    def _optional_string(response: dict[str, object], key: str) -> str | None:
        value = response.get(key)
        if value is not None and not isinstance(value, str):
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Persistence RPC returned invalid reconciliation data.",
                    retryable=True,
                )
            )
        return value

    @staticmethod
    def _confirmed_binding(
        response: dict[str, object], key: str
    ) -> ConfirmedSymbolBinding | None:
        if key not in response:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Persistence RPC omitted confirmed binding state.",
                    retryable=True,
                )
            )
        value = response.get(key)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Persistence RPC returned invalid reconciliation data.",
                    retryable=True,
                )
            )
        try:
            return ConfirmedSymbolBinding.model_validate(value, strict=False)
        except (TypeError, ValueError) as error:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Persistence RPC returned invalid confirmed binding.",
                    retryable=True,
                )
            ) from error

    def record_account(
        self,
        observation: AccountObservation,
        verification_state: AccountVerificationState,
    ) -> str:
        payload = observation.model_dump(mode="json")
        payload["verification_state"] = verification_state.value
        return self._code(
            self._client.call(
                "worker_record_mt5_account_observation",
                {"observation": payload},
            ),
            self._OBSERVATION_CODES,
        )

    def record_symbol(
        self, observation: BrokerSymbolObservation, account_fingerprint: str
    ) -> str:
        payload = observation.model_dump(mode="json")
        payload["account_fingerprint"] = account_fingerprint
        return self._code(
            self._client.call(
                "worker_record_mt5_symbol_observation",
                {"observation": payload},
            ),
            self._OBSERVATION_CODES,
        )

    def upsert_tick(
        self, observation: LatestTickObservation, account_fingerprint: str
    ) -> str:
        payload = observation.model_dump(mode="json")
        payload["account_fingerprint"] = account_fingerprint
        return self._code(
            self._client.call(
                "worker_upsert_mt5_latest_tick",
                {"observation": payload},
            ),
            self._TICK_CODES,
        )

    def load_reconciliation_state(self) -> DatabaseReconciliationState:
        response = self._client.call("worker_read_mt5_reconciliation_state", {})
        if "result_code" in response:
            raise Mt5ReadFailure(
                SafeMt5Error(
                    reason_code=Mt5ReasonCode.DATABASE_REPORT_FAILED,
                    safe_detail="Persistence RPC denied reconciliation state access.",
                    retryable=True,
                )
            )
        return DatabaseReconciliationState(
            position_tickets=self._string_set(response, "position_tickets"),
            active_order_tickets=self._string_set(response, "active_order_tickets"),
            executing_command_ids=self._string_set(response, "executing_command_ids"),
            account_fingerprint=self._optional_string(response, "account_fingerprint"),
            server_fingerprint=self._optional_string(response, "server_fingerprint"),
            confirmed_symbol_binding=self._confirmed_binding(
                response, "confirmed_symbol_binding"
            ),
        )

    def begin_reconciliation(self, report: ReconciliationReport) -> str:
        payload = report.model_dump(mode="json", exclude_none=False)
        return self._code(
            self._client.call(
                "worker_begin_reconciliation",
                {"report": payload},
            ),
            self._RECONCILIATION_START_CODES,
        )

    def record_mismatch(
        self, reconciliation_id: str, mismatch: ReconciliationMismatch
    ) -> str:
        return self._code(
            self._client.call(
                "worker_record_reconciliation_mismatch",
                {
                    "reconciliation_id": reconciliation_id,
                    "mismatch": mismatch.model_dump(mode="json"),
                },
            ),
            self._MISMATCH_CODES,
        )

    def complete_reconciliation(self, report: ReconciliationReport) -> str:
        payload = report.model_dump(mode="json", exclude_none=False)
        return self._code(
            self._client.call(
                "worker_complete_reconciliation",
                {"report": payload},
            ),
            self._RECONCILIATION_COMPLETE_CODES,
        )

    def record_component_heartbeat(self, heartbeat: ComponentHeartbeat) -> str:
        return self._code(
            self._safe_transport_call(
                "worker_record_heartbeat",
                {
                    "component_code": heartbeat.component_code.value,
                    "state": heartbeat.state.value,
                    "detail": heartbeat.detail.value,
                    "observed_at": heartbeat.observed_at.isoformat(),
                    "valid_for_seconds": heartbeat.valid_for_seconds,
                },
            ),
            self._HEARTBEAT_CODES,
        )

    def record_incident(
        self,
        code: str,
        severity: str,
        title: str,
        detail: str,
        trace_id: str,
        occurred_at: datetime,
    ) -> str:
        request_id = str(uuid5(NAMESPACE_URL, f"aurum:{trace_id}:{code}:{detail}"))
        return self._code(
            self._safe_transport_call(
                "worker_record_incident",
                {
                    "code": code,
                    "severity": severity,
                    "title": title,
                    "detail": detail,
                    "occurred_at": occurred_at.isoformat(),
                    "request_id": request_id,
                },
            ),
            self._INCIDENT_CODES,
        )
