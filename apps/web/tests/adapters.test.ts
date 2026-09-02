import { describe, expect, it } from "vitest";

import {
  ControlPlaneReadError,
  OwnerScopedControlPlaneReadAdapter,
  SYSTEM_COMMAND_PROGRESS_COLUMNS,
  type ControlPlaneReadGateway,
  type ControlPlaneReadRelation,
  type ControlPlaneReadRowMap,
  type OwnerScopedReadQuery,
  type ReadGatewayResult,
} from "../lib/adapters";
import type {
  PositionReadRow,
  RiskCheckReadRow,
  SystemCommandProgressReadRow,
  SystemComponentReadRow,
  SystemHeartbeatReadRow,
  TradeProposalReadRow,
} from "../lib/control-plane-read-models";
import { mt5ConsoleFromReadRows } from "../lib/mt5-read-models";

const OWNER_ID = "00000000-0000-4000-8000-000000000001";
const OTHER_OWNER_ID = "00000000-0000-4000-8000-000000000002";
const PROPOSAL_ID = "00000000-0000-4000-8000-000000000010";
const POSITION_ID = "00000000-0000-4000-8000-000000000020";
const COMMAND_ID = "00000000-0000-4000-8000-000000000030";
const COMPONENT_ID = "00000000-0000-4000-8000-000000000040";
const MT5_ADAPTER_COMPONENT_ID = "00000000-0000-4000-8000-000000000041";
const MARKET_DATA_COMPONENT_ID = "00000000-0000-4000-8000-000000000042";
const NOW = "2026-08-26T12:00:00.000Z";
const HISTORY_START = "2026-08-25T12:00:00.000Z";

const executionComponents: SystemComponentReadRow[] = [
  {
    id: COMPONENT_ID,
    owner_id: OWNER_ID,
    code: "execution.worker",
    label_th: "Aurum Worker",
    plane: "execution_plane",
    expected_heartbeat_seconds: 15,
    enabled: true,
    created_at: "2026-08-26T10:00:00.000Z",
  },
  {
    id: MT5_ADAPTER_COMPONENT_ID,
    owner_id: OWNER_ID,
    code: "execution.mt5_adapter",
    label_th: "การเชื่อมต่อ MT5",
    plane: "execution_plane",
    expected_heartbeat_seconds: 15,
    enabled: true,
    created_at: "2026-08-26T10:00:00.000Z",
  },
  {
    id: MARKET_DATA_COMPONENT_ID,
    owner_id: OWNER_ID,
    code: "execution.market_data",
    label_th: "ข้อมูลตลาด XAU/USD",
    plane: "execution_plane",
    expected_heartbeat_seconds: 15,
    enabled: true,
    created_at: "2026-08-26T10:00:00.000Z",
  },
];

function heartbeatRow(
  componentId: string,
  heartbeatId: string,
  overrides: Partial<SystemHeartbeatReadRow> = {},
): SystemHeartbeatReadRow {
  return {
    id: heartbeatId,
    owner_id: OWNER_ID,
    system_component_id: componentId,
    worker_id: "demo-worker",
    state: "healthy",
    detail: "HEALTHY",
    observed_at: "2026-08-26T11:59:45.000Z",
    expires_at: "2026-08-26T12:00:15.000Z",
    version: 2,
    created_at: "2026-08-26T11:58:00.000Z",
    updated_at: "2026-08-26T11:59:45.000Z",
    ...overrides,
  };
}

const proposalRow: TradeProposalReadRow = {
  id: PROPOSAL_ID,
  owner_id: OWNER_ID,
  proposal_version: 3,
  trading_account_id: "00000000-0000-4000-8000-000000000011",
  broker_symbol_id: "00000000-0000-4000-8000-000000000012",
  risk_policy_version_id: "00000000-0000-4000-8000-000000000013",
  account_type: "demo",
  account_currency: "USD",
  broker_server: "Aurum-Demo",
  canonical_symbol: "XAUUSD",
  broker_symbol: "XAUUSD.a",
  symbol_specification_version: "spec-v1",
  direction: "BUY",
  strategy_code: "shadow_baseline",
  strategy_version: "strategy-v1",
  model_version: null,
  eligibility_policy_id: "shadow-policy",
  eligibility_policy_version: "eligibility-v1",
  eligibility_outcome: "ask",
  eligibility_evaluated_at: "2026-08-26T11:00:00.000Z",
  risk_policy_version: "risk-v1",
  entry_price: 2310,
  stop_loss_price: 2300,
  take_profit_price: 2330,
  calculated_volume: 0.01,
  requested_volume: 0.01,
  approved_volume: null,
  maximum_permitted_volume: 0.01,
  risk_amount: 5.5,
  risk_pct: 0.25,
  risk_reward: 2,
  market_snapshot_id: "00000000-0000-4000-8000-000000000014",
  feature_snapshot_id: "00000000-0000-4000-8000-000000000015",
  decision_trace_id: "00000000-0000-4000-8000-000000000016",
  status: "pending_approval",
  created_at: "2026-08-26T11:00:00.000Z",
  expires_at: "2026-08-26T11:15:00.000Z",
  processed_at: null,
  updated_at: "2026-08-26T11:01:00.000Z",
};

const riskCheckRow: RiskCheckReadRow = {
  id: "00000000-0000-4000-8000-000000000017",
  owner_id: OWNER_ID,
  trade_proposal_id: PROPOSAL_ID,
  proposal_version: 3,
  key: "maximum_volume",
  label_th: "ขนาดสูงสุด",
  label_en: "Maximum volume",
  state: "pass",
  actual: "0.01 lots",
  limit_value: "<= 0.01 lots",
  hard: true,
  explanation: null,
  ordinal: 0,
  created_at: "2026-08-26T11:00:01.000Z",
};

const positionRow: PositionReadRow = {
  id: POSITION_ID,
  owner_id: OWNER_ID,
  trading_account_id: "00000000-0000-4000-8000-000000000011",
  trade_proposal_id: PROPOSAL_ID,
  broker_order_id: "00000000-0000-4000-8000-000000000021",
  broker_position_reference: "DEMO-POSITION-1",
  position_version: 2,
  direction: "BUY",
  volume: 0.01,
  entry_price: 2310,
  current_price: 2312,
  stop_loss_price: 2300,
  take_profit_price: 2330,
  unrealized_pnl: 2,
  r_multiple: 0.2,
  status: "open",
  opened_at: "2026-08-26T11:30:00.000Z",
  closed_at: null,
  created_at: "2026-08-26T11:30:00.000Z",
  updated_at: "2026-08-26T11:59:00.000Z",
};

const commandRow: SystemCommandProgressReadRow = {
  id: COMMAND_ID,
  owner_id: OWNER_ID,
  type: "PAUSE_NEW_TRADES",
  payload_schema_version: 1,
  status: "pending",
  requested_by: OWNER_ID,
  requested_at: "2026-08-26T11:50:00.000Z",
  target_resource_type: null,
  target_resource_id: null,
  expected_resource_version: null,
  idempotency_key: "pause-20260826",
  priority: 90,
  claimed_at: null,
  claimed_by: null,
  lease_expires_at: null,
  attempt_count: 0,
  maximum_attempts: 3,
  next_retry_at: null,
  expires_at: "2026-08-26T12:05:00.000Z",
  completed_at: null,
  result_code: null,
  result_message: null,
  command_version: 1,
  event_sequence: 0,
  created_at: "2026-08-26T11:50:00.000Z",
  updated_at: "2026-08-26T11:50:00.000Z",
};

interface RecordedQuery {
  readonly relation: ControlPlaneReadRelation;
  readonly columns: readonly string[];
  readonly ownerFilter: Readonly<{ column: "owner_id"; value: string }>;
  readonly filters: readonly Readonly<{ column: string; value: unknown }>[];
}

type ResponseByRelation = Partial<
  Record<ControlPlaneReadRelation, ReadGatewayResult<unknown>>
>;

function success<Value>(data: Value): ReadGatewayResult<Value> {
  return { data, error: null };
}

class RecordingReadGateway implements ControlPlaneReadGateway {
  readonly queries: RecordedQuery[] = [];

  constructor(
    private readonly one: ResponseByRelation = {},
    private readonly many: ResponseByRelation = {},
    private readonly rejectedOne: Partial<
      Record<ControlPlaneReadRelation, string>
    > = {},
    private readonly rejectedMany: Partial<
      Record<ControlPlaneReadRelation, string>
    > = {},
  ) {}

  async selectOne<Relation extends ControlPlaneReadRelation>(
    query: OwnerScopedReadQuery<Relation>,
  ): Promise<ReadGatewayResult<ControlPlaneReadRowMap[Relation] | null>> {
    this.queries.push(query);
    const rejection = this.rejectedOne[query.relation];
    if (rejection !== undefined) throw new Error(rejection);
    const response = this.one[query.relation] ?? success(null);
    return response as ReadGatewayResult<
      ControlPlaneReadRowMap[Relation] | null
    >;
  }

  async selectMany<Relation extends ControlPlaneReadRelation>(
    query: OwnerScopedReadQuery<Relation>,
  ): Promise<ReadGatewayResult<readonly ControlPlaneReadRowMap[Relation][]>> {
    this.queries.push(query);
    const rejection = this.rejectedMany[query.relation];
    if (rejection !== undefined) throw new Error(rejection);
    const response = this.many[query.relation] ?? success([]);
    return response as ReadGatewayResult<
      readonly ControlPlaneReadRowMap[Relation][]
    >;
  }
}

function expectOwnerScope(queries: readonly RecordedQuery[]): void {
  expect(queries.length).toBeGreaterThan(0);
  for (const query of queries) {
    expect(query.ownerFilter).toEqual({
      column: "owner_id",
      value: OWNER_ID,
    });
  }
}

describe("owner-scoped control-plane reads", () => {
  it("maps owner-scoped sanitized MT5 observations without privileged fields", async () => {
    const account: ControlPlaneReadRowMap["mt5_account_observations"] = {
      id: "00000000-0000-4000-8000-000000000051",
      owner_id: OWNER_ID,
      worker_id: "worker-fixture",
      account_fingerprint: "mt5-account-v1:fixture",
      server_fingerprint: "mt5-server-v1:fixture",
      masked_login: "••••3456",
      masked_server: "demo…a91f",
      trade_mode: "demo",
      verification_state: "verified_demo_bound",
      currency: "USD",
      leverage: 100,
      observed_at: NOW,
      source: "fake_mt5",
      adapter_version: "fake-v1",
      trace_id: "trace-mt5",
      schema_version: "1",
      created_at: NOW,
    };
    const symbol: ControlPlaneReadRowMap["mt5_symbol_observations"] = {
      id: "00000000-0000-4000-8000-000000000052",
      owner_id: OWNER_ID,
      worker_id: "worker-fixture",
      account_fingerprint: "mt5-account-v1:fixture",
      canonical_symbol: "XAUUSD",
      broker_symbol: "XAUUSD",
      specification_fingerprint: "mt5-spec-v1:fixture",
      normalized_specification: {
        base_currency: "XAU",
        profit_currency: "USD",
        point: "0.01",
        tick_size: "0.01",
        contract_size: "100",
        minimum_volume: "0.01",
        maximum_volume: "100",
        volume_step: "0.01",
      },
      usability_state: "usable",
      unusable_reason: null,
      observed_at: NOW,
      source: "fake_mt5",
      adapter_version: "fake-v1",
      trace_id: "trace-mt5",
      schema_version: "1",
      created_at: NOW,
    };
    const tick: ControlPlaneReadRowMap["mt5_latest_tick_observations"] = {
      id: "00000000-0000-4000-8000-000000000053",
      owner_id: OWNER_ID,
      worker_id: "worker-fixture",
      account_fingerprint: "mt5-account-v1:fixture",
      broker_symbol: "XAUUSD",
      bid: 2345.1,
      ask: 2345.3,
      spread_price: 0.2,
      spread_points: 20,
      tick_at: NOW,
      observed_at: NOW,
      age_seconds: 1,
      freshness: "live",
      source: "fake_mt5",
      adapter_version: "fake-v1",
      trace_id: "trace-mt5",
      schema_version: "1",
      version: 1,
      created_at: NOW,
      updated_at: NOW,
    };
    const reconciliation: ControlPlaneReadRowMap["mt5_reconciliation_runs"] = {
      id: "00000000-0000-4000-8000-000000000054",
      owner_id: OWNER_ID,
      worker_id: "worker-fixture",
      status: "completed",
      outcome: "matched",
      reason_code: "HEALTHY",
      account_fingerprint: "mt5-account-v1:fixture",
      server_fingerprint: "mt5-server-v1:fixture",
      broker_symbol: "XAUUSD",
      symbol_specification_fingerprint: "mt5-spec-v1:fixture",
      open_position_count: 0,
      active_order_count: 0,
      order_history_count: 0,
      deal_history_count: 0,
      mismatch_count: 0,
      report_hash: "a".repeat(32),
      trace_id: "trace-mt5",
      started_at: NOW,
      completed_at: NOW,
      created_at: NOW,
      updated_at: NOW,
    };
    const historyEvidence: ControlPlaneReadRowMap["mt5_history_query_evidence"][] =
      (["orders", "deals"] as const).map((historyKind, index) => ({
        id: `00000000-0000-4000-8000-00000000005${5 + index}`,
        owner_id: OWNER_ID,
        reconciliation_id: reconciliation.id,
        history_kind: historyKind,
        requested_start_at: HISTORY_START,
        requested_end_at: NOW,
        query_completed_at: NOW,
        returned_count: 0,
        earliest_returned_at: null,
        latest_returned_at: null,
        result_state: "empty_valid_result",
        reason_code: "HISTORY_EMPTY_VALID_RESULT",
        created_at: NOW,
      }));
    const gateway = new RecordingReadGateway(
      {
        mt5_account_observations: success(account),
        mt5_symbol_observations: success(symbol),
        mt5_latest_tick_observations: success(tick),
        mt5_reconciliation_runs: success(reconciliation),
      },
      { mt5_history_query_evidence: success(historyEvidence) },
    );
    const adapter = new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      gateway,
      () => new Date(NOW),
    );

    const model = await adapter.getMt5Console();

    expect(model.health.state).toBe("healthy");
    expect(model.account?.maskedLogin).toBe("••••3456");
    expect(model.symbol).toMatchObject({
      brokerSymbol: "XAUUSD",
      currencyBase: "XAU",
      currencyProfit: "USD",
    });
    expect(model.tick?.bid).toBe("2345.1");
    expect(model.reconciliation?.historyEvidence).toHaveLength(2);
    expect(model).not.toHaveProperty("worker_id");
    expect(model).not.toHaveProperty("report_hash");
    expectOwnerScope(gateway.queries);
    expect(gateway.queries).toHaveLength(6);

    const beforeReconciliation = await new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      new RecordingReadGateway({
        mt5_account_observations: success(account),
        mt5_symbol_observations: success(symbol),
        mt5_latest_tick_observations: success(tick),
        mt5_reconciliation_runs: success(null),
      }),
      () => new Date(NOW),
    ).getMt5Console();
    expect(beforeReconciliation.health).toMatchObject({
      state: "blocked",
      reasonCode: "RECONCILIATION_REQUIRED",
    });

    const staleObservation = await new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      gateway,
      () => new Date(Date.parse(NOW) + 61_000),
    ).getMt5Console();
    expect(staleObservation.health).toMatchObject({
      state: "unavailable",
      reasonCode: "MT5_OBSERVATION_STALE",
      packageAvailable: false,
      terminalConnected: false,
      lastSuccessfulObservationAt: null,
    });

    for (const [freshness, reasonCode] of [
      ["delayed", "TICK_DELAYED"],
      ["unavailable", "TICK_UNAVAILABLE"],
    ] as const) {
      expect(
        mt5ConsoleFromReadRows(
          {
            account,
            symbol,
            tick: { ...tick, freshness },
            reconciliation,
            mismatches: [],
            historyEvidence,
          },
          new Date(NOW),
        ).health,
      ).toMatchObject({ state: "blocked", reasonCode });
    }

    expect(
      mt5ConsoleFromReadRows(
        {
          account,
          symbol: null,
          tick,
          reconciliation,
          mismatches: [],
          historyEvidence,
        },
        new Date(NOW),
      ).health,
    ).toMatchObject({
      state: "blocked",
      reasonCode: "SYMBOL_OBSERVATION_UNAVAILABLE",
    });
    expect(
      mt5ConsoleFromReadRows(
        {
          account,
          symbol: {
            ...symbol,
            usability_state: "not_visible",
            unusable_reason: "SYMBOL_NOT_VISIBLE",
          },
          tick,
          reconciliation,
          mismatches: [],
          historyEvidence,
        },
        new Date(NOW),
      ).health,
    ).toMatchObject({ state: "blocked", reasonCode: "SYMBOL_NOT_VISIBLE" });

    for (const inconsistentRows of [
      { symbol: { ...symbol, account_fingerprint: "mt5-account-v1:changed" } },
      { tick: { ...tick, account_fingerprint: "mt5-account-v1:changed" } },
      {
        symbol: {
          ...symbol,
          specification_fingerprint: "mt5-spec-v1:changed",
        },
      },
      {
        reconciliation: {
          ...reconciliation,
          server_fingerprint: "mt5-server-v1:changed",
        },
      },
    ]) {
      expect(
        mt5ConsoleFromReadRows(
          {
            account,
            symbol,
            tick,
            reconciliation,
            mismatches: [],
            historyEvidence,
            ...inconsistentRows,
          },
          new Date(NOW),
        ).health,
      ).toMatchObject({
        state: "blocked",
        reasonCode: "RECONCILIATION_OBSERVATION_MISMATCH",
      });
    }

    const mismatch: ControlPlaneReadRowMap["mt5_reconciliation_mismatches"] = {
      id: "00000000-0000-4000-8000-000000000057",
      owner_id: OWNER_ID,
      reconciliation_id: reconciliation.id,
      category: "ACCOUNT_CHANGED",
      severity: "critical",
      resource_type: "account",
      resource_reference: "mt5-account-v1:fixture",
      reason_code: "ACCOUNT_CHANGED",
      resolution_state: "open",
      worker_id: "worker-fixture",
      created_at: NOW,
    };
    const otherReconciliationId = "00000000-0000-4000-8000-000000000058";
    const baseSingles = {
      mt5_account_observations: success(account),
      mt5_symbol_observations: success(symbol),
      mt5_latest_tick_observations: success(tick),
      mt5_reconciliation_runs: success(reconciliation),
    };

    for (const [relation, mismatchRows, evidenceRows] of [
      [
        "mt5_reconciliation_mismatches",
        [{ ...mismatch, owner_id: OTHER_OWNER_ID }],
        historyEvidence,
      ],
      [
        "mt5_reconciliation_mismatches",
        [{ ...mismatch, reconciliation_id: otherReconciliationId }],
        historyEvidence,
      ],
      [
        "mt5_history_query_evidence",
        [],
        [{ ...historyEvidence[0]!, owner_id: OTHER_OWNER_ID }],
      ],
      [
        "mt5_history_query_evidence",
        [],
        [
          {
            ...historyEvidence[0]!,
            reconciliation_id: otherReconciliationId,
          },
        ],
      ],
    ] as const) {
      const invalidChildAdapter = new OwnerScopedControlPlaneReadAdapter(
        OWNER_ID,
        new RecordingReadGateway(baseSingles, {
          mt5_reconciliation_mismatches: success(mismatchRows),
          mt5_history_query_evidence: success(evidenceRows),
        }),
        () => new Date(NOW),
      );
      await expect(invalidChildAdapter.getMt5Console()).rejects.toMatchObject({
        code: "INVALID_READ_DATA",
        relation,
      });
    }
  });

  it("maps snake_case proposal and risk evidence without fabricating a full proposal", async () => {
    const gateway = new RecordingReadGateway(
      { trade_proposals: success(proposalRow) },
      { risk_checks: success([riskCheckRow]) },
    );
    const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);

    const result = await adapter.getProposal(PROPOSAL_ID);

    expect(result?.proposal).toMatchObject({
      ownerId: OWNER_ID,
      proposalVersion: 3,
      accountType: "demo",
      maximumPermittedVolume: 0.01,
      eligibilityOutcome: "ask",
    });
    expect(result?.proposal).not.toHaveProperty("eligibility");
    expect(result?.riskChecks).toEqual([
      expect.objectContaining({
        tradeProposalId: PROPOSAL_ID,
        labelTh: "ขนาดสูงสุด",
        limitValue: "<= 0.01 lots",
      }),
    ]);
    expect(gateway.queries[0]?.filters).toEqual([
      { column: "id", value: PROPOSAL_ID },
    ]);
    expect(gateway.queries[1]?.filters).toEqual([
      { column: "trade_proposal_id", value: PROPOSAL_ID },
      { column: "proposal_version", value: 3 },
    ]);
    expectOwnerScope(gateway.queries);
  });

  it("returns null for a missing proposal without querying child evidence", async () => {
    const gateway = new RecordingReadGateway({
      trade_proposals: success(null),
    });
    const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);

    await expect(adapter.getProposal(PROPOSAL_ID)).resolves.toBeNull();
    expect(gateway.queries.map(({ relation }) => relation)).toEqual([
      "trade_proposals",
    ]);
  });

  it("fails closed and does not expose raw gateway error detail", async () => {
    const gateway = new RecordingReadGateway({
      trade_proposals: {
        data: null,
        error: {
          code: "XX000",
          message: "internal database detail that must stay private",
        },
      },
    });
    const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);

    const error = await adapter
      .getProposal(PROPOSAL_ID)
      .catch((caught) => caught);
    expect(error).toBeInstanceOf(ControlPlaneReadError);
    expect(error).toMatchObject({
      code: "READ_FAILED",
      relation: "trade_proposals",
    });
    expect(String(error)).not.toContain("internal database detail");
  });

  it.each(["system_components", "system_heartbeats"] as const)(
    "sanitizes a Promise rejection from the %s health branch",
    async (relation) => {
      const privateDetail =
        "postgresql://worker:private-password@internal-host/database";
      const gateway = new RecordingReadGateway(
        {},
        {
          system_components: success([]),
          system_heartbeats: success([]),
        },
        {},
        { [relation]: privateDetail },
      );
      const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);

      const error = await adapter.getHealthSnapshot().catch((caught) => caught);

      expect(error).toBeInstanceOf(ControlPlaneReadError);
      expect(error).toMatchObject({ code: "READ_FAILED", relation });
      expect(String(error)).not.toContain(privateDetail);
    },
  );

  it("rejects a row that does not belong to the authenticated owner", async () => {
    const gateway = new RecordingReadGateway({
      trade_proposals: success({
        ...proposalRow,
        owner_id: OTHER_OWNER_ID,
      }),
    });
    const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);

    await expect(adapter.getProposal(PROPOSAL_ID)).rejects.toMatchObject({
      code: "INVALID_READ_DATA",
      relation: "trade_proposals",
    });
  });

  it("maps Position rows and rejects malformed request ids before I/O", async () => {
    const gateway = new RecordingReadGateway({
      positions: success(positionRow),
    });
    const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);

    await expect(adapter.getPosition(POSITION_ID)).resolves.toMatchObject({
      id: POSITION_ID,
      ownerId: OWNER_ID,
      brokerPositionReference: "DEMO-POSITION-1",
      entryPrice: 2310,
      currentPrice: 2312,
      status: "open",
    });
    await expect(adapter.getPosition("not-a-uuid")).rejects.toMatchObject({
      code: "INVALID_READ_REQUEST",
    });
    expect(gateway.queries).toHaveLength(1);
    expectOwnerScope(gateway.queries);
  });

  it("keeps expired and missing heartbeats unknown, then honors lightweight renewal", async () => {
    const expiredRows = [
      heartbeatRow(COMPONENT_ID, "00000000-0000-4000-8000-000000000043", {
        observed_at: "2026-08-26T11:59:00.000Z",
        expires_at: "2026-08-26T11:59:30.000Z",
        version: 1,
      }),
      heartbeatRow(
        MT5_ADAPTER_COMPONENT_ID,
        "00000000-0000-4000-8000-000000000044",
        {
          observed_at: "2026-08-26T11:59:00.000Z",
          expires_at: "2026-08-26T11:59:30.000Z",
          version: 1,
        },
      ),
    ];
    const expiredGateway = new RecordingReadGateway(
      {},
      {
        system_components: success(executionComponents),
        system_heartbeats: success(expiredRows),
      },
    );
    const expired = await new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      expiredGateway,
      () => new Date(NOW),
    ).getHealthSnapshot();

    expect(
      expired?.components.map(({ effectiveState }) => effectiveState),
    ).toEqual(["unknown", "unknown", "unknown"]);
    expect(expired?.components[0]?.heartbeat).toMatchObject({
      reportedState: "healthy",
      effectiveState: "unknown",
      stale: true,
    });
    expect(expired?.components[2]?.heartbeat).toBeNull();

    const renewedRows = [
      heartbeatRow(COMPONENT_ID, "00000000-0000-4000-8000-000000000043", {
        state: "failed",
        detail: "RECONCILIATION_INCOMPLETE",
      }),
      heartbeatRow(
        MT5_ADAPTER_COMPONENT_ID,
        "00000000-0000-4000-8000-000000000044",
      ),
      heartbeatRow(
        MARKET_DATA_COMPONENT_ID,
        "00000000-0000-4000-8000-000000000045",
        { state: "degraded", detail: "TICK_DELAYED" },
      ),
    ];
    const renewedGateway = new RecordingReadGateway(
      {},
      {
        system_components: success(executionComponents),
        system_heartbeats: success(renewedRows),
      },
    );
    const renewed = await new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      renewedGateway,
      () => new Date(NOW),
    ).getHealthSnapshot();

    expect(renewed).toMatchObject({ capturedAt: NOW });
    expect(
      renewed?.components.map(({ code, labelTh, effectiveState }) => ({
        code,
        labelTh,
        effectiveState,
      })),
    ).toEqual([
      {
        code: "execution.worker",
        labelTh: "Aurum Worker",
        effectiveState: "failed",
      },
      {
        code: "execution.mt5_adapter",
        labelTh: "การเชื่อมต่อ MT5",
        effectiveState: "healthy",
      },
      {
        code: "execution.market_data",
        labelTh: "ข้อมูลตลาด XAU/USD",
        effectiveState: "degraded",
      },
    ]);
    expect(renewed?.components[0]?.heartbeat).toMatchObject({
      reportedState: "failed",
      effectiveState: "failed",
      stale: false,
    });
    expect(renewed?.components[2]?.heartbeat).toMatchObject({
      reportedState: "degraded",
      effectiveState: "degraded",
      detail: "TICK_DELAYED",
      stale: false,
    });
    expectOwnerScope(expiredGateway.queries);
    expectOwnerScope(renewedGateway.queries);
  });

  it("derives unknown from unvalidated heartbeat rows without exposing detail", async () => {
    const unsafeDetail = "Traceback at C:\\Private\\terminal64.exe";
    const valid = heartbeatRow(
      COMPONENT_ID,
      "00000000-0000-4000-8000-000000000043",
    );
    const invalidRows: SystemHeartbeatReadRow[] = [
      { ...valid, worker_id: "worker id with spaces" },
      { ...valid, detail: unsafeDetail },
      { ...valid, detail: "token=private-value" },
      { ...valid, state: "unknown" },
      { ...valid, state: "warning" },
      { ...valid, expires_at: "2026-08-26T11:59:30.000Z" },
      {
        ...valid,
        observed_at: NOW,
        expires_at: "2026-08-26T12:00:14.000Z",
      },
      {
        ...valid,
        observed_at: NOW,
        expires_at: "2026-08-26T12:00:30.500Z",
      },
      {
        ...valid,
        observed_at: NOW,
        expires_at: "2026-08-26T12:05:01.000Z",
      },
      {
        ...valid,
        observed_at: NOW,
        expires_at: "2027-08-26T12:00:00.000Z",
      },
      { ...valid, state: "healthy", detail: "TICK_STALE" },
      { ...valid, state: "failed", detail: "HEALTHY" },
      { ...valid, id: "not-a-uuid" },
      { ...valid, version: 0 },
    ];

    for (const invalidRow of invalidRows) {
      const gateway = new RecordingReadGateway(
        {},
        {
          system_components: success([executionComponents[0]!]),
          system_heartbeats: success([invalidRow]),
        },
      );
      const health = await new OwnerScopedControlPlaneReadAdapter(
        OWNER_ID,
        gateway,
        () => new Date(NOW),
      ).getHealthSnapshot();

      expect(health?.components[0]).toMatchObject({
        effectiveState: "unknown",
        heartbeat: null,
      });
      expect(JSON.stringify(health)).not.toContain(unsafeDetail);
      expect(JSON.stringify(health)).not.toContain("private-value");
    }

    const invalidMarketGateway = new RecordingReadGateway(
      {},
      {
        system_components: success([executionComponents[2]!]),
        system_heartbeats: success([
          heartbeatRow(
            MARKET_DATA_COMPONENT_ID,
            "00000000-0000-4000-8000-000000000045",
            { state: "degraded", detail: "DEMO_ACCOUNT_UNBOUND" },
          ),
        ]),
      },
    );
    const invalidMarket = await new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      invalidMarketGateway,
      () => new Date(NOW),
    ).getHealthSnapshot();
    expect(invalidMarket?.components[0]).toMatchObject({
      effectiveState: "unknown",
      heartbeat: null,
    });

    const invalidFailedMarketGateway = new RecordingReadGateway(
      {},
      {
        system_components: success([executionComponents[2]!]),
        system_heartbeats: success([
          heartbeatRow(
            MARKET_DATA_COMPONENT_ID,
            "00000000-0000-4000-8000-000000000045",
            { state: "failed", detail: "REAL_ACCOUNT_BLOCKED" },
          ),
        ]),
      },
    );
    const invalidFailedMarket = await new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      invalidFailedMarketGateway,
      () => new Date(NOW),
    ).getHealthSnapshot();
    expect(invalidFailedMarket?.components[0]).toMatchObject({
      effectiveState: "unknown",
      heartbeat: null,
    });

    const duplicateGateway = new RecordingReadGateway(
      {},
      {
        system_components: success([executionComponents[0]!]),
        system_heartbeats: success([
          valid,
          {
            ...valid,
            id: "00000000-0000-4000-8000-000000000046",
          },
        ]),
      },
    );
    const duplicate = await new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      duplicateGateway,
      () => new Date(NOW),
    ).getHealthSnapshot();
    expect(duplicate?.components[0]).toMatchObject({
      effectiveState: "unknown",
      heartbeat: null,
    });
  });

  it("derives unknown from future-dated heartbeat evidence", async () => {
    const gateway = new RecordingReadGateway(
      {},
      {
        system_components: success([executionComponents[0]!]),
        system_heartbeats: success([
          heartbeatRow(COMPONENT_ID, "00000000-0000-4000-8000-000000000043", {
            observed_at: "2026-08-26T12:00:30.000Z",
            expires_at: "2026-08-26T12:01:00.000Z",
          }),
        ]),
      },
    );

    const health = await new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      gateway,
      () => new Date(NOW),
    ).getHealthSnapshot();

    expect(health?.components[0]).toMatchObject({
      effectiveState: "unknown",
      heartbeat: null,
    });
  });

  it.each([
    [15, "2026-08-26T12:00:15.000Z"],
    [300, "2026-08-26T12:05:00.000Z"],
  ])(
    "accepts an exact %i-second heartbeat validity boundary",
    async (_validitySeconds, expiresAt) => {
      const gateway = new RecordingReadGateway(
        {},
        {
          system_components: success([executionComponents[0]!]),
          system_heartbeats: success([
            heartbeatRow(COMPONENT_ID, "00000000-0000-4000-8000-000000000043", {
              observed_at: NOW,
              expires_at: expiresAt,
            }),
          ]),
        },
      );

      const health = await new OwnerScopedControlPlaneReadAdapter(
        OWNER_ID,
        gateway,
        () => new Date(NOW),
      ).getHealthSnapshot();

      expect(health?.components[0]).toMatchObject({
        effectiveState: "healthy",
        heartbeat: {
          effectiveState: "healthy",
          stale: false,
        },
      });
    },
  );

  it("still fails closed on heartbeat ownership violations", async () => {
    const gateway = new RecordingReadGateway(
      {},
      {
        system_components: success([executionComponents[0]!]),
        system_heartbeats: success([
          heartbeatRow(COMPONENT_ID, "00000000-0000-4000-8000-000000000043", {
            owner_id: OTHER_OWNER_ID,
          }),
        ]),
      },
    );
    const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);

    await expect(adapter.getHealthSnapshot()).rejects.toMatchObject({
      code: "INVALID_READ_DATA",
      relation: "system_heartbeats",
    });
  });

  it("reads only the safe command-progress projection", async () => {
    const gateway = new RecordingReadGateway({
      system_command_read_models: success(commandRow),
    });
    const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);

    await expect(adapter.getCommandProgress(COMMAND_ID)).resolves.toMatchObject(
      {
        id: COMMAND_ID,
        type: "PAUSE_NEW_TRADES",
        status: "pending",
        payloadSchemaVersion: 1,
      },
    );
    expect(SYSTEM_COMMAND_PROGRESS_COLUMNS).not.toContain("payload");
    expect(SYSTEM_COMMAND_PROGRESS_COLUMNS).not.toContain("lease_token");
    expect(SYSTEM_COMMAND_PROGRESS_COLUMNS).not.toContain("last_error");
    expectOwnerScope(gateway.queries);
  });

  it("fails closed on unsafe Worker-originated command text", async () => {
    const unsafeRows: SystemCommandProgressReadRow[] = [
      { ...commandRow, claimed_by: "worker id with spaces" },
      { ...commandRow, result_code: "lowercase_code" },
      { ...commandRow, result_message: "authorization: private-value" },
    ];

    for (const row of unsafeRows) {
      const gateway = new RecordingReadGateway({
        system_command_read_models: success(row),
      });
      const adapter = new OwnerScopedControlPlaneReadAdapter(OWNER_ID, gateway);
      await expect(
        adapter.getCommandProgress(COMMAND_ID),
      ).rejects.toMatchObject({
        code: "INVALID_READ_DATA",
        relation: "system_command_read_models",
      });
    }
  });

  it("exposes read methods only", () => {
    expect(
      Object.getOwnPropertyNames(
        OwnerScopedControlPlaneReadAdapter.prototype,
      ).sort(),
    ).toEqual(
      [
        "constructor",
        "getCommandProgress",
        "getHealthSnapshot",
        "getMt5Console",
        "getPosition",
        "getProposal",
      ].sort(),
    );
  });
});
