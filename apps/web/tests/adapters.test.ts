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

const OWNER_ID = "00000000-0000-4000-8000-000000000001";
const OTHER_OWNER_ID = "00000000-0000-4000-8000-000000000002";
const PROPOSAL_ID = "00000000-0000-4000-8000-000000000010";
const POSITION_ID = "00000000-0000-4000-8000-000000000020";
const COMMAND_ID = "00000000-0000-4000-8000-000000000030";
const COMPONENT_ID = "00000000-0000-4000-8000-000000000040";
const NOW = "2026-08-26T12:00:00.000Z";

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

  it("keeps absent and stale heartbeat evidence explicit", async () => {
    const components: SystemComponentReadRow[] = [
      {
        id: COMPONENT_ID,
        owner_id: OWNER_ID,
        code: "worker",
        label_th: "เวิร์กเกอร์",
        plane: "execution_plane",
        expected_heartbeat_seconds: 30,
        enabled: true,
        created_at: "2026-08-26T10:00:00.000Z",
      },
      {
        id: "00000000-0000-4000-8000-000000000041",
        owner_id: OWNER_ID,
        code: "database",
        label_th: "ฐานข้อมูล",
        plane: "control_plane",
        expected_heartbeat_seconds: null,
        enabled: true,
        created_at: "2026-08-26T10:00:00.000Z",
      },
    ];
    const heartbeat: SystemHeartbeatReadRow = {
      id: "00000000-0000-4000-8000-000000000042",
      owner_id: OWNER_ID,
      system_component_id: COMPONENT_ID,
      worker_id: "demo-worker",
      state: "healthy",
      detail: "Last reported healthy before expiry",
      observed_at: "2026-08-26T11:58:00.000Z",
      expires_at: "2026-08-26T11:59:00.000Z",
      version: 1,
      created_at: "2026-08-26T11:58:00.000Z",
      updated_at: "2026-08-26T11:58:00.000Z",
    };
    const gateway = new RecordingReadGateway(
      {},
      {
        system_components: success(components),
        system_heartbeats: success([heartbeat]),
      },
    );
    const adapter = new OwnerScopedControlPlaneReadAdapter(
      OWNER_ID,
      gateway,
      () => new Date(NOW),
    );

    const health = await adapter.getHealthSnapshot();

    expect(health).toMatchObject({ capturedAt: NOW });
    expect(health?.components[0]).toMatchObject({
      code: "worker",
      effectiveState: "unknown",
      heartbeat: {
        reportedState: "healthy",
        effectiveState: "unknown",
        stale: true,
      },
    });
    expect(health?.components[1]).toMatchObject({
      code: "database",
      effectiveState: "unknown",
      heartbeat: null,
    });
    expectOwnerScope(gateway.queries);
  });

  it("fails closed on unsafe Worker identifiers and heartbeat detail", async () => {
    const component: SystemComponentReadRow = {
      id: COMPONENT_ID,
      owner_id: OWNER_ID,
      code: "worker",
      label_th: "เวิร์กเกอร์",
      plane: "execution_plane",
      expected_heartbeat_seconds: 30,
      enabled: true,
      created_at: "2026-08-26T10:00:00.000Z",
    };
    const heartbeat: SystemHeartbeatReadRow = {
      id: "00000000-0000-4000-8000-000000000042",
      owner_id: OWNER_ID,
      system_component_id: COMPONENT_ID,
      worker_id: "demo-worker",
      state: "healthy",
      detail: "Healthy",
      observed_at: "2026-08-26T11:58:00.000Z",
      expires_at: "2026-08-26T12:01:00.000Z",
      version: 1,
      created_at: "2026-08-26T11:58:00.000Z",
      updated_at: "2026-08-26T11:58:00.000Z",
    };

    for (const unsafeHeartbeat of [
      { ...heartbeat, worker_id: "worker id with spaces" },
      { ...heartbeat, detail: "token=private-value" },
    ]) {
      const gateway = new RecordingReadGateway(
        {},
        {
          system_components: success([component]),
          system_heartbeats: success([unsafeHeartbeat]),
        },
      );
      const adapter = new OwnerScopedControlPlaneReadAdapter(
        OWNER_ID,
        gateway,
        () => new Date(NOW),
      );
      await expect(adapter.getHealthSnapshot()).rejects.toMatchObject({
        code: "INVALID_READ_DATA",
        relation: "system_components",
      });
    }
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
        "getPosition",
        "getProposal",
      ].sort(),
    );
  });
});
