import {
  IdentifierSchema,
  IsoDateTimeSchema,
  PersistedPositionSchema,
  PersistedRiskCheckSchema,
  PersistedTradeProposalSchema,
  ResultCodeSchema,
  SafeWorkerTextSchema,
  SystemCommandStatusSchema,
  SystemCommandTargetResourceTypeSchema,
  SystemCommandTypeSchema,
  SystemHealthStateSchema,
  SystemPlaneSchema,
  UuidSchema,
  type Database,
  type PersistedPosition,
  type PersistedRiskCheck,
  type PersistedTradeProposal,
  type SystemCommandStatus,
  type SystemCommandTargetResourceType,
  type SystemCommandType,
  type SystemHealthState,
} from "@aurum/contracts";

type SystemPlane = Database["public"]["Enums"]["system_plane"];

/**
 * Every row type comes from the generated local schema. The mapper boundary
 * deliberately preserves Postgres snake_case until runtime validation succeeds.
 */
export type TradeProposalReadRow =
  Database["public"]["Tables"]["trade_proposals"]["Row"];
export type RiskCheckReadRow =
  Database["public"]["Tables"]["risk_checks"]["Row"];
export type PositionReadRow = Database["public"]["Tables"]["positions"]["Row"];
export type SystemComponentReadRow =
  Database["public"]["Tables"]["system_components"]["Row"];
export type SystemHeartbeatReadRow =
  Database["public"]["Tables"]["system_heartbeats"]["Row"];
/** Safe browser projection. It intentionally has no payload, lease token, or last error. */
export type SystemCommandProgressReadRow =
  Database["public"]["Views"]["system_command_read_models"]["Row"];

export interface ProposalReadModel {
  proposal: PersistedTradeProposal;
  riskChecks: readonly PersistedRiskCheck[];
}

export interface HeartbeatReadModel {
  id: string;
  workerId: string;
  reportedState: SystemHealthState;
  effectiveState: SystemHealthState;
  detail: string;
  observedAt: string;
  expiresAt: string;
  version: number;
  stale: boolean;
}

export interface ComponentHealthReadModel {
  id: string;
  code: string;
  labelTh: string;
  plane: SystemPlane;
  expectedHeartbeatSeconds: number | null;
  heartbeat: HeartbeatReadModel | null;
  effectiveState: SystemHealthState;
}

export interface ControlPlaneHealthReadModel {
  capturedAt: string;
  components: readonly ComponentHealthReadModel[];
}

export interface SystemCommandProgressReadModel {
  id: string;
  ownerId: string;
  type: SystemCommandType;
  payloadSchemaVersion: 1;
  status: SystemCommandStatus;
  requestedBy: string;
  requestedAt: string;
  targetResourceType: SystemCommandTargetResourceType | null;
  targetResourceId: string | null;
  expectedResourceVersion: number | null;
  idempotencyKey: string;
  priority: number;
  claimedAt: string | null;
  claimedBy: string | null;
  leaseExpiresAt: string | null;
  attemptCount: number;
  maximumAttempts: number;
  nextRetryAt: string | null;
  expiresAt: string;
  completedAt: string | null;
  resultCode: string | null;
  resultMessage: string | null;
  commandVersion: number;
  eventSequence: number;
  createdAt: string;
  updatedAt: string;
}

function requiredInteger(value: number | null, minimum: number): number {
  if (value === null || !Number.isInteger(value) || value < minimum) {
    throw new TypeError("Expected a bounded integer in a database read model.");
  }
  return value;
}

function optionalTimestamp(value: string | null): string | null {
  return value === null ? null : IsoDateTimeSchema.parse(value);
}

function optionalUuid(value: string | null): string | null {
  return value === null ? null : UuidSchema.parse(value);
}

const WORKER_IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/u;

function workerIdentifier(value: string): string {
  const identifier = IdentifierSchema.parse(value);
  const safeIdentifier = SafeWorkerTextSchema.parse(identifier);
  if (!WORKER_IDENTIFIER_PATTERN.test(safeIdentifier)) {
    throw new TypeError("Invalid Worker identifier in database read model.");
  }
  return safeIdentifier;
}

function optionalWorkerIdentifier(value: string | null): string | null {
  return value === null ? null : workerIdentifier(value);
}

function optionalResultCode(value: string | null): string | null {
  return value === null ? null : ResultCodeSchema.parse(value);
}

function optionalSafeWorkerText(value: string | null): string | null {
  return value === null ? null : SafeWorkerTextSchema.parse(value);
}

export function tradeProposalFromReadRow(
  row: TradeProposalReadRow,
): PersistedTradeProposal {
  return PersistedTradeProposalSchema.parse({
    id: row.id,
    ownerId: row.owner_id,
    proposalVersion: row.proposal_version,
    tradingAccountId: row.trading_account_id,
    brokerSymbolId: row.broker_symbol_id,
    riskPolicyVersionId: row.risk_policy_version_id,
    accountType: row.account_type,
    accountCurrency: row.account_currency,
    brokerServer: row.broker_server,
    canonicalSymbol: row.canonical_symbol,
    brokerSymbol: row.broker_symbol,
    symbolSpecificationVersion: row.symbol_specification_version,
    direction: row.direction,
    strategyCode: row.strategy_code,
    strategyVersion: row.strategy_version,
    modelVersion: row.model_version,
    eligibilityPolicyId: row.eligibility_policy_id,
    eligibilityPolicyVersion: row.eligibility_policy_version,
    eligibilityOutcome: row.eligibility_outcome,
    eligibilityEvaluatedAt: row.eligibility_evaluated_at,
    riskPolicyVersion: row.risk_policy_version,
    entryPrice: row.entry_price,
    stopLossPrice: row.stop_loss_price,
    takeProfitPrice: row.take_profit_price,
    calculatedVolume: row.calculated_volume,
    requestedVolume: row.requested_volume,
    approvedVolume: row.approved_volume,
    maximumPermittedVolume: row.maximum_permitted_volume,
    riskAmount: row.risk_amount,
    riskPct: row.risk_pct,
    riskReward: row.risk_reward,
    marketSnapshotId: row.market_snapshot_id,
    featureSnapshotId: row.feature_snapshot_id,
    decisionTraceId: row.decision_trace_id,
    status: row.status,
    createdAt: row.created_at,
    expiresAt: row.expires_at,
    processedAt: row.processed_at,
    updatedAt: row.updated_at,
  });
}

export function riskCheckFromReadRow(
  row: RiskCheckReadRow,
): PersistedRiskCheck {
  return PersistedRiskCheckSchema.parse({
    id: row.id,
    ownerId: row.owner_id,
    tradeProposalId: row.trade_proposal_id,
    proposalVersion: row.proposal_version,
    key: row.key,
    labelTh: row.label_th,
    labelEn: row.label_en,
    state: row.state,
    actual: row.actual,
    limitValue: row.limit_value,
    hard: row.hard,
    explanation: row.explanation,
    ordinal: row.ordinal,
    createdAt: row.created_at,
  });
}

export function positionFromReadRow(row: PositionReadRow): PersistedPosition {
  return PersistedPositionSchema.parse({
    id: row.id,
    ownerId: row.owner_id,
    tradingAccountId: row.trading_account_id,
    tradeProposalId: row.trade_proposal_id,
    brokerOrderId: row.broker_order_id,
    brokerPositionReference: row.broker_position_reference,
    positionVersion: row.position_version,
    direction: row.direction,
    volume: row.volume,
    entryPrice: row.entry_price,
    currentPrice: row.current_price,
    stopLossPrice: row.stop_loss_price,
    takeProfitPrice: row.take_profit_price,
    unrealizedPnl: row.unrealized_pnl,
    rMultiple: row.r_multiple,
    status: row.status,
    openedAt: row.opened_at,
    closedAt: row.closed_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  });
}

export function commandProgressFromReadRow(
  row: SystemCommandProgressReadRow,
): SystemCommandProgressReadModel {
  const payloadSchemaVersion = requiredInteger(row.payload_schema_version, 1);
  if (payloadSchemaVersion !== 1) {
    throw new TypeError("Unsupported command payload schema version.");
  }
  const targetResourceType =
    row.target_resource_type === null
      ? null
      : SystemCommandTargetResourceTypeSchema.parse(row.target_resource_type);

  return {
    id: UuidSchema.parse(row.id),
    ownerId: UuidSchema.parse(row.owner_id),
    type: SystemCommandTypeSchema.parse(row.type),
    payloadSchemaVersion,
    status: SystemCommandStatusSchema.parse(row.status),
    requestedBy: UuidSchema.parse(row.requested_by),
    requestedAt: IsoDateTimeSchema.parse(row.requested_at),
    targetResourceType,
    targetResourceId: optionalUuid(row.target_resource_id),
    expectedResourceVersion:
      row.expected_resource_version === null
        ? null
        : requiredInteger(row.expected_resource_version, 1),
    idempotencyKey: IdentifierSchema.parse(row.idempotency_key),
    priority: requiredInteger(row.priority, 0),
    claimedAt: optionalTimestamp(row.claimed_at),
    claimedBy: optionalWorkerIdentifier(row.claimed_by),
    leaseExpiresAt: optionalTimestamp(row.lease_expires_at),
    attemptCount: requiredInteger(row.attempt_count, 0),
    maximumAttempts: requiredInteger(row.maximum_attempts, 1),
    nextRetryAt: optionalTimestamp(row.next_retry_at),
    expiresAt: IsoDateTimeSchema.parse(row.expires_at),
    completedAt: optionalTimestamp(row.completed_at),
    resultCode: optionalResultCode(row.result_code),
    resultMessage: optionalSafeWorkerText(row.result_message),
    commandVersion: requiredInteger(row.command_version, 1),
    eventSequence: requiredInteger(row.event_sequence, 0),
    createdAt: IsoDateTimeSchema.parse(row.created_at),
    updatedAt: IsoDateTimeSchema.parse(row.updated_at),
  };
}

export function healthFromReadRows(
  componentRows: readonly SystemComponentReadRow[],
  heartbeatRows: readonly SystemHeartbeatReadRow[],
  capturedAt: string,
): ControlPlaneHealthReadModel | null {
  const validatedCapturedAt = IsoDateTimeSchema.parse(capturedAt);
  if (componentRows.length === 0) return null;

  const heartbeats = new Map<string, HeartbeatReadModel>();
  for (const row of heartbeatRows) {
    const componentId = UuidSchema.parse(row.system_component_id);
    if (heartbeats.has(componentId)) {
      throw new TypeError("Duplicate heartbeat row for a system component.");
    }
    const expiresAt = IsoDateTimeSchema.parse(row.expires_at);
    const stale = Date.parse(expiresAt) <= Date.parse(validatedCapturedAt);
    const reportedState = SystemHealthStateSchema.parse(row.state);
    const detail = SafeWorkerTextSchema.parse(row.detail);
    heartbeats.set(componentId, {
      id: UuidSchema.parse(row.id),
      workerId: workerIdentifier(row.worker_id),
      reportedState,
      effectiveState: stale ? "unknown" : reportedState,
      detail,
      observedAt: IsoDateTimeSchema.parse(row.observed_at),
      expiresAt,
      version: requiredInteger(row.version, 1),
      stale,
    });
  }

  return {
    capturedAt: validatedCapturedAt,
    components: componentRows.map((row) => {
      const id = UuidSchema.parse(row.id);
      const heartbeat = heartbeats.get(id) ?? null;
      const expectedHeartbeatSeconds = row.expected_heartbeat_seconds;
      if (
        expectedHeartbeatSeconds !== null &&
        (!Number.isInteger(expectedHeartbeatSeconds) ||
          expectedHeartbeatSeconds <= 0)
      ) {
        throw new TypeError("Invalid expected heartbeat interval.");
      }
      if (!row.enabled) {
        throw new TypeError(
          "Disabled components must be filtered by the read query.",
        );
      }
      return {
        id,
        code: IdentifierSchema.parse(row.code),
        labelTh: IdentifierSchema.parse(row.label_th),
        plane: SystemPlaneSchema.parse(row.plane),
        expectedHeartbeatSeconds,
        heartbeat,
        effectiveState: heartbeat?.effectiveState ?? "unknown",
      };
    }),
  };
}
