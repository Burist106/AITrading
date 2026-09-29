import { z } from "zod";

import { UuidSchema as BaseUuidSchema } from "./primitives";

const UuidSchema = BaseUuidSchema.length(36).regex(
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u,
);

export const ShadowTimeSchema = z
  .string()
  .datetime({ offset: true })
  .refine((value) => value.trim() === value)
  .regex(
    /^(?!0000)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/u,
  );
export function shadowTimeMicros(value: string): bigint {
  const [whole, fraction = ""] = value
    .replace(/(?:Z|\+00:00)$/u, "")
    .split(".");
  try {
    return (
      BigInt(Date.parse(`${whole}Z`)) * 1000n + BigInt(fraction.padEnd(6, "0"))
    );
  } catch {
    return 0n;
  } // Primitive validation already rejects malformed timestamps.
}

export const ShadowDecimalSchema = z
  .string()
  .min(1)
  .max(96)
  .regex(/^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/u)
  .refine((value) => value.trim() === value);
export function compareShadowDecimals(left: string, right: string): number {
  const [leftWhole = "", leftFraction = ""] = left.split(".");
  const [rightWhole = "", rightFraction = ""] = right.split(".");
  const scale = Math.max(leftFraction.length, rightFraction.length);
  try {
    const a = BigInt(leftWhole + leftFraction.padEnd(scale, "0"));
    const b = BigInt(rightWhole + rightFraction.padEnd(scale, "0"));
    return a < b ? -1 : a > b ? 1 : 0;
  } catch {
    return Number.NaN;
  } // Keeps safeParse safe for invalid primitive input.
}
const positive = ShadowDecimalSchema.refine(
  (value) => compareShadowDecimals(value, "0") > 0,
);
const digest = z
  .string()
  .length(64)
  .regex(/^[a-f0-9]{64}$/u);
const identifier = z
  .string()
  .min(1)
  .max(128)
  .regex(/^[A-Za-z0-9][A-Za-z0-9._:+/-]*$/u)
  .refine((value) => value.trim() === value);
const code = z
  .string()
  .min(1)
  .max(80)
  .regex(/^[A-Z][A-Z0-9_]*$/u)
  .refine((value) => value.trim() === value);
const checks = z
  .array(z.object({ code, passed: z.boolean() }).strict())
  .min(1)
  .max(64)
  .refine(
    (items) => new Set(items.map((item) => item.code)).size === items.length,
  );
const positiveInteger = z.number().int().positive().max(2147483647);

export const ShadowBarSchema = z
  .object({
    open_at: ShadowTimeSchema,
    open: positive,
    high: positive,
    low: positive,
    close: positive,
  })
  .strict()
  .refine(
    (bar) =>
      compareShadowDecimals(bar.low, bar.open) <= 0 &&
      compareShadowDecimals(bar.low, bar.close) <= 0 &&
      compareShadowDecimals(bar.high, bar.open) >= 0 &&
      compareShadowDecimals(bar.high, bar.close) >= 0 &&
      shadowTimeMicros(bar.open_at) % 60_000_000n === 0n,
  );

export const ShadowMarketSchema = z
  .object({
    snapshot_id: UuidSchema,
    feature_id: UuidSchema,
    reconciliation_id: UuidSchema,
    input_digest: digest,
    account_fingerprint: z
      .string()
      .length("mt5-account-v1:".length + 64)
      .regex(/^mt5-account-v1:[a-f0-9]{64}$/u),
    server_fingerprint: z
      .string()
      .length("mt5-server-v1:".length + 64)
      .regex(/^mt5-server-v1:[a-f0-9]{64}$/u),
    specification_fingerprint: z
      .string()
      .length("mt5-spec-v1:".length + 64)
      .regex(/^mt5-spec-v1:[a-f0-9]{64}$/u),
    adapter_version: identifier,
    market_adapter_version: identifier,
    market_time_policy: identifier,
    broker_symbol: identifier,
    captured_at: ShadowTimeSchema,
    tick_at: ShadowTimeSchema,
    last_bar_closed_at: ShadowTimeSchema,
    bid: positive,
    ask: positive,
    point: positive,
    tick_size: positive,
    fast_sma: positive,
    slow_sma: positive,
    atr: ShadowDecimalSchema,
    bars: z.array(ShadowBarSchema).length(6),
  })
  .strict()
  .superRefine((market, context) => {
    const captured = shadowTimeMicros(market.captured_at);
    const tick = shadowTimeMicros(market.tick_at);
    const lastClosed = shadowTimeMicros(market.last_bar_closed_at);
    const bars = market.bars.map((bar) => shadowTimeMicros(bar.open_at));
    if (
      bars.length !== 6 ||
      compareShadowDecimals(market.ask, market.bid) < 0 ||
      tick > captured ||
      captured - tick > 5_000_000n ||
      lastClosed > captured ||
      captured - lastClosed >= 60_000_000n ||
      bars.some(
        (time, index) =>
          time % 60_000_000n !== 0n ||
          (index > 0 && time !== bars[index - 1]! + 60_000_000n),
      ) ||
      bars[5]! + 60_000_000n !== lastClosed
    ) {
      context.addIssue({
        code: "custom",
        message: "Incoherent or incomplete market evidence.",
      });
    }
  });

export const ShadowCandidateSchema = z
  .object({
    id: UuidSchema,
    direction: z.enum(["BUY", "SELL"]),
    created_at: ShadowTimeSchema,
    expires_at: ShadowTimeSchema,
    entry_price: positive,
    stop_loss_price: positive,
    take_profit_price: positive,
  })
  .strict()
  .refine((candidate) => {
    const duration =
      shadowTimeMicros(candidate.expires_at) -
      shadowTimeMicros(candidate.created_at);
    const sign = candidate.direction === "BUY" ? 1 : -1;
    return (
      duration > 0n &&
      duration <= 30_000_000n &&
      compareShadowDecimals(
        candidate.entry_price,
        candidate.stop_loss_price,
      ) === sign &&
      compareShadowDecimals(
        candidate.take_profit_price,
        candidate.entry_price,
      ) === sign
    );
  });

export const ShadowRiskSchema = z
  .object({
    version: z.literal("shadow-risk-v1"),
    input_digest: digest,
    source_receipts: z
      .array(
        z
          .object({
            kind: z.enum(["ledger", "safety", "news", "costs"]),
            source_id: identifier,
            source_version: identifier,
            evidence_digest: digest,
            observed_at: ShadowTimeSchema,
            valid_until: ShadowTimeSchema,
            covered_from: ShadowTimeSchema.nullable(),
            covered_until: ShadowTimeSchema.nullable(),
          })
          .strict()
          .refine(
            (receipt) =>
              shadowTimeMicros(receipt.observed_at) <=
                shadowTimeMicros(receipt.valid_until) &&
              ((receipt.covered_from === null &&
                receipt.covered_until === null) ||
                (receipt.covered_from !== null &&
                  receipt.covered_until !== null &&
                  shadowTimeMicros(receipt.covered_from) <=
                    shadowTimeMicros(receipt.covered_until))),
          ),
      )
      .max(4)
      .refine(
        (receipts) =>
          new Set(receipts.map((receipt) => receipt.kind)).size ===
          receipts.length,
      ),
    outcome: z.enum(["PASS", "BLOCK"]),
    checks,
    calculated_volume: positive.nullable(),
    estimated_loss_usd: positive.nullable(),
    estimated_net_reward_usd: positive.nullable(),
  })
  .strict()
  .refine((risk) => {
    const passed = risk.outcome === "PASS";
    return (
      (!passed || risk.source_receipts.length === 4) &&
      passed === risk.checks.every((check) => check.passed) &&
      (passed
        ? risk.calculated_volume !== null &&
          compareShadowDecimals(risk.calculated_volume, "0.01") <= 0 &&
          risk.estimated_loss_usd !== null &&
          risk.estimated_net_reward_usd !== null
        : risk.calculated_volume === null &&
          risk.estimated_loss_usd === null &&
          risk.estimated_net_reward_usd === null)
    );
  });

export const ShadowEligibilitySchema = z
  .object({
    outcome: z.enum(["PASS", "BLOCK"]),
    checks,
    sample_count: z.number().int().nonnegative().max(2147483647),
    minimum_sample_size: z.number().int().min(30).max(2147483647),
    calibrated: z.literal(false),
  })
  .strict()
  .refine(
    (eligibility) =>
      (eligibility.outcome === "PASS") ===
        eligibility.checks.every((check) => check.passed) &&
      eligibility.checks.some(
        (check) =>
          check.code === "SAMPLE_SIZE" &&
          check.passed ===
            eligibility.sample_count >= eligibility.minimum_sample_size,
      ),
  );

export const ShadowCycleSchema = z
  .object({
    schema_version: z.literal("shadow-cycle-v1"),
    pipeline_version: z.literal("shadow-pipeline-v1"),
    strategy_version: z.literal("sma-atr-shadow-v1"),
    eligibility_version: z.literal("shadow-eligibility-v1"),
    id: UuidSchema,
    owner_id: UuidSchema,
    trading_account_id: UuidSchema,
    trace_id: UuidSchema,
    cycle_key: digest,
    evaluated_at: ShadowTimeSchema,
    environment: z.literal("DEMO_ONLY"),
    runtime_mode: z.literal("SHADOW"),
    source: z.literal("mt5"),
    grants_eligibility: z.literal(false),
    status: z.enum(["WAIT", "BLOCK", "PROPOSAL"]),
    reason_codes: z
      .array(code)
      .min(1)
      .max(32)
      .refine((items) => new Set(items).size === items.length),
    policy_version_id: UuidSchema.nullable(),
    policy_version: positiveInteger.nullable(),
    mode_version: positiveInteger.nullable(),
    market: ShadowMarketSchema.nullable(),
    candidate: ShadowCandidateSchema.nullable(),
    risk: ShadowRiskSchema.nullable(),
    eligibility: ShadowEligibilitySchema.nullable(),
  })
  .strict()
  .superRefine((cycle, context) => {
    if (
      (cycle.policy_version_id === null) !== (cycle.policy_version === null) ||
      (cycle.candidate !== null && cycle.market === null) ||
      (cycle.risk?.outcome === "PASS" &&
        cycle.risk.source_receipts.some(
          (receipt) =>
            shadowTimeMicros(receipt.observed_at) >
              shadowTimeMicros(cycle.evaluated_at) ||
            shadowTimeMicros(receipt.valid_until) <
              shadowTimeMicros(cycle.evaluated_at),
        )) ||
      (cycle.status === "WAIT" &&
        (cycle.candidate !== null || cycle.risk !== null)) ||
      (cycle.status === "PROPOSAL" &&
        (cycle.market === null ||
          cycle.candidate === null ||
          cycle.risk?.outcome !== "PASS" ||
          cycle.eligibility === null ||
          cycle.policy_version_id === null ||
          cycle.policy_version === null ||
          cycle.mode_version === null)) ||
      (cycle.risk !== null &&
        (cycle.market === null || cycle.candidate === null)) ||
      (cycle.market !== null &&
        (shadowTimeMicros(cycle.market.captured_at) >
          shadowTimeMicros(cycle.evaluated_at) ||
          shadowTimeMicros(cycle.evaluated_at) -
            shadowTimeMicros(cycle.market.captured_at) >
            5_000_000n)) ||
      (cycle.candidate !== null &&
        (shadowTimeMicros(cycle.candidate.created_at) !==
          shadowTimeMicros(cycle.evaluated_at) ||
          shadowTimeMicros(cycle.candidate.expires_at) <=
            shadowTimeMicros(cycle.evaluated_at)))
    ) {
      context.addIssue({
        code: "custom",
        message: "Incoherent Shadow cycle evidence.",
      });
    }
  });
export type ShadowCycle = z.infer<typeof ShadowCycleSchema>;

export const ShadowOutcomeSchema = z
  .object({
    schema_version: z.literal("shadow-outcome-v1"),
    tracker_version: z.literal("quote-observed-v1"),
    simulation: z.literal(true),
    grants_eligibility: z.literal(false),
    id: UuidSchema,
    owner_id: UuidSchema,
    trading_account_id: UuidSchema,
    cycle_id: UuidSchema,
    sequence: positiveInteger.max(32),
    observed_at: ShadowTimeSchema,
    status: z.enum([
      "OBSERVED",
      "STOP_OBSERVED",
      "TARGET_OBSERVED",
      "EXPIRED",
      "UNKNOWN",
    ]),
    reason_code: code,
    bid: positive.nullable(),
    ask: positive.nullable(),
    price_source: z.enum(["mt5", "unavailable"]),
    net_pnl_usd: z.null(),
  })
  .strict()
  .refine(
    (event) =>
      (event.sequence !== 32 || event.status !== "OBSERVED") &&
      (event.price_source === "unavailable"
        ? event.bid === null && event.ask === null && event.status === "UNKNOWN"
        : event.bid !== null &&
          event.ask !== null &&
          compareShadowDecimals(event.ask, event.bid) >= 0),
  );
export type ShadowOutcome = z.infer<typeof ShadowOutcomeSchema>;
