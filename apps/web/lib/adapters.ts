import { UuidSchema, type PersistedPosition } from "@aurum/contracts";

import {
  commandProgressFromReadRow,
  healthFromReadRows,
  positionFromReadRow,
  riskCheckFromReadRow,
  tradeProposalFromReadRow,
  type ControlPlaneHealthReadModel,
  type PositionReadRow,
  type ProposalReadModel,
  type RiskCheckReadRow,
  type SystemCommandProgressReadModel,
  type SystemCommandProgressReadRow,
  type SystemComponentReadRow,
  type SystemHeartbeatReadRow,
  type TradeProposalReadRow,
} from "./control-plane-read-models";

export interface ControlPlaneReadRowMap {
  trade_proposals: TradeProposalReadRow;
  risk_checks: RiskCheckReadRow;
  positions: PositionReadRow;
  system_components: SystemComponentReadRow;
  system_heartbeats: SystemHeartbeatReadRow;
  system_command_read_models: SystemCommandProgressReadRow;
}

export type ControlPlaneReadRelation = keyof ControlPlaneReadRowMap;
type ReadColumn<Relation extends ControlPlaneReadRelation> = Extract<
  keyof ControlPlaneReadRowMap[Relation],
  string
>;

export type EqualityReadFilter<Relation extends ControlPlaneReadRelation> = {
  [Column in ReadColumn<Relation>]: Readonly<{
    column: Column;
    value: ControlPlaneReadRowMap[Relation][Column];
  }>;
}[ReadColumn<Relation>];

interface OwnerFilter {
  readonly column: "owner_id";
  readonly value: string;
}

export interface OwnerScopedReadQuery<
  Relation extends ControlPlaneReadRelation,
> {
  readonly relation: Relation;
  readonly columns: readonly ReadColumn<Relation>[];
  /** Required even though forced RLS remains the authoritative boundary. */
  readonly ownerFilter: OwnerFilter;
  readonly filters: readonly EqualityReadFilter<Relation>[];
  readonly orderBy?: Readonly<{
    column: ReadColumn<Relation>;
    ascending: boolean;
  }>;
}

export interface ReadGatewayError {
  readonly code?: string;
  readonly message: string;
}

export type ReadGatewayResult<Value> =
  | Readonly<{ data: Value; error: null }>
  | Readonly<{ data: null; error: ReadGatewayError }>;

/**
 * Narrow capability injected around an authenticated browser client. There is
 * intentionally no insert, update, delete, RPC, credential, or service-role API.
 */
export interface ControlPlaneReadGateway {
  selectOne<Relation extends ControlPlaneReadRelation>(
    query: OwnerScopedReadQuery<Relation>,
  ): Promise<ReadGatewayResult<ControlPlaneReadRowMap[Relation] | null>>;

  selectMany<Relation extends ControlPlaneReadRelation>(
    query: OwnerScopedReadQuery<Relation>,
  ): Promise<ReadGatewayResult<readonly ControlPlaneReadRowMap[Relation][]>>;
}

export type ControlPlaneReadErrorCode =
  "READ_FAILED" | "INVALID_READ_DATA" | "INVALID_READ_REQUEST";

export class ControlPlaneReadError extends Error {
  readonly code: ControlPlaneReadErrorCode;
  readonly relation: ControlPlaneReadRelation;

  constructor(
    code: ControlPlaneReadErrorCode,
    relation: ControlPlaneReadRelation,
  ) {
    super(`Control-plane ${relation} read failed closed (${code}).`);
    this.name = "ControlPlaneReadError";
    this.code = code;
    this.relation = relation;
  }
}

const TRADE_PROPOSAL_COLUMNS = [
  "id",
  "owner_id",
  "proposal_version",
  "trading_account_id",
  "broker_symbol_id",
  "risk_policy_version_id",
  "account_type",
  "account_currency",
  "broker_server",
  "canonical_symbol",
  "broker_symbol",
  "symbol_specification_version",
  "direction",
  "strategy_code",
  "strategy_version",
  "model_version",
  "eligibility_policy_id",
  "eligibility_policy_version",
  "eligibility_outcome",
  "eligibility_evaluated_at",
  "risk_policy_version",
  "entry_price",
  "stop_loss_price",
  "take_profit_price",
  "calculated_volume",
  "requested_volume",
  "approved_volume",
  "maximum_permitted_volume",
  "risk_amount",
  "risk_pct",
  "risk_reward",
  "market_snapshot_id",
  "feature_snapshot_id",
  "decision_trace_id",
  "status",
  "created_at",
  "expires_at",
  "processed_at",
  "updated_at",
] as const satisfies readonly (keyof TradeProposalReadRow)[];

const RISK_CHECK_COLUMNS = [
  "id",
  "owner_id",
  "trade_proposal_id",
  "proposal_version",
  "key",
  "label_th",
  "label_en",
  "state",
  "actual",
  "limit_value",
  "hard",
  "explanation",
  "ordinal",
  "created_at",
] as const satisfies readonly (keyof RiskCheckReadRow)[];

const POSITION_COLUMNS = [
  "id",
  "owner_id",
  "trading_account_id",
  "trade_proposal_id",
  "broker_order_id",
  "broker_position_reference",
  "position_version",
  "direction",
  "volume",
  "entry_price",
  "current_price",
  "stop_loss_price",
  "take_profit_price",
  "unrealized_pnl",
  "r_multiple",
  "status",
  "opened_at",
  "closed_at",
  "created_at",
  "updated_at",
] as const satisfies readonly (keyof PositionReadRow)[];

const SYSTEM_COMPONENT_COLUMNS = [
  "id",
  "owner_id",
  "code",
  "label_th",
  "plane",
  "expected_heartbeat_seconds",
  "enabled",
  "created_at",
] as const satisfies readonly (keyof SystemComponentReadRow)[];

const SYSTEM_HEARTBEAT_COLUMNS = [
  "id",
  "owner_id",
  "system_component_id",
  "worker_id",
  "state",
  "detail",
  "observed_at",
  "expires_at",
  "version",
  "created_at",
  "updated_at",
] as const satisfies readonly (keyof SystemHeartbeatReadRow)[];

/** No payload, lease_token, or last_error may enter the browser projection. */
export const SYSTEM_COMMAND_PROGRESS_COLUMNS = [
  "id",
  "owner_id",
  "type",
  "payload_schema_version",
  "status",
  "requested_by",
  "requested_at",
  "target_resource_type",
  "target_resource_id",
  "expected_resource_version",
  "idempotency_key",
  "priority",
  "claimed_at",
  "claimed_by",
  "lease_expires_at",
  "attempt_count",
  "maximum_attempts",
  "next_retry_at",
  "expires_at",
  "completed_at",
  "result_code",
  "result_message",
  "command_version",
  "event_sequence",
  "created_at",
  "updated_at",
] as const satisfies readonly (keyof SystemCommandProgressReadRow)[];

function unwrapRead<Value>(
  relation: ControlPlaneReadRelation,
  result: ReadGatewayResult<Value>,
): Value {
  if (result.error !== null) {
    // Raw database messages can contain internal detail and are not propagated.
    throw new ControlPlaneReadError("READ_FAILED", relation);
  }
  return result.data;
}

async function readFromGateway<Value>(
  relation: ControlPlaneReadRelation,
  operation: () => Promise<ReadGatewayResult<Value>>,
): Promise<Value> {
  try {
    return unwrapRead(relation, await operation());
  } catch (error) {
    if (error instanceof ControlPlaneReadError) throw error;
    // Promise rejections can also contain driver/SQL detail; never propagate it.
    throw new ControlPlaneReadError("READ_FAILED", relation);
  }
}

function mapRead<Value>(
  relation: ControlPlaneReadRelation,
  mapper: () => Value,
): Value {
  try {
    return mapper();
  } catch (error) {
    if (error instanceof ControlPlaneReadError) throw error;
    throw new ControlPlaneReadError("INVALID_READ_DATA", relation);
  }
}

function parseReadId(
  relation: ControlPlaneReadRelation,
  value: string,
): string {
  const parsed = UuidSchema.safeParse(value);
  if (!parsed.success) {
    throw new ControlPlaneReadError("INVALID_READ_REQUEST", relation);
  }
  return parsed.data;
}

function requireOwner(
  relation: ControlPlaneReadRelation,
  expectedOwnerId: string,
  actualOwnerId: string | null,
): void {
  if (actualOwnerId !== expectedOwnerId) {
    throw new ControlPlaneReadError("INVALID_READ_DATA", relation);
  }
}

/**
 * Owner-scoped, read-only Milestone 1 repository. It does not wire the fixture
 * UI to Supabase and cannot submit an intent or mutate operational state.
 */
export interface ReadOnlyControlPlaneAdapter {
  getHealthSnapshot(): Promise<ControlPlaneHealthReadModel | null>;
  getProposal(proposalId: string): Promise<ProposalReadModel | null>;
  getPosition(positionId: string): Promise<PersistedPosition | null>;
  getCommandProgress(
    commandId: string,
  ): Promise<SystemCommandProgressReadModel | null>;
}

export class OwnerScopedControlPlaneReadAdapter implements ReadOnlyControlPlaneAdapter {
  readonly #ownerId: string;
  readonly #gateway: ControlPlaneReadGateway;
  readonly #clock: () => Date;

  constructor(
    ownerId: string,
    gateway: ControlPlaneReadGateway,
    clock: () => Date = () => new Date(),
  ) {
    const parsedOwnerId = UuidSchema.safeParse(ownerId);
    if (!parsedOwnerId.success) {
      throw new ControlPlaneReadError(
        "INVALID_READ_REQUEST",
        "trade_proposals",
      );
    }
    this.#ownerId = parsedOwnerId.data;
    this.#gateway = gateway;
    this.#clock = clock;
  }

  async getProposal(proposalId: string): Promise<ProposalReadModel | null> {
    const validatedProposalId = parseReadId("trade_proposals", proposalId);
    const proposalRow = await readFromGateway("trade_proposals", () =>
      this.#gateway.selectOne({
        relation: "trade_proposals",
        columns: TRADE_PROPOSAL_COLUMNS,
        ownerFilter: { column: "owner_id", value: this.#ownerId },
        filters: [{ column: "id", value: validatedProposalId }],
      }),
    );
    if (proposalRow === null) return null;

    requireOwner("trade_proposals", this.#ownerId, proposalRow.owner_id);
    const proposal = mapRead("trade_proposals", () =>
      tradeProposalFromReadRow(proposalRow),
    );

    const riskCheckRows = await readFromGateway("risk_checks", () =>
      this.#gateway.selectMany({
        relation: "risk_checks",
        columns: RISK_CHECK_COLUMNS,
        ownerFilter: { column: "owner_id", value: this.#ownerId },
        filters: [
          { column: "trade_proposal_id", value: validatedProposalId },
          { column: "proposal_version", value: proposal.proposalVersion },
        ],
        orderBy: { column: "ordinal", ascending: true },
      }),
    );
    const riskChecks = mapRead("risk_checks", () =>
      riskCheckRows.map((row) => {
        requireOwner("risk_checks", this.#ownerId, row.owner_id);
        if (
          row.trade_proposal_id !== proposal.id ||
          row.proposal_version !== proposal.proposalVersion
        ) {
          throw new TypeError("Risk check does not belong to the proposal.");
        }
        return riskCheckFromReadRow(row);
      }),
    );

    return { proposal, riskChecks };
  }

  async getPosition(positionId: string): Promise<PersistedPosition | null> {
    const validatedPositionId = parseReadId("positions", positionId);
    const row = await readFromGateway("positions", () =>
      this.#gateway.selectOne({
        relation: "positions",
        columns: POSITION_COLUMNS,
        ownerFilter: { column: "owner_id", value: this.#ownerId },
        filters: [{ column: "id", value: validatedPositionId }],
      }),
    );
    if (row === null) return null;
    requireOwner("positions", this.#ownerId, row.owner_id);
    return mapRead("positions", () => positionFromReadRow(row));
  }

  async getCommandProgress(
    commandId: string,
  ): Promise<SystemCommandProgressReadModel | null> {
    const validatedCommandId = parseReadId(
      "system_command_read_models",
      commandId,
    );
    const row = await readFromGateway("system_command_read_models", () =>
      this.#gateway.selectOne({
        relation: "system_command_read_models",
        columns: SYSTEM_COMMAND_PROGRESS_COLUMNS,
        ownerFilter: { column: "owner_id", value: this.#ownerId },
        filters: [{ column: "id", value: validatedCommandId }],
      }),
    );
    if (row === null) return null;
    requireOwner("system_command_read_models", this.#ownerId, row.owner_id);
    return mapRead("system_command_read_models", () =>
      commandProgressFromReadRow(row),
    );
  }

  async getHealthSnapshot(): Promise<ControlPlaneHealthReadModel | null> {
    const [componentRows, heartbeatRows] = await Promise.all([
      readFromGateway("system_components", () =>
        this.#gateway.selectMany({
          relation: "system_components",
          columns: SYSTEM_COMPONENT_COLUMNS,
          ownerFilter: { column: "owner_id", value: this.#ownerId },
          filters: [{ column: "enabled", value: true }],
          orderBy: { column: "code", ascending: true },
        }),
      ),
      readFromGateway("system_heartbeats", () =>
        this.#gateway.selectMany({
          relation: "system_heartbeats",
          columns: SYSTEM_HEARTBEAT_COLUMNS,
          ownerFilter: { column: "owner_id", value: this.#ownerId },
          filters: [],
          orderBy: { column: "observed_at", ascending: false },
        }),
      ),
    ]);

    for (const row of componentRows) {
      requireOwner("system_components", this.#ownerId, row.owner_id);
    }
    for (const row of heartbeatRows) {
      requireOwner("system_heartbeats", this.#ownerId, row.owner_id);
    }

    return mapRead("system_components", () =>
      healthFromReadRows(
        componentRows,
        heartbeatRows,
        this.#clock().toISOString(),
      ),
    );
  }
}

/** Local placeholder used while the P0 shell remains fixture-driven. */
export class UnavailableControlPlaneAdapter implements ReadOnlyControlPlaneAdapter {
  async getHealthSnapshot(): Promise<null> {
    return null;
  }

  async getProposal(proposalId: string): Promise<null> {
    void proposalId;
    return null;
  }

  async getPosition(positionId: string): Promise<null> {
    void positionId;
    return null;
  }

  async getCommandProgress(commandId: string): Promise<null> {
    void commandId;
    return null;
  }
}
