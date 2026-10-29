-- GeoResponse proactive state, PostgreSQL 15+
-- The demo uses SQLite; this is the production schema. Every payload is JSONB
-- plus indexed columns for the queries the scheduler and inbox actually run.

CREATE TABLE IF NOT EXISTS scopes (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS scopes_tenant_status ON scopes (tenant, status);

CREATE TABLE IF NOT EXISTS plans (
  scope_id TEXT PRIMARY KEY REFERENCES scopes(id) ON DELETE CASCADE,
  payload JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS acquisitions (
  id TEXT PRIMARY KEY,
  scope_id TEXT NOT NULL REFERENCES scopes(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  scheduled_for TIMESTAMPTZ NOT NULL,
  idempotency_key TEXT UNIQUE NOT NULL,
  payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS acquisitions_scope_time ON acquisitions (scope_id, scheduled_for DESC);
CREATE INDEX IF NOT EXISTS acquisitions_due ON acquisitions (status, scheduled_for);

CREATE TABLE IF NOT EXISTS baselines (
  scope_id TEXT NOT NULL REFERENCES scopes(id) ON DELETE CASCADE,
  metric TEXT NOT NULL,
  payload JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (scope_id, metric)
);

CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  scope_id TEXT NOT NULL REFERENCES scopes(id) ON DELETE CASCADE,
  incident_id TEXT,
  status TEXT NOT NULL,
  severity TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  sla_due TIMESTAMPTZ,
  payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS alerts_tenant_status_time ON alerts (tenant, status, created_at DESC);
CREATE INDEX IF NOT EXISTS alerts_scope_status ON alerts (scope_id, status);
CREATE INDEX IF NOT EXISTS alerts_incident ON alerts (incident_id);

CREATE TABLE IF NOT EXISTS incidents (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  scope_id TEXT NOT NULL REFERENCES scopes(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  opened_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS incidents_tenant_status ON incidents (tenant, status, opened_at DESC);

CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  alert_id TEXT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  channel TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  next_attempt_at TIMESTAMPTZ,
  payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS notifications_due ON notifications (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS notifications_tenant ON notifications (tenant, created_at DESC);

CREATE TABLE IF NOT EXISTS models (
  name TEXT PRIMARY KEY,
  payload JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS preferences (
  tenant TEXT PRIMARY KEY,
  payload JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS costs (
  id TEXT PRIMARY KEY,
  tenant TEXT NOT NULL,
  scope_id TEXT,
  kind TEXT NOT NULL,
  amount_eur NUMERIC(12,2) NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  payload JSONB
);
CREATE INDEX IF NOT EXISTS costs_tenant_time ON costs (tenant, occurred_at DESC);

CREATE TABLE IF NOT EXISTS validations (
  id BIGSERIAL PRIMARY KEY,
  scope_id TEXT NOT NULL REFERENCES scopes(id) ON DELETE CASCADE,
  analyst TEXT NOT NULL,
  alert_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  queue TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  available_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  error TEXT
);
CREATE INDEX IF NOT EXISTS jobs_queue_due ON jobs (queue, status, available_at);

CREATE TABLE IF NOT EXISTS audit (
  id BIGSERIAL PRIMARY KEY,
  tenant TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  action TEXT NOT NULL,
  alert_id TEXT,
  actor TEXT,
  detail JSONB,
  prev TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_tenant_time ON audit (tenant, occurred_at DESC);
