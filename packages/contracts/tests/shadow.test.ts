import { describe, expect, it } from "vitest";
import parity from "../../../contract-fixtures/v1/shadow-parity.json";

import {
  ShadowBarSchema,
  ShadowCandidateSchema,
  ShadowCycleSchema,
  ShadowDecimalSchema,
  ShadowEligibilitySchema,
  ShadowMarketSchema,
  ShadowOutcomeSchema,
  ShadowRiskSchema,
  ShadowTimeSchema,
  compareShadowDecimals,
  shadowTimeMicros,
} from "../src/shadow";

const id = "11111111-1111-4111-8111-111111111111";
const time = "2026-09-22T10:00:01Z";
const block = {
  schema_version: "shadow-cycle-v1",
  pipeline_version: "shadow-pipeline-v1",
  strategy_version: "sma-atr-shadow-v1",
  eligibility_version: "shadow-eligibility-v1",
  id,
  owner_id: id,
  trading_account_id: id,
  trace_id: id,
  cycle_key: "a".repeat(64),
  evaluated_at: time,
  environment: "DEMO_ONLY",
  runtime_mode: "SHADOW",
  source: "mt5",
  grants_eligibility: false,
  status: "BLOCK",
  reason_codes: ["CONTEXT_UNAVAILABLE"],
  policy_version_id: null,
  policy_version: null,
  mode_version: null,
  market: null,
  candidate: null,
  risk: null,
  eligibility: null,
};
const candidate = {
  id,
  direction: "BUY",
  created_at: time,
  expires_at: "2026-09-22T10:00:31Z",
  entry_price: "2000",
  stop_loss_price: "1990",
  take_profit_price: "2030",
};
const market = {
  snapshot_id: id,
  feature_id: id,
  reconciliation_id: id,
  input_digest: "a".repeat(64),
  account_fingerprint: `mt5-account-v1:${"a".repeat(64)}`,
  server_fingerprint: `mt5-server-v1:${"b".repeat(64)}`,
  specification_fingerprint: `mt5-spec-v1:${"c".repeat(64)}`,
  adapter_version: "native-v1",
  market_adapter_version: "native-v1:utc_epoch_v1",
  market_time_policy: "utc_epoch_v1",
  broker_symbol: "XAUUSD",
  captured_at: time,
  tick_at: time,
  last_bar_closed_at: "2026-09-22T10:00:00Z",
  bid: "1999",
  ask: "2000",
  point: "0.01",
  tick_size: "0.01",
  fast_sma: "1999",
  slow_sma: "1998",
  atr: "5",
  bars: Array.from({ length: 6 }, (_, index) => ({
    open_at: `2026-09-22T09:${54 + index}:00Z`,
    open: "1998",
    high: "2001",
    low: "1997",
    close: "2000",
  })),
};
const risk = {
  version: "shadow-risk-v1",
  input_digest: "d".repeat(64),
  source_receipts: ["ledger", "safety", "news", "costs"].map((kind) => ({
    kind,
    source_id: "reviewed-source",
    source_version: "v1",
    evidence_digest: "e".repeat(64),
    observed_at: time,
    valid_until: "2026-09-22T10:00:30Z",
    covered_from: null,
    covered_until: null,
  })),
  outcome: "PASS",
  checks: [{ code: "SAFE", passed: true }],
  calculated_volume: "0.01",
  estimated_loss_usd: "10",
  estimated_net_reward_usd: "29",
};
const eligibility = {
  outcome: "BLOCK",
  checks: [{ code: "SAMPLE_SIZE", passed: false }],
  sample_count: 0,
  minimum_sample_size: 30,
  calibrated: false,
};
const proposal = {
  ...block,
  status: "PROPOSAL",
  policy_version_id: id,
  policy_version: 1,
  mode_version: 1,
  market,
  candidate,
  risk,
  eligibility,
};
const event = {
  schema_version: "shadow-outcome-v1",
  tracker_version: "quote-observed-v1",
  simulation: true,
  grants_eligibility: false,
  id,
  owner_id: id,
  trading_account_id: id,
  cycle_id: id,
  sequence: 1,
  observed_at: "2026-09-22T10:00:02Z",
  status: "UNKNOWN",
  reason_code: "SOURCE_UNAVAILABLE",
  bid: null,
  ask: null,
  price_source: "unavailable",
  net_pnl_usd: null,
};

describe("Shadow wire v1", () => {
  it("does not accept trailing newlines through JavaScript end anchors", () => {
    expect(
      ShadowCycleSchema.safeParse({ ...block, reason_codes: ["BLOCKED\n"] })
        .success,
    ).toBe(false);
    expect(
      ShadowCycleSchema.safeParse({
        ...block,
        cycle_key: `${block.cycle_key}\n`,
      }).success,
    ).toBe(false);
    expect(ShadowTimeSchema.safeParse(`${time}\n`).success).toBe(false);
    expect(
      ShadowMarketSchema.safeParse({
        ...market,
        adapter_version: "native-v1\n",
      }).success,
    ).toBe(false);
    expect(
      ShadowMarketSchema.safeParse({
        ...market,
        account_fingerprint: `${market.account_fingerprint}\n`,
      }).success,
    ).toBe(false);
  });
  it("accepts the shared production-pipeline wire examples", () => {
    expect(ShadowCycleSchema.safeParse(parity.cycle).success).toBe(true);
    expect(ShadowOutcomeSchema.safeParse(parity.outcome).success).toBe(true);
  });
  it.each(parity.mutations)(
    "matches Python/SQL shared parity: $name",
    (mutation) => {
      const value = structuredClone(
        mutation.target === "cycle" ? parity.cycle : parity.outcome,
      );
      let current = value as unknown as Record<string, unknown>;
      for (const part of mutation.path.slice(0, -1))
        current = current[part] as Record<string, unknown>;
      const key = mutation.path.at(-1)!;
      if ("remove" in mutation && mutation.remove) delete current[key];
      else if ("value" in mutation) current[key] = mutation.value;
      const schema =
        mutation.target === "cycle" ? ShadowCycleSchema : ShadowOutcomeSchema;
      expect(schema.safeParse(value).success).toBe(mutation.valid);
    },
  );
  it("accepts honest missing evidence and non-executable proposals with blocked eligibility", () => {
    expect(ShadowCycleSchema.safeParse(block).success).toBe(true);
    expect(ShadowCycleSchema.safeParse(proposal).success).toBe(true);
    expect(ShadowOutcomeSchema.safeParse(event).success).toBe(true);
  });
  it.each(Object.keys(block))("requires cycle field %s", (key) => {
    const value: Record<string, unknown> = { ...block };
    delete value[key];
    expect(ShadowCycleSchema.safeParse(value).success).toBe(false);
  });
  it.each([
    "1e3",
    "NaN",
    "Infinity",
    "-1",
    "+1",
    "01",
    "1.",
    ".1",
    "1".repeat(97),
    " 1",
    "1\n",
  ])("rejects unsafe decimal %s", (value) => {
    expect(ShadowDecimalSchema.safeParse(value).success).toBe(false);
    expect(() =>
      ShadowCandidateSchema.safeParse({ ...candidate, entry_price: value }),
    ).not.toThrow();
  });
  it("compares decimal and timestamp boundaries without floating-point loss", () => {
    expect(compareShadowDecimals("0.01000000000000000000001", "0.01")).toBe(1);
    expect(
      shadowTimeMicros("2026-09-22T10:00:00.000001Z") -
        shadowTimeMicros("2026-09-22T10:00:00+00:00"),
    ).toBe(1n);
  });
  it.each([
    "2026-09-22T10:00:00.1234567Z",
    "2026-09-22T10:00:00+07:00",
    "2026-09-22T10:00:00",
    "2026-02-30T10:00:00Z",
  ])("rejects noncanonical time %s", (value) => {
    expect(ShadowTimeSchema.safeParse(value).success).toBe(false);
    expect(() =>
      ShadowCandidateSchema.safeParse({ ...candidate, created_at: value }),
    ).not.toThrow();
  });
  it.each(["Z", ".1Z", ".123456Z", "+00:00", ".123456+00:00"])(
    "preserves UTC precision %s",
    (suffix) => {
      expect(
        ShadowTimeSchema.safeParse(`2026-09-22T10:00:00${suffix}`).success,
      ).toBe(true);
    },
  );
  it.each([
    { source: "fake_mt5" },
    { grants_eligibility: 0 },
    { grants_eligibility: true },
    { status: "APPROVED" },
    { environment: "LIVE" },
    { extra: "data" },
    { policy_version_id: id },
    { reason_codes: ["DUPLICATE", "DUPLICATE"] },
    { policy_version: 1.2 },
  ])("rejects unsafe cycle mutation %j", (mutation) => {
    expect(ShadowCycleSchema.safeParse({ ...block, ...mutation }).success).toBe(
      false,
    );
  });
  it.each([
    { market: null },
    { candidate: null },
    { risk: null },
    { eligibility: null },
    { mode_version: null },
    { evaluated_at: "2026-09-22T10:00:07Z" },
    { candidate: { ...candidate, created_at: "2026-09-22T10:00:00Z" } },
    { risk: { ...risk, calculated_volume: "0.01000000000000000000001" } },
    { risk: { ...risk, checks: [{ code: "SAFE", passed: false }] } },
  ])("requires coherent proposal evidence %j", (mutation) => {
    expect(
      ShadowCycleSchema.safeParse({ ...proposal, ...mutation }).success,
    ).toBe(false);
  });
  it("WAIT cannot contain a candidate or risk", () => {
    expect(
      ShadowCycleSchema.safeParse({ ...block, status: "WAIT" }).success,
    ).toBe(true);
    expect(
      ShadowCycleSchema.safeParse({ ...proposal, status: "WAIT" }).success,
    ).toBe(false);
  });
  it.each([
    { ask: "1998" },
    { tick_at: "2026-09-22T09:59:55Z" },
    { tick_at: "2026-09-22T10:00:02Z" },
    { bars: market.bars.slice(1) },
    { bars: [...market.bars.slice(0, 5), market.bars[0]] },
    { last_bar_closed_at: "2026-09-22T09:59:00Z" },
    { account_fingerprint: "a".repeat(64) },
    { extra: true },
  ])("rejects invalid market evidence %j", (mutation) => {
    expect(
      ShadowMarketSchema.safeParse({ ...market, ...mutation }).success,
    ).toBe(false);
  });
  it("validates strict nested shapes and directional SL/TP", () => {
    expect(
      ShadowBarSchema.safeParse({ ...market.bars[0], high: "1990" }).success,
    ).toBe(false);
    expect(
      ShadowBarSchema.safeParse({ ...market.bars[0], extra: true }).success,
    ).toBe(false);
    expect(
      ShadowCandidateSchema.safeParse({ ...candidate, direction: "SELL" })
        .success,
    ).toBe(false);
    expect(
      ShadowCandidateSchema.safeParse({
        ...candidate,
        expires_at: "2026-09-22T10:00:31.000001Z",
      }).success,
    ).toBe(false);
    expect(
      ShadowCandidateSchema.safeParse({ ...candidate, extra: true }).success,
    ).toBe(false);
    expect(
      ShadowRiskSchema.safeParse({
        ...risk,
        checks: [{ code: "SAFE", passed: 1 }],
      }).success,
    ).toBe(false);
    expect(
      ShadowRiskSchema.safeParse({
        ...risk,
        checks: [{ code: "SAFE", passed: true, override: true }],
      }).success,
    ).toBe(false);
  });
  it("BLOCK risk contains no calculated amounts", () => {
    expect(
      ShadowRiskSchema.safeParse({
        ...risk,
        outcome: "BLOCK",
        checks: [{ code: "SAFE", passed: false }],
      }).success,
    ).toBe(false);
  });
  it("PASS requires four unique source receipts and a risk input digest", () => {
    expect(
      ShadowRiskSchema.safeParse({ ...risk, source_receipts: [] }).success,
    ).toBe(false);
    expect(
      ShadowRiskSchema.safeParse({
        ...risk,
        source_receipts: Array(4).fill(risk.source_receipts[0]),
      }).success,
    ).toBe(false);
    expect(
      ShadowRiskSchema.safeParse({ ...risk, input_digest: "invalid" }).success,
    ).toBe(false);
    expect(
      ShadowRiskSchema.safeParse({
        ...risk,
        source_receipts: risk.source_receipts.map((receipt) => ({
          ...receipt,
          covered_until: time,
        })),
      }).success,
    ).toBe(false);
  });
  it.each([
    { calibrated: 0 },
    { sample_count: 30 },
    { checks: [{ code: "OTHER", passed: false }] },
    { minimum_sample_size: 29 },
    { sample_count: -1 },
    { extra: true },
  ])("does not fabricate sample evidence %j", (mutation) => {
    expect(
      ShadowEligibilitySchema.safeParse({ ...eligibility, ...mutation })
        .success,
    ).toBe(false);
  });
  it.each([
    { simulation: 1 },
    { grants_eligibility: 0 },
    { net_pnl_usd: "0" },
    { bid: "2000" },
    { status: "TARGET_OBSERVED" },
    { sequence: 0 },
    { extra: true },
  ])("rejects unsafe outcome %j", (mutation) => {
    expect(
      ShadowOutcomeSchema.safeParse({ ...event, ...mutation }).success,
    ).toBe(false);
  });
});
