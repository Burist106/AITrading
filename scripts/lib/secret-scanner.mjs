import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { extname, resolve } from "node:path";
import { execFileSync, spawnSync } from "node:child_process";

const MAX_TEXT_BYTES = 2 * 1024 * 1024;
const TEXT_EXTENSIONS = new Set([
  "",
  ".cjs",
  ".css",
  ".env",
  ".html",
  ".js",
  ".json",
  ".jsx",
  ".md",
  ".mjs",
  ".ps1",
  ".py",
  ".sh",
  ".sql",
  ".text",
  ".toml",
  ".ts",
  ".tsx",
  ".txt",
  ".yaml",
  ".yml",
]);
// Exact hashes of two reviewed credential-shaped negative-test fixtures in
// adapters.test.ts and domain-parity.json. Values are never allowlisted by path.
const REVIEWED_SYNTHETIC_FINGERPRINTS = new Set([
  "cfde27bb192610e928089ceaaef3936d5a8119d53f2d8b04d1ce2bcc55feeb13",
  "d714ed94567128fadf8f331a2295dfe7820a23e8c9b08d8eb17e46f3c76e1806",
]);

function pattern(...parts) {
  return new RegExp(parts.join(""), "giu");
}

const SECRET_PATTERNS = [
  [
    "private key",
    pattern("-----BEGIN ", "(?:RSA |EC |OPENSSH )?", "PRIVATE KEY-----"),
  ],
  [
    "OpenAI API key",
    pattern("\\b", "sk-(?:proj-)?", "[A-Za-z0-9_-]{20,}", "\\b"),
  ],
  ["GitHub token", pattern("\\b", "gh[opusr]_", "[A-Za-z0-9]{30,}", "\\b")],
  ["AWS access key", pattern("\\b", "AKIA", "[0-9A-Z]{16}", "\\b")],
  [
    "Supabase secret key",
    pattern("\\b", "sb_", "secret_", "[A-Za-z0-9_-]{20,}", "\\b"),
  ],
  [
    "JWT or service-role token",
    pattern(
      "\\b",
      "eyJ[A-Za-z0-9_-]{8,}\\.",
      "[A-Za-z0-9_-]{8,}\\.",
      "[A-Za-z0-9_-]{8,}",
      "\\b",
    ),
  ],
  [
    "credential-bearing database URL",
    pattern(
      "\\b(?:postgres(?:ql)?|mysql)://",
      "[^\\s/:@]+:[^\\s/@]+@",
      "(?![^\\s/]*\\.invalid\\b)",
      "[^\\s\"']+",
    ),
  ],
  [
    "authorization token",
    pattern(
      "\\bAuthorization\\s*[:=]\\s*",
      "(?:Bearer|Basic)\\s+",
      "[A-Za-z0-9._~+/-]{12,}={0,2}",
    ),
  ],
  [
    "secret assignment",
    pattern(
      "(?:MT5_(?:PASSWORD|LOGIN_PASSWORD)|SUPABASE_(?:SERVICE_ROLE|SECRET)_KEY|",
      "OPENAI_API_KEY|GITHUB_TOKEN|AWS_SECRET_ACCESS_KEY|LINE_CHANNEL_SECRET|",
      "(?:ACCESS|REFRESH)_TOKEN|COOKIE)\\s*[:=]\\s*[\"']?",
      "([^\\s\"'#]{8,})",
    ),
  ],
];

function git(root, args, options = {}) {
  return execFileSync("git", ["-C", root, ...args], {
    encoding: options.encoding ?? "utf8",
    maxBuffer: options.maxBuffer ?? 128 * 1024 * 1024,
    input: options.input,
  });
}

function isText(buffer, path) {
  if (buffer.length > MAX_TEXT_BYTES || buffer.includes(0)) return false;
  const extension = extname(path).toLowerCase();
  return TEXT_EXTENSIONS.has(extension) || !extension;
}

export function enumerateTrackedTextFiles(root) {
  const output = git(root, ["ls-files", "-z"], { encoding: "buffer" });
  return output
    .toString("utf8")
    .split("\0")
    .filter(Boolean)
    .filter((path) => {
      const absolute = resolve(root, path);
      if (!existsSync(absolute)) return false;
      return isText(readFileSync(absolute), path);
    });
}

export function scanText(content, reference) {
  const findings = [];
  for (const [category, expression] of SECRET_PATTERNS) {
    expression.lastIndex = 0;
    for (const match of content.matchAll(expression)) {
      const value = match[0];
      if (/should-not-persist|example|dummy|changeme/iu.test(value)) continue;
      const fingerprint = createHash("sha256").update(value).digest("hex");
      if (REVIEWED_SYNTHETIC_FINGERPRINTS.has(fingerprint)) continue;
      findings.push({
        reference,
        category,
        fingerprint,
      });
    }
  }
  return findings;
}

function parseBatch(buffer, pathsByOid) {
  const blobs = [];
  let offset = 0;
  while (offset < buffer.length) {
    const newline = buffer.indexOf(10, offset);
    if (newline < 0) break;
    const header = buffer.subarray(offset, newline).toString("utf8");
    offset = newline + 1;
    const parts = header.split(" ");
    if (parts.at(-1) === "missing") continue;
    const [oid, type, sizeText] = parts;
    const size = Number(sizeText);
    if (!oid || !Number.isSafeInteger(size) || size < 0) break;
    const content = buffer.subarray(offset, offset + size);
    offset += size + 1;
    if (type !== "blob") continue;
    const paths = pathsByOid.get(oid) ?? ["unknown"];
    blobs.push({ oid, paths, content });
  }
  return blobs;
}

export function enumerateHistoryTextBlobs(root) {
  const objectLines = git(root, ["rev-list", "--objects", "--all"])
    .split(/\r?\n/u)
    .filter(Boolean);
  const pathsByOid = new Map();
  for (const line of objectLines) {
    const separator = line.indexOf(" ");
    const oid = separator < 0 ? line : line.slice(0, separator);
    const path = separator < 0 ? "unknown" : line.slice(separator + 1);
    const paths = pathsByOid.get(oid) ?? [];
    paths.push(path);
    pathsByOid.set(oid, paths);
  }
  const ids = [...pathsByOid.keys()];
  if (ids.length === 0) return [];
  const result = spawnSync("git", ["-C", root, "cat-file", "--batch"], {
    input: `${ids.join("\n")}\n`,
    maxBuffer: 128 * 1024 * 1024,
  });
  if (result.status !== 0) {
    throw new Error("Unable to inspect Git object history safely.");
  }
  return parseBatch(result.stdout, pathsByOid).filter(({ content, paths }) =>
    paths.some((path) => isText(content, path)),
  );
}

export function scanRepositorySecrets(root, { includeHistory = true } = {}) {
  const findings = [];
  const currentFiles = enumerateTrackedTextFiles(root);
  for (const path of currentFiles) {
    findings.push(
      ...scanText(readFileSync(resolve(root, path), "utf8"), `file:${path}`),
    );
  }
  let historyBlobCount = 0;
  if (includeHistory) {
    const blobs = enumerateHistoryTextBlobs(root);
    historyBlobCount = blobs.length;
    for (const { oid, paths, content } of blobs) {
      const path =
        paths.find((candidate) => candidate !== "unknown") ?? "unknown";
      findings.push(
        ...scanText(
          content.toString("utf8"),
          `history:${oid.slice(0, 12)}:${path}`,
        ),
      );
    }
  }
  return { findings, trackedFileCount: currentFiles.length, historyBlobCount };
}

export function formatFinding(finding) {
  return `${finding.reference}: ${finding.category} [sha256:${finding.fingerprint.slice(0, 12)}]`;
}
