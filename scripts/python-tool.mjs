import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import process from "node:process";

const candidates =
  process.platform === "win32"
    ? [".venv/Scripts/python.exe", "python.exe", "python"]
    : [".venv/bin/python", "python3", "python"];

const executable = candidates.find((candidate) =>
  candidate.includes("/") ? existsSync(candidate) : true,
);

if (!executable) {
  throw new Error("Python 3.13 is required but was not found.");
}

const args = process.argv.slice(2);
if (args.length === 0) {
  throw new Error("Expected a Python module and its arguments.");
}

const result = spawnSync(executable, ["-m", ...args], {
  cwd: process.cwd(),
  encoding: "utf8",
  stdio: "inherit",
});

if (result.error) {
  throw result.error;
}

process.exit(result.status ?? 1);
