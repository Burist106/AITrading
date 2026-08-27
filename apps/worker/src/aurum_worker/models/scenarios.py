"""Authoritative scenario identifier type shared with the static shell."""

from enum import StrEnum


class PrototypeScenarioId(StrEnum):
    NO_SIGNAL = "no_signal"
    WAIT = "wait"
    AUTO_ELIGIBLE = "auto_eligible"
    HUMAN_APPROVAL = "human_approval"
    BLOCKED = "blocked"
    PROPOSAL_EXPIRED = "proposal_expired"
    APPROVAL_RECORDED = "approval_recorded"
    REVALIDATION_FAILED = "revalidation_failed"
    ORDER_PENDING = "order_pending"
    ORDER_REJECTED = "order_rejected"
    POSITION_OPEN = "position_open"
    POSITION_CLOSED = "position_closed"
    MT5_DISCONNECTED = "mt5_disconnected"
    MARKET_DATA_STALE = "market_data_stale"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    EMERGENCY_STOP_REQUESTED = "emergency_stop_requested"
    EMERGENCY_STOP_CONFIRMED = "emergency_stop_confirmed"
    EMERGENCY_STOP_UNCONFIRMED = "emergency_stop_unconfirmed"
    LIVE_ACCOUNT_DETECTED = "live_account_detected"
    MINIMUM_LOT_EXCEEDS_RISK = "minimum_lot_exceeds_risk"
