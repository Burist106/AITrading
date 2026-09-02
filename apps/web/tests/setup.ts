import "@testing-library/jest-dom/vitest";

import { createElement, type ComponentProps } from "react";
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";

import { UnexpectedConsoleGuard } from "./console-guard";

vi.mock("next/link", () => ({
  default: ({ children, href, ...properties }: ComponentProps<"a">) =>
    createElement("a", { href, ...properties }, children),
}));

let guard: UnexpectedConsoleGuard;
let errorSpy: ReturnType<typeof vi.spyOn>;
let warningSpy: ReturnType<typeof vi.spyOn>;

const onUnhandledRejection = (reason: unknown) => {
  guard.capture("error", ["unhandled rejection", reason]);
};

beforeAll(() => {
  process.on("unhandledRejection", onUnhandledRejection);
});

beforeEach(() => {
  guard = new UnexpectedConsoleGuard();
  errorSpy = vi.spyOn(console, "error").mockImplementation((...values) => {
    guard.capture("error", values);
  });
  warningSpy = vi.spyOn(console, "warn").mockImplementation((...values) => {
    guard.capture("warning", values);
  });
});

afterEach(() => {
  errorSpy.mockRestore();
  warningSpy.mockRestore();
  guard.assertClean();
});

afterAll(() => {
  process.off("unhandledRejection", onUnhandledRejection);
});
