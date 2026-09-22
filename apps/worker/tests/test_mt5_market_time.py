from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, localcontext
from enum import IntEnum
from numbers import Integral
from typing import cast

import pytest

from aurum_worker.mt5_market_time import (
    PEPPERSTONE_POLICY,
    UTC_POLICY,
    MarketTimePolicy,
    decode_market_epoch,
    encode_market_range,
)

START = datetime(2026, 3, 9, tzinfo=UTC)
END = datetime(2026, 11, 1, tzinfo=UTC)
NOW = datetime(2026, 9, 21, 9, 9, 32, tzinfo=UTC)
OFFSET = timedelta(hours=3)


def epoch(value: datetime) -> int:
    return int(value.timestamp())


@pytest.mark.parametrize("policy", [UTC_POLICY, PEPPERSTONE_POLICY])
def test_policy_decodes_exact_milliseconds(policy: MarketTimePolicy) -> None:
    label = NOW + OFFSET if policy == PEPPERSTONE_POLICY else NOW
    result = decode_market_epoch(
        epoch(label) * 1000 + 123,
        policy=policy,
        observed_at=NOW,
        milliseconds=True,
    )
    assert result == NOW + timedelta(milliseconds=123)
    assert result.tzinfo is UTC


@pytest.mark.parametrize(
    "value", [1_790_000_000, 1_790_000_000.125, Decimal("1790000000.125")]
)
def test_utc_policy_preserves_unshifted_epoch_semantics(
    value: int | float | Decimal,
) -> None:
    assert decode_market_epoch(value, policy=UTC_POLICY, observed_at=NOW) == (
        datetime.fromtimestamp(float(value), tz=UTC)
    )


def test_exact_microseconds_are_independent_of_decimal_context() -> None:
    with localcontext() as context:
        context.prec = 6
        assert (
            decode_market_epoch(
                Decimal("1790000000.123456"), policy=UTC_POLICY, observed_at=NOW
            ).microsecond
            == 123456
        )
        assert (
            decode_market_epoch(
                Decimal("1790000000123.456"),
                policy=UTC_POLICY,
                observed_at=NOW,
                milliseconds=True,
            ).microsecond
            == 123456
        )


@pytest.mark.parametrize(
    ("raw", "microseconds"),
    [
        (Decimal("1.0000004"), 0),
        (Decimal("1.0000005"), 0),
        (Decimal("1.0000015"), 2),
        (Decimal("1.9999999"), 0),
    ],
)
def test_submicrosecond_values_round_half_even(raw: Decimal, microseconds: int) -> None:
    assert (
        decode_market_epoch(raw, policy=UTC_POLICY, observed_at=NOW).microsecond
        == microseconds
    )


@pytest.mark.parametrize("offset_hours", [-5, 0, 7])
@pytest.mark.parametrize("policy", [UTC_POLICY, PEPPERSTONE_POLICY])
def test_range_round_trip_uses_instants_not_display_timezone(
    offset_hours: int, policy: MarketTimePolicy
) -> None:
    display_zone = timezone(timedelta(hours=offset_hours))
    start = NOW.astimezone(display_zone)
    end = (NOW + timedelta(minutes=5)).astimezone(display_zone)
    encoded_start, encoded_end = encode_market_range(
        start, end, policy=policy, observed_at=NOW.astimezone(display_zone)
    )
    assert encoded_start.tzinfo is UTC
    assert encoded_end.tzinfo is UTC
    assert encoded_start == NOW + (
        OFFSET if policy == PEPPERSTONE_POLICY else timedelta()
    )
    assert (
        decode_market_epoch(epoch(encoded_start), policy=policy, observed_at=NOW)
        == start
    )
    assert (
        decode_market_epoch(epoch(encoded_end), policy=policy, observed_at=NOW) == end
    )


@pytest.mark.parametrize("instant", [START, END - timedelta(microseconds=1)])
def test_policy_allows_only_interior_and_start_of_supported_window(
    instant: datetime,
) -> None:
    encoded, _ = encode_market_range(
        instant, instant, policy=PEPPERSTONE_POLICY, observed_at=instant
    )
    # Avoid float timestamp rounding at the upper microsecond boundary.
    whole = epoch(encoded)
    raw = Decimal(whole) + Decimal(encoded.microsecond) / Decimal(1_000_000)
    assert (
        decode_market_epoch(raw, policy=PEPPERSTONE_POLICY, observed_at=instant)
        == instant
    )


@pytest.mark.parametrize(
    "instant",
    [
        START - timedelta(microseconds=1),
        END,
        datetime(2026, 3, 8, 12, tzinfo=UTC),
        datetime(2026, 11, 1, 12, tzinfo=UTC),
        datetime(2027, 9, 21, tzinfo=UTC),
    ],
)
def test_policy_rejects_unsupported_event_and_query_boundaries(
    instant: datetime,
) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_WINDOW_UNSUPPORTED$"):
        decode_market_epoch(
            Decimal(epoch(instant + OFFSET))
            + Decimal(instant.microsecond) / Decimal(1_000_000),
            policy=PEPPERSTONE_POLICY,
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="^MARKET_TIME_WINDOW_UNSUPPORTED$"):
        encode_market_range(
            instant, instant, policy=PEPPERSTONE_POLICY, observed_at=NOW
        )


@pytest.mark.parametrize("observation", [START - timedelta(seconds=1), END])
def test_supported_event_does_not_allow_unsupported_observation(
    observation: datetime,
) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_WINDOW_UNSUPPORTED$"):
        decode_market_epoch(
            epoch(NOW + OFFSET), policy=PEPPERSTONE_POLICY, observed_at=observation
        )
    with pytest.raises(ValueError, match="^MARKET_TIME_WINDOW_UNSUPPORTED$"):
        encode_market_range(
            NOW, NOW, policy=PEPPERSTONE_POLICY, observed_at=observation
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [(START - timedelta(seconds=1), NOW), (NOW, END)],
)
def test_both_query_bounds_must_be_supported(start: datetime, end: datetime) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_WINDOW_UNSUPPORTED$"):
        encode_market_range(start, end, policy=PEPPERSTONE_POLICY, observed_at=NOW)


def test_no_age_calibration_or_implicit_freshness_grant() -> None:
    raw = epoch(NOW + OFFSET)
    for observation in (NOW - timedelta(days=1), NOW + timedelta(days=1)):
        assert (
            decode_market_epoch(raw, policy=PEPPERSTONE_POLICY, observed_at=observation)
            == NOW
        )


def test_detectable_double_decoding_at_window_start_is_rejected() -> None:
    decoded = decode_market_epoch(
        epoch(START + OFFSET), policy=PEPPERSTONE_POLICY, observed_at=NOW
    )
    with pytest.raises(ValueError, match="^MARKET_TIME_WINDOW_UNSUPPORTED$"):
        decode_market_epoch(epoch(decoded), policy=PEPPERSTONE_POLICY, observed_at=NOW)


def test_interior_raw_numeric_cannot_prove_it_has_not_already_been_decoded() -> None:
    # No source tags exist in an epoch scalar: callers must enforce single decode.
    assert (
        decode_market_epoch(epoch(NOW), policy=PEPPERSTONE_POLICY, observed_at=NOW)
        == NOW - OFFSET
    )


@pytest.mark.parametrize("milliseconds", [False, True])
@pytest.mark.parametrize(
    "raw",
    [
        True,
        False,
        None,
        "1790000000",
        0,
        -1,
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        10**40,
        Decimal("1e1000"),
        Decimal("1e-1000"),
    ],
)
def test_invalid_epoch_is_rejected_with_constant_error(
    raw: object, milliseconds: bool
) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_VALUE_INVALID$"):
        decode_market_epoch(
            cast(int | float | Decimal, raw),
            policy=UTC_POLICY,
            observed_at=NOW,
            milliseconds=milliseconds,
        )


def test_millisecond_selector_must_be_boolean() -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_VALUE_INVALID$"):
        decode_market_epoch(
            epoch(NOW),
            policy=UTC_POLICY,
            observed_at=NOW,
            milliseconds=cast(bool, 1),
        )


@pytest.mark.parametrize("policy", ["", "winter", None, True])
def test_unknown_policy_fails_closed(policy: object) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_POLICY_INVALID$"):
        decode_market_epoch(
            epoch(NOW), policy=cast(MarketTimePolicy, policy), observed_at=NOW
        )
    with pytest.raises(ValueError, match="^MARKET_TIME_POLICY_INVALID$"):
        encode_market_range(
            NOW, NOW, policy=cast(MarketTimePolicy, policy), observed_at=NOW
        )


class MissingOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> None:
        return None


@pytest.mark.parametrize(
    "value",
    [NOW.replace(tzinfo=None), NOW.replace(tzinfo=MissingOffset()), None, "raw"],
)
def test_observation_and_query_dates_must_be_aware(value: object) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_OBSERVATION_INVALID$"):
        decode_market_epoch(
            epoch(NOW), policy=UTC_POLICY, observed_at=cast(datetime, value)
        )
    with pytest.raises(ValueError, match="^MARKET_TIME_RANGE_INVALID$"):
        encode_market_range(
            cast(datetime, value), NOW, policy=UTC_POLICY, observed_at=NOW
        )
    with pytest.raises(ValueError, match="^MARKET_TIME_RANGE_INVALID$"):
        encode_market_range(
            NOW, cast(datetime, value), policy=UTC_POLICY, observed_at=NOW
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [(NOW, NOW - timedelta(seconds=1)), (datetime(1970, 1, 1, tzinfo=UTC), NOW)],
)
def test_unordered_or_nonpositive_range_is_invalid(
    start: datetime, end: datetime
) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_RANGE_INVALID$"):
        encode_market_range(start, end, policy=UTC_POLICY, observed_at=NOW)


@pytest.mark.parametrize(
    ("raw", "milliseconds"),
    [
        (Decimal("253402300799.999999"), False),
        (Decimal("253402300799999.999"), True),
    ],
)
def test_maximum_representable_timestamp_preserves_precision(
    raw: Decimal, milliseconds: bool
) -> None:
    assert decode_market_epoch(
        raw, policy=UTC_POLICY, observed_at=NOW, milliseconds=milliseconds
    ) == datetime.max.replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "milliseconds"),
    [(Decimal("253402300800"), False), (Decimal("253402300800000"), True)],
)
def test_datetime_overflow_is_a_safe_validation_failure(
    raw: Decimal, milliseconds: bool
) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_VALUE_INVALID$"):
        decode_market_epoch(
            raw, policy=UTC_POLICY, observed_at=NOW, milliseconds=milliseconds
        )


class SyntheticIntegral:
    def __init__(self, value: int) -> None:
        self.value = value

    def __int__(self) -> int:
        return self.value


Integral.register(SyntheticIntegral)


class EpochEnum(IntEnum):
    OBSERVED = 1_790_000_000


@pytest.mark.parametrize("policy", [UTC_POLICY, PEPPERSTONE_POLICY])
@pytest.mark.parametrize("milliseconds", [False, True])
def test_integral_scalars_do_not_require_a_numpy_dependency(
    policy: MarketTimePolicy, milliseconds: bool
) -> None:
    label = NOW + OFFSET if policy == PEPPERSTONE_POLICY else NOW
    raw = epoch(label) * (1000 if milliseconds else 1)
    scalar = SyntheticIntegral(raw)
    assert isinstance(scalar, Integral)
    assert (
        decode_market_epoch(
            scalar, policy=policy, observed_at=NOW, milliseconds=milliseconds
        )
        == NOW
    )


def test_integral_enum_is_converted_numerically() -> None:
    assert decode_market_epoch(
        EpochEnum.OBSERVED, policy=UTC_POLICY, observed_at=NOW
    ) == datetime.fromtimestamp(int(EpochEnum.OBSERVED), tz=UTC)


@pytest.mark.parametrize("raw", [0, -1, 10**40])
def test_invalid_integral_scalar_preserves_validation(raw: int) -> None:
    with pytest.raises(ValueError, match="^MARKET_TIME_VALUE_INVALID$"):
        decode_market_epoch(
            cast(Integral, SyntheticIntegral(raw)), policy=UTC_POLICY, observed_at=NOW
        )


@pytest.mark.parametrize("policy", [UTC_POLICY, PEPPERSTONE_POLICY])
@pytest.mark.parametrize("milliseconds", [False, True])
def test_actual_numpy_int64_market_timestamp(
    policy: MarketTimePolicy, milliseconds: bool
) -> None:
    numpy = pytest.importorskip("numpy")
    label = NOW + OFFSET if policy == PEPPERSTONE_POLICY else NOW
    raw = numpy.int64(epoch(label) * (1000 if milliseconds else 1))
    assert isinstance(raw, Integral)
    assert (
        decode_market_epoch(
            raw, policy=policy, observed_at=NOW, milliseconds=milliseconds
        )
        == NOW
    )


def test_actual_numpy_boolean_is_not_an_epoch() -> None:
    numpy = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="^MARKET_TIME_VALUE_INVALID$"):
        decode_market_epoch(numpy.bool_(True), policy=UTC_POLICY, observed_at=NOW)
