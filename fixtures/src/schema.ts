import {
  BOOTSTRAP_SAFETY_POLICY,
  BootstrapSafetyPolicySchema,
  EligibilityOutcomeSchema,
  PositionSchema,
  PROTOTYPE_SCENARIO_IDS,
  PrototypeScenarioIdSchema,
} from "@aurum/contracts";
import { z } from "zod";

export const SampleReferenceSchema = z.enum([
  "humanApproval",
  "autoEligible",
  "minimumLotBlocked",
  "priceMoved",
]);

export const ScenarioSampleSchema = z
  .object({
    id: SampleReferenceSchema,
    accountEquity: z.number().finite().positive(),
    riskLimitPct: z.number().finite().positive(),
    entryPrice: z.number().finite().positive(),
    currentPrice: z.number().finite().positive(),
    entryTolerance: z.number().finite().positive(),
    stopLossPrice: z.number().finite().positive(),
    takeProfitPrice: z.number().finite().positive(),
    contractSize: z.number().finite().positive(),
    brokerMinimumVolume: z.number().finite().positive(),
    brokerVolumeStep: z.number().finite().positive(),
    maximumPermittedVolume: z.literal(0.01),
    calculatedVolume: z.number().finite().positive(),
    requestedVolume: z.number().finite().positive().max(0.01).nullable(),
    estimatedLossAtStop: z.number().finite().positive(),
    actualRiskPct: z.number().finite().positive(),
    qualityScore: z.number().finite().min(0).max(100),
    similarSampleCount: z.number().int().nonnegative(),
    minimumRequiredSampleCount: z.number().int().nonnegative(),
    calibrationStatus: z.enum([
      "not_calibrated",
      "insufficient_data",
      "calibrated",
      "out_of_date",
    ]),
    eligibilityOutcome: EligibilityOutcomeSchema,
    blockReason: z.string().trim().min(1).optional(),
  })
  .strict()
  .superRefine((sample, context) => {
    const tolerance = 0.011;
    const expectedRisk =
      (sample.estimatedLossAtStop / sample.accountEquity) * 100;
    if (Math.abs(expectedRisk - sample.actualRiskPct) > tolerance) {
      context.addIssue({
        code: "custom",
        path: ["actualRiskPct"],
        message: "Fixture risk percentage does not reconcile.",
      });
    }
    if (sample.eligibilityOutcome === "block" && !sample.blockReason) {
      context.addIssue({
        code: "custom",
        path: ["blockReason"],
        message: "Blocked fixture samples require a reason.",
      });
    }
    if (
      sample.eligibilityOutcome === "ask" &&
      sample.similarSampleCount >= sample.minimumRequiredSampleCount
    ) {
      context.addIssue({
        code: "custom",
        path: ["similarSampleCount"],
        message: "ASK fixture must retain its documented sample warning.",
      });
    }
  });

export type ScenarioSample = z.infer<typeof ScenarioSampleSchema>;

export const ScenarioPresentationSchema = z
  .object({
    id: PrototypeScenarioIdSchema,
    labelTh: z.string().trim().min(1),
    labelEn: z.string().trim().min(1),
    descriptionTh: z.string().trim().min(1),
    source: z.literal("fixture"),
    sampleRef: SampleReferenceSchema,
    systemState: z.enum(["running", "paused", "emergency_stop", "recovering"]),
    mt5State: z.enum(["connected", "disconnected", "reconnecting"]),
    marketFreshness: z.enum(["live", "delayed", "stale", "fallback"]),
    proposalState: z.enum([
      "none",
      "wait",
      "auto_eligible",
      "human_approval",
      "blocked",
      "expired",
      "approval_recorded",
      "revalidation_failed",
      "order_pending",
      "order_rejected",
      "executed",
      "closed",
      "minimum_lot_blocked",
    ]),
    positionState: z.enum(["none", "open_profit", "open_loss", "closed"]),
    emergencyState: z.enum([
      "inactive",
      "requested",
      "confirmed",
      "unconfirmed",
    ]),
    accountVerification: z.enum(["verified_demo", "blocked_non_demo"]),
  })
  .strict();

export type ScenarioPresentation = z.infer<typeof ScenarioPresentationSchema>;

export const PositionFixtureSchema = PositionSchema;

export const ScenarioStoreSchema = z
  .object({
    schemaVersion: z.literal(1),
    safety: BootstrapSafetyPolicySchema,
    defaultScenarioId: z.literal("no_signal"),
    samples: z
      .object({
        humanApproval: ScenarioSampleSchema,
        autoEligible: ScenarioSampleSchema,
        minimumLotBlocked: ScenarioSampleSchema,
        priceMoved: ScenarioSampleSchema,
      })
      .strict(),
    position: PositionFixtureSchema,
    scenarios: z.array(ScenarioPresentationSchema).length(20),
  })
  .strict()
  .superRefine((store, context) => {
    const ids = store.scenarios.map((scenario) => scenario.id);
    if (new Set(ids).size !== ids.length) {
      context.addIssue({
        code: "custom",
        path: ["scenarios"],
        message: "Scenario ids must be unique.",
      });
    }
    for (const expected of PROTOTYPE_SCENARIO_IDS) {
      if (!ids.includes(expected)) {
        context.addIssue({
          code: "custom",
          path: ["scenarios"],
          message: `Missing required scenario: ${expected}.`,
        });
      }
    }
  });

export type ScenarioStore = z.infer<typeof ScenarioStoreSchema>;

export const FIXTURE_SAFETY_POLICY = BOOTSTRAP_SAFETY_POLICY;
