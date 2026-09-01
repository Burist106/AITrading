import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  DecimalStringSchema,
  Mt5AccountReadModelSchema,
  Mt5ComponentCodeSchema,
  Mt5ComponentHeartbeatSchema,
  Mt5HistoryQueryEvidenceSchema,
  Mt5LatestTickReadModelSchema,
  Mt5ReconciliationReadModelSchema,
  Mt5ReasonCodeSchema,
  Mt5SymbolReadModelSchema,
  PositiveDecimalStringSchema,
  TicketIdentifierSchema,
} from "../src";

const parity = JSON.parse(
  readFileSync(
    new URL(
      "../../../contract-fixtures/v1/mt5-readonly-parity.json",
      import.meta.url,
    ),
    "utf8",
  ),
) as {
  schemaVersion: number;
  validDecimalStrings: string[];
  invalidDecimalValues: unknown[];
  validTicketStrings: string[];
  invalidTicketValues: unknown[];
};

describe("MT5 decimal-string and sanitized read contracts", () => {
  it("restricts component heartbeats to typed codes, states, and reasons", () => {
    const heartbeat = {
      componentCode: "execution.market_data",
      state: "degraded",
      detail: "TICK_DELAYED",
      observedAt: "2026-08-28T00:00:00Z",
      validForSeconds: 30,
      traceId: "trace-heartbeat",
    };

    expect(Mt5ComponentHeartbeatSchema.safeParse(heartbeat).success).toBe(true);
    for (const validForSeconds of [15, 300]) {
      expect(
        Mt5ComponentHeartbeatSchema.safeParse({
          ...heartbeat,
          validForSeconds,
        }).success,
      ).toBe(true);
    }
    expect(Mt5ReasonCodeSchema.parse("TICK_DELAYED")).toBe("TICK_DELAYED");
    expect(
      Mt5ComponentCodeSchema.safeParse("execution.arbitrary").success,
    ).toBe(false);
    for (const invalid of [
      { ...heartbeat, componentCode: "execution.arbitrary" },
      { ...heartbeat, state: "unknown" },
      { ...heartbeat, state: "warning" },
      { ...heartbeat, detail: "Traceback from a private terminal path" },
      { ...heartbeat, validForSeconds: 14 },
      { ...heartbeat, validForSeconds: 30.5 },
      { ...heartbeat, validForSeconds: 301 },
      { ...heartbeat, state: "healthy", detail: "TICK_STALE" },
      { ...heartbeat, state: "failed", detail: "HEALTHY" },
      { ...heartbeat, detail: "DEMO_ACCOUNT_UNBOUND" },
      { ...heartbeat, state: "failed", detail: "REAL_ACCOUNT_BLOCKED" },
    ]) {
      expect(Mt5ComponentHeartbeatSchema.safeParse(invalid).success).toBe(
        false,
      );
    }
    for (const detail of [
      "TICK_INVALID",
      "TICK_STALE",
      "TICK_FROM_FUTURE",
      "TICK_UNAVAILABLE",
    ]) {
      expect(
        Mt5ComponentHeartbeatSchema.safeParse({
          ...heartbeat,
          state: "failed",
          detail,
        }).success,
      ).toBe(true);
    }
  });

  it.each(parity.validDecimalStrings)(
    "accepts exact decimal string %s",
    (value) => {
      expect(DecimalStringSchema.safeParse(value).success).toBe(true);
    },
  );

  it.each(parity.invalidDecimalValues)(
    "rejects non-exact decimal boundary %s",
    (value) => {
      expect(DecimalStringSchema.safeParse(value).success).toBe(false);
    },
  );

  it("keeps positive decimal and ticket identities as strings", () => {
    expect(parity.schemaVersion).toBe(1);
    expect(PositiveDecimalStringSchema.safeParse("0.01").success).toBe(true);
    expect(PositiveDecimalStringSchema.safeParse("0").success).toBe(false);
    expect(
      TicketIdentifierSchema.safeParse("90071992547409930001").success,
    ).toBe(true);
    expect(TicketIdentifierSchema.safeParse(9007199254740993).success).toBe(
      false,
    );
    for (const value of parity.validTicketStrings) {
      expect(TicketIdentifierSchema.safeParse(value).success).toBe(true);
    }
    for (const value of parity.invalidTicketValues) {
      expect(TicketIdentifierSchema.safeParse(value).success).toBe(false);
    }
  });

  it("accepts only masked account identity", () => {
    const safe = {
      observedAt: "2026-08-28T00:00:00Z",
      source: "fake_mt5",
      adapterVersion: "fake-v1",
      traceId: "trace",
      schemaVersion: "1",
      tradeMode: "demo",
      verificationState: "verified_demo_bound",
      maskedLogin: "••••3456",
      maskedServer: "demo…a91f",
      accountFingerprint: "mt5-account-v1:fixture",
      serverFingerprint: "mt5-server-v1:fixture",
    };
    expect(Mt5AccountReadModelSchema.safeParse(safe).success).toBe(true);
    expect(
      Mt5AccountReadModelSchema.safeParse({ ...safe, login: "123456" }).success,
    ).toBe(false);
  });

  it("never accepts JavaScript numbers for prices", () => {
    const tick = {
      observedAt: "2026-08-28T00:00:00Z",
      source: "fake_mt5",
      adapterVersion: "fake-v1",
      traceId: "trace",
      schemaVersion: "1",
      symbol: "XAUUSD",
      bid: "2345.10",
      ask: "2345.30",
      spreadPrice: "0.20",
      spreadPoints: "20",
      tickAt: "2026-08-28T00:00:00Z",
      ageSeconds: "1",
      freshness: "live",
    };
    expect(Mt5LatestTickReadModelSchema.safeParse(tick).success).toBe(true);
    expect(
      Mt5LatestTickReadModelSchema.safeParse({ ...tick, bid: 2345.1 }).success,
    ).toBe(false);
  });

  it("accepts a broker alias only when its specification is canonical XAU/USD", () => {
    const symbol = {
      observedAt: "2026-08-28T00:00:00Z",
      source: "fake_mt5",
      adapterVersion: "fake-v1",
      traceId: "trace",
      schemaVersion: "1",
      canonicalSymbol: "XAUUSD",
      brokerSymbol: "GOLD",
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
    };

    expect(Mt5SymbolReadModelSchema.safeParse(symbol).success).toBe(true);
    expect(
      Mt5SymbolReadModelSchema.safeParse({
        ...symbol,
        currencyBase: "EUR",
      }).success,
    ).toBe(false);
    expect(
      Mt5SymbolReadModelSchema.safeParse({
        ...symbol,
        currencyProfit: "JPY",
      }).success,
    ).toBe(false);
  });

  it("keeps bounded history-query evidence explicit", () => {
    const evidence = {
      historyKind: "orders",
      requestedStartAt: "2026-08-27T00:00:00Z",
      requestedEndAt: "2026-08-28T00:00:00Z",
      queryCompletedAt: "2026-08-28T00:00:01Z",
      returnedCount: 0,
      earliestReturnedAt: null,
      latestReturnedAt: null,
      resultState: "empty_valid_result",
      reasonCode: "HISTORY_EMPTY_VALID_RESULT",
    };

    expect(Mt5HistoryQueryEvidenceSchema.safeParse(evidence).success).toBe(
      true,
    );
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...evidence,
        resultState: "complete",
      }).success,
    ).toBe(false);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...evidence,
        resultState: "query_succeeded",
      }).success,
    ).toBe(false);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...evidence,
        resultState: "query_failed",
        reasonCode: "HISTORY_EMPTY_VALID_RESULT",
      }).success,
    ).toBe(false);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...evidence,
        reasonCode: "HEALTHY",
      }).success,
    ).toBe(false);
  });

  it("requires a non-empty requested window completed no earlier than its end", () => {
    const evidence = {
      historyKind: "orders",
      requestedStartAt: "2026-08-27T00:00:00Z",
      requestedEndAt: "2026-08-28T00:00:00Z",
      queryCompletedAt: "2026-08-28T00:00:01Z",
      returnedCount: 0,
      earliestReturnedAt: null,
      latestReturnedAt: null,
      resultState: "empty_valid_result",
      reasonCode: "HISTORY_EMPTY_VALID_RESULT",
    };

    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...evidence,
        requestedStartAt: evidence.requestedEndAt,
      }).success,
    ).toBe(false);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...evidence,
        requestedStartAt: "2026-08-29T00:00:00Z",
      }).success,
    ).toBe(false);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...evidence,
        queryCompletedAt: "2026-08-27T23:59:59Z",
      }).success,
    ).toBe(false);
  });

  it("enforces history result-state reasons and nullability", () => {
    const base = {
      historyKind: "orders",
      requestedStartAt: "2026-08-27T00:00:00Z",
      requestedEndAt: "2026-08-28T00:00:00Z",
      queryCompletedAt: "2026-08-28T00:00:01Z",
      returnedCount: 0,
      earliestReturnedAt: null,
      latestReturnedAt: null,
      resultState: "empty_valid_result",
      reasonCode: "HISTORY_EMPTY_VALID_RESULT",
    };

    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...base,
        resultState: "query_succeeded",
        returnedCount: 1,
        earliestReturnedAt: "2026-08-27T12:00:00Z",
        latestReturnedAt: "2026-08-27T12:00:00Z",
        reasonCode: "HEALTHY",
      }).success,
    ).toBe(true);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...base,
        resultState: "query_succeeded",
        returnedCount: 1,
        earliestReturnedAt: "2026-08-27T12:00:00Z",
        latestReturnedAt: "2026-08-27T12:00:00Z",
      }).success,
    ).toBe(false);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...base,
        resultState: "query_failed",
        reasonCode: "HISTORY_QUERY_FAILED",
      }).success,
    ).toBe(true);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...base,
        resultState: "query_failed",
        queryCompletedAt: null,
        reasonCode: "HISTORY_QUERY_FAILED",
      }).success,
    ).toBe(false);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...base,
        resultState: "window_unknown",
        queryCompletedAt: null,
        reasonCode: "HISTORY_WINDOW_INCOMPLETE",
      }).success,
    ).toBe(true);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...base,
        resultState: "window_unknown",
        reasonCode: "HISTORY_WINDOW_INCOMPLETE",
      }).success,
    ).toBe(false);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...base,
        resultState: "window_incomplete",
        reasonCode: "HISTORY_WINDOW_INCOMPLETE",
      }).success,
    ).toBe(true);
    expect(
      Mt5HistoryQueryEvidenceSchema.safeParse({
        ...base,
        resultState: "window_incomplete",
      }).success,
    ).toBe(false);
  });

  it("requires exactly one orders and one deals evidence row when completed", () => {
    const orderEvidence = {
      historyKind: "orders",
      requestedStartAt: "2026-08-27T00:00:00Z",
      requestedEndAt: "2026-08-28T00:00:00Z",
      queryCompletedAt: "2026-08-28T00:00:01Z",
      returnedCount: 0,
      earliestReturnedAt: null,
      latestReturnedAt: null,
      resultState: "empty_valid_result",
      reasonCode: "HISTORY_EMPTY_VALID_RESULT",
    };
    const reconciliation = {
      id: "00000000-0000-4000-8000-000000000054",
      traceId: "trace-mt5",
      status: "completed",
      outcome: "matched",
      reasonCode: "HEALTHY",
      startedAt: "2026-08-28T00:00:00Z",
      completedAt: "2026-08-28T00:00:02Z",
      openPositionCount: 0,
      activeOrderCount: 0,
      mismatchCount: 0,
      mismatches: [],
      historyEvidence: [
        orderEvidence,
        { ...orderEvidence, historyKind: "deals" },
      ],
    };

    expect(
      Mt5ReconciliationReadModelSchema.safeParse(reconciliation).success,
    ).toBe(true);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...reconciliation,
        historyEvidence: [orderEvidence],
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...reconciliation,
        historyEvidence: [orderEvidence, { ...orderEvidence }],
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...reconciliation,
        outcome: null,
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...reconciliation,
        completedAt: null,
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...reconciliation,
        completedAt: "2026-08-27T23:59:59Z",
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...reconciliation,
        historyEvidence: [
          orderEvidence,
          {
            ...orderEvidence,
            historyKind: "deals",
            resultState: "query_failed",
            reasonCode: "HISTORY_QUERY_FAILED",
          },
        ],
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...reconciliation,
        reasonCode: "RECONCILIATION_INCOMPLETE",
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...reconciliation,
        mismatchCount: 1,
      }).success,
    ).toBe(false);
  });

  it("keeps a running reconciliation free of completion claims", () => {
    const running = {
      id: "00000000-0000-4000-8000-000000000054",
      traceId: "trace-mt5",
      status: "running",
      outcome: null,
      reasonCode: "RECONCILIATION_INCOMPLETE",
      startedAt: "2026-08-28T00:00:00Z",
      completedAt: null,
      openPositionCount: 0,
      activeOrderCount: 0,
      mismatchCount: 0,
      mismatches: [],
      historyEvidence: [],
    };

    expect(Mt5ReconciliationReadModelSchema.safeParse(running).success).toBe(
      true,
    );
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...running,
        outcome: "matched",
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...running,
        completedAt: "2026-08-28T00:00:01Z",
      }).success,
    ).toBe(false);
    expect(
      Mt5ReconciliationReadModelSchema.safeParse({
        ...running,
        historyEvidence: [
          {
            historyKind: "orders",
            requestedStartAt: "2026-08-27T00:00:00Z",
            requestedEndAt: "2026-08-28T00:00:00Z",
            queryCompletedAt: "2026-08-28T00:00:01Z",
            returnedCount: 0,
            earliestReturnedAt: null,
            latestReturnedAt: null,
            resultState: "empty_valid_result",
            reasonCode: "HISTORY_EMPTY_VALID_RESULT",
          },
        ],
      }).success,
    ).toBe(false);
  });
});
