from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from mt5_factories import NOW
from test_shadow_context import capture_and_control, sourced_evidence

from aurum_worker.shadow.models import (
    ShadowBar,
    ShadowCandidateRecord,
    ShadowCheck,
    ShadowCycle,
    ShadowEligibility,
    ShadowMarket,
    ShadowOutcomeEvent,
    ShadowRiskRecord,
    ShadowSourceReceipt,
)
from aurum_worker.shadow.persistence import (
    RpcShadowStore,
    ShadowPersistenceCode,
    ShadowPersistenceError,
)
from aurum_worker.shadow.pipeline import cycle_identity


@dataclass
class Client:
    response: dict[str, object]
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    fail: bool = False

    def call(self, function: str, parameters: dict[str, object]) -> dict[str, object]:
        self.calls.append((function, parameters))
        if self.fail:
            raise RuntimeError("internal transport detail")
        return self.response


def cycle(*, proposal: bool = False) -> ShadowCycle:
    capture, context = capture_and_control()
    key, identifier = cycle_identity(context.trading_account_id, NOW)
    market = ShadowMarket(
        snapshot_id=UUID(int=1, version=4),
        feature_id=UUID(int=2, version=4),
        reconciliation_id=UUID(int=3, version=4),
        input_digest="a" * 64,
        account_fingerprint=capture.account.account_fingerprint,
        server_fingerprint=capture.account.server_fingerprint,
        specification_fingerprint="mt5-spec-v1:" + "a" * 64,
        adapter_version="aurum-mt5-read-v1",
        market_adapter_version="aurum-mt5-read-v1",
        market_time_policy="utc_epoch_v1",
        broker_symbol="XAUUSD",
        captured_at=NOW,
        tick_at=NOW - timedelta(seconds=1),
        last_bar_closed_at=NOW,
        bid=Decimal("2000"),
        ask=Decimal("2000.02"),
        point=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        fast_sma=Decimal("2000"),
        slow_sma=Decimal("1999"),
        atr=Decimal("2"),
        bars=tuple(
            ShadowBar(
                open_at=NOW - timedelta(minutes=6 - i),
                open=Decimal("2000"),
                high=Decimal("2001"),
                low=Decimal("1999"),
                close=Decimal("2000"),
            )
            for i in range(6)
        ),
    )
    return ShadowCycle(
        id=identifier,
        owner_id=context.owner_id,
        trading_account_id=context.trading_account_id,
        trace_id=UUID(int=4, version=4),
        cycle_key=key,
        evaluated_at=NOW,
        status="PROPOSAL" if proposal else "BLOCK",
        reason_codes=("SHADOW_CANDIDATE" if proposal else "POLICY_UNAVAILABLE",),
        policy_version_id=context.policy.id if proposal else None,
        policy_version=1 if proposal else None,
        mode_version=1 if proposal else None,
        market=market if proposal else None,
        candidate=ShadowCandidateRecord(
            id=UUID(int=5, version=4),
            direction="BUY",
            created_at=NOW,
            expires_at=NOW + timedelta(seconds=30),
            entry_price=Decimal("2000.02"),
            stop_loss_price=Decimal("1995.02"),
            take_profit_price=Decimal("2010.02"),
        )
        if proposal
        else None,
        risk=ShadowRiskRecord(
            outcome="PASS",
            checks=(ShadowCheck(code="SOURCE_READY", passed=True),),
            input_digest="b" * 64,
            source_receipts=tuple(
                ShadowSourceReceipt.model_validate(
                    receipt.model_dump(exclude={"provenance"})
                )
                for receipt in sourced_evidence(capture, context).receipts
            ),
            calculated_volume=Decimal("0.01"),
            estimated_loss_usd=Decimal("5"),
            estimated_net_reward_usd=Decimal("10"),
        )
        if proposal
        else None,
        eligibility=ShadowEligibility(
            outcome="BLOCK",
            checks=(ShadowCheck(code="SAMPLE_SIZE", passed=False),),
            sample_count=0,
            minimum_sample_size=30,
        )
        if proposal
        else None,
    )


def event(value: ShadowCycle) -> ShadowOutcomeEvent:
    return ShadowOutcomeEvent(
        id=UUID(int=6, version=4),
        owner_id=value.owner_id,
        trading_account_id=value.trading_account_id,
        cycle_id=value.id,
        sequence=1,
        observed_at=NOW + timedelta(seconds=1),
        status="OBSERVED",
        reason_code="CURRENT_QUOTE",
        bid=Decimal("2000"),
        ask=Decimal("2000.02"),
        price_source="mt5",
    )


def context_response() -> dict[str, object]:
    _capture, context = capture_and_control()
    # SQL row uses snake_case, unlike the existing RiskPolicyVersion wire aliases.
    return {
        "result_code": "CONTEXT_READY",
        "data": {
            "owner_id": str(context.owner_id),
            "trading_account_id": str(context.trading_account_id),
            "observed_at": NOW.isoformat(),
            "mode_version": 1,
            "system_state": "running",
            "policy": context.policy.model_dump(mode="json", by_alias=False),
        },
    }


def test_reads_exact_control_rpc_and_converts_validated_sql_policy_row() -> None:
    response = context_response()
    client = Client(response)
    _capture, expected = capture_and_control()
    actual = RpcShadowStore(client).read_context(expected.trading_account_id)
    assert actual == expected
    assert client.calls == [
        (
            "worker_read_shadow_context",
            {"p_trading_account_id": str(expected.trading_account_id)},
        )
    ]


@pytest.mark.parametrize(
    "code",
    [
        "WORKER_UNAUTHORIZED",
        "ACCOUNT_UNAVAILABLE",
        "SAFETY_STATE_BLOCKED",
        "POLICY_UNAVAILABLE",
    ],
)
def test_unavailable_control_returns_none_without_manufacturing_policy(
    code: str,
) -> None:
    value = cycle()
    assert (
        RpcShadowStore(Client({"result_code": code, "data": None})).read_context(
            value.trading_account_id
        )
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "unknown",
        "account",
        "boolean",
        "count",
        "timestamp",
        "code",
        "policy_owner",
        "policy_extra",
    ],
)
def test_context_rejects_malformed_binding_policy_or_safety_fields(change: str) -> None:
    response = context_response()
    data = response["data"]
    assert isinstance(data, dict) and isinstance(data["policy"], dict)
    if change == "missing":
        del data["mode_version"]
    elif change == "unknown":
        data["extra"] = True
    elif change == "account":
        data["trading_account_id"] = str(UUID(int=99, version=4))
    elif change == "boolean":
        data["policy"]["stop_loss_required"] = 1
    elif change == "count":
        data["mode_version"] = True
    elif change == "timestamp":
        data["observed_at"] = "2026-08-27T12:00:00.0000001Z"
    elif change == "code":
        response["result_code"] = []
    elif change == "policy_owner":
        data["policy"]["owner_id"] = str(UUID(int=99, version=4))
    else:
        data["policy"]["unexpected"] = 1
    with pytest.raises(ShadowPersistenceError) as raised:
        RpcShadowStore(Client(response)).read_context(cycle().trading_account_id)
    assert raised.value.code is ShadowPersistenceCode.RESPONSE_INVALID


def test_cycle_and_outcome_round_trip_use_exact_rpc_parameters() -> None:
    value = cycle(proposal=True)
    observed = event(value)
    client = Client(
        {"result_code": "CYCLE_RECORDED", "cycle_id": str(value.id), "created": True}
    )
    store = RpcShadowStore(client)
    assert store.record_cycle(value) == "CYCLE_RECORDED"
    assert client.calls[-1] == (
        "worker_record_shadow_cycle",
        {"p_cycle": value.model_dump(mode="json")},
    )
    client.response = {
        "result_code": "OUTCOME_RECORDED",
        "event_id": str(observed.id),
        "created": True,
    }
    assert store.append_outcome(observed) == "OUTCOME_RECORDED"
    assert client.calls[-1] == (
        "worker_append_shadow_outcome",
        {"p_event": observed.model_dump(mode="json")},
    )
    client.response = {
        "result_code": "CYCLES_READ",
        "data": {
            "cycles": [value.model_dump(mode="json")],
            "outcomes": [observed.model_dump(mode="json")],
        },
    }
    assert store.read_cycles(value.trading_account_id, value.cycle_key) == (
        (value,),
        (observed,),
    )
    assert client.calls[-1] == (
        "worker_read_shadow_cycles",
        {
            "p_trading_account_id": str(value.trading_account_id),
            "p_cycle_key": value.cycle_key,
        },
    )


def test_idempotent_replay_is_accepted_only_for_exact_acknowledged_identity() -> None:
    value = cycle()
    client = Client(
        {
            "result_code": "IDEMPOTENT_REPLAY",
            "cycle_id": str(value.id),
            "created": False,
        }
    )
    assert RpcShadowStore(client).record_cycle(value) == "IDEMPOTENT_REPLAY"
    client.response["cycle_id"] = str(UUID(int=99, version=4))
    with pytest.raises(ShadowPersistenceError):
        RpcShadowStore(client).record_cycle(value)


@pytest.mark.parametrize(
    "response",
    [
        {"result_code": "CONFLICT"},
        {"result_code": "FORBIDDEN"},
        {"result_code": "CYCLE_RECORDED", "created": True},
        {
            "result_code": "CYCLE_RECORDED",
            "cycle_id": str(UUID(int=99, version=4)),
            "created": 1,
        },
    ],
)
def test_write_denials_or_malformed_success_never_confirm_durability(
    response: dict[str, object],
) -> None:
    with pytest.raises(ShadowPersistenceError):
        RpcShadowStore(Client(response)).record_cycle(cycle())


@pytest.mark.parametrize(
    "change",
    [
        "wrong_account",
        "wrong_key",
        "duplicates",
        "unknown_field",
        "missing_default",
        "outcome_parent",
        "sequence_gap",
        "equal_initial_time",
        "reversed_time",
        "terminal_reversed",
    ],
)
def test_loaded_cycles_and_outcomes_fail_closed_on_identity_or_sequence_defects(
    change: str,
) -> None:
    value = cycle(proposal=True)
    observed = event(value)
    cycles = [value.model_dump(mode="json")]
    outcomes = [observed.model_dump(mode="json")]
    if change == "wrong_account":
        cycles[0]["trading_account_id"] = str(UUID(int=99, version=4))
    elif change == "wrong_key":
        cycles[0]["cycle_key"] = "b" * 64
    elif change == "duplicates":
        cycles.append(cycles[0])
    elif change == "unknown_field":
        cycles[0]["unexpected"] = True
    elif change == "missing_default":
        del cycles[0]["source"]
    elif change == "outcome_parent":
        outcomes[0]["cycle_id"] = str(UUID(int=99, version=4))
    elif change == "sequence_gap":
        outcomes[0]["sequence"] = 2
    elif change == "equal_initial_time":
        outcomes[0]["observed_at"] = value.evaluated_at.isoformat()
    else:
        second = observed.model_copy(
            update={"id": UUID(int=7, version=4), "sequence": 2}
        )
        if change == "terminal_reversed":
            outcomes[0]["status"] = "EXPIRED"
            second = second.model_copy(
                update={"observed_at": NOW + timedelta(seconds=2)}
            )
        outcomes.append(second.model_dump(mode="json"))
    response: dict[str, object] = {
        "result_code": "CYCLES_READ",
        "data": {"cycles": cycles, "outcomes": outcomes},
    }
    with pytest.raises(ShadowPersistenceError):
        RpcShadowStore(Client(response)).read_cycles(
            value.trading_account_id, value.cycle_key
        )


def test_store_failures_are_sanitized() -> None:
    client = Client({}, fail=True)
    with pytest.raises(ShadowPersistenceError) as raised:
        RpcShadowStore(client).read_cycles(cycle().trading_account_id)
    assert str(raised.value) == "SHADOW_TRANSPORT_UNAVAILABLE"
    assert raised.value.__cause__ is None


def test_unbounded_reads_are_rejected() -> None:
    value = cycle()
    response: dict[str, object] = {
        "result_code": "CYCLES_READ",
        "data": {
            "cycles": [value.model_dump(mode="json")] * 101,
            "outcomes": [],
        },
    }
    with pytest.raises(ShadowPersistenceError):
        RpcShadowStore(Client(response)).read_cycles(value.trading_account_id)
