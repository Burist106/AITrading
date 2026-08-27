import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ApplicationShell } from "../../../components/ApplicationShell";
import { ProposalDetailView } from "../../../components/ProposalDetailView";
import { loadScenarioView, type ScenarioQuery } from "../../../lib/scenario";

export const metadata: Metadata = { title: "รายละเอียดข้อเสนอ" };

export function generateStaticParams() {
  return [{ id: "demo-proposal" }];
}

export default async function ProposalPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: ScenarioQuery;
}) {
  const { id } = await params;
  if (id !== "demo-proposal") notFound();
  const view = await loadScenarioView(searchParams);
  return (
    <ApplicationShell scenario={view.scenario} scenarioId={view.scenarioId}>
      <ProposalDetailView view={view} />
    </ApplicationShell>
  );
}
