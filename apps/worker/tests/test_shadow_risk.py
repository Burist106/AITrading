"""Deterministic/adversarial tests using explicit fake observations only."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, Inexact, localcontext
from itertools import count
from uuid import UUID

import pytest
from mt5_factories import (
    NOW,
    account,
    confirmed_binding,
    fake_adapter,
    specification,
    tick,
)
from pydantic import ValidationError

from aurum_worker.adapters.native_mt5 import ADAPTER_VERSION, MetaTrader5ReadAdapter
from aurum_worker.adapters.persistence_mt5 import InMemoryMt5ObservationPersistence
from aurum_worker.models.mt5 import (
    AccountTradeMode,
    DatabaseReconciliationState,
    HistoryQueryEvidence,
    HistoryQueryResultState,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    ReconciliationOutcome,
    ReconciliationReport,
    SymbolTradeMode,
    TickFreshness,
)
from aurum_worker.models.risk_policy import RiskPolicyActorType, RiskPolicyVersion
from aurum_worker.models.trading import TradeDirection
from aurum_worker.mt5_market_time import (
    PEPPERSTONE_POLICY,
    UTC_POLICY,
    MarketTimePolicy,
)
from aurum_worker.reconciliation import ReadOnlyReconciliationService
from aurum_worker.shadow.risk import (
    ShadowAccountRiskState,
    ShadowCandidate,
    ShadowCostContext,
    ShadowRiskEvidence,
    ShadowRiskInput,
    ShadowRiskProvenance,
    ShadowSafetyContext,
    evaluate_shadow_risk,
)


def _input() -> ShadowRiskInput:
    binding = confirmed_binding()
    # Native-shaped test data only: no terminal, credentials or real-source gate.
    observed_account = account().model_copy(update={"source": "mt5"})
    provenance = ShadowRiskProvenance(
        source="mt5",
        adapter_version="fake-v1",
        market_adapter_version="fake-v1",
        owner_id=UUID(binding.owner_id),
        trading_account_id=UUID(binding.trading_account_id),
        account_fingerprint=observed_account.account_fingerprint,
        server_fingerprint=observed_account.server_fingerprint,
        broker_symbol=binding.broker_symbol,
        specification_fingerprint=binding.confirmed_specification_fingerprint,
        risk_policy_version_id=UUID("00000000-0000-4000-8000-000000000401"),
        risk_policy_version=1,
    )
    policy = RiskPolicyVersion.model_validate(
        {
            "id": provenance.risk_policy_version_id,
            "ownerId": provenance.owner_id,
            "riskPolicyId": UUID("00000000-0000-4000-8000-000000000402"),
            "tradingAccountId": provenance.trading_account_id,
            "version": 1,
            "versionLabel": "risk-v1",
            "sourceCommandId": None,
            "environment": "DEMO_ONLY",
            "canonicalSymbol": "XAUUSD",
            "maximumPermittedVolume": 0.01,
            "maximumOpenPositions": 1,
            "stopLossRequired": True,
            "martingaleAllowed": False,
            "gridTradingAllowed": False,
            "averagingDownAllowed": False,
            "lossBasedVolumeIncreaseAllowed": False,
            "riskPerTradePct": 0.25,
            "dailyLossLimitPct": 1.0,
            "weeklyLossLimitPct": 3.0,
            "maximumDrawdownPct": 5.0,
            "maximumTradesPerDay": 3,
            "minimumRiskReward": 1.5,
            "staleDataMaxAgeSeconds": 10,
            "maximumSpreadPoints": 3.5,
            "spreadWarningPoints": 2.0,
            "newsBlackoutMinutes": 15,
            "proposalExpirySeconds": 30,
            "entryTolerancePoints": 0.6,
            "minimumSampleSize": 30,
            "requireCalibratedModel": False,
            "maximumSlippagePoints": 0.5,
            "automaticRetryOnBrokerReject": False,
            "reason": "Explicit test policy",
            "createdByType": RiskPolicyActorType.SYSTEM,
            "createdBy": "test",
            "createdAt": NOW,
        }
    )
    observed_tick = tick().model_copy(
        update={
            "source": "mt5",
            "bid": Decimal("2000"),
            "ask": Decimal("2000.02"),
            "spread_price": Decimal("0.02"),
            "spread_points": Decimal("2"),
        }
    )
    histories = tuple(
        HistoryQueryEvidence(
            history_kind=kind,
            requested_start_at=NOW - timedelta(days=1),
            requested_end_at=NOW - timedelta(seconds=2),
            query_completed_at=NOW,
            returned_count=0,
            earliest_returned_at=None,
            latest_returned_at=None,
            result_state=HistoryQueryResultState.EMPTY_VALID_RESULT,
            reason_code=Mt5ReasonCode.HISTORY_EMPTY_VALID_RESULT,
        )
        for kind in ("orders", "deals")
    )
    reconciliation = ReconciliationReport(
        observed_at=NOW,
        source="mt5",
        adapter_version="aurum-reconciliation-v1",
        trace_id="reconciliation-test",
        reconciliation_id="reconciliation-test",
        started_at=NOW - timedelta(seconds=2),
        completed_at=NOW,
        outcome=ReconciliationOutcome.MATCHED,
        reason_code=Mt5ReasonCode.HEALTHY,
        account_fingerprint=provenance.account_fingerprint,
        server_fingerprint=provenance.server_fingerprint,
        broker_symbol=provenance.broker_symbol,
        symbol_specification_fingerprint=provenance.specification_fingerprint,
        open_position_count=0,
        active_order_count=0,
        order_history_count=0,
        deal_history_count=0,
        order_history_evidence=histories[0],
        deal_history_evidence=histories[1],
    )
    day_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    return ShadowRiskInput(
        evaluated_at=NOW,
        provenance=provenance,
        candidate=ShadowCandidate(
            candidate_id=UUID("00000000-0000-4000-8000-000000000501"),
            provenance=provenance,
            market_trace_id=observed_tick.trace_id,
            created_at=NOW,
            expires_at=NOW + timedelta(seconds=30),
            direction=TradeDirection.BUY,
            entry_price=Decimal("2000.02"),
            stop_loss_price=Decimal("1995.02"),
            take_profit_price=Decimal("2010.02"),
        ),
        account=observed_account,
        account_risk=ShadowAccountRiskState(
            provenance=provenance,
            trace_id="account-risk-test",
            observed_at=NOW,
            currency="USD",
            equity=Decimal("2200"),
            day_start_equity=Decimal("2200"),
            week_start_equity=Decimal("2200"),
            peak_equity=Decimal("2200"),
            daily_loss_amount=Decimal("0"),
            weekly_loss_amount=Decimal("0"),
            day_started_at=day_start,
            week_started_at=day_start - timedelta(days=day_start.weekday()),
            losses_include_unrealized_and_costs=True,
            ledger_complete=True,
            trades_today=0,
            open_position_count=0,
            active_order_count=0,
        ),
        safety=ShadowSafetyContext(
            provenance=provenance,
            trace_id="safety-test",
            observed_at=NOW,
            terminal_connected=True,
            worker_healthy=True,
            database_healthy=True,
            clock_synchronized=True,
            policy_active=True,
            active_policy_version_id=provenance.risk_policy_version_id,
            reconciliation_required=False,
            emergency_stop_requested=False,
            emergency_stop_active=False,
            resume_required=False,
            news_blackout_clear=True,
            news_checked_from=NOW - timedelta(minutes=15),
            news_checked_until=NOW + timedelta(minutes=15),
        ),
        costs=ShadowCostContext(
            provenance=provenance,
            trace_id="cost-test",
            observed_at=NOW,
            currency="USD",
            commission_round_trip_per_lot=Decimal("0"),
            swap_allowance_per_lot=Decimal("0"),
            slippage_points_per_side=Decimal("0"),
        ),
        tick=observed_tick,
        specification=specification().model_copy(update={"source": "mt5"}),
        confirmed_binding=binding,
        reconciliation=reconciliation,
        policy=policy,
        reconciliation_adapter_version="aurum-reconciliation-v1",
        maximum_tick_age_seconds=10,
        maximum_reconciliation_age_seconds=600,
        maximum_specification_age_seconds=600,
    )


def _blocked(value: ShadowRiskInput, code: str) -> ShadowRiskEvidence:
    result = evaluate_shadow_risk(value)
    assert result.outcome == "BLOCK"
    assert result.grants_eligibility is False
    assert result.calculated_volume is None
    assert result.estimated_loss_usd is None
    assert result.estimated_net_reward_usd is None
    assert any(check.code == code and not check.passed for check in result.checks)
    return result


def _equity(value: ShadowRiskInput, equity: str) -> ShadowRiskInput:
    assert value.account_risk is not None
    return value.model_copy(
        update={
            "account_risk": value.account_risk.model_copy(
                update={
                    "equity": Decimal(equity),
                    "day_start_equity": Decimal(equity),
                    "week_start_equity": Decimal(equity),
                    "peak_equity": Decimal(equity),
                }
            )
        }
    )


def test_buy_evidence_is_decimal_immutable_deterministic_and_never_eligible() -> None:
    value = _input()
    result = evaluate_shadow_risk(value)
    assert result == evaluate_shadow_risk(value)
    assert result.outcome == "PASS"
    assert result.grants_eligibility is False
    assert result.calculated_volume == Decimal("0.01")
    assert result.estimated_loss_usd == Decimal("5")
    assert result.estimated_net_reward_usd == Decimal("10")
    assert result.calculation is not None
    assert result.calculation.risk_budget_usd == Decimal("5.5")
    assert result.calculation.net_risk_reward == Decimal("2")
    assert result.calculation.spread_points == Decimal("2")
    assert all(check.hard for check in result.checks)
    with pytest.raises(ValidationError):
        result.outcome = "BLOCK"
    assert '"grants_eligibility":false' in result.model_dump_json()


@pytest.mark.parametrize(
    "field",
    [
        "account",
        "account_risk",
        "safety",
        "costs",
        "tick",
        "specification",
        "confirmed_binding",
        "reconciliation",
        "policy",
    ],
)
def test_missing_input_blocks_without_default_ready_evidence(field: str) -> None:
    value = _input().model_copy(update={field: None})
    _blocked(value, field.upper() + "_AVAILABLE")


@pytest.mark.parametrize(
    "mode", [AccountTradeMode.REAL, AccountTradeMode.UNKNOWN, AccountTradeMode.CONTEST]
)
def test_non_demo_accounts_block(mode: AccountTradeMode) -> None:
    value = _input()
    assert value.account is not None
    _blocked(
        value.model_copy(
            update={"account": value.account.model_copy(update={"trade_mode": mode})}
        ),
        "DEMO_ACCOUNT_BINDING",
    )


@pytest.mark.parametrize(
    "field", ["account_risk", "safety", "costs", "account", "tick"]
)
@pytest.mark.parametrize("offset", [-11, 1])
def test_stale_or_future_context_blocks(field: str, offset: int) -> None:
    value = _input()
    context = getattr(value, field)
    _blocked(
        value.model_copy(
            update={
                field: context.model_copy(
                    update={"observed_at": NOW + timedelta(seconds=offset)}
                )
            }
        ),
        field.upper() + "_FRESH",
    )


@pytest.mark.parametrize("field", ["specification", "reconciliation"])
def test_specification_and_reconciliation_have_bounded_freshness(field: str) -> None:
    value = _input()
    context = getattr(value, field)
    _blocked(
        value.model_copy(
            update={
                field: context.model_copy(
                    update={"observed_at": NOW - timedelta(seconds=601)}
                )
            }
        ),
        field.upper() + "_FRESH",
    )


@pytest.mark.parametrize(
    "field", ["account", "tick", "specification", "reconciliation"]
)
def test_mixed_observation_sources_block(field: str) -> None:
    value = _input()
    context = getattr(value, field)
    _blocked(
        value.model_copy(
            update={field: context.model_copy(update={"source": "fake_mt5"})}
        ),
        field.upper() + "_SOURCE",
    )


def test_coherent_fake_source_is_rejected_by_production_evaluator() -> None:
    value = _input()
    provenance = value.provenance.model_copy(update={"source": "fake_mt5"})
    updates: dict[str, object] = {"provenance": provenance}
    for field in ("account", "tick", "specification", "reconciliation"):
        updates[field] = getattr(value, field).model_copy(update={"source": "fake_mt5"})
    for field in ("candidate", "account_risk", "safety", "costs"):
        updates[field] = getattr(value, field).model_copy(
            update={"provenance": provenance}
        )
    _blocked(value.model_copy(update=updates), "PRODUCTION_SOURCE")


@pytest.mark.parametrize("field", ["account_risk", "safety", "costs"])
def test_context_identity_mismatch_blocks(field: str) -> None:
    value = _input()
    context = getattr(value, field)
    other = value.provenance.model_copy(update={"server_fingerprint": "different"})
    _blocked(
        value.model_copy(
            update={field: context.model_copy(update={"provenance": other})}
        ),
        field.upper() + "_PROVENANCE",
    )


@pytest.mark.parametrize(
    "field",
    ["terminal_connected", "worker_healthy", "database_healthy", "clock_synchronized"],
)
@pytest.mark.parametrize("state", [None, False])
def test_unknown_or_unhealthy_operational_state_blocks(
    field: str, state: bool | None
) -> None:
    value = _input()
    assert value.safety is not None
    _blocked(
        value.model_copy(
            update={"safety": value.safety.model_copy(update={field: state})}
        ),
        "OPERATIONAL_SAFETY",
    )


@pytest.mark.parametrize(
    "field", ["emergency_stop_requested", "emergency_stop_active", "resume_required"]
)
@pytest.mark.parametrize("state", [None, True])
def test_emergency_unknown_or_active_blocks(field: str, state: bool | None) -> None:
    value = _input()
    assert value.safety is not None
    _blocked(
        value.model_copy(
            update={"safety": value.safety.model_copy(update={field: state})}
        ),
        "EMERGENCY_CLEAR",
    )


@pytest.mark.parametrize(
    "update",
    [
        {"news_blackout_clear": None},
        {"news_blackout_clear": False},
        {"news_checked_from": None},
        {"news_checked_until": None},
        {"news_checked_from": NOW - timedelta(minutes=14)},
        {"news_checked_until": NOW + timedelta(minutes=14)},
    ],
)
def test_news_requires_complete_clear_blackout_window(
    update: dict[str, object],
) -> None:
    value = _input()
    assert value.safety is not None
    _blocked(
        value.model_copy(update={"safety": value.safety.model_copy(update=update)}),
        "NEWS_CLEAR",
    )


@pytest.mark.parametrize(
    "update",
    [
        {"open_position_count": 1},
        {"active_order_count": 1},
        {"open_position_count": None},
        {"active_order_count": None},
    ],
)
def test_any_or_unknown_current_exposure_blocks(update: dict[str, object]) -> None:
    value = _input()
    assert value.account_risk is not None
    _blocked(
        value.model_copy(
            update={"account_risk": value.account_risk.model_copy(update=update)}
        ),
        "NO_OPEN_EXPOSURE",
    )


@pytest.mark.parametrize("count", [None, 3, 4])
def test_daily_count_limit_or_unknown_blocks(count: int | None) -> None:
    value = _input()
    assert value.account_risk is not None
    _blocked(
        value.model_copy(
            update={
                "account_risk": value.account_risk.model_copy(
                    update={"trades_today": count}
                )
            }
        ),
        "DAILY_TRADE_LIMIT",
    )


def test_exact_budget_threshold_passes_but_below_it_blocks() -> None:
    assert evaluate_shadow_risk(_equity(_input(), "2000")).outcome == "PASS"
    _blocked(_equity(_input(), "1999.999999999999"), "BROKER_MINIMUM_VOLUME")


def test_broker_step_floors_reduced_volume_and_never_rounds_up() -> None:
    value = _equity(_input(), "1000")
    assert value.specification is not None
    value = value.model_copy(
        update={
            "specification": value.specification.model_copy(
                update={
                    "minimum_volume": Decimal("0.001"),
                    "volume_step": Decimal("0.003"),
                }
            )
        }
    )
    result = evaluate_shadow_risk(value)
    assert result.outcome == "PASS"
    assert result.calculated_volume == Decimal("0.003")
    assert result.estimated_loss_usd == Decimal("1.5")
    assert result.calculation is not None
    assert result.calculation.risk_budget_usd == Decimal("2.5")


def test_volume_is_capped_at_point_zero_one_even_with_large_budget() -> None:
    result = evaluate_shadow_risk(_equity(_input(), "1000000"))
    assert result.calculated_volume == Decimal("0.01")


@pytest.mark.parametrize(
    "policy_field",
    [
        "risk_per_trade_pct",
        "daily_loss_limit_pct",
        "weekly_loss_limit_pct",
        "maximum_drawdown_pct",
    ],
)
def test_zero_policy_budget_blocks_with_no_volume(policy_field: str) -> None:
    value = _input()
    assert value.policy is not None
    _blocked(
        value.model_copy(
            update={"policy": value.policy.model_copy(update={policy_field: 0.0})}
        ),
        "RISK_BUDGET",
    )


@pytest.mark.parametrize(
    ("field", "amount"),
    [
        ("daily_loss_amount", "20"),
        ("weekly_loss_amount", "64"),
    ],
)
def test_remaining_loss_budget_limits_new_volume(field: str, amount: str) -> None:
    value = _input()
    assert value.account_risk is not None
    result = _blocked(
        value.model_copy(
            update={
                "account_risk": value.account_risk.model_copy(
                    update={field: Decimal(amount)}
                )
            }
        ),
        "BROKER_MINIMUM_VOLUME",
    )
    assert result.calculation is not None
    assert result.calculation.risk_budget_usd == Decimal("2")


def test_drawdown_and_unreported_equity_loss_reduce_available_budget() -> None:
    value = _input()
    assert value.account_risk is not None
    # 2315 peak permits 115.75 drawdown, of which 115 has already occurred.
    result = _blocked(
        value.model_copy(
            update={
                "account_risk": value.account_risk.model_copy(
                    update={"peak_equity": Decimal("2315")}
                )
            }
        ),
        "BROKER_MINIMUM_VOLUME",
    )
    assert result.calculation is not None
    assert result.calculation.remaining_drawdown_budget_usd == Decimal("0.75")
    # A zero supplied loss cannot conceal an equity decline from the daily baseline.
    result = _blocked(
        value.model_copy(
            update={
                "account_risk": value.account_risk.model_copy(
                    update={"day_start_equity": Decimal("2220")}
                )
            }
        ),
        "BROKER_MINIMUM_VOLUME",
    )
    assert result.calculation is not None
    assert result.calculation.remaining_daily_budget_usd == Decimal("2.20")


def test_sell_uses_bid_and_directional_loss_and_target() -> None:
    value = _input()
    value = value.model_copy(
        update={
            "candidate": value.candidate.model_copy(
                update={
                    "direction": TradeDirection.SELL,
                    "entry_price": Decimal("2000"),
                    "stop_loss_price": Decimal("2005"),
                    "take_profit_price": Decimal("1990"),
                }
            )
        }
    )
    result = evaluate_shadow_risk(value)
    assert result.outcome == "PASS"
    assert result.estimated_loss_usd == Decimal("5")
    assert result.estimated_net_reward_usd == Decimal("10")
    assert result.calculation is not None
    assert result.calculation.effective_entry_price == Decimal("2000")


def test_commission_swap_and_two_slippage_sides_reduce_net_rr() -> None:
    value = _input()
    assert value.costs is not None
    value = value.model_copy(
        update={
            "costs": value.costs.model_copy(
                update={
                    "commission_round_trip_per_lot": Decimal("4"),
                    "swap_allowance_per_lot": Decimal("1"),
                    "slippage_points_per_side": Decimal("0.5"),
                }
            )
        }
    )
    result = evaluate_shadow_risk(value)
    assert result.outcome == "PASS"
    assert result.calculation is not None
    assert result.calculation.commission_and_swap_per_lot_usd == Decimal("5")
    assert result.calculation.two_sided_slippage_per_lot_usd == Decimal("1")
    assert result.estimated_loss_usd == Decimal("5.06")
    assert result.estimated_net_reward_usd == Decimal("9.94")


def test_costs_can_turn_gross_rr_pass_into_net_rr_block() -> None:
    value = _input()
    assert value.costs is not None
    value = value.model_copy(
        update={
            "candidate": value.candidate.model_copy(
                update={"take_profit_price": Decimal("2007.52")}
            ),
            "costs": value.costs.model_copy(
                update={"commission_round_trip_per_lot": Decimal("0.01")}
            ),
        }
    )
    _blocked(value, "NET_RISK_REWARD")


def test_exact_net_rr_threshold_passes() -> None:
    value = _input()
    value = value.model_copy(
        update={
            "candidate": value.candidate.model_copy(
                update={"take_profit_price": Decimal("2007.52")}
            )
        }
    )
    assert evaluate_shadow_risk(value).outcome == "PASS"


@pytest.mark.parametrize(
    "field",
    [
        "commission_round_trip_per_lot",
        "swap_allowance_per_lot",
        "slippage_points_per_side",
    ],
)
def test_unknown_cost_blocks(field: str) -> None:
    value = _input()
    assert value.costs is not None
    _blocked(
        value.model_copy(
            update={"costs": value.costs.model_copy(update={field: None})}
        ),
        "COSTS_COMPLETE",
    )


@pytest.mark.parametrize(
    "invalid", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), 1.5, True, 1]
)
def test_decimal_inputs_reject_nonfinite_negative_floats_and_bool(
    invalid: object,
) -> None:
    value = _input()
    assert value.costs is not None
    with pytest.raises(ValidationError):
        evaluate_shadow_risk(
            value.model_copy(
                update={
                    "costs": value.costs.model_copy(
                        update={"commission_round_trip_per_lot": invalid}
                    )
                }
            )
        )


def test_decimal_strings_are_parsed_exactly() -> None:
    value = _input()
    payload = value.candidate.model_dump(mode="python")
    payload["entry_price"] = "2000.020000000001"
    candidate = ShadowCandidate.model_validate(payload)
    assert candidate.entry_price == Decimal("2000.020000000001")


@pytest.mark.parametrize("invalid", [0, 1, "false", "true"])
def test_safety_bools_never_coerce(invalid: object) -> None:
    value = _input()
    assert value.safety is not None
    with pytest.raises(ValidationError):
        evaluate_shadow_risk(
            value.model_copy(
                update={
                    "safety": value.safety.model_copy(
                        update={"emergency_stop_requested": invalid}
                    )
                }
            )
        )


@pytest.mark.parametrize("invalid", [True, False, "0", 0.0])
def test_counts_never_coerce(invalid: object) -> None:
    value = _input()
    assert value.account_risk is not None
    with pytest.raises(ValidationError):
        evaluate_shadow_risk(
            value.model_copy(
                update={
                    "account_risk": value.account_risk.model_copy(
                        update={"trades_today": invalid}
                    )
                }
            )
        )


def test_revalidates_policy_literal_flags_and_counts_after_unchecked_model_copy() -> (
    None
):
    value = _input()
    assert value.policy is not None
    for field, invalid in (("stop_loss_required", 1), ("maximum_open_positions", True)):
        with pytest.raises(ValidationError):
            evaluate_shadow_risk(
                value.model_copy(
                    update={"policy": value.policy.model_copy(update={field: invalid})}
                )
            )


@pytest.mark.parametrize(
    "field",
    [
        "equity",
        "day_start_equity",
        "week_start_equity",
        "peak_equity",
        "daily_loss_amount",
        "weekly_loss_amount",
        "ledger_complete",
        "losses_include_unrealized_and_costs",
    ],
)
def test_unknown_account_ledger_blocks(field: str) -> None:
    value = _input()
    assert value.account_risk is not None
    _blocked(
        value.model_copy(
            update={"account_risk": value.account_risk.model_copy(update={field: None})}
        ),
        "LOSS_LEDGER_COMPLETE",
    )


def test_non_usd_blocks_even_if_all_currency_labels_match() -> None:
    value = _input()
    assert value.account is not None and value.account_risk is not None
    assert value.costs is not None
    _blocked(
        value.model_copy(
            update={
                "account": value.account.model_copy(update={"currency": "EUR"}),
                "account_risk": value.account_risk.model_copy(
                    update={"currency": "EUR"}
                ),
                "costs": value.costs.model_copy(update={"currency": "EUR"}),
            }
        ),
        "USD_VALUATION",
    )


@pytest.mark.parametrize(
    ("update", "code"),
    [
        ({"stop_loss_price": Decimal("2001")}, "DIRECTIONAL_SL_TP"),
        ({"take_profit_price": Decimal("1999")}, "DIRECTIONAL_SL_TP"),
        ({"entry_price": Decimal("2000")}, "ENTRY_TOLERANCE"),
        ({"stop_loss_price": Decimal("1995.021")}, "TICK_GRID"),
        ({"stop_loss_price": Decimal("1999.95")}, "BROKER_STOPS"),
        ({"market_trace_id": "another-quote"}, "CANDIDATE_CURRENT"),
        ({"expires_at": NOW}, "CANDIDATE_CURRENT"),
        ({"expires_at": NOW + timedelta(seconds=31)}, "CANDIDATE_CURRENT"),
    ],
)
def test_candidate_prices_trace_and_expiry_fail_closed(
    update: dict[str, object], code: str
) -> None:
    value = _input()
    _blocked(
        value.model_copy(
            update={"candidate": value.candidate.model_copy(update=update)}
        ),
        code,
    )


def test_missing_mandatory_sl_is_validation_error() -> None:
    payload = _input().candidate.model_dump(mode="python")
    del payload["stop_loss_price"]
    with pytest.raises(ValidationError):
        ShadowCandidate.model_validate(payload)


@pytest.mark.parametrize(
    "freshness",
    [
        TickFreshness.STALE,
        TickFreshness.DELAYED,
        TickFreshness.UNAVAILABLE,
        TickFreshness.FUTURE_INVALID,
    ],
)
def test_non_live_tick_blocks(freshness: TickFreshness) -> None:
    value = _input()
    assert value.tick is not None
    _blocked(
        value.model_copy(
            update={"tick": value.tick.model_copy(update={"freshness": freshness})}
        ),
        "TICK_CURRENT",
    )


def test_spread_points_cannot_override_actual_quote_spread() -> None:
    value = _input()
    assert value.tick is not None
    _blocked(
        value.model_copy(
            update={
                "tick": value.tick.model_copy(update={"spread_points": Decimal("0")})
            }
        ),
        "SPREAD_LIMIT",
    )


@pytest.mark.parametrize(
    "mode",
    [
        SymbolTradeMode.SHORT_ONLY,
        SymbolTradeMode.DISABLED,
        SymbolTradeMode.UNKNOWN,
        SymbolTradeMode.CLOSE_ONLY,
    ],
)
def test_unusable_directional_symbol_blocks(mode: SymbolTradeMode) -> None:
    value = _input()
    assert value.specification is not None
    _blocked(
        value.model_copy(
            update={
                "specification": value.specification.model_copy(
                    update={"trade_mode": mode}
                )
            }
        ),
        "SYMBOL_USABLE",
    )


def test_output_does_not_depend_on_global_decimal_precision_or_traps() -> None:
    value = _input()
    expected = evaluate_shadow_risk(value)
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = True
        assert evaluate_shadow_risk(value) == expected


def test_policy_activation_binding_and_confirmation_are_not_inferred() -> None:
    value = _input()
    assert value.safety is not None and value.confirmed_binding is not None
    _blocked(
        value.model_copy(
            update={"safety": value.safety.model_copy(update={"policy_active": None})}
        ),
        "POLICY_BINDING",
    )
    _blocked(
        value.model_copy(
            update={
                "confirmed_binding": value.confirmed_binding.model_copy(
                    update={
                        "confirmed_specification_fingerprint": "mt5-spec-v1:changed"
                    }
                )
            }
        ),
        "SYMBOL_BINDING",
    )


def test_actual_reconciler_contract_with_advancing_clock_and_distinct_version() -> None:
    value = _input()
    ticks = count()

    def clock() -> datetime:
        return NOW - timedelta(seconds=1) + timedelta(microseconds=next(ticks))

    report = (
        ReadOnlyReconciliationService(
            fake_adapter(),
            InMemoryMt5ObservationPersistence(
                database_state=DatabaseReconciliationState(
                    account_fingerprint=value.provenance.account_fingerprint,
                    server_fingerprint=value.provenance.server_fingerprint,
                    confirmed_symbol_binding=confirmed_binding(),
                )
            ),
            Mt5WorkerConfig(
                broker_symbol="XAUUSD",
                expected_account_fingerprint=value.provenance.account_fingerprint,
            ),
            clock=clock,
        )
        .run(trace_id="actual-reconciler-contract-test")
        .report
    )
    assert report.outcome is ReconciliationOutcome.MATCHED
    assert report.started_at < report.observed_at < report.completed_at < NOW
    assert report.adapter_version != value.provenance.adapter_version
    assert (
        evaluate_shadow_risk(
            value.model_copy(update={"reconciliation": report})
        ).outcome
        == "PASS"
    )


def test_reconciliation_version_and_query_windows_are_not_inferred() -> None:
    value = _input()
    assert value.reconciliation is not None
    report = value.reconciliation
    changed_history = report.deal_history_evidence.model_copy(
        update={"requested_end_at": NOW - timedelta(seconds=1)}
    )
    _blocked(
        value.model_copy(
            update={
                "reconciliation": report.model_copy(
                    update={"adapter_version": "unknown-version"}
                )
            }
        ),
        "RECONCILIATION_SOURCE",
    )
    _blocked(
        value.model_copy(
            update={
                "reconciliation": report.model_copy(
                    update={
                        "deal_history_evidence": changed_history,
                    }
                )
            }
        ),
        "RECONCILIATION_MATCHED",
    )


@pytest.mark.parametrize(
    ("spread", "expected"), [("0.035", "PASS"), ("0.036", "BLOCK")]
)
def test_spread_threshold_uses_broker_point_units(spread: str, expected: str) -> None:
    value = _input()
    assert value.specification is not None and value.tick is not None
    entry = Decimal("2000") + Decimal(spread)
    value = value.model_copy(
        update={
            "specification": value.specification.model_copy(
                update={
                    "tick_size": Decimal("0.001"),
                    "tick_value_loss": Decimal("0.1"),
                    "tick_value_profit": Decimal("0.1"),
                }
            ),
            "tick": value.tick.model_copy(
                update={
                    "ask": entry,
                    "spread_price": Decimal(spread),
                    "spread_points": Decimal(spread) / Decimal("0.01"),
                }
            ),
            "candidate": value.candidate.model_copy(
                update={
                    "entry_price": entry,
                    "stop_loss_price": entry - Decimal("5"),
                    "take_profit_price": entry + Decimal("10"),
                }
            ),
        }
    )
    assert evaluate_shadow_risk(value).outcome == expected
    if expected == "BLOCK":
        _blocked(value, "SPREAD_LIMIT")


@pytest.mark.parametrize(
    ("entry", "expected"), [("2000.026", "PASS"), ("2000.027", "BLOCK")]
)
def test_entry_tolerance_threshold_is_exact(entry: str, expected: str) -> None:
    value = _input()
    assert value.specification is not None
    value = value.model_copy(
        update={
            "specification": value.specification.model_copy(
                update={
                    "tick_size": Decimal("0.001"),
                    "tick_value_loss": Decimal("0.1"),
                    "tick_value_profit": Decimal("0.1"),
                }
            ),
            "candidate": value.candidate.model_copy(
                update={"entry_price": Decimal(entry)}
            ),
        }
    )
    assert evaluate_shadow_risk(value).outcome == expected
    if expected == "BLOCK":
        _blocked(value, "ENTRY_TOLERANCE")


def test_stricter_policy_age_applies_at_exact_tick_event_boundary() -> None:
    value = _input()
    assert value.policy is not None
    value = value.model_copy(
        update={
            "policy": value.policy.model_copy(update={"stale_data_max_age_seconds": 1})
        }
    )
    assert evaluate_shadow_risk(value).outcome == "PASS"
    _blocked(
        value.model_copy(update={"evaluated_at": NOW + timedelta(microseconds=1)}),
        "TICK_CURRENT",
    )


def test_broker_minimum_above_hard_volume_cap_blocks() -> None:
    value = _equity(_input(), "1000000")
    assert value.specification is not None
    _blocked(
        value.model_copy(
            update={
                "specification": value.specification.model_copy(
                    update={"minimum_volume": Decimal("0.02")}
                )
            }
        ),
        "BROKER_MINIMUM_VOLUME",
    )


def test_missing_or_unknown_directional_tick_values_block() -> None:
    value = _input()
    assert value.specification is not None
    for field in ("tick_value_loss", "tick_value_profit"):
        _blocked(
            value.model_copy(
                update={
                    "specification": value.specification.model_copy(
                        update={field: Decimal("0")}
                    )
                }
            ),
            "SYMBOL_USABLE",
        )


def test_output_schema_cannot_encode_block_with_volume_or_pass_with_failure() -> None:
    result = evaluate_shadow_risk(_input())
    payload = result.model_dump(mode="python")
    payload["outcome"] = "BLOCK"
    with pytest.raises(ValidationError):
        ShadowRiskEvidence.model_validate(payload)
    payload["checks"] = (result.checks[0].model_copy(update={"passed": False}),)
    with pytest.raises(ValidationError):
        ShadowRiskEvidence.model_validate(payload)


@pytest.mark.parametrize("elapsed_microseconds", [4_000_001, 5_000_000])
def test_cached_live_tick_cannot_remain_live_after_current_age_exceeds_five_seconds(
    elapsed_microseconds: int,
) -> None:
    value = _input()
    assert value.tick is not None and value.safety is not None
    # The tick was LIVE at observation (age 1s). Later evaluation must recalculate
    # current freshness even though the cached classification has not changed.
    value = value.model_copy(
        update={
            "evaluated_at": NOW + timedelta(microseconds=elapsed_microseconds),
            "safety": value.safety.model_copy(
                update={
                    "news_checked_until": NOW + timedelta(minutes=16),
                }
            ),
        }
    )
    assert value.tick is not None
    assert value.tick.freshness is TickFreshness.LIVE
    assert value.tick.age_seconds == Decimal("1")
    _blocked(value, "TICK_CURRENT")


@pytest.mark.parametrize(
    ("configured_maximum", "live_milliseconds"),
    [
        (10, 5000),
        (4, 2000),
        (3, 1500),
        (1, 500),
        (300, 5000),
    ],
)
def test_tick_live_threshold_includes_exact_boundary_and_rejects_next_microsecond(
    configured_maximum: int,
    live_milliseconds: int,
) -> None:
    value = _input()
    assert value.tick is not None
    value = value.model_copy(
        update={
            "maximum_tick_age_seconds": configured_maximum,
            "tick": value.tick.model_copy(
                update={
                    "tick_at": NOW - timedelta(milliseconds=live_milliseconds),
                    "age_seconds": Decimal(live_milliseconds) / Decimal("1000"),
                }
            ),
        }
    )
    assert evaluate_shadow_risk(value).outcome == "PASS"
    _blocked(
        value.model_copy(update={"evaluated_at": NOW + timedelta(microseconds=1)}),
        "TICK_CURRENT",
    )


@pytest.mark.parametrize("policy", [UTC_POLICY, PEPPERSTONE_POLICY])
def test_exact_native_market_version_is_distinct_from_base_and_reconciliation(
    policy: MarketTimePolicy,
) -> None:
    value = _input()
    assert value.account is not None and value.specification is not None
    assert value.tick is not None
    # Construct an unconnected adapter and call only its pure version helper.
    # No SDK import, terminal access or native account/session is involved.
    adapter = MetaTrader5ReadAdapter(
        Mt5WorkerConfig(
            market_time_policy=policy,
            broker_symbol=value.provenance.broker_symbol,
            expected_account_fingerprint=value.provenance.account_fingerprint,
            smoke_confirmed_specification_fingerprint=(
                value.provenance.specification_fingerprint
            ),
        ),
        clock=lambda: NOW,
        platform="win32",
    )
    market_version = adapter._market_adapter_version()
    assert market_version == (
        ADAPTER_VERSION if policy == UTC_POLICY else f"{ADAPTER_VERSION}:{policy}"
    )
    provenance = value.provenance.model_copy(
        update={
            "adapter_version": ADAPTER_VERSION,
            "market_adapter_version": market_version,
        }
    )
    updates: dict[str, object] = {
        "provenance": provenance,
        "account": value.account.model_copy(
            update={"adapter_version": ADAPTER_VERSION}
        ),
        "specification": value.specification.model_copy(
            update={"adapter_version": ADAPTER_VERSION}
        ),
        "tick": value.tick.model_copy(update={"adapter_version": market_version}),
    }
    for field in ("candidate", "account_risk", "safety", "costs"):
        updates[field] = getattr(value, field).model_copy(
            update={"provenance": provenance}
        )
    bound = value.model_copy(update=updates)
    result = evaluate_shadow_risk(bound)
    assert result.outcome == "PASS"
    assert result.provenance.market_adapter_version == market_version
    assert bound.tick is not None
    wrong_version = (
        f"{ADAPTER_VERSION}:{PEPPERSTONE_POLICY}"
        if policy == UTC_POLICY
        else ADAPTER_VERSION
    )
    _blocked(
        bound.model_copy(
            update={
                "tick": bound.tick.model_copy(update={"adapter_version": wrong_version})
            }
        ),
        "TICK_SOURCE",
    )
    _blocked(
        bound.model_copy(update={"candidate": value.candidate}), "CANDIDATE_CURRENT"
    )


def test_missing_market_adapter_version_is_not_inferred_from_base_version() -> None:
    payload = _input().provenance.model_dump(mode="python")
    del payload["market_adapter_version"]
    with pytest.raises(ValidationError):
        ShadowRiskProvenance.model_validate(payload)
