"""Bounded diagnostics for the existing public-company market-policy guard.

This pure helper neither selects a policy nor verifies an account or source. Its
only accepted string forms preserve the existing trim/casefold provider rule.
No raw company value is returned, coerced to text, logged, or retained.
"""

from __future__ import annotations

PUBLIC_PROVIDER_FAILURE_DETAILS: frozenset[str] = frozenset(
    {
        "PUBLIC_PROVIDER_MISSING",
        "PUBLIC_PROVIDER_INVALID",
        "PUBLIC_PROVIDER_EMPTY",
        "PUBLIC_PROVIDER_METAQUOTES",
        "PUBLIC_PROVIDER_UNSUPPORTED",
    }
)

_METAQUOTES_COMPANIES = frozenset(
    {"metaquotes ltd.", "metaquotes software corp.", "metaquotes software corp"}
)


def provider_failure_detail(company: object) -> str | None:
    """Return a bounded failure detail, or None for the unchanged provider rule."""

    if company is None:
        return "PUBLIC_PROVIDER_MISSING"
    if not isinstance(company, str):
        return "PUBLIC_PROVIDER_INVALID"
    # Builtin methods avoid coercion and hostile string-subclass overrides.
    normalized = str.casefold(str.strip(company))
    if not normalized:
        return "PUBLIC_PROVIDER_EMPTY"
    if normalized == "pepperstone" or normalized.startswith("pepperstone "):
        return None
    if normalized in _METAQUOTES_COMPANIES:
        return "PUBLIC_PROVIDER_METAQUOTES"
    return "PUBLIC_PROVIDER_UNSUPPORTED"
