import { existsSync } from "node:fs";
import { readFile, rename, unlink, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { format, resolveConfig } from "prettier";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const localSupabaseWrapper = resolve(
  projectRoot,
  "scripts",
  "supabase-local.mjs",
);
const target = resolve(
  projectRoot,
  "packages",
  "contracts",
  "src",
  "database.generated.ts",
);
const mode = process.argv[2];

if (mode !== "--write" && mode !== "--check") {
  console.error(
    "Usage: node scripts/generate-database-types.mjs <--write|--check>",
  );
  process.exit(2);
}

const result = spawnSync(process.execPath, [localSupabaseWrapper, "types"], {
  cwd: projectRoot,
  encoding: "utf8",
  env: {
    ...process.env,
    CI: "1",
    CLAUDECODE: "",
    NO_COLOR: "1",
    SUPABASE_NO_UPDATE_NOTIFIER: "1",
  },
  maxBuffer: 16 * 1024 * 1024,
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});

if (result.status !== 0) {
  const detail = result.error?.code
    ? ` (${result.error.code})`
    : Number.isInteger(result.status)
      ? ` (exit ${result.status})`
      : "";
  console.error(`Local database type generation failed${detail}.`);
  process.exit(1);
}

const rawGenerated = `${result.stdout.replace(/\r\n/gu, "\n").trimEnd()}\n`;

if (
  !rawGenerated.includes("export type Database") ||
  rawGenerated.includes("<claude-code-hint")
) {
  console.error("Supabase returned invalid or contaminated TypeScript output.");
  process.exit(1);
}

const prettierConfig = (await resolveConfig(target)) ?? {};
const generated = await format(rawGenerated, {
  ...prettierConfig,
  filepath: target,
});

const current = existsSync(target)
  ? (await readFile(target, "utf8")).replace(/\r\n/gu, "\n")
  : null;

if (mode === "--check") {
  if (current !== generated) {
    console.error(
      "Generated database types are missing or stale. Run pnpm db:types:generate.",
    );
    process.exit(1);
  }

  console.log("Generated database types match the local schema.");
  process.exit(0);
}

if (current === generated) {
  console.log("Generated database types are already current.");
  process.exit(0);
}

const temporaryTarget = `${target}.tmp-${process.pid}-${Date.now()}`;

try {
  await writeFile(temporaryTarget, generated, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600,
  });
  await rename(temporaryTarget, target);
} catch (error) {
  await unlink(temporaryTarget).catch(() => undefined);
  throw error;
}

console.log("Generated database types were updated atomically.");
