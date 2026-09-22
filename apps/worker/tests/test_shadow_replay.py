"""Historical replay uses centralized constructed inputs, never real credentials."""

from __future__ import annotations

import json
import socket
from datetime import UTC, timedelta, timezone
from decimal import ROUND_DOWN, Decimal, localcontext
from typing import Any
from uuid import UUID

import pytest
from mt5_factories import NOW
from shadow_factories import MemoryReplayArchive
from test_shadow_pipeline import pipeline

from aurum_worker.shadow.context import risk_input_digest
from aurum_worker.shadow.models import ShadowCheck, ShadowCycle
from aurum_worker.shadow.replay import (
    MAX_REPLAY_BYTES,
    ReplayEnvelope,
    ReplayError,
    canonical_replay_json,
    make_replay_envelope,
    parse_replay_json,
    verify_replay,
)
from aurum_worker.shadow.risk import ShadowRiskInput, evaluate_shadow_risk
from aurum_worker.shadow.strategy import evaluate_baseline_eligibility


def archived(*, direction: str = "BUY", complete: bool = True) -> ReplayEnvelope:
    host, _ = pipeline(direction=direction, complete=complete)
    cycle = host.run_cycle().cycle
    assert cycle is not None
    assert isinstance(host.replay_archive, MemoryReplayArchive)
    return host.replay_archive.envelopes[cycle.id]


def verify(envelope: ReplayEnvelope) -> str:
    result = verify_replay(
        envelope,
        owner_id=envelope.cycle.owner_id,
        trading_account_id=envelope.cycle.trading_account_id,
    )
    assert result.grants_eligibility is False
    return result.status


def with_input(envelope: ReplayEnvelope, value: ShadowRiskInput) -> ReplayEnvelope:
    """Bind a changed test input, without modifying the recorded output."""
    assert envelope.cycle.risk is not None
    cycle = envelope.cycle.model_copy(
        update={
            "risk": envelope.cycle.risk.model_copy(
                update={"input_digest": risk_input_digest(value)}
            )
        }
    )
    return make_replay_envelope(cycle, value)


@pytest.mark.parametrize(
    "direction,complete", [("BUY", True), ("SELL", True), ("BUY", False)]
)
def test_pipeline_archives_full_repeatable_risk_input(
    direction: str, complete: bool
) -> None:
    envelope = archived(direction=direction, complete=complete)
    assert verify(envelope) == "MATCH"
    wire = canonical_replay_json(envelope)
    decoded = parse_replay_json(wire)
    assert decoded == envelope
    assert ReplayEnvelope.model_validate_json(wire) == envelope
    assert canonical_replay_json(decoded) == wire
    assert len(wire.encode("utf-8")) < MAX_REPLAY_BYTES
    assert (json.loads(wire)["risk_input"]["account_risk"] is not None) is complete
    for _ in range(3):
        assert verify(decoded) == "MATCH"
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_DOWN
        assert verify(decoded) == "MATCH"
        assert canonical_replay_json(decoded) == wire


def test_full_inputs_and_original_context_are_retained_not_just_a_digest() -> None:
    envelope = archived()
    value = envelope.risk_input
    decoded = parse_replay_json(canonical_replay_json(envelope)).risk_input
    assert decoded == value
    assert decoded.account_risk is not None and decoded.costs is not None
    assert isinstance(decoded.account_risk.equity, Decimal)
    assert isinstance(decoded.costs.commission_round_trip_per_lot, Decimal)
    assert decoded.policy is not None and decoded.reconciliation is not None
    assert value.reconciliation is not None
    assert (
        decoded.reconciliation.order_history_evidence
        == value.reconciliation.order_history_evidence
    )
    assert decoded.policy.minimum_sample_size == 30
    assert decoded.evaluated_at == NOW
    assert decoded.account is not None and "••••" in decoded.account.masked_login


def test_verification_is_network_and_clock_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = archived()

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay must be local and deterministic")

    monkeypatch.setattr(socket, "socket", forbidden)
    assert verify(envelope) == "MATCH"


@pytest.mark.parametrize("field", ["owner_id", "trading_account_id"])
def test_requested_identity_is_independently_enforced(field: str) -> None:
    envelope = archived()
    identities = {
        "owner_id": envelope.cycle.owner_id,
        "trading_account_id": envelope.cycle.trading_account_id,
    }
    identities[field] = UUID("00000000-0000-4000-8000-000000000099")
    result = verify_replay(envelope, **identities)
    assert result.status == "UNAVAILABLE"
    assert result.code == "REPLAY_IDENTITY_MISMATCH"


@pytest.mark.parametrize(
    "field,value",
    [
        ("environment", "LIVE"),
        ("mode", "AUTO"),
        ("schema_version", "shadow-replay-v2"),
        ("grants_eligibility", True),
        ("grants_eligibility", 0),
    ],
)
def test_unsafe_top_level_is_rejected(field: str, value: object) -> None:
    wire = json.loads(canonical_replay_json(archived()))
    wire[field] = value
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        parse_replay_json(json.dumps(wire))


@pytest.mark.parametrize(
    "path",
    [
        ("schema_version",),
        ("cycle", "grants_eligibility"),
        ("cycle", "risk", "version"),
        ("risk_input", "account", "schema_version"),
        ("risk_input", "policy", "stopLossRequired"),
        ("risk_input", "costs"),
    ],
)
def test_missing_defaults_or_nullable_fields_are_rejected(
    path: tuple[str, ...],
) -> None:
    wire = json.loads(canonical_replay_json(archived()))
    current = wire
    for part in path[:-1]:
        current = current[part]
    del current[path[-1]]
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        parse_replay_json(json.dumps(wire))


@pytest.mark.parametrize(
    "path,value",
    [
        (("risk_input", "account", "masked_login"), "12345678"),
        (("risk_input", "account", "masked_server"), "unmasked-example-server"),
        (("risk_input", "provenance", "account_fingerprint"), "12345678"),
        (("risk_input", "account", "server_fingerprint"), "raw-server"),
        (
            ("risk_input", "specification", "specification_fingerprint"),
            "mt5-spec-v1:test",
        ),
        (("risk_input", "account", "source"), "fake_mt5"),
        (("risk_input", "candidate", "entry_price"), 2000.02),
        (("risk_input", "tick", "bid"), 2000),
        (("risk_input", "safety", "worker_healthy"), 1),
        (("risk_input", "policy", "stopLossRequired"), 1),
        (("risk_input", "policy", "maximumOpenPositions"), True),
        (("risk_input", "policy", "riskPerTradePct"), "0.25"),
        (("risk_input", "evaluated_at"), "2026-09-22T00:00:00.1234567Z"),
        (("risk_input", "evaluated_at"), 1700000000),
        (("risk_input", "evaluated_at"), "2026-09-22T07:00:00+07:00"),
    ],
)
def test_untrusted_nested_json_is_not_coerced(
    path: tuple[str, ...], value: object
) -> None:
    wire = json.loads(canonical_replay_json(archived()))
    current = wire
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$") as failure:
        parse_replay_json(json.dumps(wire))
    assert failure.value.__cause__ is None


@pytest.mark.parametrize(
    "field", ["login", "server", "password", "token", "unexpected"]
)
def test_unknown_identity_or_secret_fields_are_never_accepted(field: str) -> None:
    wire = json.loads(canonical_replay_json(archived()))
    wire["risk_input"]["account"][field] = "untrusted-input-must-not-appear-in-error"
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$") as failure:
        parse_replay_json(json.dumps(wire))
    assert "untrusted-input" not in str(failure.value)


def test_duplicate_nested_keys_nonfinite_and_oversize_are_rejected() -> None:
    wire = canonical_replay_json(archived())
    duplicate = wire.replace('"mode":"SHADOW"', '"mode":"SHADOW","mode":"SHADOW"')
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        parse_replay_json(duplicate)
    nested = wire.replace(
        '"worker_healthy":true', '"worker_healthy":true,"worker_healthy":false'
    )
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        parse_replay_json(nested)
    for value in ["NaN", "Infinity", "-Infinity", "[]", "null", "{", '"\ud800"']:
        with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
            parse_replay_json(value)
    with pytest.raises(ReplayError, match="^REPLAY_TOO_LARGE$"):
        parse_replay_json(" " * (MAX_REPLAY_BYTES + 1))


def test_changed_input_without_matching_digest_is_rejected() -> None:
    wire: dict[str, Any] = json.loads(canonical_replay_json(archived()))
    wire["risk_input"]["costs"]["commission_round_trip_per_lot"] = "100"
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        parse_replay_json(json.dumps(wire))


def test_rebound_changed_input_is_a_calculation_mismatch() -> None:
    envelope = archived()
    assert envelope.risk_input.costs is not None
    costs = envelope.risk_input.costs.model_copy(
        update={"commission_round_trip_per_lot": Decimal("10000")}
    )
    changed = with_input(
        envelope, envelope.risk_input.model_copy(update={"costs": costs})
    )
    result = verify_replay(
        changed,
        owner_id=changed.cycle.owner_id,
        trading_account_id=changed.cycle.trading_account_id,
    )
    assert result.status == "MISMATCH" and result.code == "REPLAY_RISK_MISMATCH"


@pytest.mark.parametrize(
    "field", ["calculated_volume", "estimated_loss_usd", "estimated_net_reward_usd"]
)
def test_every_recorded_amount_is_recalculated(field: str) -> None:
    envelope = archived()
    assert envelope.cycle.risk is not None
    changed = envelope.cycle.risk.model_copy(update={field: Decimal("0.00001")})
    envelope = make_replay_envelope(
        envelope.cycle.model_copy(update={"risk": changed}), envelope.risk_input
    )
    assert verify(envelope) == "MISMATCH"


def test_ordered_full_hard_check_set_is_recalculated() -> None:
    envelope = archived()
    assert envelope.cycle.risk is not None
    risk = envelope.cycle.risk.model_copy(
        update={"checks": envelope.cycle.risk.checks[::-1]}
    )
    assert (
        verify(
            make_replay_envelope(
                envelope.cycle.model_copy(update={"risk": risk}), envelope.risk_input
            )
        )
        == "MISMATCH"
    )


def test_baseline_eligibility_uses_original_policy_minimum_sample() -> None:
    envelope = archived()
    assert envelope.cycle.eligibility is not None
    changed = envelope.cycle.eligibility.model_copy(update={"minimum_sample_size": 31})
    envelope = make_replay_envelope(
        envelope.cycle.model_copy(update={"eligibility": changed}), envelope.risk_input
    )
    result = verify_replay(
        envelope,
        owner_id=envelope.cycle.owner_id,
        trading_account_id=envelope.cycle.trading_account_id,
    )
    assert result.status == "MISMATCH"
    assert result.code == "REPLAY_ELIGIBILITY_MISMATCH"


def test_original_risk_timestamp_can_follow_cycle_timestamp() -> None:
    envelope = archived(complete=False)
    changed = envelope.risk_input.model_copy(
        update={"evaluated_at": NOW + timedelta(seconds=1)}
    )
    envelope = with_input(envelope, changed)
    assert verify(envelope) == "MATCH"
    assert parse_replay_json(
        canonical_replay_json(envelope)
    ).risk_input.evaluated_at == NOW + timedelta(seconds=1)


@pytest.mark.parametrize("delta", [-1, 601])
def test_evaluation_order_and_bounded_delay(delta: int) -> None:
    envelope = archived()
    changed = envelope.risk_input.model_copy(
        update={"evaluated_at": NOW + timedelta(seconds=delta)}
    )
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        with_input(envelope, changed)


def test_historical_expired_block_is_replayable_without_freshening_time() -> None:
    envelope = archived()
    assert envelope.cycle.risk is not None
    value = envelope.risk_input.model_copy(
        update={"evaluated_at": NOW + timedelta(seconds=31)}
    )
    result = evaluate_shadow_risk(value)
    assert result.outcome == "BLOCK"
    risk = envelope.cycle.risk.model_copy(
        update={
            "outcome": result.outcome,
            "checks": tuple(
                ShadowCheck(code=item.code, passed=item.passed)
                for item in result.checks
            ),
            "input_digest": risk_input_digest(value),
            "calculated_volume": None,
            "estimated_loss_usd": None,
            "estimated_net_reward_usd": None,
        }
    )
    cycle = envelope.cycle.model_copy(
        update={
            "status": "BLOCK",
            "risk": risk,
            "reason_codes": tuple(
                item.code for item in result.checks if not item.passed
            )[:32],
            "eligibility": evaluate_baseline_eligibility(
                minimum_sample_size=30, risk_passed=False
            ),
        }
    )
    assert verify(make_replay_envelope(cycle, value)) == "MATCH"


def test_datetime_normalization_preserves_original_instant() -> None:
    envelope = archived()
    changed = envelope.risk_input.model_copy(
        update={"evaluated_at": NOW.astimezone(timezone(timedelta(hours=7)))}
    )
    normalized = make_replay_envelope(envelope.cycle, changed)
    assert normalized.risk_input.evaluated_at.utcoffset() == timedelta(0)
    assert normalized.risk_input.evaluated_at == NOW.astimezone(UTC)
    assert canonical_replay_json(normalized) == canonical_replay_json(envelope)


def test_source_receipts_are_retained_claims_not_independently_authenticated() -> None:
    envelope = archived()
    assert envelope.cycle.risk is not None
    receipts = tuple(
        item.model_copy(update={"evidence_digest": "c" * 64})
        for item in envelope.cycle.risk.source_receipts
    )
    risk = envelope.cycle.risk.model_copy(update={"source_receipts": receipts})
    changed = make_replay_envelope(
        envelope.cycle.model_copy(update={"risk": risk}), envelope.risk_input
    )
    assert verify(changed) == "MATCH"
    assert parse_replay_json(canonical_replay_json(changed)).cycle.risk == risk


def test_model_copy_cannot_bypass_wire_safety_or_binding_validation() -> None:
    envelope = archived()
    unsafe = envelope.model_copy(update={"grants_eligibility": 0})
    assert verify(unsafe) == "UNAVAILABLE"
    assert envelope.cycle.candidate is not None
    candidate = envelope.cycle.candidate.model_copy(
        update={"id": UUID("00000000-0000-4000-8000-000000000099")}
    )
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        make_replay_envelope(
            envelope.cycle.model_copy(update={"candidate": candidate}),
            envelope.risk_input,
        )


def test_earlier_cycle_without_risk_inputs_is_not_replayable() -> None:
    host, _ = pipeline(direction="WAIT")
    cycle = host.run_cycle().cycle
    assert isinstance(cycle, ShadowCycle)
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        make_replay_envelope(cycle, archived().risk_input)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", UUID("00000000-0000-4000-8000-000000000099")),
        ("trace_id", UUID("00000000-0000-4000-8000-000000000099")),
        ("cycle_key", "0" * 64),
    ],
)
def test_cycle_identity_cannot_be_rebound(field: str, value: object) -> None:
    envelope = archived()
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        make_replay_envelope(
            envelope.cycle.model_copy(update={field: value}), envelope.risk_input
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("reconciliation_id", UUID("00000000-0000-4000-8000-000000000099")),
        ("point", Decimal("0.1")),
        ("tick_size", Decimal("0.1")),
        ("broker_symbol", "XAUUSD.other"),
        ("account_fingerprint", "mt5-account-v1:" + "0" * 64),
        ("market_adapter_version", "unsupported-v2"),
    ],
)
def test_market_binding_cannot_change_without_exact_risk_input(
    field: str, value: object
) -> None:
    envelope = archived()
    assert envelope.cycle.market is not None
    market = envelope.cycle.market.model_copy(update={field: value})
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        make_replay_envelope(
            envelope.cycle.model_copy(update={"market": market}), envelope.risk_input
        )


def test_raw_login_key_cannot_hide_in_diagnostic_metadata() -> None:
    envelope = archived()
    assert envelope.risk_input.specification is not None
    specification = envelope.risk_input.specification.model_copy(
        update={"raw_diagnostic_codes": {"login": 12345678}}
    )
    value = envelope.risk_input.model_copy(update={"specification": specification})
    with pytest.raises(ReplayError, match="^REPLAY_INVALID$"):
        with_input(envelope, value)


def test_serialization_also_enforces_payload_size() -> None:
    envelope = archived()
    assert envelope.risk_input.specification is not None
    specification = envelope.risk_input.specification.model_copy(
        update={"description": "x" * MAX_REPLAY_BYTES}
    )
    value = envelope.risk_input.model_copy(update={"specification": specification})
    with pytest.raises(ReplayError, match="^REPLAY_TOO_LARGE$"):
        with_input(envelope, value)


def test_cycle_reason_summary_cannot_misrepresent_the_calculation() -> None:
    envelope = archived()
    cycle = envelope.cycle.model_copy(
        update={"reason_codes": ("ALTERED_RESEARCH_CLAIM",)}
    )
    assert verify(make_replay_envelope(cycle, envelope.risk_input)) == "MISMATCH"
