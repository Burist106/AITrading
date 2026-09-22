import { ShadowCycleList, ShadowShell } from "../../components/ShadowConsole";
import { loadShadowScreen } from "../../lib/shadow-session";

export const dynamic = "force-dynamic";
export const metadata = { title: "สุขภาพระบบ" };
export default async function HealthPage() {
  const screen = await loadShadowScreen();
  return (
    <ShadowShell screen={screen} title="สุขภาพ pipeline จากหลักฐานที่บันทึก">
      <p className="text-muted text-sm">
        แสดงเหตุผล WAIT/BLOCK/PROPOSAL ของรอบที่บันทึก ไม่อนุมาน heartbeat
        หรือการเชื่อมต่อ Terminal จากบันทึกเก่า ประเด็น native transaction-time
        ยังคงเป็น gate ของ Worker
      </p>
      <ShadowCycleList decisions={screen.page?.decisions ?? []} />
    </ShadowShell>
  );
}
