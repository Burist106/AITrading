import type { PrototypeScenarioId } from "@aurum/contracts";
import type { ScenarioPresentation } from "@aurum/fixtures";
import Link from "next/link";
import type { ReactNode } from "react";

import { withScenario } from "../lib/scenario";
import { StateSimulatorGate } from "./StateSimulatorGate";
import { StatusBadge, type Tone } from "./ui";

const navItems = [
  ["/dashboard", "ภาพรวม"],
  ["/proposals/demo-proposal", "ข้อเสนอ"],
  ["/position", "Position"],
  ["/health", "สุขภาพระบบ"],
] as const;

function connectionTone(state: ScenarioPresentation["mt5State"]): Tone {
  return state === "connected"
    ? "success"
    : state === "reconnecting"
      ? "warning"
      : "critical";
}

function freshnessTone(state: ScenarioPresentation["marketFreshness"]): Tone {
  return state === "live"
    ? "success"
    : state === "delayed" || state === "fallback"
      ? "warning"
      : "critical";
}

function systemTone(state: ScenarioPresentation["systemState"]): Tone {
  return state === "running"
    ? "success"
    : state === "paused" || state === "recovering"
      ? "warning"
      : "critical";
}

function BlockingBanner({ scenario }: { scenario: ScenarioPresentation }) {
  if (
    scenario.systemState === "running" &&
    scenario.accountVerification === "verified_demo"
  )
    return null;

  const critical =
    scenario.accountVerification === "blocked_non_demo" ||
    scenario.emergencyState === "unconfirmed";
  return (
    <div
      role={critical ? "alert" : "status"}
      className={`border-b px-4 py-3 lg:px-6 ${critical ? "border-critical bg-critical-fill text-white" : "border-warning/40 bg-warning/10 text-warning"}`}
    >
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-start justify-between gap-2">
        <p className="font-semibold">
          {scenario.accountVerification === "blocked_non_demo"
            ? "บล็อกระบบ: ตรวจพบบัญชีที่ไม่ใช่ Demo"
            : scenario.descriptionTh}
        </p>
        <span className="font-mono text-xs uppercase">
          Fail closed · ไม่มี Override
        </span>
      </div>
    </div>
  );
}

export function ApplicationShell({
  children,
  scenario,
  scenarioId,
}: {
  children: ReactNode;
  scenario: ScenarioPresentation;
  scenarioId: PrototypeScenarioId;
}) {
  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="bg-gold text-canvas fixed top-3 left-3 z-50 -translate-y-24 px-4 py-3 font-semibold transition-transform focus:translate-y-0"
      >
        ข้ามไปเนื้อหาหลัก
      </a>
      <header className="border-line bg-surface/95 border-b backdrop-blur">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-4 px-4 py-4 lg:px-6">
          <Link
            href={withScenario("/dashboard", scenarioId)}
            className="flex min-h-11 items-center gap-3"
            aria-label="Aurum Console — หน้าภาพรวม"
          >
            <span
              aria-hidden="true"
              className="border-gold font-display text-gold grid size-10 place-items-center border text-lg font-bold"
            >
              A
            </span>
            <span>
              <span className="font-display block text-base font-bold tracking-[0.06em]">
                AURUM
              </span>
              <span className="text-muted block font-mono text-[0.7rem] tracking-[0.12em] uppercase">
                XAU/USD Research Console
              </span>
            </span>
          </Link>
          <div
            className="flex flex-wrap items-center justify-end gap-2"
            aria-label="ข้อจำกัดระบบถาวร"
          >
            <StatusBadge tone="blocked">DEMO ONLY</StatusBadge>
            <StatusBadge tone="gold">XAU/USD ONLY</StatusBadge>
            <StatusBadge tone="info">SHADOW · READ ONLY</StatusBadge>
          </div>
        </div>
        <div className="border-line/70 border-t">
          <div className="mx-auto flex max-w-[1480px] flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6">
            <nav aria-label="เมนูหลัก" className="-mx-2 flex overflow-x-auto">
              {navItems.map(([href, label]) => (
                <Link
                  key={href}
                  href={withScenario(href, scenarioId)}
                  className="text-muted hover:border-gold hover:text-ink flex min-h-11 shrink-0 items-center border-b-2 border-transparent px-3 text-sm font-medium"
                >
                  {label}
                </Link>
              ))}
            </nav>
            <div className="flex flex-wrap gap-2" aria-label="สถานะระบบทั่วโลก">
              <StatusBadge tone={systemTone(scenario.systemState)}>
                ระบบ {scenario.systemState}
              </StatusBadge>
              <StatusBadge tone={connectionTone(scenario.mt5State)}>
                MT5 {scenario.mt5State} · fixture
              </StatusBadge>
              <StatusBadge tone={freshnessTone(scenario.marketFreshness)}>
                ข้อมูล {scenario.marketFreshness} · simulated
              </StatusBadge>
            </div>
          </div>
        </div>
      </header>
      <BlockingBanner scenario={scenario} />
      <StateSimulatorGate />
      <main
        id="main-content"
        className="mx-auto max-w-[1480px] px-4 py-6 lg:px-6 lg:py-8"
      >
        {children}
      </main>
      <footer className="border-line text-muted border-t px-4 py-5 text-center text-xs leading-5">
        Aurum Console Bootstrap · Fixture เท่านั้น ·
        ไม่เชื่อมต่อบัญชีหรือข้อมูลรับรองจริง
      </footer>
    </div>
  );
}
