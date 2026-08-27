import { z } from "zod";

export const PROTOTYPE_SCENARIO_IDS = [
  "no_signal",
  "wait",
  "auto_eligible",
  "human_approval",
  "blocked",
  "proposal_expired",
  "approval_recorded",
  "revalidation_failed",
  "order_pending",
  "order_rejected",
  "position_open",
  "position_closed",
  "mt5_disconnected",
  "market_data_stale",
  "daily_loss_limit",
  "emergency_stop_requested",
  "emergency_stop_confirmed",
  "emergency_stop_unconfirmed",
  "live_account_detected",
  "minimum_lot_exceeds_risk",
] as const;

export const PrototypeScenarioIdSchema = z.enum(PROTOTYPE_SCENARIO_IDS);
export type PrototypeScenarioId = z.infer<typeof PrototypeScenarioIdSchema>;
