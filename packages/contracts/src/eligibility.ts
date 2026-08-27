import { z } from "zod";

import {
  FiniteNumberSchema,
  IdentifierSchema,
  IsoDateTimeSchema,
  NonNegativeNumberSchema,
} from "./primitives";

export const EligibilityCheckKeySchema = z.enum([
  "strategy_policy",
  "regime_eligibility",
  "minimum_sample_size",
  "data_quality",
  "calibration_requirement",
  "hard_risk_validation",
  "execution_environment",
]);

export const EligibilityCheckStateSchema = z.enum([
  "pass",
  "warn",
  "fail",
  "not_required",
]);

export const EligibilityCheckSchema = z
  .object({
    key: EligibilityCheckKeySchema,
    labelTh: IdentifierSchema,
    state: EligibilityCheckStateSchema,
    actualValue: z.union([z.string(), FiniteNumberSchema]).optional(),
    requiredValue: z.union([z.string(), FiniteNumberSchema]).optional(),
    explanation: z.string().trim().min(1).optional(),
  })
  .strict();

export type EligibilityCheck = z.infer<typeof EligibilityCheckSchema>;

export const EligibilityOutcomeSchema = z.enum(["auto", "ask", "block"]);

export const EligibilityPolicyResultSchema = z
  .object({
    policyId: IdentifierSchema,
    policyVersion: IdentifierSchema,
    outcome: EligibilityOutcomeSchema,
    evaluatedAt: IsoDateTimeSchema,
    checks: z.array(EligibilityCheckSchema).min(1),
  })
  .strict()
  .superRefine((result, context) => {
    const keys = result.checks.map((check) => check.key);
    if (new Set(keys).size !== keys.length) {
      context.addIssue({
        code: "custom",
        path: ["checks"],
        message: "Eligibility check keys must be unique.",
      });
    }

    const expected = result.checks.some((check) => check.state === "fail")
      ? "block"
      : result.checks.some((check) => check.state === "warn")
        ? "ask"
        : "auto";
    if (result.outcome !== expected) {
      context.addIssue({
        code: "custom",
        path: ["outcome"],
        message: `Outcome must be ${expected} for the supplied checks.`,
      });
    }
  });

export type EligibilityPolicyResult = z.infer<
  typeof EligibilityPolicyResultSchema
>;

export const SignalEvidenceSchema = z
  .object({
    qualityScore: NonNegativeNumberSchema.max(100).nullable(),
    calibratedProbability: NonNegativeNumberSchema.max(1).nullable(),
    calibrationStatus: z.enum([
      "not_calibrated",
      "insufficient_data",
      "calibrated",
      "out_of_date",
    ]),
    similarSampleCount: z.number().int().nonnegative(),
    minimumRequiredSampleCount: z.number().int().nonnegative(),
    strategyVersion: IdentifierSchema,
    modelVersion: IdentifierSchema.optional(),
  })
  .strict()
  .superRefine((evidence, context) => {
    if (
      evidence.calibrationStatus !== "calibrated" &&
      evidence.calibratedProbability !== null
    ) {
      context.addIssue({
        code: "custom",
        path: ["calibratedProbability"],
        message: "A calibrated probability requires a calibrated model status.",
      });
    }
  });

export type SignalEvidence = z.infer<typeof SignalEvidenceSchema>;
