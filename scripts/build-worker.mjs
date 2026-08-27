import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import process from "node:process";

const candidates =
  process.platform === "win32"
    ? [resolve(".venv/Scripts/python.exe"), "python.exe", "python"]
    : [resolve(".venv/bin/python"), "python3", "python"];

const executable = candidates.find((candidate) =>
  candidate.includes("/") || candidate.includes("\\")
    ? existsSync(candidate)
    : true,
);

if (!executable) {
  throw new Error("Python 3.13 is required but was not found.");
}

const result = spawnSync(executable, ["-m", "hatchling", "build"], {
  cwd: "apps/worker",
  encoding: "utf8",
  stdio: "inherit",
});

if (result.error) throw result.error;
process.exit(result.status ?? 1);
