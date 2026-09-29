// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as signInForm, POST as signIn } from "../app/auth/sign-in/route";
import { POST as signOut } from "../app/auth/sign-out/route";

const origin = "https://console.example.invalid";
const nonce = "a".repeat(64);
const token = "fictional.header.signature";
beforeEach(() => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://database.example.invalid");
  vi.stubEnv(
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    "sb_publishable_fictional_public_test_key",
  );
  vi.stubEnv("AURUM_WEB_ORIGIN", origin);
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
function request(path: string, body: string, requestOrigin = origin) {
  return new NextRequest(`${origin}${path}`, {
    method: "POST",
    headers: {
      origin: requestOrigin,
      "content-type": "application/x-www-form-urlencoded",
      cookie: `__Host-aurum-csrf=${nonce}; __Host-aurum-session=${token}`,
      "sec-fetch-site": "same-origin",
    },
    body,
  });
}

describe("protected sign-in and sign-out routes", () => {
  it.each([signIn, signOut])(
    "rejects impossible Origin before touching a stalled body",
    async (handler) => {
      const incoming = request(
        "/auth/sign-in",
        "ignored",
        "https://attacker.invalid",
      );
      const getter = vi
        .spyOn(incoming, "body", "get")
        .mockImplementation(() => {
          throw new Error("body must not be read");
        });
      expect((await handler(incoming)).status).toBe(400);
      expect(getter).not.toHaveBeenCalled();
    },
  );
  it("serves an uncached credential-free form with protected CSRF cookie", async () => {
    const response = signInForm();
    const html = await response.text();
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("content-security-policy")).toContain(
      "frame-ancestors 'none'",
    );
    expect(response.cookies.get("__Host-aurum-csrf")?.value).toMatch(
      /^[a-f0-9]{64}$/u,
    );
    for (const attribute of ["HttpOnly", "Secure", "SameSite=strict"])
      expect(response.headers.get("set-cookie")).toContain(attribute);
    expect(html).not.toContain(token);
    expect(html).toContain('type="password"');
  });
  it("rejects cross-origin sign-in before any Auth call", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    const response = await signIn(
      request(
        "/auth/sign-in",
        `csrf=${nonce}&email=fictional%40example.invalid&password=fictional`,
        "https://attacker.invalid",
      ),
    );
    expect(response.status).toBe(400);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([
    "csrf=wrong&email=x&password=y",
    `csrf=${nonce}&csrf=${nonce}&email=x&password=y`,
    `csrf=${nonce}&email=x&password=y&owner_id=wrong`,
  ])("rejects malformed or replay-ambiguous input", async (body) => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    expect((await signIn(request("/auth/sign-in", body))).status).toBe(400);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("sets access-only cookies after Auth verification without reflecting submitted identity", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(
          Response.json({
            access_token: token,
            expires_in: 1800,
            refresh_token: "discarded",
          }),
        )
        .mockResolvedValueOnce(
          Response.json({ id: "11111111-1111-4111-8111-111111111111" }),
        ),
    );
    const response = await signIn(
      request(
        "/auth/sign-in",
        `csrf=${nonce}&email=fictional%40example.invalid&password=fictional`,
      ),
    );
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(`${origin}/dashboard`);
    expect(response.cookies.get("__Host-aurum-session")?.value).toBe(token);
    expect(response.cookies.get("__Host-aurum-csrf")?.value).not.toBe(nonce);
    expect(response.headers.get("set-cookie")).not.toContain("discarded");
    expect(await response.text()).not.toMatch(/fictional|discarded/u);
  });
  it("does not reflect remote error details or submitted fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          new Response("internal secret-shaped detail", { status: 400 }),
        ),
    );
    const response = await signIn(
      request(
        "/auth/sign-in",
        `csrf=${nonce}&email=fictional%40example.invalid&password=fictional`,
      ),
    );
    expect(response.status).toBe(400);
    expect(await response.text()).not.toMatch(/internal|fictional/u);
  });
  it("clears only browser session cookies on CSRF-checked sign-out", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    const response = await signOut(request("/auth/sign-out", `csrf=${nonce}`));
    expect(response.status).toBe(303);
    expect(response.cookies.get("__Host-aurum-session")?.value).toBe("");
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
    expect(fetcher).not.toHaveBeenCalled();
    expect(
      (
        await signOut(
          request(
            "/auth/sign-out",
            `csrf=${nonce}`,
            "https://attacker.invalid",
          ),
        )
      ).status,
    ).toBe(400);
  });
});
