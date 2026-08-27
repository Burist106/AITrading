from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from mt5_factories import NOW, account, specification, tick
from pydantic import ValidationError

from aurum_worker.models.mt5 import (
    AccountTradeMode,
    AccountVerificationState,
    BrokerSymbolObservation,
    CandleObservation,
    CandleRequest,
    CandleSeries,
    HealthState,
    HistoryRequest,
    LatestTickObservation,
    Mt5ReasonCode,
    Mt5WorkerConfig,
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
            "AURUM_MT5_MAX_TICK_AGE_SECONDS": "12",
            "AURUM_MT5_MAX_CLOCK_DRIFT_SECONDS": "20",
            "AURUM_MT5_CANDLE_LIMIT": "200",
            "AURUM_MT5_HISTORY_WINDOW_HOURS": "12",
            "AURUM_MT5_POLL_INTERVAL_SECONDS": "2.5",
            "AURUM_MT5_RECONNECT_MAX_SECONDS": "30",
            "AURUM_MT5_READONLY_SMOKE": "1",
        }
    )
    assert config.terminal_path == Path("C:/MT5/terminal64.exe")
    assert config.poll_interval_seconds == Decimal("2.5")
    assert config.readonly_smoke is True
    assert not any("password" in name.lower() for name in Mt5WorkerConfig.model_fields)


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
