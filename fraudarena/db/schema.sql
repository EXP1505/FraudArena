-- Owner: M2. Phase 1 subset; later phases add plans, patches, ledger, metrics.
CREATE TABLE IF NOT EXISTS rule_versions(
  version INT PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT now(),
  rules_json JSONB NOT NULL, source TEXT);
CREATE TABLE IF NOT EXISTS events(
  id BIGSERIAL PRIMARY KEY, run_id TEXT, ts BIGINT, account TEXT,
  type TEXT, amount NUMERIC, payee TEXT, device TEXT,
  action TEXT, rule_id TEXT, version INT, features JSONB);
