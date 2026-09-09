# Milestone 3 readiness gate

Status: **NOT READY — REAL TERMINAL TIMESTAMP EVIDENCE PENDING**.

The user authorized a read-only timestamp diagnostic and a goal to reach readiness on 2026-09-08. This document does not start the Shadow Pipeline or override its safety prerequisites. Milestone 2 remains **COMPLETE WITH DOCUMENTED LIMITATIONS**, its release-time real-terminal smoke remains **NOT RUN**, and Milestone 3 remains **NOT STARTED**.

## Follow-up gates

- [x] Preserve the released Milestone 2 baseline and implement the diagnostic on a separate branch.
- [x] Complete local diagnostic regression, format, lint, type, unit, build, dependency, and security checks.
- [x] Complete database checks and clean-checkout CI on diagnostic implementation commit `773d64d` (evidence below).
- [ ] Obtain separately operator-confirmed, local-only Demo diagnostic evidence from the exact reviewed patch.
- [ ] Establish the native timestamp convention or field defect from evidence; do not guess an offset, alter the PC clock, or widen safety tolerances.
- [ ] Resolve the timestamp incompatibility within an explicitly reviewed safe contract, if a source correction is justified.
- [ ] Run the complete opted-in real Demo read-only smoke and record its actual output, exit code, and shutdown. A diagnostic success is not this gate.
- [ ] Complete source review and required clean-checkout CI for any patch before merge authorization; do not merge automatically.
- [ ] Record remaining operational limitations and present a bounded Milestone 3 implementation plan for explicit authorization.

## Evidence boundaries

Real-terminal reports stay outside Git and contain no identifiers or fingerprints. The diagnostic reads only one tick after bound-account and confirmed-specification checks. No strategy, feature pipeline, Risk Engine, proposal generation, command consumer, broker write, Position modification, or Live Trading is authorized by this follow-up.

The original roadmap treats the real smoke as optional for the historical Milestone 2 release. This goal deliberately addresses the subsequently observed real-terminal blocker before declaring readiness; it does not rewrite the release record into a pass or failure.

## Diagnostic implementation verification (2026-09-08)

The new regression was run before implementation and failed because the diagnostic method did not exist. After implementation, all 35 diagnostic tests passed. The full local `pnpm check` passed: formatting, lint, TypeScript checks, mypy, 88 TypeScript tests, 268 Worker tests, production builds, runtime boundaries, secret scanning, and seven scanner tests. The secret scan was repeated after adding the new files to Git's inventory. `pnpm audit --audit-level high`, `pip check`, and `git diff --check` also passed.

Local database startup was attempted through the repository's isolated wrapper and failed with `The local Docker engine is not running or is unavailable (exit 1)`. Docker Desktop displayed an internal startup error. No factory reset, Docker data deletion, settings change, or diagnostic upload was performed. Local database reset, lint, pgTAP/concurrency tests, and generated-type validation therefore have no passing result for this patch; the Draft PR's isolated database job must supply independent evidence.

That independent evidence is now available: [GitHub Actions run 34247359271](https://github.com/Burist106/AITrading/actions/runs/34247359271) passed all three jobs on implementation commit `773d64d4d9458e409fe1329c255f5e6f0976b185`. The database job passed both deterministic resets, schema lint, 400 pgTAP assertions, four concurrent-claim assertions, and generated-type comparison. The Windows boundary job passed 132 fake-backed tests and the package/import and security checks. The quality job passed the full repository checks, including 268 Worker tests. This is CI evidence, not a successful local Docker repair or a real-terminal smoke.

The Windows boundary CI job also includes the new fake-backed diagnostic tests. Real-terminal diagnostic and full smoke have not been run on this patch. Current process-local operator bindings are absent; prior confirmations are not reconstructed, persisted, or automatically copied from observed account/specification values.

## Next operator gate

On 2026-09-09 the user authorized the separate [encrypted local profile setup](LOCAL_MT5_PROFILE.md) to remove repeated fingerprint entry across restarts. The operator may complete its two local confirmation dialogs once and subsequently use the profile-backed diagnostic. Saved values are never a cached pass or automatic confirmation of changed observations. This narrow authorization supersedes the earlier requirement to re-enter all binding values each session; it does not resolve the timestamp gate or authorize Milestone 3.

Keep [PR #2](https://github.com/Burist106/AITrading/pull/2) in Draft; no merge or branch deletion is authorized. When the operator is available, resume the existing local-only path/account/symbol/specification confirmation sequence against the reviewed diagnostic source. Do not ask for any local value in chat. Run the diagnostic only after all confirmations exist in that process, and retain only its sanitized evidence outside Git. If the native time evidence remains incompatible with freshness policy, classify and stop; do not infer a fixed timezone correction.

After evidence supports a reviewed resolution and the complete real read-only smoke passes, present the roadmap's bounded Shadow Pipeline plan for explicit authorization: versioned market normalization and features, a reproducible rule-based baseline, deterministic eligibility and risk, and traceable shadow proposals/outcomes with owner-scoped dashboard read models. Strategy implementation, Risk Engine implementation, proposal production, approvals, command consumption, and broker execution remain outside this diagnostic follow-up.
