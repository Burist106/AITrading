import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  EMERGENCY_STOP_CONTROL_PLANE_STATES,
  EMERGENCY_STOP_WORKER_STATES,
  POSITION_STATUSES,
  PersistedPositionSchema,
  PersistedRiskCheckSchema,
  PersistedTradeProposalSchema,
  RISK_CHECK_STATES,
  RISK_POLICY_ACTOR_TYPES,
  RISK_POLICY_NUMERIC_RULE_KEYS,
  RiskCheckSchema,
  RiskPolicyVersionSchema,
  SYSTEM_COMMAND_STATUSES,
  SYSTEM_COMMAND_TARGET_RESOURCE_TYPES,
  SYSTEM_COMMAND_TYPES,
  SYSTEM_HEALTH_STATES,
  SYSTEM_PLANES,
  SignalEvidenceSchema,
  SystemCommandPayloadEnvelopeSchema,
  SystemCommandSchema,
  TRADE_PROPOSAL_STATUSES,
  PositionSchema,
  deriveSystemHealthState,
  positionFromPersisted,
  riskCheckFromPersisted,
} from "../src";

type JsonObject = Record<string, unknown>;

interface PayloadCase {
  caseId: string;
  type: string;
  payload: unknown;
}

interface EnvelopeCase {
  caseId: string;
  value: JsonObject;
}

interface InvalidEnvelopeCase {
  caseId: string;
  patchValidCase: string;
  patch?: JsonObject;
  remove?: string[];
}

interface RuleChange {
  ruleKey: string;
  newValue: number;
}

interface SegmentedFixture {
  parts: string[];
  separator: string;
}

interface ParityCorpus {
  schemaVersion: 1;
  domainSets: Record<string, string[]>;
  validPayloads: PayloadCase[];
  invalidPayloads: PayloadCase[];
  validRiskPolicyRuleChanges: RuleChange[];
  invalidRiskPolicyRuleChanges: RuleChange[];
  envelopeDefaults: JsonObject;
  validEnvelopes: EnvelopeCase[];
  unsafeResultCodes: SegmentedFixture[];
  invalidEnvelopes: InvalidEnvelopeCase[];
  domainRecords: {
    riskCheck: unknown;
    persistedRiskCheck: unknown;
    position: unknown;
    persistedPosition: unknown;
    persistedTradeProposal: unknown;
    riskPolicy: unknown;
  };
}

const corpus = JSON.parse(
  readFileSync(
    new URL(
      "../../../contract-fixtures/v1/domain-parity.json",
      import.meta.url,
    ),
    "utf8",
  ),
) as ParityCorpus;

const domainManifest = {
  commandTypes: [...SYSTEM_COMMAND_TYPES],
  commandStatuses: [...SYSTEM_COMMAND_STATUSES],
  commandTargetResourceTypes: [...SYSTEM_COMMAND_TARGET_RESOURCE_TYPES],
  tradeProposalStatuses: [...TRADE_PROPOSAL_STATUSES],
  positionStatuses: [...POSITION_STATUSES],
  riskCheckStates: [...RISK_CHECK_STATES],
  riskPolicyNumericRuleKeys: [...RISK_POLICY_NUMERIC_RULE_KEYS],
  riskPolicyActorTypes: [...RISK_POLICY_ACTOR_TYPES],
  systemHealthStates: [...SYSTEM_HEALTH_STATES],
  systemPlanes: [...SYSTEM_PLANES],
  emergencyStopControlPlaneStates: [...EMERGENCY_STOP_CONTROL_PLANE_STATES],
  emergencyStopWorkerStates: [...EMERGENCY_STOP_WORKER_STATES],
};

describe("shared SQL/TypeScript/Python parity corpus", () => {
  it("matches every canonical TypeScript domain set in exact order", () => {
    expect(corpus.schemaVersion).toBe(1);
    expect(domainManifest).toEqual(corpus.domainSets);
  });

  it("accepts all nine valid typed command payloads", () => {
    expect(corpus.validPayloads).toHaveLength(SYSTEM_COMMAND_TYPES.length);
    expect(corpus.validPayloads.map(({ type }) => type)).toEqual(
      SYSTEM_COMMAND_TYPES,
    );
    for (const fixture of corpus.validPayloads) {
      expect(
        SystemCommandPayloadEnvelopeSchema.safeParse({
          type: fixture.type,
          payload: fixture.payload,
        }).success,
        fixture.caseId,
      ).toBe(true);
    }
  });

  it("rejects every invalid typed command payload", () => {
    expect(corpus.invalidPayloads.map(({ type }) => type)).toEqual(
      SYSTEM_COMMAND_TYPES,
    );
    for (const fixture of corpus.invalidPayloads) {
      expect(
        SystemCommandPayloadEnvelopeSchema.safeParse({
          type: fixture.type,
          payload: fixture.payload,
        }).success,
        fixture.caseId,
      ).toBe(false);
    }
  });

  it("enforces the SQL-aligned bound for every mutable risk rule", () => {
    for (const change of corpus.validRiskPolicyRuleChanges) {
      expect(
        SystemCommandPayloadEnvelopeSchema.safeParse({
          type: "REQUEST_RISK_POLICY_CHANGE",
          payload: { ...change, reason: "Parity boundary fixture" },
        }).success,
        `valid ${change.ruleKey}`,
      ).toBe(true);
    }
    for (const change of corpus.invalidRiskPolicyRuleChanges) {
      expect(
        SystemCommandPayloadEnvelopeSchema.safeParse({
          type: "REQUEST_RISK_POLICY_CHANGE",
          payload: { ...change, reason: "Parity boundary fixture" },
        }).success,
        `invalid ${change.ruleKey}`,
      ).toBe(false);
    }
  });

  it("accepts every valid lifecycle envelope", () => {
    expect(corpus.validEnvelopes.map(({ caseId }) => caseId)).toEqual(
      SYSTEM_COMMAND_STATUSES,
    );
    for (const fixture of corpus.validEnvelopes) {
      const value = { ...corpus.envelopeDefaults, ...fixture.value };
      expect(SystemCommandSchema.safeParse(value).success, fixture.caseId).toBe(
        true,
      );
    }
    const succeeded = corpus.validEnvelopes.find(
      ({ caseId }) => caseId === "succeeded",
    );
    if (!succeeded) throw new Error("Missing succeeded parity case");
    const longResult = {
      ...corpus.envelopeDefaults,
      ...succeeded.value,
      resultMessage: "x".repeat(512),
    };
    expect(SystemCommandSchema.safeParse(longResult).success).toBe(true);
    expect(
      SystemCommandSchema.safeParse({
        ...longResult,
        resultMessage: "x".repeat(513),
      }).success,
    ).toBe(false);
  });

  it("rejects every invalid lifecycle, target, and idempotency envelope", () => {
    for (const fixture of corpus.invalidEnvelopes) {
      const base = corpus.validEnvelopes.find(
        ({ caseId }) => caseId === fixture.patchValidCase,
      );
      if (!base)
        throw new Error(`Missing base case: ${fixture.patchValidCase}`);
      const value = structuredClone({
        ...corpus.envelopeDefaults,
        ...base.value,
        ...fixture.patch,
      });
      for (const field of fixture.remove ?? []) delete value[field];
      expect(SystemCommandSchema.safeParse(value).success, fixture.caseId).toBe(
        false,
      );
    }

    const succeededFixture = corpus.validEnvelopes.find(
      ({ caseId }) => caseId === "succeeded",
    );
    if (!succeededFixture) throw new Error("Missing succeeded parity case");
    const succeeded = {
      ...corpus.envelopeDefaults,
      ...succeededFixture.value,
    };
    for (const unsafeResultMessage of [
      "sk-" + "1234567890abcdefghijklmnop",
      ["eyJabcdefghijk", "eyJmnopqrstuv", "wxyzABCDEFGHI"].join("."),
    ]) {
      expect(
        SystemCommandSchema.safeParse({
          ...succeeded,
          resultMessage: unsafeResultMessage,
        }).success,
      ).toBe(false);
    }
    for (const fixture of corpus.unsafeResultCodes) {
      expect(
        SystemCommandSchema.safeParse({
          ...succeeded,
          resultCode: fixture.parts.join(fixture.separator),
        }).success,
      ).toBe(false);
    }
  });

  it("validates shared read-side records and the explicit risk-check mapper", () => {
    expect(RiskCheckSchema.parse(corpus.domainRecords.riskCheck).state).toBe(
      "pass",
    );
    const longRiskCheck = {
      ...(corpus.domainRecords.riskCheck as JsonObject),
      actual: "x".repeat(512),
    };
    expect(RiskCheckSchema.safeParse(longRiskCheck).success).toBe(true);
    expect(
      RiskCheckSchema.safeParse({ ...longRiskCheck, actual: "x".repeat(513) })
        .success,
    ).toBe(false);
    const persisted = PersistedRiskCheckSchema.parse(
      corpus.domainRecords.persistedRiskCheck,
    );
    expect(riskCheckFromPersisted(persisted)).toMatchObject({
      key: "maximum_spread",
      limit: "3.50 points",
    });
    expect(PositionSchema.parse(corpus.domainRecords.position).status).toBe(
      "open",
    );
    const persistedPosition = PersistedPositionSchema.parse(
      corpus.domainRecords.persistedPosition,
    );
    expect(positionFromPersisted(persistedPosition)).toMatchObject({
      accountType: "demo",
      canonicalSymbol: "XAUUSD",
      entry: 2405.85,
    });
    const persistedTradeProposal = PersistedTradeProposalSchema.parse(
      corpus.domainRecords.persistedTradeProposal,
    );
    expect(persistedTradeProposal.eligibilityOutcome).toBe("ask");
    expect("eligibility" in persistedTradeProposal).toBe(false);
    expect(
      PersistedTradeProposalSchema.safeParse({
        ...(corpus.domainRecords.persistedTradeProposal as JsonObject),
        maximumPermittedVolume: 0.005,
      }).success,
    ).toBe(false);
    expect(
      PersistedTradeProposalSchema.safeParse({
        ...(corpus.domainRecords.persistedTradeProposal as JsonObject),
        requestedVolume: 0.005,
        approvedVolume: 0.01,
      }).success,
    ).toBe(false);
    const riskPolicy = RiskPolicyVersionSchema.parse(
      corpus.domainRecords.riskPolicy,
    );
    expect(riskPolicy.maximumPermittedVolume).toBe(0.01);
    for (const patch of [
      { minimumRiskReward: 10_000 },
      { newsBlackoutMinutes: 2_147_483_648 },
    ]) {
      expect(
        RiskPolicyVersionSchema.safeParse({
          ...(corpus.domainRecords.riskPolicy as JsonObject),
          ...patch,
        }).success,
      ).toBe(false);
    }
  });

  it("keeps calibration and empty-health behavior aligned with Python", () => {
    expect(
      SignalEvidenceSchema.safeParse({
        qualityScore: 71,
        calibratedProbability: 0.8,
        calibrationStatus: "not_calibrated",
        similarSampleCount: 24,
        minimumRequiredSampleCount: 30,
        strategyVersion: "fixture-v1",
      }).success,
    ).toBe(false);
    expect(deriveSystemHealthState([])).toBe("unknown");
  });
});
