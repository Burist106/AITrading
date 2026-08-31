# Milestone 2 Security Model

## Scope

Milestone 2 is **IMPLEMENTED — PATCH AND CI VERIFICATION PENDING**. It adds a Windows-only, read-only MT5 observation boundary to the local Supabase authorization and data-integrity foundation. It does not evaluate a strategy, create a proposal, execute or simulate an order, modify an MT5 Position, send a notification, or deploy a remote Supabase project. Milestone 3 is not started or authorized.

The invariant boundary is fixed:

- environment `DEMO_ONLY`;
- canonical asset `XAUUSD`;
- initial and only enabled runtime mode `SHADOW`;
- maximum permitted volume `0.01` and at most one open Position;
- mandatory Stop Loss for any represented proposal or open Position;
- no Live Trading setting or alternate path;
- no broker or MT5 write function.

## Principals and trust boundaries

| Principal               | Identity source                                                             | Direct table access                                                                                           | Function access                                                                               |
| ----------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `anon`                  | No authenticated subject                                                    | None                                                                                                          | None                                                                                          |
| `authenticated`         | Supabase Auth JWT; ownership is `auth.uid()`                                | Read owner-scoped rows; update only explicitly granted safe profile columns                                   | The nine owner intent functions only                                                          |
| `aurum_worker`          | Future dedicated Worker JWT with `role`, `owner_id`, and `worker_id` claims | No direct operational or MT5-observation DML                                                                  | Existing Worker lifecycle functions plus seven sanitized observation/reconciliation functions |
| `aurum_function_owner`  | Internal NOLOGIN database role                                              | Minimum privileges needed by secured functions, still constrained by explicit ownership checks and forced RLS | Owns secured functions; cannot authenticate as an application                                 |
| Migration administrator | Local CLI migration process                                                 | Schema administration                                                                                         | Not an application identity                                                                   |

The browser publishable key and authenticated user session are not Worker credentials. The dedicated Worker credential concept is independently rotatable and revocable and must remain outside frontend code, Git, snapshots, and logs. Milestone 1 tests fake claims only; it does not mint a production credential.

The native terminal is reached only through an explicit local executable path passed as the sole positional argument to `initialize()`. No password is accepted and `login()` is forbidden. Raw account and server identifiers exist transiently during verification; persistence, incidents, logs, tests, and browser contracts receive only masks or one-way SHA-256 fingerprints. Missing, invalid, or false terminal connection state fails closed before `account_info()`.

The configured or confirmed broker name is not sufficient proof of XAU/USD. The native and contract boundaries require canonical `XAUUSD`, base `XAU`, and profit `USD`. Discovery creates candidates only. An observation is append-only evidence and never updates confirmation. The confirmed fingerprint and its owner actor/version metadata live on a separate immutable binding record; absent or changed confirmation blocks health until an explicitly authorized future/manual operation creates a new confirmed version.

> Warning: the Supabase `service_role` must never be exposed to the browser and is not the Worker application design.

## RLS intent matrix

Every application table in `public` has RLS enabled and forced. No policy means deny. `anon` has no table privileges, and an unauthenticated `auth.uid()` is null.

| Resource                                                            | Authenticated owner read                                                                                              | Authenticated direct write                | Worker direct write                                   |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- | ----------------------------------------------------- |
| `profiles`                                                          | Own                                                                                                                   | Safe display/locale/time-zone fields only | None                                                  |
| `trading_accounts`, `broker_symbols`, `trading_modes`               | Own                                                                                                                   | None                                      | None                                                  |
| `risk_policies`, `risk_policy_versions`                             | Own                                                                                                                   | None; request function only               | None                                                  |
| `market_snapshots`, `feature_snapshots`                             | Own                                                                                                                   | None                                      | None                                                  |
| `trade_proposals`, `risk_checks`, `trade_decisions`                 | Own                                                                                                                   | None; approval/rejection functions only   | None                                                  |
| `system_commands`, `system_command_events`                          | Own safe command projection and own events; command payload, lease token, and raw last error are not browser-readable | None; intent functions only               | None; Worker functions only                           |
| `broker_orders`, `trade_executions`, `positions`, `position_events` | Own                                                                                                                   | None                                      | Read through reconciliation RPC only; no direct write |
| `system_components`, `system_heartbeats`, `system_incidents`        | Own                                                                                                                   | None                                      | None; narrowly scoped Worker functions only           |
| `audit_logs`                                                        | Own                                                                                                                   | None                                      | None; secured functions append records                |
| MT5 observation, reconciliation, and history-evidence tables        | Own sanitized rows only                                                                                               | None                                      | None; seven owner-derived Worker RPCs only            |

Owner policies compare `owner_id` with `(select auth.uid())`. Child rows use owner-aware composite foreign keys so RLS cannot hide a cross-owner referential-integrity defect. Cross-owner and anonymous cases are part of the database test suite even though the initial product is single-user.

## Secured functions

Authenticated user functions create durable intents for:

- proposal approval or rejection;
- pause, resume, or Emergency Stop;
- Position close, Stop Loss change, or Take Profit change;
- versioned risk-policy change.

They derive the owner from `auth.uid()`, validate exact payload shape, bind target identifiers and expected versions, apply idempotency, append an event and audit record, and return a bounded result code. They never accept an `owner_id` argument and never mutate broker orders, executions, or Positions.

Worker functions are limited to:

- claim the next eligible command atomically;
- renew its lease and advance legal pre-defined lifecycle states;
- complete, reject, or fail the command owned by the current unexpired lease;
- record a heartbeat or incident;
- append narrowly typed operational history.

There is no Worker function for broker submission, order creation, trade execution creation, or Position mutation.

The Milestone 2 persistence adapter exposes only the seven observation/reconciliation RPC capabilities; it exposes no command claim, transition, or completion method. Full reconciliation completion atomically records exactly one bounded Order-history evidence record and one Deal-history evidence record. Mismatch append and completion lock the same owner-scoped parent run; completion requires the exact normalized persisted-child and payload mismatch sets, and completed runs reject new mismatch evidence. A successful empty tuple is explicit valid-empty evidence; native `None`, an incomplete window, or unknown coverage blocks healthy state. Routine latest-tick upserts remain bounded current telemetry and deliberately append no security-audit row.

Claim and incident calls return exactly one typed, payload-free result envelope instead of overloading zero rows or `NULL` as an error signal. Claim codes distinguish `CLAIMED`, `NO_ELIGIBLE_COMMAND`, `INVALID_LEASE_DURATION`, and `WORKER_UNAUTHORIZED`; only the Worker-only successful envelope contains the opaque lease. Incident codes distinguish `CREATED`, `IDEMPOTENT_REPLAY`, `IDEMPOTENCY_CONFLICT`, field-specific invalid input, and unauthorized calls. An exact owner/request replay returns the existing incident identity, while changed canonical content on that key produces no mutation or audit row.

All exposed secured functions:

- are owned by a NOLOGIN role;
- use `SECURITY DEFINER` only where required;
- pin `search_path` to an empty value;
- fully qualify tables, types, and helper functions;
- avoid dynamic SQL;
- revoke default `PUBLIC` execution;
- grant execution only to the intended caller role.

## Durable command security

`system_commands` is durable PostgreSQL state. Realtime is disabled and is not required for correctness.

The database validates one of the nine canonical command payloads and derives its target binding. A non-empty owner-scoped idempotency key identifies one semantic intent. Reusing the key with the same command returns the original identifier; reusing it with different content returns a deterministic conflict.

Canonical payload validation precedes the idempotency lookup. Once a command exists, an exact replay is answered before current command-expiry or mutable target-state/version checks; this makes retries stable without allowing a changed request to bypass those gates. An unused key still has to pass all current creation checks.

Claiming uses a row lock with `FOR UPDATE SKIP LOCKED`. Eligibility includes status, expiry, retry time, maximum attempts, and lease state. Emergency Stop receives database-derived priority. An active lease cannot be stolen, and every renewal or transition checks the worker claim, opaque lease token, and server clock. Claims and renewals are capped at the command expiry. Expired or attempt-exhausted `pending`, `claimed`, and `validating` rows are deterministically terminalized with event and audit evidence; an `executing` command is never swept or automatically reclaimed because future broker outcome could be uncertain.

Command events and audit rows are appended in the same successful transaction as the state change. Terminal completion is idempotent only for the same result; a conflicting repeat fails closed.

Worker result codes must use a bounded uppercase machine-code format. Result messages, failure details, incident titles/descriptions, and component details are length-bounded and reject control characters, authorization/password/token labels, credential-bearing connection strings, private-key markers, and common high-confidence API-key/JWT shapes. The authenticated command read model omits the payload, opaque lease token, and raw last error, so browser progress polling does not become a sensitive-data channel.

## Optimistic concurrency

- Proposal actions include the proposal ID and positive proposal version. An expired, terminal, blocked, or stale proposal is rejected before command creation.
- Position requests include the Position ID and positive expected version. A missing, closed, or stale Position is rejected.
- A risk-policy change references the active policy version and creates a new immutable version; it never overwrites history.
- Worker transitions require the current lease owner and cannot overwrite another valid lease.

## Append-only records and safe metadata

Broker-symbol confirmation versions, MT5 history-query evidence, risk-policy versions, command events, Position events, and audit logs are immutable to application roles. Database triggers reject update and delete attempts in addition to withholding grants.

Audit metadata is bounded and rejects secret-shaped keys such as tokens, passwords, credentials, cookies, authorization headers, raw exception dumps, and stacks. Audit fixtures contain only fictional identifiers and safe result context. Transactional authorization errors that PostgreSQL rolls back cannot create a durable row in the same transaction; those attempts belong in external Auth/platform logs.

## Credential and network rules

- Local Supabase runs inside a disposable, pinned Docker-in-Docker boundary whose outer published ports are verified as IPv4 loopback-only. The inner Docker API remains on a private outer network and the host Docker socket is never mounted.
- CLI start/status output is suppressed because it can contain local keys.
- Exact image digests, privileged-container identity, labels, mounts, inner/outer network membership, and port mappings are checked before and after commands. A failed database command removes only the label-verified Aurum resources.
- No command in the repository logs in, links a project, pushes a database, or accepts a remote project identifier.
- No Supabase secret, Worker credential, MT5 credential, LINE secret, password, or production token belongs in source control.
- `.env.example` contains names only. Browser configuration, if added later, may contain only public local values.
- The Worker uses the already-open local Demo terminal session. It has no MT5 password setting or credential-reading path; no MT5 credential may be stored in Supabase.

## Defense responsibilities outside the database

Database constraints enforce identity, ownership, version, lifecycle, Demo/XAUUSD, volume, Stop Loss, and immutable-policy ceilings. The read-only Worker verifies account/symbol/tick state and reconciles current Position/Order identities, but it does not evaluate strategy eligibility, news windows, realized loss, drawdown, order margin, or broker execution response. Those checks belong to future explicitly authorized milestones. Every operational outcome remains fail-closed and no command has a broker side effect.
