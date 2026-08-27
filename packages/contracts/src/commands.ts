import { z } from "zod";

import {
  IdentifierSchema,
  IsoDateTimeSchema,
  UuidSchema,
  isBefore,
} from "./primitives";
import {
  RiskPolicyNumericRuleKeySchema,
  riskPolicyRuleValueIssue,
} from "./risk-policy";

export const SYSTEM_COMMAND_STATUSES = [
  "pending",
  "claimed",
  "validating",
  "executing",
  "succeeded",
  "rejected",
  "failed",
  "expired",
  "cancelled",
] as const;

export const SystemCommandStatusSchema = z.enum(SYSTEM_COMMAND_STATUSES);

export type SystemCommandStatus = z.infer<typeof SystemCommandStatusSchema>;

export const ApproveProposalPayloadSchema = z
  .object({
    proposalId: UuidSchema,
    proposalVersion: z.number().int().positive(),
    approvalSessionId: UuidSchema.optional(),
  })
  .strict();
export const RejectProposalPayloadSchema = z
  .object({
    proposalId: UuidSchema,
    proposalVersion: z.number().int().positive(),
    reason: IdentifierSchema,
  })
  .strict();
export const PauseNewTradesPayloadSchema = z
  .object({ reason: IdentifierSchema.optional() })
  .strict();
export const ResumeSystemPayloadSchema = z
  .object({ checklistAcknowledgementId: UuidSchema })
  .strict();
export const ActivateEmergencyStopPayloadSchema = z
  .object({ reason: IdentifierSchema })
  .strict();
export const RequestPositionClosePayloadSchema = z
  .object({
    positionId: UuidSchema,
    expectedPositionVersion: z.number().int().positive(),
    reason: IdentifierSchema,
  })
  .strict();
export const RequestStopLossChangePayloadSchema = z
  .object({
    positionId: UuidSchema,
    expectedPositionVersion: z.number().int().positive(),
    newStopLoss: z.number().finite().positive(),
  })
  .strict();
export const RequestTakeProfitChangePayloadSchema = z
  .object({
    positionId: UuidSchema,
    expectedPositionVersion: z.number().int().positive(),
    newTakeProfit: z.number().finite().positive(),
  })
  .strict();
export const RequestRiskPolicyChangePayloadSchema = z
  .object({
    ruleKey: RiskPolicyNumericRuleKeySchema,
    newValue: z.number().finite().nonnegative(),
    reason: IdentifierSchema,
  })
  .strict()
  .superRefine((change, context) => {
    const issue = riskPolicyRuleValueIssue(change.ruleKey, change.newValue);
    if (issue) {
      context.addIssue({
        code: "custom",
        path: ["newValue"],
        message: `${change.ruleKey} ${issue}.`,
      });
    }
  });

export interface SystemCommandPayloadMap {
  APPROVE_PROPOSAL: z.infer<typeof ApproveProposalPayloadSchema>;
  REJECT_PROPOSAL: z.infer<typeof RejectProposalPayloadSchema>;
  PAUSE_NEW_TRADES: z.infer<typeof PauseNewTradesPayloadSchema>;
  RESUME_SYSTEM: z.infer<typeof ResumeSystemPayloadSchema>;
  ACTIVATE_EMERGENCY_STOP: z.infer<typeof ActivateEmergencyStopPayloadSchema>;
  REQUEST_POSITION_CLOSE: z.infer<typeof RequestPositionClosePayloadSchema>;
  REQUEST_STOP_LOSS_CHANGE: z.infer<typeof RequestStopLossChangePayloadSchema>;
  REQUEST_TAKE_PROFIT_CHANGE: z.infer<
    typeof RequestTakeProfitChangePayloadSchema
  >;
  REQUEST_RISK_POLICY_CHANGE: z.infer<
    typeof RequestRiskPolicyChangePayloadSchema
  >;
}

export const SYSTEM_COMMAND_TYPES = [
  "APPROVE_PROPOSAL",
  "REJECT_PROPOSAL",
  "PAUSE_NEW_TRADES",
  "RESUME_SYSTEM",
  "ACTIVATE_EMERGENCY_STOP",
  "REQUEST_POSITION_CLOSE",
  "REQUEST_STOP_LOSS_CHANGE",
  "REQUEST_TAKE_PROFIT_CHANGE",
  "REQUEST_RISK_POLICY_CHANGE",
] as const;

export const SystemCommandTypeSchema = z.enum(SYSTEM_COMMAND_TYPES);
export type SystemCommandType = z.infer<typeof SystemCommandTypeSchema>;

export const SYSTEM_COMMAND_TARGET_RESOURCE_TYPES = [
  "trade_proposal",
  "position",
  "risk_policy",
] as const;

export const SystemCommandTargetResourceTypeSchema = z.enum(
  SYSTEM_COMMAND_TARGET_RESOURCE_TYPES,
);
export type SystemCommandTargetResourceType = z.infer<
  typeof SystemCommandTargetResourceTypeSchema
>;

const unsafeWorkerText = new RegExp(
  [
    "[\\u0000-\\u001f\\u007f-\\u009f]",
    "bearer\\s",
    "authorization\\s*[:=]",
    "password\\s*[:=]",
    "token\\s*[:=]",
    "secret\\s*[:=]",
    "client[_-]?secret\\s*[:=]",
    "api[_-]?key\\s*[:=]",
    "access[_-]?key\\s*[:=]",
    "sb_secret_",
    "(?:^|[^A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}(?:$|[^A-Za-z0-9_-])",
    "sk-[A-Za-z0-9_-]{16,}",
    "AKIA[0-9A-Z]{16}",
    "gh[pousr]_[A-Za-z0-9]{20,}",
    "(?:postgres(?:ql)?|mysql|redis|amqps?|mongodb(?:\\+srv)?):\\/\\/[^\\s/:@]+:[^\\s/@]+@",
    "-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----",
  ].join("|"),
  "iu",
);
export const ResultCodeSchema = z
  .string()
  .regex(/^[A-Z][A-Z0-9_]{0,159}$/u)
  .refine((value) => !unsafeWorkerText.test(value), {
    message: "Result code must be bounded, printable, and secret-free.",
  });
export const SafeWorkerTextSchema = z
  .string()
  .min(1)
  .max(512)
  .refine((value) => value.trim() !== "" && !unsafeWorkerText.test(value), {
    message: "Command detail must be bounded, printable, and secret-free.",
  });
export const CommandDetailSchema = SafeWorkerTextSchema;

export const SystemCommandPayloadEnvelopeSchema = z.discriminatedUnion("type", [
  z
    .object({
      type: z.literal("APPROVE_PROPOSAL"),
      payload: ApproveProposalPayloadSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("REJECT_PROPOSAL"),
      payload: RejectProposalPayloadSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("PAUSE_NEW_TRADES"),
      payload: PauseNewTradesPayloadSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("RESUME_SYSTEM"),
      payload: ResumeSystemPayloadSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("ACTIVATE_EMERGENCY_STOP"),
      payload: ActivateEmergencyStopPayloadSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("REQUEST_POSITION_CLOSE"),
      payload: RequestPositionClosePayloadSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("REQUEST_STOP_LOSS_CHANGE"),
      payload: RequestStopLossChangePayloadSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("REQUEST_TAKE_PROFIT_CHANGE"),
      payload: RequestTakeProfitChangePayloadSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("REQUEST_RISK_POLICY_CHANGE"),
      payload: RequestRiskPolicyChangePayloadSchema,
    })
    .strict(),
]);

export type SystemCommandPayloadEnvelope = z.infer<
  typeof SystemCommandPayloadEnvelopeSchema
>;

const commonCommandShape = {
  id: UuidSchema,
  ownerId: UuidSchema,
  status: SystemCommandStatusSchema,
  payloadSchemaVersion: z.literal(1),
  requestedBy: UuidSchema,
  requestedAt: IsoDateTimeSchema,
  targetResourceType: SystemCommandTargetResourceTypeSchema.optional(),
  targetResourceId: UuidSchema.optional(),
  expectedResourceVersion: z.number().int().positive().optional(),
  idempotencyKey: IdentifierSchema,
  priority: z.number().int().min(0).max(100),
  claimedAt: IsoDateTimeSchema.optional(),
  claimedBy: IdentifierSchema.optional(),
  leaseToken: UuidSchema.optional(),
  leaseExpiresAt: IsoDateTimeSchema.optional(),
  attemptCount: z.number().int().nonnegative(),
  maximumAttempts: z.number().int().positive(),
  nextRetryAt: IsoDateTimeSchema.optional(),
  expiresAt: IsoDateTimeSchema,
  completedAt: IsoDateTimeSchema.optional(),
  resultCode: ResultCodeSchema.optional(),
  resultMessage: CommandDetailSchema.optional(),
  lastError: CommandDetailSchema.optional(),
  commandVersion: z.number().int().positive(),
  eventSequence: z.number().int().nonnegative(),
  createdAt: IsoDateTimeSchema,
  updatedAt: IsoDateTimeSchema,
};

const commandUnion = z.discriminatedUnion("type", [
  z
    .object({
      ...commonCommandShape,
      type: z.literal("APPROVE_PROPOSAL"),
      payload: ApproveProposalPayloadSchema,
    })
    .strict(),
  z
    .object({
      ...commonCommandShape,
      type: z.literal("REJECT_PROPOSAL"),
      payload: RejectProposalPayloadSchema,
    })
    .strict(),
  z
    .object({
      ...commonCommandShape,
      type: z.literal("PAUSE_NEW_TRADES"),
      payload: PauseNewTradesPayloadSchema,
    })
    .strict(),
  z
    .object({
      ...commonCommandShape,
      type: z.literal("RESUME_SYSTEM"),
      payload: ResumeSystemPayloadSchema,
    })
    .strict(),
  z
    .object({
      ...commonCommandShape,
      type: z.literal("ACTIVATE_EMERGENCY_STOP"),
      payload: ActivateEmergencyStopPayloadSchema,
    })
    .strict(),
  z
    .object({
      ...commonCommandShape,
      type: z.literal("REQUEST_POSITION_CLOSE"),
      payload: RequestPositionClosePayloadSchema,
    })
    .strict(),
  z
    .object({
      ...commonCommandShape,
      type: z.literal("REQUEST_STOP_LOSS_CHANGE"),
      payload: RequestStopLossChangePayloadSchema,
    })
    .strict(),
  z
    .object({
      ...commonCommandShape,
      type: z.literal("REQUEST_TAKE_PROFIT_CHANGE"),
      payload: RequestTakeProfitChangePayloadSchema,
    })
    .strict(),
  z
    .object({
      ...commonCommandShape,
      type: z.literal("REQUEST_RISK_POLICY_CHANGE"),
      payload: RequestRiskPolicyChangePayloadSchema,
    })
    .strict(),
]);

const terminalStatuses = new Set<SystemCommandStatus>([
  "succeeded",
  "rejected",
  "failed",
  "expired",
  "cancelled",
]);

const activeStatuses = new Set<SystemCommandStatus>([
  "claimed",
  "validating",
  "executing",
]);

export const SystemCommandSchema = commandUnion.superRefine(
  (command, context) => {
    if (!isBefore(command.requestedAt, command.expiresAt)) {
      context.addIssue({
        code: "custom",
        path: ["expiresAt"],
        message: "Command expiry must be after the request time.",
      });
    }

    const claimFields = [
      command.claimedAt,
      command.claimedBy,
      command.leaseToken,
      command.leaseExpiresAt,
    ];
    const suppliedClaimFields = claimFields.filter(
      (value) => value !== undefined,
    ).length;
    if (suppliedClaimFields !== 0 && suppliedClaimFields !== 4) {
      context.addIssue({
        code: "custom",
        path: ["claimedAt"],
        message:
          "Claim time, owner, token, and lease expiry must be supplied together.",
      });
    }

    if (command.status === "pending" && suppliedClaimFields !== 0) {
      context.addIssue({
        code: "custom",
        path: ["claimedAt"],
        message: "A pending command cannot carry an active claim.",
      });
    }

    if (terminalStatuses.has(command.status) && suppliedClaimFields !== 0) {
      context.addIssue({
        code: "custom",
        path: ["leaseToken"],
        message:
          "Terminal command claim ownership belongs in immutable event history.",
      });
    }

    if (activeStatuses.has(command.status) && suppliedClaimFields !== 4) {
      context.addIssue({
        code: "custom",
        path: ["claimedAt"],
        message: "An active command requires a complete claim and lease.",
      });
    }

    if (activeStatuses.has(command.status) && command.attemptCount < 1) {
      context.addIssue({
        code: "custom",
        path: ["attemptCount"],
        message: "An active command must record at least one claim attempt.",
      });
    }

    if (command.attemptCount > command.maximumAttempts) {
      context.addIssue({
        code: "custom",
        path: ["attemptCount"],
        message: "Attempt count cannot exceed the configured maximum.",
      });
    }

    if (
      command.claimedAt &&
      command.leaseExpiresAt &&
      !isBefore(command.claimedAt, command.leaseExpiresAt)
    ) {
      context.addIssue({
        code: "custom",
        path: ["leaseExpiresAt"],
        message: "Lease expiry must be after claim time.",
      });
    }

    if (
      command.leaseExpiresAt &&
      isBefore(command.expiresAt, command.leaseExpiresAt)
    ) {
      context.addIssue({
        code: "custom",
        path: ["leaseExpiresAt"],
        message: "Lease expiry cannot exceed command expiry.",
      });
    }

    if (terminalStatuses.has(command.status) && !command.completedAt) {
      context.addIssue({
        code: "custom",
        path: ["completedAt"],
        message: "Terminal commands require a completion time.",
      });
    }

    if (!terminalStatuses.has(command.status) && command.completedAt) {
      context.addIssue({
        code: "custom",
        path: ["completedAt"],
        message: "A non-terminal command cannot have a completion time.",
      });
    }

    if (command.nextRetryAt && command.status !== "pending") {
      context.addIssue({
        code: "custom",
        path: ["nextRetryAt"],
        message: "Retry scheduling is valid only while a command is pending.",
      });
    }

    if (
      command.type === "ACTIVATE_EMERGENCY_STOP"
        ? command.priority !== 100
        : command.priority >= 100
    ) {
      context.addIssue({
        code: "custom",
        path: ["priority"],
        message:
          "Emergency Stop has priority 100; all other commands must be lower.",
      });
    }

    if (Date.parse(command.updatedAt) < Date.parse(command.createdAt)) {
      context.addIssue({
        code: "custom",
        path: ["updatedAt"],
        message: "Command update time cannot precede creation.",
      });
    }

    const latestLifecycleTime = Math.max(
      Date.parse(command.requestedAt),
      command.claimedAt
        ? Date.parse(command.claimedAt)
        : Number.NEGATIVE_INFINITY,
      command.completedAt
        ? Date.parse(command.completedAt)
        : Number.NEGATIVE_INFINITY,
    );
    if (Date.parse(command.updatedAt) < latestLifecycleTime) {
      context.addIssue({
        code: "custom",
        path: ["updatedAt"],
        message: "Command update time cannot precede lifecycle evidence.",
      });
    }

    const requireTarget = (
      resourceType: SystemCommandTargetResourceType,
      resourceId?: string,
      resourceVersion?: number,
    ) => {
      if (
        command.targetResourceType !== resourceType ||
        command.targetResourceId === undefined ||
        command.expectedResourceVersion === undefined
      ) {
        context.addIssue({
          code: "custom",
          path: ["targetResourceType"],
          message: `Command requires a versioned ${resourceType} target.`,
        });
        return;
      }
      if (resourceId && command.targetResourceId !== resourceId) {
        context.addIssue({
          code: "custom",
          path: ["targetResourceId"],
          message: "Command target id must match its typed payload.",
        });
      }
      if (
        resourceVersion !== undefined &&
        command.expectedResourceVersion !== resourceVersion
      ) {
        context.addIssue({
          code: "custom",
          path: ["expectedResourceVersion"],
          message: "Command target version must match its typed payload.",
        });
      }
    };

    switch (command.type) {
      case "APPROVE_PROPOSAL":
      case "REJECT_PROPOSAL":
        requireTarget(
          "trade_proposal",
          command.payload.proposalId,
          command.payload.proposalVersion,
        );
        break;
      case "REQUEST_POSITION_CLOSE":
      case "REQUEST_STOP_LOSS_CHANGE":
      case "REQUEST_TAKE_PROFIT_CHANGE":
        requireTarget(
          "position",
          command.payload.positionId,
          command.payload.expectedPositionVersion,
        );
        break;
      case "REQUEST_RISK_POLICY_CHANGE":
        requireTarget("risk_policy");
        break;
      case "PAUSE_NEW_TRADES":
      case "RESUME_SYSTEM":
      case "ACTIVATE_EMERGENCY_STOP":
        if (
          command.targetResourceType !== undefined ||
          command.targetResourceId !== undefined ||
          command.expectedResourceVersion !== undefined
        ) {
          context.addIssue({
            code: "custom",
            path: ["targetResourceType"],
            message: "A global command cannot carry a resource target.",
          });
        }
        break;
    }
  },
);

export type SystemCommand = z.infer<typeof SystemCommandSchema>;
export type SystemCommandFor<T extends SystemCommandType> = Omit<
  SystemCommand,
  "type" | "payload"
> & {
  type: T;
  payload: SystemCommandPayloadMap[T];
};
