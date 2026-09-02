import {
  Mt5ConsoleReadModelSchema,
  type Mt5ConsoleReadModel,
} from "@aurum/contracts";
import type { ScenarioPresentation } from "@aurum/fixtures";

const OBSERVED_AT = "2026-08-28T00:00:00.000Z";
const HISTORY_START_AT = "2026-08-27T00:00:00.000Z";
const HISTORY_COMPLETED_AT = "2026-08-28T00:00:01.000Z";

export function buildMt5ConsoleFixture(
  scenario: ScenarioPresentation,
): Mt5ConsoleReadModel {
  const blocked = scenario.accountVerification === "blocked_non_demo";
  const connected = scenario.mt5State === "connected";
  const stale = scenario.marketFreshness === "stale";
  const pending = scenario.mt5State === "reconnecting";
  const state =
    blocked || stale ? "blocked" : connected ? "healthy" : "degraded";
  const reasonCode = blocked
    ? "REAL_ACCOUNT_BLOCKED"
    : stale
      ? "TICK_STALE"
      : pending
        ? "TERMINAL_DISCONNECTED"
        : connected
          ? "HEALTHY"
          : "TERMINAL_DISCONNECTED";
  const outcome = blocked ? "incomplete" : pending ? null : "matched";
  const reconciliationReasonCode =
    outcome === "matched" ? "HEALTHY" : reasonCode;

  return Mt5ConsoleReadModelSchema.parse({
    account: {
      observedAt: OBSERVED_AT,
      source: "fake_mt5",
      adapterVersion: "fixture-v1",
      traceId: "fixture-mt5",
      schemaVersion: "1",
      tradeMode: blocked ? "real" : "demo",
      verificationState: blocked
        ? "real_account_blocked"
        : "verified_demo_bound",
      maskedLogin: "••••3456",
      maskedServer: "demo…a91f",
      accountFingerprint: "mt5-account-v1:fixture",
      serverFingerprint: "mt5-server-v1:fixture",
    },
    symbol: {
      observedAt: OBSERVED_AT,
      source: "fake_mt5",
      adapterVersion: "fixture-v1",
      traceId: "fixture-mt5",
      schemaVersion: "1",
      canonicalSymbol: "XAUUSD",
      brokerSymbol: "XAUUSD",
      currencyBase: "XAU",
      currencyProfit: "USD",
      specificationFingerprint: "mt5-spec-v1:fixture",
      usabilityState: "usable",
      unusableReason: null,
      point: "0.01",
      tickSize: "0.01",
      contractSize: "100",
      minimumVolume: "0.01",
      maximumVolume: "100",
      volumeStep: "0.01",
    },
    tick: connected
      ? {
          observedAt: OBSERVED_AT,
          source: "fake_mt5",
          adapterVersion: "fixture-v1",
          traceId: "fixture-mt5",
          schemaVersion: "1",
          symbol: "XAUUSD",
          bid: "2345.10",
          ask: "2345.30",
          spreadPrice: "0.20",
          spreadPoints: "20",
          tickAt: OBSERVED_AT,
          ageSeconds: stale ? "45" : "1",
          freshness: stale ? "stale" : "live",
        }
      : null,
    reconciliation: {
      id: "00000000-0000-4000-8000-000000008201",
      traceId: "fixture-mt5",
      status: pending ? "running" : "completed",
      outcome,
      reasonCode: reconciliationReasonCode,
      startedAt: OBSERVED_AT,
      completedAt: pending ? null : OBSERVED_AT,
      openPositionCount: scenario.positionState.startsWith("open") ? 1 : 0,
      activeOrderCount: 0,
      mismatchCount: blocked ? 1 : 0,
      mismatches: blocked
        ? [
            {
              category: "ACCOUNT_CHANGED",
              severity: "critical",
              resourceType: "account",
              resourceReference: "mt5-account-v1:fixture",
              reasonCode: "REAL_ACCOUNT_BLOCKED",
            },
          ]
        : [],
      historyEvidence: pending
        ? []
        : (["orders", "deals"] as const).map((historyKind) => ({
            historyKind,
            requestedStartAt: HISTORY_START_AT,
            requestedEndAt: OBSERVED_AT,
            queryCompletedAt: blocked ? null : HISTORY_COMPLETED_AT,
            returnedCount: 0,
            earliestReturnedAt: null,
            latestReturnedAt: null,
            resultState: blocked
              ? ("window_unknown" as const)
              : ("empty_valid_result" as const),
            reasonCode: blocked
              ? "HISTORY_WINDOW_INCOMPLETE"
              : "HISTORY_EMPTY_VALID_RESULT",
          })),
    },
    health: {
      observedAt: OBSERVED_AT,
      source: "fake_mt5",
      adapterVersion: "fixture-v1",
      traceId: "fixture-mt5",
      schemaVersion: "1",
      state,
      reasonCode,
      packageAvailable: true,
      platform: "windows",
      terminalConnected: connected,
      terminalVersion: connected ? "terminal-fixture-v1" : null,
      accountVerificationState: blocked
        ? "real_account_blocked"
        : "verified_demo_bound",
      maskedAccount: "••••3456",
      maskedServer: "demo…a91f",
      brokerSymbol: "XAUUSD",
      specificationFingerprint: "mt5-spec-v1:fixture",
      tickAgeSeconds: connected ? (stale ? "45" : "1") : null,
      lastCompletedCandleAt: connected ? OBSERVED_AT : null,
      lastSuccessfulObservationAt: connected ? OBSERVED_AT : null,
      reconciliationOutcome: outcome,
      openPositionCount: scenario.positionState.startsWith("open") ? 1 : 0,
      activeOrderCount: 0,
    },
  });
}
