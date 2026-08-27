import { z } from "zod";

import { IdentifierSchema, IsoDateTimeSchema, UuidSchema } from "./primitives";

export const RISK_CHECK_STATES = ["pass", "warn", "fail", "na"] as const;

export const RiskCheckStateSchema = z.enum(RISK_CHECK_STATES);
export type RiskCheckState = z.infer<typeof RiskCheckStateSchema>;

const RiskCheckDetailSchema = z.string().trim().min(1).max(512);

/** A deterministic risk result. It is read-only evidence, never an override. */
export const RiskCheckSchema = z
  .object({
    key: IdentifierSchema,
    labelTh: IdentifierSchema,
    labelEn: IdentifierSchema,
    state: RiskCheckStateSchema,
    actual: RiskCheckDetailSchema,
    limit: RiskCheckDetailSchema.nullish(),
    hard: z.boolean(),
  })
  .strict();

export type RiskCheck = z.infer<typeof RiskCheckSchema>;

/** Persistence-boundary shape used when a risk check is read from the control plane. */
export const PersistedRiskCheckSchema = RiskCheckSchema.omit({
  limit: true,
})
  .extend({
    id: UuidSchema,
    ownerId: UuidSchema,
    tradeProposalId: UuidSchema,
    proposalVersion: z.number().int().positive(),
    limitValue: RiskCheckDetailSchema.nullable(),
    explanation: RiskCheckDetailSchema.nullable(),
    ordinal: z.number().int().nonnegative(),
    createdAt: IsoDateTimeSchema,
  })
  .strict();

export type PersistedRiskCheck = z.infer<typeof PersistedRiskCheckSchema>;

export function riskCheckFromPersisted(record: PersistedRiskCheck): RiskCheck {
  return RiskCheckSchema.parse({
    key: record.key,
    labelTh: record.labelTh,
    labelEn: record.labelEn,
    state: record.state,
    actual: record.actual,
    limit: record.limitValue,
    hard: record.hard,
  });
}
