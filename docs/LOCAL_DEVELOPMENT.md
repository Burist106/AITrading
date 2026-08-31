# Local Development

## Prerequisites

- Node.js 24.19.0
- pnpm 11.24.0
- Python 3.13.7 on `PATH`
- Git for normal source control workflows
- Docker Desktop with a running Linux-container engine for Milestone 1 database checks

The exact Supabase CLI is installed as the workspace dependency `supabase@2.115.0`; do not install or silently substitute a global CLI. MetaTrader, an MT5 account, Supabase credentials, LINE credentials, and OpenAI credentials are **not** required and must not be added.

Verify the required runtimes from PowerShell:

```powershell
node --version
pnpm --version
python --version
```

## Install

From the extracted project root:

```powershell
pnpm install --frozen-lockfile
pnpm worker:install
```

`worker:install` creates a root `.venv` when needed and installs the Worker package with its pinned development dependencies. On Windows, ensure `python` resolves to Python 3.13.7 before running it.

Do not populate `.env.example`. If a later UI task needs local public configuration, copy it to an ignored `.env` and use non-secret local values only. Database migrations, pgTAP tests, and contract generation require no environment values or remote project.

## Run the web shell

```powershell
pnpm dev
```

Open `http://localhost:3000`. The initial view is the `no_signal` scenario in immutable `SHADOW` mode. The Development State Simulator is available only in development and test; it changes presentation fixtures only.

## Quality commands

Run individual checks while developing:

```powershell
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm security
```

`pnpm build` compiles the TypeScript packages, creates the optimized Next.js production output, builds the Worker sdist/wheel, and verifies that the development simulator marker is absent from production artifacts.

Run the full clean-checkout gate:

```powershell
pnpm check
```

The build command also verifies that the Development State Simulator marker is absent from the production output. Tests and type checking do not require MetaTrader.

Worker checks can also be run directly after `pnpm worker:install`:

```powershell
.venv\Scripts\python.exe -m ruff format --check apps/worker
.venv\Scripts\python.exe -m ruff check apps/worker
.venv\Scripts\python.exe -m mypy apps/worker/src apps/worker/tests
.venv\Scripts\python.exe -m pytest apps/worker/tests
```

The root scripts are preferred because they select the platform-appropriate interpreter.

## Local Supabase foundation

Start Docker Desktop first. Then run the pinned, guarded local wrapper:

```powershell
pnpm db:start
```

The wrapper starts a disposable, pinned Docker-in-Docker runtime plus a pinned Node runner. The runner is the only place the exact `supabase@2.115.0` CLI executes. The inner Docker API is reachable only on the dedicated outer container network and is never published to the host. Supabase may bind to wildcard addresses **inside** that isolated runtime, while the outer runtime publishes ports `54320` through `54329` exclusively on Windows/Linux IPv4 loopback. The wrapper verifies the exact image digests, privileged mode, private network membership, inner network membership, and every outer port binding before and after each command; any mismatch fails closed.

This workaround is intentionally local and disposable. Docker-in-Docker requires a privileged container, which gives that container broad kernel capabilities, and the repository is mounted read/write at `/workspace` so its nested daemon can use migration and test files at the same path as the runner. The host Docker socket is never mounted. Run these commands only from this reviewed repository, and use `pnpm db:stop` when finished; it removes only the exact label-verified Aurum containers, volumes, and network. A failed start, reset, lint, test, or type-generation command also removes the isolated runtime rather than leaving a partially verified stack running. A fresh start must download the pinned tools and Supabase images again, so it can take several minutes and use substantial temporary disk space.

Apply the complete schema and deterministic fictional seed from zero, run it a second time to prove reset repeatability, execute pgTAP/RLS/queue tests plus the overlapping-session claim integration, and check generated types:

```powershell
pnpm db:check
```

The individual commands are:

```powershell
pnpm db:reset
pnpm db:lint
pnpm db:test
pnpm db:types:generate
pnpm db:types:check
```

Stop the stack when finished:

```powershell
pnpm db:stop
```

`db:lint` runs schema linting locally at error severity. `db:test` runs eight pgTAP suites and then a credential-free integration with two overlapping local `psql` sessions inside the inner database container. The integration verifies and uses the pinned local role graph's existing SET access to the exact Worker role without changing membership: the first session must receive a typed `CLAIMED` result and hold its lock, while the second receives one payload-free `NO_ELIGIBLE_COMMAND` result. It rolls both transactions back and verifies that no command/event/audit mutation survived. If any phase fails, the guarded wrapper removes the isolated volume instead of leaving a partial database behind. `db:types:generate` formats with the pinned workspace Prettier configuration and writes `packages/contracts/src/database.generated.ts` atomically from the local `public` schema. `db:types:check` performs the same isolated generation and formatting in memory, then fails on any missing or stale output. Never redirect generation directly over the committed file because a failed CLI command could truncate it.

This milestone is local only. Do not log in to Supabase, link the workspace, select a remote project, use a remote-project flag, or push the database. The local Auth seed has a fictional `.invalid` owner address and no password.

## Expected safety behavior

- The UI always shows Demo identity and starts in Shadow.
- Scenario states such as Live account detected, AUTO eligible, order pending, or position open are fictional presentation fixtures.
- Production output contains no Development State Simulator.
- Browser direct DML to protected operational tables is denied; user actions create durable intents through narrow functions.
- No MetaTrader import, Worker command consumer, broker write, simulated execution, or Position modification exists.
- Realtime is disabled and is never durable command truth.
- The security check must report any high-confidence forbidden runtime pattern instead of silently ignoring it.

## Troubleshooting

### Wrong Python version

If `python --version` is not 3.13.7, correct the Windows `PATH` or Python launcher configuration before running `pnpm worker:install`. Delete and recreate only the repository-local `.venv` after confirming the target path; do not reuse an environment made with another Python minor version.

### A check cannot run

Report the exact command, output, and missing prerequisite. Do not mark a gate as passed when it did not execute.

### Local Supabase refuses a wildcard binding

Do not bypass the check. The inner Supabase containers can use wildcard bindings only inside the disposable Docker-in-Docker runtime; every host-visible outer binding must remain exactly `127.0.0.1`. Docker Desktop may ignore a bridge network's default host-binding option, which is why the wrapper does not run Supabase directly against the host daemon. Stop and remove the isolated resources with `pnpm db:stop` before troubleshooting. Never change the wrapper to accept `0.0.0.0` or `[::]`.

### A migration, pgTAP, or concurrent-claim test fails

Fix the migration or test and rerun `pnpm db:reset` from zero. Do not edit the live local database through Studio to make the test pass; migrations and `seed.sql` are the reproducible source of truth.

### Production simulator check fails

Do not weaken the check. Remove the production import/path that includes the development simulator and rebuild.

### Security check reports a possible secret

Do not paste the matched value into chat or logs. Remove it and rotate it outside this repository if it was real.
