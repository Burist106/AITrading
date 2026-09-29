import { ShadowShell } from "../../components/ShadowConsole";
import { EmptyState } from "../../components/ui";
import { loadShadowScreen } from "../../lib/shadow-session";

export const dynamic = "force-dynamic";
export const metadata = { title: "Position" };
export default async function PositionPage() {
  const screen = await loadShadowScreen();
  return (
    <ShadowShell screen={screen} title="Position · ไม่มีความสามารถซื้อขาย">
      <EmptyState
        title="Shadow ไม่สร้าง Position โบรกเกอร์"
        description="หน้านี้ไม่มีหลักฐาน Position ปัจจุบัน จึงไม่แสดงราคา P/L หรืออ้างว่าไม่มี Position เปิดอยู่ ผลสังเกตแบบสมมติอยู่ในบันทึกผล Shadow"
      />
    </ShadowShell>
  );
}
