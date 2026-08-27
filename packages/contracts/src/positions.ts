import { z } from "zod";

import {
  FiniteNumberSchema,
  IsoDateTimeSchema,
  PositiveNumberSchema,
  UuidSchema,
} from "./primitives";

export const POSITION_STATUSES = [
  "open",
  "close_requested",
  "closing",
  "closed",
  "mismatch",
] as const;

export const PositionStatusSchema = z.enum(POSITION_STATUSES);
export type PositionStatus = z.infer<typeof PositionStatusSchema>;

/** Read-side Position state. This contract grants no broker mutation capability. */
export const PositionSchema = z
  .object({
    id: UuidSchema,
    positionVersion: z.number().int().positive(),
    userId: UuidSchema,
    tradingAccountId: UuidSchema,
    accountType: z.literal("demo"),
    canonicalSymbol: z.literal("XAUUSD"),
    direction: z.enum(["BUY", "SELL"]),
    volume: PositiveNumberSchema.max(0.01),
    entry: PositiveNumberSchema,
    current: PositiveNumberSchema,
    stopLoss: PositiveNumberSchema,
    takeProfit: PositiveNumberSchema,
    unrealizedPnl: FiniteNumberSchema,
    rMultiple: FiniteNumberSchema,
    status: PositionStatusSchema,
    openedAt: IsoDateTimeSchema,
    updatedAt: IsoDateTimeSchema,
    closedAt: IsoDateTimeSchema.nullable(),
  })
  .strict()
  .superRefine((position, context) => {
    const pricesAreOrdered =
      position.direction === "BUY"
        ? position.stopLoss < position.entry &&
          position.entry < position.takeProfit
        : position.takeProfit < position.entry &&
          position.entry < position.stopLoss;
    if (!pricesAreOrdered) {
      context.addIssue({
        code: "custom",
        path: ["stopLoss"],
        message: "Entry, Stop Loss, and Take Profit are invalid for direction.",
      });
    }

    if (position.status === "closed" && position.closedAt === null) {
      context.addIssue({
        code: "custom",
        path: ["closedAt"],
        message: "A closed Position requires a close timestamp.",
      });
    }
    if (position.status !== "closed" && position.closedAt !== null) {
      context.addIssue({
        code: "custom",
        path: ["closedAt"],
        message: "Only a closed Position may carry a close timestamp.",
      });
    }
    if (
      position.closedAt !== null &&
      Date.parse(position.closedAt) < Date.parse(position.openedAt)
    ) {
      context.addIssue({
        code: "custom",
        path: ["closedAt"],
        message: "A Position cannot close before it opened.",
      });
    }
  });

export type Position = z.infer<typeof PositionSchema>;

/** SQL-aligned Position row after snake_case has been mapped to camelCase. */
export const PersistedPositionSchema = z
  .object({
    id: UuidSchema,
    ownerId: UuidSchema,
    tradingAccountId: UuidSchema,
    tradeProposalId: UuidSchema,
    brokerOrderId: UuidSchema,
    brokerPositionReference: z.string().trim().min(1).max(160),
    positionVersion: z.number().int().positive(),
    direction: z.enum(["BUY", "SELL"]),
    volume: PositiveNumberSchema.max(0.01),
    entryPrice: PositiveNumberSchema,
    currentPrice: PositiveNumberSchema,
    stopLossPrice: PositiveNumberSchema,
    takeProfitPrice: PositiveNumberSchema,
    unrealizedPnl: FiniteNumberSchema,
    rMultiple: FiniteNumberSchema,
    status: PositionStatusSchema,
    openedAt: IsoDateTimeSchema,
    closedAt: IsoDateTimeSchema.nullable(),
    createdAt: IsoDateTimeSchema,
    updatedAt: IsoDateTimeSchema,
  })
  .strict();

export type PersistedPosition = z.infer<typeof PersistedPositionSchema>;

export function positionFromPersisted(record: PersistedPosition): Position {
  return PositionSchema.parse({
    id: record.id,
    positionVersion: record.positionVersion,
    userId: record.ownerId,
    tradingAccountId: record.tradingAccountId,
    accountType: "demo",
    canonicalSymbol: "XAUUSD",
    direction: record.direction,
    volume: record.volume,
    entry: record.entryPrice,
    current: record.currentPrice,
    stopLoss: record.stopLossPrice,
    takeProfit: record.takeProfitPrice,
    unrealizedPnl: record.unrealizedPnl,
    rMultiple: record.rMultiple,
    status: record.status,
    openedAt: record.openedAt,
    updatedAt: record.updatedAt,
    closedAt: record.closedAt,
  });
}
