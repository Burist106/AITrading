"""Explicit, bounded Pepperstone Demo transaction timestamp transport codec.

This policy is selected separately from the market-data policy. It represents
the operator-accepted server-wall convention for the supported 2026 summer
interval, not a universal MT5/Python timestamp guarantee. Native event labels
must be decoded exactly once after their numeric fields have been validated.
The codec neither verifies a Demo/account binding nor grants risk eligibility.

History transports use integral seconds deliberately. Callers must validate all
returned rows, reject events outside the selected whole-second envelope, and
then filter only boundary overfetch against the original inclusive UTC bounds.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

TransactionTimePolicy = Literal["pepperstone_demo_transactions_2026_summer_v1"]

PEPPERSTONE_TRANSACTION_POLICY: TransactionTimePolicy = (
    "pepperstone_demo_transactions_2026_summer_v1"
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_COVERAGE_START = datetime(2026, 3, 9, tzinfo=UTC)
_COVERAGE_END = datetime(2026, 11, 1, tzinfo=UTC)
_TRANSPORT_OFFSET = timedelta(hours=3)
_MAXIMUM_RANGE = timedelta(days=7)


def _utc_datetime(value: datetime, *, code: str) -> datetime:
    try:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError(code)
        return value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError):
        raise ValueError(code) from None


def _validate_coverage(value: datetime) -> None:
    if not _COVERAGE_START <= value < _COVERAGE_END:
        raise ValueError("TRANSACTION_TIME_WINDOW_UNSUPPORTED")


def _validate_context(policy: TransactionTimePolicy, observed_at: datetime) -> None:
    if type(policy) is not str or policy != PEPPERSTONE_TRANSACTION_POLICY:
        raise ValueError("TRANSACTION_TIME_POLICY_INVALID")
    observation = _utc_datetime(
        observed_at, code="TRANSACTION_TIME_OBSERVATION_INVALID"
    )
    _validate_coverage(observation)


def decode_transaction_label(
    label: datetime,
    *,
    policy: TransactionTimePolicy,
    observed_at: datetime,
) -> datetime:
    """Decode an already validated native epoch label into an actual UTC instant.

    ``label`` is the aware datetime obtained by interpreting native epoch fields
    as UTC before applying this explicit transaction convention. Datetime
    arithmetic preserves every microsecond; no float epoch conversion is used.
    Capture and event instants must both fit the supported half-open interval.
    """

    _validate_context(policy, observed_at)
    encoded = _utc_datetime(label, code="TRANSACTION_TIME_VALUE_INVALID")
    try:
        decoded = encoded - _TRANSPORT_OFFSET
    except (OverflowError, ValueError):
        raise ValueError("TRANSACTION_TIME_VALUE_INVALID") from None
    _validate_coverage(decoded)
    return decoded


def encode_transaction_range(
    start: datetime,
    end: datetime,
    *,
    policy: TransactionTimePolicy,
    observed_at: datetime,
) -> tuple[int, int]:
    """Encode a bounded inclusive UTC range as whole-second native labels.

    Both labels are floored exactly. For fractional boundaries, native selection
    may return events in ``[floor(start), floor(end) + 1 second)``. The original
    endpoints remain authoritative after decoding; these transport labels must
    never replace the requested UTC bounds in reconciliation evidence.
    """

    _validate_context(policy, observed_at)
    start_utc = _utc_datetime(start, code="TRANSACTION_TIME_RANGE_INVALID")
    end_utc = _utc_datetime(end, code="TRANSACTION_TIME_RANGE_INVALID")
    if (
        start_utc <= _EPOCH
        or end_utc <= _EPOCH
        or end_utc <= start_utc
        or end_utc - start_utc > _MAXIMUM_RANGE
    ):
        raise ValueError("TRANSACTION_TIME_RANGE_INVALID")
    _validate_coverage(start_utc)
    _validate_coverage(end_utc)
    # Covered values are far from datetime limits. Timedelta division floors
    # with integer arithmetic and avoids platform/local-zone timestamp APIs.
    second = timedelta(seconds=1)
    return (
        (start_utc + _TRANSPORT_OFFSET - _EPOCH) // second,
        (end_utc + _TRANSPORT_OFFSET - _EPOCH) // second,
    )
