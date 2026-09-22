from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from mt5_factories import NOW
from pydantic import ValidationError
from test_shadow_market import read_port, service
from test_shadow_risk import _input

from aurum_worker.models.mt5 import Mt5WorkerConfig
from aurum_worker.shadow.context import (
    MissingEvidenceProvider,
    ShadowControlContext,
    ShadowEvidenceReceipt,
    ShadowExternalEvidence,
    ValidatedEvidenceProvider,
    build_risk_input,
    risk_input_digest,
    risk_provenance,
)
from aurum_worker.shadow.market import MarketCapture
from aurum_worker.shadow.risk import evaluate_shadow_risk


def capture_and_control() -> tuple[MarketCapture, ShadowControlContext]:
    adapter = read_port()
    adapter.ticks["XAUUSD"] = adapter.ticks["XAUUSD"].model_copy(
        update={
            "ask": Decimal("2345.12"),
            "spread_price": Decimal("0.02"),
            "spread_points": Decimal("2"),
        }
    )
    capture = service(adapter).capture_bundle(trace_id="context-test")
    assert isinstance(capture, MarketCapture)
    policy = _input().policy
    assert policy is not None
    return capture, ShadowControlContext(
        owner_id=policy.owner_id,
        trading_account_id=policy.trading_account_id,
        observed_at=NOW,
        mode_version=1,
        system_state="running",
        policy=policy,
    )


def sourced_evidence(
    capture: MarketCapture, control: ShadowControlContext
) -> ShadowExternalEvidence:
    inputs = _input()
    assert (
        inputs.account_risk is not None
        and inputs.safety is not None
        and inputs.costs is not None
    )
    provenance = risk_provenance(capture, control)
    return ShadowExternalEvidence(
        account_risk=inputs.account_risk.model_copy(update={"provenance": provenance}),
        safety=inputs.safety.model_copy(update={"provenance": provenance}),
        costs=inputs.costs.model_copy(update={"provenance": provenance}),
        receipts=tuple(
            ShadowEvidenceReceipt.model_validate(
                {
                    "kind": kind,
                    "source_id": "fictional-test-provider",
                    "source_version": "test-v1",
                    "evidence_digest": "a" * 64,
                    "provenance": provenance,
                    "observed_at": NOW,
                    "valid_until": NOW + timedelta(seconds=10),
                    "covered_from": NOW - timedelta(days=7),
                    "covered_until": NOW + timedelta(minutes=15),
                }
            )
            for kind in ("ledger", "safety", "news", "costs")
        ),
        unavailable_reasons=(),
    )


def test_missing_provider_flows_to_real_risk_block_without_fabricated_defaults() -> (
    None
):
    capture, control = capture_and_control()
    evidence = MissingEvidenceProvider().read_evidence(capture, control, NOW)
    assert (
        evidence.account_risk is None
        and evidence.safety is None
        and evidence.costs is None
    )
    candidate = _input().candidate.model_copy(
        update={"provenance": risk_provenance(capture, control)}
    )
    result = evaluate_shadow_risk(
        build_risk_input(capture, control, candidate, evidence, Mt5WorkerConfig(), NOW)
    )
    assert result.outcome == "BLOCK" and result.calculated_volume is None
    assert {check.code for check in result.checks if not check.passed} >= {
        "ACCOUNT_RISK_AVAILABLE",
        "SAFETY_AVAILABLE",
        "COSTS_AVAILABLE",
    }


def test_explicit_source_receipts_can_reach_pure_calculation_without_eligibility() -> (
    None
):
    capture, control = capture_and_control()
    evidence = sourced_evidence(capture, control)
    candidate = _input().candidate.model_copy(
        update={
            "provenance": risk_provenance(capture, control),
            "market_trace_id": capture.tick.trace_id,
            "entry_price": capture.tick.ask,
            "stop_loss_price": capture.tick.ask - Decimal("5"),
            "take_profit_price": capture.tick.ask + Decimal("10"),
        }
    )
    result = evaluate_shadow_risk(
        build_risk_input(capture, control, candidate, evidence, Mt5WorkerConfig(), NOW)
    )
    assert result.outcome == "PASS"
    assert result.grants_eligibility is False


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "wrong_binding",
        "stale",
        "freshened",
        "expired",
        "news_gap",
        "ledger_gap",
        "uncertain",
    ],
)
def test_external_evidence_failure_never_becomes_ready(change: str) -> None:
    capture, control = capture_and_control()
    evidence = sourced_evidence(capture, control)
    receipts = list(evidence.receipts)
    if change == "missing":
        receipts.pop()
    elif change == "wrong_binding":
        receipts[0] = receipts[0].model_copy(
            update={
                "provenance": receipts[0].provenance.model_copy(
                    update={"server_fingerprint": "wrong"}
                )
            }
        )
    elif change in ("stale", "freshened"):
        receipts[0] = receipts[0].model_copy(
            update={
                "observed_at": NOW - timedelta(seconds=11 if change == "stale" else 1)
            }
        )
    elif change == "expired":
        receipts[0] = receipts[0].model_copy(
            update={"valid_until": NOW - timedelta(seconds=1)}
        )
    elif change == "news_gap":
        receipts[2] = receipts[2].model_copy(
            update={"covered_until": NOW + timedelta(minutes=14)}
        )
    elif change == "ledger_gap":
        receipts[0] = receipts[0].model_copy(update={"covered_from": NOW})
    else:
        evidence = evidence.model_copy(
            update={"unavailable_reasons": ("SOURCE_UNCERTAIN",)}
        )
    evidence = evidence.model_copy(update={"receipts": tuple(receipts)})
    result = ValidatedEvidenceProvider(
        lambda _capture, _control, _at: evidence
    ).read_evidence(capture, control, NOW)
    assert (
        result.account_risk is None and result.safety is None and result.costs is None
    )
    assert result.unavailable_reasons == ("EXTERNAL_EVIDENCE_UNAVAILABLE",)


def test_provider_failure_suppresses_exception_details() -> None:
    capture, control = capture_and_control()

    def failed(
        _capture: MarketCapture, _control: ShadowControlContext, _at: datetime
    ) -> ShadowExternalEvidence:
        raise RuntimeError("internal provider detail that must not escape")

    result = ValidatedEvidenceProvider(failed).read_evidence(capture, control, NOW)
    assert "internal" not in result.model_dump_json()


@pytest.mark.parametrize("age", [5.000001, 6, 11])
def test_stale_control_cannot_be_refreshed_by_new_external_receipts(age: float) -> None:
    capture, control = capture_and_control()
    evidence = sourced_evidence(capture, control)
    stale = control.model_copy(update={"observed_at": NOW - timedelta(seconds=age)})
    result = ValidatedEvidenceProvider(
        lambda _capture, _control, _at: evidence
    ).read_evidence(capture, stale, NOW)
    assert result.safety is None


def test_risk_input_digest_is_canonical_and_changes_with_source_input() -> None:
    value = _input()
    first = risk_input_digest(value)
    assert len(first) == 64
    assert first == risk_input_digest(value)
    offset = value.model_copy(
        update={
            "evaluated_at": value.evaluated_at.astimezone(timezone(timedelta(hours=7)))
        }
    )
    assert first == risk_input_digest(offset)
    assert value.costs is not None
    changed = value.model_copy(
        update={
            "costs": value.costs.model_copy(
                update={"commission_round_trip_per_lot": Decimal("1.000001")}
            )
        }
    )
    assert first != risk_input_digest(changed)


def test_risk_input_digest_revalidates_untrusted_model_copies() -> None:
    value = _input().model_copy(update={"maximum_tick_age_seconds": True})
    with pytest.raises(ValidationError):
        risk_input_digest(value)


@pytest.mark.parametrize("state", ["paused", None, True])
def test_unvalidated_control_copy_cannot_supply_ready_evidence(state: object) -> None:
    capture, control = capture_and_control()
    evidence = sourced_evidence(capture, control)
    changed = control.model_copy(update={"system_state": state})
    result = ValidatedEvidenceProvider(
        lambda _capture, _control, _at: evidence
    ).read_evidence(capture, changed, NOW)
    assert result.safety is None and not result.receipts
