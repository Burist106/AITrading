import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs, {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, test } from "node:test";

import {
  enumerateTrackedTextFiles,
  enumerateRepositoryTextFiles,
  formatFinding,
  scanRepositorySecrets,
  scanText,
} from "../lib/secret-scanner.mjs";
import {
  scanRuntimeFiles,
  scanTypeScriptSource,
} from "../runtime-boundary-check.mjs";

const temporaryDirectories = [];
const projectRoot = resolve(import.meta.dirname, "..", "..");

function temporaryDirectory(prefix) {
  const directory = mkdtempSync(join(tmpdir(), prefix));
  temporaryDirectories.push(directory);
  return directory;
}

function git(root, ...args) {
  return execFileSync("git", ["-C", root, ...args], { encoding: "utf8" });
}

function initializeRepository(root) {
  git(root, "init", "--initial-branch=main");
  git(root, "config", "core.autocrlf", "false");
  git(root, "config", "user.email", "scanner-test@invalid.example");
  git(root, "config", "user.name", "Scanner Test");
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { force: true, recursive: true });
  }
});

test("tracked-file enumeration includes Markdown, PowerShell, and shell scripts", () => {
  const root = temporaryDirectory("aurum-secret-files-");
  initializeRepository(root);
  writeFileSync(join(root, "README.md"), "safe documentation\n");
  writeFileSync(join(root, "Dockerfile"), "FROM scratch\n");
  writeFileSync(join(root, ".env.example"), "EXAMPLE_VALUE=\n");
  writeFileSync(join(root, "verify.ps1"), "Write-Output 'safe'\n");
  writeFileSync(join(root, "verify.sh"), "#!/bin/sh\nprintf '%s\\n' safe\n");
  git(root, "add", ".");
  git(root, "commit", "-m", "safe fixtures");

  assert.deepEqual(enumerateTrackedTextFiles(root).sort(), [
    ".env.example",
    "Dockerfile",
    "README.md",
    "verify.ps1",
    "verify.sh",
  ]);
});

test("repository secret scan includes new untracked source and deduplicates index entries", () => {
  const root = temporaryDirectory("aurum-secret-untracked-");
  initializeRepository(root);
  writeFileSync(join(root, "tracked.md"), "safe documentation\n");
  git(root, "add", "tracked.md");
  writeFileSync(join(root, "intent.ts"), "export const safe = true;\n");
  git(root, "add", "-N", "intent.ts");
  const synthetic = `AKIA${"C".repeat(16)}`;
  writeFileSync(join(root, "new.ts"), `export const value = '${synthetic}';\n`);
  assert.deepEqual(enumerateRepositoryTextFiles(root).sort(), [
    "intent.ts",
    "new.ts",
    "tracked.md",
  ]);
  const result = scanRepositorySecrets(root, { includeHistory: false });
  assert.equal(result.repositoryFileCount, 3);
  assert.equal(result.findings.length, 1);
  assert.equal(result.findings[0].reference, "file:new.ts");
  assert.equal(formatFinding(result.findings[0]).includes(synthetic), false);
});

test("runtime scan includes untracked production code but keeps its existing source roots", () => {
  const root = temporaryDirectory("aurum-runtime-untracked-");
  initializeRepository(root);
  mkdirSync(join(root, "apps", "web"), { recursive: true });
  mkdirSync(join(root, "tests"));
  writeFileSync(
    join(root, "apps", "web", "tracked.ts"),
    "export const safe = 1;\n",
  );
  git(root, "add", "apps/web/tracked.ts");
  writeFileSync(
    join(root, "apps", "web", "intent.ts"),
    "export const safe = 2;\n",
  );
  git(root, "add", "-N", "apps/web/intent.ts");
  writeFileSync(
    join(root, "apps", "web", "new.ts"),
    "broker.order_send({});\n",
  );
  writeFileSync(join(root, "tests", "outside.ts"), "broker.order_send({});\n");
  const result = scanRuntimeFiles(root);
  assert.equal(result.fileCount, 3);
  assert.equal(result.findings.length, 1);
  assert.equal(result.findings[0].reference, "apps/web/new.ts");
  assert.match(result.findings[0].category, /order_send/u);
});

test("both inventories exclude ignored environment/profile/source files before reading contents", (t) => {
  const root = temporaryDirectory("aurum-scanner-ignore-");
  initializeRepository(root);
  writeFileSync(join(root, ".gitignore"), ".env*\n*.dpapi\nignored/\n");
  mkdirSync(join(root, "apps", "web", "ignored"), { recursive: true });
  const ignored = [
    join(root, ".env.local"),
    join(root, "apps", "web", "local.dpapi"),
    join(root, "apps", "web", "ignored", "private.ts"),
  ];
  for (const path of ignored)
    writeFileSync(path, "fictional ignored test data\n");
  writeFileSync(
    join(root, "apps", "web", "new.ts"),
    "export const safe = true;\n",
  );
  const originalRead = fs.readFileSync;
  const spy = t.mock.method(fs, "readFileSync", (path, ...options) => {
    assert.equal(ignored.includes(resolve(String(path))), false);
    return originalRead(path, ...options);
  });
  syncBuiltinESMExports();
  try {
    const secrets = scanRepositorySecrets(root, { includeHistory: false });
    assert.equal(secrets.repositoryFileCount, 2);
    assert.deepEqual(secrets.findings, []);
    assert.deepEqual(scanRuntimeFiles(root), { findings: [], fileCount: 1 });
    assert.equal(spy.mock.callCount() > 0, true);
  } finally {
    spy.mock.restore();
    syncBuiltinESMExports();
  }
});

test("Git-history scan detects a removed synthetic secret without exposing it", () => {
  const root = temporaryDirectory("aurum-secret-history-");
  initializeRepository(root);
  const synthetic = `AKIA${"A".repeat(16)}`;
  writeFileSync(join(root, "removed.md"), `synthetic=${synthetic}\n`);
  git(root, "add", "removed.md");
  git(root, "commit", "-m", "synthetic history fixture");
  rmSync(join(root, "removed.md"));
  git(root, "add", "-u");
  git(root, "commit", "-m", "remove fixture");

  const result = scanRepositorySecrets(root);
  assert.equal(
    result.findings.some(({ reference }) => reference.includes("removed.md")),
    true,
  );
  const report = result.findings.map(formatFinding).join("\n");
  assert.equal(report.includes(synthetic), false);
  assert.match(report, /sha256:[a-f0-9]{12}/u);
});

test("formatted findings never include the discovered value", () => {
  const synthetic = `ghp_${"B".repeat(32)}`;
  const findings = scanText(synthetic, "file:synthetic.txt");
  assert.equal(findings.length, 1);
  assert.equal(formatFinding(findings[0]).includes(synthetic), false);
});

test("secret assignment names do not match safe function suffixes or exempt real assignment shapes", () => {
  assert.deepEqual(
    scanText(
      "export const sessionCookie = (config: WebConfiguration) => null;",
      "safe.ts",
    ),
    [],
  );
  for (const name of ["COOKIE", "SESSION_COOKIE", "REFRESH_TOKEN"]) {
    const source = `${name}=${"Q".repeat(32)}`;
    assert.equal(scanText(source, "different.ts").length, 1);
  }
});

test("runtime boundary scan ignores documentation mentions", () => {
  const root = temporaryDirectory("aurum-runtime-doc-");
  const documentation = join(root, "README.md");
  writeFileSync(documentation, "order_send is forbidden documentation.\n");
  assert.deepEqual(scanRuntimeFiles(projectRoot, [documentation]).findings, []);
});

test("runtime boundary scan detects forbidden Python calls and dynamic dispatch", () => {
  const root = temporaryDirectory("aurum-runtime-python-");
  const source = join(root, "unsafe.py");
  writeFileSync(
    source,
    [
      "def unsafe(mt5, method_name):",
      "    mt5.order_send({})",
      "    mt5.market_book_get('XAUUSD')",
      "    return getattr(mt5, method_name)()",
      "",
    ].join("\n"),
  );
  const categories = scanRuntimeFiles(projectRoot, [source]).findings.map(
    ({ category }) => category,
  );
  assert.equal(
    categories.some((value) => value.includes("order_send")),
    true,
  );
  assert.equal(
    categories.some((value) => value.includes("market_book_get")),
    true,
  );
  assert.equal(categories.includes("forbidden dynamic MT5 dispatch"), true);
});

test("runtime boundary scan rejects every market_book-prefixed call", () => {
  const findings = scanTypeScriptSource(
    "broker.market_book_subscribe('XAUUSD');\n",
    "apps/worker/src/unsafe.ts",
  );
  assert.equal(
    findings.some(({ category }) => category.includes("market_book_subscribe")),
    true,
  );
});

test("workflow actions are immutable and checkout credentials are not persisted", () => {
  const workflow = readFileSync(
    resolve(projectRoot, ".github", "workflows", "ci.yml"),
    "utf8",
  );
  const uses = [...workflow.matchAll(/uses:\s+[^@\s]+@([^\s#]+)/gu)].map(
    (match) => match[1],
  );
  assert.equal(uses.length > 0, true);
  assert.equal(
    uses.every((reference) => /^[a-f0-9]{40}$/u.test(reference)),
    true,
  );
  const checkoutCount = (workflow.match(/actions\/checkout@/gu) ?? []).length;
  const credentialCount = (
    workflow.match(/persist-credentials:\s+false/gu) ?? []
  ).length;
  assert.equal(credentialCount, checkoutCount);
});
