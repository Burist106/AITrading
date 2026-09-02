import { describe, expect, expectTypeOf, it } from "vitest";

import {
  POSITION_STATUSES,
  RISK_CHECK_STATES,
  SYSTEM_COMMAND_STATUSES,
  SYSTEM_COMMAND_TYPES,
  TRADE_PROPOSAL_STATUSES,
  type Database,
  type Json,
  type PositionStatus,
  type RiskCheckState,
  type SystemCommandStatus,
  type SystemCommandType,
} from "../src";

const TABLE_NAMES = [
  "audit_logs",
  "broker_orders",
  "broker_symbols",
  "feature_snapshots",
  "market_snapshots",
  "mt5_account_observations",
  "mt5_history_query_evidence",
  "mt5_latest_tick_observations",
  "mt5_reconciliation_mismatches",
  "mt5_reconciliation_runs",
  "mt5_symbol_observations",
  "position_events",
  "positions",
  "profiles",
  "risk_checks",
  "risk_policies",
  "risk_policy_versions",
  "system_command_events",
  "system_commands",
  "system_components",
  "system_heartbeats",
  "system_incidents",
  "trade_decisions",
  "trade_executions",
  "trade_proposals",
  "trading_accounts",
  "trading_modes",
] as const;

const COMMAND_VIEW_COLUMNS = [
  "attempt_count",
  "claimed_at",
  "claimed_by",
  "command_version",
  "completed_at",
  "created_at",
  "event_sequence",
  "expected_resource_version",
  "expires_at",
  "id",
  "idempotency_key",
  "lease_expires_at",
  "maximum_attempts",
  "next_retry_at",
  "owner_id",
  "payload_schema_version",
  "priority",
  "requested_at",
  "requested_by",
  "result_code",
  "result_message",
  "status",
  "target_resource_id",
  "target_resource_type",
  "type",
  "updated_at",
] as const;

const USER_FUNCTION_NAMES = [
  "request_emergency_stop",
  "request_pause_new_trades",
  "request_position_close",
  "request_proposal_approval",
  "request_proposal_rejection",
  "request_resume_system",
  "request_risk_policy_change",
  "request_stop_loss_change",
  "request_take_profit_change",
] as const;

const WORKER_FUNCTION_NAMES = [
  "worker_begin_reconciliation",
  "worker_claim_next_command",
  "worker_complete_reconciliation",
  "worker_complete_command",
  "worker_fail_command",
  "worker_mark_command_executing",
  "worker_mark_command_validating",
  "worker_record_heartbeat",
  "worker_record_incident",
  "worker_read_mt5_reconciliation_state",
  "worker_record_mt5_account_observation",
  "worker_record_mt5_symbol_observation",
  "worker_record_reconciliation_mismatch",
  "worker_reject_command",
  "worker_renew_command_lease",
  "worker_upsert_mt5_latest_tick",
] as const;

const FUNCTION_NAMES = [
  ...USER_FUNCTION_NAMES,
  ...WORKER_FUNCTION_NAMES,
] as const;

const COMPOSITE_TYPE_NAMES = [
  "command_action_result",
  "worker_action_result",
  "worker_claim_result",
  "worker_incident_result",
] as const;

const WORKER_CLAIM_RESULT_COLUMNS = [
  "accepted",
  "command_id",
  "status",
  "lease_token",
  "lease_expires_at",
  "command_version",
  "result_code",
] as const;

const WORKER_INCIDENT_RESULT_COLUMNS = [
  "accepted",
  "incident_id",
  "created",
  "result_code",
] as const;

describe("generated database type parity", () => {
  it("keeps canonical command and risk-domain enum unions exact", () => {
    expectTypeOf<
      Database["public"]["Enums"]["system_command_type"]
    >().toEqualTypeOf<SystemCommandType>();
    expectTypeOf<
      Database["public"]["Enums"]["system_command_status"]
    >().toEqualTypeOf<SystemCommandStatus>();
    expectTypeOf<
      Database["public"]["Enums"]["risk_check_state"]
    >().toEqualTypeOf<RiskCheckState>();
    expectTypeOf<
      Database["public"]["Enums"]["trade_proposal_status"]
    >().toEqualTypeOf<(typeof TRADE_PROPOSAL_STATUSES)[number]>();
    expectTypeOf<
      Database["public"]["Enums"]["position_status"]
    >().toEqualTypeOf<PositionStatus>();

    expect(SYSTEM_COMMAND_TYPES).toHaveLength(9);
    expect(SYSTEM_COMMAND_STATUSES).toHaveLength(9);
    expect(RISK_CHECK_STATES).toEqual(["pass", "warn", "fail", "na"]);
    expect(TRADE_PROPOSAL_STATUSES).toHaveLength(10);
    expect(POSITION_STATUSES).toHaveLength(5);
  });

  it("contains exactly the 27 Milestone 2 tables", () => {
    expectTypeOf<keyof Database["public"]["Tables"]>().toEqualTypeOf<
      (typeof TABLE_NAMES)[number]
    >();
    expect(TABLE_NAMES).toHaveLength(27);
    expect(TABLE_NAMES).not.toContain("notifications");
    expect(TABLE_NAMES).not.toContain("candles");
    expect(TABLE_NAMES).not.toContain("strategies");
    expect(TABLE_NAMES).not.toContain("model_registry");
  });

  it("keeps the command view exact and omits privileged fields", () => {
    type CommandView =
      Database["public"]["Views"]["system_command_read_models"]["Row"];

    expectTypeOf<
      keyof Database["public"]["Views"]
    >().toEqualTypeOf<"system_command_read_models">();
    expectTypeOf<keyof CommandView>().toEqualTypeOf<
      (typeof COMMAND_VIEW_COLUMNS)[number]
    >();
    expect(COMMAND_VIEW_COLUMNS).not.toContain("payload");
    expect(COMMAND_VIEW_COLUMNS).not.toContain("lease_token");
    expect(COMMAND_VIEW_COLUMNS).not.toContain("last_error");
    expect(COMMAND_VIEW_COLUMNS).toHaveLength(26);
  });

  it("contains all and only nine user plus sixteen Worker functions", () => {
    expectTypeOf<keyof Database["public"]["Functions"]>().toEqualTypeOf<
      (typeof FUNCTION_NAMES)[number]
    >();
    expect(USER_FUNCTION_NAMES).toHaveLength(9);
    expect(WORKER_FUNCTION_NAMES).toHaveLength(16);
    expect(FUNCTION_NAMES).toHaveLength(25);
  });

  it("preserves important row nullability and safety columns", () => {
    type Command = Database["public"]["Tables"]["system_commands"]["Row"];
    type CommandView =
      Database["public"]["Views"]["system_command_read_models"]["Row"];
    type Proposal = Database["public"]["Tables"]["trade_proposals"]["Row"];
    type Position = Database["public"]["Tables"]["positions"]["Row"];
    type RiskPolicy =
      Database["public"]["Tables"]["risk_policy_versions"]["Row"];

    expectTypeOf<Command["owner_id"]>().toEqualTypeOf<string>();
    expectTypeOf<Command["payload"]>().toEqualTypeOf<Json>();
    expectTypeOf<Command["claimed_by"]>().toEqualTypeOf<string | null>();
    expectTypeOf<Command["lease_token"]>().toEqualTypeOf<string | null>();
    expectTypeOf<CommandView["id"]>().toEqualTypeOf<string | null>();
    expectTypeOf<CommandView["result_code"]>().toEqualTypeOf<string | null>();

    expectTypeOf<Proposal["approved_volume"]>().toEqualTypeOf<number | null>();
    expectTypeOf<
      Proposal["maximum_permitted_volume"]
    >().toEqualTypeOf<number>();
    expectTypeOf<Position["stop_loss_price"]>().toEqualTypeOf<number>();
    expectTypeOf<Position["closed_at"]>().toEqualTypeOf<string | null>();
    expectTypeOf<
      RiskPolicy["maximum_permitted_volume"]
    >().toEqualTypeOf<number>();
    expectTypeOf<
      RiskPolicy["maximum_open_positions"]
    >().toEqualTypeOf<number>();
    expectTypeOf<RiskPolicy["stop_loss_required"]>().toEqualTypeOf<boolean>();
  });

  it("keeps critical intent and Worker function arguments typed", () => {
    type ApprovalArgs =
      Database["public"]["Functions"]["request_proposal_approval"]["Args"];
    type CompleteArgs =
      Database["public"]["Functions"]["worker_complete_command"]["Args"];

    expectTypeOf<ApprovalArgs>().toEqualTypeOf<{
      approval_session_id?: string;
      command_expires_at?: string;
      idempotency_key: string;
      proposal_id: string;
      proposal_version: number;
    }>();
    expectTypeOf<CompleteArgs>().toEqualTypeOf<{
      command_id: string;
      lease_token: string;
      result_code: string;
      result_message?: string;
    }>();
  });

  it("keeps the exact payload-free Worker result envelopes", () => {
    type CompositeTypes = Database["public"]["CompositeTypes"];
    type WorkerClaimResult = CompositeTypes["worker_claim_result"];
    type WorkerIncidentResult = CompositeTypes["worker_incident_result"];

    expectTypeOf<keyof CompositeTypes>().toEqualTypeOf<
      (typeof COMPOSITE_TYPE_NAMES)[number]
    >();
    expectTypeOf<keyof WorkerClaimResult>().toEqualTypeOf<
      (typeof WORKER_CLAIM_RESULT_COLUMNS)[number]
    >();
    expectTypeOf<keyof WorkerIncidentResult>().toEqualTypeOf<
      (typeof WORKER_INCIDENT_RESULT_COLUMNS)[number]
    >();
    expectTypeOf<WorkerClaimResult>().toEqualTypeOf<{
      accepted: boolean | null;
      command_id: string | null;
      status: SystemCommandStatus | null;
      lease_token: string | null;
      lease_expires_at: string | null;
      command_version: number | null;
      result_code: string | null;
    }>();
    expectTypeOf<WorkerIncidentResult>().toEqualTypeOf<{
      accepted: boolean | null;
      incident_id: string | null;
      created: boolean | null;
      result_code: string | null;
    }>();

    expect(COMPOSITE_TYPE_NAMES).toHaveLength(4);
    expect(WORKER_CLAIM_RESULT_COLUMNS).not.toContain("payload");
    expect(WORKER_CLAIM_RESULT_COLUMNS).not.toContain("last_error");
    expect(WORKER_INCIDENT_RESULT_COLUMNS).not.toContain("payload");
    expect(WORKER_INCIDENT_RESULT_COLUMNS).not.toContain("detail");
  });

  it("returns bounded single composite envelopes from claim and incident RPCs", () => {
    type Functions = Database["public"]["Functions"];
    type WorkerClaimResult =
      Database["public"]["CompositeTypes"]["worker_claim_result"];
    type WorkerIncidentResult =
      Database["public"]["CompositeTypes"]["worker_incident_result"];

    expectTypeOf<
      Functions["worker_claim_next_command"]["Returns"]
    >().toEqualTypeOf<WorkerClaimResult>();
    expectTypeOf<
      Functions["worker_claim_next_command"]["SetofOptions"]
    >().toEqualTypeOf<{
      from: "*";
      to: "worker_claim_result";
      isOneToOne: true;
      isSetofReturn: false;
    }>();
    expectTypeOf<
      Functions["worker_record_incident"]["Returns"]
    >().toEqualTypeOf<WorkerIncidentResult>();
    expectTypeOf<
      Functions["worker_record_incident"]["SetofOptions"]
    >().toEqualTypeOf<{
      from: "*";
      to: "worker_incident_result";
      isOneToOne: true;
      isSetofReturn: false;
    }>();
  });
});
