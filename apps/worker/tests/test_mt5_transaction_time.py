from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from typing import cast

import pytest

from aurum_worker.mt5_market_time import PEPPERSTONE_POLICY, encode_market_range
from aurum_worker.mt5_transaction_time import (
    PEPPERSTONE_TRANSACTION_POLICY,
    TransactionTimePolicy,
    decode_transaction_label,
    encode_transaction_range,
)

POLICY = PEPPERSTONE_TRANSACTION_POLICY
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
START = datetime(2026, 3, 9, tzinfo=UTC)
END = datetime(2026, 11, 1, tzinfo=UTC)
NOW = datetime(2026, 9, 18, 6, 7, 8, tzinfo=UTC)
OFFSET = timedelta(hours=3)
SECOND = timedelta(seconds=1)
MICROSECOND = timedelta(microseconds=1)


def exact_seconds(value: datetime) -> int:
    return (value - EPOCH) // SECOND


@pytest.mark.parametrize("micros", [0, 1, 999, 1000, 123456, 999999])
def test_decode_preserves_exact_microseconds(micros: int) -> None:
    actual = NOW.replace(microsecond=micros)
    decoded = decode_transaction_label(actual + OFFSET, policy=POLICY, observed_at=NOW)
    assert decoded == actual
    assert decoded.microsecond == micros
    assert decoded.tzinfo is UTC


@pytest.mark.parametrize("hours", [-12, -5, 0, 3, 7, 14])
def test_aware_labels_and_observation_are_normalized_by_instant(hours: int) -> None:
    zone = timezone(timedelta(hours=hours))
    assert (
        decode_transaction_label(
            (NOW + OFFSET).astimezone(zone),
            policy=POLICY,
            observed_at=NOW.astimezone(zone),
        )
        == NOW
    )


@pytest.mark.parametrize("micros", [0, 1, 999, 1000, 123456, 999999])
@pytest.mark.parametrize("hours", [-5, 0, 7])
def test_history_range_returns_exact_integral_native_seconds(
    micros: int, hours: int
) -> None:
    zone = timezone(timedelta(hours=hours))
    start = NOW.replace(microsecond=micros)
    end = start + timedelta(minutes=1, microseconds=1)
    encoded = encode_transaction_range(
        start.astimezone(zone),
        end.astimezone(zone),
        policy=POLICY,
        observed_at=NOW.astimezone(zone),
    )
    assert encoded == (exact_seconds(start + OFFSET), exact_seconds(end + OFFSET))
    assert all(type(value) is int for value in encoded)


@pytest.mark.parametrize("start_micros", [0, 1, 200000, 999998])
def test_subsecond_window_uses_same_second_envelope(start_micros: int) -> None:
    start = NOW.replace(microsecond=start_micros)
    end = start + MICROSECOND
    assert encode_transaction_range(start, end, policy=POLICY, observed_at=NOW) == (
        exact_seconds(NOW + OFFSET),
        exact_seconds(NOW + OFFSET),
    )


@pytest.mark.parametrize("end_micros", [0, 1, 123456, 999999])
def test_fractional_transport_does_not_round_up_upper_second(end_micros: int) -> None:
    end = (NOW + SECOND).replace(microsecond=end_micros)
    encoded_start, encoded_end = encode_transaction_range(
        NOW + MICROSECOND, end, policy=POLICY, observed_at=NOW
    )
    assert encoded_start == exact_seconds(NOW + OFFSET)
    assert encoded_end == exact_seconds(NOW + SECOND + OFFSET)


@pytest.mark.parametrize("actual", [START, END - MICROSECOND])
def test_event_and_capture_coverage_include_start_but_not_end(actual: datetime) -> None:
    assert (
        decode_transaction_label(actual + OFFSET, policy=POLICY, observed_at=actual)
        == actual
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [(START, START + MICROSECOND), (END - SECOND, END - MICROSECOND)],
)
def test_ranges_at_supported_edges_are_allowed(start: datetime, end: datetime) -> None:
    assert encode_transaction_range(start, end, policy=POLICY, observed_at=NOW) == (
        exact_seconds(start + OFFSET),
        exact_seconds(end + OFFSET),
    )


@pytest.mark.parametrize("duration", [MICROSECOND, SECOND, timedelta(days=7)])
def test_positive_ranges_up_to_seven_days_are_supported(duration: timedelta) -> None:
    assert encode_transaction_range(
        NOW - duration, NOW, policy=POLICY, observed_at=NOW
    ) == (exact_seconds(NOW - duration + OFFSET), exact_seconds(NOW + OFFSET))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (NOW, NOW),
        (NOW, NOW - MICROSECOND),
        (NOW, NOW + timedelta(days=7, microseconds=1)),
        (EPOCH, EPOCH + SECOND),
        (EPOCH - SECOND, EPOCH),
        (EPOCH - timedelta(days=1), EPOCH - SECOND),
    ],
)
def test_nonpositive_unordered_and_unbounded_ranges_fail(
    start: datetime, end: datetime
) -> None:
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_RANGE_INVALID$"):
        encode_transaction_range(start, end, policy=POLICY, observed_at=NOW)


@pytest.mark.parametrize(
    "actual",
    [
        START - MICROSECOND,
        END,
        datetime(2026, 3, 8, 12, tzinfo=UTC),
        datetime(2026, 11, 1, 12, tzinfo=UTC),
        datetime(2027, 9, 18, tzinfo=UTC),
    ],
)
def test_unsupported_events_and_capture_times_are_rejected(actual: datetime) -> None:
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_WINDOW_UNSUPPORTED$"):
        decode_transaction_label(actual + OFFSET, policy=POLICY, observed_at=NOW)
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_WINDOW_UNSUPPORTED$"):
        decode_transaction_label(NOW + OFFSET, policy=POLICY, observed_at=actual)
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_WINDOW_UNSUPPORTED$"):
        encode_transaction_range(NOW, NOW + SECOND, policy=POLICY, observed_at=actual)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (START - MICROSECOND, START),
        (END - MICROSECOND, END),
        (START - SECOND, START - MICROSECOND),
        (END, END + SECOND),
    ],
)
def test_each_original_range_boundary_must_have_coverage(
    start: datetime, end: datetime
) -> None:
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_WINDOW_UNSUPPORTED$"):
        encode_transaction_range(start, end, policy=POLICY, observed_at=NOW)


@pytest.mark.parametrize(
    "policy", ["", "utc_epoch_v1", PEPPERSTONE_POLICY, None, True, 1]
)
def test_no_implicit_default_or_market_policy_authorization(policy: object) -> None:
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_POLICY_INVALID$"):
        decode_transaction_label(
            NOW + OFFSET,
            policy=cast(TransactionTimePolicy, policy),
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_POLICY_INVALID$"):
        encode_transaction_range(
            NOW,
            NOW + SECOND,
            policy=cast(TransactionTimePolicy, policy),
            observed_at=NOW,
        )


class MissingOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> None:
        return None


class BrokenOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta:
        raise ValueError("PRIVATE_CONTEXT_MUST_NOT_ESCAPE")

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> None:
        return None


INVALID_DATES: list[object] = [
    None,
    True,
    1,
    1.0,
    "PRIVATE_INVALID_INPUT",
    date(2026, 9, 18),
    NOW.replace(tzinfo=None),
    NOW.replace(tzinfo=MissingOffset()),
    NOW.replace(tzinfo=BrokenOffset()),
    datetime.min.replace(tzinfo=timezone(timedelta(hours=14))),
    datetime.max.replace(tzinfo=timezone(timedelta(hours=-12))),
]


@pytest.mark.parametrize("value", INVALID_DATES)
def test_label_requires_valid_aware_datetime_with_safe_error(value: object) -> None:
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_VALUE_INVALID$"):
        decode_transaction_label(cast(datetime, value), policy=POLICY, observed_at=NOW)


@pytest.mark.parametrize("value", INVALID_DATES)
def test_capture_requires_valid_aware_datetime_with_safe_error(value: object) -> None:
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_OBSERVATION_INVALID$"):
        decode_transaction_label(
            NOW + OFFSET, policy=POLICY, observed_at=cast(datetime, value)
        )
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_OBSERVATION_INVALID$"):
        encode_transaction_range(
            NOW, NOW + SECOND, policy=POLICY, observed_at=cast(datetime, value)
        )


@pytest.mark.parametrize("value", INVALID_DATES)
@pytest.mark.parametrize("invalid_start", [False, True])
def test_each_range_boundary_requires_valid_aware_datetime(
    value: object, invalid_start: bool
) -> None:
    start = cast(datetime, value) if invalid_start else NOW
    end = NOW if invalid_start else cast(datetime, value)
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_RANGE_INVALID$"):
        encode_transaction_range(start, end, policy=POLICY, observed_at=NOW)


@pytest.mark.parametrize(
    "label",
    [datetime.min.replace(tzinfo=UTC), datetime.min.replace(tzinfo=UTC) + SECOND],
)
def test_offset_underflow_is_a_safe_validation_failure(label: datetime) -> None:
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_VALUE_INVALID$"):
        decode_transaction_label(label, policy=POLICY, observed_at=NOW)


def test_maximum_datetime_is_unsupported_without_epoch_float_conversion() -> None:
    with pytest.raises(ValueError, match="^TRANSACTION_TIME_WINDOW_UNSUPPORTED$"):
        decode_transaction_label(
            datetime.max.replace(tzinfo=UTC), policy=POLICY, observed_at=NOW
        )


@pytest.mark.parametrize("capture_delta", [timedelta(days=-1), timedelta(days=1)])
def test_observation_age_never_changes_offset_or_grants_freshness(
    capture_delta: timedelta,
) -> None:
    assert (
        decode_transaction_label(
            NOW + OFFSET, policy=POLICY, observed_at=NOW + capture_delta
        )
        == NOW
    )


def test_caller_must_apply_explicit_codec_exactly_once() -> None:
    decoded = decode_transaction_label(NOW + OFFSET, policy=POLICY, observed_at=NOW)
    assert decode_transaction_label(decoded, policy=POLICY, observed_at=NOW) == (
        NOW - OFFSET
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (START, START + SECOND),
        (NOW + MICROSECOND, NOW + SECOND + MICROSECOND),
        (END - SECOND, END - MICROSECOND),
    ],
)
def test_independent_explicit_policy_agrees_with_documented_market_window(
    start: datetime, end: datetime
) -> None:
    # Agreement checks a deliberate shared convention, not implied permission.
    market_start, market_end = encode_market_range(
        start, end, policy=PEPPERSTONE_POLICY, observed_at=NOW
    )
    assert str(POLICY) != str(PEPPERSTONE_POLICY)
    assert encode_transaction_range(start, end, policy=POLICY, observed_at=NOW) == (
        exact_seconds(market_start),
        exact_seconds(market_end),
    )
