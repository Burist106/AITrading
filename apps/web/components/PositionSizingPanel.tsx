import type { PositionSizingResult } from "@aurum/contracts";

import { Card, DefinitionRow, SectionHeading, StatusBadge } from "./ui";

const money = (value: number) =>
  value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export function PositionSizingPanel({
  sizing,
}: {
  sizing: PositionSizingResult;
}) {
  return (
    <Card labelledBy="sizing-heading">
      <SectionHeading
        id="sizing-heading"
        eyebrow="Deterministic fixture"
        title="การคำนวณ Position Sizing"
        aside={
          <StatusBadge tone={sizing.result === "pass" ? "success" : "blocked"}>
            {sizing.result}
          </StatusBadge>
        }
      />
      <dl>
        <DefinitionRow
          label="Equity"
          value={`${money(sizing.accountEquity)} USD`}
        />
        <DefinitionRow
          label="Risk limit"
          value={`${sizing.riskLimitPct.toFixed(2)}%`}
        />
        <DefinitionRow
          label="Risk budget"
          value={`${money(sizing.riskBudgetAmount)} USD`}
          emphasized
        />
        <DefinitionRow
          label="Stop distance"
          value={`${sizing.stopDistancePrice.toFixed(2)} / ${sizing.stopDistancePoints.toFixed(0)} points`}
        />
        <DefinitionRow
          label="Calculated volume"
          value={sizing.calculatedVolume.toFixed(4)}
        />
        <DefinitionRow
          label="Broker minimum / step"
          value={`${sizing.brokerMinimumVolume.toFixed(2)} / ${sizing.brokerVolumeStep.toFixed(2)}`}
        />
        <DefinitionRow
          label="Maximum permitted volume"
          value={sizing.maximumPermittedVolume.toFixed(2)}
          emphasized
        />
        <DefinitionRow
          label="Requested volume"
          value={
            sizing.requestedVolume === null
              ? "BLOCK"
              : sizing.requestedVolume.toFixed(2)
          }
          emphasized
        />
        <DefinitionRow
          label="Volume adjustment"
          value={
            sizing.result === "block"
              ? "ไม่ปรับขึ้นเพื่อผ่านขั้นต่ำ"
              : sizing.calculatedVolume === sizing.requestedVolume
                ? "ไม่มีการปรับ"
                : "ปรับตาม minimum / step"
          }
        />
        <DefinitionRow
          label="Calculation source"
          value={sizing.calculationSource}
        />
        <DefinitionRow
          label="Estimated loss at SL"
          value={`${money(sizing.estimatedLossAtStop)} USD (${sizing.actualRiskPct.toFixed(2)}%)`}
        />
      </dl>
      {sizing.result === "block" ? (
        <p
          role="status"
          className="border-blocked/50 bg-blocked/8 text-blocked mt-4 border p-3 font-mono text-xs leading-5"
        >
          {sizing.blockReason}
        </p>
      ) : null}
    </Card>
  );
}
