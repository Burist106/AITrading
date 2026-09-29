import { ShadowCycleSchema, ShadowOutcomeSchema } from "@aurum/contracts";
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import parity from "../../../contract-fixtures/v1/shadow-parity.json";
import {
  ShadowCycleList,
  ShadowDecisionEvidence,
  ShadowEmpty,
  ShadowShell,
} from "../components/ShadowConsole";
import type { ShadowConnectionState } from "../lib/shadow-read-models";
import type { ShadowScreenData } from "../lib/shadow-session";

const decision = {
  cycle: ShadowCycleSchema.parse(parity.cycle),
  outcomes: [ShadowOutcomeSchema.parse(parity.outcome)],
};
const data: ShadowScreenData = {
  state: "stale",
  capturedAt: "2026-08-27T12:01:00Z",
  csrf: null,
  page: null,
  decision,
};

describe("production Shadow console", () => {
  it.each([
    "not_configured",
    "signed_out",
    "read_failed",
    "invalid_data",
    "no_data",
    "stale",
    "blocked",
    "ready",
  ] satisfies ShadowConnectionState[])(
    "renders explicit %s without sample market values",
    (state) => {
      const { container } = render(
        <ShadowShell screen={{ ...data, state }} title="ภาพรวม">
          <ShadowEmpty />
        </ShadowShell>,
      );
      expect(screen.getByText("DEMO ONLY")).toBeVisible();
      expect(screen.getByText("SHADOW · READ ONLY")).toBeVisible();
      expect(
        screen.getByRole(
          state === "blocked" || state === "invalid_data" ? "alert" : "status",
        ),
      ).toHaveTextContent(state);
      expect(container.textContent).not.toContain("demo-proposal");
      expect(container.textContent).not.toContain("2000.02");
    },
  );
  it("links actual cycle UUIDs and renders immutable evidence without trading controls", () => {
    render(
      <ShadowShell screen={data} title="รายละเอียด">
        <ShadowDecisionEvidence decision={decision} />
      </ShadowShell>,
    );
    expect(
      screen.getByRole("link", { name: `${decision.cycle.id} · PROPOSAL` }),
    ).toHaveAttribute("href", `/proposals/${decision.cycle.id}`);
    expect(
      screen.getByText("ไม่มี · grants_eligibility = false"),
    ).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/QUOTE_GAP/)).toBeVisible();
    expect(screen.getByText(/Net P\/L ไม่มีข้อมูล/)).toBeVisible();
  });
  it("provides only authenticated sign-out, never approval or execution controls", () => {
    render(
      <ShadowShell screen={{ ...data, csrf: "a".repeat(64) }} title="ภาพรวม">
        <ShadowEmpty />
      </ShadowShell>,
    );
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button")).toHaveTextContent("ออกจากระบบ");
  });
  it("retains explicit no-proposal state for a page of blocked cycles", () => {
    render(
      <ShadowCycleList
        decisions={[
          { ...decision, cycle: { ...decision.cycle, status: "BLOCK" } },
        ]}
        proposalsOnly
      />,
    );
    expect(
      screen.getByRole("heading", { name: "ไม่มีหลักฐานที่แสดงได้" }),
    ).toBeVisible();
  });
  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <ShadowShell screen={data} title="รายละเอียด">
        <ShadowDecisionEvidence decision={decision} />
      </ShadowShell>,
    );
    const result = await axe.run(container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(result.violations).toEqual([]);
  });
  it.each([
    "app/dashboard/page.tsx",
    "app/health/page.tsx",
    "app/position/page.tsx",
    "app/proposals/[id]/page.tsx",
    "app/proposals/page.tsx",
    "app/journal/page.tsx",
    "components/ShadowConsole.tsx",
  ])("keeps production source %s independent of fixtures", (path) => {
    const source = readFileSync(path, "utf8");
    expect(source).not.toMatch(
      /@aurum\/fixtures|lib\/scenario|loadScenarioView|mt5-fixture|demo-proposal/u,
    );
  });
});
