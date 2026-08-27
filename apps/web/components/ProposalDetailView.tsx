import type { ScenarioView } from "../lib/scenario";
import { PageIntro } from "./PageIntro";
import { PositionSizingPanel } from "./PositionSizingPanel";
import { RiskValidationPanel } from "./RiskValidationPanel";
import {
  Card,
  DefinitionRow,
  Metric,
  SectionHeading,
  StatusBadge,
  type Tone,
} from "./ui";

const checkTone = {
  pass: "success",
  warn: "warning",
  fail: "blocked",
  not_required: "neutral",
} as const satisfies Record<
  ScenarioView["eligibility"]["checks"][number]["state"],
  Tone
>;
const outcomeTone = {
  auto: "success",
  ask: "warning",
  block: "blocked",
} as const satisfies Record<ScenarioView["eligibility"]["outcome"], Tone>;

export function ProposalDetailView({ view }: { view: ScenarioView }) {
  const { proposal, eligibility, evidence, sample, metrics } = view;

  return (
    <>
      <PageIntro
        eyebrow="Proposal detail · Fixture"
        title="ข้อเสนอ XAU/USD"
        description="รายละเอียดแบบอ่านอย่างเดียว แสดง Contract, Eligibility และการคำนวณจากแหล่งข้อมูลกลางเดียว"
        badge={`${eligibility.outcome} · ${proposal.status}`}
        badgeTone={outcomeTone[eligibility.outcome]}
      />
      <div
        className="border-info/40 bg-info/8 text-info mb-5 border px-4 py-3 text-sm leading-6"
        role="note"
      >
        Bootstrap ไม่มีปุ่มอนุมัติ ปฏิเสธ Override หรือส่งต่อไปยังโบรกเกอร์
        สถานะทั้งหมดเป็น Fixture สำหรับตรวจ UI และ Contract เท่านั้น
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(21rem,0.8fr)]">
        <div className="grid content-start gap-5">
          <Card labelledBy="proposal-prices-heading">
            <SectionHeading
              id="proposal-prices-heading"
              eyebrow="Immutable snapshot"
              title="ราคาและความเสี่ยง"
              aside={
                <StatusBadge tone="gold">
                  {proposal.direction} · {proposal.canonicalSymbol}
                </StatusBadge>
              }
            />
            <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Entry" value={proposal.entryPrice.toFixed(2)} />
              <Metric
                label="Current"
                value={sample.currentPrice.toFixed(2)}
                detail={`Deviation ${metrics.deviation >= 0 ? "+" : ""}${metrics.deviation.toFixed(2)}`}
                tone={metrics.withinTolerance ? "success" : "blocked"}
              />
              <Metric
                label="Stop Loss"
                value={proposal.stopLossPrice.toFixed(2)}
                tone="blocked"
              />
              <Metric
                label="Take Profit"
                value={proposal.takeProfitPrice.toFixed(2)}
                tone="success"
              />
            </dl>
            <dl className="border-line mt-5 grid gap-5 border-t pt-5 sm:grid-cols-2 lg:grid-cols-4">
              <Metric
                label="Maximum volume"
                value={proposal.maximumPermittedVolume.toFixed(2)}
              />
              <Metric
                label="Risk amount"
                value={`${proposal.riskAmount.toFixed(2)} USD`}
              />
              <Metric
                label="Actual risk"
                value={`${proposal.riskPct.toFixed(2)}%`}
              />
              <Metric
                label="Risk / Reward"
                value={`1 : ${proposal.riskReward.toFixed(1)}`}
              />
            </dl>
          </Card>

          <Card labelledBy="eligibility-heading">
            <SectionHeading
              id="eligibility-heading"
              eyebrow={`Policy ${eligibility.policyVersion}`}
              title="Eligibility — เหตุผลของผลลัพธ์"
              aside={
                <StatusBadge tone={outcomeTone[eligibility.outcome]}>
                  {eligibility.outcome}
                </StatusBadge>
              }
            />
            <ul className="divide-line/70 divide-y">
              {eligibility.checks.map((check) => (
                <li
                  key={check.key}
                  className="grid min-h-14 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 py-3"
                >
                  <span>
                    <span className="text-ink block text-sm">
                      {check.labelTh}
                    </span>
                    <span className="text-muted mt-1 block font-mono text-[0.7rem] leading-5">
                      actual: {String(check.actualValue)} · required:{" "}
                      {String(check.requiredValue)}
                    </span>
                  </span>
                  <StatusBadge tone={checkTone[check.state]}>
                    {check.state}
                  </StatusBadge>
                </li>
              ))}
            </ul>
          </Card>

          <RiskValidationPanel checks={view.riskChecks} />
        </div>

        <div className="grid content-start gap-5">
          <PositionSizingPanel sizing={view.sizing} />
          <Card labelledBy="evidence-heading">
            <SectionHeading
              id="evidence-heading"
              eyebrow="Supporting evidence only"
              title="Signal Evidence"
              aside={<StatusBadge tone="info">ไม่ใช่ Verdict</StatusBadge>}
            />
            <div className="border-info bg-info/8 text-info mb-4 border-l-4 px-4 py-3 text-sm leading-6">
              Quality score เป็นหลักฐานประกอบเท่านั้น ผล AUTO / ASK / BLOCK
              มาจากกฎ Eligibility และ Hard Risk — ไม่ได้คำนวณจากคะแนน
            </div>
            <dl>
              <DefinitionRow
                label="Quality score"
                value={
                  evidence.qualityScore === null
                    ? "N/A"
                    : `${evidence.qualityScore.toFixed(0)} / 100`
                }
                emphasized
              />
              <DefinitionRow
                label="Similar samples"
                value={`${evidence.similarSampleCount} / ${evidence.minimumRequiredSampleCount}`}
              />
              <DefinitionRow
                label="Calibration"
                value={evidence.calibrationStatus}
              />
              <DefinitionRow
                label="Calibrated probability"
                value={evidence.calibratedProbability ?? "N/A"}
              />
              <DefinitionRow
                label="Strategy version"
                value={evidence.strategyVersion}
              />
            </dl>
          </Card>
          <Card labelledBy="identity-heading">
            <SectionHeading
              id="identity-heading"
              eyebrow="Audit identity"
              title="ตัวระบุข้อเสนอ"
            />
            <dl>
              <DefinitionRow label="Proposal ID" value={proposal.id} />
              <DefinitionRow
                label="Proposal version"
                value={proposal.proposalVersion}
              />
              <DefinitionRow label="Environment" value="DEMO ONLY" emphasized />
              <DefinitionRow label="Mode" value="SHADOW" emphasized />
              <DefinitionRow label="Source" value="fixture" />
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
