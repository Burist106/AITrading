import type { Metadata } from "next";

import { ApplicationShell } from "../../components/ApplicationShell";
import { PositionView } from "../../components/PositionView";
import { loadScenarioView, type ScenarioQuery } from "../../lib/scenario";

export const metadata: Metadata = { title: "Position" };

export default async function PositionPage({
  searchParams,
}: {
  searchParams: ScenarioQuery;
}) {
  const view = await loadScenarioView(searchParams);
  return (
    <ApplicationShell scenario={view.scenario} scenarioId={view.scenarioId}>
      <PositionView view={view} />
    </ApplicationShell>
  );
}
