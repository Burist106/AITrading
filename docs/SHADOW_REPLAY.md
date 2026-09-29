# Local Shadow decision replay

Status: local implementation in Milestone 3, not real-source acceptance. Replay never enables execution or changes `DEMO ONLY / SHADOW`.

## What it retains

Each cycle that reaches risk evaluation retains its exact immutable cycle and full validated risk input in one local SQLite transaction, before the Worker sends the cycle to the existing remote RPC. The input includes the original evaluation time, candidate, sanitized observations, policy, equity/loss baselines, costs and safety/news context (including explicit missing values). Existing receipt identities/digests remain in the cycle. It does not fetch or archive the independently referenced raw ledger/calendar sources.

An archive error blocks that calculated cycle's remote write. A remote error can leave a **local-only** archive record. These are two stores, not a distributed transaction. A replay MATCH is not proof of a remote write. WAIT and pre-risk BLOCK cycles have no risk input to replay; older digest-only cycles cannot be reconstructed.

An in-process retry retains the exact input/cycle and rechecks the archive before retrying its remote write. Restart does not automatically resend local-only archived records. Recomputing different content under an already archived minute conflicts and blocks rather than replacing history. This archive is not a distributed outbox or a defense against a same-user administrator racing filesystem replacement.

## Local setup and privacy

The operator's Worker environment must provide `AURUM_SHADOW_REPLAY_PATH`: an absolute path with filename ending `.aurum-replay.sqlite3`, in an existing personal directory outside every Git checkout/project root. The Worker does not create its parent directory, discover a profile, or infer a path from credentials. It rejects symlinks/reparse points and unsafe existing files; the verifier never creates a missing archive. The standard Git ignore also excludes matching database sidecars.

This archive contains sensitive **sanitized financial research data**. Raw login/server values, passwords, cookies and keys are not part of the accepted schema; fingerprinted/masked identifiers are not anonymous data. SQLite itself does not encrypt the archive. Use an access-restricted personal folder on an appropriately protected disk; do not copy the archive into Git, chat, tickets or public storage. No archive containing the user's actual account data was opened or created during implementation.

Retention is bounded: at most 10,000 records, 262,144 bytes per envelope and 64 MiB for the main archive file (temporary rollback-journal overhead is additional). Full archives fail closed; there is no automatic purge or overwrite. Preserve an archive outside Git before selecting a fresh explicit path. Deleting an archive loses replay capability and does not delete its remote cycles.

## Verify one record without MT5

Use the non-secret owner/account/cycle UUIDs that identify the recorded cycle and the local archive path. These are database identifiers, not the MT5 login or account fingerprint:

```text
pnpm worker:shadow:replay --archive <absolute-path.aurum-replay.sqlite3> --owner-id <owner-uuid> --account-id <account-uuid> --cycle-id <cycle-uuid>
```

The command reads no environment credentials, connects to no service and opens SQLite read-only. It outputs status/reason only, not identifiers, source values, paths or raw errors:

- `MATCH` (exit 0): the validated stored input reproduces the recorded risk/eligibility checks and amounts for the supported versions at the original time.
- `MISMATCH` (exit 1): structurally valid evidence does not reproduce the recorded calculation.
- `UNAVAILABLE` (exit 2): missing/unreadable/invalid archive or record, wrong identity, unsupported version, or incomplete replay input. It is never treated as MATCH.

Canonical input identity uses UTC timestamps, sorted compact JSON and exact Decimal strings. The envelope is revalidated on write and read; duplicate JSON keys, unknown fields, unsafe flags, unsupported versions and mismatched owner/account/candidate/digest are rejected. SQLite stores one complete envelope under immutable cycle ID/key and rejects changed content on an existing identity. A hash is an integrity comparison, not a cryptographic signature: a local administrator able to rewrite all input/output evidence can still manufacture a self-consistent archive.

## Limits

Replay is a historical risk/eligibility calculation check. It does not rerun raw market normalization, feature extraction or strategy candidate generation; the retained candidate is checked against the risk input, not regenerated from broker history. It does not establish that submitted source receipts are authentic, independently retained sources are complete, the native transaction-time contract is resolved, current state is safe, eligibility is granted, a proposal was executed or a strategy is profitable. Real ledger/calendar/cost/safety providers, hosted Auth/persistence and real-source end-to-end validation remain pending.
