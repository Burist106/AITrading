# Security Boundaries

## Security posture

Aurum Console is fail-closed and `DEMO ONLY`. Milestone 2 adds a Windows-only read boundary for an already-open MT5 Demo terminal plus sanitized reconciliation evidence. It remains intentionally incapable of writing to a broker, consuming a command, or modifying an Order or Position. Static fixtures and database schema foundations may illustrate future states, but they do not grant capability.

## Credential boundary

No real credential is needed for Milestone 2. Do not read, request, print, log, commit, upload, or place into a prompt:

- MT5 login, password, server credential, terminal secret, or terminal path tied to a real account;
- Supabase secret/service-role key or future Worker credential;
- LINE channel secret or access token;
- OpenAI API key;
- browser cookie or personal access token.

`.env.example` contains names and empty values only. A local `.env` is ignored and must never be shared. The Worker uses an already-open local Demo terminal and must never accept or read an MT5 password; the explicit executable path and local binding values remain outside Git and browser-visible state.

## Trust zones

| Zone                  | Authority through Milestone 2                                                                                            | Explicitly prohibited                                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Browser / web app     | Render validated fixtures and read owner-authorized control-plane and sanitized MT5 observations                         | Broker access; direct operational DML; risk-result mutation; secrets; order/Position mutation                |
| Authenticated actions | Call the nine narrow functions that create durable intents                                                               | Claiming/completing Worker commands; creating broker orders/executions; mutating Positions                   |
| Shared contracts      | Validate typed data and deliberate persistence DTOs at runtime                                                           | Executing commands; inferring authorization from a valid payload                                             |
| Python read Worker    | Poll allowed MT5 reads, normalize/mask observations, and reconcile through fake or Windows adapters                      | Command consumption; broker writes; real credentials; strategy, proposal, risk, approval, or execution logic |
| Dedicated Worker role | Fake local claims may execute observation, reconciliation, heartbeat, incident, and M1 lifecycle functions for one owner | Browser use; unrelated-owner access; direct table DML; broker/order/execution/Position writes                |
| Local Supabase        | Enforce schema, forced RLS, secured functions, queue, sanitized MT5 evidence, audit, and deterministic seed              | Remote linking/push; production credentials; external calls; broad browser grants                            |
| Design references     | Supply visual and behavioral requirements                                                                                | Production runtime import, direct conversion to a monolith, or dependency on `support.js` / `_ds`            |

## Fixed fail-closed rules

- Runtime configuration accepts only Demo, Shadow, and XAUUSD.
- A visual `live_account_detected` fixture represents a blocking failure; it is not a supported account type.
- Missing, stale, inconsistent, or uncertain account, market, database, time, Worker, or MT5 state must not be presented as executable.
- The `0.01` volume is a maximum. If the broker minimum would exceed the risk budget, the proposal is `BLOCK` with no requested volume.
- Every proposal includes a Stop Loss. No UI control can bypass a hard failure.
- Quality score is supporting evidence only and cannot determine `AUTO`, `ASK`, or `BLOCK`.
- Emergency Stop requested, recorded, Worker-acknowledged, locally disabled, confirmed, and unconfirmed are distinct states.
- Resume is not available from an unconfirmed emergency state.

## Current browser behavior

The browser has no direct mutation repository. In development/test, the scenario selector changes local presentation state only. Production forces `no_signal` and ignores manual scenario query values. The State Simulator never changes runtime mode, creates a command, or implies broker acknowledgement. The database action foundation provides secured intent functions with idempotency, expiry, current-version validation, durable events, and audit logging; the static P0 UI is not wired to active actions in this milestone.

## Implemented Supabase/RLS model

1. Every application table in `public` has enabled and forced RLS.
2. `anon` has no table or action-function access. The authenticated owner reads only matching `owner_id` rows and may update only safe profile columns.
3. Protected proposal, risk-check, broker-order, execution, Position, incident, heartbeat, command, event, and audit records are not directly browser-writable.
4. Nine user functions validate typed inputs, derive `auth.uid()`, enforce target versions and idempotency, and create durable commands.
5. The Worker role is NOLOGIN, separately claim-based, owner-scoped, and granted only read access needed for validation plus narrow Worker functions. Claim and incident actions return one typed safe-code envelope; the browser cannot execute them or read their lease data.
6. Security-definer functions have an empty `search_path`, qualified references, a NOLOGIN owner, and explicit execution revocations/grants.
7. Durable commands include typed JSON, expiry, attempts, retry scheduling, atomic claim, opaque lease, result, and event history.
8. Six forced-RLS MT5 tables and seven Worker-only RPCs store sanitized observations, full-reconciliation results, and per-run history-query evidence without direct Worker or browser DML.
9. Realtime is disabled. If introduced later as a wake-up mechanism, the committed database row remains command truth.

The detailed principal, table, function, and credential matrices are in [SECURITY.md](./SECURITY.md). The schema and queue lifecycle are in [DATABASE_FOUNDATION.md](./DATABASE_FOUNDATION.md).

## Security checks

The deterministic repository security check scans runtime, configuration, shared contract fixtures, local Supabase files, root manifests, and CI for high-confidence secret patterns, privileged frontend credential identifiers, forbidden remote Supabase operations, broker-write call patterns, MetaTrader imports outside the one native adapter, non-allowlisted or dynamically dispatched MT5 calls, Position-mutation patterns, and Live Trading runtime labels. pgTAP separately inspects function grants, RLS, append-only protections, and pinned function search paths. These checks supplement review; they do not make committing secrets safe.

Run from the repository root:

```powershell
pnpm security
```

If a check reports a possible secret, do not print the value. Remove it from the workspace and rotate it outside this project if it was real.

## Future authorization gates

- Milestones 3–4: reproducible Shadow proposals and simulated secured approval/command processing.
- Milestone 5: Demo execution only after explicit user authorization and all earlier gates pass.

No milestone in the current repository authorizes Live Trading.
