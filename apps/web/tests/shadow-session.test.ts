// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import parity from "../../../contract-fixtures/v1/shadow-parity.json";
import {
  CYCLE_READ_COLUMNS,
  OUTCOME_READ_COLUMNS,
} from "../lib/shadow-read-models";
import { loadShadowScreen } from "../lib/shadow-session";

const { jar } = vi.hoisted(() => ({ jar: new Map<string, string>() }));
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (key: string) => (jar.has(key) ? { value: jar.get(key) } : undefined),
  }),
}));
const token = "fictional.header.signature";
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

const rowsResponse = (rows: unknown[]) =>
  Response.json(rows, {
    headers: {
      "Content-Range": rows.length
        ? `0-${rows.length - 1}/${rows.length}`
        : "*/0",
    },
  });

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://database.example.invalid");
  vi.stubEnv(
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    "sb_publishable_fictional_public_test_key",
  );
  vi.stubEnv("AURUM_WEB_ORIGIN", "https://console.example.invalid");
  jar.set("__Host-aurum-session", token);
  jar.set("__Host-aurum-csrf", "a".repeat(64));
});
afterEach(() => {
  jar.clear();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("authenticated server screen loader", () => {
  it("never fetches or creates fixtures without public configuration", async () => {
    vi.stubEnv("AURUM_WEB_ORIGIN", "");
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    const result = await loadShadowScreen();
    expect(result).toMatchObject({
      state: "not_configured",
      page: null,
      decision: null,
    });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("never fetches without a session", async () => {
    jar.clear();
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    expect((await loadShadowScreen()).state).toBe("signed_out");
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("rejects an expired session before database access", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("not exposed", { status: 401 }));
    vi.stubGlobal("fetch", fetcher);
    expect((await loadShadowScreen()).state).toBe("signed_out");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("verifies owner then renders persisted records without passing tokens to the view", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ id: parity.cycle.owner_id }))
      .mockResolvedValueOnce(rowsResponse([cycleRow()]))
      .mockResolvedValueOnce(rowsResponse([eventRow()]));
    vi.stubGlobal("fetch", fetcher);
    const result = await loadShadowScreen();
    expect(result.state).toBe("stale");
    expect(result.page?.decisions[0]?.cycle.id).toBe(parity.cycle.id);
    expect(result.csrf).toBe("a".repeat(64));
    expect(JSON.stringify(result)).not.toContain(token);
    expect(String(fetcher.mock.calls[0]?.[0])).toContain("/auth/v1/user");
    expect(
      new URL(String(fetcher.mock.calls[1]?.[0])).searchParams.get("owner_id"),
    ).toBe(`eq.${parity.cycle.owner_id}`);
  });
  it("fails closed for cross-owner data even after successful authentication", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(
          Response.json({ id: "11111111-1111-4111-8111-111111111111" }),
        )
        .mockResolvedValueOnce(rowsResponse([cycleRow()])),
    );
    expect(await loadShadowScreen()).toMatchObject({
      state: "invalid_data",
      page: null,
      decision: null,
    });
  });
  it("distinguishes an authenticated empty database", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(Response.json({ id: parity.cycle.owner_id }))
        .mockResolvedValueOnce(rowsResponse([])),
    );
    expect(await loadShadowScreen()).toMatchObject({
      state: "no_data",
      page: { decisions: [] },
    });
  });
  it("sanitizes rejected database reads", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(Response.json({ id: parity.cycle.owner_id }))
        .mockRejectedValueOnce(new Error("private driver message")),
    );
    const result = await loadShadowScreen();
    expect(result).toMatchObject({ state: "read_failed", page: null });
    expect(JSON.stringify(result)).not.toContain("private");
  });
  it("loads exact UUID details and explicitly reports missing owner records", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(Response.json({ id: parity.cycle.owner_id }))
        .mockResolvedValueOnce(rowsResponse([])),
    );
    expect(await loadShadowScreen({ id: parity.cycle.id })).toMatchObject({
      state: "no_data",
      decision: null,
    });
  });
});
