# Milestone 3 implementation

Status (2026-09-22): **IN PROGRESS — INTEGRATED DEMO/SHADOW CODE; REAL-SOURCE ACCEPTANCE BLOCKED**.

The user authorized real system development and then an end-to-end continuation. The production code now connects the Worker, strategy/risk/eligibility, immutable Shadow journal and authenticated dashboard. This is not an operational milestone-completion claim: genuine external evidence, hosted provisioning and the native transaction-time contract remain unresolved.

## Integrated path

### Current continuation plan — deterministic local replay

The user explicitly authorized both continued development and commit/push on 2026-09-22. Implement a bounded local replay archive before publication: retain the validated risk input and exact cycle together in one SQLite transaction, verify the historical risk/eligibility calculation without MT5 or network access, and connect archive-before-remote-write behavior to the Worker. An archive failure must not publish the calculated cycle. Local archiving and the remote RPC are not a distributed transaction; a locally archived decision may remain unpublished. The verifier must distinguish reproducibility from remote confirmation and independent source truth. Then rerun the full local quality/database/security gates and publish on the existing work branch, without merging or declaring M3 complete.

Assumptions: the archive contains sanitized fingerprints and financial research inputs, never credentials or raw account login/server values; it stays outside the checkout and is not uploaded. This closes part of deterministic decision replay, not the missing genuine provider integrations or native transaction-time gate. Earlier records with only an input digest remain unreplayable.

```text
Existing serialized MT5 read-only poller
  → current confirmed market + six completed M1 bars
  → SMA3 / SMA5 / ATR5 → versioned research candidate
  → explicit source contexts → deterministic risk + eligibility
  → immutable Shadow cycle / quote-observed outcome RPCs
  → owner-scoped Supabase reads → dashboard / details / journal
```

The runtime uses synchronous full-cycle/tick/failure hooks on the poller's single native-owner thread. Full reconciliation is handed to the market stage, not repeated for every tick. The operator CLI selects one-second tick observations and one-minute full cycles; Position/active-Order observations retain their independent cadence. Existing failure/reconnect/heartbeat logic remains authoritative. No approval or command is consumed.

### Market, baseline and risk

The existing market stage rechecks confirmed Demo/account/server/specification bindings, complete reconciliation, source versions, current tick age and six completed consecutive UTC M1 bars. It rejects fixture source and preserves the exact normalized price inputs behind its market/feature digest. A frozen capture bundle retains the observations required by risk instead of reconstructing them from unrelated reads.

The explicit `sma-atr-shadow-v1` research rule returns WAIT for equal averages or zero ATR. Otherwise it chooses BUY when SMA3 exceeds SMA5, SELL below, an outward tick-rounded two-ATR stop and a target three times the stop distance. It uses the actual quote side, never a quietly rounded entry or assumed price-dollar point. This baseline has no validated regime/performance sample and is not calibrated. Eligibility records those failed gates and cannot promote itself by counting incomplete quote outcomes.

The existing Decimal risk evaluator checks current source-bound Demo state, policy, account equity/baselines/losses/exposure, news, safety, specification, costs and conservative sizing. The maximum volume remains 0.01, mandatory SL and all hard ceilings remain enforced. Missing or invalid independent context blocks without a fabricated volume or zero-cost assumption.

Every reached risk stage retains its canonical input digest, source receipt identities/versions/digests/coverage, all hard check results and calculated amounts only on PASS. A required local replay archive now retains the full validated calculation input with the exact cycle before remote publication; the read-only verifier recalculates at the original time. This is deterministic decision replay, not full historical-ledger replay: a real provider must retain the independently referenced source evidence. Local MATCH does not confirm a remote write or source authenticity. Financial values cross the wire as decimal strings. See [the replay runbook](SHADOW_REPLAY.md).

### Durable records and restart

`shadow_cycles` and `shadow_outcome_events` are dedicated append-only tables, separate from legacy approval proposals, commands, broker orders, executions and Positions. New tables use FORCE RLS, composite ownership links, browser SELECT only and four narrow Worker RPCs. Account/Worker authority comes from verified database claims, never the payload alone.

One immutable cycle is keyed by account, UTC minute and pipeline/strategy versions. Same-key identical content replays; changed content conflicts. An uncertain write retains the exact envelope for retry. Database failure is reported as persistence unavailable, not a pretend durable BLOCK. The failure hook attempts a source BLOCK when persistence is available; an already-recorded minute remains immutable and Worker failure telemetry remains distinct from that historical record.

A PROPOSAL is non-executable research even when risk passes. The RPC checks current account/binding/policy/mode/reconciliation and pending safety intents before recording it. These are evidence-at-check validations, not execution authority or locks against unrelated operational writers.

Quote outcomes use BUY bid / SELL ask. They describe observed thresholds, not fills or a continuously observed market path. Expiry takes precedence at the exact boundary; gaps beyond five seconds, missing source or restart uncertainty become UNKNOWN. Events are ordered, limited to 32, idempotent and terminal states cannot reverse. `net_pnl_usd` is always null: this version cannot prove realized costs or broker fills.

Restart reads at most 100 recent cycles and their bounded events. Unresolved research within that window is closed UNKNOWN after downtime. Older unresolved records outside that bounded read are historical/incomplete, never implicitly profitable or complete.

### Real read-only pages and authentication

Production dashboard, proposal list/UUID detail, journal, health and Position routes no longer load design scenarios. Legacy visual fixtures remain test/development artifacts and are excluded from the production bundle.

The server verifies the current Supabase Auth user before deriving an owner-scoped SELECT gateway. Reads validate both SQL identity columns and strict payloads, complete bounded outcome chains, microsecond ordering and exact response counts. Unconfigured, signed-out, unavailable, invalid, empty, stale and blocked states are explicit; none uses fixture fallback. Health pages describe persisted pipeline evidence rather than asserting current native health. Missing Position evidence is not displayed as zero exposure.

Sign-in is for an already provisioned Supabase user, not MT5. Access-only cookies are HttpOnly, SameSite Strict and Secure with a host-only prefix in production; no refresh token/localStorage/privileged-key fallback is retained. Exact Origin and CSRF checks precede processing, bodies and requests are bounded/cancellable, and raw authentication errors are not displayed. Hosted Auth provisioning was not performed.

## Operator runbook and unresolved inputs

Do not paste credentials into chat or put real values in Git. `.env.example` contains empty names only.

Web configuration requires the existing public Supabase URL/publishable key and explicit `AURUM_WEB_ORIGIN`. Production URLs must be HTTPS. With no configuration, `pnpm dev` renders an honest disconnected screen. A provisioned Auth user and matching owner/account records are external setup, not fictional seed credentials.

The Worker composition accepts an already-issued least-privilege Worker token, public key, service URL, explicit owner/account UUIDs and outside-checkout `AURUM_SHADOW_REPLAY_PATH` from the operator's process environment. It neither issues credentials nor discovers secret files. The usual independently confirmed local terminal/account/specification configuration is required. The CLI uses the existing default time policy and cannot clear the unresolved alternate-policy transaction gate.

An operator may explicitly invoke a bounded read-only run:

```text
pnpm worker:shadow --confirm-demo-read-only --duration-seconds 300
```

This command was not run against the user's terminal or real credentials during implementation. Its fixed Demo/Shadow boundary has no broker-write capability. The supplied CLI uses `MissingEvidenceProvider`: until genuine sources are integrated, risk remains BLOCK. A hosted service/embedding application can inject `ValidatedEvidenceProvider` with independently sourced ledger, safety/news and cost contexts; merely implementing that interface does not prove those sources valid.

Remaining prerequisites:

- Authoritative native transaction event/query semantics and a complete opted-in read-only smoke pass.
- Complete account-wide equity/ledger coverage, valid UTC day/week and drawdown baselines, and retained source evidence for replay.
- Genuine calendar coverage, account-specific commission/swap terms, conservative slippage assumptions and independently verified clock/safety evidence.
- Provisioned authenticated persistence/Auth environment and confirmed bindings; no remote credentials or deployment were created.
- Real-source end-to-end validation, clean-checkout CI and separately authorized publication/review.

Milestone 2 remains **COMPLETE WITH DOCUMENTED LIMITATIONS**. Its original release smoke is **NOT RUN**; the later native attempt is **BLOCKED**, not passed. Milestone 4/5, approval consumption, broker writes, Position mutation and Live Trading remain unauthorized. No commit, push, merge or deployment is automatic.

## Verification record

Previous local integration verification, before the local replay continuation:

- `pnpm check` passed: Prettier, Ruff format/lint, ESLint, TypeScript, mypy (82 files), all tests, web/Worker builds and production fixture/simulator exclusion.
- Complete Worker suite: 1,252 passed. TypeScript: 393 passed (262 contracts, nine fixtures, 122 web).
- `pnpm db:check` passed: two isolated fixture resets, schema lint, 801 pgTAP assertions in ten suites, four existing overlapping Worker-claim assertions, 39 shared Shadow wire assertions and generated-type comparison.
- Tests use constructed native-shaped observations, mocked HTTP/loopback servers and fictional local database claims. They are not real Auth, MT5 or hosted end-to-end evidence.
- Security checks passed, including 11 scanner regressions. The expanded inventory inspected 262 tracked/untracked repository text files, 348 bounded history blobs and 118 production files. Tracked environment examples and extensionless source files remain covered; ignored local environment/profile files remain unread. These are bounded scanner results, not a guarantee against every possible secret pattern.
- `pnpm audit --audit-level high`, Python `pip check` and `git diff --check` passed. No dependency versions were changed.
- A browser preview launch was denied by the local tool policy; no interactive browser screenshot/visual inspection was completed. Rendering/accessibility tests and production build are separate evidence.

Earlier component results (178 TypeScript / 1,052 Worker / 582 pgTAP) are historical and are not reused as current integration checks. Remote CI, real-source smoke, commit, push, merge and deployment were not performed at that integration checkpoint.

Replay continuation verification (2026-09-22):

- Full `pnpm check` passed: formatting, lint, TypeScript, mypy (88 files), 1,371 Worker tests, 393 TypeScript tests, web/Worker builds and production fixture exclusion.
- Security checks passed: 269 repository text files, 348 bounded pre-publication history blobs, 121 production files and 11 scanner regressions. `pnpm audit --audit-level high` and Python `pip check` also passed.
- The local database rerun is **NOT RUN**: Docker Desktop was started hidden, but its engine did not respond within the bounded startup attempt or a later bounded probe, so fixture ownership/data preconditions could not be reverified. No database reset or repair was attempted. Do not reuse the previous 801 assertions as a fresh local run; the newly published commit requires its own CI results.
- Tests used constructed inputs and temporary local archives only. No actual account archive, credentials/profile, native MT5 smoke, hosted setup or interactive browser QA was accessed/performed.
- Commit/push is explicitly authorized for this delivery; PR #2 remains draft on the existing work branch. Merge, tag, deployment and milestone completion are not part of publication. Remote CI is a post-push gate, not claimed by the pre-publication local results above.

Only the independently verified disposable fixture database was reset. Failed intermediate migration/test attempts triggered its wrapper cleanup; corrected migrations recreated it from repository seed. No pre-existing user database or unrelated Docker stack was removed. The previous reversible Docker runtime-directory backups remain retained; no new Docker repair, credential inspection or native smoke was performed in this continuation.
