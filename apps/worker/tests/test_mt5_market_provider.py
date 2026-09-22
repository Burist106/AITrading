from __future__ import annotations

import pytest

from aurum_worker.mt5_market_provider import (
    PUBLIC_PROVIDER_FAILURE_DETAILS,
    provider_failure_detail,
)


def test_public_failure_allowlist_is_exact_and_immutable() -> None:
    assert isinstance(PUBLIC_PROVIDER_FAILURE_DETAILS, frozenset)
    assert PUBLIC_PROVIDER_FAILURE_DETAILS == {
        "PUBLIC_PROVIDER_MISSING",
        "PUBLIC_PROVIDER_INVALID",
        "PUBLIC_PROVIDER_EMPTY",
        "PUBLIC_PROVIDER_METAQUOTES",
        "PUBLIC_PROVIDER_UNSUPPORTED",
    }


def test_missing_company_is_distinct_from_invalid_or_empty() -> None:
    assert provider_failure_detail(None) == "PUBLIC_PROVIDER_MISSING"


@pytest.mark.parametrize("company", [True, False, 0, 123, b"Pepperstone", [], {}])
def test_non_strings_are_not_coerced(company: object) -> None:
    assert provider_failure_detail(company) == "PUBLIC_PROVIDER_INVALID"


@pytest.mark.parametrize("company", ["", " ", "\t\r\n", "\u00a0", "\u2003"])
def test_empty_after_existing_trim_has_distinct_code(company: str) -> None:
    assert provider_failure_detail(company) == "PUBLIC_PROVIDER_EMPTY"


@pytest.mark.parametrize(
    "company",
    [
        "MetaQuotes Ltd.",
        "METAQUOTES LTD.",
        "  MetaQuotes Ltd.\t",
        "MetaQuotes Software Corp.",
        "MetaQuotes Software Corp",
        "\u00a0MetaQuotes Software Corp.\u00a0",
    ],
)
def test_only_exact_known_metaquotes_company_names_receive_public_category(
    company: str,
) -> None:
    assert provider_failure_detail(company) == "PUBLIC_PROVIDER_METAQUOTES"


@pytest.mark.parametrize(
    "company",
    [
        "Pepperstone",
        "PEPPERSTONE",
        "  pepperstone\t",
        "Pepperstone Test",
        "Pepperstone Group Limited",
        "Pepperstone \tTest",
        "Pepperstone \nTest",
        "Pepperstone \u200b",
        "\u00a0Pepperstone\u00a0",
        "Pepperſtone",
    ],
)
def test_acceptance_preserves_original_trim_casefold_ascii_space_prefix(
    company: str,
) -> None:
    assert provider_failure_detail(company) is None


@pytest.mark.parametrize(
    "company",
    [
        "Pepperstoneish",
        "Pepperstone-Test",
        "Pepperstone.Test",
        "Other Pepperstone",
        "Pepper stone",
        "Pepperstone\tTest",
        "Pepperstone\nTest",
        "Pepperstone\u00a0Test",
        "Pepperstone\u2003Test",
        "Pepperstone\u200bTest",
        "Pepperstone\x00",
        "Pеpperstone",  # Cyrillic e is not an ASCII e.
        "Ｐｅｐｐｅｒｓｔｏｎｅ",
        "MetaQuotes",
        "MetaQuotes Ltd",
        "MetaQuotes Ltd. Test",
        "MetaQuotes Software Corp..",
        "MetaQuotes\tSoftware Corp.",
        "MetaQuotes\u00a0Software Corp.",
        "MetaQuotes  Software Corp.",
        "\u200b",
        "synthetic-private-company-detail",
    ],
)
def test_near_matches_and_internal_unicode_whitespace_are_not_normalized(
    company: str,
) -> None:
    detail = provider_failure_detail(company)
    assert detail == "PUBLIC_PROVIDER_UNSUPPORTED"
    assert detail in PUBLIC_PROVIDER_FAILURE_DETAILS
    assert "synthetic-private-company-detail" not in detail


@pytest.mark.parametrize("trim", ["", " ", "\t", "\u00a0"])
@pytest.mark.parametrize(
    "base", ["pepperstone", "PEPPERSTONE", "Pepperſtone", "pepperstoneish", "Other"]
)
@pytest.mark.parametrize("suffix", ["", " Test", "\tTest", "\u00a0Test", "-Test"])
def test_ordinary_string_acceptance_has_exact_parity_with_previous_guard(
    trim: str, base: str, suffix: str
) -> None:
    company = trim + base + suffix + trim
    accepted_before = company.strip().casefold() == "pepperstone" or (
        company.strip().casefold().startswith("pepperstone ")
    )
    assert (provider_failure_detail(company) is None) is accepted_before


class HostileObject:
    def __str__(self) -> str:
        raise AssertionError("Object must not be converted to text.")

    def __repr__(self) -> str:
        raise AssertionError("Object must not be represented.")

    def __bool__(self) -> bool:
        raise AssertionError("Object truthiness must not be consulted.")

    def __eq__(self, other: object) -> bool:
        raise AssertionError("Object equality must not be consulted.")

    def strip(self) -> str:
        raise AssertionError("Object methods must not be consulted.")


def test_hostile_object_has_no_conversion_or_comparison_side_effects() -> None:
    assert provider_failure_detail(HostileObject()) == "PUBLIC_PROVIDER_INVALID"


class HostileString(str):
    def __str__(self) -> str:
        raise AssertionError("String must not be coerced.")

    def strip(self, chars: str | None = None) -> str:
        raise AssertionError("String strip override must not be called.")

    def casefold(self) -> str:
        raise AssertionError("String casefold override must not be called.")


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        ("Pepperstone Test", None),
        ("MetaQuotes Ltd.", "PUBLIC_PROVIDER_METAQUOTES"),
        ("  ", "PUBLIC_PROVIDER_EMPTY"),
        ("synthetic-private-company-detail", "PUBLIC_PROVIDER_UNSUPPORTED"),
    ],
)
def test_string_subclasses_are_classified_from_content_without_override_execution(
    contents: str, expected: str | None
) -> None:
    assert provider_failure_detail(HostileString(contents)) == expected
