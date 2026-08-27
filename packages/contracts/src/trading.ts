import { z } from "zod";

import { EligibilityPolicyResultSchema } from "./eligibility";
import {
  CurrencyCodeSchema,
  IdentifierSchema,
  IsoDateTimeSchema,
  PositiveNumberSchema,
  UuidSchema,
  isBefore,
} from "./primitives";

export const BrokerSymbolSpecificationSchema = z
  .object({
    canonicalSymbol: z.literal("XAUUSD"),
    brokerSymbol: IdentifierSchema,
    specificationVersion: IdentifierSchema,
    accountCurrency: CurrencyCodeSchema,
    contractSize: PositiveNumberSchema,
    digits: z.number().int().nonnegative(),
    pointSize: PositiveNumberSchema,
    tickSize: PositiveNumberSchema,
    tickValue: PositiveNumberSchema.nullable(),
    minimumVolume: PositiveNumberSchema,
    maximumVolume: PositiveNumberSchema,
    volumeStep: PositiveNumberSchema,
    stopLevel: z.number().int().nonnegative(),
    calculationMode: IdentifierSchema,
    fetchedAt: IsoDateTimeSchema,
  })
  .strict()
  .refine(
    (specification) =>
      specification.minimumVolume <= specification.maximumVolume,
    {
      path: ["minimumVolume"],
      message: "Broker minimum volume cannot exceed broker maximum volume.",
    },
  );

export type BrokerSymbolSpecification = z.infer<
  typeof BrokerSymbolSpecificationSchema
>;

const sizingCommonShape = {
  entryPrice: PositiveNumberSchema,
  stopLossPrice: PositiveNumberSchema,
  stopDistancePrice: PositiveNumberSchema,
  stopDistancePoints: PositiveNumberSchema,
  accountEquity: PositiveNumberSchema,
  riskLimitPct: PositiveNumberSchema,
  riskBudgetAmount: PositiveNumberSchema,
  calculatedVolume: PositiveNumberSchema,
  brokerMinimumVolume: PositiveNumberSchema,
  brokerVolumeStep: PositiveNumberSchema,
  maximumPermittedVolume: z.literal(0.01),
  estimatedLossAtStop: PositiveNumberSchema,
  actualRiskPct: PositiveNumberSchema,
  unusedRiskCapacity: z.number().finite(),
  calculationSource: z.enum([
    "mt5_order_calc_profit",
    "broker_tick_value",
    "simulation",
  ]),
};

const positionSizingUnion = z.discriminatedUnion("result", [
  z
    .object({
      ...sizingCommonShape,
      result: z.literal("pass"),
      requestedVolume: PositiveNumberSchema.max(0.01),
      approvedVolume: PositiveNumberSchema.max(0.01).nullable(),
    })
    .strict(),
  z
    .object({
      ...sizingCommonShape,
      result: z.literal("block"),
      requestedVolume: z.null(),
      approvedVolume: z.null(),
      blockReason: IdentifierSchema,
    })
    .strict(),
]);

export const PositionSizingResultSchema = positionSizingUnion.superRefine(
  (sizing, context) => {
    const tolerance = 0.011;
    const expectedDistance = Math.abs(sizing.entryPrice - sizing.stopLossPrice);
    if (Math.abs(expectedDistance - sizing.stopDistancePrice) > tolerance) {
      context.addIssue({
        code: "custom",
        path: ["stopDistancePrice"],
        message: "Stop distance must match entry and Stop Loss prices.",
      });
    }

    const expectedBudget = sizing.accountEquity * (sizing.riskLimitPct / 100);
    if (Math.abs(expectedBudget - sizing.riskBudgetAmount) > tolerance) {
      context.addIssue({
        code: "custom",
        path: ["riskBudgetAmount"],
        message: "Risk budget must reconcile with equity and risk percentage.",
      });
    }

    const expectedRisk =
      (sizing.estimatedLossAtStop / sizing.accountEquity) * 100;
    if (Math.abs(expectedRisk - sizing.actualRiskPct) > tolerance) {
      context.addIssue({
        code: "custom",
        path: ["actualRiskPct"],
        message: "Actual risk must reconcile with estimated loss and equity.",
      });
    }

    if (
      sizing.result === "pass" &&
      sizing.approvedVolume !== null &&
      sizing.approvedVolume > sizing.requestedVolume
    ) {
      context.addIssue({
        code: "custom",
        path: ["approvedVolume"],
        message: "Approved volume cannot exceed requested volume.",
      });
    }
  },
);

export type PositionSizingResult = z.infer<typeof PositionSizingResultSchema>;

export const TRADE_PROPOSAL_STATUSES = [
  "candidate",
  "validated",
  "pending_approval",
  "approved",
  "rejected",
  "blocked",
  "expired",
  "execution_pending",
  "executed",
  "failed",
] as const;

export const TradeProposalStatusSchema = z.enum(TRADE_PROPOSAL_STATUSES);

export const TRADE_DIRECTIONS = ["BUY", "SELL"] as const;
export const TradeDirectionSchema = z.enum(TRADE_DIRECTIONS);

export const TradeProposalSchema = z
  .object({
    id: UuidSchema,
    proposalVersion: z.number().int().positive(),
    userId: UuidSchema,
    tradingAccountId: UuidSchema,
    accountType: z.literal("demo"),
    accountCurrency: CurrencyCodeSchema,
    brokerServer: IdentifierSchema,
    canonicalSymbol: z.literal("XAUUSD"),
    brokerSymbol: IdentifierSchema,
    symbolSpecificationVersion: IdentifierSchema,
    direction: TradeDirectionSchema,
    strategyCode: IdentifierSchema,
    strategyVersion: IdentifierSchema,
    modelVersion: IdentifierSchema.optional(),
    eligibilityPolicyVersion: IdentifierSchema,
    riskPolicyVersion: IdentifierSchema,
    entryPrice: PositiveNumberSchema,
    stopLossPrice: PositiveNumberSchema,
    takeProfitPrice: PositiveNumberSchema,
    calculatedVolume: PositiveNumberSchema,
    requestedVolume: PositiveNumberSchema.max(0.01).nullable(),
    approvedVolume: PositiveNumberSchema.max(0.01).nullable(),
    maximumPermittedVolume: z.literal(0.01),
    riskAmount: PositiveNumberSchema,
    riskPct: PositiveNumberSchema,
    riskReward: PositiveNumberSchema,
    marketSnapshotId: UuidSchema,
    featureSnapshotId: UuidSchema,
    decisionTraceId: UuidSchema,
    eligibility: EligibilityPolicyResultSchema,
    status: TradeProposalStatusSchema,
    createdAt: IsoDateTimeSchema,
    expiresAt: IsoDateTimeSchema,
    processedAt: IsoDateTimeSchema.optional(),
  })
  .strict()
  .superRefine((proposal, context) => {
    const orderedPrices =
      proposal.direction === "BUY"
        ? proposal.stopLossPrice < proposal.entryPrice &&
          proposal.entryPrice < proposal.takeProfitPrice
        : proposal.takeProfitPrice < proposal.entryPrice &&
          proposal.entryPrice < proposal.stopLossPrice;
    if (!orderedPrices) {
      context.addIssue({
        code: "custom",
        path: ["stopLossPrice"],
        message: "Entry, Stop Loss, and Take Profit are invalid for direction.",
      });
    }

    if (!isBefore(proposal.createdAt, proposal.expiresAt)) {
      context.addIssue({
        code: "custom",
        path: ["expiresAt"],
        message: "Proposal expiry must be after creation.",
      });
    }

    if (
      proposal.status === "blocked" &&
      (proposal.requestedVolume !== null || proposal.approvedVolume !== null)
    ) {
      context.addIssue({
        code: "custom",
        path: ["requestedVolume"],
        message: "Blocked proposals cannot request or approve volume.",
      });
    }

    if (proposal.approvedVolume !== null && proposal.requestedVolume === null) {
      context.addIssue({
        code: "custom",
        path: ["approvedVolume"],
        message: "Approved volume requires a requested volume.",
      });
    }
    if (
      proposal.approvedVolume !== null &&
      proposal.requestedVolume !== null &&
      proposal.approvedVolume > proposal.requestedVolume
    ) {
      context.addIssue({
        code: "custom",
        path: ["approvedVolume"],
        message: "Approved volume cannot exceed requested volume.",
      });
    }
  });

export type TradeProposal = z.infer<typeof TradeProposalSchema>;

/**
 * SQL-aligned proposal summary. It intentionally does not pretend to be a full
 * TradeProposal: the database row stores eligibility summary fields, not the
 * EligibilityPolicyResult.checks evidence required by TradeProposalSchema.
 */
export const PersistedTradeProposalSchema = z
  .object({
    id: UuidSchema,
    ownerId: UuidSchema,
    proposalVersion: z.number().int().positive(),
    tradingAccountId: UuidSchema,
    brokerSymbolId: UuidSchema,
    riskPolicyVersionId: UuidSchema,
    accountType: z.literal("demo"),
    accountCurrency: CurrencyCodeSchema,
    brokerServer: IdentifierSchema,
    canonicalSymbol: z.literal("XAUUSD"),
    brokerSymbol: IdentifierSchema,
    symbolSpecificationVersion: IdentifierSchema,
    direction: TradeDirectionSchema,
    strategyCode: IdentifierSchema,
    strategyVersion: IdentifierSchema,
    modelVersion: IdentifierSchema.nullable(),
    eligibilityPolicyId: IdentifierSchema,
    eligibilityPolicyVersion: IdentifierSchema,
    eligibilityOutcome: z.enum(["auto", "ask", "block"]),
    eligibilityEvaluatedAt: IsoDateTimeSchema,
    riskPolicyVersion: IdentifierSchema,
    entryPrice: PositiveNumberSchema,
    stopLossPrice: PositiveNumberSchema,
    takeProfitPrice: PositiveNumberSchema,
    calculatedVolume: PositiveNumberSchema,
    requestedVolume: PositiveNumberSchema.max(0.01).nullable(),
    approvedVolume: PositiveNumberSchema.max(0.01).nullable(),
    maximumPermittedVolume: z.literal(0.01),
    riskAmount: PositiveNumberSchema,
    riskPct: PositiveNumberSchema,
    riskReward: PositiveNumberSchema,
    marketSnapshotId: UuidSchema,
    featureSnapshotId: UuidSchema,
    decisionTraceId: UuidSchema,
    status: TradeProposalStatusSchema,
    createdAt: IsoDateTimeSchema,
    expiresAt: IsoDateTimeSchema,
    processedAt: IsoDateTimeSchema.nullable(),
    updatedAt: IsoDateTimeSchema,
  })
  .strict()
  .superRefine((proposal, context) => {
    const orderedPrices =
      proposal.direction === "BUY"
        ? proposal.stopLossPrice < proposal.entryPrice &&
          proposal.entryPrice < proposal.takeProfitPrice
        : proposal.takeProfitPrice < proposal.entryPrice &&
          proposal.entryPrice < proposal.stopLossPrice;
    if (!orderedPrices) {
      context.addIssue({
        code: "custom",
        path: ["stopLossPrice"],
        message: "Entry, Stop Loss, and Take Profit are invalid for direction.",
      });
    }
    if (!isBefore(proposal.createdAt, proposal.expiresAt)) {
      context.addIssue({
        code: "custom",
        path: ["expiresAt"],
        message: "Proposal expiry must be after creation.",
      });
    }
    if (
      proposal.status === "blocked" &&
      (proposal.requestedVolume !== null || proposal.approvedVolume !== null)
    ) {
      context.addIssue({
        code: "custom",
        path: ["requestedVolume"],
        message: "Blocked proposals cannot request or approve volume.",
      });
    }
    if (proposal.approvedVolume !== null && proposal.requestedVolume === null) {
      context.addIssue({
        code: "custom",
        path: ["approvedVolume"],
        message: "Approved volume requires a requested volume.",
      });
    }
    if (
      proposal.approvedVolume !== null &&
      proposal.requestedVolume !== null &&
      proposal.approvedVolume > proposal.requestedVolume
    ) {
      context.addIssue({
        code: "custom",
        path: ["approvedVolume"],
        message: "Approved volume cannot exceed requested volume.",
      });
    }
  });

export type PersistedTradeProposal = z.infer<
  typeof PersistedTradeProposalSchema
>;

export const MobileApprovalSessionStatusSchema = z.enum([
  "created",
  "validated",
  "used",
  "expired",
  "revoked",
]);

export const MobileApprovalSessionSchema = z
  .object({
    id: UuidSchema,
    proposalId: UuidSchema,
    proposalVersion: z.number().int().positive(),
    allowedUserId: IdentifierSchema,
    tokenHash: z.string().min(32).max(256),
    nonce: IdentifierSchema,
    status: MobileApprovalSessionStatusSchema,
    createdAt: IsoDateTimeSchema,
    expiresAt: IsoDateTimeSchema,
    usedAt: IsoDateTimeSchema.optional(),
  })
  .strict()
  .superRefine((session, context) => {
    if (!isBefore(session.createdAt, session.expiresAt)) {
      context.addIssue({
        code: "custom",
        path: ["expiresAt"],
        message: "Approval session expiry must be after creation.",
      });
    }
    if (session.status === "used" && !session.usedAt) {
      context.addIssue({
        code: "custom",
        path: ["usedAt"],
        message: "Used approval sessions require a usedAt timestamp.",
      });
    }
  });

export type MobileApprovalSession = z.infer<typeof MobileApprovalSessionSchema>;
