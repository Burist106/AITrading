from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from mt5_factories import NOW, account, candidate, specification, tick
from pydantic import ValidationError

from aurum_worker.models.mt5 import (
    AccountTradeMode,
    AccountVerificationState,
    BrokerSymbolCandidate,
    BrokerSymbolObservation,
    CandleObservation,
    CandleRequest,
    CandleSeries,
    ComponentHeartbeat,
    ComponentHeartbeatState,
    HealthState,
    HistoryQueryEvidence,
    HistoryQueryResultState,
    HistoryRequest,
    LatestTickObservation,
    Mt5ComponentCode,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReconciliationCategory,
    ReconciliationMismatch,
    ReconciliationOutcome,
    ReconciliationReport,
    SymbolUsabilityState,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_safety import (
    account_fingerprint,
    align_to_step,
    broker_specification_material,
    candle_gaps,
    decimal_from_native,
    mask_login,
    mask_server,
    sanitize_comment,
    specification_fingerprint,
    utc_from_epoch,
    utc_from_epoch_milliseconds,
    verify_account,
)

PARITY_PATH = (
    Path(__file__).resolve().parents[3]
    / "contract-fixtures"
    / "v1"
    / "mt5-readonly-parity.json"
)


def test_configuration_reads_only_local_readonly_settings() -> None:
    config = Mt5WorkerConfig.from_environ(
        {
            "AURUM_MT5_TERMINAL_PATH": "C:/MT5/terminal64.exe",
            "AURUM_MT5_BROKER_SYMBOL": "XAUUSD",
            "AURUM_MT5_EXPECTED_ACCOUNT_FINGERPRINT": "mt5-account-v1:test",
            "AURUM_MT5_SMOKE_CONFIRMED_SPECIFICATION_FINGERPRINT": ("mt5-spec-v1:test"),
            "AURUM_MT5_MAX_TICK_AGE_SECONDS": "12",
            "AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS": "20",
            "AURUM_MT5_CANDLE_LIMIT": "200",
            "AURUM_MT5_HISTORY_WINDOW_HOURS": "12",
            "AURUM_MT5_TICK_POLL_SECONDS": "2.5",
            "AURUM_MT5_HEARTBEAT_VALID_FOR_SECONDS": "30",
            "AURUM_MT5_POSITION_POLL_SECONDS": "20",
            "AURUM_MT5_FULL_RECONCILIATION_SECONDS": "600",
            "AURUM_MT5_RECONNECT_MAX_SECONDS": "30",
            "AURUM_MT5_READONLY_SMOKE": "1",
        }
    )
    assert config.terminal_path == Path("C:/MT5/terminal64.exe")
    assert config.tick_poll_seconds == Decimal("2.5")
    assert config.heartbeat_valid_for_seconds == 30
    assert config.position_poll_seconds == Decimal("20")
    assert config.full_reconciliation_seconds == Decimal("600")
    assert config.smoke_confirmed_specification_fingerprint == "mt5-spec-v1:test"
    assert config.readonly_smoke is True
    assert not any("password" in name.lower() for name in Mt5WorkerConfig.model_fields)

    defaults = Mt5WorkerConfig.from_environ(
        {
            "AURUM_MT5_TICK_POLL_SECONDS": "",
            "AURUM_MT5_HEARTBEAT_VALID_FOR_SECONDS": "",
            "AURUM_MT5_POSITION_POLL_SECONDS": "",
            "AURUM_MT5_FULL_RECONCILIATION_SECONDS": "",
        }
    )
    assert defaults.tick_poll_seconds == Decimal("5")
    assert defaults.heartbeat_valid_for_seconds == 30
    assert defaults.position_poll_seconds == Decimal("15")
    assert defaults.full_reconciliation_seconds == Decimal("600")


def test_tick_poll_cadence_is_bounded_below_web_liveness_expiry() -> None:
    assert Mt5WorkerConfig(
        tick_poll_seconds=Decimal("30"), heartbeat_valid_for_seconds=90
    ).tick_poll_seconds == Decimal("30")
    with pytest.raises(ValidationError):
        Mt5WorkerConfig(tick_poll_seconds=Decimal("30.001"))


def test_heartbeat_ttl_is_bounded_and_covers_three_tick_intervals() -> None:
    assert (
        Mt5WorkerConfig(
            tick_poll_seconds=Decimal("5"), heartbeat_valid_for_seconds=15
        ).heartbeat_valid_for_seconds
        == 15
    )
    assert (
        Mt5WorkerConfig(
            tick_poll_seconds=Decimal("10.1"), heartbeat_valid_for_seconds=31
        ).heartbeat_valid_for_seconds
        == 31
    )

    for tick_seconds, ttl_seconds in (
        (Decimal("10"), 29),
        (Decimal("5"), 14),
        (Decimal("5"), 0),
        (Decimal("5"), -1),
        (Decimal("5"), 301),
    ):
        with pytest.raises(ValidationError):
            Mt5WorkerConfig(
                tick_poll_seconds=tick_seconds,
                heartbeat_valid_for_seconds=ttl_seconds,
            )


def test_component_heartbeat_is_typed_and_rejects_unknown_producer_values() -> None:
    heartbeat = ComponentHeartbeat(
        component_code=Mt5ComponentCode.MARKET_DATA,
        state=ComponentHeartbeatState.DEGRADED,
        detail=Mt5ReasonCode.TICK_DELAYED,
        observed_at=NOW,
        valid_for_seconds=30,
        trace_id="heartbeat-model",
    )

    assert {component.value for component in Mt5ComponentCode} == {
        "execution.worker",
        "execution.mt5_adapter",
        "execution.market_data",
    }
    assert {state.value for state in ComponentHeartbeatState} == {
        "healthy",
        "degraded",
        "failed",
    }
    assert heartbeat.detail is Mt5ReasonCode.TICK_DELAYED

    payload = heartbeat.model_dump(mode="python")
    payload["component_code"] = "execution.arbitrary"
    with pytest.raises(ValidationError):
        ComponentHeartbeat.model_validate(payload)

    payload = heartbeat.model_dump(mode="python")
    payload["state"] = "unknown"
    with pytest.raises(ValidationError):
        ComponentHeartbeat.model_validate(payload)


@pytest.mark.parametrize(
    ("component", "state", "detail", "ttl"),
    [
        (
            Mt5ComponentCode.WORKER,
            ComponentHeartbeatState.HEALTHY,
            Mt5ReasonCode.HEALTHY,
            15,
        ),
        (
            Mt5ComponentCode.MT5_ADAPTER,
            ComponentHeartbeatState.FAILED,
            Mt5ReasonCode.TERMINAL_DISCONNECTED,
            300,
        ),
        (
            Mt5ComponentCode.MARKET_DATA,
            ComponentHeartbeatState.DEGRADED,
            Mt5ReasonCode.TICK_DELAYED,
            30,
        ),
        (
            Mt5ComponentCode.WORKER,
            ComponentHeartbeatState.DEGRADED,
            Mt5ReasonCode.DEMO_ACCOUNT_UNBOUND,
            30,
        ),
    ],
)
def test_component_heartbeat_accepts_cross_layer_state_detail_pairs(
    component: Mt5ComponentCode,
    state: ComponentHeartbeatState,
    detail: Mt5ReasonCode,
    ttl: int,
) -> None:
    heartbeat = ComponentHeartbeat(
        component_code=component,
        state=state,
        detail=detail,
        observed_at=NOW,
        valid_for_seconds=ttl,
        trace_id="heartbeat-valid-pair",
    )

    assert heartbeat.valid_for_seconds == ttl


@pytest.mark.parametrize(
    ("component", "state", "detail"),
    [
        (
            Mt5ComponentCode.WORKER,
            ComponentHeartbeatState.HEALTHY,
            Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
        ),
        (
            Mt5ComponentCode.WORKER,
            ComponentHeartbeatState.FAILED,
            Mt5ReasonCode.HEALTHY,
        ),
        (
            Mt5ComponentCode.MT5_ADAPTER,
            ComponentHeartbeatState.DEGRADED,
            Mt5ReasonCode.HEALTHY,
        ),
        (
            Mt5ComponentCode.MARKET_DATA,
            ComponentHeartbeatState.DEGRADED,
            Mt5ReasonCode.DEMO_ACCOUNT_UNBOUND,
        ),
    ],
)
def test_component_heartbeat_rejects_cross_layer_state_detail_contradictions(
    component: Mt5ComponentCode,
    state: ComponentHeartbeatState,
    detail: Mt5ReasonCode,
) -> None:
    with pytest.raises(ValidationError):
        ComponentHeartbeat(
            component_code=component,
            state=state,
            detail=detail,
            observed_at=NOW,
            valid_for_seconds=30,
            trace_id="heartbeat-invalid-pair",
        )


@pytest.mark.parametrize(
    ("state", "detail"),
    [
        (ComponentHeartbeatState.HEALTHY, Mt5ReasonCode.HEALTHY),
        (ComponentHeartbeatState.DEGRADED, Mt5ReasonCode.TICK_DELAYED),
        (ComponentHeartbeatState.FAILED, Mt5ReasonCode.TICK_INVALID),
        (ComponentHeartbeatState.FAILED, Mt5ReasonCode.TICK_STALE),
        (ComponentHeartbeatState.FAILED, Mt5ReasonCode.TICK_FROM_FUTURE),
        (ComponentHeartbeatState.FAILED, Mt5ReasonCode.TICK_UNAVAILABLE),
    ],
)
def test_market_heartbeat_accepts_only_freshness_state_detail_pairs(
    state: ComponentHeartbeatState,
    detail: Mt5ReasonCode,
) -> None:
    heartbeat = ComponentHeartbeat(
        component_code=Mt5ComponentCode.MARKET_DATA,
        state=state,
        detail=detail,
        observed_at=NOW,
        valid_for_seconds=30,
        trace_id="market-heartbeat-valid-pair",
    )

    assert heartbeat.detail is detail


@pytest.mark.parametrize(
    ("state", "detail"),
    [
        (ComponentHeartbeatState.FAILED, Mt5ReasonCode.REAL_ACCOUNT_BLOCKED),
        (ComponentHeartbeatState.FAILED, Mt5ReasonCode.TICK_DELAYED),
        (ComponentHeartbeatState.DEGRADED, Mt5ReasonCode.TICK_STALE),
    ],
)
def test_market_heartbeat_rejects_non_freshness_state_detail_pairs(
    state: ComponentHeartbeatState,
    detail: Mt5ReasonCode,
) -> None:
    with pytest.raises(ValidationError):
        ComponentHeartbeat(
            component_code=Mt5ComponentCode.MARKET_DATA,
            state=state,
            detail=detail,
            observed_at=NOW,
            valid_for_seconds=30,
            trace_id="market-heartbeat-invalid-pair",
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "-1", "0"])
def test_positive_decimal_conversion_rejects_invalid_native_values(
    value: object,
) -> None:
    with pytest.raises(ValueError):
        decimal_from_native(value, positive=True)


def test_decimal_conversion_and_alignment_are_exact() -> None:
    value = decimal_from_native(0.1, positive=True)
    assert value == Decimal("0.1")
    assert align_to_step(Decimal("2345.127"), Decimal("0.01")) == Decimal("2345.12")
    assert align_to_step(Decimal("0.019"), Decimal("0.01")) == Decimal("0.01")


def test_utc_conversion_is_aware_and_millisecond_precise() -> None:
    seconds = int(NOW.timestamp())
    assert utc_from_epoch(seconds).tzinfo is UTC
    milliseconds = seconds * 1000 + 123
    assert utc_from_epoch_milliseconds(milliseconds).microsecond == 123_000
    with pytest.raises(ValueError):
        utc_from_epoch(0)


def test_account_masking_and_fingerprint_never_emit_raw_identity() -> None:
    login = int("987" + "654")
    server = "Demo" + "-Broker-01"
    fingerprint = account_fingerprint(login, server)
    assert mask_login(login) == "••••7654"
    assert str(login) not in fingerprint
    assert server not in fingerprint
    assert server not in mask_server(server)


@pytest.mark.parametrize(
    ("mode", "expected", "state", "health", "reason"),
    [
        (
            AccountTradeMode.DEMO,
            "match",
            AccountVerificationState.VERIFIED_DEMO_BOUND,
            HealthState.HEALTHY,
            Mt5ReasonCode.HEALTHY,
        ),
        (
            AccountTradeMode.DEMO,
            None,
            AccountVerificationState.VERIFIED_DEMO_UNBOUND,
            HealthState.DEGRADED,
            Mt5ReasonCode.DEMO_ACCOUNT_UNBOUND,
        ),
        (
            AccountTradeMode.CONTEST,
            "match",
            AccountVerificationState.CONTEST_ACCOUNT_BLOCKED,
            HealthState.BLOCKED,
            Mt5ReasonCode.CONTEST_ACCOUNT_BLOCKED,
        ),
        (
            AccountTradeMode.REAL,
            "match",
            AccountVerificationState.REAL_ACCOUNT_BLOCKED,
            HealthState.BLOCKED,
            Mt5ReasonCode.REAL_ACCOUNT_BLOCKED,
        ),
        (
            AccountTradeMode.UNKNOWN,
            "match",
            AccountVerificationState.TRADE_MODE_UNKNOWN,
            HealthState.BLOCKED,
            Mt5ReasonCode.TRADE_MODE_UNKNOWN,
        ),
    ],
)
def test_account_verification_fails_closed(
    mode: AccountTradeMode,
    expected: str | None,
    state: AccountVerificationState,
    health: HealthState,
    reason: Mt5ReasonCode,
) -> None:
    observed = account(mode)
    fingerprint = observed.account_fingerprint if expected == "match" else expected
    result = verify_account(observed, fingerprint)
    assert result.state is state
    assert result.health_state is health
    assert result.reason_code is reason


def test_account_binding_mismatch_blocks() -> None:
    result = verify_account(account(), "mt5-account-v1:different")
    assert result.state is AccountVerificationState.ACCOUNT_BINDING_MISMATCH
    assert result.market_data_eligible is False
    missing = verify_account(None, None)
    assert missing.state is AccountVerificationState.ACCOUNT_INFO_UNAVAILABLE
    assert missing.health_state is HealthState.UNAVAILABLE


def test_symbol_specification_validation_and_fingerprint_are_stable() -> None:
    observed = specification()
    material = broker_specification_material(observed)
    assert specification_fingerprint(material) == specification_fingerprint(material)
    invalid = observed.model_dump(mode="python")
    invalid["maximum_volume"] = Decimal("0.001")
    with pytest.raises(ValidationError):
        BrokerSymbolObservation.model_validate(invalid)
    invisible = specification(usability=SymbolUsabilityState.NOT_VISIBLE)
    assert invisible.unusable_reason is Mt5ReasonCode.SYMBOL_NOT_VISIBLE


@pytest.mark.parametrize(
    ("field", "value"),
    [("base_currency", "EUR"), ("profit_currency", "JPY")],
)
def test_symbol_models_require_actual_xau_usd_currencies(
    field: str, value: str
) -> None:
    observed = specification().model_dump(mode="python")
    observed[field] = value
    with pytest.raises(ValidationError):
        BrokerSymbolObservation.model_validate(observed)

    discovered = candidate().model_dump(mode="python")
    discovered[field] = value
    with pytest.raises(ValidationError):
        BrokerSymbolCandidate.model_validate(discovered)


def test_tick_requires_positive_ordered_prices_and_exact_spread() -> None:
    observed = tick()
    payload = observed.model_dump(mode="python")
    payload["ask"] = Decimal("2300")
    with pytest.raises(ValidationError):
        LatestTickObservation.model_validate(payload)
    for field in ("bid", "ask"):
        payload = observed.model_dump(mode="python")
        payload[field] = Decimal("0")
        with pytest.raises(ValidationError):
            LatestTickObservation.model_validate(payload)
    payload = observed.model_dump(mode="python")
    payload["spread_price"] = Decimal("0.21")
    with pytest.raises(ValidationError):
        LatestTickObservation.model_validate(payload)
    assert tick(TickFreshness.STALE).freshness is TickFreshness.STALE
    assert tick(TickFreshness.FUTURE_INVALID).freshness is TickFreshness.FUTURE_INVALID


def _candle(open_at: datetime) -> CandleObservation:
    return CandleObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="test",
        trace_id="test",
        symbol="XAUUSD",
        timeframe=Timeframe.M1,
        open_at=open_at,
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
        tick_volume=Decimal("1"),
        spread=Decimal("1"),
        real_volume=Decimal("0"),
        is_complete=True,
    )


def test_candle_bounds_completeness_and_gap_metadata() -> None:
    with pytest.raises(ValidationError):
        CandleRequest(start_position=0, count=1)
    current = CandleRequest(start_position=0, count=1, include_current=True)
    assert current.include_current is True
    candles = (_candle(NOW), _candle(NOW + timedelta(minutes=3)))
    gaps = candle_gaps(candles, Timeframe.M1)
    assert gaps[0].missing_intervals == 2
    assert CandleSeries(candles=candles, gaps=gaps).gaps == gaps
    assert len(CandleSeries(candles=candles, gaps=gaps).candles) == 2
    with pytest.raises(ValueError):
        candle_gaps((candles[0], candles[0]), Timeframe.M1)
    with pytest.raises(ValidationError):
        CandleSeries(candles=(candles[1], candles[0]))
    with pytest.raises(ValidationError):
        CandleRequest(count=2_001)
    with pytest.raises(ValidationError):
        CandleRequest.model_validate({"count": 1, "timeframe": "M30"})


def test_invalid_ohlc_and_unbounded_history_are_rejected() -> None:
    payload = _candle(NOW).model_dump(mode="python")
    payload["high"] = Decimal("9.5")
    with pytest.raises(ValidationError):
        CandleObservation.model_validate(payload)
    payload = _candle(NOW).model_dump(mode="python")
    payload["low"] = Decimal("-1")
    with pytest.raises(ValidationError):
        CandleObservation.model_validate(payload)
    with pytest.raises(ValidationError):
        HistoryRequest(start_at=NOW - timedelta(days=8), end_at=NOW)


@pytest.mark.parametrize(
    ("start_at", "end_at"),
    [
        (NOW, NOW),
        (NOW, NOW - timedelta(seconds=1)),
    ],
)
def test_history_requests_and_evidence_require_a_positive_window(
    start_at: datetime, end_at: datetime
) -> None:
    with pytest.raises(ValidationError):
        HistoryRequest(start_at=start_at, end_at=end_at)
    with pytest.raises(ValidationError):
        HistoryQueryEvidence(
            history_kind="orders",
            requested_start_at=start_at,
            requested_end_at=end_at,
            query_completed_at=None,
            returned_count=0,
            result_state=HistoryQueryResultState.WINDOW_UNKNOWN,
            reason_code=Mt5ReasonCode.HISTORY_WINDOW_INCOMPLETE,
        )


def test_history_evidence_completion_cannot_precede_request_end() -> None:
    with pytest.raises(ValidationError):
        HistoryQueryEvidence(
            history_kind="orders",
            requested_start_at=NOW - timedelta(hours=1),
            requested_end_at=NOW,
            query_completed_at=NOW - timedelta(microseconds=1),
            returned_count=0,
            result_state=HistoryQueryResultState.EMPTY_VALID_RESULT,
            reason_code=Mt5ReasonCode.HISTORY_EMPTY_VALID_RESULT,
        )


def test_empty_and_non_empty_history_success_use_distinct_reasons() -> None:
    empty = HistoryQueryEvidence(
        history_kind="orders",
        requested_start_at=NOW - timedelta(hours=1),
        requested_end_at=NOW,
        query_completed_at=NOW,
        returned_count=0,
        result_state=HistoryQueryResultState.EMPTY_VALID_RESULT,
        reason_code=Mt5ReasonCode.HISTORY_EMPTY_VALID_RESULT,
    )
    assert empty.reason_code is Mt5ReasonCode.HISTORY_EMPTY_VALID_RESULT

    returned_at = NOW - timedelta(minutes=30)
    non_empty = HistoryQueryEvidence(
        history_kind="deals",
        requested_start_at=NOW - timedelta(hours=1),
        requested_end_at=NOW,
        query_completed_at=NOW,
        returned_count=1,
        earliest_returned_at=returned_at,
        latest_returned_at=returned_at,
        result_state=HistoryQueryResultState.QUERY_SUCCEEDED,
        reason_code=Mt5ReasonCode.HEALTHY,
    )
    assert non_empty.reason_code is Mt5ReasonCode.HEALTHY

    with pytest.raises(ValidationError):
        HistoryQueryEvidence(
            history_kind="orders",
            requested_start_at=NOW - timedelta(hours=1),
            requested_end_at=NOW,
            query_completed_at=NOW,
            returned_count=0,
            result_state=HistoryQueryResultState.EMPTY_VALID_RESULT,
            reason_code=Mt5ReasonCode.HEALTHY,
        )


def _matched_reconciliation_report() -> ReconciliationReport:
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

    return ReconciliationReport(
        observed_at=NOW,
        source="mt5",
        adapter_version="test",
        trace_id="trace-matched",
        reconciliation_id="00000000-0000-4000-8000-000000000001",
        started_at=NOW - timedelta(minutes=1),
        completed_at=NOW,
        outcome=ReconciliationOutcome.MATCHED,
        reason_code=Mt5ReasonCode.HEALTHY,
        account_fingerprint="mt5-account-v1:fixture",
        server_fingerprint="mt5-server-v1:fixture",
        broker_symbol="XAUUSD",
        symbol_specification_fingerprint="mt5-spec-v1:fixture",
        open_position_count=0,
        active_order_count=0,
        order_history_count=0,
        deal_history_count=0,
        order_history_evidence=evidence("orders"),
        deal_history_evidence=evidence("deals"),
    )


@pytest.mark.parametrize(
    "field",
    [
        "account_fingerprint",
        "server_fingerprint",
        "broker_symbol",
        "symbol_specification_fingerprint",
    ],
)
def test_matched_reconciliation_requires_complete_identity(field: str) -> None:
    payload = _matched_reconciliation_report().model_dump(mode="python")
    payload[field] = None

    with pytest.raises(ValidationError):
        ReconciliationReport.model_validate(payload)


@pytest.mark.parametrize("field", ["order_history_evidence", "deal_history_evidence"])
def test_matched_reconciliation_requires_successful_history(field: str) -> None:
    payload = _matched_reconciliation_report().model_dump(mode="python")
    failed_evidence = payload[field]
    assert isinstance(failed_evidence, dict)
    failed_evidence["result_state"] = HistoryQueryResultState.QUERY_FAILED
    failed_evidence["reason_code"] = Mt5ReasonCode.HISTORY_QUERY_FAILED

    with pytest.raises(ValidationError):
        ReconciliationReport.model_validate(payload)


def test_matched_reconciliation_cannot_contain_mismatches() -> None:
    payload = _matched_reconciliation_report().model_dump(mode="python")
    payload["mismatches"] = (
        ReconciliationMismatch(
            category=ReconciliationCategory.ACCOUNT_CHANGED,
            severity="critical",
            resource_type="account",
            resource_reference="mt5-account-v1:changed",
            reason_code=Mt5ReasonCode.RECONCILIATION_INCOMPLETE,
        ),
    )

    with pytest.raises(ValidationError):
        ReconciliationReport.model_validate(payload)


def test_matched_reconciliation_requires_healthy_reason() -> None:
    payload = _matched_reconciliation_report().model_dump(mode="python")
    payload["reason_code"] = Mt5ReasonCode.RECONCILIATION_INCOMPLETE

    with pytest.raises(ValidationError):
        ReconciliationReport.model_validate(payload)


def test_decimal_and_ticket_json_boundaries_remain_strings() -> None:
    serialized = tick().model_dump(mode="json")
    assert serialized["bid"] == "2345.10"
    assert isinstance(serialized["bid"], str)
    model_source = (
        Path(__file__).parents[1] / "src" / "aurum_worker" / "models" / "mt5.py"
    ).read_text(encoding="utf8")
    assert "float" not in model_source


def test_comments_are_sanitized_without_echoing_sensitive_text() -> None:
    assert sanitize_comment("safe broker comment") == "safe broker comment"
    unsafe = "password=" + "do-not-echo"
    assert sanitize_comment(unsafe) == "[redacted]"


def test_python_decimal_and_ticket_rules_match_the_shared_parity_fixture() -> None:
    parity = json.loads(PARITY_PATH.read_text(encoding="utf8"))
    decimal_pattern = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
    ticket_pattern = re.compile(r"^[0-9]{1,32}$")
    assert parity["schemaVersion"] == 1
    assert all(
        isinstance(value, str) and decimal_pattern.fullmatch(value)
        for value in parity["validDecimalStrings"]
    )
    assert all(
        not isinstance(value, str) or not decimal_pattern.fullmatch(value)
        for value in parity["invalidDecimalValues"]
    )
    assert all(
        ticket_pattern.fullmatch(value) for value in parity["validTicketStrings"]
    )
    assert all(
        not isinstance(value, str) or not ticket_pattern.fullmatch(value)
        for value in parity["invalidTicketValues"]
    )
