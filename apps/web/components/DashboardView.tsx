import Link from "next/link";

import type { ScenarioView } from "../lib/scenario";
import { withScenario } from "../lib/scenario";
import { EmergencyStatePanel } from "./EmergencyStatePanel";
import { PageIntro } from "./PageIntro";
import { RiskValidationPanel } from "./RiskValidationPanel";
import {
  Card,
  DefinitionRow,
  EmptyState,
  Metric,
  SectionHeading,
  StatusBadge,
  type Tone,
} from "./ui";

const proposalTone: Record<ScenarioView["eligibility"]["outcome"], Tone> = {
  auto: "success",
  ask: "warning",
  block: "blocked",
};

const number = (value: number) =>
  value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export function DashboardView({ view }: { view: ScenarioView }) {
  const {
    scenario,
    scenarioId,
    sample,
    metrics,
    eligibility,
    proposal,
    position,
  } = view;
  const hasProposal = !["none", "wait"].includes(scenario.proposalState);
  const hasPosition = scenario.positionState !== "none";

  return (
    <>
      <PageIntro
        eyebrow="Main dashboard"
        title="ศูนย์ควบคุมการวิจัย"
        description={`${scenario.labelTh} — ${scenario.descriptionTh}`}
        badge={`${scenario.systemState} · SHADOW`}
        badgeTone={
          scenario.systemState === "running"
            ? "success"
            : scenario.systemState === "paused" ||
                scenario.systemState === "recovering"
              ? "warning"
              : "critical"
        }
      />

      <section
        aria-labelledby="market-heading"
        className="border-line bg-elevated mb-5 border p-4 sm:p-5"
      >
        <SectionHeading
          id="market-heading"
          eyebrow="Fixture market snapshot"
          title="XAU/USD"
          aside={
            <StatusBadge
              tone={
                scenario.marketFreshness === "live"
                  ? "success"
                  : scenario.marketFreshness === "stale"
                    ? "critical"
                    : "warning"
              }
            >
              {scenario.marketFreshness} · simulated
            </StatusBadge>
          }
        />
        <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
          <Metric
            label="ราคาปัจจุบัน"
            value={number(sample.currentPrice)}
            tone="gold"
          />
          <Metric
            label="Bid / Ask"
            value={`${view.market.bid.toFixed(2)} / ${view.market.ask.toFixed(2)}`}
            detail={`Spread ${view.market.spread.toFixed(2)}`}
          />
          <Metric label="Session" value={view.market.session} />
          <Metric
            label="Regime"
            value={view.market.regime}
            tone={view.market.regime === "volatile" ? "warning" : "info"}
          />
          <Metric label="ราคาเข้า" value={number(sample.entryPrice)} />
          <Metric
            label="ความคลาดเคลื่อน"
            value={`${metrics.deviation >= 0 ? "+" : ""}${metrics.deviation.toFixed(2)}`}
            detail={`ช่วงอนุญาต ±${sample.entryTolerance.toFixed(2)}`}
            tone={metrics.withinTolerance ? "success" : "blocked"}
          />
          <Metric
            label="Stop Loss"
            value={number(sample.stopLossPrice)}
            tone="blocked"
          />
          <Metric
            label="Take Profit"
            value={number(sample.takeProfitPrice)}
            tone="success"
          />
        </dl>
        <p className="border-line text-muted mt-4 border-t pt-3 text-xs leading-5">
          Event warning: {view.market.eventWindow}
        </p>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(20rem,0.7fr)]">
        <div className="grid gap-5">
          <Card labelledBy="proposal-summary-heading">
            <SectionHeading
              id="proposal-summary-heading"
              eyebrow="Trade proposal"
              title="สรุปข้อเสนอ"
              aside={
                hasProposal ? (
                  <StatusBadge tone={proposalTone[eligibility.outcome]}>
                    {eligibility.outcome}
                  </StatusBadge>
                ) : (
                  <StatusBadge>ไม่มีข้อเสนอ</StatusBadge>
                )
              }
            />
            {hasProposal ? (
              <>
                <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
                  <Metric
                    label="ทิศทาง"
                    value={proposal.direction}
                    tone="success"
                  />
                  <Metric
                    label="Volume สูงสุด"
                    value={proposal.maximumPermittedVolume.toFixed(2)}
                  />
                  <Metric
                    label="Risk / Reward"
                    value={`1 : ${proposal.riskReward.toFixed(1)}`}
                  />
                  <Metric
                    label="สถานะ"
                    value={proposal.status}
                    tone={proposal.status === "blocked" ? "blocked" : "warning"}
                  />
                </div>
                <div className="border-line mt-5 border-t pt-4">
                  <Link
                    href={withScenario("/proposals/demo-proposal", scenarioId)}
                    className="border-line-strong text-ink hover:border-gold hover:text-gold inline-flex min-h-11 items-center border px-4 text-sm font-semibold"
                  >
                    ดูรายละเอียดและหลักฐาน →
                  </Link>
                </div>
              </>
            ) : (
              <EmptyState
                title={
                  scenario.proposalState === "wait"
                    ? "กำลังรอเงื่อนไข"
                    : "ยังไม่มีข้อเสนอ"
                }
                description="ระบบแสดง Fixture แบบอ่านอย่างเดียวและจะไม่สร้างหรือส่งคำสั่งใด ๆ ใน Bootstrap"
              />
            )}
          </Card>
          <RiskValidationPanel checks={view.riskChecks} compact />
        </div>

        <div className="grid content-start gap-5">
          <Card labelledBy="position-summary-heading">
            <SectionHeading
              id="position-summary-heading"
              eyebrow="Single-position ceiling"
              title="Position จำลอง"
              aside={
                <StatusBadge tone={hasPosition ? "info" : "neutral"}>
                  {scenario.positionState}
                </StatusBadge>
              }
            />
            {hasPosition ? (
              <>
                <dl>
                  <DefinitionRow
                    label="Direction / volume"
                    value={`${position.direction} · ${position.volume.toFixed(2)}`}
                    emphasized
                  />
                  <DefinitionRow
                    label="Entry / current"
                    value={`${number(position.entry)} / ${number(position.current)}`}
                  />
                  <DefinitionRow
                    label="Unrealized P/L"
                    value={`${position.unrealizedPnl >= 0 ? "+" : ""}${number(position.unrealizedPnl)} USD`}
                    emphasized
                  />
                  <DefinitionRow
                    label="Stop Loss"
                    value={number(position.stopLoss)}
                  />
                </dl>
                <Link
                  href={withScenario("/position", scenarioId)}
                  className="text-gold mt-4 inline-flex min-h-11 items-center text-sm font-semibold"
                >
                  ดู Position แบบอ่านอย่างเดียว →
                </Link>
              </>
            ) : (
              <EmptyState
                title="ไม่มี Position เปิดอยู่"
                description="เพดานสูงสุดหนึ่ง Position ถูกบันทึกในสัญญา แต่ Bootstrap ไม่มีความสามารถแก้ไข Position"
              />
            )}
          </Card>
          <EmergencyStatePanel state={view.emergency} />
        </div>
      </div>
    </>
  );
}
