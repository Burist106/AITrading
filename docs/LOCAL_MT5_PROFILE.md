# Remember this local Demo terminal

This user-authorized setup remembers a manually confirmed binding across normal app, PowerShell, and PC restarts. It remains **DEMO ONLY / SHADOW**, does not store or request passwords, and does not fix the unresolved native tick-time issue or start Milestone 3.

## One-time setup

1. Open MT5 yourself, select the intended Demo account, and make the intended XAU/USD symbol visible in Market Watch. Aurum never signs in, switches accounts, changes Market Watch, or enables AutoTrading.
2. Double-click `Aurum MT5.cmd` in the repository root. It uses the installed project Python directly, so daily use does not require Node, pnpm, a command prompt, or repeated environment setup. Opening this window alone makes no MT5 call.
3. Choose **ตั้งค่าครั้งแรก / ยืนยันค่าใหม่**, then select that terminal's `terminal64.exe` in the local file picker. No candidate is selected automatically.
4. Inspect the masked Demo account/server and confirm with the first dialog. Then explicitly choose a visible native XAU/USD candidate.
5. Inspect the separately read specification, especially contract size, minimum volume, volume step, tick size/value, stops level, and trade mode. Confirm with the second dialog. No fingerprint needs to be copied or typed.
6. Aurum opens a separate read-only connection to recheck the approved account/specification. Only after all reads and shutdowns succeed is the encrypted profile saved.

All dialogs default to non-acceptance. Cancelling before saving leaves any prior profile untouched. Saving a binding is **not** a healthy tick, full smoke, or trading eligibility result.

## After restarting

Open MT5 and the same launcher. Use **ตรวจบัญชีและสเปกที่จดจำไว้** to compare current native evidence with the saved binding. Use **ตรวจเวลา tick (diagnostic เท่านั้น)** to run the gated timestamp diagnostic. Neither action rewrites a saved fingerprint. A changed account/server/specification or unusable symbol blocks and requires a new deliberate setup; a non-Demo account always blocks.

The profile-backed CLI alternatives are:

```text
pnpm worker:mt5:profile
pnpm worker:mt5:profile:check
pnpm worker:mt5:profile:tick-time
```

These are separate from the existing environment-backed `worker:mt5:fingerprint`, `worker:mt5:tick-time`, and `worker:mt5:smoke` commands. Legacy commands and the deployed database-backed Worker do not load this profile. The local profile does not create a Supabase confirmed binding.

The dedicated `worker:mt5:profile:smoke` command requires `AURUM_MT5_READONLY_SMOKE=1` in that invocation's process. The flag is never remembered. Without opt-in, it reports NOT RUN before reading the profile or terminal. With opt-in, it first verifies the saved binding and then invokes the unchanged complete read-only smoke workflow. Do not interpret check/diagnostic success as smoke success.

## Storage and failure behavior

- Only ciphertext is written to `%LOCALAPPDATA%\Aurum\LocalDemo\mt5-profile.dpapi`, outside Git. There is no plaintext `.env`, registry/setx value, credential-store entry, cloud upload, or browser copy.
- The allowlisted payload contains the explicit path, broker alias, account/specification hashes, two manual confirmation timestamps, schema version, and fixed Demo/Shadow labels. It contains no raw account/server identity, password, secret, smoke flag, limits, observations, or cached pass result.
- [Windows DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata) uses current-user protection, not machine-wide access. [Decryption](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata) is normally tied to that Windows identity and machine; roaming-profile exceptions exist. Copying the file to a different user/machine is not a supported migration workflow. Reconfirm on the new environment instead.
- DPAPI failure, corruption, schema/version/size violations, or invalid location fails closed without fallback. Same-user malware/administrators and rollback of an older valid profile are outside this local storage defense; current Demo/account/specification checks remain mandatory regardless.
- Saves encrypt in memory, write ciphertext to an exclusive temporary file, flush, and atomically replace the profile under a setup lock with a revision comparison. The prior file remains intact on failed encryption/write/replace. No plaintext temporary file is used. A cleanup failure reports failure rather than claiming the operation fully completed.
- `PROFILE_BUSY` means an active or interrupted setup lock exists. A second setup will not clear another process's lock automatically. If no setup is running, request local recovery; do not remove broad folders or reset Windows/Docker settings. Ordinary successful saves remove their own lock.
- `PROFILE_ENV_CONFLICT` means binding environment values were also supplied. Use a fresh process without those four values or intentionally use the legacy environment workflow. Never combine half a saved profile with half an environment binding. Nondefault 10/30-second limits also block profile commands.
- Invalid/missing terminal, disconnected/non-Demo account, changed bindings, or unsafe market evidence is not a reason to widen limits, auto-confirm, or change the PC clock.

## Verification boundary

Local verification on 2026-09-09: frozen-lockfile install and full `pnpm check` passed (format, lint, TypeScript/Python types, 88 JavaScript tests, 324 Worker tests, production/Worker build, secret and runtime scanners, and 7 scanner tests). The Worker total includes 56 new profile tests, including real Windows DPAPI cross-process reload and damaged-ciphertext rejection. `pip check` passed. Dependency audit initially failed on two existing transitive dependencies; the narrowly scoped patches in `DEPENDENCY_PATCH_2026_09_09.md` brought the audit to no known vulnerabilities. The local Tk preview used stubbed operations with no terminal access; visual inspection prompted larger Thai fonts and button spacing.

Local database verification remains **BLOCKED**: `db:start` failed because the local Docker engine was unavailable, so database reset/lint/tests/type comparison could not run here. No Docker settings/data reset was attempted. Real terminal setup, actual PC reboot, and real MT5 smoke were **NOT RUN** for this profile implementation. No readiness gate or Milestone 3 status was promoted by these results.

Tests use fictional adapters and data. Windows-only tests additionally encrypt/decrypt a synthetic profile with actual DPAPI and load it from a second Python process, then reject damaged ciphertext. They require neither a real terminal nor credentials. This demonstrates cross-process persistence, not an actual reboot, cross-user attack test, or passing real MT5 smoke. The real profile can be created only when the operator completes the local confirmation dialogs.
