import { z } from "zod";

import {
  IdentifierSchema,
  IsoDateTimeSchema,
  NonNegativeNumberSchema,
  UuidSchema,
} from "./primitives";

export const RISK_POLICY_NUMERIC_RULE_KEYS = [
  "risk_per_trade_pct",
  "daily_loss_limit_pct",
  "weekly_loss_limit_pct",
  "maximum_drawdown_pct",
  "maximum_trades_per_day",
  "minimum_risk_reward",
  "stale_data_max_age_seconds",
  "maximum_spread_points",
  "news_blackout_minutes",
] as const;

export const RiskPolicyNumericRuleKeySchema = z.enum(
  RISK_POLICY_NUMERIC_RULE_KEYS,
);
export type RiskPolicyNumericRuleKey = z.infer<
  typeof RiskPolicyNumericRuleKeySchema
>;

export const RISK_POLICY_ACTOR_TYPES = ["user", "worker", "system"] as const;
export const RiskPolicyActorTypeSchema = z.enum(RISK_POLICY_ACTOR_TYPES);

export function riskPolicyRuleValueIssue(
  ruleKey: RiskPolicyNumericRuleKey,
  newValue: number,
): string | undefined {
  switch (ruleKey) {
    case "risk_per_trade_pct":
      return newValue <= 0.25 ? undefined : "must be at most 0.25";
    case "daily_loss_limit_pct":
      return newValue <= 1 ? undefined : "must be at most 1";
    case "weekly_loss_limit_pct":
      return newValue <= 3 ? undefined : "must be at most 3";
    case "maximum_drawdown_pct":
      return newValue <= 5 ? undefined : "must be at most 5";
    case "maximum_trades_per_day":
      return Number.isInteger(newValue) && newValue <= 3
        ? undefined
        : "must be an integer at most 3";
    case "minimum_risk_reward":
      return newValue >= 1.5 && newValue <= 9999.9999
        ? undefined
        : "must be between 1.5 and 9999.9999";
    case "stale_data_max_age_seconds":
      return Number.isInteger(newValue) && newValue <= 10
        ? undefined
        : "must be an integer at most 10";
    case "maximum_spread_points":
      return newValue <= 3.5 ? undefined : "must be at most 3.5";
    case "news_blackout_minutes":
      return Number.isInteger(newValue) &&
        newValue >= 15 &&
        newValue <= 2_147_483_647
        ? undefined
        : "must be an integer between 15 and 2147483647";
  }
}

/**
 * Immutable, versioned Demo policy snapshot sent across the Worker boundary.
 * Database authorization decides activation; this shape cannot weaken the fixed
 * account, asset, volume, Position-count, Stop Loss, or anti-martingale rules.
 */
export const RiskPolicyVersionSchema = z
  .object({
    id: UuidSchema,
    ownerId: UuidSchema,
    riskPolicyId: UuidSchema,
    tradingAccountId: UuidSchema,
    version: z.number().int().positive(),
    versionLabel: IdentifierSchema,
    sourceCommandId: UuidSchema.nullable(),
    environment: z.literal("DEMO_ONLY"),
    canonicalSymbol: z.literal("XAUUSD"),
    maximumPermittedVolume: z.literal(0.01),
    maximumOpenPositions: z.literal(1),
    stopLossRequired: z.literal(true),
    martingaleAllowed: z.literal(false),
    gridTradingAllowed: z.literal(false),
    averagingDownAllowed: z.literal(false),
    lossBasedVolumeIncreaseAllowed: z.literal(false),
    riskPerTradePct: NonNegativeNumberSchema.max(0.25),
    dailyLossLimitPct: NonNegativeNumberSchema.max(1),
    weeklyLossLimitPct: NonNegativeNumberSchema.max(3),
    maximumDrawdownPct: NonNegativeNumberSchema.max(5),
    maximumTradesPerDay: z.number().int().nonnegative().max(3),
    minimumRiskReward: NonNegativeNumberSchema.min(1.5).max(9999.9999),
    staleDataMaxAgeSeconds: z.number().int().nonnegative().max(10),
    maximumSpreadPoints: NonNegativeNumberSchema.max(3.5),
    spreadWarningPoints: NonNegativeNumberSchema,
    newsBlackoutMinutes: z.number().int().min(15).max(2_147_483_647),
    proposalExpirySeconds: z.number().int().positive().max(30),
    entryTolerancePoints: NonNegativeNumberSchema.max(0.6),
    minimumSampleSize: z.number().int().min(30),
    requireCalibratedModel: z.literal(false),
    maximumSlippagePoints: NonNegativeNumberSchema.max(0.5),
    automaticRetryOnBrokerReject: z.literal(false),
    reason: IdentifierSchema,
    createdByType: RiskPolicyActorTypeSchema,
    createdBy: IdentifierSchema,
    createdAt: IsoDateTimeSchema,
  })
  .strict()
  .refine(
    (policy) => policy.spreadWarningPoints <= policy.maximumSpreadPoints,
    {
      path: ["spreadWarningPoints"],
      message: "Spread warning must not exceed the maximum spread.",
    },
  );

export type RiskPolicyVersion = z.infer<typeof RiskPolicyVersionSchema>;
