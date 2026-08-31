import {
  Mt5ConsoleReadModelSchema,
  type Database,
  type Mt5ConsoleReadModel,
} from "@aurum/contracts";

export type Mt5AccountObservationReadRow =
  Database["public"]["Tables"]["mt5_account_observations"]["Row"];
export type Mt5SymbolObservationReadRow =
  Database["public"]["Tables"]["mt5_symbol_observations"]["Row"];
export type Mt5LatestTickObservationReadRow =
  Database["public"]["Tables"]["mt5_latest_tick_observations"]["Row"];
export type Mt5ReconciliationRunReadRow =
  Database["public"]["Tables"]["mt5_reconciliation_runs"]["Row"];
export type Mt5ReconciliationMismatchReadRow =
  Database["public"]["Tables"]["mt5_reconciliation_mismatches"]["Row"];
export type Mt5HistoryQueryEvidenceReadRow =
  Database["public"]["Tables"]["mt5_history_query_evidence"]["Row"];

/** Two missed maximum-length tick polls expire the browser's liveness claim. */
const MT5_OBSERVATION_MAX_AGE_SECONDS = 60;

function decimalString(value: number): string {
  if (!Number.isFinite(value)) throw new TypeError("Invalid database decimal.");
  return String(value);
}

function specificationValue(
  specification: Mt5SymbolObservationReadRow["normalized_specification"],
  key: string,
): string {
  if (
    specification === null ||
    Array.isArray(specification) ||
    typeof specification !== "object"
  ) {
    throw new TypeError("Invalid normalized specification.");
  }
  const value = specification[key];
  if (typeof value !== "string") {
    throw new TypeError("Invalid normalized specification field.");
  }
  return value;
}

export interface Mt5ConsoleRows {
  readonly account: Mt5AccountObservationReadRow | null;
  readonly symbol: Mt5SymbolObservationReadRow | null;
  readonly tick: Mt5LatestTickObservationReadRow | null;
  readonly reconciliation: Mt5ReconciliationRunReadRow | null;
  readonly mismatches: readonly Mt5ReconciliationMismatchReadRow[];
  readonly historyEvidence: readonly Mt5HistoryQueryEvidenceReadRow[];
}

export function mt5ConsoleFromReadRows(
  rows: Mt5ConsoleRows,
  currentTime: Date = new Date(),
): Mt5ConsoleReadModel {
  const account = rows.account;
  const symbol = rows.symbol;
  const tick = rows.tick;
  const reconciliation = rows.reconciliation;
  const verificationState = account?.verification_state ?? null;
  const reconciliationMatchesCurrentObservations =
    account !== null &&
    symbol !== null &&
    tick !== null &&
    reconciliation !== null &&
    symbol.account_fingerprint === account.account_fingerprint &&
    tick.account_fingerprint === account.account_fingerprint &&
    tick.broker_symbol === symbol.broker_symbol &&
    reconciliation.account_fingerprint === account.account_fingerprint &&
    reconciliation.server_fingerprint === account.server_fingerprint &&
    reconciliation.broker_symbol === symbol.broker_symbol &&
    reconciliation.symbol_specification_fingerprint ===
      symbol.specification_fingerprint;
  const historyKinds = new Set(
    rows.historyEvidence.map(({ history_kind }) => history_kind),
  );
  const reconciliationHasHealthyHistoryEvidence =
    rows.historyEvidence.length === 2 &&
    historyKinds.size === 2 &&
    historyKinds.has("orders") &&
    historyKinds.has("deals") &&
    rows.historyEvidence.every(
      ({ result_state }) =>
        result_state === "query_succeeded" ||
        result_state === "empty_valid_result",
    );
  const tickObservationAgeSeconds =
    tick === null
      ? null
      : (currentTime.getTime() - Date.parse(tick.observed_at)) / 1_000;
  const tickObservationCurrent =
    tickObservationAgeSeconds !== null &&
    tickObservationAgeSeconds >= -MT5_OBSERVATION_MAX_AGE_SECONDS &&
    tickObservationAgeSeconds <= MT5_OBSERVATION_MAX_AGE_SECONDS;
  const currentTickAgeSeconds =
    tick === null
      ? null
      : Math.max(
          0,
          Math.round(
            ((currentTime.getTime() - Date.parse(tick.tick_at)) / 1_000) *
              1_000,
          ) / 1_000,
        );

  let state: "healthy" | "degraded" | "blocked" | "unavailable" =
    account === null ? "unavailable" : "healthy";
  let reasonCode = account === null ? "MT5_OBSERVATION_UNAVAILABLE" : "HEALTHY";
  if (account === null) {
    state = "unavailable";
    reasonCode = "MT5_OBSERVATION_UNAVAILABLE";
  } else if (
    account.trade_mode !== "demo" ||
    (verificationState !== "verified_demo_bound" &&
      verificationState !== "verified_demo_unbound")
  ) {
    state = "blocked";
    reasonCode = "ACCOUNT_VERIFICATION_BLOCKED";
  } else if (tick !== null && !tickObservationCurrent) {
    state = "unavailable";
    reasonCode = "MT5_OBSERVATION_STALE";
  } else if (reconciliation === null) {
    state = "blocked";
    reasonCode = "RECONCILIATION_REQUIRED";
  } else if (reconciliation.status === "running") {
    state = "degraded";
    reasonCode = "RECONCILIATION_PENDING";
  } else if (reconciliation.outcome !== "matched") {
    state = "blocked";
    reasonCode = reconciliation.reason_code;
  } else if (symbol === null) {
    state = "blocked";
    reasonCode = "SYMBOL_OBSERVATION_UNAVAILABLE";
  } else if (symbol.usability_state !== "usable") {
    state = "blocked";
    reasonCode = symbol.unusable_reason ?? "SYMBOL_UNUSABLE";
  } else if (tick === null) {
    state = "blocked";
    reasonCode = "TICK_UNAVAILABLE";
  } else if (!reconciliationMatchesCurrentObservations) {
    state = "blocked";
    reasonCode = "RECONCILIATION_OBSERVATION_MISMATCH";
  } else if (
    reconciliation.mismatch_count !== 0 ||
    rows.mismatches.length !== 0 ||
    !reconciliationHasHealthyHistoryEvidence
  ) {
    state = "blocked";
    reasonCode = "RECONCILIATION_EVIDENCE_INCOMPLETE";
  } else if (tick.freshness !== "live") {
    state = "blocked";
    reasonCode =
      tick.freshness === "future_invalid"
        ? "TICK_FROM_FUTURE"
        : tick.freshness === "stale"
          ? "TICK_STALE"
          : tick.freshness === "delayed"
            ? "TICK_DELAYED"
            : "TICK_UNAVAILABLE";
  } else if (verificationState === "verified_demo_unbound") {
    state = "degraded";
    reasonCode = "DEMO_ACCOUNT_UNBOUND";
  }

  const observedAt =
    tick?.observed_at ?? account?.observed_at ?? "1970-01-01T00:00:00Z";
  const source = tick?.source ?? account?.source ?? "fake_mt5";
  const adapterVersion =
    tick?.adapter_version ?? account?.adapter_version ?? "unavailable";
  const traceId = tick?.trace_id ?? account?.trace_id ?? "unavailable";

  return Mt5ConsoleReadModelSchema.parse({
    account:
      account === null
        ? null
        : {
            observedAt: account.observed_at,
            source: account.source,
            adapterVersion: account.adapter_version,
            traceId: account.trace_id,
            schemaVersion: account.schema_version,
            tradeMode: account.trade_mode,
            verificationState: account.verification_state,
            maskedLogin: account.masked_login,
            maskedServer: account.masked_server,
            accountFingerprint: account.account_fingerprint,
            serverFingerprint: account.server_fingerprint,
          },
    symbol:
      symbol === null
        ? null
        : {
            observedAt: symbol.observed_at,
            source: symbol.source,
            adapterVersion: symbol.adapter_version,
            traceId: symbol.trace_id,
            schemaVersion: symbol.schema_version,
            canonicalSymbol: symbol.canonical_symbol,
            brokerSymbol: symbol.broker_symbol,
            currencyBase: specificationValue(
              symbol.normalized_specification,
              "base_currency",
            ),
            currencyProfit: specificationValue(
              symbol.normalized_specification,
              "profit_currency",
            ),
            specificationFingerprint: symbol.specification_fingerprint,
            usabilityState: symbol.usability_state,
            unusableReason: symbol.unusable_reason,
            point: specificationValue(symbol.normalized_specification, "point"),
            tickSize: specificationValue(
              symbol.normalized_specification,
              "tick_size",
            ),
            contractSize: specificationValue(
              symbol.normalized_specification,
              "contract_size",
            ),
            minimumVolume: specificationValue(
              symbol.normalized_specification,
              "minimum_volume",
            ),
            maximumVolume: specificationValue(
              symbol.normalized_specification,
              "maximum_volume",
            ),
            volumeStep: specificationValue(
              symbol.normalized_specification,
              "volume_step",
            ),
          },
    tick:
      tick === null
        ? null
        : {
            observedAt: tick.observed_at,
            source: tick.source,
            adapterVersion: tick.adapter_version,
            traceId: tick.trace_id,
            schemaVersion: tick.schema_version,
            symbol: tick.broker_symbol,
            bid: decimalString(tick.bid),
            ask: decimalString(tick.ask),
            spreadPrice: decimalString(tick.spread_price),
            spreadPoints: decimalString(tick.spread_points),
            tickAt: tick.tick_at,
            ageSeconds: decimalString(tick.age_seconds),
            freshness: tick.freshness,
          },
    reconciliation:
      reconciliation === null
        ? null
        : {
            id: reconciliation.id,
            traceId: reconciliation.trace_id,
            status: reconciliation.status,
            outcome: reconciliation.outcome,
            reasonCode: reconciliation.reason_code,
            startedAt: reconciliation.started_at,
            completedAt: reconciliation.completed_at,
            openPositionCount: reconciliation.open_position_count,
            activeOrderCount: reconciliation.active_order_count,
            mismatchCount: reconciliation.mismatch_count,
            mismatches: rows.mismatches.map((mismatch) => ({
              category: mismatch.category,
              severity: mismatch.severity,
              resourceType: mismatch.resource_type,
              resourceReference: mismatch.resource_reference,
              reasonCode: mismatch.reason_code,
            })),
            historyEvidence: rows.historyEvidence.map((evidence) => ({
              historyKind: evidence.history_kind,
              requestedStartAt: evidence.requested_start_at,
              requestedEndAt: evidence.requested_end_at,
              queryCompletedAt: evidence.query_completed_at,
              returnedCount: evidence.returned_count,
              earliestReturnedAt: evidence.earliest_returned_at,
              latestReturnedAt: evidence.latest_returned_at,
              resultState: evidence.result_state,
              reasonCode: evidence.reason_code,
            })),
          },
    health: {
      observedAt,
      source,
      adapterVersion,
      traceId,
      schemaVersion: "1",
      state,
      reasonCode,
      packageAvailable: account !== null && tickObservationCurrent,
      platform: "windows",
      terminalConnected: account !== null && tickObservationCurrent,
      terminalVersion: null,
      accountVerificationState: verificationState,
      maskedAccount: account?.masked_login ?? null,
      maskedServer: account?.masked_server ?? null,
      brokerSymbol: symbol?.broker_symbol ?? null,
      specificationFingerprint: symbol?.specification_fingerprint ?? null,
      tickAgeSeconds:
        currentTickAgeSeconds === null
          ? null
          : decimalString(currentTickAgeSeconds),
      lastCompletedCandleAt: null,
      lastSuccessfulObservationAt: tickObservationCurrent ? observedAt : null,
      reconciliationOutcome: reconciliation?.outcome ?? null,
      openPositionCount: reconciliation?.open_position_count ?? null,
      activeOrderCount: reconciliation?.active_order_count ?? null,
    },
  });
}

export type Mt5PanelState =
  | "loading"
  | "empty"
  | "healthy"
  | "degraded"
  | "blocked"
  | "unavailable"
  | "stale"
  | "reconnecting"
  | "reconciliation_pending"
  | "reconciliation_failed";

export function deriveMt5PanelState(
  model: Mt5ConsoleReadModel | null | undefined,
): Mt5PanelState {
  if (model === undefined) return "loading";
  if (model === null || model.account === null) return "empty";
  if (!model.health.terminalConnected) return "reconnecting";
  if (model.reconciliation?.status === "running") {
    return "reconciliation_pending";
  }
  if (
    model.reconciliation?.status === "completed" &&
    model.reconciliation.outcome !== "matched"
  ) {
    return "reconciliation_failed";
  }
  if (
    model.tick?.freshness === "stale" ||
    model.tick?.freshness === "future_invalid"
  ) {
    return "stale";
  }
  return model.health.state;
}
