"""Production Shadow market stage over the existing read-only port.

No native SDK, profile, environment, fixture fallback, or broker-write dependency.
Capture is an explicit bounded full-cycle operation, never short-tick polling.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import AwareDatetime

from aurum_worker.adapters.protocols import Mt5ObservationPersistencePort, Mt5ReadPort
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountVerificationState,
    BrokerSymbolObservation,
    CandleRequest,
    CandleSeries,
    ConfirmedSymbolBinding,
    HealthState,
    HistoryQueryResultState,
    LatestTickObservation,
    Mt5Model,
    Mt5ReadFailure,
    Mt5ReasonCode,
    Mt5WorkerConfig,
    PositiveDecimal,
    ReconciliationOutcome,
    SymbolUsabilityState,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_market_time import UTC_POLICY, MarketTimePolicy
from aurum_worker.mt5_safety import verify_account
from aurum_worker.reconciliation import (
    ReadOnlyReconciliationService,
    ReconciliationResult,
)


class MarketBlockCode(StrEnum):
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    BINDING_CHANGED = "BINDING_CHANGED"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    TIME_INVALID = "TIME_INVALID"
    TICK_NOT_CURRENT = "TICK_NOT_CURRENT"
    CANDLES_INVALID = "CANDLES_INVALID"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class MarketBlocked(Mt5Model):
    status: Literal["blocked"] = "blocked"
    reason: MarketBlockCode
    native_reason: Mt5ReasonCode | None = None
    grants_eligibility: Literal[False] = False


class MarketFeatures(Mt5Model):
    status: Literal["features_ready"] = "features_ready"
    environment: Literal["DEMO_ONLY"] = "DEMO_ONLY"
    runtime_mode: Literal["SHADOW"] = "SHADOW"
    source: Literal["mt5"] = "mt5"
    adapter_version: str
    market_adapter_version: str
    market_time_policy: MarketTimePolicy
    normalization_version: Literal["completed-m1-v1"] = "completed-m1-v1"
    feature_version: Literal["sma3-sma5-atr5-v1"] = "sma3-sma5-atr5-v1"
    account_fingerprint: str
    specification_fingerprint: str
    reconciliation_id: str
    market_snapshot_id: str
    feature_snapshot_id: str
    input_digest: str
    evaluated_at: AwareDatetime
    last_bar_closed_at: AwareDatetime
    bid: PositiveDecimal
    ask: PositiveDecimal
    fast_sma: PositiveDecimal
    slow_sma: PositiveDecimal
    atr: Decimal
    grants_eligibility: Literal[False] = False


@dataclass(frozen=True, slots=True)
class MarketCapture:
    """Exact validated source inputs retained alongside their normalized digest."""

    features: MarketFeatures
    series: CandleSeries
    tick: LatestTickObservation
    account: AccountObservation
    specification: BrokerSymbolObservation
    confirmed_binding: ConfirmedSymbolBinding
    reconciliation: ReconciliationResult


class _Blocked(Exception):
    def __init__(self, reason: MarketBlockCode) -> None:
        self.reason = reason


def _require(condition: bool, reason: MarketBlockCode) -> None:
    if not condition:
        raise _Blocked(reason)


def _current(at: datetime, now: datetime, seconds: int = 5) -> bool:
    return (
        at.utcoffset() is not None
        and now.utcoffset() is not None
        and timedelta(0) <= now - at <= timedelta(seconds=seconds)
    )


def _number(value: Decimal) -> str:
    # normalize() applies the active Decimal precision and can erase source
    # digits from a content hash. Canonicalize zeros without numeric rounding.
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _calculate_normalized(
    series: CandleSeries,
    tick: LatestTickObservation,
    specification: BrokerSymbolObservation,
    account: AccountObservation,
    reconciliation: ReconciliationResult,
    now: datetime,
    maximum_live_age: timedelta,
    market_time_policy: MarketTimePolicy,
) -> MarketFeatures:
    # Revalidate nested data instead of trusting model_copy/model_construct callers.
    series = CandleSeries.model_validate(series.model_dump())
    tick = LatestTickObservation.model_validate(tick.model_dump())
    bars = series.candles
    expected_market_version = (
        account.adapter_version
        if market_time_policy == UTC_POLICY
        else f"{account.adapter_version}:{market_time_policy}"
    )
    _require(len(bars) == 6 and not series.gaps, MarketBlockCode.CANDLES_INVALID)
    for index, bar in enumerate(bars):
        _require(
            bar.source == tick.source == account.source == specification.source == "mt5"
            and bar.adapter_version == tick.adapter_version == expected_market_version
            and account.adapter_version == specification.adapter_version
            and bar.symbol == tick.symbol == specification.broker_symbol,
            MarketBlockCode.SOURCE_MISMATCH,
        )
        _require(
            bar.timeframe is Timeframe.M1
            and bar.is_complete
            and bar.open_at.astimezone(UTC).second == 0
            and bar.open_at.astimezone(UTC).microsecond == 0
            and bar.open_at + timedelta(minutes=1) <= bar.observed_at <= now
            and _current(bar.observed_at, now)
            and (
                index == 0
                or bar.open_at - bars[index - 1].open_at == timedelta(minutes=1)
            ),
            MarketBlockCode.CANDLES_INVALID,
        )
    close_at = bars[-1].open_at + timedelta(minutes=1)
    _require(now - close_at < timedelta(minutes=1), MarketBlockCode.CANDLES_INVALID)
    _require(
        tick.freshness is TickFreshness.LIVE
        and _current(tick.tick_at, now)
        and now - tick.tick_at <= maximum_live_age
        and _current(tick.observed_at, now),
        MarketBlockCode.TICK_NOT_CURRENT,
    )
    _require(
        tick.spread_points * specification.point == tick.spread_price,
        MarketBlockCode.SOURCE_MISMATCH,
    )
    with localcontext() as context:
        context.prec = 38
        fast = sum((bar.close for bar in bars[-3:]), Decimal(0)) / 3
        slow = sum((bar.close for bar in bars[-5:]), Decimal(0)) / 5
        ranges = [
            max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - bars[i - 1].close),
                abs(bars[i].low - bars[i - 1].close),
            )
            for i in range(1, 6)
        ]
        atr = sum(ranges, Decimal(0)) / 5
        payload = {
            "normalization": "completed-m1-v1",
            "source": tick.source,
            "adapter": tick.adapter_version,
            "account": account.account_fingerprint,
            "server": account.server_fingerprint,
            "specification": specification.specification_fingerprint,
            "symbol": specification.broker_symbol,
            "point": _number(specification.point),
            "tick_size": _number(specification.tick_size),
            "tick_at": tick.tick_at.astimezone(UTC).isoformat(),
            "bid": _number(tick.bid),
            "ask": _number(tick.ask),
            "bars": [
                [bar.open_at.astimezone(UTC).isoformat()]
                + [_number(value) for value in (bar.open, bar.high, bar.low, bar.close)]
                for bar in bars
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        market_id = str(uuid5(NAMESPACE_URL, "aurum:market:" + digest))
        return MarketFeatures(
            adapter_version=account.adapter_version,
            market_adapter_version=tick.adapter_version,
            market_time_policy=market_time_policy,
            account_fingerprint=account.account_fingerprint,
            specification_fingerprint=specification.specification_fingerprint,
            reconciliation_id=reconciliation.report.reconciliation_id,
            market_snapshot_id=market_id,
            feature_snapshot_id=str(
                uuid5(NAMESPACE_URL, market_id + ":sma3-sma5-atr5-v1")
            ),
            input_digest=digest,
            evaluated_at=now.astimezone(UTC),
            last_bar_closed_at=close_at.astimezone(UTC),
            bid=tick.bid,
            ask=tick.ask,
            fast_sma=fast,
            slow_sma=slow,
            atr=atr,
        )


class ShadowMarketService:
    """Collect real-port input only after a current successful full reconciliation.

    Caller owns adapter lifecycle and serialization with any poller. This service
    never starts a second native session or supplies missing market/history data.
    Features are returned to the caller, not yet persisted or promoted to proposals.
    """

    def __init__(
        self,
        adapter: Mt5ReadPort,
        persistence: Mt5ObservationPersistencePort,
        reconciliation: ReadOnlyReconciliationService,
        config: Mt5WorkerConfig,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._adapter = adapter
        self._persistence = persistence
        self._reconciliation = reconciliation
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))

    def _bindings(
        self,
        binding: ConfirmedSymbolBinding,
        result: ReconciliationResult,
        trace_id: str,
    ) -> tuple[AccountObservation, BrokerSymbolObservation]:
        terminal = self._adapter.get_terminal_info(trace_id=trace_id)
        _require(terminal.connected is True, MarketBlockCode.SOURCE_UNAVAILABLE)
        account = self._adapter.get_account_info(trace_id=trace_id)
        _require(
            verify_account(account, self._config.expected_account_fingerprint).state
            is AccountVerificationState.VERIFIED_DEMO_BOUND
            and account.account_fingerprint == result.report.account_fingerprint
            and account.server_fingerprint == result.report.server_fingerprint,
            MarketBlockCode.BINDING_CHANGED,
        )
        specification = self._adapter.get_symbol_specification(
            binding.broker_symbol, trace_id=trace_id
        )
        now = self._clock()
        _require(
            all(
                _current(item.observed_at, now)
                for item in (terminal, account, specification)
            ),
            MarketBlockCode.TIME_INVALID,
        )
        _require(
            terminal.source == account.source == specification.source == "mt5"
            and terminal.adapter_version
            == account.adapter_version
            == specification.adapter_version,
            MarketBlockCode.SOURCE_MISMATCH,
        )
        _require(
            verify_account(account, self._config.expected_account_fingerprint).state
            is AccountVerificationState.VERIFIED_DEMO_BOUND
            and account.account_fingerprint == result.report.account_fingerprint
            and account.server_fingerprint == result.report.server_fingerprint
            and specification.broker_symbol
            == binding.broker_symbol
            == result.report.broker_symbol
            and specification.specification_fingerprint
            == binding.confirmed_specification_fingerprint
            == result.report.symbol_specification_fingerprint
            and specification.base_currency == "XAU"
            and specification.profit_currency == "USD"
            and specification.usability_state is SymbolUsabilityState.USABLE,
            MarketBlockCode.BINDING_CHANGED,
        )
        return account, specification

    def capture(self, *, trace_id: str) -> MarketFeatures | MarketBlocked:
        """Compatibility entry point returning only the normalized features."""

        result = self.capture_bundle(trace_id=trace_id)
        return result.features if isinstance(result, MarketCapture) else result

    def capture_bundle(
        self,
        *,
        trace_id: str,
        reconciliation_result: ReconciliationResult | None = None,
    ) -> MarketCapture | MarketBlocked:
        """Collect once and retain the exact source observations used for features."""

        try:
            _require(
                bool(self._config.expected_account_fingerprint),
                MarketBlockCode.BINDING_CHANGED,
            )
            result = (
                reconciliation_result
                if reconciliation_result is not None
                else self._reconciliation.run(trace_id=trace_id)
            )
            report, health = result.report, result.health
            now = self._clock()
            _require(
                health.state is HealthState.HEALTHY
                and health.reason_code is Mt5ReasonCode.HEALTHY
                and health.terminal_connected
                and health.account_verification_state
                is AccountVerificationState.VERIFIED_DEMO_BOUND
                and health.reconciliation_outcome is ReconciliationOutcome.MATCHED
                and report.outcome is ReconciliationOutcome.MATCHED
                and not report.mismatches,
                MarketBlockCode.RECONCILIATION_REQUIRED,
            )
            _require(
                _current(report.started_at, now)
                and _current(report.completed_at, now)
                and _current(health.observed_at, now),
                MarketBlockCode.TIME_INVALID,
            )
            orders, deals = report.order_history_evidence, report.deal_history_evidence
            successful = {
                HistoryQueryResultState.QUERY_SUCCEEDED,
                HistoryQueryResultState.EMPTY_VALID_RESULT,
            }
            _require(
                orders.result_state in successful
                and deals.result_state in successful
                and orders.requested_start_at == deals.requested_start_at
                and orders.requested_end_at == deals.requested_end_at
                and orders.query_completed_at is not None
                and deals.query_completed_at is not None
                and _current(orders.requested_end_at, now)
                and _current(orders.query_completed_at, now)
                and _current(deals.query_completed_at, now)
                and orders.requested_end_at == report.started_at
                and report.started_at
                <= orders.query_completed_at
                <= report.completed_at
                and report.started_at <= deals.query_completed_at <= report.completed_at
                and report.completed_at <= health.observed_at,
                MarketBlockCode.RECONCILIATION_REQUIRED,
            )
            database = self._persistence.load_reconciliation_state()
            _require(
                database.account_fingerprint == report.account_fingerprint
                and database.server_fingerprint == report.server_fingerprint
                and database.position_tickets == result.position_tickets
                and database.active_order_tickets == result.active_order_tickets
                and not database.executing_command_ids,
                MarketBlockCode.RECONCILIATION_REQUIRED,
            )
            binding = database.confirmed_symbol_binding
            _require(binding is not None, MarketBlockCode.BINDING_CHANGED)
            assert binding is not None
            _require(binding.confirmed_at <= now, MarketBlockCode.TIME_INVALID)
            account, specification = self._bindings(binding, result, trace_id)
            tick = self._adapter.get_latest_tick(
                binding.broker_symbol, trace_id=trace_id
            )
            series = self._adapter.get_candles(
                binding.broker_symbol,
                Timeframe.M1,
                CandleRequest(count=6),
                trace_id=trace_id,
            )
            positions = self._adapter.get_open_positions(trace_id=trace_id)
            active_orders = self._adapter.get_active_orders(trace_id=trace_id)
            position_check_at = self._clock()
            _require(
                all(
                    item.source == "mt5"
                    and item.adapter_version == account.adapter_version
                    and _current(item.observed_at, position_check_at)
                    for item in (*positions, *active_orders)
                ),
                MarketBlockCode.SOURCE_MISMATCH,
            )
            _require(
                frozenset(item.ticket for item in positions) == result.position_tickets
                and frozenset(item.ticket for item in active_orders)
                == result.active_order_tickets
                and len(positions) == len(result.position_tickets)
                and len(active_orders) == len(result.active_order_tickets),
                MarketBlockCode.RECONCILIATION_REQUIRED,
            )
            final_account, final_specification = self._bindings(
                binding, result, trace_id
            )
            _require(
                self._persistence.load_reconciliation_state() == database
                and final_account.source == account.source
                and final_account.adapter_version == account.adapter_version
                and final_specification.model_dump(exclude={"observed_at", "trace_id"})
                == specification.model_dump(exclude={"observed_at", "trace_id"}),
                MarketBlockCode.BINDING_CHANGED,
            )
            final_now = self._clock()
            _require(
                _current(report.completed_at, final_now)
                and _current(report.started_at, final_now),
                MarketBlockCode.TIME_INVALID,
            )
            with localcontext(Context(prec=38, rounding=ROUND_HALF_EVEN)):
                features = _calculate_normalized(
                    series,
                    tick,
                    specification,
                    final_account,
                    result,
                    final_now,
                    timedelta(
                        milliseconds=min(5000, self._config.max_tick_age_seconds * 500)
                    ),
                    self._config.market_time_policy,
                )
            return MarketCapture(
                features=features,
                series=series,
                tick=tick,
                account=final_account,
                specification=specification,
                confirmed_binding=binding,
                reconciliation=result,
            )
        except _Blocked as blocked:
            return MarketBlocked(reason=blocked.reason)
        except Mt5ReadFailure as failure:
            return MarketBlocked(
                reason=MarketBlockCode.SOURCE_UNAVAILABLE,
                native_reason=failure.error.reason_code,
            )
        except Exception:
            # Never expose native exception text, input values, or partial features.
            return MarketBlocked(reason=MarketBlockCode.SOURCE_UNAVAILABLE)
