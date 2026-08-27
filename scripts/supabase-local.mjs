import { readFileSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const docker = process.platform === "win32" ? "docker.exe" : "docker";
const localDockerHost =
  process.platform === "win32"
    ? "npipe:////./pipe/docker_engine"
    : "unix:///var/run/docker.sock";

const purposeLabel = "com.aurum.purpose=supabase-dind";
const purposeLabelKey = "com.aurum.purpose";
const purposeLabelValue = "supabase-dind";
const outerNetwork = "aurum-supabase-dind-outer";
const innerNetwork = "aurum-supabase-inner";
const dindContainer = "aurum-supabase-dind";
const runnerContainer = "aurum-supabase-runner";
const innerDatabaseContainer = "supabase_db_aurum-console";
const toolsInitContainer = "aurum-supabase-tools-init";
const dockerClientInitContainer = "aurum-supabase-docker-client-init";
const dataVolume = "aurum-supabase-dind-data";
const toolsVolume = "aurum-supabase-tools";
const supabaseVersion = "2.115.0";
const dindDigest =
  "sha256:ea9d20492ca1caaaba78e68453433895d256173c79281756e88b745647fcbcfd";
const runnerDigest =
  "sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43";
const dindImage = `docker:28.5.1-dind@${dindDigest}`;
const runnerImage = `node:24.19.0-alpine@${runnerDigest}`;
const supabaseCli = "/tools/node_modules/supabase/dist/supabase.js";
const runnerPath =
  "/tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";
const localPorts = Array.from({ length: 10 }, (_, index) => 54320 + index);
const command = process.argv[2];
const supportedCommands = new Set([
  "start",
  "stop",
  "reset",
  "test",
  "lint",
  "types",
]);
const pgTapTestPaths = [
  "supabase/tests/001_catalog_security.test.sql",
  "supabase/tests/002_constraints.test.sql",
  "supabase/tests/003_rls_isolation.test.sql",
  "supabase/tests/004_user_actions.test.sql",
  "supabase/tests/005_queue_lifecycle.test.sql",
  "supabase/tests/006_audit_immutability.test.sql",
];
const concurrentClaimTestDirectory = resolve(
  projectRoot,
  "supabase",
  "integration-tests",
  "007_concurrent_claim",
);
const concurrentClaimBarrierKey = 820260007;

if (!supportedCommands.has(command)) {
  console.error(
    "Usage: node scripts/supabase-local.mjs <start|stop|reset|test|lint|types>",
  );
  process.exit(2);
}

const dockerEnvironment = {
  ...process.env,
  DOCKER_HOST: localDockerHost,
};
let cleanupOnFailure = false;
let cleanupInProgress = false;

function run(executable, args, options = {}) {
  const hasInput = typeof options.input === "string";
  return spawnSync(executable, args, {
    cwd: projectRoot,
    encoding: "utf8",
    env: options.env ?? dockerEnvironment,
    maxBuffer: options.maxBuffer ?? 32 * 1024 * 1024,
    input: hasInput ? options.input : undefined,
    stdio: [hasInput ? "pipe" : "ignore", "pipe", "pipe"],
    windowsHide: true,
  });
}

function startDockerProcess(args, input) {
  const child = spawn(docker, ["--host", localDockerHost, ...args], {
    cwd: projectRoot,
    encoding: "utf8",
    env: dockerEnvironment,
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
  let stdout = "";
  let stderr = "";
  let outputExceededLimit = false;
  const maximumOutputLength = 1024 * 1024;

  const collect = (target, chunk) => {
    const next = `${target}${chunk}`;
    if (next.length > maximumOutputLength) {
      outputExceededLimit = true;
      child.kill();
      return next.slice(0, maximumOutputLength);
    }
    return next;
  };

  child.stdout.on("data", (chunk) => {
    stdout = collect(stdout, chunk);
  });
  child.stderr.on("data", (chunk) => {
    stderr = collect(stderr, chunk);
  });
  child.stdin.end(input);

  let settled = false;
  const completion = new Promise((resolveCompletion) => {
    child.once("error", (error) => {
      if (settled) return;
      settled = true;
      resolveCompletion({ status: null, stdout, stderr, error });
    });
    child.once("close", (status) => {
      if (settled) return;
      settled = true;
      resolveCompletion({
        status: outputExceededLimit ? 1 : status,
        stdout,
        stderr,
      });
    });
  });

  return { child, completion };
}

function runDocker(args, options) {
  return run(docker, ["--host", localDockerHost, ...args], options);
}

function resultDetail(result) {
  if (result?.error?.code) {
    return ` (${result.error.code})`;
  }

  return Number.isInteger(result?.status) ? ` (exit ${result.status})` : "";
}

function fail(message, result) {
  // Never echo raw Supabase CLI output here. In particular, `start` and
  // `status` can include local publishable and secret keys.
  if (cleanupOnFailure && !cleanupInProgress) {
    cleanupInProgress = true;
    cleanupOwnedResources();
  }

  console.error(`${message}${resultDetail(result)}`);
  process.exit(1);
}

function parseInspect(result, resourceDescription) {
  if (result.status !== 0) {
    fail(`Could not inspect ${resourceDescription}`, result);
  }

  try {
    const parsed = JSON.parse(result.stdout);
    return Array.isArray(parsed) ? parsed[0] : parsed;
  } catch {
    fail(`Docker returned invalid metadata for ${resourceDescription}`, result);
  }
}

function inspectOptional(kind, name) {
  const result = runDocker([kind, "inspect", name]);

  if (result.status !== 0) {
    return null;
  }

  return parseInspect(result, `${kind} ${name}`);
}

function isOwned(resource) {
  return resource?.Labels?.[purposeLabelKey] === purposeLabelValue;
}

function requireOwned(resource, description) {
  if (!isOwned(resource)) {
    fail(`Refusing to modify unowned Docker resource ${description}`);
  }
}

function requireDockerEngine() {
  const result = runDocker(["info", "--format", "{{.ServerVersion}}"]);

  if (result.status !== 0 || !result.stdout?.trim()) {
    fail("The local Docker engine is not running or is unavailable", result);
  }
}

function removeOwnedContainer(name, expectedDigest) {
  const resource = inspectOptional("container", name);

  if (!resource) {
    return;
  }

  requireOwned(resource.Config, `container ${name}`);

  if (!resource.Config.Image?.endsWith(`@${expectedDigest}`)) {
    fail(
      `Refusing to remove Docker container ${name} with an unexpected image`,
    );
  }

  const result = runDocker(["container", "rm", "--force", name]);

  if (result.status !== 0) {
    fail(`Could not remove Docker container ${name}`, result);
  }
}

function removeOwnedVolume(name) {
  const resource = inspectOptional("volume", name);

  if (!resource) {
    return;
  }

  requireOwned(resource, `volume ${name}`);
  const result = runDocker(["volume", "rm", name]);

  if (result.status !== 0) {
    fail(`Could not remove Docker volume ${name}`, result);
  }
}

function removeOwnedNetwork(name) {
  const resource = inspectOptional("network", name);

  if (!resource) {
    return;
  }

  requireOwned(resource, `network ${name}`);
  const result = runDocker(["network", "rm", name]);

  if (result.status !== 0) {
    fail(`Could not remove Docker network ${name}`, result);
  }
}

function cleanupOwnedResources() {
  removeOwnedContainer(runnerContainer, runnerDigest);
  removeOwnedContainer(toolsInitContainer, runnerDigest);
  removeOwnedContainer(dockerClientInitContainer, dindDigest);
  removeOwnedContainer(dindContainer, dindDigest);
  removeOwnedVolume(dataVolume);
  removeOwnedVolume(toolsVolume);
  removeOwnedNetwork(outerNetwork);
}

function ensureImage(image, description) {
  const inspect = runDocker(["image", "inspect", image]);

  if (inspect.status === 0) {
    return;
  }

  const pull = runDocker(["image", "pull", image]);

  if (pull.status !== 0) {
    fail(`Could not pull the pinned ${description} image`, pull);
  }
}

function createOwnedVolume(name) {
  const result = runDocker(["volume", "create", "--label", purposeLabel, name]);

  if (result.status !== 0) {
    fail(`Could not create Docker volume ${name}`, result);
  }
}

function createOuterNetwork() {
  const result = runDocker([
    "network",
    "create",
    "--driver",
    "bridge",
    "--label",
    purposeLabel,
    "--opt",
    "com.docker.network.enable_ipv6=false",
    outerNetwork,
  ]);

  if (result.status !== 0) {
    fail("Could not create the private Docker-in-Docker network", result);
  }
}

function initializeToolsVolume() {
  const copyDocker = runDocker([
    "run",
    "--rm",
    "--name",
    dockerClientInitContainer,
    "--network",
    "none",
    "--label",
    purposeLabel,
    "--mount",
    `type=volume,source=${toolsVolume},target=/tools`,
    dindImage,
    "sh",
    "-c",
    "mkdir -p /tools/bin && cp /usr/local/bin/docker /tools/bin/docker && chmod 0555 /tools/bin/docker",
  ]);

  if (copyDocker.status !== 0) {
    fail("Could not prepare the pinned Docker client", copyDocker);
  }

  const installCli = runDocker([
    "run",
    "--rm",
    "--name",
    toolsInitContainer,
    "--label",
    purposeLabel,
    "--network",
    "bridge",
    "--mount",
    `type=volume,source=${toolsVolume},target=/tools`,
    runnerImage,
    "npm",
    "install",
    "--prefix",
    "/tools",
    "--no-audit",
    "--no-fund",
    "--save-exact",
    `supabase@${supabaseVersion}`,
  ]);

  if (installCli.status !== 0) {
    fail(
      "Could not install the pinned Supabase CLI in the isolated runner",
      installCli,
    );
  }

  const verifyCli = runDocker([
    "run",
    "--rm",
    "--network",
    "none",
    "--mount",
    `type=volume,source=${toolsVolume},target=/tools`,
    runnerImage,
    "node",
    supabaseCli,
    "--version",
  ]);

  if (verifyCli.status !== 0 || verifyCli.stdout.trim() !== supabaseVersion) {
    fail("The isolated Supabase CLI version could not be verified", verifyCli);
  }
}

function startDindContainer() {
  const args = [
    "run",
    "--detach",
    "--name",
    dindContainer,
    "--hostname",
    "dind",
    "--label",
    purposeLabel,
    "--privileged",
    "--network",
    outerNetwork,
    "--network-alias",
    "dind",
    "--env",
    "DOCKER_TLS_CERTDIR=",
    "--mount",
    `type=bind,source=${projectRoot},target=/workspace`,
    "--mount",
    `type=volume,source=${dataVolume},target=/var/lib/docker`,
  ];

  for (const port of localPorts) {
    args.push("--publish", `127.0.0.1:${port}:${port}`);
  }

  args.push(dindImage);
  const result = runDocker(args);

  if (result.status !== 0) {
    fail("Could not start the isolated Docker-in-Docker runtime", result);
  }
}

function inspectDind() {
  const resource = inspectOptional("container", dindContainer);

  if (!resource) {
    fail("The isolated local database is not running. Run pnpm db:start first");
  }

  requireOwned(resource.Config, `container ${dindContainer}`);

  if (
    !resource.Config.Image?.endsWith(`@${dindDigest}`) ||
    resource.HostConfig?.Privileged !== true ||
    resource.State?.Running !== true
  ) {
    fail(
      "The isolated Docker-in-Docker runtime does not match its safety contract",
    );
  }

  const network = resource.NetworkSettings?.Networks?.[outerNetwork];

  if (
    !network?.IPAddress ||
    Object.keys(resource.NetworkSettings?.Networks ?? {}).length !== 1
  ) {
    fail("The isolated Docker-in-Docker runtime is not on its private network");
  }

  const mounts = resource.Mounts ?? [];
  const workspaceMount = mounts.find(
    (mount) => mount.Type === "bind" && mount.Destination === "/workspace",
  );
  const dataMount = mounts.find(
    (mount) =>
      mount.Type === "volume" &&
      mount.Name === dataVolume &&
      mount.Destination === "/var/lib/docker",
  );

  if (
    mounts.length !== 2 ||
    !workspaceMount?.RW ||
    !dataMount?.RW ||
    resource.HostConfig?.PublishAllPorts === true
  ) {
    fail(
      "The isolated Docker-in-Docker mounts do not match their safety contract",
    );
  }

  return resource;
}

function verifyOwnedSupportResources() {
  const network = inspectOptional("network", outerNetwork);
  const storedData = inspectOptional("volume", dataVolume);
  const storedTools = inspectOptional("volume", toolsVolume);

  if (!network || !storedData || !storedTools) {
    fail("The isolated local database resources are incomplete");
  }

  requireOwned(network, `network ${outerNetwork}`);
  requireOwned(storedData, `volume ${dataVolume}`);
  requireOwned(storedTools, `volume ${toolsVolume}`);

  const networkMembers = Object.values(network.Containers ?? {});

  if (
    network.Driver !== "bridge" ||
    networkMembers.length !== 1 ||
    networkMembers[0]?.Name !== dindContainer
  ) {
    fail("The private Docker-in-Docker network has unexpected membership");
  }
}

function verifyOuterBindings() {
  const resource = inspectDind();
  verifyOwnedSupportResources();
  const bindings = resource.NetworkSettings?.Ports ?? {};
  const expectedKeys = localPorts.map((port) => `${port}/tcp`).sort();
  const publishedKeys = Object.entries(bindings)
    .filter(([, entries]) => Array.isArray(entries) && entries.length > 0)
    .map(([key]) => key)
    .sort();

  if (
    publishedKeys.length !== expectedKeys.length ||
    publishedKeys.some((key, index) => key !== expectedKeys[index])
  ) {
    fail("The isolated runtime has an unexpected published-port set");
  }

  for (const port of localPorts) {
    const entries = bindings[`${port}/tcp`];

    if (
      !Array.isArray(entries) ||
      entries.length !== 1 ||
      entries[0]?.HostIp !== "127.0.0.1" ||
      entries[0]?.HostPort !== String(port)
    ) {
      fail(`Port ${port} is not bound exclusively to IPv4 loopback`);
    }
  }
}

function waitForInnerDocker() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const result = runDocker([
      "exec",
      dindContainer,
      "docker",
      "info",
      "--format",
      "{{.ServerVersion}}",
    ]);

    if (result.status === 0 && result.stdout.trim()) {
      return;
    }

    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
  }

  fail("The isolated inner Docker engine did not become ready");
}

function createInnerNetwork() {
  const result = runDocker([
    "exec",
    dindContainer,
    "docker",
    "network",
    "create",
    "--driver",
    "bridge",
    "--label",
    purposeLabel,
    innerNetwork,
  ]);

  if (result.status !== 0) {
    fail("Could not create the inner Supabase network", result);
  }
}

function verifyInnerNetwork() {
  const result = runDocker([
    "exec",
    dindContainer,
    "docker",
    "network",
    "inspect",
    innerNetwork,
  ]);
  const resource = parseInspect(result, `inner network ${innerNetwork}`);

  if (!isOwned(resource)) {
    fail("The inner Supabase network does not match its safety contract");
  }

  const attachedContainers = Object.values(resource.Containers ?? {});

  if (
    attachedContainers.length === 0 ||
    attachedContainers.some(
      (container) => !container?.Name?.startsWith("supabase_"),
    )
  ) {
    fail("The inner Supabase network has unexpected container membership");
  }

  if (
    attachedContainers.filter(
      (container) => container?.Name === innerDatabaseContainer,
    ).length !== 1
  ) {
    fail("The isolated Supabase database container could not be identified");
  }
}

function innerPsqlDockerArgs(databaseRole) {
  return [
    "exec",
    "--interactive",
    dindContainer,
    "docker",
    "exec",
    "--interactive",
    innerDatabaseContainer,
    "psql",
    "--no-psqlrc",
    "--no-password",
    "--set=ON_ERROR_STOP=1",
    "--quiet",
    "--tuples-only",
    "--no-align",
    `--username=${databaseRole}`,
    "--dbname=postgres",
  ];
}

function readConcurrentClaimSql(name) {
  const sql = readFileSync(resolve(concurrentClaimTestDirectory, name), "utf8");
  if (/^\s*\\/mu.test(sql)) {
    fail("Concurrent claim SQL must not contain psql meta-commands");
  }
  return sql;
}

function runInnerPsql(databaseRole, sql) {
  return runDocker(innerPsqlDockerArgs(databaseRole), {
    input: sql,
    maxBuffer: 1024 * 1024,
  });
}

function requirePsqlSuccess(result, description) {
  if (result.status !== 0) {
    fail(`The isolated ${description} failed`, result);
  }
}

function yieldFor(milliseconds) {
  return new Promise((resolveYield) => {
    setTimeout(resolveYield, milliseconds);
  });
}

async function runConcurrentClaimIntegrationTest() {
  verifyOuterBindings();
  verifyInnerNetwork();

  const setupResult = runInnerPsql(
    "supabase_admin",
    readConcurrentClaimSql("setup.sql"),
  );
  requirePsqlSuccess(setupResult, "concurrent claim setup");

  const sessionA = startDockerProcess(
    innerPsqlDockerArgs("postgres"),
    readConcurrentClaimSql("session-a.sql"),
  );
  let sessionAResult;
  const sessionACompletion = sessionA.completion.then((result) => {
    sessionAResult = result;
    return result;
  });

  let barrierHeld = false;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await yieldFor(50);
    if (sessionAResult) {
      requirePsqlSuccess(sessionAResult, "first concurrent Worker claim");
      break;
    }
    const probe = runInnerPsql(
      "postgres",
      `select case when pg_catalog.pg_try_advisory_lock(${concurrentClaimBarrierKey}) then 'free' else 'held' end;`,
    );
    requirePsqlSuccess(probe, "concurrent claim barrier probe");
    const state = probe.stdout.trim();
    if (state === "held") {
      barrierHeld = true;
      break;
    }
    if (state !== "free") {
      sessionA.child.kill();
      fail("The concurrent claim barrier returned an invalid state");
    }
  }

  if (!barrierHeld) {
    sessionA.child.kill();
    await sessionACompletion;
    fail("The first concurrent Worker session did not acquire its barrier");
  }

  const sessionBResult = runInnerPsql(
    "postgres",
    readConcurrentClaimSql("session-b.sql"),
  );
  requirePsqlSuccess(sessionBResult, "second concurrent Worker claim");

  const completedSessionA = await sessionACompletion;
  requirePsqlSuccess(completedSessionA, "first concurrent Worker claim");

  const verifyResult = runInnerPsql(
    "supabase_admin",
    readConcurrentClaimSql("verify.sql"),
  );
  requirePsqlSuccess(verifyResult, "concurrent claim rollback verification");

  const cleanupResult = runInnerPsql(
    "supabase_admin",
    readConcurrentClaimSql("cleanup.sql"),
  );
  requirePsqlSuccess(cleanupResult, "concurrent claim cleanup");

  verifyOuterBindings();
  verifyInnerNetwork();
  console.log(
    "The isolated concurrent claim integration passed 4 assertions across two overlapping Worker sessions.",
  );
}

function prepareRunner() {
  const staleRunner = inspectOptional("container", runnerContainer);

  if (staleRunner) {
    requireOwned(staleRunner.Config, `container ${runnerContainer}`);

    if (staleRunner.State?.Running) {
      fail("Another isolated Supabase command is already running");
    }

    removeOwnedContainer(runnerContainer, runnerDigest);
  }
}

function runSupabase(args) {
  prepareRunner();
  const result = runDocker([
    "run",
    "--rm",
    "--name",
    runnerContainer,
    "--label",
    purposeLabel,
    "--network",
    outerNetwork,
    "--env",
    "CI=1",
    "--env",
    "DOCKER_HOST=tcp://dind:2375",
    "--env",
    "DOCKER_TLS_CERTDIR=",
    "--env",
    "NO_COLOR=1",
    "--env",
    `PATH=${runnerPath}`,
    "--env",
    "SUPABASE_NO_UPDATE_NOTIFIER=1",
    "--env",
    "SUPABASE_SERVICES_HOSTNAME=dind",
    "--mount",
    `type=bind,source=${projectRoot},target=/workspace`,
    "--mount",
    `type=volume,source=${toolsVolume},target=/tools`,
    "--workdir",
    "/workspace",
    runnerImage,
    "node",
    supabaseCli,
    ...args,
    "--workdir",
    "/workspace",
    "--network-id",
    innerNetwork,
  ]);

  const leftoverRunner = inspectOptional("container", runnerContainer);

  if (leftoverRunner) {
    removeOwnedContainer(runnerContainer, runnerDigest);
  }

  return result;
}

function sanitizeCliOutput(value) {
  return value
    .replace(new RegExp("\\u001B\\[[0-?]*[ -/]*[@-~]", "gu"), "")
    .replace(/(postgres(?:ql)?:\/\/)[^@\s]+@/giu, "$1[REDACTED]@")
    .replace(
      /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/gu,
      "[REDACTED_JWT]",
    )
    .replace(
      /((?:service[ _-]?role|publishable|secret|anon|jwt)[ _-]?(?:key|token|secret)?\s*[:=]\s*)\S+/giu,
      "$1[REDACTED]",
    );
}

function printSafeCliOutput(result) {
  const output = sanitizeCliOutput(
    `${result.stdout ?? ""}\n${result.stderr ?? ""}`,
  ).trim();

  if (output) {
    console.log(output);
  }
}

function requireRunningStack() {
  verifyOuterBindings();
  waitForInnerDocker();
  verifyInnerNetwork();
}

async function runCheckedLocalCommand(args, successMessage, afterSuccess) {
  requireRunningStack();
  prepareRunner();
  cleanupOnFailure = true;
  const result = runSupabase(args);
  printSafeCliOutput(result);

  if (result.status !== 0) {
    fail("The isolated local Supabase command failed", result);
  }

  if (afterSuccess) {
    try {
      await afterSuccess();
    } catch (error) {
      fail("The isolated post-command verification failed", { error });
    }
  }

  verifyOuterBindings();
  verifyInnerNetwork();
  cleanupOnFailure = false;
  console.log(successMessage);
}

requireDockerEngine();

if (command === "stop") {
  cleanupOwnedResources();
  console.log("The isolated local Supabase runtime was removed.");
  process.exit(0);
}

if (command === "start") {
  console.log("Preparing the isolated local Supabase runtime...");
  cleanupOwnedResources();
  ensureImage(dindImage, "Docker-in-Docker");
  ensureImage(runnerImage, "Node runner");
  cleanupOnFailure = true;
  createOuterNetwork();
  createOwnedVolume(dataVolume);
  createOwnedVolume(toolsVolume);
  initializeToolsVolume();
  startDindContainer();
  waitForInnerDocker();
  verifyOuterBindings();
  createInnerNetwork();
  const result = runSupabase(["start"]);

  if (result.status !== 0) {
    printSafeCliOutput(result);
    fail("Local Supabase failed to start inside the isolated runtime", result);
  }

  verifyOuterBindings();
  verifyInnerNetwork();
  cleanupOnFailure = false;
  console.log(
    "Local Supabase started in Docker-in-Docker with verified localhost-only bindings.",
  );
  process.exit(0);
}

if (command === "reset") {
  await runCheckedLocalCommand(
    ["db", "reset", "--local"],
    "The isolated local database reset completed.",
  );
  process.exit(0);
}

if (command === "test") {
  await runCheckedLocalCommand(
    ["test", "db", ...pgTapTestPaths, "--local"],
    "The isolated pgTAP and concurrent claim database tests completed.",
    runConcurrentClaimIntegrationTest,
  );
  process.exit(0);
}

if (command === "lint") {
  await runCheckedLocalCommand(
    ["db", "lint", "--local", "--level", "error", "--fail-on", "error"],
    "The isolated database lint completed.",
  );
  process.exit(0);
}

requireRunningStack();
prepareRunner();
cleanupOnFailure = true;
const typeResult = runSupabase([
  "gen",
  "types",
  "--lang",
  "typescript",
  "--schema",
  "public",
  "--local",
]);

if (typeResult.status !== 0) {
  fail("Local database type generation failed", typeResult);
}

verifyOuterBindings();
verifyInnerNetwork();
cleanupOnFailure = false;
process.stdout.write(typeResult.stdout);
