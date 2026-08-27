import { describe, expect, it } from "vitest";

import {
  BOOTSTRAP_SAFETY_POLICY,
  PROTOTYPE_SCENARIO_IDS,
} from "@aurum/contracts";

import {
  ScenarioStoreSchema,
  buildEligibility,
  buildPositionFixture,
  buildPositionSizing,
  buildRiskChecks,
  buildTradeProposal,
  deriveSampleMetrics,
  getSample,
  scenarioStore,
} from "../src";

describe("authoritative scenario store", () => {
  it("contains exactly the documented 20 scenarios in canonical order", () => {
    expect(scenarioStore.scenarios.map((scenario) => scenario.id)).toEqual(
      PROTOTYPE_SCENARIO_IDS,
    );
    expect(scenarioStore.defaultScenarioId).toBe("no_signal");
    expect(scenarioStore.safety).toEqual(BOOTSTRAP_SAFETY_POLICY);
  });

  it("rejects duplicate, missing, and stale scenario identifiers", () => {
    const invalid = structuredClone(scenarioStore);
    const firstScenario = invalid.scenarios[0];
    if (!firstScenario) throw new Error("Fixture corpus must not be empty.");
    invalid.scenarios[19] = {
      ...firstScenario,
      labelTh: "ซ้ำ",
      labelEn: "Duplicate",
    };
    expect(ScenarioStoreSchema.safeParse(invalid).success).toBe(false);
  });
});

describe("Human Approval fixture arithmetic", () => {
  const sample = getSample("human_approval");
  const metrics = deriveSampleMetrics(sample);

  it("reconciles every mandated value", () => {
    expect(sample.accountEquity).toBe(2200);
    expect(sample.riskLimitPct).toBe(0.25);
    expect(metrics.riskBudgetAmount).toBe(5.5);
    expect(sample.entryPrice).toBe(2410.4);
    expect(sample.currentPrice).toBe(2410.55);
    expect(sample.entryTolerance).toBe(0.6);
    expect(metrics.deviation).toBe(0.15);
    expect(metrics.withinTolerance).toBe(true);
    expect(sample.stopLossPrice).toBe(2404.9);
    expect(sample.takeProfitPrice).toBe(2421.95);
    expect(metrics.riskReward).toBe(2.1);
    expect(sample.requestedVolume).toBe(0.01);
    expect(sample.estimatedLossAtStop).toBe(5.5);
    expect(sample.actualRiskPct).toBe(0.25);
    expect(sample.similarSampleCount).toBe(24);
    expect(sample.minimumRequiredSampleCount).toBe(30);
  });

  it("returns ASK from the minimum-sample warning, independent of score", () => {
    expect(buildEligibility(sample, "human_approval").outcome).toBe("ask");
    for (const qualityScore of [0, 100]) {
      expect(
        buildEligibility({ ...sample, qualityScore }, "human_approval").outcome,
      ).toBe("ask");
    }
  });
});

describe("safety scenarios", () => {
  it("blocks when broker minimum volume exceeds the risk budget", () => {
    const sample = getSample("minimum_lot_exceeds_risk");
    const sizing = buildPositionSizing(sample);
    expect(sample.calculatedVolume).toBe(0.0045);
    expect(sample.brokerMinimumVolume).toBe(0.01);
    expect(deriveSampleMetrics(sample).riskBudgetAmount).toBe(2.5);
    expect(sizing).toMatchObject({
      result: "block",
      requestedVolume: null,
      approvedVolume: null,
      blockReason: "BROKER_MINIMUM_VOLUME_EXCEEDS_RISK",
    });
  });

  it("keeps every proposal Demo-only, XAUUSD-only, and capped at 0.01", () => {
    for (const id of PROTOTYPE_SCENARIO_IDS) {
      const proposal = buildTradeProposal(id);
      expect(proposal.accountType).toBe("demo");
      expect(proposal.canonicalSymbol).toBe("XAUUSD");
      expect(proposal.maximumPermittedVolume).toBe(0.01);
      expect(proposal.stopLossPrice).toBeGreaterThan(0);
      expect(proposal.approvedVolume).toBeNull();
    }
  });

  it("keeps every fail-closed scenario coherent across verdict, sizing, and checks", () => {
    const failClosedScenarios = [
      "blocked",
      "revalidation_failed",
      "mt5_disconnected",
      "market_data_stale",
      "daily_loss_limit",
      "emergency_stop_requested",
      "emergency_stop_confirmed",
      "emergency_stop_unconfirmed",
      "live_account_detected",
      "minimum_lot_exceeds_risk",
    ] as const;

    for (const id of failClosedScenarios) {
      const sample = getSample(id);
      expect(buildEligibility(sample, id).outcome, id).toBe("block");
      expect(buildPositionSizing(sample, id).result, id).toBe("block");
      expect(buildTradeProposal(id).status, id).toBe("blocked");
      expect(
        buildRiskChecks(id).some((check) => check.state === "fail"),
        id,
      ).toBe(true);
    }
  });

  it("derives coherent profit and loss positions from the central fixture", () => {
    const profit = buildPositionFixture("position_open");
    const loss = buildPositionFixture("mt5_disconnected");
    expect(profit.current).toBeGreaterThan(profit.entry);
    expect(profit.unrealizedPnl).toBeGreaterThan(0);
    expect(profit.rMultiple).toBeGreaterThan(0);
    expect(loss.current).toBeLessThan(loss.entry);
    expect(loss.unrealizedPnl).toBeLessThan(0);
    expect(loss.rMultiple).toBeLessThan(0);
  });
});
