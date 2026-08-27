"""Read-side Position state with no broker mutation capability."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from aurum_worker.models.base import (
    FiniteFloat,
    Identifier,
    PositiveFloat,
    PositiveInt,
    WireModel,
)
from aurum_worker.models.trading import PermittedVolume, TradeDirection


class PositionStatus(StrEnum):
    OPEN = "open"
    CLOSE_REQUESTED = "close_requested"
    CLOSING = "closing"
    CLOSED = "closed"
    MISMATCH = "mismatch"


class Position(WireModel):
    id: UUID
    position_version: PositiveInt
    user_id: UUID
    trading_account_id: UUID
    account_type: Literal["demo"]
    canonical_symbol: Literal["XAUUSD"]
    direction: TradeDirection
    volume: PermittedVolume
    entry: PositiveFloat
    current: PositiveFloat
    stop_loss: PositiveFloat
    take_profit: PositiveFloat
    unrealized_pnl: FiniteFloat
    r_multiple: FiniteFloat
    status: PositionStatus
    opened_at: AwareDatetime
    updated_at: AwareDatetime
    closed_at: AwareDatetime | None

    @model_validator(mode="after")
    def validate_position_state(self) -> Position:
        if self.direction is TradeDirection.BUY:
            prices_are_ordered = self.stop_loss < self.entry < self.take_profit
        else:
            prices_are_ordered = self.take_profit < self.entry < self.stop_loss
        if not prices_are_ordered:
            raise ValueError(
                "Entry, Stop Loss, and Take Profit are invalid for direction."
            )

        if self.status is PositionStatus.CLOSED and self.closed_at is None:
            raise ValueError("A closed Position requires a close timestamp.")
        if self.status is not PositionStatus.CLOSED and self.closed_at is not None:
            raise ValueError("Only a closed Position may carry a close timestamp.")
        if self.closed_at is not None and self.closed_at < self.opened_at:
            raise ValueError("A Position cannot close before it opened.")
        return self


class PersistedPosition(WireModel):
    """SQL-aligned row after snake_case has been mapped to wire aliases."""

    id: UUID
    owner_id: UUID
    trading_account_id: UUID
    trade_proposal_id: UUID
    broker_order_id: UUID
    broker_position_reference: Identifier
    position_version: PositiveInt
    direction: TradeDirection
    volume: PermittedVolume
    entry_price: PositiveFloat
    current_price: PositiveFloat
    stop_loss_price: PositiveFloat
    take_profit_price: PositiveFloat
    unrealized_pnl: FiniteFloat
    r_multiple: FiniteFloat
    status: PositionStatus
    opened_at: AwareDatetime
    closed_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    def to_position(self) -> Position:
        return Position.model_validate(
            {
                "id": self.id,
                "positionVersion": self.position_version,
                "userId": self.owner_id,
                "tradingAccountId": self.trading_account_id,
                "accountType": "demo",
                "canonicalSymbol": "XAUUSD",
                "direction": self.direction,
                "volume": self.volume,
                "entry": self.entry_price,
                "current": self.current_price,
                "stopLoss": self.stop_loss_price,
                "takeProfit": self.take_profit_price,
                "unrealizedPnl": self.unrealized_pnl,
                "rMultiple": self.r_multiple,
                "status": self.status,
                "openedAt": self.opened_at,
                "updatedAt": self.updated_at,
                "closedAt": self.closed_at,
            }
        )
