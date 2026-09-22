import {
  ShadowJournal,
  ShadowPagination,
  ShadowShell,
} from "../../components/ShadowConsole";
import { loadShadowScreen } from "../../lib/shadow-session";

export const dynamic = "force-dynamic";
export const metadata = { title: "บันทึกผล Shadow" };
export default async function JournalPage({
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
    <ShadowShell screen={screen} title="บันทึกผล Shadow">
      <ShadowJournal decisions={screen.page?.decisions ?? []} />
      <ShadowPagination screen={screen} path="/journal" />
    </ShadowShell>
  );
}
