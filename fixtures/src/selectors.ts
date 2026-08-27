import {
  EligibilityPolicyResultSchema,
  EmergencyStopStateSchema,
  PositionSizingResultSchema,
  PrototypeScenarioIdSchema,
  SignalEvidenceSchema,
  SystemHealthSnapshotSchema,
  TradeProposalSchema,
  type RiskCheck,
  type EligibilityPolicyResult,
  type EmergencyStopState,
  type PositionSizingResult,
  type PrototypeScenarioId,
  type SignalEvidence,
  type SystemHealthSnapshot,
  type TradeProposal,
} from "@aurum/contracts";

import { type ScenarioSample } from "./schema";
import { PositionFixtureSchema, type ScenarioStore } from "./schema";
import { getSample, getScenario, scenarioStore } from "./store";

const timestamp = "2026-08-26T08:22:31.000Z";

export interface DerivedSampleMetrics {
  riskBudgetAmount: number;
  deviation: number;
  withinTolerance: boolean;
  stopDistancePrice: number;
  riskReward: number;
}

export interface MarketContextFixture {
  bid: number;
  ask: number;
  spread: number;
  session: "London / New York overlap";
  regime: "trending" | "volatile";
  eventWindow: "ไม่มี Event window ใน Bootstrap Fixture";
}

export function deriveSampleMetrics(
  sample: ScenarioSample,
): DerivedSampleMetrics {
  const round = (value: number, digits = 2) => Number(value.toFixed(digits));
  const riskBudgetAmount = round(
    sample.accountEquity * (sample.riskLimitPct / 100),
  );
  const deviation = round(sample.currentPrice - sample.entryPrice);
  const stopDistancePrice = round(
    Math.abs(sample.entryPrice - sample.stopLossPrice),
  );
  const riskReward = round(
    Math.abs(sample.takeProfitPrice - sample.entryPrice) / stopDistancePrice,
    1,
  );
  return {
    riskBudgetAmount,
    deviation,
    withinTolerance: Math.abs(deviation) <= sample.entryTolerance,
    stopDistancePrice,
    riskReward,
  };
}

export function buildMarketContext(
  sample: ScenarioSample,
  scenarioId: PrototypeScenarioId,
): MarketContextFixture {
  const halfSpread = 0.05;
  return {
    bid: Number((sample.currentPrice - halfSpread).toFixed(2)),
    ask: Number((sample.currentPrice + halfSpread).toFixed(2)),
    spread: Number((halfSpread * 2).toFixed(2)),
    session: "London / New York overlap",
    regime:
      scenarioId === "market_data_stale" || scenarioId === "mt5_disconnected"
        ? "volatile"
        : "trending",
    eventWindow: "ไม่มี Event window ใน Bootstrap Fixture",
  };
}

export function buildEligibility(
  sample: ScenarioSample,
  scenarioId: PrototypeScenarioId,
): EligibilityPolicyResult {
  const scenario = getScenario(scenarioId);
  const hardFailure =
    sample.eligibilityOutcome === "block" ||
    scenario.accountVerification === "blocked_non_demo" ||
    scenario.marketFreshness === "stale" ||
    scenario.mt5State !== "connected" ||
    scenarioId === "daily_loss_limit" ||
    scenario.emergencyState !== "inactive";
  const minimumState =
    sample.similarSampleCount < sample.minimumRequiredSampleCount
      ? "warn"
      : "pass";
  const outcome = hardFailure
    ? "block"
    : minimumState === "warn"
      ? "ask"
      : "auto";

  return EligibilityPolicyResultSchema.parse({
    policyId: "demo-eligibility-policy",
    policyVersion: "v1.0.4",
    outcome,
    evaluatedAt: timestamp,
    checks: [
      {
        key: "strategy_policy",
        labelTh: "นโยบายกลยุทธ์",
        state: "pass",
        actualValue: "fixture-baseline",
        requiredValue: "versioned policy",
      },
      {
        key: "regime_eligibility",
        labelTh: "สภาวะตลาดเข้าเกณฑ์",
        state: "pass",
        actualValue: "trending",
        requiredValue: "eligible regime",
      },
      {
        key: "minimum_sample_size",
        labelTh: "จำนวนตัวอย่างขั้นต่ำ",
        state: minimumState,
        actualValue: sample.similarSampleCount,
        requiredValue: sample.minimumRequiredSampleCount,
      },
      {
        key: "data_quality",
        labelTh: "คุณภาพข้อมูล",
        state: scenario.marketFreshness === "stale" ? "fail" : "pass",
        actualValue: scenario.marketFreshness,
        requiredValue: "live or delayed",
      },
      {
        key: "calibration_requirement",
        labelTh: "สถานะการสอบเทียบ",
        state: "not_required",
        actualValue: sample.calibrationStatus,
        requiredValue: "not required in Bootstrap",
      },
      {
        key: "hard_risk_validation",
        labelTh: "กฎความเสี่ยงแบบ Hard",
        state: hardFailure ? "fail" : "pass",
        actualValue: hardFailure
          ? (sample.blockReason ?? "SCENARIO_SAFETY_BLOCK")
          : "all fixture checks pass",
        requiredValue: "all must pass",
      },
      {
        key: "execution_environment",
        labelTh: "สภาพแวดล้อมการทำงาน",
        state:
          scenario.mt5State === "connected" &&
          scenario.accountVerification === "verified_demo"
            ? "pass"
            : "fail",
        actualValue: `${scenario.mt5State}/${scenario.accountVerification}`,
        requiredValue: "connected/verified_demo",
      },
    ],
  });
}

export function buildSignalEvidence(sample: ScenarioSample): SignalEvidence {
  return SignalEvidenceSchema.parse({
    qualityScore: sample.qualityScore,
    calibratedProbability: null,
    calibrationStatus: sample.calibrationStatus,
    similarSampleCount: sample.similarSampleCount,
    minimumRequiredSampleCount: sample.minimumRequiredSampleCount,
    strategyVersion: "bootstrap-fixture-v1",
  });
}

export function buildPositionSizing(
  sample: ScenarioSample,
  scenarioId?: PrototypeScenarioId,
): PositionSizingResult {
  const metrics = deriveSampleMetrics(sample);
  const scenario = scenarioId ? getScenario(scenarioId) : null;
  const scenarioBlockReason =
    scenario?.accountVerification === "blocked_non_demo"
      ? "NON_DEMO_ACCOUNT_BLOCKED"
      : scenario?.emergencyState !== undefined &&
          scenario.emergencyState !== "inactive"
        ? "EMERGENCY_STOP_ACTIVE"
        : scenario?.mt5State !== undefined && scenario.mt5State !== "connected"
          ? "MT5_NOT_CONNECTED"
          : scenario?.marketFreshness === "stale"
            ? "MARKET_DATA_STALE"
            : scenarioId === "daily_loss_limit"
              ? "DAILY_LOSS_LIMIT_REACHED"
              : undefined;
  const blockReason = sample.blockReason ?? scenarioBlockReason;
  const common = {
    entryPrice: sample.entryPrice,
    stopLossPrice: sample.stopLossPrice,
    stopDistancePrice: metrics.stopDistancePrice,
    stopDistancePoints: metrics.stopDistancePrice / 0.01,
    accountEquity: sample.accountEquity,
    riskLimitPct: sample.riskLimitPct,
    riskBudgetAmount: metrics.riskBudgetAmount,
    calculatedVolume: sample.calculatedVolume,
    brokerMinimumVolume: sample.brokerMinimumVolume,
    brokerVolumeStep: sample.brokerVolumeStep,
    maximumPermittedVolume: sample.maximumPermittedVolume,
    estimatedLossAtStop: sample.estimatedLossAtStop,
    actualRiskPct: sample.actualRiskPct,
    unusedRiskCapacity: metrics.riskBudgetAmount - sample.estimatedLossAtStop,
    calculationSource: "simulation" as const,
  };

  return sample.eligibilityOutcome === "block" || blockReason
    ? PositionSizingResultSchema.parse({
        ...common,
        result: "block",
        requestedVolume: null,
        approvedVolume: null,
        blockReason: blockReason ?? "ELIGIBILITY_BLOCKED",
      })
    : PositionSizingResultSchema.parse({
        ...common,
        result: "pass",
        requestedVolume: sample.requestedVolume,
        approvedVolume: null,
      });
}

const statusByScenario: Partial<
  Record<PrototypeScenarioId, TradeProposal["status"]>
> = {
  human_approval: "pending_approval",
  blocked: "blocked",
  proposal_expired: "expired",
  approval_recorded: "approved",
  revalidation_failed: "blocked",
  order_pending: "execution_pending",
  order_rejected: "failed",
  position_open: "executed",
  position_closed: "executed",
  mt5_disconnected: "blocked",
  market_data_stale: "blocked",
  daily_loss_limit: "blocked",
  emergency_stop_requested: "blocked",
  emergency_stop_confirmed: "blocked",
  emergency_stop_unconfirmed: "blocked",
  live_account_detected: "blocked",
  minimum_lot_exceeds_risk: "blocked",
};

export function buildTradeProposal(
  scenarioId: PrototypeScenarioId,
): TradeProposal {
  PrototypeScenarioIdSchema.parse(scenarioId);
  const sample = getSample(scenarioId);
  const eligibility = buildEligibility(sample, scenarioId);
  const status = statusByScenario[scenarioId] ?? "validated";
  const blocked = status === "blocked";

  return TradeProposalSchema.parse({
    id: "00000000-0000-4000-8000-000000000101",
    proposalVersion: 1,
    userId: "00000000-0000-4000-8000-000000000201",
    tradingAccountId: "00000000-0000-4000-8000-000000000301",
    accountType: "demo",
    accountCurrency: "USD",
    brokerServer: "DEMO-FIXTURE-SERVER",
    canonicalSymbol: "XAUUSD",
    brokerSymbol: "XAUUSD",
    symbolSpecificationVersion: "fixture-spec-v1",
    direction: "BUY",
    strategyCode: "fixture-london-breakout",
    strategyVersion: "bootstrap-fixture-v1",
    eligibilityPolicyVersion: eligibility.policyVersion,
    riskPolicyVersion: "demo-risk-policy-v1.0.4",
    entryPrice: sample.entryPrice,
    stopLossPrice: sample.stopLossPrice,
    takeProfitPrice: sample.takeProfitPrice,
    calculatedVolume: sample.calculatedVolume,
    requestedVolume: blocked ? null : sample.requestedVolume,
    approvedVolume: null,
    maximumPermittedVolume: 0.01,
    riskAmount: sample.estimatedLossAtStop,
    riskPct: sample.actualRiskPct,
    riskReward: deriveSampleMetrics(sample).riskReward,
    marketSnapshotId: "00000000-0000-4000-8000-000000000401",
    featureSnapshotId: "00000000-0000-4000-8000-000000000501",
    decisionTraceId: "00000000-0000-4000-8000-000000000601",
    eligibility,
    status,
    createdAt: "2026-08-26T08:22:31.000Z",
    expiresAt: "2026-08-26T08:23:01.000Z",
  });
}

export function buildRiskChecks(scenarioId: PrototypeScenarioId): RiskCheck[] {
  const scenario = getScenario(scenarioId);
  const sample = getSample(scenarioId);
  const sizing = buildPositionSizing(sample, scenarioId);
  const metrics = deriveSampleMetrics(sample);
  return [
    {
      key: "demo_account",
      labelTh: "ยืนยันบัญชี Demo",
      labelEn: "Demo account verified",
      state: scenario.accountVerification === "verified_demo" ? "pass" : "fail",
      actual: scenario.accountVerification,
      hard: true,
    },
    {
      key: "market_freshness",
      labelTh: "ข้อมูลตลาดสด",
      labelEn: "Market data freshness",
      state: scenario.marketFreshness === "stale" ? "fail" : "pass",
      actual: scenario.marketFreshness,
      limit: "ไม่เกิน 10 วินาที",
      hard: true,
    },
    {
      key: "mt5_connection",
      labelTh: "การเชื่อมต่อ MT5",
      labelEn: "MT5 connection",
      state: scenario.mt5State === "connected" ? "pass" : "fail",
      actual: scenario.mt5State,
      hard: true,
    },
    {
      key: "entry_tolerance",
      labelTh: "ราคาอยู่ในช่วงที่อนุญาต",
      labelEn: "Entry price tolerance",
      state: metrics.withinTolerance ? "pass" : "fail",
      actual: `${metrics.deviation >= 0 ? "+" : ""}${metrics.deviation.toFixed(2)}`,
      limit: `±${sample.entryTolerance.toFixed(2)}`,
      hard: true,
    },
    {
      key: "stop_loss",
      labelTh: "มี Stop Loss ที่ถูกต้อง",
      labelEn: "Valid Stop Loss",
      state: sample.stopLossPrice > 0 ? "pass" : "fail",
      actual: sample.stopLossPrice.toFixed(2),
      hard: true,
    },
    {
      key: "volume_ceiling",
      labelTh: "ปริมาณไม่เกินเพดาน",
      labelEn: "Volume ceiling",
      state:
        sample.requestedVolume === null || sample.requestedVolume <= 0.01
          ? "pass"
          : "fail",
      actual:
        sample.requestedVolume === null
          ? "BLOCK"
          : sample.requestedVolume.toFixed(2),
      limit: "0.01",
      hard: true,
    },
    {
      key: "minimum_lot",
      labelTh: "Lot ขั้นต่ำอยู่ในงบความเสี่ยง",
      labelEn: "Minimum lot within risk budget",
      state:
        sizing.result === "block" &&
        sample.blockReason === "BROKER_MINIMUM_VOLUME_EXCEEDS_RISK"
          ? "fail"
          : "pass",
      actual: sample.brokerMinimumVolume.toFixed(2),
      limit: metrics.riskBudgetAmount.toFixed(2) + " USD",
      hard: true,
    },
    {
      key: "daily_loss_limit",
      labelTh: "ยังไม่ถึงลิมิตขาดทุนรายวัน",
      labelEn: "Daily loss limit",
      state: scenarioId === "daily_loss_limit" ? "fail" : "pass",
      actual:
        scenarioId === "daily_loss_limit"
          ? "limit reached"
          : "within fixture limit",
      hard: true,
    },
    {
      key: "emergency_stop",
      labelTh: "ไม่มี Emergency Stop ที่ทำงานอยู่",
      labelEn: "Emergency Stop inactive",
      state: scenario.emergencyState === "inactive" ? "pass" : "fail",
      actual: scenario.emergencyState,
      hard: true,
    },
    {
      key: "sample_size",
      labelTh: "จำนวนตัวอย่างขั้นต่ำ",
      labelEn: "Minimum sample size",
      state:
        sample.similarSampleCount < sample.minimumRequiredSampleCount
          ? "warn"
          : "pass",
      actual: String(sample.similarSampleCount),
      limit: String(sample.minimumRequiredSampleCount),
      hard: false,
    },
    {
      key: "calibration",
      labelTh: "สถานะการสอบเทียบ",
      labelEn: "Calibration status",
      state: "na",
      actual: sample.calibrationStatus,
      hard: false,
    },
  ];
}

export function buildEmergencyStopState(
  scenarioId: PrototypeScenarioId,
): EmergencyStopState | null {
  const state = getScenario(scenarioId).emergencyState;
  if (state === "inactive") return null;
  const common = {
    commandId: "00000000-0000-4000-8000-000000000701",
    requestedAt: "2026-08-26T08:22:00.000Z",
    ackDeadlineAt: "2026-08-26T08:22:10.000Z",
  };
  if (state === "requested") {
    return EmergencyStopStateSchema.parse({
      ...common,
      controlPlane: "CONTROL_PLANE_RECORDED",
      worker: null,
      localKillSwitchEngaged: null,
    });
  }
  if (state === "confirmed") {
    return EmergencyStopStateSchema.parse({
      ...common,
      controlPlane: "CONTROL_PLANE_RECORDED",
      worker: "CONFIRMED",
      localKillSwitchEngaged: true,
      workerAckAt: "2026-08-26T08:22:04.000Z",
    });
  }
  return EmergencyStopStateSchema.parse({
    ...common,
    controlPlane: "CONTROL_PLANE_RECORDED",
    worker: "WORKER_ACK_TIMEOUT",
    localKillSwitchEngaged: null,
    workerAckAt: "2026-08-26T08:22:10.000Z",
  });
}

export function buildSystemHealth(
  scenarioId: PrototypeScenarioId,
): SystemHealthSnapshot {
  const scenario = getScenario(scenarioId);
  const observedAt = timestamp;
  const failedAccount = scenario.accountVerification === "blocked_non_demo";
  return SystemHealthSnapshotSchema.parse({
    capturedAt: observedAt,
    components: [
      {
        code: "worker.bootstrap",
        labelTh: "Worker Bootstrap",
        plane: "execution_plane",
        state: failedAccount
          ? "failed"
          : scenario.mt5State === "disconnected"
            ? "failed"
            : "healthy",
        detail: failedAccount
          ? "บล็อกบัญชีที่ไม่ใช่ Demo"
          : "โครงจำลองพร้อมทำงานแบบอ่านอย่างเดียว",
        observedAt,
      },
      {
        code: "mt5.adapter",
        labelTh: "MT5 Adapter",
        plane: "execution_plane",
        state: scenario.mt5State === "connected" ? "healthy" : "failed",
        detail:
          scenario.mt5State === "connected"
            ? "Fake adapter · ไม่มี MT5 runtime"
            : "สถานะจำลอง: ขาดการเชื่อมต่อ",
        observedAt,
      },
      {
        code: "market.fixture",
        labelTh: "ข้อมูลตลาดจำลอง",
        plane: "execution_plane",
        state:
          scenario.marketFreshness === "stale"
            ? "failed"
            : scenario.marketFreshness === "delayed"
              ? "warning"
              : "healthy",
        detail: `fixture/${scenario.marketFreshness}`,
        observedAt,
      },
      {
        code: "execution.disabled",
        labelTh: "การดำเนินการกับโบรกเกอร์",
        plane: "execution_plane",
        state: "unknown",
        detail: "ไม่ได้ติดตั้งใน Bootstrap",
        observedAt,
      },
      {
        code: "supabase.placeholder",
        labelTh: "Supabase Control Plane",
        plane: "control_plane",
        state: "unknown",
        detail: "ยังไม่เชื่อมต่อ · Milestone 1",
        observedAt,
      },
      {
        code: "realtime.placeholder",
        labelTh: "Realtime",
        plane: "control_plane",
        state: "unknown",
        detail: "ยังไม่เชื่อมต่อ · ไม่ใช่คิวคำสั่ง",
        observedAt,
      },
      {
        code: "line.placeholder",
        labelTh: "LINE",
        plane: "control_plane",
        state: "unknown",
        detail: "ยังไม่เชื่อมต่อใน Bootstrap",
        observedAt,
      },
    ],
  });
}

export function buildPositionFixture(
  scenarioId: PrototypeScenarioId,
): ScenarioStore["position"] {
  const state = getScenario(scenarioId).positionState;
  if (state === "open_loss") {
    return PositionFixtureSchema.parse({
      ...scenarioStore.position,
      current: 2401.84,
      unrealizedPnl: -4.01,
      rMultiple: -0.73,
    });
  }
  if (state === "closed") {
    return PositionFixtureSchema.parse({
      ...scenarioStore.position,
      unrealizedPnl: 4.7,
      rMultiple: 0.85,
      status: "closed",
      updatedAt: "2026-08-26T08:22:31.000Z",
      closedAt: "2026-08-26T08:22:31.000Z",
    });
  }
  return scenarioStore.position;
}

export function resolveScenarioId(
  value: string | undefined,
): PrototypeScenarioId {
  const parsed = PrototypeScenarioIdSchema.safeParse(value);
  return parsed.success ? parsed.data : scenarioStore.defaultScenarioId;
}
