CREATE OR REPLACE VIEW provider_rollups AS
SELECT
  f.provider,
  COUNT(*) AS sessions,
  SUM(u.input_tokens) AS input_tokens,
  SUM(u.output_tokens) AS output_tokens,
  SUM(u.total_tokens) AS total_tokens,
  SUM(COALESCE(e.estimated_cost_usd, 0)) AS estimated_cost_usd,
  SUM(COALESCE(e.estimated_cache_savings_usd, 0)) AS estimated_cache_savings_usd
FROM session_facts f
JOIN session_usage u
  ON u.provider = f.provider
 AND u.session_id = f.session_id
LEFT JOIN session_estimates e
  ON e.provider = f.provider
 AND e.session_id = f.session_id
GROUP BY f.provider;

CREATE OR REPLACE VIEW daily_rollups AS
SELECT
  f.local_day AS day,
  f.provider,
  f.workspace_id,
  COUNT(*) AS sessions,
  SUM(u.input_tokens) AS input_tokens,
  SUM(u.output_tokens) AS output_tokens,
  SUM(u.total_tokens) AS total_tokens,
  SUM(u.cached_input_tokens + u.cache_read_tokens) AS cached_tokens,
  SUM(COALESCE(e.estimated_cost_usd, 0)) AS estimated_cost_usd,
  AVG(
    CASE
      WHEN e.estimate_label = 'Direct' THEN 1.0
      WHEN e.estimate_label = 'Approx' THEN 0.6
      WHEN e.estimate_label = 'Partial' THEN 0.3
      ELSE 0.0
    END
  ) AS coverage_ratio,
  SUM(CASE WHEN f.has_task_agent OR f.has_subagent THEN 1 ELSE 0 END) AS agent_sessions,
  SUM(CASE WHEN f.has_web THEN 1 ELSE 0 END) AS web_sessions,
  SUM(CASE WHEN f.has_edits THEN 1 ELSE 0 END) AS edit_sessions
FROM session_facts f
JOIN session_usage u
  ON u.provider = f.provider
 AND u.session_id = f.session_id
LEFT JOIN session_estimates e
  ON e.provider = f.provider
 AND e.session_id = f.session_id
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW workspace_rollups AS
SELECT
  f.workspace_id,
  w.workspace_label,
  COALESCE(w.anonymized_label, w.workspace_label) AS display_workspace_label,
  w.is_temp,
  f.provider,
  COUNT(*) AS sessions,
  MAX(f.started_at) AS last_active_at,
  SUM(u.input_tokens) AS input_tokens,
  SUM(u.output_tokens) AS output_tokens,
  SUM(u.total_tokens) AS total_tokens,
  SUM(u.cached_input_tokens + u.cache_read_tokens) AS cached_tokens,
  SUM(COALESCE(e.estimated_cost_usd, 0)) AS estimated_cost_usd,
  SUM(COALESCE(e.estimated_cache_savings_usd, 0)) AS estimated_cache_savings_usd
FROM session_facts f
JOIN workspaces w
  ON w.workspace_id = f.workspace_id
JOIN session_usage u
  ON u.provider = f.provider
 AND u.session_id = f.session_id
LEFT JOIN session_estimates e
  ON e.provider = f.provider
 AND e.session_id = f.session_id
GROUP BY
  f.workspace_id,
  w.workspace_label,
  COALESCE(w.anonymized_label, w.workspace_label),
  w.is_temp,
  f.provider;

CREATE OR REPLACE VIEW session_summary AS
SELECT
  f.provider,
  f.session_id,
  f.ingest_id,
  f.source_app,
  f.raw_path,
  f.started_at,
  f.local_day,
  f.local_hour,
  f.local_weekday,
  f.workspace_id,
  w.workspace_label,
  COALESCE(w.anonymized_label, w.workspace_label) AS display_workspace_label,
  w.cwd,
  w.repo_root,
  w.repo_name,
  w.is_temp,
  f.model,
  f.model_confidence,
  f.parse_status,
  f.user_messages,
  f.assistant_messages,
  f.reasoning_messages,
  f.duration_s,
  f.has_tools,
  f.has_web,
  f.has_task_agent,
  f.has_subagent,
  f.has_edits,
  f.has_mcp,
  u.input_tokens,
  u.output_tokens,
  u.total_tokens,
  u.cached_input_tokens,
  u.reasoning_output_tokens,
  u.cache_creation_input_tokens,
  u.cache_creation_5m_tokens,
  u.cache_creation_1h_tokens,
  u.cache_read_tokens,
  u.token_coverage,
  e.snapshot_id,
  e.estimation_method,
  e.estimate_label,
  e.pricing_freshness,
  e.estimated_cost_usd,
  e.estimated_cache_savings_usd,
  e.excluded,
  e.exclusion_reason,
  e.assumption_flags_json
FROM session_facts f
JOIN workspaces w
  ON w.workspace_id = f.workspace_id
JOIN session_usage u
  ON u.provider = f.provider
 AND u.session_id = f.session_id
LEFT JOIN session_estimates e
  ON e.provider = f.provider
 AND e.session_id = f.session_id;

CREATE OR REPLACE VIEW model_rollups AS
SELECT
  f.provider,
  f.model,
  COUNT(*) AS sessions,
  SUM(u.total_tokens) AS total_tokens,
  SUM(COALESCE(e.estimated_cost_usd, 0)) AS estimated_cost_usd
FROM session_facts f
JOIN session_usage u
  ON u.provider = f.provider
 AND u.session_id = f.session_id
LEFT JOIN session_estimates e
  ON e.provider = f.provider
 AND e.session_id = f.session_id
GROUP BY f.provider, f.model;
