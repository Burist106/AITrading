import { UuidSchema } from "@aurum/contracts";
import { notFound } from "next/navigation";

import {
  ShadowDecisionEvidence,
  ShadowEmpty,
  ShadowShell,
} from "../../../components/ShadowConsole";
import { loadShadowScreen } from "../../../lib/shadow-session";

export const dynamic = "force-dynamic";
export const metadata = { title: "รายละเอียดรอบ Shadow" };

export default async function ProposalPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!UuidSchema.safeParse(id).success) notFound();
  const screen = await loadShadowScreen({ id });
  return (
    <ShadowShell screen={screen} title="รายละเอียดรอบ Shadow">
      {screen.decision ? (
        <ShadowDecisionEvidence decision={screen.decision} />
      ) : (
        <ShadowEmpty />
      )}
    </ShadowShell>
  );
}
