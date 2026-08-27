-- Aurum Console Milestone 1: owner-scoped control-plane domain schema.
-- All instants are timestamptz, all prices/money/percentages/volumes are numeric,
-- and all browser-facing ownership joins are enforced by composite foreign keys.

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text not null default 'Aurum Owner',
  locale text not null default 'th' check (locale in ('th', 'en')),
  timezone text not null default 'Asia/Bangkok'
    check (pg_catalog.btrim(timezone) <> '' and pg_catalog.length(timezone) <= 80),
  version integer not null default 1 check (version > 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.btrim(display_name) <> '' and pg_catalog.length(display_name) <= 160)
);

create table public.trading_accounts (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null references public.profiles (id) on delete cascade,
  environment text not null default 'DEMO_ONLY'
    check (environment = 'DEMO_ONLY'),
  account_type text not null default 'demo' check (account_type = 'demo'),
  verification_state text not null default 'pending'
    check (verification_state in ('pending', 'verified_demo', 'blocked')),
  broker_account_reference text not null,
  broker_server text not null,
  account_currency text not null default 'USD'
    check (account_currency ~ '^[A-Z]{3}$'),
  maximum_permitted_volume numeric(8, 4) not null default 0.01
    check (maximum_permitted_volume = 0.01),
  maximum_open_positions smallint not null default 1
    check (maximum_open_positions = 1),
  stop_loss_required boolean not null default true check (stop_loss_required),
  version integer not null default 1 check (version > 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (
    pg_catalog.btrim(broker_account_reference) <> ''
    and pg_catalog.length(broker_account_reference) <= 160
  ),
  check (
    pg_catalog.btrim(broker_server) <> ''
    and pg_catalog.length(broker_server) <= 160
  ),
  unique (id, owner_id),
  unique (owner_id, broker_account_reference, broker_server)
);

create index trading_accounts_owner_idx
  on public.trading_accounts (owner_id);

create table public.broker_symbols (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trading_account_id uuid not null,
  canonical_symbol text not null default 'XAUUSD'
    check (canonical_symbol = 'XAUUSD'),
  broker_symbol text not null,
  specification_version text not null,
  account_currency text not null check (account_currency ~ '^[A-Z]{3}$'),
  contract_size numeric(24, 8) not null check (contract_size > 0),
  digits smallint not null check (digits >= 0),
  point_size numeric(24, 12) not null check (point_size > 0),
  tick_size numeric(24, 12) not null check (tick_size > 0),
  tick_value numeric(24, 8) check (tick_value is null or tick_value > 0),
  minimum_volume numeric(8, 4) not null check (minimum_volume > 0),
  maximum_volume numeric(8, 4) not null check (maximum_volume > 0),
  volume_step numeric(8, 4) not null check (volume_step > 0),
  stop_level integer not null check (stop_level >= 0),
  calculation_mode text not null,
  fetched_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (minimum_volume <= maximum_volume),
  check (pg_catalog.btrim(broker_symbol) <> '' and pg_catalog.length(broker_symbol) <= 160),
  check (
    pg_catalog.btrim(specification_version) <> ''
    and pg_catalog.length(specification_version) <= 160
  ),
  check (
    pg_catalog.btrim(calculation_mode) <> ''
    and pg_catalog.length(calculation_mode) <= 160
  ),
  unique (id, owner_id),
  unique (id, owner_id, specification_version),
  unique (id, owner_id, trading_account_id, specification_version),
  unique (trading_account_id, specification_version),
  foreign key (trading_account_id, owner_id)
    references public.trading_accounts (id, owner_id) on delete cascade
);

create index broker_symbols_owner_account_idx
  on public.broker_symbols (owner_id, trading_account_id, fetched_at desc);

create table public.trading_modes (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trading_account_id uuid not null,
  mode text not null default 'shadow' check (mode = 'shadow'),
  system_state public.runtime_system_state not null default 'running',
  state_reason text,
  version integer not null default 1 check (version > 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (
    state_reason is null
    or (pg_catalog.btrim(state_reason) <> '' and pg_catalog.length(state_reason) <= 160)
  ),
  unique (id, owner_id),
  unique (trading_account_id),
  foreign key (trading_account_id, owner_id)
    references public.trading_accounts (id, owner_id) on delete cascade
);

create index trading_modes_owner_idx on public.trading_modes (owner_id);

create table public.risk_policies (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trading_account_id uuid not null,
  policy_key text not null,
  active_version_id uuid,
  resource_version integer not null default 1 check (resource_version > 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.btrim(policy_key) <> '' and pg_catalog.length(policy_key) <= 160),
  unique (id, owner_id),
  unique (id, owner_id, trading_account_id),
  unique (owner_id, trading_account_id, policy_key),
  foreign key (trading_account_id, owner_id)
    references public.trading_accounts (id, owner_id) on delete cascade
);

create index risk_policies_owner_account_idx
  on public.risk_policies (owner_id, trading_account_id);

create table public.risk_policy_versions (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  risk_policy_id uuid not null,
  trading_account_id uuid not null,
  version integer not null check (version > 0),
  version_label text not null,
  source_command_id uuid,
  environment text not null default 'DEMO_ONLY' check (environment = 'DEMO_ONLY'),
  canonical_symbol text not null default 'XAUUSD' check (canonical_symbol = 'XAUUSD'),
  maximum_permitted_volume numeric(8, 4) not null default 0.01
    check (maximum_permitted_volume = 0.01),
  maximum_open_positions smallint not null default 1 check (maximum_open_positions = 1),
  stop_loss_required boolean not null default true check (stop_loss_required),
  martingale_allowed boolean not null default false check (not martingale_allowed),
  grid_trading_allowed boolean not null default false check (not grid_trading_allowed),
  averaging_down_allowed boolean not null default false check (not averaging_down_allowed),
  loss_based_volume_increase_allowed boolean not null default false
    check (not loss_based_volume_increase_allowed),
  risk_per_trade_pct numeric(8, 4) not null default 0.25
    check (risk_per_trade_pct >= 0 and risk_per_trade_pct <= 0.25),
  daily_loss_limit_pct numeric(8, 4) not null default 1.00
    check (daily_loss_limit_pct >= 0 and daily_loss_limit_pct <= 1.00),
  weekly_loss_limit_pct numeric(8, 4) not null default 3.00
    check (weekly_loss_limit_pct >= 0 and weekly_loss_limit_pct <= 3.00),
  maximum_drawdown_pct numeric(8, 4) not null default 5.00
    check (maximum_drawdown_pct >= 0 and maximum_drawdown_pct <= 5.00),
  maximum_trades_per_day smallint not null default 3
    check (maximum_trades_per_day >= 0 and maximum_trades_per_day <= 3),
  minimum_risk_reward numeric(8, 4) not null default 1.50
    check (minimum_risk_reward >= 1.50),
  stale_data_max_age_seconds integer not null default 10
    check (stale_data_max_age_seconds >= 0 and stale_data_max_age_seconds <= 10),
  maximum_spread_points numeric(12, 4) not null default 3.50
    check (maximum_spread_points >= 0 and maximum_spread_points <= 3.50),
  spread_warning_points numeric(12, 4) not null default 2.80
    check (spread_warning_points >= 0 and spread_warning_points <= maximum_spread_points),
  news_blackout_minutes integer not null default 15
    check (news_blackout_minutes >= 15),
  proposal_expiry_seconds integer not null default 30
    check (proposal_expiry_seconds > 0 and proposal_expiry_seconds <= 30),
  entry_tolerance_points numeric(12, 4) not null default 0.60
    check (entry_tolerance_points >= 0 and entry_tolerance_points <= 0.60),
  minimum_sample_size integer not null default 30 check (minimum_sample_size >= 30),
  require_calibrated_model boolean not null default false
    check (not require_calibrated_model),
  maximum_slippage_points numeric(12, 4) not null default 0.50
    check (maximum_slippage_points >= 0 and maximum_slippage_points <= 0.50),
  automatic_retry_on_broker_reject boolean not null default false
    check (not automatic_retry_on_broker_reject),
  reason text not null,
  created_by_type public.actor_type not null,
  created_by text not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.btrim(version_label) <> '' and pg_catalog.length(version_label) <= 160),
  check (pg_catalog.btrim(reason) <> '' and pg_catalog.length(reason) <= 160),
  check (pg_catalog.btrim(created_by) <> '' and pg_catalog.length(created_by) <= 160),
  unique (id, owner_id),
  unique (id, risk_policy_id, owner_id),
  unique (id, owner_id, version_label),
  unique (id, owner_id, version_label, trading_account_id),
  unique (risk_policy_id, version),
  foreign key (risk_policy_id, owner_id, trading_account_id)
    references public.risk_policies (id, owner_id, trading_account_id) on delete cascade
);

alter table public.risk_policies
  add constraint risk_policies_active_version_owner_fk
  foreign key (active_version_id, id, owner_id)
  references public.risk_policy_versions (id, risk_policy_id, owner_id)
  deferrable initially deferred;

create index risk_policy_versions_owner_policy_idx
  on public.risk_policy_versions (owner_id, risk_policy_id, version desc);
create unique index risk_policy_versions_source_command_once_idx
  on public.risk_policy_versions (source_command_id)
  where source_command_id is not null;

comment on column public.risk_policy_versions.news_blackout_minutes is
  'Symmetric high-impact event blackout: this many minutes both before and after the event.';

create table public.market_snapshots (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trading_account_id uuid not null,
  canonical_symbol text not null default 'XAUUSD' check (canonical_symbol = 'XAUUSD'),
  bid numeric(24, 8) not null check (bid > 0),
  ask numeric(24, 8) not null check (ask > 0),
  spread_points numeric(16, 6) not null check (spread_points >= 0),
  session public.market_session not null,
  regime public.market_regime not null,
  atr numeric(24, 8) not null check (atr >= 0),
  freshness public.market_freshness not null,
  age_ms integer not null check (age_ms >= 0),
  transport public.market_transport not null,
  captured_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (ask >= bid),
  unique (id, owner_id),
  unique (id, owner_id, trading_account_id),
  foreign key (trading_account_id, owner_id)
    references public.trading_accounts (id, owner_id) on delete cascade
);

create index market_snapshots_owner_account_time_idx
  on public.market_snapshots (owner_id, trading_account_id, captured_at desc);

create table public.feature_snapshots (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trading_account_id uuid not null,
  market_snapshot_id uuid not null,
  feature_schema_version text not null,
  feature_values jsonb not null,
  captured_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.jsonb_typeof(feature_values) = 'object'),
  check (
    pg_catalog.btrim(feature_schema_version) <> ''
    and pg_catalog.length(feature_schema_version) <= 160
  ),
  unique (id, owner_id),
  unique (id, owner_id, trading_account_id),
  unique (id, owner_id, trading_account_id, market_snapshot_id),
  foreign key (trading_account_id, owner_id)
    references public.trading_accounts (id, owner_id) on delete cascade,
  foreign key (market_snapshot_id, owner_id, trading_account_id)
    references public.market_snapshots (id, owner_id, trading_account_id) on delete restrict
);

create index feature_snapshots_owner_account_time_idx
  on public.feature_snapshots (owner_id, trading_account_id, captured_at desc);

create table public.trade_proposals (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  proposal_version integer not null check (proposal_version > 0),
  trading_account_id uuid not null,
  broker_symbol_id uuid not null,
  risk_policy_version_id uuid not null,
  account_type text not null default 'demo' check (account_type = 'demo'),
  account_currency text not null check (account_currency ~ '^[A-Z]{3}$'),
  broker_server text not null,
  canonical_symbol text not null default 'XAUUSD' check (canonical_symbol = 'XAUUSD'),
  broker_symbol text not null,
  symbol_specification_version text not null,
  direction public.trade_direction not null,
  strategy_code text not null,
  strategy_version text not null,
  model_version text,
  eligibility_policy_id text not null,
  eligibility_policy_version text not null,
  eligibility_outcome public.eligibility_outcome not null,
  eligibility_evaluated_at timestamptz not null,
  risk_policy_version text not null,
  entry_price numeric(24, 8) not null check (entry_price > 0),
  stop_loss_price numeric(24, 8) not null check (stop_loss_price > 0),
  take_profit_price numeric(24, 8) not null check (take_profit_price > 0),
  calculated_volume numeric(8, 4) not null check (calculated_volume > 0),
  requested_volume numeric(8, 4)
    check (requested_volume is null or (requested_volume > 0 and requested_volume <= 0.01)),
  approved_volume numeric(8, 4)
    check (approved_volume is null or (approved_volume > 0 and approved_volume <= 0.01)),
  maximum_permitted_volume numeric(8, 4) not null default 0.01
    check (maximum_permitted_volume = 0.01),
  risk_amount numeric(24, 8) not null check (risk_amount > 0),
  risk_pct numeric(8, 4) not null check (risk_pct > 0),
  risk_reward numeric(12, 4) not null check (risk_reward > 0),
  market_snapshot_id uuid not null,
  feature_snapshot_id uuid not null,
  decision_trace_id uuid not null,
  status public.trade_proposal_status not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  expires_at timestamptz not null,
  processed_at timestamptz,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (expires_at > created_at),
  check (
    (direction = 'BUY' and stop_loss_price < entry_price and entry_price < take_profit_price)
    or
    (direction = 'SELL' and take_profit_price < entry_price and entry_price < stop_loss_price)
  ),
  check (status <> 'blocked' or (requested_volume is null and approved_volume is null)),
  check (approved_volume is null or requested_volume is not null),
  check (approved_volume is null or approved_volume <= requested_volume),
  check (pg_catalog.btrim(broker_server) <> '' and pg_catalog.length(broker_server) <= 160),
  check (pg_catalog.btrim(broker_symbol) <> '' and pg_catalog.length(broker_symbol) <= 160),
  check (pg_catalog.btrim(strategy_code) <> '' and pg_catalog.length(strategy_code) <= 160),
  check (pg_catalog.btrim(strategy_version) <> '' and pg_catalog.length(strategy_version) <= 160),
  unique (id, owner_id),
  unique (id, owner_id, proposal_version),
  unique (id, owner_id, trading_account_id),
  foreign key (trading_account_id, owner_id)
    references public.trading_accounts (id, owner_id) on delete restrict,
  foreign key (
    broker_symbol_id, owner_id, trading_account_id, symbol_specification_version
  ) references public.broker_symbols (
    id, owner_id, trading_account_id, specification_version
  ) on delete restrict,
  foreign key (
    risk_policy_version_id, owner_id, risk_policy_version, trading_account_id
  ) references public.risk_policy_versions (
    id, owner_id, version_label, trading_account_id
  ) on delete restrict,
  foreign key (market_snapshot_id, owner_id, trading_account_id)
    references public.market_snapshots (id, owner_id, trading_account_id) on delete restrict,
  foreign key (
    feature_snapshot_id, owner_id, trading_account_id, market_snapshot_id
  ) references public.feature_snapshots (
    id, owner_id, trading_account_id, market_snapshot_id
  ) on delete restrict
);

create index trade_proposals_owner_status_time_idx
  on public.trade_proposals (owner_id, status, created_at desc);
create index trade_proposals_account_idx
  on public.trade_proposals (trading_account_id, created_at desc);

create table public.risk_checks (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trade_proposal_id uuid not null,
  proposal_version integer not null check (proposal_version > 0),
  key text not null,
  label_th text not null,
  label_en text not null,
  state public.risk_check_state not null,
  actual text not null,
  limit_value text,
  hard boolean not null,
  explanation text,
  ordinal smallint not null check (ordinal >= 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (pg_catalog.btrim(key) <> '' and pg_catalog.length(key) <= 160),
  check (pg_catalog.btrim(label_th) <> '' and pg_catalog.length(label_th) <= 160),
  check (pg_catalog.btrim(label_en) <> '' and pg_catalog.length(label_en) <= 160),
  check (pg_catalog.btrim(actual) <> '' and pg_catalog.length(actual) <= 512),
  check (
    limit_value is null
    or (pg_catalog.btrim(limit_value) <> '' and pg_catalog.length(limit_value) <= 512)
  ),
  check (
    explanation is null
    or (pg_catalog.btrim(explanation) <> '' and pg_catalog.length(explanation) <= 512)
  ),
  unique (id, owner_id),
  unique (trade_proposal_id, proposal_version, key),
  foreign key (trade_proposal_id, owner_id, proposal_version)
    references public.trade_proposals (id, owner_id, proposal_version) on delete cascade
);

create index risk_checks_owner_proposal_idx
  on public.risk_checks (owner_id, trade_proposal_id, ordinal);

create table public.trade_decisions (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  owner_id uuid not null,
  trade_proposal_id uuid not null,
  proposal_version integer not null check (proposal_version > 0),
  decision public.trade_decision_kind not null,
  reason text,
  command_id uuid not null,
  decided_by uuid not null,
  decided_at timestamptz not null default pg_catalog.clock_timestamp(),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  check (
    (decision = 'approve' and reason is null)
    or
    (decision = 'reject' and reason is not null and pg_catalog.btrim(reason) <> '')
  ),
  check (decided_by = owner_id),
  check (reason is null or pg_catalog.length(reason) <= 160),
  unique (id, owner_id),
  unique (trade_proposal_id, proposal_version),
  unique (command_id),
  foreign key (trade_proposal_id, owner_id, proposal_version)
    references public.trade_proposals (id, owner_id, proposal_version) on delete restrict,
  foreign key (decided_by) references public.profiles (id) on delete restrict
);

create index trade_decisions_owner_time_idx
  on public.trade_decisions (owner_id, decided_at desc);

-- PostgreSQL numeric admits NaN and infinities. Shared Zod/Pydantic contracts
-- require finite values, so every persisted numeric field is checked here in
-- addition to its business bound.
alter table public.trading_accounts add constraint trading_accounts_numeric_finite
  check (private.numeric_is_finite(maximum_permitted_volume));
alter table public.broker_symbols add constraint broker_symbols_numeric_finite
  check (
    private.numeric_is_finite(contract_size)
    and private.numeric_is_finite(point_size)
    and private.numeric_is_finite(tick_size)
    and (tick_value is null or private.numeric_is_finite(tick_value))
    and private.numeric_is_finite(minimum_volume)
    and private.numeric_is_finite(maximum_volume)
    and private.numeric_is_finite(volume_step)
  );
alter table public.risk_policy_versions add constraint risk_policy_versions_numeric_finite
  check (
    private.numeric_is_finite(maximum_permitted_volume)
    and private.numeric_is_finite(risk_per_trade_pct)
    and private.numeric_is_finite(daily_loss_limit_pct)
    and private.numeric_is_finite(weekly_loss_limit_pct)
    and private.numeric_is_finite(maximum_drawdown_pct)
    and private.numeric_is_finite(minimum_risk_reward)
    and private.numeric_is_finite(maximum_spread_points)
    and private.numeric_is_finite(spread_warning_points)
    and private.numeric_is_finite(entry_tolerance_points)
    and private.numeric_is_finite(maximum_slippage_points)
  );
alter table public.market_snapshots add constraint market_snapshots_numeric_finite
  check (
    private.numeric_is_finite(bid)
    and private.numeric_is_finite(ask)
    and private.numeric_is_finite(spread_points)
    and private.numeric_is_finite(atr)
  );
alter table public.trade_proposals add constraint trade_proposals_numeric_finite
  check (
    private.numeric_is_finite(entry_price)
    and private.numeric_is_finite(stop_loss_price)
    and private.numeric_is_finite(take_profit_price)
    and private.numeric_is_finite(calculated_volume)
    and (requested_volume is null or private.numeric_is_finite(requested_volume))
    and (approved_volume is null or private.numeric_is_finite(approved_volume))
    and private.numeric_is_finite(maximum_permitted_volume)
    and private.numeric_is_finite(risk_amount)
    and private.numeric_is_finite(risk_pct)
    and private.numeric_is_finite(risk_reward)
  );

comment on table public.risk_policy_versions is
  'Immutable policy snapshots. A change request creates a new row; only secured Worker acknowledgement may move risk_policies.active_version_id.';
comment on table public.market_snapshots is
  'Schema binding only in Milestone 1; no market-data ingestion is implemented.';
comment on table public.feature_snapshots is
  'Schema binding only in Milestone 1; no strategy or feature pipeline is implemented.';
