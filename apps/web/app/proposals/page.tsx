import {
  ShadowCycleList,
  ShadowPagination,
  ShadowShell,
} from "../../components/ShadowConsole";
import { loadShadowScreen } from "../../lib/shadow-session";

export const dynamic = "force-dynamic";
export const metadata = { title: "ข้อเสนอวิจัย" };
export default async function ProposalsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const query = await searchParams;
  const page =
    query.page === undefined
      ? 0
      : /^\d{1,3}$/u.test(query.page)
        ? Number(query.page)
        : -1;
  const screen = await loadShadowScreen({ page });
  return (
    <ShadowShell screen={screen} title="ข้อเสนอวิจัย · ไม่ส่งคำสั่ง">
      <ShadowCycleList decisions={screen.page?.decisions ?? []} proposalsOnly />
      <ShadowPagination screen={screen} path="/proposals" />
    </ShadowShell>
  );
}
