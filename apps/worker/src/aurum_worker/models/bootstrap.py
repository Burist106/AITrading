"""Local Bootstrap account observations and successful startup report."""

from typing import Literal

from pydantic import AwareDatetime

from aurum_worker.models.base import Identifier, NonNegativeInt, WireModel


class AccountInspection(WireModel):
    """Credential-free account classification returned by a broker read adapter."""

    is_demo: bool | None
    observed_at: AwareDatetime


class WorkerStartupReport(WireModel):
    """Evidence that fixed Bootstrap checks passed before Shadow startup."""

    started_at: AwareDatetime
    environment: Literal["DEMO_ONLY"]
    runtime_mode: Literal["shadow"]
    canonical_symbol: Literal["XAUUSD"]
    account_verified_demo: Literal[True]
    detected_open_positions: NonNegativeInt
    symbol_specification_version: Identifier
