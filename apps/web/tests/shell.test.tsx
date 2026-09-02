import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

import { ApplicationShell } from "../components/ApplicationShell";
import { DashboardView } from "../components/DashboardView";
import DevelopmentStateSimulator from "../components/DevelopmentStateSimulator";
import { HealthView } from "../components/HealthView";
import { ProposalDetailView } from "../components/ProposalDetailView";
import {
  loadScenarioView,
  resolveRuntimeScenarioId,
  withScenario,
} from "../lib/scenario";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));

const axeOptions = {
  // JSDOM has no canvas implementation; token contrast is tested explicitly below.
  rules: { "color-contrast": { enabled: false } },
} as const;

function contrastRatio(first: string, second: string): number {
  const luminance = (hex: string) => {
    const channels = hex
      .slice(1)
      .match(/.{2}/g)!
      .map((channel) => Number.parseInt(channel, 16) / 255)
      .map((channel) =>
        channel <= 0.04045
          ? channel / 12.92
          : ((channel + 0.055) / 1.055) ** 2.4,
      );
    return (
      0.2126 * channels[0]! + 0.7152 * channels[1]! + 0.0722 * channels[2]!
    );
  };
  const lighter = Math.max(luminance(first), luminance(second));
  const darker = Math.min(luminance(first), luminance(second));
  return (lighter + 0.05) / (darker + 0.05);
}

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams("scenario=no_signal"),
}));

vi.mock("../components/StateSimulatorGate", () => ({
  StateSimulatorGate: () => null,
}));

describe("static P0 shell", () => {
  it("keeps the permanent Demo and Shadow identity visible", async () => {
    const view = await loadScenarioView(
      Promise.resolve({ scenario: "no_signal" }),
    );
    render(
      <ApplicationShell scenario={view.scenario} scenarioId={view.scenarioId}>
        <DashboardView view={view} />
      </ApplicationShell>,
    );

    expect(screen.getByText("DEMO ONLY")).toBeVisible();
    expect(screen.getByText("XAU/USD ONLY")).toBeVisible();
    expect(screen.getByText("SHADOW · READ ONLY")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "ศูนย์ควบคุมการวิจัย" }),
    ).toBeVisible();
  });

  it("renders the authoritative Human Approval arithmetic", async () => {
    const view = await loadScenarioView(
      Promise.resolve({ scenario: "human_approval" }),
    );
    render(<ProposalDetailView view={view} />);

    expect(
      screen.getAllByText("5.50 USD", { exact: false }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("0.25%", { exact: false }).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("24 / 30")).toBeVisible();
    expect(screen.getAllByText("ask", { exact: false }).length).toBeGreaterThan(
      0,
    );
  });

  it("does not expose approval, override, or execution controls", async () => {
    const view = await loadScenarioView(
      Promise.resolve({ scenario: "auto_eligible" }),
    );
    render(<ProposalDetailView view={view} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Quality score เป็นหลักฐานประกอบเท่านั้น/),
    ).toBeVisible();
    expect(screen.getByText(/ไม่มีปุ่มอนุมัติ/)).toBeVisible();
  });

  it("treats an unconfirmed emergency stop as an alert", async () => {
    const view = await loadScenarioView(
      Promise.resolve({ scenario: "emergency_stop_unconfirmed" }),
    );
    render(<HealthView view={view} />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "อย่าถือว่าการหยุดสำเร็จ",
    );
    expect(screen.getByText("WORKER_ACK_TIMEOUT")).toBeVisible();
  });

  it("renders the three safe MT5 component identities without sensitive data", async () => {
    const view = await loadScenarioView(
      Promise.resolve({ scenario: "no_signal" }),
    );
    const { container } = render(<HealthView view={view} />);

    expect(screen.getByText("Aurum Worker")).toBeVisible();
    expect(screen.getByText("การเชื่อมต่อ MT5")).toBeVisible();
    expect(screen.getByText("ข้อมูลตลาด XAU/USD")).toBeVisible();
    expect(screen.getByText("••••3456", { exact: false })).toBeVisible();

    const rendered = container.textContent ?? "";
    for (const sensitiveValue of [
      "123456",
      "Aurum-Demo-Server",
      "C:\\Private\\terminal64.exe",
      "Traceback",
      "private-password",
      "private-token",
    ]) {
      expect(rendered).not.toContain(sensitiveValue);
    }
  });

  it("exposes exactly the 20 documented states in development", () => {
    render(<DevelopmentStateSimulator />);
    expect(screen.getAllByRole("option")).toHaveLength(20);
    expect(screen.getByRole("combobox", { name: "สถานะจำลอง" })).toHaveValue(
      "no_signal",
    );
  });

  it("ignores manual scenario queries and propagation in production", () => {
    expect(resolveRuntimeScenarioId("human_approval", "production")).toBe(
      "no_signal",
    );
    expect(withScenario("/dashboard", "human_approval", "production")).toBe(
      "/dashboard",
    );
  });

  it("has no automated accessibility violations in the default shell", async () => {
    const view = await loadScenarioView(
      Promise.resolve({ scenario: "no_signal" }),
    );
    const { container } = render(
      <ApplicationShell scenario={view.scenario} scenarioId={view.scenarioId}>
        <DashboardView view={view} />
      </ApplicationShell>,
    );
    const result = await axe.run(container, axeOptions);
    expect(result.violations).toEqual([]);
  });

  it("keeps every semantic text token at WCAG AA contrast", () => {
    const css = readFileSync("app/globals.css", "utf8");
    const token = (name: string) => {
      const match = css.match(
        new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, "i"),
      );
      if (!match?.[1]) throw new Error(`Missing color token: ${name}`);
      return match[1];
    };
    const pairs = [
      ["ink", "canvas"],
      ["muted", "canvas"],
      ["muted", "surface"],
      ["gold", "canvas"],
      ["buy", "surface"],
      ["sell", "surface"],
      ["blocked", "surface"],
      ["warning", "surface"],
      ["info", "surface"],
      ["critical", "surface"],
      ["ink", "critical-fill"],
    ] as const;
    for (const [foreground, background] of pairs) {
      expect(
        contrastRatio(token(foreground), token(background)),
        `${foreground} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(["emergency_stop_unconfirmed", "live_account_detected"] as const)(
    "has no automated accessibility violations in safety state %s",
    async (scenario) => {
      const view = await loadScenarioView(Promise.resolve({ scenario }));
      const { container } = render(
        <ApplicationShell scenario={view.scenario} scenarioId={view.scenarioId}>
          <HealthView view={view} />
        </ApplicationShell>,
      );
      const result = await axe.run(container, axeOptions);
      expect(result.violations).toEqual([]);
    },
  );
});
