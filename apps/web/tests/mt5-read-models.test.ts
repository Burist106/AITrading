import {
  Mt5ConsoleReadModelSchema,
  type Mt5ConsoleReadModel,
} from "@aurum/contracts";
import { getScenario } from "@aurum/fixtures";
import { describe, expect, it } from "vitest";

import { buildMt5ConsoleFixture } from "../lib/mt5-fixture";
import { deriveMt5PanelState } from "../lib/mt5-read-models";

function changed(
  model: Mt5ConsoleReadModel,
  values: Record<string, unknown>,
): Mt5ConsoleReadModel {
  return Mt5ConsoleReadModelSchema.parse({ ...model, ...values });
}

describe("MT5 read-only Console states", () => {
  const healthy = buildMt5ConsoleFixture(getScenario("no_signal"));

  it("distinguishes loading, empty, and healthy", () => {
    expect(deriveMt5PanelState(undefined)).toBe("loading");
    expect(deriveMt5PanelState(null)).toBe("empty");
    expect(deriveMt5PanelState(healthy)).toBe("healthy");
  });

  it("distinguishes degraded and blocked health", () => {
    expect(
      deriveMt5PanelState(
        changed(healthy, {
          health: { ...healthy.health, state: "degraded" },
        }),
      ),
    ).toBe("degraded");
    expect(
      deriveMt5PanelState(
        changed(healthy, {
          health: { ...healthy.health, state: "blocked" },
        }),
      ),
    ).toBe("blocked");
  });

  it("distinguishes stale and reconnecting observations", () => {
    expect(
      deriveMt5PanelState(
        changed(healthy, {
          tick: { ...healthy.tick, freshness: "stale" },
        }),
      ),
    ).toBe("stale");
    expect(
      deriveMt5PanelState(
        changed(healthy, {
          health: { ...healthy.health, terminalConnected: false },
        }),
      ),
    ).toBe("reconnecting");
  });

  it("distinguishes pending and failed reconciliation", () => {
    expect(
      deriveMt5PanelState(
        changed(healthy, {
          reconciliation: {
            ...healthy.reconciliation,
            status: "running",
            outcome: null,
            completedAt: null,
          },
        }),
      ),
    ).toBe("reconciliation_pending");
    expect(
      deriveMt5PanelState(
        changed(healthy, {
          reconciliation: {
            ...healthy.reconciliation,
            status: "completed",
            outcome: "mismatch",
          },
        }),
      ),
    ).toBe("reconciliation_failed");
  });
});
