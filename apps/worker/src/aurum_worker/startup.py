"""Fail-closed Bootstrap startup validation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from aurum_worker.adapters.protocols import Mt5ReadAdapter
from aurum_worker.models.bootstrap import WorkerStartupReport
from aurum_worker.models.safety import (
    BOOTSTRAP_SAFETY_POLICY,
    BootstrapSafetyPolicy,
)


class StartupBlockCode(StrEnum):
    NON_DEMO_ACCOUNT = "NON_DEMO_ACCOUNT"
    ACCOUNT_TYPE_UNCERTAIN = "ACCOUNT_TYPE_UNCERTAIN"
    SYMBOL_SPECIFICATION_UNAVAILABLE = "SYMBOL_SPECIFICATION_UNAVAILABLE"
    OPEN_POSITION_STATE_UNAVAILABLE = "OPEN_POSITION_STATE_UNAVAILABLE"
    OPEN_POSITION_LIMIT_EXCEEDED = "OPEN_POSITION_LIMIT_EXCEEDED"
    BROKER_MINIMUM_VOLUME_EXCEEDS_POLICY = "BROKER_MINIMUM_VOLUME_EXCEEDS_POLICY"


class StartupBlockedError(RuntimeError):
    """Raised before startup whenever a required safety fact is unsafe or unknown."""

    def __init__(self, code: StartupBlockCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class WorkerBootstrap:
    """Verify immutable Demo safety constraints and enter Shadow mode only."""

    def __init__(
        self,
        broker: Mt5ReadAdapter,
        policy: BootstrapSafetyPolicy = BOOTSTRAP_SAFETY_POLICY,
    ) -> None:
        self._broker = broker
        self._policy = policy

    async def start(self, *, started_at: datetime | None = None) -> WorkerStartupReport:
        account = await self._broker.inspect_account()
        if account.is_demo is False:
            raise StartupBlockedError(
                StartupBlockCode.NON_DEMO_ACCOUNT,
                "Worker startup blocked: the detected account is not Demo.",
            )
        if account.is_demo is not True:
            raise StartupBlockedError(
                StartupBlockCode.ACCOUNT_TYPE_UNCERTAIN,
                "Worker startup blocked: Demo account status is uncertain.",
            )

        symbol = self._policy.canonical_symbol
        specification = await self._broker.read_symbol_specification(symbol)
        if specification is None:
            raise StartupBlockedError(
                StartupBlockCode.SYMBOL_SPECIFICATION_UNAVAILABLE,
                "Worker startup blocked: XAUUSD specification is unavailable.",
            )
        if specification.minimum_volume > self._policy.maximum_permitted_volume:
            raise StartupBlockedError(
                StartupBlockCode.BROKER_MINIMUM_VOLUME_EXCEEDS_POLICY,
                "Worker startup blocked: broker minimum volume exceeds policy.",
            )

        open_positions = await self._broker.count_open_positions(symbol)
        if open_positions is None or open_positions < 0:
            raise StartupBlockedError(
                StartupBlockCode.OPEN_POSITION_STATE_UNAVAILABLE,
                "Worker startup blocked: open Position state is uncertain.",
            )
        if open_positions > self._policy.maximum_open_positions:
            raise StartupBlockedError(
                StartupBlockCode.OPEN_POSITION_LIMIT_EXCEEDED,
                "Worker startup blocked: the one-Position limit is exceeded.",
            )

        now = started_at or datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Startup time must include a timezone offset.")
        return WorkerStartupReport.model_validate(
            {
                "startedAt": now,
                "environment": self._policy.environment,
                "runtimeMode": self._policy.runtime_mode,
                "canonicalSymbol": symbol,
                "accountVerifiedDemo": True,
                "detectedOpenPositions": open_positions,
                "symbolSpecificationVersion": specification.specification_version,
            }
        )
