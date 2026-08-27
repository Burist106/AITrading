import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, test } from "node:test";

import {
  enumerateTrackedTextFiles,
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
  writeFileSync(join(root, "verify.ps1"), "Write-Output 'safe'\n");
  writeFileSync(join(root, "verify.sh"), "#!/bin/sh\nprintf '%s\\n' safe\n");
  git(root, "add", ".");
  git(root, "commit", "-m", "safe fixtures");

  assert.deepEqual(enumerateTrackedTextFiles(root).sort(), [
    "README.md",
    "verify.ps1",
    "verify.sh",
  ]);
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
