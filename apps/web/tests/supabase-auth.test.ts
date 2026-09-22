// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  SafeReadFailure,
  boundedForm,
  boundedJson,
  cookieOptions,
  csrfCookie,
  newCsrfToken,
  passwordSession,
  sessionCookie,
  validCsrf,
  verifyAuthUser,
  webConfiguration,
} from "../lib/supabase-auth";

const environment = {
  NODE_ENV: "production",
  NEXT_PUBLIC_SUPABASE_URL: "https://database.example.invalid",
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:
    "sb_publishable_fictional_public_test_key",
  AURUM_WEB_ORIGIN: "https://console.example.invalid",
};
const config = webConfiguration(environment)!;
const owner = "11111111-1111-4111-8111-111111111111";
const token = "fictional.header.signature";

describe("server-owned Supabase authentication", () => {
  it("aborts stalled request bodies and cancels their streams", async () => {
    const controller = new AbortController();
    const cancel = vi.fn();
    const options: RequestInit & { duplex: "half" } = {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new ReadableStream({ cancel }),
      signal: controller.signal,
      duplex: "half",
    };
    const pending = boundedForm(new Request(config.origin, options));
    controller.abort();
    expect(await pending).toBeNull();
    expect(cancel).toHaveBeenCalledOnce();
  });
  it("applies a deadline to a never-finishing body independently of byte count", async () => {
    vi.useFakeTimers();
    try {
      const cancel = vi.fn();
      const options: RequestInit & { duplex: "half" } = {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new ReadableStream({ cancel }),
        duplex: "half",
      };
      const pending = boundedForm(new Request(config.origin, options));
      await vi.advanceTimersByTimeAsync(8000);
      expect(await pending).toBeNull();
      expect(cancel).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
    }
  });
  it("validates public configuration without privileged fallback", () => {
    expect(config.origin).toBe(environment.AURUM_WEB_ORIGIN);
    expect(webConfiguration({})).toBeNull();
    expect(
      webConfiguration({
        ...environment,
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_secret_rejected",
      }),
    ).toBeNull();
    expect(
      webConfiguration({
        ...environment,
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: token,
      }),
    ).toBeNull();
  });
  it.each([
    "http://console.example.invalid",
    "https://user:password@console.example.invalid",
    "https://console.example.invalid/path",
    "https://console.example.invalid?query=1",
  ])("rejects unsafe production origin %s", (origin) => {
    expect(
      webConfiguration({ ...environment, AURUM_WEB_ORIGIN: origin }),
    ).toBeNull();
  });
  it("permits HTTP only on development loopback", () => {
    expect(
      webConfiguration({
        ...environment,
        NODE_ENV: "development",
        AURUM_WEB_ORIGIN: "http://localhost:3000",
        NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:54321",
      }),
    ).not.toBeNull();
    expect(
      webConfiguration({
        ...environment,
        NODE_ENV: "development",
        AURUM_WEB_ORIGIN: "http://other.invalid",
      }),
    ).toBeNull();
  });
  it("sets secure host-only HttpOnly Strict cookies", () => {
    expect(cookieOptions(config, 60)).toEqual({
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      path: "/",
      maxAge: 60,
    });
    expect(sessionCookie(config)).toBe("__Host-aurum-session");
    expect(csrfCookie(config)).toBe("__Host-aurum-csrf");
  });
  it("requires verified Auth response, not token claims, to establish owner", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ id: owner }));
    expect(await verifyAuthUser(config, token, fetcher)).toBe(owner);
    const [url, request] = fetcher.mock.calls[0]!;
    expect(url).toBe(`${config.supabaseUrl}/auth/v1/user`);
    expect(request).toMatchObject({
      method: "GET",
      cache: "no-store",
      redirect: "error",
    });
    expect(request?.headers).toMatchObject({
      Authorization: `Bearer ${token}`,
    });
  });
  it.each([401, 403, 500])(
    "sanitizes remote authentication error %i",
    async (status) => {
      const fetcher = vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("private remote error", { status }));
      await expect(verifyAuthUser(config, token, fetcher)).rejects.toThrow(
        status < 500 ? "signed_out" : "read_failed",
      );
    },
  );
  it("does not fetch with malformed access tokens", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(verifyAuthUser(config, "invalid", fetcher)).rejects.toThrow(
      "signed_out",
    );
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("fails closed for malformed user data and raw network failures", async () => {
    await expect(
      verifyAuthUser(
        config,
        token,
        vi
          .fn<typeof fetch>()
          .mockResolvedValue(Response.json({ id: "not-uuid" })),
      ),
    ).rejects.toThrow("invalid_data");
    await expect(
      verifyAuthUser(
        config,
        token,
        vi
          .fn<typeof fetch>()
          .mockRejectedValue(new Error("private network text")),
      ),
    ).rejects.toThrow("read_failed");
  });
  it("retains only bounded access session after server verification", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        Response.json({
          access_token: token,
          expires_in: 7200,
          refresh_token: "discarded",
        }),
      )
      .mockResolvedValueOnce(Response.json({ id: owner }));
    const session = await passwordSession(
      config,
      "fictional@example.invalid",
      "fictional-password",
      fetcher,
    );
    expect(session).toEqual({ token, maxAge: 3600 });
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      `${config.supabaseUrl}/auth/v1/token?grant_type=password`,
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("does not sign in with invalid or oversized forms", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(
      passwordSession(config, "invalid", "anything", fetcher),
    ).rejects.toThrow("signed_out");
    await expect(
      passwordSession(
        config,
        "fictional@example.invalid",
        "x".repeat(1025),
        fetcher,
      ),
    ).rejects.toThrow("signed_out");
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("requires matching nonce and exact configured Origin, not forwarded hosts", () => {
    const nonce = newCsrfToken();
    const request = (origin: string, site = "same-origin") =>
      new Request(`${config.origin}/auth/sign-in`, {
        method: "POST",
        headers: {
          origin,
          "sec-fetch-site": site,
          "x-forwarded-host": "attacker.invalid",
        },
      });
    expect(validCsrf(request(config.origin), config, nonce, nonce)).toBe(true);
    expect(
      validCsrf(request("https://attacker.invalid"), config, nonce, nonce),
    ).toBe(false);
    expect(
      validCsrf(request(config.origin, "cross-site"), config, nonce, nonce),
    ).toBe(false);
    expect(
      validCsrf(request(config.origin), config, nonce, newCsrfToken()),
    ).toBe(false);
    expect(validCsrf(request(config.origin), config, undefined, nonce)).toBe(
      false,
    );
  });
  it("bounds form bodies without reflecting supplied credentials", async () => {
    const form = (body: string) =>
      new Request(`${config.origin}/auth/sign-in`, {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body,
      });
    expect(
      (await boundedForm(form("csrf=abc&email=fictional")))?.get("csrf"),
    ).toBe("abc");
    expect(await boundedForm(form("x".repeat(4097)))).toBeNull();
    expect(
      await boundedForm(
        new Request(config.origin, { method: "POST", body: "text" }),
      ),
    ).toBeNull();
  });
  it("bounds streamed JSON and discards malformed/error bodies", async () => {
    await expect(boundedJson(new Response("x".repeat(20)), 10)).rejects.toThrow(
      "invalid_data",
    );
    await expect(boundedJson(new Response("not-json"))).rejects.toThrow(
      "invalid_data",
    );
    expect(new SafeReadFailure("read_failed").message).toBe("read_failed");
  });
});
