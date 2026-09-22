import {
  ShadowCycleSchema,
  ShadowOutcomeSchema,
  ShadowTimeSchema,
  shadowTimeMicros,
  type Database,
  type ShadowCycle,
  type ShadowOutcome,
} from "@aurum/contracts";

import { SafeReadFailure } from "./supabase-auth";

function record(
  value: unknown,
  fields: readonly string[],
): Record<string, unknown> {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).length !== fields.length ||
    fields.some((key) => !Object.hasOwn(value, key))
  ) {
    throw new SafeReadFailure("invalid_data");
  }
  return value as Record<string, unknown>;
}

export const CYCLE_READ_COLUMNS = [
  "id",
  "owner_id",
  "trading_account_id",
  "cycle_key",
  "evaluated_at",
  "status",
  "payload",
] as const satisfies readonly (keyof Database["public"]["Tables"]["shadow_cycles"]["Row"])[];
export const OUTCOME_READ_COLUMNS = [
  "id",
  "owner_id",
  "trading_account_id",
  "cycle_id",
  "sequence",
  "observed_at",
  "status",
  "payload",
] as const satisfies readonly (keyof Database["public"]["Tables"]["shadow_outcome_events"]["Row"])[];

export function shadowCycleFromRow(
  value: unknown,
  ownerId: string,
): ShadowCycle {
  const row = record(value, CYCLE_READ_COLUMNS);
  const parsed = ShadowCycleSchema.safeParse(row.payload);
  if (!parsed.success) throw new SafeReadFailure("invalid_data");
  const cycle = parsed.data;
  if (
    cycle.owner_id !== ownerId ||
    CYCLE_READ_COLUMNS.filter((key) => key !== "payload").some((key) =>
      key === "evaluated_at"
        ? typeof row[key] !== "string" ||
          !ShadowTimeSchema.safeParse(row[key]).success ||
          shadowTimeMicros(row[key]) !== shadowTimeMicros(cycle[key])
        : row[key] !== cycle[key],
    )
  ) {
    throw new SafeReadFailure("invalid_data");
  }
  return cycle;
}

export function shadowOutcomesFromRows(
  values: readonly unknown[],
  cycle: ShadowCycle,
): readonly ShadowOutcome[] {
  if (values.length > 32 || (values.length > 0 && cycle.status !== "PROPOSAL"))
    throw new SafeReadFailure("invalid_data");
  const events = values.map((value) => {
    const row = record(value, OUTCOME_READ_COLUMNS);
    const parsed = ShadowOutcomeSchema.safeParse(row.payload);
    if (!parsed.success) throw new SafeReadFailure("invalid_data");
    const event = parsed.data;
    if (
      event.owner_id !== cycle.owner_id ||
      event.trading_account_id !== cycle.trading_account_id ||
      event.cycle_id !== cycle.id ||
      OUTCOME_READ_COLUMNS.filter((key) => key !== "payload").some((key) =>
        key === "observed_at"
          ? typeof row[key] !== "string" ||
            !ShadowTimeSchema.safeParse(row[key]).success ||
            shadowTimeMicros(row[key]) !== shadowTimeMicros(event[key])
          : row[key] !== event[key],
      )
    )
      throw new SafeReadFailure("invalid_data");
    return event;
  });
  events.sort((left, right) => left.sequence - right.sequence);
  const ids = new Set<string>();
  for (const [index, event] of events.entries()) {
    const previous = events[index - 1];
    if (
      event.sequence !== index + 1 ||
      ids.has(event.id) ||
      (previous !== undefined && previous.status !== "OBSERVED") ||
      shadowTimeMicros(event.observed_at) <=
        shadowTimeMicros(previous?.observed_at ?? cycle.evaluated_at)
    ) {
      throw new SafeReadFailure("invalid_data");
    }
    ids.add(event.id);
  }
  return events;
}

export interface ShadowDecisionReadModel {
  readonly cycle: ShadowCycle;
  readonly outcomes: readonly ShadowOutcome[];
}
export interface ShadowPageReadModel {
  readonly decisions: readonly ShadowDecisionReadModel[];
  readonly page: number;
  readonly hasMore: boolean;
}
export type ShadowConnectionState =
  | "not_configured"
  | "signed_out"
  | "read_failed"
  | "invalid_data"
  | "no_data"
  | "stale"
  | "blocked"
  | "ready";

/** A stored research decision is never current execution permission. */
export function shadowDisplayState(
  cycle: ShadowCycle | null,
  now: Date,
): ShadowConnectionState {
  if (cycle === null) return "no_data";
  if (!Number.isFinite(now.getTime())) return "invalid_data";
  const current = BigInt(now.getTime()) * 1000n;
  const age = current - shadowTimeMicros(cycle.evaluated_at);
  if (age < 0n) return "invalid_data";
  if (cycle.status === "BLOCK") return "blocked";
  if (
    age > 60_000_000n ||
    (cycle.candidate !== null &&
      shadowTimeMicros(cycle.candidate.expires_at) <= current)
  )
    return "stale";
  return "ready";
}
