import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import process from "node:process";

for (const script of ["secret-check.mjs", "runtime-boundary-check.mjs"]) {
  execFileSync(process.execPath, [resolve("scripts", script)], {
    cwd: process.cwd(),
    stdio: "inherit",
  });
}

console.log(
  "Security checks passed: repository secrets and production runtime boundaries are clean.",
);
