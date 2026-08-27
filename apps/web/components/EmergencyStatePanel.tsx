import type { EmergencyStopState } from "@aurum/contracts";

import { Card, DefinitionRow, SectionHeading, StatusBadge } from "./ui";

export function EmergencyStatePanel({
  state,
}: {
  state: EmergencyStopState | null;
}) {
  if (!state) {
    return (
      <Card labelledBy="emergency-heading">
        <SectionHeading
          id="emergency-heading"
          eyebrow="Safety control"
          title="Emergency Stop"
          aside={<StatusBadge tone="success">ไม่ได้ร้องขอ</StatusBadge>}
        />
        <p className="text-muted text-sm leading-6">
          ไม่มีสถานะฉุกเฉินใน Fixture นี้
          การ์ดนี้เป็นมุมมองสถานะเท่านั้นและไม่มีปุ่มสั่งงาน
        </p>
      </Card>
    );
  }

  const unconfirmed = state.worker === "WORKER_ACK_TIMEOUT";
  const confirmed = state.worker === "CONFIRMED";
  const tone = unconfirmed
    ? "border-critical bg-critical-fill/25"
    : confirmed
      ? "border-buy/50 bg-buy/8"
      : "border-warning/50 bg-warning/8";
  const title = unconfirmed
    ? "ยืนยันการหยุด Worker ไม่ได้"
    : confirmed
      ? "Worker ยืนยันการหยุดแล้ว"
      : "บันทึกคำขอหยุดแล้ว";

  return (
    <Card labelledBy="emergency-heading" className={tone}>
      <SectionHeading
        id="emergency-heading"
        eyebrow="Emergency state"
        title={title}
        aside={
          <StatusBadge
            tone={unconfirmed ? "critical" : confirmed ? "success" : "warning"}
          >
            {unconfirmed
              ? "UNCONFIRMED"
              : confirmed
                ? "CONFIRMED"
                : "REQUESTED"}
          </StatusBadge>
        }
      />
      {unconfirmed ? (
        <div
          role="alert"
          className="border-critical bg-critical-fill mb-4 border-l-4 px-4 py-3 text-sm leading-6 text-white"
        >
          <p className="font-semibold">
            สถานะฝั่ง Worker ไม่ทราบแน่ชัด อย่าถือว่าการหยุดสำเร็จ
          </p>
          <ol className="mt-2 list-decimal space-y-1 pl-5">
            <li>เปิดเครื่อง Windows Execution Node โดยตรง</li>
            <li>ตรวจสถานะ Worker และ Log ในเครื่อง</li>
            <li>ปิด MT5 AutoTrading ด้วยตนเอง</li>
            <li>ใช้ Local Emergency Stop ตาม Runbook</li>
            <li>ตรวจ Position ที่เปิดอยู่ใน MT5 โดยตรง</li>
          </ol>
        </div>
      ) : null}
      <dl>
        <DefinitionRow label="Control plane" value={state.controlPlane} />
        <DefinitionRow
          label="Worker acknowledgment"
          value={state.worker ?? "PENDING / UNKNOWN"}
          emphasized
        />
        <DefinitionRow
          label="Local kill switch"
          value={
            state.localKillSwitchEngaged === true
              ? "ENGAGED"
              : state.localKillSwitchEngaged === false
                ? "NOT ENGAGED"
                : "UNKNOWN"
          }
        />
        <DefinitionRow
          label="เส้นตายการยืนยัน"
          value={
            new Date(state.ackDeadlineAt).toLocaleTimeString("th-TH", {
              timeZone: "UTC",
            }) + " UTC"
          }
        />
      </dl>
    </Card>
  );
}
