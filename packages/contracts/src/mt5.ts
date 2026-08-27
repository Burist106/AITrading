import { z } from "zod";

import { IdentifierSchema, IsoDateTimeSchema, UuidSchema } from "./primitives";

export const DecimalStringSchema = z
  .string()
  .regex(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/u);
export const NonNegativeDecimalStringSchema = DecimalStringSchema.refine(
  (value) => !value.startsWith("-"),
  "Expected a non-negative decimal string",
);
export const PositiveDecimalStringSchema =
  NonNegativeDecimalStringSchema.refine(
    (value) => /[1-9]/u.test(value),
    "Expected a positive decimal string",
  );
export const TicketIdentifierSchema = z.string().regex(/^[0-9]{1,32}$/u);

export const MT5_ACCOUNT_VERIFICATION_STATES = [
  "verified_demo_bound",
  "verified_demo_unbound",
  "account_info_unavailable",
  "trade_mode_unknown",
  "contest_account_blocked",
  "real_account_blocked",
  "account_binding_mismatch",
] as const;
export const Mt5AccountVerificationStateSchema = z.enum(
  MT5_ACCOUNT_VERIFICATION_STATES,
);

export const MT5_HEALTH_STATES = [
  "healthy",
  "degraded",
  "blocked",
  "unavailable",
] as const;
export const Mt5HealthStateSchema = z.enum(MT5_HEALTH_STATES);

export const MT5_TICK_FRESHNESS_STATES = [
  "live",
  "delayed",
  "stale",
  "future_invalid",
  "unavailable",
] as const;
export const Mt5TickFreshnessSchema = z.enum(MT5_TICK_FRESHNESS_STATES);

export const MT5_RECONCILIATION_OUTCOMES = [
  "matched",
  "mismatch",
  "incomplete",
] as const;
export const Mt5ReconciliationOutcomeSchema = z.enum(
  MT5_RECONCILIATION_OUTCOMES,
);

export const MT5_RECONCILIATION_CATEGORIES = [
  "UNEXPECTED_BROKER_POSITION",
  "DATABASE_POSITION_MISSING_AT_BROKER",
  "UNEXPECTED_ACTIVE_ORDER",
  "DATABASE_ORDER_MISSING_AT_BROKER",
  "EXECUTION_RESULT_UNCERTAIN",
  "ACCOUNT_CHANGED",
  "SERVER_CHANGED",
  "SYMBOL_SPEC_CHANGED",
  "HISTORY_WINDOW_INCOMPLETE",
  "CLOCK_INCONSISTENCY",
] as const;
export const Mt5ReconciliationCategorySchema = z.enum(
  MT5_RECONCILIATION_CATEGORIES,
);

const ObservationMetadataSchema = z.strictObject({
  observedAt: IsoDateTimeSchema,
  source: z.enum(["mt5", "fake_mt5"]),
  adapterVersion: IdentifierSchema,
  traceId: IdentifierSchema,
  schemaVersion: z.literal("1"),
});

export const Mt5AccountReadModelSchema = ObservationMetadataSchema.extend({
  tradeMode: z.enum(["demo", "contest", "real", "unknown"]),
  verificationState: Mt5AccountVerificationStateSchema,
  maskedLogin: z.string().regex(/^••••[0-9]{0,4}$/u),
  maskedServer: z.string().min(5).max(32),
  accountFingerprint: z.string().startsWith("mt5-account-v1:"),
  serverFingerprint: z.string().startsWith("mt5-server-v1:"),
}).strict();

export const Mt5SymbolReadModelSchema = ObservationMetadataSchema.extend({
  canonicalSymbol: z.literal("XAUUSD"),
  brokerSymbol: IdentifierSchema,
  specificationFingerprint: z.string().startsWith("mt5-spec-v1:"),
  usabilityState: z.enum(["usable", "not_visible", "incomplete", "invalid"]),
  unusableReason: IdentifierSchema.nullable(),
  point: PositiveDecimalStringSchema,
  tickSize: PositiveDecimalStringSchema,
  contractSize: PositiveDecimalStringSchema,
  minimumVolume: PositiveDecimalStringSchema,
  maximumVolume: PositiveDecimalStringSchema,
  volumeStep: PositiveDecimalStringSchema,
}).strict();

export const Mt5LatestTickReadModelSchema = ObservationMetadataSchema.extend({
  symbol: IdentifierSchema,
  bid: PositiveDecimalStringSchema,
  ask: PositiveDecimalStringSchema,
  spreadPrice: NonNegativeDecimalStringSchema,
  spreadPoints: NonNegativeDecimalStringSchema,
  tickAt: IsoDateTimeSchema,
  ageSeconds: NonNegativeDecimalStringSchema,
  freshness: Mt5TickFreshnessSchema,
}).strict();

export const Mt5ReconciliationMismatchSchema = z.strictObject({
  category: Mt5ReconciliationCategorySchema,
  severity: z.enum(["warning", "critical"]),
  resourceType: IdentifierSchema,
  resourceReference: IdentifierSchema,
  reasonCode: IdentifierSchema.nullable(),
});

export const Mt5ReconciliationReadModelSchema = z.strictObject({
  id: UuidSchema,
  traceId: IdentifierSchema,
  status: z.enum(["running", "completed"]),
  outcome: Mt5ReconciliationOutcomeSchema.nullable(),
  reasonCode: IdentifierSchema,
  startedAt: IsoDateTimeSchema,
  completedAt: IsoDateTimeSchema.nullable(),
  openPositionCount: z.number().int().nonnegative(),
  activeOrderCount: z.number().int().nonnegative(),
  mismatchCount: z.number().int().nonnegative(),
  mismatches: z.array(Mt5ReconciliationMismatchSchema),
});

export const Mt5HealthReadModelSchema = ObservationMetadataSchema.extend({
  state: Mt5HealthStateSchema,
  reasonCode: IdentifierSchema,
  packageAvailable: z.boolean(),
  platform: IdentifierSchema,
  terminalConnected: z.boolean(),
  terminalVersion: IdentifierSchema.nullable(),
  accountVerificationState: Mt5AccountVerificationStateSchema.nullable(),
  maskedAccount: z.string().nullable(),
  maskedServer: z.string().nullable(),
  brokerSymbol: IdentifierSchema.nullable(),
  specificationFingerprint: z.string().nullable(),
  tickAgeSeconds: NonNegativeDecimalStringSchema.nullable(),
  lastCompletedCandleAt: IsoDateTimeSchema.nullable(),
  lastSuccessfulObservationAt: IsoDateTimeSchema.nullable(),
  reconciliationOutcome: Mt5ReconciliationOutcomeSchema.nullable(),
  openPositionCount: z.number().int().nonnegative().nullable(),
  activeOrderCount: z.number().int().nonnegative().nullable(),
}).strict();

export const Mt5ConsoleReadModelSchema = z.strictObject({
  account: Mt5AccountReadModelSchema.nullable(),
  symbol: Mt5SymbolReadModelSchema.nullable(),
  tick: Mt5LatestTickReadModelSchema.nullable(),
  reconciliation: Mt5ReconciliationReadModelSchema.nullable(),
  health: Mt5HealthReadModelSchema,
});

export type DecimalString = z.infer<typeof DecimalStringSchema>;
export type Mt5AccountReadModel = z.infer<typeof Mt5AccountReadModelSchema>;
export type Mt5SymbolReadModel = z.infer<typeof Mt5SymbolReadModelSchema>;
export type Mt5LatestTickReadModel = z.infer<
  typeof Mt5LatestTickReadModelSchema
>;
export type Mt5ReconciliationMismatch = z.infer<
  typeof Mt5ReconciliationMismatchSchema
>;
export type Mt5ReconciliationReadModel = z.infer<
  typeof Mt5ReconciliationReadModelSchema
>;
export type Mt5HealthReadModel = z.infer<typeof Mt5HealthReadModelSchema>;
export type Mt5ConsoleReadModel = z.infer<typeof Mt5ConsoleReadModelSchema>;
