import process from "node:process";

import { formatFinding, scanRepositorySecrets } from "./lib/secret-scanner.mjs";

const result = scanRepositorySecrets(process.cwd());

if (result.findings.length > 0) {
  console.error(
    `Repository-file and Git-history secret scan failed:\n${result.findings
      .map(formatFinding)
      .join("\n")}`,
  );
  process.exit(1);
}

console.log(
  `Secret scan passed: ${result.repositoryFileCount} tracked/untracked repository text files and ${result.historyBlobCount} bounded Git-history blobs inspected; no high-confidence secrets found.`,
);
