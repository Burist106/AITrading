// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import parity from "../../../contract-fixtures/v1/shadow-parity.json";
import {
  CYCLE_READ_COLUMNS,
  OUTCOME_READ_COLUMNS,
  shadowCycleFromRow,
  shadowDisplayState,
  shadowOutcomesFromRows,
} from "../lib/shadow-read-models";
import { SupabaseShadowReadGateway } from "../lib/supabase-read-gateway";
import { webConfiguration } from "../lib/supabase-auth";

const config = webConfiguration({
  NODE_ENV: "production",
  NEXT_PUBLIC_SUPABASE_URL: "https://database.example.invalid",
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:
    "sb_publishable_fictional_public_test_key",
  AURUM_WEB_ORIGIN: "https://console.example.invalid",
})!;
const cycleRow = () =>
  Object.fromEntries(
    CYCLE_READ_COLUMNS.map((key) => [
      key,
      key === "payload" ? structuredClone(parity.cycle) : parity.cycle[key],
    ]),
  );
const eventRow = () =>
  Object.fromEntries(
    OUTCOME_READ_COLUMNS.map((key) => [
      key,
      key === "payload" ? structuredClone(parity.outcome) : parity.outcome[key],
    ]),
  );
const cycle = shadowCycleFromRow(cycleRow(), parity.cycle.owner_id);
const fetchRows = (...values: unknown[]) => {
  const fetcher = vi.fn<typeof fetch>();
  for (const value of values)
    fetcher.mockImplementationOnce(async (input) => {
      const offset = Number(
        new URL(String(input)).searchParams.get("offset") ?? 0,
      );
      const length = Array.isArray(value) ? value.length : 0;
      return Response.json(value, {
        headers: {
          "Content-Range": length
            ? `${offset}-${offset + length - 1}/${offset + length}`
            : "*/0",
        },
      });
    });
  return fetcher;
};
const gateway = (fetcher: typeof fetch) =>
  new SupabaseShadowReadGateway(
    config,
    "fictional.header.signature",
    cycle.owner_id,
    fetcher,
  );

describe("bounded owner-scoped Shadow reads", () => {
  it("rejects future submillisecond observations instead of rounding them to now", () => {
    expect(
      shadowDisplayState(
        { ...cycle, evaluated_at: "2026-08-27T12:00:00.000500Z" },
        new Date("2026-08-27T12:00:00Z"),
      ),
    ).toBe("invalid_data");
    expect(
      shadowDisplayState(
        {
          ...cycle,
          candidate: {
            ...cycle.candidate!,
            expires_at: "2026-08-27T12:00:00.000500Z",
          },
        },
        new Date("2026-08-27T12:00:00Z"),
      ),
    ).toBe("ready");
  });
  it("rejects missing counts and silent server-side journal truncation", async () => {
    await expect(
      gateway(
        vi.fn<typeof fetch>().mockResolvedValue(Response.json([cycleRow()])),
      ).getPage(),
    ).rejects.toThrow("invalid_data");
    const fetcher = fetchRows([cycleRow()]);
    fetcher.mockResolvedValueOnce(
      Response.json([eventRow()], { headers: { "Content-Range": "0-0/2" } }),
    );
    await expect(gateway(fetcher).getPage()).rejects.toThrow("invalid_data");
  });
  it("reads the actual cycle UUID and its complete outcome chain with GET only", async () => {
    const fetcher = fetchRows([cycleRow()], [eventRow()]);
    const decision = await gateway(fetcher).getDecision(cycle.id);
    expect(decision?.cycle.id).toBe(cycle.id);
    expect(decision?.outcomes[0]?.status).toBe("UNKNOWN");
    for (const [input, request] of fetcher.mock.calls) {
      const url = new URL(String(input));
      expect(url.searchParams.get("owner_id")).toBe(`eq.${cycle.owner_id}`);
      expect(request).toMatchObject({
        method: "GET",
        cache: "no-store",
        redirect: "error",
      });
      expect(request?.body).toBeUndefined();
      expect(url.pathname).not.toContain("rpc");
      expect(url.searchParams.has("limit")).toBe(true);
    }
  });
  it("uses bounded deterministic page queries and complete child sets", async () => {
    const fetcher = fetchRows([cycleRow()], [eventRow()]);
    const page = await gateway(fetcher).getPage(2);
    expect(page).toMatchObject({ page: 2, hasMore: false });
    const url = new URL(String(fetcher.mock.calls[0]?.[0]));
    expect(url.searchParams.get("limit")).toBe("21");
    expect(url.searchParams.get("offset")).toBe("40");
    expect(url.searchParams.get("order")).toBe("evaluated_at.desc,id.desc");
  });
  it("distinguishes genuinely empty reads without querying children", async () => {
    const fetcher = fetchRows([]);
    expect((await gateway(fetcher).getPage()).decisions).toEqual([]);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(await gateway(fetchRows([])).getDecision(cycle.id)).toBeNull();
  });
  it.each([-1, 501, 1.5, Number.NaN])(
    "rejects invalid page %s before transport",
    async (page) => {
      const fetcher = fetchRows();
      await expect(gateway(fetcher).getPage(page)).rejects.toThrow(
        "invalid_data",
      );
      expect(fetcher).not.toHaveBeenCalled();
    },
  );
  it("rejects query injection before transport", async () => {
    const fetcher = fetchRows();
    await expect(
      gateway(fetcher).getDecision("id&owner_id=other"),
    ).rejects.toThrow("invalid_data");
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([
    "owner_id",
    "trading_account_id",
    "id",
    "cycle_key",
    "status",
    "evaluated_at",
  ])("rejects inconsistent indexed cycle %s", (key) => {
    expect(() =>
      shadowCycleFromRow({ ...cycleRow(), [key]: "mismatch" }, cycle.owner_id),
    ).toThrow("invalid_data");
  });
  it("rejects an internally consistent different owner", () => {
    expect(() =>
      shadowCycleFromRow(cycleRow(), "11111111-1111-4111-8111-111111111111"),
    ).toThrow("invalid_data");
  });
  it("preserves database timestamps with equivalent UTC representation", () => {
    expect(
      shadowCycleFromRow(
        { ...cycleRow(), evaluated_at: "2026-08-27T12:00:00+00:00" },
        cycle.owner_id,
      ).evaluated_at,
    ).toBe(cycle.evaluated_at);
  });
  it("rejects unsupported row/payload keys and unsafe fake source", () => {
    expect(() =>
      shadowCycleFromRow({ ...cycleRow(), secret: "rejected" }, cycle.owner_id),
    ).toThrow("invalid_data");
    expect(() =>
      shadowCycleFromRow(
        { ...cycleRow(), payload: { ...parity.cycle, source: "fake_mt5" } },
        cycle.owner_id,
      ),
    ).toThrow("invalid_data");
  });
  it.each([
    "owner_id",
    "trading_account_id",
    "cycle_id",
    "id",
    "sequence",
    "status",
    "observed_at",
  ])("rejects mismatched child index %s", (key) => {
    expect(() =>
      shadowOutcomesFromRows([{ ...eventRow(), [key]: "mismatch" }], cycle),
    ).toThrow("invalid_data");
  });
  it("rejects sequence gaps, duplicate UUIDs and terminal reversals", () => {
    const second = {
      ...parity.outcome,
      sequence: 2,
      observed_at: "2026-08-27T12:00:07Z",
    };
    const secondRow = {
      ...eventRow(),
      sequence: 2,
      observed_at: second.observed_at,
      payload: second,
    };
    expect(() => shadowOutcomesFromRows([secondRow], cycle)).toThrow(
      "invalid_data",
    );
    expect(() =>
      shadowOutcomesFromRows([eventRow(), secondRow], cycle),
    ).toThrow("invalid_data");
    expect(() =>
      shadowOutcomesFromRows(Array(33).fill(eventRow()), cycle),
    ).toThrow("invalid_data");
  });
  it("rejects events belonging to a different queried cycle", async () => {
    await expect(
      gateway(
        fetchRows(
          [cycleRow()],
          [{ ...eventRow(), cycle_id: "11111111-1111-4111-8111-111111111111" }],
        ),
      ).getPage(),
    ).rejects.toThrow("invalid_data");
  });
  it("rejects duplicates and oversized server result sets", async () => {
    await expect(
      gateway(fetchRows([cycleRow(), cycleRow()])).getDecision(cycle.id),
    ).rejects.toThrow("invalid_data");
    await expect(
      gateway(fetchRows([cycleRow(), cycleRow()])).getPage(),
    ).rejects.toThrow("invalid_data");
    await expect(
      gateway(fetchRows(Array(22).fill(cycleRow()))).getPage(),
    ).rejects.toThrow("invalid_data");
  });
  it("sanitizes transport errors without falling back to fixtures", async () => {
    await expect(
      gateway(
        vi
          .fn<typeof fetch>()
          .mockRejectedValue(new Error("internal database text")),
      ).getPage(),
    ).rejects.toThrow("read_failed");
    await expect(
      gateway(
        vi
          .fn<typeof fetch>()
          .mockResolvedValue(new Response("raw error", { status: 500 })),
      ).getPage(),
    ).rejects.toThrow("read_failed");
  });
  it("marks expired research evidence stale, absent evidence empty, and future evidence invalid", () => {
    expect(shadowDisplayState(cycle, new Date("2026-08-27T12:00:01Z"))).toBe(
      "ready",
    );
    expect(shadowDisplayState(cycle, new Date("2026-08-27T12:00:31Z"))).toBe(
      "stale",
    );
    expect(shadowDisplayState(cycle, new Date("2026-08-27T11:59:59Z"))).toBe(
      "invalid_data",
    );
    expect(shadowDisplayState(null, new Date())).toBe("no_data");
    expect(
      shadowDisplayState(
        { ...cycle, status: "BLOCK" },
        new Date("2026-08-27T12:00:01Z"),
      ),
    ).toBe("blocked");
  });
});
