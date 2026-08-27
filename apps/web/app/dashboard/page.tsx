import type { Metadata } from "next";

import { ApplicationShell } from "../../components/ApplicationShell";
import { DashboardView } from "../../components/DashboardView";
import { loadScenarioView, type ScenarioQuery } from "../../lib/scenario";

export const metadata: Metadata = { title: "ภาพรวม" };

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: ScenarioQuery;
}) {
  const view = await loadScenarioView(searchParams);
  return (
    <ApplicationShell scenario={view.scenario} scenarioId={view.scenarioId}>
      <DashboardView view={view} />
    </ApplicationShell>
  );
}
