-- Owner: M2. All 7 tables (docs/FraudArena_24h_Implementation_Plan.pdf section 13),
-- frozen at H1 per docs/TIMELINE.md section 2.

CREATE TABLE IF NOT EXISTS rule_versions(
  version TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now(),
  rules_json JSONB NOT NULL,
  source TEXT
);

CREATE TABLE IF NOT EXISTS events(
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT,
  ts BIGINT,
  account TEXT,
  type TEXT,
  amount BIGINT,          -- integer paise
  payee TEXT,
  device TEXT,
  action TEXT,
  rule_id TEXT,
  version TEXT,
  features JSONB
);

CREATE TABLE IF NOT EXISTS rounds(
  id TEXT PRIMARY KEY,
  playbook TEXT NOT NULL,
  started_by TEXT,
  state TEXT NOT NULL,     -- SELECT|PLAN|SEARCH|EVALUATE|DEFEND|VERIFY|AWAIT_APPROVAL|DONE
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plans(
  plan_id TEXT PRIMARY KEY,
  round_id TEXT REFERENCES rounds(id),
  playbook TEXT NOT NULL,
  seed INT NOT NULL,
  params_json JSONB NOT NULL,
  steps_json JSONB NOT NULL,
  loss_through BIGINT,
  missed_step INT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS patches(
  id TEXT PRIMARY KEY,
  round_id TEXT REFERENCES rounds(id),
  rule_json JSONB NOT NULL,
  rationale TEXT,
  gate_results_json JSONB,
  status TEXT NOT NULL,    -- PROPOSED|VERIFIED|REJECTED|AWAITING_APPROVAL|ACTIVE
  proposed_by TEXT,
  checker TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  decided_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ledger(
  seq BIGSERIAL PRIMARY KEY,
  ts BIGINT NOT NULL,
  action TEXT NOT NULL,
  payload JSONB NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,
  sig TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics(
  id BIGSERIAL PRIMARY KEY,
  version TEXT NOT NULL,
  playbook TEXT,
  wcel BIGINT,
  hold_rate DOUBLE PRECISION,
  hold_rate_lo DOUBLE PRECISION,
  hold_rate_hi DOUBLE PRECISION,
  detection_delay_s BIGINT,
  recorded_at TIMESTAMPTZ DEFAULT now()
);
