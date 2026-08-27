import { z } from "zod";

import { IdentifierSchema, IsoDateTimeSchema } from "./primitives";

export const SYSTEM_HEALTH_STATES = [
  "healthy",
  "degraded",
  "warning",
  "failed",
  "unknown",
] as const;

export const SystemHealthStateSchema = z.enum(SYSTEM_HEALTH_STATES);

export const SYSTEM_PLANES = ["control_plane", "execution_plane"] as const;

export const SystemPlaneSchema = z.enum(SYSTEM_PLANES);

export const SystemComponentHealthSchema = z
  .object({
    code: IdentifierSchema,
    labelTh: IdentifierSchema,
    plane: SystemPlaneSchema,
    state: SystemHealthStateSchema,
    detail: IdentifierSchema,
    observedAt: IsoDateTimeSchema,
  })
  .strict();

export const SystemHealthSnapshotSchema = z
  .object({
    capturedAt: IsoDateTimeSchema,
    components: z.array(SystemComponentHealthSchema).min(1),
  })
  .strict();

export type SystemHealthState = z.infer<typeof SystemHealthStateSchema>;
export type SystemComponentHealth = z.infer<typeof SystemComponentHealthSchema>;
export type SystemHealthSnapshot = z.infer<typeof SystemHealthSnapshotSchema>;

const stateSeverity: Record<SystemHealthState, number> = {
  healthy: 0,
  unknown: 1,
  degraded: 2,
  warning: 3,
  failed: 4,
};

export function deriveSystemHealthState(
  components: readonly SystemComponentHealth[],
): SystemHealthState {
  if (components.length === 0) return "unknown";
  return components.reduce<SystemHealthState>(
    (worst, component) =>
      stateSeverity[component.state] > stateSeverity[worst]
        ? component.state
        : worst,
    "healthy",
  );
}
