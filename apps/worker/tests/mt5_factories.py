from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aurum_worker.adapters.fake_mt5 import FakeMt5ReadAdapter
from aurum_worker.models.mt5 import (
    AccountObservation,
    AccountTradeMode,
    ActiveOrderObservation,
    BrokerSymbolCandidate,
    BrokerSymbolObservation,
    CandleObservation,
    CandleSeries,
    ConfirmedSymbolBinding,
    HistoricalDealObservation,
    HistoricalOrderObservation,
    LatestTickObservation,
    OpenPositionObservation,
    PositionDirection,
    SymbolTradeMode,
    SymbolUsabilityState,
    TerminalObservation,
    TickFreshness,
    Timeframe,
)
from aurum_worker.mt5_safety import account_fingerprint, server_fingerprint

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
RAW_LOGIN = int("123" + "456")
RAW_SERVER = "Demo" + "-Server"


def terminal() -> TerminalObservation:
    return TerminalObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        connected=True,
        platform="windows",
        terminal_version="5.0",
        terminal_build="5000",
        trade_allowed=False,
    )


def account(mode: AccountTradeMode = AccountTradeMode.DEMO) -> AccountObservation:
    return AccountObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        trade_mode=mode,
        masked_login="••••3456",
        masked_server="demo…1234",
        account_fingerprint=account_fingerprint(RAW_LOGIN, RAW_SERVER),
        server_fingerprint=server_fingerprint(RAW_SERVER),
        currency="USD",
        leverage=100,
    )


def candidate(symbol: str = "XAUUSD", *, visible: bool = True) -> BrokerSymbolCandidate:
    return BrokerSymbolCandidate(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        broker_symbol=symbol,
        symbol_path="Metals",
        description="Gold versus US Dollar",
        base_currency="XAU",
        profit_currency="USD",
        exact_name=symbol == "XAUUSD",
        visible=visible,
    )


def specification(
    fingerprint: str = "mt5-spec-v1:fixture",
    *,
    usability: SymbolUsabilityState = SymbolUsabilityState.USABLE,
) -> BrokerSymbolObservation:
    from aurum_worker.models.mt5 import Mt5ReasonCode

    return BrokerSymbolObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        broker_symbol="XAUUSD",
        symbol_path="Metals",
        description="Gold versus US Dollar",
        base_currency="XAU",
        profit_currency="USD",
        margin_currency="USD",
        digits=2,
        point=Decimal("0.01"),
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1.00"),
        tick_value_profit=Decimal("1.00"),
        tick_value_loss=Decimal("1.00"),
        contract_size=Decimal("100"),
        minimum_volume=Decimal("0.01"),
        maximum_volume=Decimal("100"),
        volume_step=Decimal("0.01"),
        stops_level=10,
        freeze_level=0,
        trade_calculation_mode="calc_1",
        trade_mode=SymbolTradeMode.FULL,
        filling_mode="fill_1",
        expiration_mode="expiration_1",
        order_mode="order_127",
        specification_fingerprint=fingerprint,
        usability_state=usability,
        unusable_reason=(
            None
            if usability is SymbolUsabilityState.USABLE
            else Mt5ReasonCode.SYMBOL_NOT_VISIBLE
        ),
        raw_diagnostic_codes={"trade_mode": 4},
    )


def confirmed_binding(
    fingerprint: str = "mt5-spec-v1:fixture",
    *,
    broker_symbol: str = "XAUUSD",
    version: int = 1,
) -> ConfirmedSymbolBinding:
    return ConfirmedSymbolBinding(
        owner_id="00000000-0000-4000-8000-000000000201",
        trading_account_id="00000000-0000-4000-8000-000000000301",
        canonical_symbol="XAUUSD",
        broker_symbol=broker_symbol,
        confirmed_specification_fingerprint=fingerprint,
        confirmation_status="confirmed",
        confirmed_at=NOW,
        confirmed_by="00000000-0000-4000-8000-000000000201",
        version=version,
    )


def tick(freshness: TickFreshness = TickFreshness.LIVE) -> LatestTickObservation:
    age = Decimal("1")
    tick_at = NOW - timedelta(seconds=1)
    if freshness is TickFreshness.STALE:
        age = Decimal("120")
        tick_at = NOW - timedelta(seconds=120)
    elif freshness is TickFreshness.FUTURE_INVALID:
        age = Decimal("60")
        tick_at = NOW + timedelta(seconds=60)
    return LatestTickObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        symbol="XAUUSD",
        bid=Decimal("2345.10"),
        ask=Decimal("2345.30"),
        spread_price=Decimal("0.20"),
        spread_points=Decimal("20"),
        tick_at=tick_at,
        age_seconds=age,
        freshness=freshness,
    )


def candle_series() -> CandleSeries:
    candles = tuple(
        CandleObservation(
            observed_at=NOW,
            source="fake_mt5",
            adapter_version="fake-v1",
            trace_id="fixture",
            symbol="XAUUSD",
            timeframe=Timeframe.M1,
            open_at=NOW - timedelta(minutes=3 - index),
            open=Decimal("2345.00"),
            high=Decimal("2346.00"),
            low=Decimal("2344.00"),
            close=Decimal("2345.50"),
            tick_volume=Decimal("100"),
            spread=Decimal("20"),
            real_volume=Decimal("0"),
            is_complete=True,
        )
        for index in range(3)
    )
    return CandleSeries(candles=candles)


def position(ticket: str = "1001") -> OpenPositionObservation:
    return OpenPositionObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        ticket=ticket,
        symbol="XAUUSD",
        direction=PositionDirection.BUY,
        volume=Decimal("0.01"),
        entry_price=Decimal("2340"),
        current_price=Decimal("2345"),
        stop_loss=Decimal("2330"),
        take_profit=Decimal("2350"),
        unrealized_profit=Decimal("5"),
        swap=Decimal("-0.10"),
        opened_at=NOW - timedelta(hours=1),
    )


def active_order(ticket: str = "2001") -> ActiveOrderObservation:
    return ActiveOrderObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        ticket=ticket,
        symbol="XAUUSD",
        order_type="order_type_2",
        state="order_state_1",
        volume_initial=Decimal("0.01"),
        volume_current=Decimal("0.01"),
        requested_price=Decimal("2330"),
        stop_loss=Decimal("2320"),
        take_profit=Decimal("2350"),
        setup_at=NOW - timedelta(minutes=10),
    )


def historical_order(ticket: str = "3001") -> HistoricalOrderObservation:
    return HistoricalOrderObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        ticket=ticket,
        symbol="XAUUSD",
        order_type="order_type_0",
        state="order_state_4",
        volume_initial=Decimal("0.01"),
        volume_current=Decimal("0"),
        requested_price=Decimal("2340"),
        stop_loss=Decimal("2330"),
        take_profit=Decimal("2350"),
        setup_at=NOW - timedelta(hours=1),
        completed_at=NOW - timedelta(minutes=59),
        safe_comment="safe",
    )


def deal(ticket: str = "4001") -> HistoricalDealObservation:
    return HistoricalDealObservation(
        observed_at=NOW,
        source="fake_mt5",
        adapter_version="fake-v1",
        trace_id="fixture",
        ticket=ticket,
        order_ticket="3001",
        position_ticket="1001",
        symbol="XAUUSD",
        direction=PositionDirection.BUY,
        volume=Decimal("0.01"),
        price=Decimal("2340"),
        profit=Decimal("0"),
        commission=Decimal("-0.10"),
        swap=Decimal("0"),
        occurred_at=NOW - timedelta(minutes=59),
        safe_comment="safe",
    )


def fake_adapter(
    *,
    account_modes: tuple[AccountTradeMode, ...] = (AccountTradeMode.DEMO,),
    positions: tuple[OpenPositionObservation, ...] = (),
    orders: tuple[ActiveOrderObservation, ...] = (),
    freshness: TickFreshness = TickFreshness.LIVE,
) -> FakeMt5ReadAdapter:
    return FakeMt5ReadAdapter(
        terminal=terminal(),
        accounts=tuple(account(mode) for mode in account_modes),
        candidates=(candidate(),),
        specifications={"XAUUSD": specification()},
        ticks={"XAUUSD": tick(freshness)},
        candles={("XAUUSD", Timeframe.M1): candle_series()},
        positions=positions,
        orders=orders,
        order_history=(historical_order(),),
        deal_history=(deal(),),
    )
