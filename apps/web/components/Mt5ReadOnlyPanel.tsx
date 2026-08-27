import type { Mt5ConsoleReadModel } from "@aurum/contracts";

import { deriveMt5PanelState } from "../lib/mt5-read-models";
import {
  Card,
  DefinitionRow,
  EmptyState,
  SectionHeading,
  StatusBadge,
  type Tone,
} from "./ui";

const toneByState = {
  loading: "neutral",
  empty: "neutral",
  healthy: "success",
  degraded: "warning",
  blocked: "critical",
  unavailable: "critical",
  stale: "critical",
  reconnecting: "warning",
  reconciliation_pending: "warning",
  reconciliation_failed: "critical",
} as const satisfies Record<ReturnType<typeof deriveMt5PanelState>, Tone>;

export function Mt5ReadOnlyPanel({
  model,
}: {
  model: Mt5ConsoleReadModel | null | undefined;
}) {
  const state = deriveMt5PanelState(model);

  return (
    <Card labelledBy="mt5-readonly-heading">
      <SectionHeading
        id="mt5-readonly-heading"
        eyebrow="MT5 observation boundary · Read only"
        title="Windows MT5 Worker"
        aside={<StatusBadge tone={toneByState[state]}>{state}</StatusBadge>}
      />
      {model === undefined ? (
        <p role="status" className="text-muted text-sm">
          กำลังโหลดข้อมูลสังเกตการณ์แบบอ่านอย่างเดียว…
        </p>
      ) : model === null || model.account === null ? (
        <EmptyState
          title="ยังไม่มีข้อมูล MT5"
          description="Worker ยังไม่ได้บันทึกข้อมูลสังเกตการณ์ที่ปลอดภัย"
        />
      ) : (
        <>
          <dl className="grid gap-x-8 md:grid-cols-2 xl:grid-cols-3">
            <DefinitionRow
              label="Package / platform"
              value={`${model.health.packageAvailable ? "available" : "unavailable"} · ${model.health.platform}`}
            />
            <DefinitionRow
              label="Terminal"
              value={
                model.health.terminalConnected
                  ? (model.health.terminalVersion ?? "connected")
                  : "disconnected / reconnecting"
              }
            />
            <DefinitionRow
              label="Demo verification"
              value={model.account.verificationState}
              emphasized
            />
            <DefinitionRow
              label="Masked identity"
              value={`${model.account.maskedLogin} · ${model.account.maskedServer}`}
            />
            <DefinitionRow
              label="Broker symbol"
              value={`${model.symbol?.brokerSymbol ?? "not confirmed"} · ${model.symbol?.usabilityState ?? "unknown"}`}
            />
            <DefinitionRow
              label="Specification"
              value={model.symbol?.specificationFingerprint ?? "unavailable"}
            />
            <DefinitionRow
              label="Bid / Ask"
              value={
                model.tick === null
                  ? "unavailable"
                  : `${model.tick.bid} / ${model.tick.ask}`
              }
            />
            <DefinitionRow
              label="Spread / tick age"
              value={
                model.tick === null
                  ? "unavailable"
                  : `${model.tick.spreadPrice} · ${model.tick.ageSeconds}s · ${model.tick.freshness}`
              }
            />
            <DefinitionRow
              label="Last completed candle"
              value={model.health.lastCompletedCandleAt ?? "not observed"}
            />
            <DefinitionRow
              label="Worker observation"
              value={
                model.health.lastSuccessfulObservationAt ?? "not available"
              }
            />
            <DefinitionRow
              label="Reconciliation"
              value={`${model.reconciliation?.status ?? "not started"} · ${model.reconciliation?.outcome ?? "pending"}`}
              emphasized
            />
            <DefinitionRow
              label="Positions / active orders"
              value={`${model.health.openPositionCount ?? "?"} / ${model.health.activeOrderCount ?? "?"}`}
            />
          </dl>
          {model.reconciliation?.mismatches.length ? (
            <div className="border-critical bg-critical-fill mt-4 border p-3 text-sm text-white">
              Safe incidents: {model.reconciliation.mismatches.length} ·{" "}
              {model.reconciliation.mismatches
                .map((mismatch) => mismatch.category)
                .join(", ")}
            </div>
          ) : null}
          <p className="border-line text-muted mt-4 border-t pt-3 text-xs leading-5">
            DEMO ONLY · SHADOW · ไม่มีข้อมูลบัญชีดิบ ไม่มี Terminal path
            และไม่มีความสามารถเปลี่ยนสถานะโบรกเกอร์
          </p>
        </>
      )}
    </Card>
  );
}
