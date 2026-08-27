import type { SystemComponentHealth } from "@aurum/contracts";

import type { ScenarioView } from "../lib/scenario";
import { EmergencyStatePanel } from "./EmergencyStatePanel";
import { PageIntro } from "./PageIntro";
import { Card, SectionHeading, StatusBadge, type Tone } from "./ui";

const stateTone = {
  healthy: "success",
  degraded: "warning",
  warning: "warning",
  failed: "critical",
  unknown: "neutral",
} as const satisfies Record<SystemComponentHealth["state"], Tone>;

function Plane({
  title,
  eyebrow,
  components,
}: {
  title: string;
  eyebrow: string;
  components: SystemComponentHealth[];
}) {
  const failed = components.filter((item) => item.state === "failed").length;
  const warned = components.filter(
    (item) => item.state === "warning" || item.state === "degraded",
  ).length;
  const unknown = components.filter((item) => item.state === "unknown").length;
  const healthy = components.filter((item) => item.state === "healthy").length;
  return (
    <Card labelledBy={`${eyebrow}-heading`}>
      <SectionHeading
        id={`${eyebrow}-heading`}
        eyebrow={eyebrow.replaceAll("-", " ")}
        title={title}
        aside={
          <StatusBadge
            tone={
              failed
                ? "critical"
                : warned
                  ? "warning"
                  : unknown
                    ? "neutral"
                    : "success"
            }
          >
            {components.length} TOTAL · {healthy} HEALTHY · {warned} WARN ·{" "}
            {failed} FAIL · {unknown} UNKNOWN
          </StatusBadge>
        }
      />
      <ul className="divide-line/70 divide-y">
        {components.map((component) => (
          <li
            key={component.code}
            className="grid min-h-16 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-3"
          >
            <span
              aria-hidden="true"
              className={`size-2 ${component.state === "healthy" ? "bg-buy" : component.state === "warning" || component.state === "degraded" ? "bg-warning" : component.state === "failed" ? "bg-critical" : "bg-line-strong"}`}
            />
            <span>
              <span className="text-ink block text-sm font-medium">
                {component.labelTh}
              </span>
              <span className="text-muted mt-1 block text-xs leading-5">
                {component.detail}
              </span>
              <span className="text-muted mt-1 block font-mono text-[0.7rem]">
                {component.code}
              </span>
            </span>
            <StatusBadge tone={stateTone[component.state]}>
              {component.state}
            </StatusBadge>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function HealthView({ view }: { view: ScenarioView }) {
  const execution = view.health.components.filter(
    (component) => component.plane === "execution_plane",
  );
  const control = view.health.components.filter(
    (component) => component.plane === "control_plane",
  );
  const hasFailure = view.health.components.some(
    (component) => component.state === "failed",
  );
  const hasWarning = view.health.components.some(
    (component) =>
      component.state === "warning" || component.state === "degraded",
  );
  const hasUnknown = view.health.components.some(
    (component) => component.state === "unknown",
  );

  return (
    <>
      <PageIntro
        eyebrow="System health · Fixture"
        title="สุขภาพระบบ"
        description="แยก Control Plane ออกจาก Execution Plane ชัดเจน ค่า UNKNOWN เป็น Placeholder ที่ตั้งใจไว้ ไม่ได้ตีความว่า Healthy"
        badge={
          hasFailure
            ? "FAILED / BLOCKED"
            : hasWarning
              ? "DEGRADED"
              : hasUnknown
                ? "UNKNOWN PLACEHOLDERS"
                : "FIXTURE HEALTH"
        }
        badgeTone={
          hasFailure
            ? "critical"
            : hasWarning
              ? "warning"
              : hasUnknown
                ? "neutral"
                : "success"
        }
      />
      {view.scenario.accountVerification === "blocked_non_demo" ? (
        <div
          role="alert"
          className="border-critical bg-critical-fill mb-5 border-2 p-4 text-white"
        >
          <p className="font-display text-lg font-bold">
            บัญชีที่ไม่ใช่ Demo ถูกบล็อก
          </p>
          <p className="mt-1 text-sm leading-6">
            Worker ต้องล้มเหลวแบบปิด ไม่มี Override และไม่มีเส้นทางดำเนินการต่อ
          </p>
        </div>
      ) : null}
      <div className="grid gap-5 xl:grid-cols-2">
        <Plane
          title="Execution Plane"
          eyebrow="execution-plane"
          components={execution}
        />
        <Plane
          title="Control Plane"
          eyebrow="control-plane"
          components={control}
        />
      </div>
      <div className="mt-5">
        <EmergencyStatePanel state={view.emergency} />
      </div>
      <p className="text-muted mt-5 font-mono text-xs">
        Snapshot:{" "}
        {new Date(view.health.capturedAt).toLocaleString("th-TH", {
          timeZone: "UTC",
        })}{" "}
        UTC · แหล่งข้อมูล fixture เท่านั้น
      </p>
    </>
  );
}
