CREATE TABLE IF NOT EXISTS ingest_runs (
  ingest_id VARCHAR PRIMARY KEY,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  timezone VARCHAR NOT NULL,
  include_temp BOOLEAN NOT NULL,
  codex_path VARCHAR NOT NULL,
  claude_path VARCHAR NOT NULL,
  pricing_mode VARCHAR NOT NULL,
  app_version VARCHAR NOT NULL,
  schema_version INTEGER NOT NULL,
  status VARCHAR NOT NULL,
  notes_json VARCHAR NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS pricing_snapshots (
  snapshot_id VARCHAR NOT NULL,
  provider VARCHAR NOT NULL,
  model VARCHAR NOT NULL,
  checked_at TIMESTAMP NOT NULL,
  freshness_label VARCHAR NOT NULL,
  source_url VARCHAR NOT NULL,
  currency VARCHAR NOT NULL DEFAULT 'USD',
  input_per_million DOUBLE,
  cached_input_per_million DOUBLE,
  output_per_million DOUBLE,
  cache_write_5m_per_million DOUBLE,
  cache_write_1h_per_million DOUBLE,
  cache_read_per_million DOUBLE,
  snapshot_path VARCHAR,
  notes_json VARCHAR NOT NULL DEFAULT '[]',
  PRIMARY KEY (snapshot_id, provider, model)
);

CREATE TABLE IF NOT EXISTS workspaces (
  workspace_id VARCHAR PRIMARY KEY,
  workspace_label VARCHAR NOT NULL,
  cwd VARCHAR NOT NULL,
  repo_root VARCHAR,
  repo_name VARCHAR,
  is_temp BOOLEAN NOT NULL,
  anonymized_label VARCHAR
);

CREATE TABLE IF NOT EXISTS session_facts (
  provider VARCHAR NOT NULL,
  session_id VARCHAR NOT NULL,
  ingest_id VARCHAR NOT NULL,
  source_app VARCHAR NOT NULL,
  raw_path VARCHAR NOT NULL,
  started_at TIMESTAMP NOT NULL,
  local_day DATE NOT NULL,
  local_hour SMALLINT NOT NULL,
  local_weekday VARCHAR NOT NULL,
  workspace_id VARCHAR NOT NULL,
  model VARCHAR NOT NULL,
  model_confidence VARCHAR NOT NULL,
  parse_status VARCHAR NOT NULL,
  user_messages INTEGER NOT NULL DEFAULT 0,
  assistant_messages INTEGER NOT NULL DEFAULT 0,
  reasoning_messages INTEGER NOT NULL DEFAULT 0,
  duration_s DOUBLE,
  has_tools BOOLEAN NOT NULL DEFAULT FALSE,
  has_web BOOLEAN NOT NULL DEFAULT FALSE,
  has_task_agent BOOLEAN NOT NULL DEFAULT FALSE,
  has_subagent BOOLEAN NOT NULL DEFAULT FALSE,
  has_edits BOOLEAN NOT NULL DEFAULT FALSE,
  has_mcp BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (provider, session_id)
);

CREATE TABLE IF NOT EXISTS session_usage (
  provider VARCHAR NOT NULL,
  session_id VARCHAR NOT NULL,
  input_tokens BIGINT NOT NULL DEFAULT 0,
  output_tokens BIGINT NOT NULL DEFAULT 0,
  total_tokens BIGINT NOT NULL DEFAULT 0,
  cached_input_tokens BIGINT NOT NULL DEFAULT 0,
  reasoning_output_tokens BIGINT NOT NULL DEFAULT 0,
  cache_creation_input_tokens BIGINT NOT NULL DEFAULT 0,
  cache_creation_5m_tokens BIGINT NOT NULL DEFAULT 0,
  cache_creation_1h_tokens BIGINT NOT NULL DEFAULT 0,
  cache_read_tokens BIGINT NOT NULL DEFAULT 0,
  token_coverage VARCHAR NOT NULL,
  PRIMARY KEY (provider, session_id)
);

CREATE TABLE IF NOT EXISTS session_estimates (
  provider VARCHAR NOT NULL,
  session_id VARCHAR NOT NULL,
  snapshot_id VARCHAR,
  estimation_method VARCHAR NOT NULL,
  estimate_label VARCHAR NOT NULL,
  pricing_freshness VARCHAR NOT NULL,
  estimated_cost_usd DOUBLE,
  estimated_cache_savings_usd DOUBLE,
  excluded BOOLEAN NOT NULL DEFAULT FALSE,
  exclusion_reason VARCHAR,
  assumption_flags_json VARCHAR NOT NULL DEFAULT '[]',
  PRIMARY KEY (provider, session_id)
);
