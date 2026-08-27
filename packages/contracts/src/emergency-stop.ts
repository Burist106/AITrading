import { z } from "zod";

import { IsoDateTimeSchema, UuidSchema, isBefore } from "./primitives";

export const EMERGENCY_STOP_CONTROL_PLANE_STATES = [
  "REQUESTED",
  "CONTROL_PLANE_RECORDED",
  "CONTROL_PLANE_UNAVAILABLE",
] as const;

export const EmergencyStopControlPlaneStateSchema = z.enum(
  EMERGENCY_STOP_CONTROL_PLANE_STATES,
);

export const EMERGENCY_STOP_WORKER_STATES = [
  "WORKER_RECEIVED",
  "LOCAL_EXECUTION_DISABLED",
  "CONFIRMED",
  "WORKER_NOT_REACHABLE",
  "WORKER_ACK_TIMEOUT",
  "LOCAL_STATE_UNCONFIRMED",
  "FAILED",
] as const;

export const EmergencyStopWorkerStateSchema = z.enum(
  EMERGENCY_STOP_WORKER_STATES,
);

export const EmergencyStopStateSchema = z
  .object({
    commandId: UuidSchema,
    controlPlane: EmergencyStopControlPlaneStateSchema,
    worker: EmergencyStopWorkerStateSchema.nullable(),
    localKillSwitchEngaged: z.boolean().nullable(),
    requestedAt: IsoDateTimeSchema,
    workerAckAt: IsoDateTimeSchema.optional(),
    ackDeadlineAt: IsoDateTimeSchema,
  })
  .strict()
  .superRefine((state, context) => {
    if (!isBefore(state.requestedAt, state.ackDeadlineAt)) {
      context.addIssue({
        code: "custom",
        path: ["ackDeadlineAt"],
        message: "Acknowledgement deadline must follow the request.",
      });
    }
    if (state.worker === null && state.workerAckAt !== undefined) {
      context.addIssue({
        code: "custom",
        path: ["workerAckAt"],
        message: "A Worker acknowledgement time requires a Worker state.",
      });
    }
    if (state.worker === "CONFIRMED" && state.localKillSwitchEngaged !== true) {
      context.addIssue({
        code: "custom",
        path: ["localKillSwitchEngaged"],
        message: "Confirmed Emergency Stop requires the local switch.",
      });
    }
  });

export type EmergencyStopControlPlaneState = z.infer<
  typeof EmergencyStopControlPlaneStateSchema
>;
export type EmergencyStopWorkerState = z.infer<
  typeof EmergencyStopWorkerStateSchema
>;
export type EmergencyStopState = z.infer<typeof EmergencyStopStateSchema>;
