# Shadow persistence wire v1

Implementation contract for the authorized M3 continuation. All objects are strict (unknown keys rejected), JSON uses snake_case, financial decimals are finite plain decimal **strings**, timestamps are UTC `Z` or `+00:00` with at most six fractional digits, IDs are UUIDs, digests are lowercase SHA-256 hex. Arrays are bounded. Never include raw native structures or credentials.

## Cycle

`shadow_cycles` contains indexed identity columns and the exact immutable `payload` below. Browser reads `payload` plus verifies indexed IDs agree. Optional evidence uses explicit JSON null, not invented values.

Required fields:

- `schema_version`: `shadow-cycle-v1`; `pipeline_version`: `shadow-pipeline-v1`; `strategy_version`: `sma-atr-shadow-v1`; `eligibility_version`: `shadow-eligibility-v1`.
- `id`, `owner_id`, `trading_account_id`, `trace_id`: UUID.
- `cycle_key`: lowercase SHA-256 of UTF-8 `str(account_uuid) + "|" + UTC_minute.isoformat() + "|shadow-pipeline-v1|sma-atr-shadow-v1"`; the minute has zero seconds/microseconds and an explicit `+00:00` suffix. The identifier is UUID5 in NAMESPACE_URL of `aurum:shadow-cycle:` plus this key. Restart first loads an existing cycle before repeating capture. SQL enforces unique key and UUID linkage, not a second implementation of the hashing algorithm.
- `evaluated_at`: timestamp; `environment`: `DEMO_ONLY`; `runtime_mode`: `SHADOW`; `source`: `mt5`; `grants_eligibility`: false.
- `status`: `WAIT`, `BLOCK`, or `PROPOSAL`; `reason_codes`: 1..32 unique uppercase underscore codes (1..80 characters), no arbitrary exception text.
- `policy_version_id`: UUID or null; `policy_version`, `mode_version`: positive integer or null.
- `market`: null or the object below.
- `candidate`: null or `{id, direction: BUY|SELL, created_at, expires_at, entry_price, stop_loss_price, take_profit_price}`. All three prices positive strings; expiry after creation and at most 30 seconds later; directional SL/TP mandatory.
- `risk`: null or `{version: shadow-risk-v1, outcome: PASS|BLOCK, checks: [{code, passed}], input_digest, source_receipts, calculated_volume, estimated_loss_usd, estimated_net_reward_usd}`. Checks 1..64, unique uppercase codes, strict boolean. PASS iff all checks pass. BLOCK amounts all null; PASS positive strings and volume <=0.01. `input_digest` is SHA-256 of the validated risk input canonical JSON, not a substitute for source availability or full ledger replay.
- Each of at most four `risk.source_receipts` is `{kind: ledger|safety|news|costs, source_id, source_version, evidence_digest, observed_at, valid_until, covered_from, covered_until}`. IDs/versions use the same bounded 128-character identifier; digest is SHA-256. Times are UTC, observed <= valid_until, coverage both null or ordered covered_from <= covered_until. Kinds are unique; PASS requires all four. BLOCK may have none. Source receipt provenance must match market/account/policy during Worker validation; receipts retain independent source identity instead of relabeling calendar/fees as MT5 observations.
- `eligibility`: null or `{outcome: PASS|BLOCK, checks: [{code, passed}], sample_count: nonnegative integer, minimum_sample_size: integer>=30, calibrated: false}`. No probability. Missing sample evidence is count zero, explicitly failing the SAMPLE_SIZE gate; it is not an observed success count.

Market object:

- `snapshot_id`, `feature_id`, `reconciliation_id`: UUID; `input_digest`: SHA-256.
- `account_fingerprint`, `server_fingerprint`, `specification_fingerprint`: existing native identities `mt5-account-v1:`, `mt5-server-v1:`, `mt5-spec-v1:` followed by 64 lowercase hex digits. Never strip prefixes or infer a binding from these fields alone.
- `adapter_version`, `market_adapter_version`, `market_time_policy`, `broker_symbol`: bounded identifiers, 1..128.
- `captured_at`, `tick_at`, `last_bar_closed_at`: timestamps; `bid`, `ask`, `point`, `tick_size`, `fast_sma`, `slow_sma`: positive decimal strings; `atr`: nonnegative string.
- `bars`: exactly six `{open_at, open, high, low, close}` completed consecutive M1 bars, positive strings, valid OHLC. This is the exact normalized price input; volumes are not used by this version.

`PROPOSAL` requires all evidence and policy/mode versions, PASS risk, candidate and coherent current persisted reconciliation/binding/policy. It is a non-executable research proposal. Eligibility may BLOCK (e.g. unvalidated baseline/minimum sample), and never grants authority. `BLOCK` and `WAIT` may retain reached evidence and must have appropriate bounded reasons. A failing risk cannot yield PROPOSAL. WAIT has no candidate or risk. Full input provenance is retained in market, version IDs and risk checks; no unsupported full historical ledger is fabricated.

## Outcome event

`shadow_outcome_events` contains indexed identity plus exact immutable `payload`:

- `schema_version`: `shadow-outcome-v1`; `tracker_version`: `quote-observed-v1`; `simulation`: true; `grants_eligibility`: false.
- `id`, `owner_id`, `trading_account_id`, `cycle_id`: UUID.
- `sequence`: positive integer; `observed_at`: timestamp.
- `status`: `OBSERVED`, `STOP_OBSERVED`, `TARGET_OBSERVED`, `EXPIRED`, `UNKNOWN`.
- `reason_code`: bounded uppercase underscore code.
- `bid`, `ask`: positive strings or both null; `price_source`: `mt5` or `unavailable` (null quotes iff unavailable).
- `net_pnl_usd`: null (quote-only v1 does not claim broker fills, continuous paths or complete realized costs).

Only recorded PROPOSAL cycles accept events. OBSERVED is nonterminal; other statuses terminal. Sequence starts at one, increases by one, time strictly increases; terminal state cannot be reversed. Maximum sequence is 32, reserved for a terminal state. Other counts/versions are strict integers bounded by 2147483647. Event UUID idempotent replay must have identical payload; changed replay conflicts. Use BUY bid / SELL ask for threshold observation, never favorable bar-path assumptions. A source gap beyond five seconds, a future observation or restart without contiguous evidence terminates UNKNOWN. Expiry is candidate expiry, not an unbounded hypothetical position lifetime.

## Worker RPCs

- `worker_read_shadow_context(p_trading_account_id uuid)` returns `{result_code: CONTEXT_READY, data: {owner_id, trading_account_id, observed_at, mode_version, system_state, policy: <risk_policy_versions row>}}` or bounded result with null data. Owner/Worker identity derives from existing private claim helpers. Reads pending Emergency Stop/resume/uncertain state without consuming commands. Ready context requires Demo/Shadow, running, one current policy and no pending safety intents; this alone is not market readiness.
- `worker_read_shadow_cycles(p_trading_account_id uuid, p_cycle_key text default null)` returns `{result_code: CYCLES_READ, data: {cycles: [payload], outcomes: [payload]}}`. Exact key lookup when supplied; otherwise at most 100 most recent cycles and their at-most-32 events per cycle for restart/outcomes. Owner/account scoped, no raw provider data.
- `worker_record_shadow_cycle(p_cycle jsonb)` returns `{result_code: CYCLE_RECORDED|IDEMPOTENT_REPLAY, cycle_id, created: boolean}` or bounded denial/invalid/conflict result. Same key same semantic payload replays, different payload conflicts. Atomic current-state checks on new PROPOSAL.
- `worker_append_shadow_outcome(p_event jsonb)` returns `{result_code: OUTCOME_RECORDED|IDEMPOTENT_REPLAY, event_id, created: boolean}` or bounded denial/invalid/conflict result. Serialized per cycle.

Authenticated browser SELECT is owner-scoped and read-only; no RPC write grants. Dedicated Worker has narrow RPC EXECUTE only for new tables. FORCE RLS, composite owner/account foreign keys, append-only protections, dedicated function owner and empty search path apply. No interaction with approval/execution tables except read-only safety checks.
