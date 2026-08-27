import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";
import process from "node:process";

const roots = [
  "apps",
  "packages",
  "fixtures",
  "contract-fixtures",
  "scripts",
  "supabase",
  ".github",
];
const rootFiles = [
  ".env.example",
  "package.json",
  "pnpm-lock.yaml",
  "pnpm-workspace.yaml",
];
const extensions = new Set([
  ".css",
  ".html",
  ".js",
  ".json",
  ".mjs",
  ".py",
  ".sql",
  ".toml",
  ".ts",
  ".tsx",
  ".yaml",
  ".yml",
]);
const excluded = new Set(["node_modules", ".next", "dist", ".venv"]);
// The scanner necessarily contains the forbidden patterns it searches for.
// Its own source is reviewed by lint/type tooling and cannot be self-scanned
// without creating guaranteed false positives.
const excludedFiles = new Set(["scripts/security-check.mjs"]);

const secretPatterns = [
  ["private key", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/u],
  ["OpenAI key", /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/u],
  ["GitHub token", /\bgh[opusr]_[A-Za-z0-9]{30,}\b/u],
  ["AWS access key", /\bAKIA[0-9A-Z]{16}\b/u],
  ["Supabase secret key", /\bsb_secret_[A-Za-z0-9_-]{20,}\b/u],
  [
    "Supabase service-role JWT",
    /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/u,
  ],
];

const forbiddenRuntimePatterns = [
  [
    "broker order write",
    /\b(?:order_send|OrderSend|submit_order|place_order|send_order)\s*\(/u,
  ],
  [
    "position modification",
    /\b(?:position_(?:modify|close)|Position(?:Modify|Close)|modify_position|close_position)\s*\(/u,
  ],
  ["MetaTrader runtime dependency", /(?:from|import)\s+MetaTrader5\b/u],
  ["Live Trading runtime label", /\bLIVE(?:_|\s+)TRADING\b/iu],
  [
    "prototype runtime dependency",
    /(?:from\s+|import\s*(?:\(\s*)?)["'][^"']*(?:support\.js|[\\/]_ds[\\/])/u,
  ],
  [
    "remote Supabase operation",
    /(?:\bsupabase\s+(?:login|link|db\s+push)\b|--linked\b)/iu,
  ],
];

function walk(path) {
  if (!statSync(path).isDirectory()) return [path];
  return readdirSync(path).flatMap((entry) => {
    if (excluded.has(entry)) return [];
    return walk(join(path, entry));
  });
}

const files = roots
  .filter((root) => exists(root))
  .flatMap(walk)
  .filter((file) => extensions.has(extname(file)))
  .filter(
    (file) =>
      !excludedFiles.has(relative(process.cwd(), file).replaceAll("\\", "/")),
  )
  .concat(rootFiles.filter((file) => exists(file)));

const failures = [];
for (const file of files) {
  const content = readFileSync(file, "utf8");
  for (const [label, pattern] of [
    ...secretPatterns,
    ...forbiddenRuntimePatterns,
  ]) {
    if (pattern.test(content)) {
      failures.push(`${relative(process.cwd(), file)}: ${label}`);
    }
  }

  if (
    relative(process.cwd(), file)
      .replaceAll("\\", "/")
      .startsWith("apps/web/") &&
    /\b(?:SUPABASE_SERVICE_ROLE_KEY|SUPABASE_SECRET_KEY|WORKER_CREDENTIAL)\b/u.test(
      content,
    )
  ) {
    failures.push(
      `${relative(process.cwd(), file)}: privileged credential identifier in frontend`,
    );
  }
}

function exists(path) {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
}

if (failures.length > 0) {
  console.error("Security check failed:\n" + failures.join("\n"));
  process.exit(1);
}

console.log(
  `Security check passed: scanned ${files.length} runtime/configuration files; no high-confidence secrets or forbidden broker-write paths found.`,
);
