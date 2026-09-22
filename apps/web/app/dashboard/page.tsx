import {
  ShadowCycleList,
  ShadowEmpty,
  ShadowMarketEvidence,
  ShadowShell,
} from "../../components/ShadowConsole";
import { loadShadowScreen } from "../../lib/shadow-session";

export const dynamic = "force-dynamic";
export const metadata = { title: "ภาพรวม" };

export default async function DashboardPage() {
  const screen = await loadShadowScreen();
  const latest = screen.page?.decisions[0]?.cycle;
  return (
    <ShadowShell screen={screen} title="ศูนย์ควบคุมการวิจัย">
      {latest ? <ShadowMarketEvidence cycle={latest} /> : <ShadowEmpty />}
      <ShadowCycleList decisions={screen.page?.decisions ?? []} />
    </ShadowShell>
  );
}
