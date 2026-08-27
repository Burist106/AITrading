import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { extname, resolve } from "node:path";
import process from "node:process";
import ts from "typescript";

const PRODUCTION_ROOTS = [
  "apps/web",
  "apps/worker/src",
  "packages/contracts/src",
  "fixtures/src",
];
const TYPESCRIPT_EXTENSIONS = new Set([".js", ".jsx", ".mjs", ".ts", ".tsx"]);
const FORBIDDEN_CALLS = new Set([
  "login",
  "market_book_add",
  "market_book_release",
  "order_calc_margin",
  "order_calc_profit",
  "order_check",
  "order_send",
  "position_close",
  "position_modify",
  "symbol_select",
]);
const FORBIDDEN_RUNTIME_FLAGS = new Set([
  "AUTO_TRADING",
  "LIVE_TRADING",
  "MT5_AUTO_LOGIN",
  "MT5_ENABLE_TRADING",
  "MT5_LIVE_ACCOUNT",
]);
const FRONTEND_PRIVILEGED_IDENTIFIERS = new Set([
  "SUPABASE_SERVICE_ROLE_KEY",
  "SUPABASE_SECRET_KEY",
  "WORKER_CREDENTIAL",
]);

function gitTrackedFiles(root) {
  const output = execFileSync(
    "git",
    ["-C", root, "ls-files", "-z", "--", ...PRODUCTION_ROOTS],
    { encoding: "buffer" },
  );
  return output.toString("utf8").split("\0").filter(Boolean);
}

function scriptKind(path) {
  if (path.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (path.endsWith(".jsx")) return ts.ScriptKind.JSX;
  if (path.endsWith(".ts")) return ts.ScriptKind.TS;
  return ts.ScriptKind.JS;
}

export function scanTypeScriptSource(source, reference) {
  const findings = [];
  const sourceFile = ts.createSourceFile(
    reference,
    source,
    ts.ScriptTarget.Latest,
    true,
    scriptKind(reference),
  );
  const frontend = reference.replaceAll("\\", "/").startsWith("apps/web/");

  function report(node, category) {
    const { line } = sourceFile.getLineAndCharacterOfPosition(
      node.getStart(sourceFile),
    );
    findings.push({ reference, line: line + 1, category });
  }

  function visit(node) {
    if (
      ts.isImportDeclaration(node) &&
      ts.isStringLiteral(node.moduleSpecifier)
    ) {
      const specifier = node.moduleSpecifier.text.replaceAll("\\", "/");
      if (specifier.endsWith("support.js") || specifier.includes("/_ds/")) {
        report(node, "prototype runtime dependency");
      }
      if (
        specifier.includes("apps/worker") ||
        specifier.includes("aurum_worker")
      ) {
        report(node, "Web imports Worker code");
      }
    }
    if (ts.isCallExpression(node)) {
      const expression = node.expression;
      const name = ts.isPropertyAccessExpression(expression)
        ? expression.name.text
        : ts.isIdentifier(expression)
          ? expression.text
          : undefined;
      if (name && FORBIDDEN_CALLS.has(name)) {
        report(node, `forbidden broker/runtime call: ${name}`);
      }
      if (name === "getattr" || name === "__getattribute__") {
        report(node, "forbidden dynamic MT5 dispatch");
      }
    }
    if (ts.isIdentifier(node)) {
      if (FORBIDDEN_RUNTIME_FLAGS.has(node.text)) {
        report(node, `forbidden Live Trading flag: ${node.text}`);
      }
      if (frontend && FRONTEND_PRIVILEGED_IDENTIFIERS.has(node.text)) {
        report(
          node,
          `privileged credential identifier in frontend: ${node.text}`,
        );
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return findings;
}

function pythonExecutable(root) {
  const candidate =
    process.platform === "win32"
      ? resolve(root, ".venv", "Scripts", "python.exe")
      : resolve(root, ".venv", "bin", "python");
  if (!existsSync(candidate)) {
    throw new Error(
      "Worker virtual environment is required for the Python AST scan.",
    );
  }
  return candidate;
}

export function scanRuntimeFiles(root, files = gitTrackedFiles(root)) {
  const findings = [];
  const pythonFiles = [];
  for (const path of files) {
    const extension = extname(path).toLowerCase();
    if (extension === ".py") {
      pythonFiles.push(resolve(root, path));
    } else if (TYPESCRIPT_EXTENSIONS.has(extension)) {
      findings.push(
        ...scanTypeScriptSource(
          readFileSync(resolve(root, path), "utf8"),
          path,
        ),
      );
    }
  }
  if (pythonFiles.length > 0) {
    const output = execFileSync(
      pythonExecutable(root),
      [resolve(root, "scripts", "runtime-boundary-ast.py"), ...pythonFiles],
      { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 },
    );
    findings.push(...JSON.parse(output));
  }
  return { findings, fileCount: files.length };
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === resolve(import.meta.filename)
) {
  const result = scanRuntimeFiles(process.cwd());
  if (result.findings.length > 0) {
    console.error(
      `Runtime safety-boundary scan failed:\n${result.findings
        .map(
          ({ reference, line, category }) =>
            `${reference}:${line}: ${category}`,
        )
        .join("\n")}`,
    );
    process.exit(1);
  }
  console.log(
    `Runtime boundary scan passed: ${result.fileCount} production files inspected with syntax-aware call checks.`,
  );
}
