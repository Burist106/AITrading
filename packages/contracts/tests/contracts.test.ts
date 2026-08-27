import { describe, expect, it } from "vitest";

import {
  BOOTSTRAP_SAFETY_POLICY,
  BootstrapSafetyPolicySchema,
  BrokerSymbolSpecificationSchema,
  EmergencyStopStateSchema,
  MobileApprovalSessionSchema,
  PositionSizingResultSchema,
  SystemCommandSchema,
  TradeProposalSchema,
  deriveSystemHealthState,
} from "../src";

const ids = {
  command: "00000000-0000-4000-8000-000000000001",
  proposal: "00000000-0000-4000-8000-000000000002",
  user: "00000000-0000-4000-8000-000000000003",
  account: "00000000-0000-4000-8000-000000000004",
  market: "00000000-0000-4000-8000-000000000005",
  feature: "00000000-0000-4000-8000-000000000006",
  trace: "00000000-0000-4000-8000-000000000007",
};

const validEligibility = {
  policyId: "demo-policy",
  policyVersion: "v1",
  outcome: "ask",
  evaluatedAt: "2026-08-26T08:22:31.000Z",
  checks: [
    {
      key: "minimum_sample_size",
      labelTh: "จำนวนตัวอย่างขั้นต่ำ",
      state: "warn",
      actualValue: 24,
      requiredValue: 30,
    },
  ],
} as const;

const validProposal = {
  id: ids.proposal,
  proposalVersion: 1,
  userId: ids.user,
  tradingAccountId: ids.account,
  accountType: "demo",
  accountCurrency: "USD",
  brokerServer: "DEMO-SERVER",
  canonicalSymbol: "XAUUSD",
  brokerSymbol: "XAUUSD",
  symbolSpecificationVersion: "spec-v1",
  direction: "BUY",
  strategyCode: "fixture",
  strategyVersion: "v1",
  eligibilityPolicyVersion: "v1",
  riskPolicyVersion: "v1",
  entryPrice: 2410.4,
  stopLossPrice: 2404.9,
  takeProfitPrice: 2421.95,
  calculatedVolume: 0.01,
  requestedVolume: 0.01,
  approvedVolume: null,
  maximumPermittedVolume: 0.01,
  riskAmount: 5.5,
  riskPct: 0.25,
  riskReward: 2.1,
  marketSnapshotId: ids.market,
  featureSnapshotId: ids.feature,
  decisionTraceId: ids.trace,
  eligibility: validEligibility,
  status: "pending_approval",
  createdAt: "2026-08-26T08:22:31.000Z",
  expiresAt: "2026-08-26T08:23:01.000Z",
} as const;

describe("Bootstrap safety policy", () => {
  it("accepts only the immutable Demo Shadow policy", () => {
    expect(BootstrapSafetyPolicySchema.parse(BOOTSTRAP_SAFETY_POLICY)).toEqual(
      BOOTSTRAP_SAFETY_POLICY,
    );
    expect(
      BootstrapSafetyPolicySchema.safeParse({
        ...BOOTSTRAP_SAFETY_POLICY,
        environment: "LIVE",
      }).success,
    ).toBe(false);
    expect(
      BootstrapSafetyPolicySchema.safeParse({
        ...BOOTSTRAP_SAFETY_POLICY,
        runtimeMode: "conditional_auto",
      }).success,
    ).toBe(false);
    expect(
      BootstrapSafetyPolicySchema.safeParse({
        ...BOOTSTRAP_SAFETY_POLICY,
        brokerWritesEnabled: false,
      }).success,
    ).toBe(false);
  });
});

describe("typed command envelope", () => {
  const validCommand = {
    id: ids.command,
    ownerId: ids.user,
    type: "APPROVE_PROPOSAL",
    payload: { proposalId: ids.proposal, proposalVersion: 1 },
    status: "pending",
    payloadSchemaVersion: 1,
    requestedBy: ids.user,
    requestedAt: "2026-08-26T08:22:31.000Z",
    targetResourceType: "trade_proposal",
    targetResourceId: ids.proposal,
    expectedResourceVersion: 1,
    idempotencyKey: "fixture-idempotency-1",
    priority: 0,
    attemptCount: 0,
    maximumAttempts: 3,
    expiresAt: "2026-08-26T08:23:01.000Z",
    commandVersion: 1,
    eventSequence: 0,
    createdAt: "2026-08-26T08:22:31.000Z",
    updatedAt: "2026-08-26T08:22:31.000Z",
  } as const;

  it("couples each type to its runtime-validated payload", () => {
    expect(SystemCommandSchema.parse(validCommand).type).toBe(
      "APPROVE_PROPOSAL",
    );
    expect(
      SystemCommandSchema.safeParse({
        ...validCommand,
        payload: {
          positionId: ids.proposal,
          expectedPositionVersion: 1,
          reason: "wrong branch",
        },
      }).success,
    ).toBe(false);
  });

  it("requires complete leases and terminal completion metadata", () => {
    expect(
      SystemCommandSchema.safeParse({
        ...validCommand,
        status: "claimed",
        claimedAt: "2026-08-26T08:22:32.000Z",
      }).success,
    ).toBe(false);
    expect(
      SystemCommandSchema.safeParse({
        ...validCommand,
        status: "succeeded",
      }).success,
    ).toBe(false);
    expect(
      SystemCommandSchema.safeParse({
        ...validCommand,
        status: "claimed",
        claimedAt: "2026-08-26T08:22:32.000Z",
        claimedBy: "worker-1",
        leaseToken: "00000000-0000-4000-8000-000000000099",
        leaseExpiresAt: "2026-08-26T08:23:02.000Z",
        attemptCount: 1,
      }).success,
    ).toBe(false);
  });
});

describe("trading boundary schemas", () => {
  it("accepts the internally consistent Demo proposal", () => {
    expect(TradeProposalSchema.parse(validProposal).accountType).toBe("demo");
  });

  it("rejects non-Demo, wrong-symbol, unsafe-volume, and invalid-SL proposals", () => {
    for (const patch of [
      { accountType: "live" },
      { canonicalSymbol: "EURUSD" },
      { requestedVolume: 0.0101 },
      { requestedVolume: 0.005, approvedVolume: 0.01 },
      { stopLossPrice: 2411 },
    ]) {
      expect(
        TradeProposalSchema.safeParse({ ...validProposal, ...patch }).success,
      ).toBe(false);
    }
  });

  it("models broker minimum volume above the product ceiling for a safe block", () => {
    const specification = BrokerSymbolSpecificationSchema.parse({
      canonicalSymbol: "XAUUSD",
      brokerSymbol: "XAUUSD.a",
      specificationVersion: "spec-v1",
      accountCurrency: "USD",
      contractSize: 100,
      digits: 2,
      pointSize: 0.01,
      tickSize: 0.01,
      tickValue: 0.01,
      minimumVolume: 0.02,
      maximumVolume: 10,
      volumeStep: 0.01,
      stopLevel: 10,
      calculationMode: "fixture",
      fetchedAt: "2026-08-26T08:22:31.000Z",
    });
    expect(specification.minimumVolume).toBe(0.02);
  });

  it("validates pass and minimum-lot block sizing variants", () => {
    const common = {
      entryPrice: 2410.4,
      stopLossPrice: 2404.9,
      stopDistancePrice: 5.5,
      stopDistancePoints: 550,
      brokerMinimumVolume: 0.01,
      brokerVolumeStep: 0.01,
      maximumPermittedVolume: 0.01,
      calculationSource: "simulation",
    } as const;
    expect(
      PositionSizingResultSchema.parse({
        ...common,
        result: "pass",
        accountEquity: 2200,
        riskLimitPct: 0.25,
        riskBudgetAmount: 5.5,
        calculatedVolume: 0.01,
        requestedVolume: 0.01,
        approvedVolume: null,
        estimatedLossAtStop: 5.5,
        actualRiskPct: 0.25,
        unusedRiskCapacity: 0,
      }).result,
    ).toBe("pass");
    expect(
      PositionSizingResultSchema.safeParse({
        ...common,
        result: "pass",
        accountEquity: 2200,
        riskLimitPct: 0.25,
        riskBudgetAmount: 5.5,
        calculatedVolume: 0.005,
        requestedVolume: 0.005,
        approvedVolume: 0.01,
        estimatedLossAtStop: 5.5,
        actualRiskPct: 0.25,
        unusedRiskCapacity: 0,
      }).success,
    ).toBe(false);
    expect(
      PositionSizingResultSchema.parse({
        ...common,
        result: "block",
        accountEquity: 1000,
        riskLimitPct: 0.25,
        riskBudgetAmount: 2.5,
        calculatedVolume: 0.0045,
        requestedVolume: null,
        approvedVolume: null,
        estimatedLossAtStop: 5.5,
        actualRiskPct: 0.55,
        unusedRiskCapacity: -3,
        blockReason: "BROKER_MINIMUM_VOLUME_EXCEEDS_RISK",
      }).result,
    ).toBe("block");
  });
});

describe("approval, emergency, and health state semantics", () => {
  it("never accepts a raw approval token or incomplete used state", () => {
    const session = {
      id: ids.command,
      proposalId: ids.proposal,
      proposalVersion: 1,
      allowedUserId: "fixture-user",
      tokenHash: "0".repeat(64),
      nonce: "fixture-nonce",
      status: "created",
      createdAt: "2026-08-26T08:22:31.000Z",
      expiresAt: "2026-08-26T08:23:01.000Z",
    } as const;
    expect(MobileApprovalSessionSchema.parse(session).status).toBe("created");
    expect(
      MobileApprovalSessionSchema.safeParse({
        ...session,
        token: "raw-token-is-never-a-field",
      }).success,
    ).toBe(false);
    expect(
      MobileApprovalSessionSchema.safeParse({
        ...session,
        status: "used",
      }).success,
    ).toBe(false);
  });

  it("requires local execution disablement before Emergency Stop confirmation", () => {
    const state = {
      commandId: ids.command,
      controlPlane: "CONTROL_PLANE_RECORDED",
      worker: "CONFIRMED",
      localKillSwitchEngaged: true,
      requestedAt: "2026-08-26T08:22:00.000Z",
      workerAckAt: "2026-08-26T08:22:04.000Z",
      ackDeadlineAt: "2026-08-26T08:22:10.000Z",
    } as const;
    expect(EmergencyStopStateSchema.parse(state).worker).toBe("CONFIRMED");
    expect(
      EmergencyStopStateSchema.safeParse({
        ...state,
        localKillSwitchEngaged: false,
      }).success,
    ).toBe(false);
  });

  it("derives aggregate health from component states", () => {
    expect(
      deriveSystemHealthState([
        {
          code: "fixture.a",
          labelTh: "องค์ประกอบ ก",
          plane: "control_plane",
          state: "healthy",
          detail: "พร้อม",
          observedAt: "2026-08-26T08:22:31.000Z",
        },
        {
          code: "fixture.b",
          labelTh: "องค์ประกอบ ข",
          plane: "execution_plane",
          state: "failed",
          detail: "ล้มเหลว",
          observedAt: "2026-08-26T08:22:31.000Z",
        },
      ]),
    ).toBe("failed");
  });
});
