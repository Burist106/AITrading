import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import process from "node:process";

function run(executable, args) {
  const result = spawnSync(executable, args, {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: "inherit",
  });

  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

if (!existsSync(".venv")) {
  run(process.platform === "win32" ? "python" : "python3", [
    "-m",
    "venv",
    ".venv",
  ]);
}

const python =
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python";

run(python, ["-m", "pip", "install", "--upgrade", "pip==26.2.1"]);
const extras = process.argv.includes("--mt5") ? "dev,mt5" : "dev";
run(python, ["-m", "pip", "install", "-e", `apps/worker[${extras}]`]);
