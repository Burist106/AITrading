import { z } from "zod";

export const BootstrapSafetyPolicySchema = z
  .object({
    schemaVersion: z.literal(1),
    environment: z.literal("DEMO_ONLY"),
    runtimeMode: z.literal("shadow"),
    canonicalSymbol: z.literal("XAUUSD"),
    maximumPermittedVolume: z.literal(0.01),
    maximumOpenPositions: z.literal(1),
    stopLossRequired: z.literal(true),
  })
  .strict();

export type BootstrapSafetyPolicy = z.infer<typeof BootstrapSafetyPolicySchema>;

export const BOOTSTRAP_SAFETY_POLICY = Object.freeze({
  schemaVersion: 1,
  environment: "DEMO_ONLY",
  runtimeMode: "shadow",
  canonicalSymbol: "XAUUSD",
  maximumPermittedVolume: 0.01,
  maximumOpenPositions: 1,
  stopLossRequired: true,
} satisfies BootstrapSafetyPolicy);

BootstrapSafetyPolicySchema.parse(BOOTSTRAP_SAFETY_POLICY);
