import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join } from "node:path";
import process from "node:process";

const buildRoot = "apps/web/.next";
const developmentOutput = join(buildRoot, "dev");
const markers = [
  "AURUM_DEVELOPMENT_STATE_SIMULATOR",
  "demo-proposal",
  "Fixture market snapshot",
  "Central prototype/demo fixtures",
];
const searchable = new Set([".html", ".js", ".json", ".map", ".txt"]);

function walk(path) {
  if (path === developmentOutput) return [];
  return statSync(path).isDirectory()
    ? readdirSync(path).flatMap((entry) => walk(join(path, entry)))
    : [path];
}

try {
  const leaked = walk(buildRoot)
    .filter((file) => searchable.has(extname(file)))
    .filter((file) =>
      markers.some((marker) => readFileSync(file, "utf8").includes(marker)),
    );

  if (leaked.length > 0) {
    console.error(
      `Production bundle contains a development fixture/simulator marker:\n${leaked.join("\n")}`,
    );
    process.exit(1);
  }

  console.log(
    "Production bundle check passed: development fixture and simulator markers are absent.",
  );
} catch (error) {
  console.error(`Production bundle check failed: ${error.message}`);
  process.exit(1);
}
