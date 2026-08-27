-- Aurum Console deterministic LOCAL-DEVELOPMENT seed.
-- All identifiers and records are fictional. This file contains no password,
-- Supabase secret, Worker credential, MT5 credential, or LINE credential.

insert into auth.users (
  instance_id,
  id,
  aud,
  role,
  email,
  encrypted_password,
  email_confirmed_at,
  raw_app_meta_data,
  raw_user_meta_data,
  created_at,
  updated_at,
  confirmation_token,
  email_change,
  email_change_token_new,
  recovery_token
)
values (
  '00000000-0000-0000-0000-000000000000',
  '00000000-0000-4000-8000-000000000201',
  'authenticated',
  'authenticated',
  'owner@aurum.invalid',
  null,
  '2026-08-26T00:00:00Z',
  '{"provider":"development_seed","providers":[]}'::jsonb,
  '{"developmentOnly":true,"fictional":true}'::jsonb,
  '2026-08-26T00:00:00Z',
  '2026-08-26T00:00:00Z',
  '',
  '',
  '',
  ''
)
on conflict (id) do nothing;

insert into public.profiles (
  id,
  display_name,
  locale,
  timezone,
  created_at,
  updated_at
)
values (
  '00000000-0000-4000-8000-000000000201',
  'Aurum Development Owner',
  'th',
  'Asia/Bangkok',
  '2026-08-26T00:00:00Z',
  '2026-08-26T00:00:00Z'
)
on conflict (id) do nothing;

insert into public.trading_accounts (
  id,
  owner_id,
  environment,
  account_type,
  verification_state,
  broker_account_reference,
  broker_server,
  account_currency,
  maximum_permitted_volume,
  maximum_open_positions,
  stop_loss_required,
  created_at,
  updated_at
)
values (
  '00000000-0000-4000-8000-000000000301',
  '00000000-0000-4000-8000-000000000201',
  'DEMO_ONLY',
  'demo',
  'verified_demo',
  'DEVELOPMENT-DEMO-ACCOUNT',
  'DEMO-FIXTURE-SERVER',
  'USD',
  0.01,
  1,
  true,
  '2026-08-26T00:00:00Z',
  '2026-08-26T00:00:00Z'
)
on conflict (id) do nothing;

insert into public.broker_symbols (
  id,
  owner_id,
  trading_account_id,
  canonical_symbol,
  broker_symbol,
  specification_version,
  account_currency,
  contract_size,
  digits,
  point_size,
  tick_size,
  tick_value,
  minimum_volume,
  maximum_volume,
  volume_step,
  stop_level,
  calculation_mode,
  fetched_at,
  created_at
)
values (
  '00000000-0000-4000-8000-000000000311',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301',
  'XAUUSD',
  'XAUUSD',
  'development-spec-v1',
  'USD',
  100,
  2,
  0.01,
  0.01,
  1.00,
  0.01,
  100.00,
  0.01,
  10,
  'development-placeholder',
  '2026-08-26T00:00:00Z',
  '2026-08-26T00:00:00Z'
)
on conflict (id) do nothing;

insert into public.trading_modes (
  id,
  owner_id,
  trading_account_id,
  mode,
  system_state,
  version,
  created_at,
  updated_at
)
values (
  '00000000-0000-4000-8000-000000000321',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301',
  'shadow',
  'running',
  1,
  '2026-08-26T00:00:00Z',
  '2026-08-26T00:00:00Z'
)
on conflict (id) do nothing;

insert into public.risk_policies (
  id,
  owner_id,
  trading_account_id,
  policy_key,
  resource_version,
  created_at,
  updated_at
)
values (
  '00000000-0000-4000-8000-000000000331',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000301',
  'demo-risk-policy',
  1,
  '2026-08-26T00:00:00Z',
  '2026-08-26T00:00:00Z'
)
on conflict (id) do nothing;

insert into public.risk_policy_versions (
  id,
  owner_id,
  risk_policy_id,
  trading_account_id,
  version,
  version_label,
  environment,
  canonical_symbol,
  maximum_permitted_volume,
  maximum_open_positions,
  stop_loss_required,
  martingale_allowed,
  grid_trading_allowed,
  averaging_down_allowed,
  loss_based_volume_increase_allowed,
  risk_per_trade_pct,
  daily_loss_limit_pct,
  weekly_loss_limit_pct,
  maximum_drawdown_pct,
  maximum_trades_per_day,
  minimum_risk_reward,
  stale_data_max_age_seconds,
  maximum_spread_points,
  spread_warning_points,
  news_blackout_minutes,
  proposal_expiry_seconds,
  entry_tolerance_points,
  minimum_sample_size,
  require_calibrated_model,
  maximum_slippage_points,
  automatic_retry_on_broker_reject,
  reason,
  created_by_type,
  created_by,
  created_at
)
values (
  '00000000-0000-4000-8000-000000000332',
  '00000000-0000-4000-8000-000000000201',
  '00000000-0000-4000-8000-000000000331',
  '00000000-0000-4000-8000-000000000301',
  1,
  'demo-risk-policy-v1',
  'DEMO_ONLY',
  'XAUUSD',
  0.01,
  1,
  true,
  false,
  false,
  false,
  false,
  0.25,
  1.00,
  3.00,
  5.00,
  3,
  1.50,
  10,
  3.50,
  2.80,
  15,
  30,
  0.60,
  30,
  false,
  0.50,
  false,
  'Deterministic conservative development-only baseline.',
  'system',
  'development-seed',
  '2026-08-26T00:00:00Z'
)
on conflict (id) do nothing;

update public.risk_policies
set active_version_id = '00000000-0000-4000-8000-000000000332'
where id = '00000000-0000-4000-8000-000000000331'
  and active_version_id is null;

insert into public.system_components (
  id,
  owner_id,
  code,
  label_th,
  plane,
  expected_heartbeat_seconds,
  enabled,
  created_at
)
values
  (
    '00000000-0000-4000-8000-000000000811',
    '00000000-0000-4000-8000-000000000201',
    'control.database',
    'ฐานข้อมูล Control Plane',
    'control_plane',
    null,
    true,
    '2026-08-26T00:00:00Z'
  ),
  (
    '00000000-0000-4000-8000-000000000812',
    '00000000-0000-4000-8000-000000000201',
    'control.auth',
    'การยืนยันตัวตน Control Plane',
    'control_plane',
    null,
    true,
    '2026-08-26T00:00:00Z'
  ),
  (
    '00000000-0000-4000-8000-000000000813',
    '00000000-0000-4000-8000-000000000201',
    'execution.worker',
    'Aurum Worker',
    'execution_plane',
    15,
    true,
    '2026-08-26T00:00:00Z'
  ),
  (
    '00000000-0000-4000-8000-000000000814',
    '00000000-0000-4000-8000-000000000201',
    'execution.mt5_adapter',
    'MT5 Adapter (ยังไม่เชื่อมต่อ)',
    'execution_plane',
    15,
    true,
    '2026-08-26T00:00:00Z'
  ),
  (
    '00000000-0000-4000-8000-000000000815',
    '00000000-0000-4000-8000-000000000201',
    'execution.market_data',
    'ข้อมูลตลาด (ยังไม่เชื่อมต่อ)',
    'execution_plane',
    15,
    true,
    '2026-08-26T00:00:00Z'
  )
on conflict (id) do nothing;

comment on table public.profiles is
  'Seed owner is fictional and local-development only; no login credential is supplied.';
