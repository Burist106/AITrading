import {
  buildEligibility,
  buildEmergencyStopState,
  buildMarketContext,
  buildPositionSizing,
  buildPositionFixture,
  buildRiskChecks,
  buildSignalEvidence,
  buildSystemHealth,
  buildTradeProposal,
  deriveSampleMetrics,
  getSample,
  getScenario,
  resolveScenarioId,
  scenarioStore,
} from "@aurum/fixtures";

export type ScenarioQuery = Promise<{ scenario?: string }>;

export async function loadScenarioView(searchParams: ScenarioQuery) {
  const query = await searchParams;
  const scenarioId = resolveRuntimeScenarioId(query.scenario);
  const scenario = getScenario(scenarioId);
  const sample = getSample(scenarioId);

  return {
    scenarioId,
    scenario,
    sample,
    metrics: deriveSampleMetrics(sample),
    market: buildMarketContext(sample, scenarioId),
    eligibility: buildEligibility(sample, scenarioId),
    evidence: buildSignalEvidence(sample),
    sizing: buildPositionSizing(sample, scenarioId),
    proposal: buildTradeProposal(scenarioId),
    riskChecks: buildRiskChecks(scenarioId),
    emergency: buildEmergencyStopState(scenarioId),
    health: buildSystemHealth(scenarioId),
    position: buildPositionFixture(scenarioId),
  };
}

export type ScenarioView = Awaited<ReturnType<typeof loadScenarioView>>;

export function resolveRuntimeScenarioId(
  value: string | undefined,
  runtimeEnvironment: string | undefined = process.env.NODE_ENV,
) {
  return runtimeEnvironment === "production"
    ? scenarioStore.defaultScenarioId
    : resolveScenarioId(value);
}

export function withScenario(
  path: string,
  scenarioId: string,
  runtimeEnvironment: string | undefined = process.env.NODE_ENV,
): string {
  return runtimeEnvironment === "production"
    ? path
    : `${path}?scenario=${encodeURIComponent(scenarioId)}`;
}
