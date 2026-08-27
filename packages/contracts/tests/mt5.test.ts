import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  DecimalStringSchema,
  Mt5AccountReadModelSchema,
  Mt5LatestTickReadModelSchema,
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
});
