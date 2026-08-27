import type { ScenarioView } from "../lib/scenario";
import { PageIntro } from "./PageIntro";
import {
  Card,
  DefinitionRow,
  EmptyState,
  Metric,
  SectionHeading,
  StatusBadge,
} from "./ui";

const number = (value: number) =>
  value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export function PositionView({ view }: { view: ScenarioView }) {
  const { scenario, position } = view;
  const open =
    scenario.positionState === "open_profit" ||
    scenario.positionState === "open_loss";
  const closed = scenario.positionState === "closed";
  const pnl = position.unrealizedPnl;

  return (
    <>
      <PageIntro
        eyebrow="Active position · Fixture"
        title="Position จำลอง"
        description="ข้อมูลสำหรับติดตามสถานะเท่านั้น Bootstrap ไม่มีคำสั่งปิด เลื่อน Stop Loss หรือแก้ไข Position"
        badge={scenario.positionState}
        badgeTone={open ? (pnl >= 0 ? "success" : "negative") : "neutral"}
      />
      <div
        className="border-info/40 bg-info/8 text-info mb-5 border px-4 py-3 text-sm leading-6"
        role="note"
      >
        Read only · สูงสุด 1 Position · Volume 0.01 · Stop Loss บังคับ ·
        ไม่มีการเปลี่ยนแปลงสถานะภายนอก
      </div>
      {!open && !closed ? (
        <Card>
          <EmptyState
            title="ไม่มี Position ในสถานะนี้"
            description="เลือก Fixture position_open หรือ position_closed ใน Development State Simulator เพื่อทดสอบการจัดวาง"
          />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.8fr)]">
          <Card labelledBy="position-overview-heading">
            <SectionHeading
              id="position-overview-heading"
              eyebrow={closed ? "Historical fixture" : "Read-only monitor"}
              title={closed ? "Position ปิดแล้ว" : "Position เปิดอยู่"}
              aside={
                <StatusBadge
                  tone={closed ? "neutral" : pnl >= 0 ? "success" : "negative"}
                >
                  {closed ? "CLOSED" : "OPEN"}
                </StatusBadge>
              }
            />
            <div className="mb-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Symbol" value="XAUUSD" tone="gold" />
              <Metric
                label="Direction"
                value={position.direction}
                tone="success"
              />
              <Metric label="Volume" value={position.volume.toFixed(2)} />
              <Metric
                label={closed ? "Recorded P/L" : "Unrealized P/L"}
                value={`${pnl >= 0 ? "+" : ""}${number(pnl)} USD`}
                tone={pnl >= 0 ? "success" : "negative"}
              />
            </div>
            <dl className="grid gap-x-8 sm:grid-cols-2">
              <DefinitionRow
                label="Entry"
                value={number(position.entry)}
                emphasized
              />
              <DefinitionRow
                label="Current fixture price"
                value={number(position.current)}
                emphasized
              />
              <DefinitionRow
                label="Stop Loss"
                value={number(position.stopLoss)}
              />
              <DefinitionRow
                label="Take Profit"
                value={number(position.takeProfit)}
              />
              <DefinitionRow
                label="R multiple"
                value={`${position.rMultiple.toFixed(2)}R`}
              />
              <DefinitionRow
                label="Opened at"
                value={
                  new Date(position.openedAt).toLocaleString("th-TH", {
                    timeZone: "UTC",
                  }) + " UTC"
                }
              />
            </dl>
          </Card>
          <Card labelledBy="position-guardrails-heading">
            <SectionHeading
              id="position-guardrails-heading"
              eyebrow="Immutable guardrails"
              title="ขอบเขตความปลอดภัย"
              aside={<StatusBadge tone="blocked">NO CONTROLS</StatusBadge>}
            />
            <dl>
              <DefinitionRow label="Environment" value="DEMO ONLY" emphasized />
              <DefinitionRow label="Runtime mode" value="SHADOW" emphasized />
              <DefinitionRow label="Maximum positions" value="1" />
              <DefinitionRow label="Maximum volume" value="0.01" />
              <DefinitionRow label="Stop Loss" value="REQUIRED" />
              <DefinitionRow label="Source" value="fixture / simulated" />
            </dl>
            <p className="border-line text-muted mt-4 border p-3 text-sm leading-6">
              ไม่มีปุ่มแก้ไข ปิด หรือเพิ่มขนาด Position และไม่มี Adapter
              ที่เปลี่ยนสถานะโบรกเกอร์
            </p>
          </Card>
        </div>
      )}
    </>
  );
}
