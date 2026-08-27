import type { Metadata } from "next";

import { ApplicationShell } from "../../components/ApplicationShell";
import { HealthView } from "../../components/HealthView";
import { loadScenarioView, type ScenarioQuery } from "../../lib/scenario";

export const metadata: Metadata = { title: "สุขภาพระบบ" };

export default async function HealthPage({
  searchParams,
}: {
  searchParams: ScenarioQuery;
}) {
  const view = await loadScenarioView(searchParams);
  return (
    <ApplicationShell scenario={view.scenario} scenarioId={view.scenarioId}>
      <HealthView view={view} />
    </ApplicationShell>
  );
}
