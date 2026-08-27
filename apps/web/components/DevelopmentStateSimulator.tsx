"use client";

import { scenarioStore } from "@aurum/fixtures";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const productionExclusionMarker = "AURUM_DEVELOPMENT_STATE_SIMULATOR";

export default function DevelopmentStateSimulator() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const selected =
    searchParams.get("scenario") ?? scenarioStore.defaultScenarioId;

  function changeScenario(value: string) {
    const next = new URLSearchParams(searchParams.toString());
    next.set("scenario", value);
    router.replace(`${pathname}?${next.toString()}`);
  }

  return (
    <aside
      aria-labelledby="state-simulator-title"
      data-bundle-marker={productionExclusionMarker}
      className="border-info/30 bg-info/8 border-b px-4 py-3 lg:px-6"
    >
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-3">
        <div className="min-w-48 flex-1">
          <p
            id="state-simulator-title"
            className="text-info font-mono text-[0.7rem] tracking-[0.12em] uppercase"
          >
            Development State Simulator
          </p>
          <p className="text-muted mt-1 text-xs">
            เปลี่ยนเฉพาะ Fixture ที่แสดงผล · ไม่เปลี่ยนโหมดหรือส่งคำสั่ง
          </p>
        </div>
        <label className="sr-only" htmlFor="scenario-select">
          สถานะจำลอง
        </label>
        <select
          id="scenario-select"
          value={selected}
          onChange={(event) => changeScenario(event.target.value)}
          className="border-info/50 bg-canvas text-ink min-h-11 min-w-64 border px-3 text-sm"
        >
          {scenarioStore.scenarios.map((scenario) => (
            <option key={scenario.id} value={scenario.id}>
              {scenario.labelTh} · {scenario.labelEn}
            </option>
          ))}
        </select>
      </div>
    </aside>
  );
}
