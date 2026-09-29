"""Pure, explicitly selected timestamp codecs for market observations only.

The Pepperstone policy represents server-wall labels during a bounded, documented
2026 summer interval. Its fixed offset follows the provider's published US-DST
server-time policy; it is never estimated from a tick or the observation clock.
The entire spring and autumn transition dates are excluded. This is not a winter
calendar, a transaction/history timestamp policy, account verification, or a
freshness/eligibility decision. Callers must establish those independently.

Raw numeric epochs carry no source or normalization tag. A second normalization
cannot generally be detected inside the supported interval; callers must apply
this codec exactly once, at the verified native market-data boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from numbers import Integral
from typing import Literal

MarketTimePolicy = Literal["utc_epoch_v1", "pepperstone_demo_market_2026_summer_v1"]

UTC_POLICY: MarketTimePolicy = "utc_epoch_v1"
PEPPERSTONE_POLICY: MarketTimePolicy = "pepperstone_demo_market_2026_summer_v1"

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_PEPPERSTONE_START = datetime(2026, 3, 9, tzinfo=UTC)
_PEPPERSTONE_END = datetime(2026, 11, 1, tzinfo=UTC)
_PEPPERSTONE_OFFSET = timedelta(hours=3)


def _utc_datetime(value: datetime, *, code: str) -> datetime:
    try:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError(code)
        return value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError):
        raise ValueError(code) from None


def _validate_context(policy: MarketTimePolicy, observed_at: datetime) -> datetime:
    if policy not in (UTC_POLICY, PEPPERSTONE_POLICY):
        raise ValueError("MARKET_TIME_POLICY_INVALID")
    observed_utc = _utc_datetime(observed_at, code="MARKET_TIME_OBSERVATION_INVALID")
    _validate_window(observed_utc, policy)
    return observed_utc


def _validate_window(value: datetime, policy: MarketTimePolicy) -> None:
    if policy == PEPPERSTONE_POLICY and not (
        _PEPPERSTONE_START <= value < _PEPPERSTONE_END
    ):
        raise ValueError("MARKET_TIME_WINDOW_UNSUPPORTED")


def _epoch_datetime(
    value: int | float | Decimal | Integral, *, milliseconds: bool
) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (Integral, float, Decimal)):
        raise ValueError("MARKET_TIME_VALUE_INVALID")
    if type(milliseconds) is not bool:
        raise ValueError("MARKET_TIME_VALUE_INVALID")
    try:
        # Native candle arrays expose Integral scalars such as NumPy int64.
        # Normalize those exactly without depending on NumPy or coercing strings.
        if isinstance(value, Integral):
            number = Decimal(int(value))
        else:
            number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (OverflowError, ValueError):
        raise ValueError("MARKET_TIME_VALUE_INVALID") from None
    maximum = Decimal("253402300799999.999" if milliseconds else "253402300799.999999")
    minimum = Decimal("0.0005" if milliseconds else "0.0000005")
    if not number.is_finite() or number < minimum or number > maximum:
        raise ValueError("MARKET_TIME_VALUE_INVALID")

    # Exact integer arithmetic preserves every millisecond. Round finer inputs to
    # datetime's microsecond resolution without binary-float epoch conversion.
    numerator, denominator = number.as_integer_ratio()
    micros, remainder = divmod(
        numerator * (1_000 if milliseconds else 1_000_000), denominator
    )
    if remainder * 2 > denominator or (
        remainder * 2 == denominator and micros % 2 != 0
    ):
        micros += 1
    if micros <= 0:
        raise ValueError("MARKET_TIME_VALUE_INVALID")
    try:
        return _EPOCH + timedelta(microseconds=micros)
    except (OverflowError, ValueError):
        raise ValueError("MARKET_TIME_VALUE_INVALID") from None


def decode_market_epoch(
    value: int | float | Decimal | Integral,
    *,
    policy: MarketTimePolicy,
    observed_at: datetime,
    milliseconds: bool = False,
) -> datetime:
    """Decode one raw market label to UTC, without judging its freshness."""

    _validate_context(policy, observed_at)
    encoded = _epoch_datetime(value, milliseconds=milliseconds)
    decoded = encoded - _PEPPERSTONE_OFFSET if policy == PEPPERSTONE_POLICY else encoded
    _validate_window(decoded, policy)
    return decoded


def encode_market_range(
    start: datetime,
    end: datetime,
    *,
    policy: MarketTimePolicy,
    observed_at: datetime,
) -> tuple[datetime, datetime]:
    """Encode UTC event bounds as aware-UTC native market-query transport labels.

    With the Pepperstone policy these returned values are deliberately shifted
    transport labels, not the actual UTC instants of the requested events. Do not
    reuse them as observations or transaction/history query boundaries.
    """

    _validate_context(policy, observed_at)
    start_utc = _utc_datetime(start, code="MARKET_TIME_RANGE_INVALID")
    end_utc = _utc_datetime(end, code="MARKET_TIME_RANGE_INVALID")
    if start_utc <= _EPOCH or end_utc <= _EPOCH or start_utc > end_utc:
        raise ValueError("MARKET_TIME_RANGE_INVALID")
    _validate_window(start_utc, policy)
    _validate_window(end_utc, policy)
    if policy == PEPPERSTONE_POLICY:
        return start_utc + _PEPPERSTONE_OFFSET, end_utc + _PEPPERSTONE_OFFSET
    return start_utc, end_utc
