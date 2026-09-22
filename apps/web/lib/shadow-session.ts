import { cookies } from "next/headers";
import { shadowTimeMicros } from "@aurum/contracts";

import {
  shadowDisplayState,
  type ShadowConnectionState,
  type ShadowDecisionReadModel,
  type ShadowPageReadModel,
} from "./shadow-read-models";
import {
  SafeReadFailure,
  csrfCookie,
  sessionCookie,
  verifyAuthUser,
  webConfiguration,
} from "./supabase-auth";
import { SupabaseShadowReadGateway } from "./supabase-read-gateway";

export interface ShadowScreenData {
  readonly state: ShadowConnectionState;
  readonly capturedAt: string;
  readonly csrf: string | null;
  readonly page: ShadowPageReadModel | null;
  readonly decision: ShadowDecisionReadModel | null;
}

export async function loadShadowScreen(
  options: { id?: string; page?: number } = {},
): Promise<ShadowScreenData> {
  const captured = new Date();
  const empty: ShadowScreenData = {
    state: "not_configured",
    capturedAt: captured.toISOString(),
    csrf: null,
    page: null,
    decision: null,
  };
  const config = webConfiguration(process.env);
  if (!config) return empty;
  const jar = await cookies();
  const token = jar.get(sessionCookie(config))?.value;
  if (!token) return { ...empty, state: "signed_out" };
  try {
    // Auth server verifies the session; unverified JWT claims never establish owner.
    const owner = await verifyAuthUser(config, token);
    const gateway = new SupabaseShadowReadGateway(config, token, owner);
    const csrf = jar.get(csrfCookie(config))?.value;
    const base = {
      ...empty,
      csrf: csrf && /^[a-f0-9]{64}$/u.test(csrf) ? csrf : null,
    };
    if (options.id !== undefined) {
      const decision = await gateway.getDecision(options.id);
      const now = new Date();
      const state = shadowDisplayState(decision?.cycle ?? null, now);
      if (
        state === "invalid_data" ||
        decision?.outcomes.some(
          (event) =>
            shadowTimeMicros(event.observed_at) > BigInt(now.getTime()) * 1000n,
        )
      )
        return { ...base, state: "invalid_data" };
      return {
        ...base,
        decision,
        capturedAt: now.toISOString(),
        state,
      };
    }
    const page = await gateway.getPage(options.page ?? 0);
    const now = new Date();
    if (
      page.decisions.some(
        ({ cycle, outcomes }) =>
          shadowTimeMicros(cycle.evaluated_at) >
            BigInt(now.getTime()) * 1000n ||
          outcomes.some(
            (event) =>
              shadowTimeMicros(event.observed_at) >
              BigInt(now.getTime()) * 1000n,
          ),
      )
    ) {
      return { ...base, state: "invalid_data" };
    }
    return {
      ...base,
      page,
      capturedAt: now.toISOString(),
      state: shadowDisplayState(page.decisions[0]?.cycle ?? null, now),
    };
  } catch (error) {
    return {
      ...empty,
      state: error instanceof SafeReadFailure ? error.code : "read_failed",
    };
  }
}
