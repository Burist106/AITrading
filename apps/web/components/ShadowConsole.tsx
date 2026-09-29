import type { ShadowCycle } from "@aurum/contracts";
import Link from "next/link";
import type { ReactNode } from "react";

import type {
  ShadowConnectionState,
  ShadowDecisionReadModel,
} from "../lib/shadow-read-models";
import type { ShadowScreenData } from "../lib/shadow-session";
import {
  Card,
  DefinitionRow,
  EmptyState,
  SectionHeading,
  StatusBadge,
} from "./ui";

const stateText: Record<ShadowConnectionState, string> = {
  not_configured: "ยังไม่ได้ตั้งค่าการเชื่อมต่อที่ปลอดภัย",
  signed_out: "ต้องเข้าสู่ระบบก่อนอ่านข้อมูลของคุณ",
  read_failed: "อ่านบริการไม่ได้ · ไม่ใช้ข้อมูลจำลองทดแทน",
  invalid_data: "หลักฐานไม่ถูกต้องหรือไม่สอดคล้อง · บล็อกการแสดงผล",
  no_data: "ยังไม่มีรอบ Shadow ที่บันทึกไว้",
  stale: "หลักฐานย้อนหลัง · ไม่ใช่สถานะตลาดปัจจุบัน",
  blocked: "รอบล่าสุดถูกบล็อกตามหลักฐาน",
  ready: "อ่านหลักฐานที่บันทึกไว้แล้ว · ไม่ใช่สิทธิ์ซื้อขาย",
};

export function ShadowShell({
  screen,
  title,
  children,
}: {
  screen: ShadowScreenData;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="bg-gold text-canvas fixed top-3 left-3 z-50 -translate-y-24 px-4 py-3 focus:translate-y-0"
      >
        ข้ามไปเนื้อหาหลัก
      </a>
      <header className="border-line bg-surface border-b px-4 py-5">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-4">
          <Link
            href="/dashboard"
            className="text-gold font-display text-xl font-bold"
          >
            AURUM
          </Link>
          <div className="flex flex-wrap gap-2">
            <StatusBadge tone="blocked">DEMO ONLY</StatusBadge>
            <StatusBadge tone="gold">XAU/USD ONLY</StatusBadge>
            <StatusBadge tone="info">SHADOW · READ ONLY</StatusBadge>
          </div>
          <nav aria-label="เมนูหลัก" className="flex flex-wrap gap-4">
            {[
              ["/dashboard", "ภาพรวม"],
              ["/proposals", "ข้อเสนอ"],
              ["/journal", "บันทึกผล"],
              ["/health", "สุขภาพระบบ"],
              ["/position", "Position"],
            ].map(([href, label]) => (
              <Link
                className="text-muted hover:text-gold inline-flex min-h-11 items-center"
                key={href}
                href={href!}
              >
                {label}
              </Link>
            ))}
          </nav>
          {screen.csrf ? (
            <form action="/auth/sign-out" method="post">
              <input type="hidden" name="csrf" value={screen.csrf} />
              <button
                className="border-line min-h-11 border px-3"
                type="submit"
              >
                ออกจากระบบ
              </button>
            </form>
          ) : (
            <Link
              href="/auth/sign-in"
              className="text-gold inline-flex min-h-11 items-center"
            >
              เข้าสู่ระบบ
            </Link>
          )}
        </div>
      </header>
      <main
        id="main-content"
        className="mx-auto max-w-[1480px] space-y-5 px-4 py-6 lg:px-6"
      >
        <div>
          <p className="text-gold font-mono text-xs">
            Production Shadow evidence · ไม่มีความสามารถส่งคำสั่ง
          </p>
          <h1 className="font-display mt-2 text-2xl font-bold">{title}</h1>
        </div>
        <div
          role={
            screen.state === "invalid_data" || screen.state === "blocked"
              ? "alert"
              : "status"
          }
          className="border-warning/40 bg-warning/10 text-warning border px-4 py-3"
        >
          {stateText[screen.state]}{" "}
          <span className="font-mono text-xs">· {screen.state}</span>
        </div>
        <p className="text-muted text-sm leading-6">
          ข้อมูลจากบันทึกฐานข้อมูลของเจ้าของที่เข้าสู่ระบบเท่านั้น
          ไม่ยืนยันการเชื่อมต่อ Terminal ปัจจุบัน ไม่มีการอนุมัติ Override
          หรือส่งคำสั่งโบรกเกอร์
        </p>
        {children}
        <p className="text-muted text-xs">
          อ่านเมื่อ {screen.capturedAt} · UTC · รีเฟรชหน้าเพื่ออ่านหลักฐานใหม่
        </p>
      </main>
      <footer className="border-line text-muted border-t px-4 py-5 text-center text-xs">
        M3 · วิจัยแบบไม่ส่งคำสั่ง ·
        ผลจำลองจากราคาที่สังเกตได้ไม่ใช่การเติมคำสั่งหรือกำไรจริง
      </footer>
    </div>
  );
}

export function ShadowEmpty() {
  return (
    <EmptyState
      title="ไม่มีหลักฐานที่แสดงได้"
      description="ไม่เติมราคา ประวัติ หรือสถานะปลอดภัยจากตัวอย่าง เมื่อบริการหรือข้อมูลยังไม่พร้อม"
    />
  );
}

export function ShadowCycleList({
  decisions,
  proposalsOnly = false,
}: {
  decisions: readonly ShadowDecisionReadModel[];
  proposalsOnly?: boolean;
}) {
  const visible = decisions.filter(
    ({ cycle }) => !proposalsOnly || cycle.status === "PROPOSAL",
  );
  if (visible.length === 0) return <ShadowEmpty />;
  return (
    <Card labelledBy="cycles-heading">
      <SectionHeading
        id="cycles-heading"
        title={
          proposalsOnly
            ? "ข้อเสนอวิจัยในหน้าปัจจุบัน"
            : "รอบการประเมินที่บันทึกไว้"
        }
        eyebrow="Immutable evidence"
      />
      <ul className="divide-line divide-y">
        {visible.map(({ cycle, outcomes }) => (
          <li key={cycle.id} className="space-y-2 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Link
                href={`/proposals/${cycle.id}`}
                className="text-gold min-h-11 font-mono text-sm break-all"
              >
                {cycle.id}
              </Link>
              <StatusBadge tone={cycle.status === "BLOCK" ? "blocked" : "info"}>
                {cycle.status}
              </StatusBadge>
            </div>
            <p className="text-muted text-sm">
              {cycle.evaluated_at} · {cycle.reason_codes.join(" · ")}
            </p>
            <p className="text-muted text-xs">
              {cycle.candidate?.direction ?? "ไม่มี Candidate"} · Eligibility{" "}
              {cycle.eligibility?.outcome ?? "ยังไม่ประเมิน"} · ผลสังเกต{" "}
              {outcomes.at(-1)?.status ?? "ยังไม่มีบันทึก"}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function ShadowMarketEvidence({ cycle }: { cycle: ShadowCycle }) {
  const market = cycle.market;
  return (
    <Card labelledBy="market-heading">
      <SectionHeading
        id="market-heading"
        title="หลักฐานตลาด XAU/USD"
        eyebrow="Captured native observation · ไม่ใช่ราคา streaming"
      />
      {market === null ? (
        <ShadowEmpty />
      ) : (
        <dl>
          <DefinitionRow
            label="Bid / Ask ที่บันทึก"
            value={`${market.bid} / ${market.ask}`}
          />
          <DefinitionRow
            label="เวลาราคา / เวลาบันทึก"
            value={`${market.tick_at} / ${market.captured_at}`}
          />
          <DefinitionRow
            label="SMA3 / SMA5 / ATR5"
            value={`${market.fast_sma} / ${market.slow_sma} / ${market.atr}`}
          />
          <DefinitionRow
            label="แท่ง M1 ที่ปิดแล้ว"
            value={`${market.bars.length} · ${market.last_bar_closed_at}`}
          />
          <DefinitionRow
            label="Source / symbol"
            value={`mt5 · ${market.broker_symbol}`}
          />
          <DefinitionRow
            label="Adapter / market policy"
            value={`${market.adapter_version} / ${market.market_time_policy}`}
          />
          <DefinitionRow
            label="Reconciliation"
            value={market.reconciliation_id}
          />
        </dl>
      )}
    </Card>
  );
}

export function ShadowDecisionEvidence({
  decision,
}: {
  decision: ShadowDecisionReadModel;
}) {
  const { cycle } = decision;
  const checkGroups = [
    { label: "Risk", checks: cycle.risk?.checks },
    { label: "Eligibility", checks: cycle.eligibility?.checks },
  ];
  return (
    <div className="space-y-5">
      <ShadowMarketEvidence cycle={cycle} />
      <Card labelledBy="decision-heading">
        <SectionHeading
          id="decision-heading"
          title="Candidate และการตรวจความเสี่ยง"
          eyebrow="Non-executable research proposal"
        />
        <dl>
          <DefinitionRow
            label="สถานะ / เหตุผล"
            value={`${cycle.status} · ${cycle.reason_codes.join(" · ")}`}
          />
          <DefinitionRow
            label="ทิศทาง / Entry"
            value={
              cycle.candidate
                ? `${cycle.candidate.direction} / ${cycle.candidate.entry_price}`
                : "ยังไม่มีหลักฐาน"
            }
          />
          <DefinitionRow
            label="Stop Loss / Take Profit"
            value={
              cycle.candidate
                ? `${cycle.candidate.stop_loss_price} / ${cycle.candidate.take_profit_price}`
                : "ยังไม่มีหลักฐาน"
            }
          />
          <DefinitionRow
            label="หมดอายุ"
            value={cycle.candidate?.expires_at ?? "ไม่มี Candidate"}
          />
          <DefinitionRow
            label="Risk / volume"
            value={`${cycle.risk?.outcome ?? "ยังไม่ประเมิน"} / ${cycle.risk?.calculated_volume ?? "ไม่มี"}`}
          />
          <DefinitionRow
            label="ประมาณการ loss / net reward USD"
            value={`${cycle.risk?.estimated_loss_usd ?? "ไม่มี"} / ${cycle.risk?.estimated_net_reward_usd ?? "ไม่มี"}`}
          />
          <DefinitionRow
            label="Eligibility / samples"
            value={
              cycle.eligibility
                ? `${cycle.eligibility.outcome} / ${cycle.eligibility.sample_count} จากขั้นต่ำ ${cycle.eligibility.minimum_sample_size}`
                : "ยังไม่ประเมิน"
            }
          />
          <DefinitionRow
            label="สิทธิ์ซื้อขาย"
            value="ไม่มี · grants_eligibility = false"
            emphasized
          />
        </dl>
        <p className="text-muted my-4 text-sm">
          จำนวนตัวอย่างศูนย์เมื่อไม่มีหลักฐาน ไม่ใช่จำนวนตัวอย่างสำเร็จ
          ไม่มีความน่าจะเป็นที่สอบเทียบแล้ว
        </p>
        {checkGroups.map(({ label, checks }) => (
          <div key={label}>
            <h3 className="text-ink mt-4 font-semibold">{label}</h3>
            <ul>
              {checks ? (
                checks.map((check) => (
                  <li
                    key={check.code}
                    className="text-muted py-1 font-mono text-xs"
                  >
                    {check.code} · {check.passed ? "PASS" : "BLOCK"}
                  </li>
                ))
              ) : (
                <li className="text-muted text-sm">ยังไม่ประเมิน</li>
              )}
            </ul>
          </div>
        ))}
      </Card>
      <Card labelledBy="provenance-heading">
        <SectionHeading id="provenance-heading" title="เวอร์ชันและตัวอ้างอิง" />
        <dl>
          <DefinitionRow
            label="Cycle / trace"
            value={`${cycle.id} / ${cycle.trace_id}`}
          />
          <DefinitionRow
            label="Pipeline / strategy"
            value={`${cycle.pipeline_version} / ${cycle.strategy_version}`}
          />
          <DefinitionRow
            label="Policy / mode version"
            value={`${cycle.policy_version ?? "ไม่มี"} / ${cycle.mode_version ?? "ไม่มี"}`}
          />
          <DefinitionRow
            label="Risk input digest"
            value={cycle.risk?.input_digest ?? "ยังไม่มีหลักฐาน"}
          />
        </dl>
        <ul className="divide-line divide-y">
          {cycle.risk?.source_receipts.map((receipt) => (
            <li
              key={receipt.kind}
              className="text-muted space-y-1 py-3 text-xs break-all"
            >
              <p>
                {receipt.kind} · {receipt.source_id} · {receipt.source_version}
              </p>
              <p>Digest {receipt.evidence_digest}</p>
              <p>
                สังเกต {receipt.observed_at} · ใช้ได้ถึง {receipt.valid_until}
              </p>
              <p>
                ช่วงครอบคลุม {receipt.covered_from ?? "ไม่ได้ระบุ"} /{" "}
                {receipt.covered_until ?? "ไม่ได้ระบุ"}
              </p>
            </li>
          ))}
        </ul>
        <p className="text-muted mt-3 text-xs">
          Digest และใบรับแหล่งข้อมูลเป็นตัวอ้างอิง ไม่ใช่ประวัติ ledger
          เต็มหรือหลักฐานการเติมคำสั่ง
        </p>
      </Card>
      <ShadowJournal decisions={[decision]} />
    </div>
  );
}

export function ShadowJournal({
  decisions,
}: {
  decisions: readonly ShadowDecisionReadModel[];
}) {
  return (
    <Card labelledBy="journal-heading">
      <SectionHeading
        id="journal-heading"
        title="บันทึกผลสังเกตแบบสมมติ"
        eyebrow="Quote-observed only · net P/L unavailable"
      />
      <p className="text-muted mb-4 text-sm leading-6">
        STOP/TARGET หมายถึงราคาที่สังเกตได้ ไม่ใช่การยืนยัน fill
        ไม่มีสมมติฐานเส้นทางราคาในช่วงที่ขาดข้อมูล ผล UNKNOWN คงเป็นไม่ทราบ
        และไม่คำนวณกำไรสุทธิ
      </p>
      {decisions.length === 0 ? (
        <ShadowEmpty />
      ) : (
        <ul className="divide-line divide-y">
          {decisions.map(({ cycle, outcomes }) => (
            <li key={cycle.id} className="py-4">
              <Link
                className="text-gold font-mono text-sm break-all"
                href={`/proposals/${cycle.id}`}
              >
                {cycle.id} · {cycle.status}
              </Link>
              {outcomes.length === 0 ? (
                <p className="text-muted mt-2 text-sm">
                  ยังไม่มีผลสังเกต · ไม่ใช่กำไรศูนย์หรือไม่มีความเสี่ยง
                </p>
              ) : (
                <ol className="mt-3 space-y-3">
                  {outcomes.map((event) => (
                    <li key={event.id} className="text-muted text-sm">
                      {event.sequence}. {event.status} · {event.reason_code} ·{" "}
                      {event.observed_at}
                      <br />
                      Bid/Ask {event.bid ?? "ไม่มี"} / {event.ask ?? "ไม่มี"} ·
                      Source {event.price_source} · Net P/L ไม่มีข้อมูล
                    </li>
                  ))}
                </ol>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function ShadowPagination({
  screen,
  path,
}: {
  screen: ShadowScreenData;
  path: "/journal" | "/proposals";
}) {
  const page = screen.page;
  if (!page) return null;
  return (
    <nav
      aria-label="หน้าบันทึก"
      className="flex min-h-11 items-center gap-6 text-sm"
    >
      {page.page > 0 ? (
        <Link className="text-gold" href={`${path}?page=${page.page - 1}`}>
          ใหม่กว่า
        </Link>
      ) : null}
      <span className="text-muted">
        หน้า {page.page + 1} · ไม่เกิน 20 รอบต่อหน้า
      </span>
      {page.hasMore ? (
        <Link className="text-gold" href={`${path}?page=${page.page + 1}`}>
          เก่ากว่า
        </Link>
      ) : null}
    </nav>
  );
}
