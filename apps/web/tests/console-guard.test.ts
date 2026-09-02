import { describe, expect, it } from "vitest";

import { UnexpectedConsoleGuard } from "./console-guard";

describe("unexpected console guard", () => {
  it("fails closed when console.error was not explicitly handled", () => {
    const guard = new UnexpectedConsoleGuard();
    guard.capture("error", ["unexpected"]);
    expect(() => guard.assertClean()).toThrow(/Unexpected console/u);
  });

  it("accepts a clean test", () => {
    expect(() => new UnexpectedConsoleGuard().assertClean()).not.toThrow();
  });
});
