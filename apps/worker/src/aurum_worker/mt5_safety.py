"""Pure safety helpers for read-only MT5 normalization and verification."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountTradeMode,
    AccountVerificationResult,
    AccountVerificationState,
    BrokerSymbolObservation,
    CandleGap,
    CandleObservation,
    HealthState,
    Mt5ReasonCode,
    Timeframe,
)

_TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.H1: 3_600,
}
_UNSAFE_COMMENT = re.compile(
    r"(?:authorization\s*:|password\s*=|postgres(?:ql)?://|sk-[A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]+\.)",
    re.IGNORECASE,
)


def decimal_from_native(value: object, *, positive: bool = False) -> Decimal:
    """Convert native numerics through their string form, never through binary float."""

    if isinstance(value, bool) or value is None:
        raise ValueError("numeric observation is unavailable")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("numeric observation must be finite")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("numeric observation is invalid") from error
    if not result.is_finite():
        raise ValueError("numeric observation must be finite")
    if positive and result <= 0:
        raise ValueError("numeric observation must be positive")
    if not positive and result < 0:
        raise ValueError("numeric observation must not be negative")
    return result


def signed_decimal_from_native(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("numeric observation is unavailable")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("numeric observation is invalid") from error
    if not result.is_finite():
        raise ValueError("numeric observation must be finite")
    return result


def align_to_step(value: Decimal, step: Decimal) -> Decimal:
    if not value.is_finite() or value < 0 or not step.is_finite() or step <= 0:
        raise ValueError("alignment values must be finite and non-negative")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def utc_from_epoch(seconds: int | float | Decimal) -> datetime:
    try:
        value = Decimal(str(seconds))
    except InvalidOperation as error:
        raise ValueError("invalid epoch") from error
    if not value.is_finite() or value <= 0:
        raise ValueError("invalid epoch")
    return datetime.fromtimestamp(float(value), tz=UTC)


def utc_from_epoch_milliseconds(milliseconds: int) -> datetime:
    if milliseconds <= 0:
        raise ValueError("invalid millisecond epoch")
    seconds = Decimal(milliseconds) / Decimal(1_000)
    return utc_from_epoch(seconds)


def mask_login(login: int | str) -> str:
    normalized = str(login).strip()
    if not normalized.isdecimal() or len(normalized) < 4:
        return "••••"
    return f"••••{normalized[-4:]}"


def server_fingerprint(server: str) -> str:
    normalized = server.strip().casefold()
    if not normalized:
        raise ValueError("server identity is unavailable")
    digest = hashlib.sha256(normalized.encode("utf8")).hexdigest()
    return f"mt5-server-v1:{digest}"


def mask_server(server: str) -> str:
    normalized = server.strip()
    if not normalized:
        return "demo…unknown"
    safe_prefix = re.sub(r"[^A-Za-z0-9]", "", normalized)[:4].lower() or "demo"
    return f"{safe_prefix}…{server_fingerprint(normalized)[-4:]}"


def account_fingerprint(login: int | str, server: str) -> str:
    normalized_login = str(login).strip()
    normalized_server = server.strip().casefold()
    if not normalized_login.isdecimal() or not normalized_server:
        raise ValueError("account identity is incomplete")
    material = f"mt5-account-v1\0{normalized_login}\0{normalized_server}".encode()
    return f"mt5-account-v1:{hashlib.sha256(material).hexdigest()}"


def sanitize_comment(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.replace("\x00", " ").split())[:120]
    if _UNSAFE_COMMENT.search(normalized):
        return "[redacted]"
    return re.sub(r"[^\w .,:;+#/@()-]", "?", normalized, flags=re.UNICODE)


def verify_account(
    observation: AccountObservation | None,
    expected_fingerprint: str | None,
) -> AccountVerificationResult:
    if observation is None:
        return AccountVerificationResult(
            state=AccountVerificationState.ACCOUNT_INFO_UNAVAILABLE,
            health_state=HealthState.UNAVAILABLE,
            reason_code=Mt5ReasonCode.ACCOUNT_INFO_UNAVAILABLE,
            market_data_eligible=False,
        )
    common = {
        "masked_login": observation.masked_login,
        "masked_server": observation.masked_server,
        "account_fingerprint": observation.account_fingerprint,
    }
    if observation.trade_mode is AccountTradeMode.CONTEST:
        return AccountVerificationResult(
            state=AccountVerificationState.CONTEST_ACCOUNT_BLOCKED,
            health_state=HealthState.BLOCKED,
            reason_code=Mt5ReasonCode.CONTEST_ACCOUNT_BLOCKED,
            market_data_eligible=False,
            **common,
        )
    if observation.trade_mode is AccountTradeMode.REAL:
        return AccountVerificationResult(
            state=AccountVerificationState.REAL_ACCOUNT_BLOCKED,
            health_state=HealthState.BLOCKED,
            reason_code=Mt5ReasonCode.REAL_ACCOUNT_BLOCKED,
            market_data_eligible=False,
            **common,
        )
    if observation.trade_mode is not AccountTradeMode.DEMO:
        return AccountVerificationResult(
            state=AccountVerificationState.TRADE_MODE_UNKNOWN,
            health_state=HealthState.BLOCKED,
            reason_code=Mt5ReasonCode.TRADE_MODE_UNKNOWN,
            market_data_eligible=False,
            **common,
        )
    if expected_fingerprint is None:
        return AccountVerificationResult(
            state=AccountVerificationState.VERIFIED_DEMO_UNBOUND,
            health_state=HealthState.DEGRADED,
            reason_code=Mt5ReasonCode.DEMO_ACCOUNT_UNBOUND,
            market_data_eligible=False,
            **common,
        )
    if observation.account_fingerprint != expected_fingerprint:
        return AccountVerificationResult(
            state=AccountVerificationState.ACCOUNT_BINDING_MISMATCH,
            health_state=HealthState.BLOCKED,
            reason_code=Mt5ReasonCode.ACCOUNT_BINDING_MISMATCH,
            market_data_eligible=False,
            **common,
        )
    return AccountVerificationResult(
        state=AccountVerificationState.VERIFIED_DEMO_BOUND,
        health_state=HealthState.HEALTHY,
        reason_code=Mt5ReasonCode.HEALTHY,
        market_data_eligible=True,
        **common,
    )


def specification_fingerprint(specification: dict[str, object]) -> str:
    canonical = json.dumps(specification, sort_keys=True, separators=(",", ":"))
    return f"mt5-spec-v1:{hashlib.sha256(canonical.encode()).hexdigest()}"


def broker_specification_material(
    observation: BrokerSymbolObservation,
) -> dict[str, object]:
    excluded = {
        "adapter_version",
        "observed_at",
        "raw_diagnostic_codes",
        "schema_version",
        "source",
        "specification_fingerprint",
        "trace_id",
        "unusable_reason",
        "usability_state",
    }
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in observation.model_dump(mode="python").items()
        if key not in excluded
    }


def candle_gaps(
    candles: tuple[CandleObservation, ...], timeframe: Timeframe
) -> tuple[CandleGap, ...]:
    expected = _TIMEFRAME_SECONDS[timeframe]
    gaps: list[CandleGap] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        difference = int((current.open_at - previous.open_at).total_seconds())
        if difference <= 0:
            raise ValueError("candle timestamps must be strictly increasing")
        if difference > expected:
            gaps.append(
                CandleGap(
                    after_open_at=previous.open_at,
                    before_open_at=current.open_at,
                    missing_intervals=(difference // expected) - 1,
                )
            )
    return tuple(gaps)
