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
export const Mt5SpecificationFingerprintSchema = z
  .string()
  .regex(/^mt5-spec-v1:[A-Za-z0-9:_-]{4,128}$/u);

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

export const MT5_COMPONENT_CODES = [
  "execution.worker",
  "execution.mt5_adapter",
  "execution.market_data",
] as const;
export const Mt5ComponentCodeSchema = z.enum(MT5_COMPONENT_CODES);

export const MT5_COMPONENT_HEARTBEAT_STATES = [
  "healthy",
  "degraded",
  "failed",
] as const;
export const Mt5ComponentHeartbeatStateSchema = z.enum(
  MT5_COMPONENT_HEARTBEAT_STATES,
);

export const MT5_REASON_CODES = [
  "HEALTHY",
  "MT5_PACKAGE_NOT_INSTALLED",
  "UNSUPPORTED_PLATFORM",
  "TERMINAL_PATH_NOT_CONFIGURED",
  "TERMINAL_NOT_FOUND",
  "INITIALIZE_FAILED",
  "TERMINAL_INFO_UNAVAILABLE",
  "TERMINAL_DISCONNECTED",
  "ACCOUNT_INFO_UNAVAILABLE",
  "TRADE_MODE_UNKNOWN",
  "CONTEST_ACCOUNT_BLOCKED",
  "REAL_ACCOUNT_BLOCKED",
  "ACCOUNT_BINDING_MISMATCH",
  "DEMO_ACCOUNT_UNBOUND",
  "SYMBOL_NOT_CONFIGURED",
  "SYMBOL_NOT_FOUND",
  "SYMBOL_AMBIGUOUS",
  "SYMBOL_NOT_VISIBLE",
  "SYMBOL_CANONICAL_MISMATCH",
  "SYMBOL_SPEC_INCOMPLETE",
  "SYMBOL_SPEC_CONFIRMATION_REQUIRED",
  "SYMBOL_SPEC_CHANGED",
  "TICK_UNAVAILABLE",
  "TICK_INVALID",
  "TICK_DELAYED",
  "TICK_STALE",
  "TICK_FROM_FUTURE",
  "CLOCK_DRIFT_EXCEEDED",
  "CANDLE_DATA_INVALID",
  "CANDLE_DATA_STALE",
  "HISTORY_EMPTY_VALID_RESULT",
  "HISTORY_QUERY_FAILED",
  "HISTORY_WINDOW_INCOMPLETE",
  "RECONCILIATION_INCOMPLETE",
  "DATABASE_REPORT_FAILED",
  "NATIVE_ACCESS_CONFLICT",
] as const;
export const Mt5ReasonCodeSchema = z.enum(MT5_REASON_CODES);

export const MT5_CONSOLE_DERIVED_REASON_CODES = [
  "MT5_OBSERVATION_UNAVAILABLE",
  "ACCOUNT_VERIFICATION_BLOCKED",
  "MT5_OBSERVATION_STALE",
  "RECONCILIATION_REQUIRED",
  "RECONCILIATION_PENDING",
  "SYMBOL_OBSERVATION_UNAVAILABLE",
  "SYMBOL_UNUSABLE",
  "RECONCILIATION_OBSERVATION_MISMATCH",
  "RECONCILIATION_EVIDENCE_INCOMPLETE",
] as const;
export const Mt5ConsoleReasonCodeSchema = z.enum([
  ...MT5_REASON_CODES,
  ...MT5_CONSOLE_DERIVED_REASON_CODES,
]);

export const Mt5ComponentHeartbeatSchema = z
  .strictObject({
    componentCode: Mt5ComponentCodeSchema,
    state: Mt5ComponentHeartbeatStateSchema,
    detail: Mt5ReasonCodeSchema,
    observedAt: IsoDateTimeSchema,
    validForSeconds: z.number().int().min(15).max(300),
    traceId: IdentifierSchema,
  })
  .superRefine((value, context) => {
    if ((value.state === "healthy") !== (value.detail === "HEALTHY")) {
      context.addIssue({
        code: "custom",
        path: ["detail"],
        message:
          "Healthy component state and HEALTHY detail must be reported together.",
      });
    }
    if (
      value.componentCode === "execution.market_data" &&
      ((value.state === "degraded" && value.detail !== "TICK_DELAYED") ||
        (value.state === "failed" &&
          ![
            "TICK_INVALID",
            "TICK_STALE",
            "TICK_FROM_FUTURE",
            "TICK_UNAVAILABLE",
          ].includes(value.detail)))
    ) {
      context.addIssue({
        code: "custom",
        path: ["detail"],
        message: "Market-data state requires an exact tick-freshness detail.",
      });
    }
  });

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
  "SYMBOL_SPEC_CONFIRMATION_REQUIRED",
  "SYMBOL_SPEC_CHANGED",
  "HISTORY_QUERY_FAILED",
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
  currencyBase: z.literal("XAU"),
  currencyProfit: z.literal("USD"),
  specificationFingerprint: Mt5SpecificationFingerprintSchema,
  usabilityState: z.enum(["usable", "not_visible", "incomplete", "invalid"]),
  unusableReason: Mt5ReasonCodeSchema.nullable(),
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
  reasonCode: Mt5ReasonCodeSchema.nullable(),
});

export const MT5_HISTORY_QUERY_KINDS = ["orders", "deals"] as const;
export const Mt5HistoryQueryKindSchema = z.enum(MT5_HISTORY_QUERY_KINDS);

export const MT5_HISTORY_QUERY_RESULT_STATES = [
  "query_succeeded",
  "empty_valid_result",
  "query_failed",
  "window_incomplete",
  "window_unknown",
] as const;
export const Mt5HistoryQueryResultStateSchema = z.enum(
  MT5_HISTORY_QUERY_RESULT_STATES,
);

export const Mt5HistoryQueryEvidenceSchema = z
  .strictObject({
    historyKind: Mt5HistoryQueryKindSchema,
    requestedStartAt: IsoDateTimeSchema,
    requestedEndAt: IsoDateTimeSchema,
    queryCompletedAt: IsoDateTimeSchema.nullable(),
    returnedCount: z.number().int().nonnegative(),
    earliestReturnedAt: IsoDateTimeSchema.nullable(),
    latestReturnedAt: IsoDateTimeSchema.nullable(),
    resultState: Mt5HistoryQueryResultStateSchema,
    reasonCode: Mt5ReasonCodeSchema,
  })
  .superRefine((value, context) => {
    const issue = (message: string): void => {
      context.addIssue({ code: "custom", message });
    };
    if (
      Date.parse(value.requestedEndAt) <= Date.parse(value.requestedStartAt)
    ) {
      issue("History evidence end must be after start.");
    }
    if (
      value.queryCompletedAt !== null &&
      Date.parse(value.queryCompletedAt) < Date.parse(value.requestedEndAt)
    ) {
      issue("History evidence completion must not precede the requested end.");
    }
    const hasEarliest = value.earliestReturnedAt !== null;
    const hasLatest = value.latestReturnedAt !== null;
    if (hasEarliest !== hasLatest) {
      issue("History evidence boundaries must be paired.");
    } else if (
      value.earliestReturnedAt !== null &&
      value.latestReturnedAt !== null &&
      Date.parse(value.latestReturnedAt) < Date.parse(value.earliestReturnedAt)
    ) {
      issue("History evidence boundaries are inconsistent.");
    }

    if (
      (value.resultState === "query_succeeded" ||
        value.resultState === "empty_valid_result") &&
      value.queryCompletedAt === null
    ) {
      issue("Successful history evidence requires a completion time.");
    }
    if (
      value.resultState === "query_succeeded" &&
      (value.returnedCount === 0 ||
        !hasEarliest ||
        value.reasonCode !== "HEALTHY")
    ) {
      issue(
        "Non-empty history evidence requires row boundaries and a healthy reason.",
      );
    }
    if (
      value.resultState === "empty_valid_result" &&
      (value.returnedCount !== 0 ||
        hasEarliest ||
        value.reasonCode !== "HISTORY_EMPTY_VALID_RESULT")
    ) {
      issue(
        "Empty history evidence requires an explicit valid-empty reason and no returned rows.",
      );
    }
    if (
      value.resultState === "query_failed" &&
      (value.queryCompletedAt === null ||
        value.returnedCount !== 0 ||
        hasEarliest ||
        value.reasonCode !== "HISTORY_QUERY_FAILED")
    ) {
      issue(
        "Failed history evidence must carry only bounded failure evidence.",
      );
    }
    if (
      value.resultState === "window_unknown" &&
      (value.queryCompletedAt !== null ||
        value.returnedCount !== 0 ||
        hasEarliest ||
        value.reasonCode !== "HISTORY_WINDOW_INCOMPLETE")
    ) {
      issue(
        "Unknown history evidence cannot claim completion or returned rows.",
      );
    }
    if (
      value.resultState === "window_incomplete" &&
      value.reasonCode !== "HISTORY_WINDOW_INCOMPLETE"
    ) {
      issue("Incomplete history evidence requires an incomplete reason.");
    }
  });

export const Mt5ReconciliationReadModelSchema = z
  .strictObject({
    id: UuidSchema,
    traceId: IdentifierSchema,
    status: z.enum(["running", "completed"]),
    outcome: Mt5ReconciliationOutcomeSchema.nullable(),
    reasonCode: Mt5ReasonCodeSchema,
    startedAt: IsoDateTimeSchema,
    completedAt: IsoDateTimeSchema.nullable(),
    openPositionCount: z.number().int().nonnegative(),
    activeOrderCount: z.number().int().nonnegative(),
    mismatchCount: z.number().int().nonnegative(),
    mismatches: z.array(Mt5ReconciliationMismatchSchema),
    historyEvidence: z.array(Mt5HistoryQueryEvidenceSchema).max(2),
  })
  .superRefine((value, context) => {
    if (value.status === "running") {
      if (
        value.outcome !== null ||
        value.completedAt !== null ||
        value.historyEvidence.length !== 0
      ) {
        context.addIssue({
          code: "custom",
          message:
            "A running reconciliation cannot claim an outcome, completion time, or history evidence.",
        });
      }
      return;
    }

    if (value.outcome === null || value.completedAt === null) {
      context.addIssue({
        code: "custom",
        message:
          "A completed reconciliation requires an outcome and completion time.",
      });
    } else if (Date.parse(value.completedAt) < Date.parse(value.startedAt)) {
      context.addIssue({
        code: "custom",
        path: ["completedAt"],
        message: "Reconciliation completion cannot precede its start.",
      });
    }

    const kinds = new Set(
      value.historyEvidence.map(({ historyKind }) => historyKind),
    );
    if (
      value.historyEvidence.length !== 2 ||
      kinds.size !== 2 ||
      !kinds.has("orders") ||
      !kinds.has("deals")
    ) {
      context.addIssue({
        code: "custom",
        path: ["historyEvidence"],
        message:
          "A completed reconciliation requires one orders and one deals evidence record.",
      });
    }
    if (value.mismatchCount !== value.mismatches.length) {
      context.addIssue({
        code: "custom",
        path: ["mismatchCount"],
        message:
          "Completed reconciliation mismatch count must match its evidence.",
      });
    }
    if (
      value.outcome === "matched" &&
      value.historyEvidence.some(
        ({ resultState }) =>
          resultState !== "query_succeeded" &&
          resultState !== "empty_valid_result",
      )
    ) {
      context.addIssue({
        code: "custom",
        path: ["historyEvidence"],
        message:
          "A matched reconciliation requires successful current-run history evidence.",
      });
    }
    if (
      value.outcome === "matched" &&
      (value.reasonCode !== "HEALTHY" ||
        value.mismatchCount !== 0 ||
        value.mismatches.length !== 0)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "A matched reconciliation requires a healthy reason and no mismatches.",
      });
    }
  });

export const Mt5HealthReadModelSchema = ObservationMetadataSchema.extend({
  state: Mt5HealthStateSchema,
  reasonCode: Mt5ConsoleReasonCodeSchema,
  packageAvailable: z.boolean(),
  platform: IdentifierSchema,
  terminalConnected: z.boolean(),
  terminalVersion: IdentifierSchema.nullable(),
  accountVerificationState: Mt5AccountVerificationStateSchema.nullable(),
  maskedAccount: z.string().nullable(),
  maskedServer: z.string().nullable(),
  brokerSymbol: IdentifierSchema.nullable(),
  specificationFingerprint: Mt5SpecificationFingerprintSchema.nullable(),
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
export type Mt5ComponentCode = z.infer<typeof Mt5ComponentCodeSchema>;
export type Mt5ComponentHeartbeatState = z.infer<
  typeof Mt5ComponentHeartbeatStateSchema
>;
export type Mt5ReasonCode = z.infer<typeof Mt5ReasonCodeSchema>;
export type Mt5ConsoleReasonCode = z.infer<typeof Mt5ConsoleReasonCodeSchema>;
export type Mt5ComponentHeartbeat = z.infer<typeof Mt5ComponentHeartbeatSchema>;
export type Mt5AccountReadModel = z.infer<typeof Mt5AccountReadModelSchema>;
export type Mt5SymbolReadModel = z.infer<typeof Mt5SymbolReadModelSchema>;
export type Mt5LatestTickReadModel = z.infer<
  typeof Mt5LatestTickReadModelSchema
>;
export type Mt5ReconciliationMismatch = z.infer<
  typeof Mt5ReconciliationMismatchSchema
>;
export type Mt5HistoryQueryEvidence = z.infer<
  typeof Mt5HistoryQueryEvidenceSchema
>;
export type Mt5ReconciliationReadModel = z.infer<
  typeof Mt5ReconciliationReadModelSchema
>;
export type Mt5HealthReadModel = z.infer<typeof Mt5HealthReadModelSchema>;
export type Mt5ConsoleReadModel = z.infer<typeof Mt5ConsoleReadModelSchema>;
