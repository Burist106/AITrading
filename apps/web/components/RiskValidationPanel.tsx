import type { RiskCheckFixture } from "@aurum/fixtures";

import { Card, SectionHeading, StatusBadge, type Tone } from "./ui";

const stateTone: Record<RiskCheckFixture["state"], Tone> = {
  pass: "success",
  warn: "warning",
  fail: "blocked",
  na: "neutral",
};

export function RiskValidationPanel({
  checks,
  compact = false,
}: {
  checks: RiskCheckFixture[];
  compact?: boolean;
}) {
  const passed = checks.filter((check) => check.state === "pass").length;
  const failed = checks.filter((check) => check.state === "fail").length;
  const warned = checks.filter((check) => check.state === "warn").length;
  const notApplicable = checks.filter((check) => check.state === "na").length;
  const visible = compact ? checks.slice(0, 5) : checks;

  return (
    <Card labelledBy="risk-heading">
      <SectionHeading
        id="risk-heading"
        eyebrow="Hard + evidence checks"
        title="การตรวจความเสี่ยง"
        aside={
          <StatusBadge
            tone={failed ? "blocked" : warned ? "warning" : "success"}
          >
            {checks.length} CHECKS · {passed} PASS · {warned} WARN · {failed}{" "}
            FAIL · {notApplicable} N/A
          </StatusBadge>
        }
      />
      <ul className="divide-line/70 divide-y" aria-label="ผลการตรวจความเสี่ยง">
        {visible.map((check) => (
          <li
            key={check.key}
            className="grid min-h-12 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-2.5"
          >
            <span
              aria-hidden="true"
              className={`size-2 ${check.state === "pass" ? "bg-buy" : check.state === "warn" ? "bg-warning" : check.state === "fail" ? "bg-blocked" : "bg-line-strong"}`}
            />
            <span>
              <span className="text-ink block text-sm">{check.labelTh}</span>
              <span className="text-muted block font-mono text-[0.7rem]">
                {check.hard ? "HARD" : "EVIDENCE"} · {check.actual}
                {check.limit ? ` / ${check.limit}` : ""}
              </span>
            </span>
            <StatusBadge tone={stateTone[check.state]}>
              {check.state}
            </StatusBadge>
          </li>
        ))}
      </ul>
    </Card>
  );
}
