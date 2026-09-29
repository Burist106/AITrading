import { randomBytes, timingSafeEqual } from "node:crypto";

import { UuidSchema } from "@aurum/contracts";

export interface WebConfiguration {
  readonly supabaseUrl: string;
  readonly publishableKey: string;
  readonly origin: string;
  readonly secure: boolean;
}

/** Public configuration only. There is deliberately no privileged-key fallback. */
export function webConfiguration(
  environment: Record<string, string | undefined>,
): WebConfiguration | null {
  try {
    const url = new URL(environment.NEXT_PUBLIC_SUPABASE_URL ?? "");
    const origin = new URL(environment.AURUM_WEB_ORIGIN ?? "");
    const secure = !["development", "test"].includes(
      environment.NODE_ENV ?? "",
    );
    const validUrl = (value: URL) =>
      !value.username &&
      !value.password &&
      !value.search &&
      !value.hash &&
      value.pathname === "/" &&
      (value.protocol === "https:" ||
        (!secure &&
          value.protocol === "http:" &&
          ["localhost", "127.0.0.1", "[::1]"].includes(value.hostname)));
    const key = environment.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";
    if (
      !validUrl(url) ||
      !validUrl(origin) ||
      key.trim() !== key ||
      !/^sb_publishable_[A-Za-z0-9_-]{8,256}$/u.test(key)
    )
      return null;
    return {
      supabaseUrl: url.origin,
      publishableKey: key,
      origin: origin.origin,
      secure,
    };
  } catch {
    return null;
  }
}

export const sessionCookie = (config: WebConfiguration) =>
  config.secure ? "__Host-aurum-session" : "aurum-session";
export const csrfCookie = (config: WebConfiguration) =>
  config.secure ? "__Host-aurum-csrf" : "aurum-csrf";
export const cookieOptions = (config: WebConfiguration, maxAge: number) => ({
  httpOnly: true,
  secure: config.secure,
  sameSite: "strict" as const,
  path: "/",
  maxAge,
});
export const newCsrfToken = () => randomBytes(32).toString("hex");

export class SafeReadFailure extends Error {
  constructor(readonly code: "read_failed" | "invalid_data" | "signed_out") {
    super(code);
    this.name = "SafeReadFailure";
  }
}

/** Bound the stream, not merely Content-Length; discard remote error bodies. */
export async function boundedJson(
  response: Response,
  maximumBytes = 2_000_000,
): Promise<unknown> {
  if (!response.ok)
    throw new SafeReadFailure(
      response.status === 401 || response.status === 403
        ? "signed_out"
        : "read_failed",
    );
  const reader = response.body?.getReader();
  if (!reader) throw new SafeReadFailure("invalid_data");
  let size = 0;
  const chunks: Uint8Array[] = [];
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximumBytes) throw new SafeReadFailure("invalid_data");
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(bytes),
    ) as unknown;
  } catch (error) {
    if (error instanceof SafeReadFailure) throw error;
    throw new SafeReadFailure("invalid_data");
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}

export function validAccessToken(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length <= 3800 &&
    /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/u.test(value)
  );
}

export async function verifyAuthUser(
  config: WebConfiguration,
  token: string,
  fetcher: typeof fetch = fetch,
): Promise<string> {
  if (!validAccessToken(token)) throw new SafeReadFailure("signed_out");
  try {
    const result = await boundedJson(
      await fetcher(`${config.supabaseUrl}/auth/v1/user`, {
        method: "GET",
        headers: {
          apikey: config.publishableKey,
          Authorization: `Bearer ${token}`,
        },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(8000),
      }),
      64_000,
    );
    if (!result || typeof result !== "object" || !("id" in result))
      throw new SafeReadFailure("invalid_data");
    const id = UuidSchema.safeParse(result.id);
    if (!id.success) throw new SafeReadFailure("invalid_data");
    return id.data;
  } catch (error) {
    if (error instanceof SafeReadFailure) throw error;
    throw new SafeReadFailure("read_failed");
  }
}

export function validRequestOrigin(
  request: Request,
  config: WebConfiguration,
): boolean {
  return (
    request.headers.get("origin") === config.origin &&
    new URL(request.url).origin === config.origin &&
    [null, "same-origin"].includes(request.headers.get("sec-fetch-site"))
  );
}

export function validCsrf(
  request: Request,
  config: WebConfiguration,
  cookie: string | undefined,
  submitted: string | null,
): boolean {
  if (
    !validRequestOrigin(request, config) ||
    !cookie ||
    !submitted ||
    !/^[a-f0-9]{64}$/u.test(cookie) ||
    !/^[a-f0-9]{64}$/u.test(submitted)
  )
    return false;
  return timingSafeEqual(Buffer.from(cookie), Buffer.from(submitted));
}

export async function boundedForm(
  request: Request,
): Promise<URLSearchParams | null> {
  if (
    !request.headers
      .get("content-type")
      ?.startsWith("application/x-www-form-urlencoded")
  )
    return null;
  const reader = request.body?.getReader();
  if (!reader) return null;
  let stopped = false;
  const cancel = () => {
    stopped = true;
    void reader.cancel().catch(() => undefined);
  };
  const deadline = setTimeout(cancel, 8000);
  request.signal.addEventListener("abort", cancel, { once: true });
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    if (request.signal.aborted) {
      cancel();
      return null;
    }
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4096) return null;
      chunks.push(value);
    }
    return stopped
      ? null
      : new URLSearchParams(Buffer.concat(chunks).toString("utf8"));
  } catch {
    return null;
  } finally {
    clearTimeout(deadline);
    request.signal.removeEventListener("abort", cancel);
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

/** No refresh token is retained. Expired sessions require a fresh sign-in. */
export async function passwordSession(
  config: WebConfiguration,
  email: string,
  password: string,
  fetcher: typeof fetch = fetch,
): Promise<{ token: string; maxAge: number }> {
  if (
    email.length > 254 ||
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(email) ||
    password.length < 1 ||
    password.length > 1024
  ) {
    throw new SafeReadFailure("signed_out");
  }
  try {
    const result = await boundedJson(
      await fetcher(`${config.supabaseUrl}/auth/v1/token?grant_type=password`, {
        method: "POST",
        headers: {
          apikey: config.publishableKey,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(8000),
      }),
      64_000,
    );
    if (
      !result ||
      typeof result !== "object" ||
      !("access_token" in result) ||
      !("expires_in" in result) ||
      !validAccessToken(result.access_token) ||
      typeof result.expires_in !== "number" ||
      !Number.isSafeInteger(result.expires_in) ||
      result.expires_in <= 0
    ) {
      throw new SafeReadFailure("invalid_data");
    }
    await verifyAuthUser(config, result.access_token, fetcher);
    return {
      token: result.access_token,
      maxAge: Math.min(result.expires_in, 3600),
    };
  } catch (error) {
    if (error instanceof SafeReadFailure) throw error;
    throw new SafeReadFailure("read_failed");
  }
}
