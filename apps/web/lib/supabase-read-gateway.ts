import { UuidSchema } from "@aurum/contracts";

import {
  CYCLE_READ_COLUMNS,
  OUTCOME_READ_COLUMNS,
  shadowCycleFromRow,
  shadowOutcomesFromRows,
  type ShadowDecisionReadModel,
  type ShadowPageReadModel,
} from "./shadow-read-models";
import {
  SafeReadFailure,
  boundedJson,
  type WebConfiguration,
} from "./supabase-auth";

/** Server-only injected capability: two exact SELECT relations; no RPC or DML. */
export class SupabaseShadowReadGateway {
  constructor(
    private readonly config: WebConfiguration,
    private readonly token: string,
    private readonly ownerId: string,
    private readonly fetcher: typeof fetch = fetch,
  ) {
    if (!UuidSchema.safeParse(ownerId).success)
      throw new SafeReadFailure("invalid_data");
  }

  private async select(
    relation: "shadow_cycles" | "shadow_outcome_events",
    parameters: URLSearchParams,
    maximumRows: number,
  ): Promise<readonly unknown[]> {
    parameters.set("owner_id", `eq.${this.ownerId}`);
    parameters.set("limit", String(maximumRows));
    try {
      const response = await this.fetcher(
        `${this.config.supabaseUrl}/rest/v1/${relation}?${parameters}`,
        {
          method: "GET",
          headers: {
            apikey: this.config.publishableKey,
            Authorization: `Bearer ${this.token}`,
            Accept: "application/json",
            Prefer: "count=exact",
          },
          cache: "no-store",
          redirect: "error",
          signal: AbortSignal.timeout(8000),
        },
      );
      const rows = await boundedJson(response);
      if (!Array.isArray(rows) || rows.length > maximumRows)
        throw new SafeReadFailure("invalid_data");
      // A lower server max_rows must not silently truncate a durable journal.
      const range = response.headers
        .get("content-range")
        ?.match(/^(?:(\d+)-(\d+)|\*)\/(\d+)$/u);
      if (!range) throw new SafeReadFailure("invalid_data");
      const total = Number(range[3]);
      const offset = Number(parameters.get("offset") ?? 0);
      if (
        !Number.isSafeInteger(total) ||
        rows.length !== Math.min(maximumRows, Math.max(0, total - offset)) ||
        (rows.length > 0 &&
          (Number(range[1]) !== offset ||
            Number(range[2]) !== offset + rows.length - 1))
      ) {
        throw new SafeReadFailure("invalid_data");
      }
      return rows;
    } catch (error) {
      if (error instanceof SafeReadFailure) throw error;
      throw new SafeReadFailure("read_failed");
    }
  }

  async getDecision(id: string): Promise<ShadowDecisionReadModel | null> {
    if (!UuidSchema.safeParse(id).success)
      throw new SafeReadFailure("invalid_data");
    const rows = await this.select(
      "shadow_cycles",
      new URLSearchParams({
        select: CYCLE_READ_COLUMNS.join(","),
        id: `eq.${id}`,
      }),
      2,
    );
    if (rows.length === 0) return null;
    if (rows.length !== 1) throw new SafeReadFailure("invalid_data");
    const cycle = shadowCycleFromRow(rows[0], this.ownerId);
    if (cycle.id !== id) throw new SafeReadFailure("invalid_data");
    const outcomes = await this.select(
      "shadow_outcome_events",
      new URLSearchParams({
        select: OUTCOME_READ_COLUMNS.join(","),
        cycle_id: `eq.${cycle.id}`,
        order: "sequence.asc",
      }),
      33,
    );
    return { cycle, outcomes: shadowOutcomesFromRows(outcomes, cycle) };
  }

  async getPage(page = 0): Promise<ShadowPageReadModel> {
    if (!Number.isSafeInteger(page) || page < 0 || page > 500)
      throw new SafeReadFailure("invalid_data");
    const rows = await this.select(
      "shadow_cycles",
      new URLSearchParams({
        select: CYCLE_READ_COLUMNS.join(","),
        order: "evaluated_at.desc,id.desc",
        offset: String(page * 20),
      }),
      21,
    );
    const validated = rows.map((row) => shadowCycleFromRow(row, this.ownerId));
    if (new Set(validated.map((cycle) => cycle.id)).size !== validated.length)
      throw new SafeReadFailure("invalid_data");
    const cycles = validated.slice(0, 20);
    const outcomes =
      cycles.length === 0
        ? []
        : await this.select(
            "shadow_outcome_events",
            new URLSearchParams({
              select: OUTCOME_READ_COLUMNS.join(","),
              cycle_id: `in.(${cycles.map((cycle) => cycle.id).join(",")})`,
              order: "cycle_id.asc,sequence.asc",
            }),
            cycles.length * 32 + 1,
          );
    if (outcomes.length > cycles.length * 32)
      throw new SafeReadFailure("invalid_data");
    const grouped = new Map(cycles.map((cycle) => [cycle.id, [] as unknown[]]));
    for (const row of outcomes) {
      if (
        !row ||
        typeof row !== "object" ||
        !("cycle_id" in row) ||
        typeof row.cycle_id !== "string" ||
        !grouped.has(row.cycle_id)
      ) {
        throw new SafeReadFailure("invalid_data");
      }
      grouped.get(row.cycle_id)!.push(row);
    }
    return {
      decisions: cycles.map((cycle) => ({
        cycle,
        outcomes: shadowOutcomesFromRows(grouped.get(cycle.id)!, cycle),
      })),
      page,
      hasMore: rows.length === 21 && page < 500,
    };
  }
}
