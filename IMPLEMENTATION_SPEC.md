# Local AI Usage Dashboard v1 Implementation Spec

This file is the implementation reference for phases 1 and 2.

- `README.md` is the operator guide
- `PHASE3_PLAN.md` is the next-phase planning document

## Goal

Build a local, open-source dashboard for Codex/OpenAI and Claude that answers:

- Where did AI usage happen?
- What did it likely cost?
- Which workspaces drove that usage?
- What kind of work was it?

This is an estimate-first local tool. It is not a billing product, not a productivity score, and not a generic BI system.

## Product Boundaries

### In scope

- Codex/OpenAI local session ingestion
- Claude local session ingestion
- Estimated cost from local usage plus official pricing
- Workspace concentration
- Model mix
- Cache usage and cache savings estimate
- Work-shape flags
- Local web UI
- Static snapshot export

### Out of scope

- Copilot
- Team or multi-user aggregation
- Transcript browsing
- Commits, pushes, lines changed, or productivity scores
- Background daemon or continuous sync
- React/Vite frontend
- Desktop packaging

## Product Shape

### Pages

1. `Overview`
2. `Workspaces`
3. `Methodology`

### Top-level metrics

- Estimated cost
- Sessions
- Total tokens
- Cache savings estimate
- Provider mix
- Model mix
- Workspace mix
- Active days
- Work-shape shares

### Trust labels

- `Direct`: model and token classes are present
- `Approx`: one or more estimation assumptions were required
- `Partial`: some sessions were excluded from the estimate

### Pricing freshness labels

- `Fresh`: official pricing was refreshed on this run
- `Snapshot`: last known pricing snapshot was used
- `Unavailable`: no defensible pricing source exists

## Architecture

### Stack

- Python
- DuckDB
- FastAPI
- Jinja templates
- Apache ECharts
- Small vanilla JS

### Design rules

- Keep one language in the application codepath
- Keep the database local and inspectable
- Keep UI state in query params
- Keep charts as supporting evidence, not the product itself
- Prefer SQL views over extra Python aggregation layers when possible

## Target File Tree

```text
dashboard/
  __init__.py
  cli.py
  app.py
  config.py
  db.py
  ingest.py
  estimates.py
  generate.py
  doctor.py
  queries.py
  routes.py
  providers/
    __init__.py
    openai_local.py
    claude_local.py
  templates/
    base.html
    overview.html
    workspaces.html
    methodology.html
    partials/
      filter_bar.html
      trust_banner.html
  static/
    dashboard.css
    dashboard.js
  sql/
    schema.sql
    views.sql
tests/
  test_dashboard_estimates.py
  test_dashboard_ingest.py
  test_dashboard_openai_local.py
  test_dashboard_phase1.py
  test_queries.py
  test_routes.py
  test_doctor.py
  test_usage_report.py
```

### Current repo migration stance

- Keep `usage_report_common.py` and `usage_report_providers.py` as the source of truth during phase 1
- Build the new app under `dashboard/`
- Delete or retire old renderer code only after parity is proven

### Current repo mapping

Use the current files as the migration boundary instead of rewriting everything at once.

- `codex_usage_report.py`: keep as the temporary orchestration reference while the new CLI is built
- `usage_report_common.py`: keep shared formatting, path, timezone, and snapshot helpers where useful
- `usage_report_providers.py`: keep provider discovery, parsing, pricing, and current aggregate rules as phase-1 source of truth
- `usage_report_render.py`: treat as legacy output only; do not extend it further
- `dashboard/cli.py`: new command entrypoint for ingest, generate, doctor, and serve wiring
- `dashboard/generate.py`: static snapshot export from DuckDB
- `dashboard/doctor.py`: local health and coverage summary
- `tests/test_usage_report.py`: keep existing regression coverage and add parity tests beside it

The first architectural change is data normalization into DuckDB, not a wholesale parser rewrite.

Current status:

- phase 1 is complete
- phase 2 is complete for the core command and web wiring
- `dashboard/cli.py`, `dashboard/app.py`, `dashboard/routes.py`, `dashboard/queries.py`, `dashboard/generate.py`, and `dashboard/doctor.py` are now the main phase-2 surfaces
- the remaining work is polish and parity hardening, not new core architecture

Related docs:

- `README.md`: clone-and-run entry point
- `PHASE3_PLAN.md`: polish and release-hardening plan
- `RELEASE_CHECKLIST.md`: pre-release verification steps

## Module Responsibilities

`dashboard/cli.py`

- parse subcommands
- resolve paths and timezone
- dispatch to ingest, serve, generate, and doctor

`dashboard/app.py`

- create the FastAPI app
- register routes and static assets
- attach template and database dependencies

`dashboard/config.py`

- centralize default paths
- expose schema version and app version
- hold query default values like last-30-days and include-temp default

`dashboard/db.py`

- own database connection helpers
- apply schema and views
- expose transaction helpers for staged ingest

`dashboard/ingest.py`

- coordinate one ingest run end to end
- call provider adapters
- write normalized rows
- rebuild derived views
- write metadata output

`dashboard/estimates.py`

- compute OpenAI/Codex and Claude estimates
- attach estimate labels, pricing freshness, and assumption flags
- reject unsupported models cleanly

`dashboard/queries.py`

- hold all page query functions
- keep SQL close to return shapes
- return plain dict/list structures ready for templates

`dashboard/routes.py`

- map GET routes to query functions and templates
- keep route handlers thin

`dashboard/providers/openai_local.py`

- adapt current Codex/OpenAI discovery into normalized rows
- derive work-shape flags from local events

`dashboard/providers/claude_local.py`

- adapt current Claude session-meta and transcript enrichment into normalized rows
- preserve partial-parse recovery and model inference behavior

## Local Storage Layout

Store all generated artifacts under repo-local `.dashboard/`.

```text
.dashboard/
  dashboard.duckdb
  pricing_snapshot.json
  metadata.json
  snapshots/
    latest/
      index.html
      overview.html
      workspaces.html
      methodology.html
      static/
        dashboard.css
        dashboard.js
```

### Storage rules

- `dashboard.duckdb` is the primary working database
- `pricing_snapshot.json` is a human-readable fallback and diffable artifact
- `metadata.json` stores app version and most recent ingest summary
- static snapshots are disposable outputs, not source of truth
- anonymized snapshots are the public-sharing form of the product and must not include raw workspace labels or path-like source metadata

## CLI Contract

### `dashboard ingest`

Reads local logs, refreshes pricing if possible, writes normalized rows, and refreshes derived views.

```text
dashboard ingest
  [--codex-dir PATH]
  [--claude-dir PATH]
  [--timezone IANA_TZ]
  [--db PATH]
  [--include-temp]
  [--pricing-mode fresh|snapshot|auto]
```

Behavior:

- `auto` tries a live refresh first, then falls back to the last snapshot
- `fresh` fails pricing freshness if the live refresh fails
- `snapshot` skips live pricing refresh and uses the last snapshot only
- data rows are always ingested, even if pricing is unavailable

### `dashboard serve`

Starts the local FastAPI app.

```text
dashboard serve
  [--db PATH]
  [--host HOST]
  [--port PORT]
```

### `dashboard generate`

Renders a static snapshot from DuckDB.

```text
dashboard generate
  [--db PATH]
  [--output-dir PATH]
  [--anonymize-workspaces]
```

Behavior:

- `--anonymize-workspaces` must produce a commit-safe export with anonymized workspace labels and redacted path-like metadata

### `dashboard doctor`

Checks source paths, parse coverage, unsupported models, and pricing freshness.

```text
dashboard doctor
  [--codex-dir PATH]
  [--claude-dir PATH]
  [--db PATH]
```

Doctor output should include:

- source path presence
- session counts discovered
- parse failures and partial parses
- unsupported models
- pricing freshness state
- excluded sessions from cost estimation

## DuckDB Schema

### Base tables

```sql
CREATE TABLE IF NOT EXISTS ingest_runs (
  ingest_id VARCHAR PRIMARY KEY,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  timezone VARCHAR NOT NULL,
  include_temp BOOLEAN NOT NULL,
  codex_path VARCHAR NOT NULL,
  claude_path VARCHAR NOT NULL,
  pricing_mode VARCHAR NOT NULL,
  app_version VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_snapshots (
  snapshot_id VARCHAR NOT NULL,
  provider VARCHAR NOT NULL,
  model VARCHAR NOT NULL,
  checked_at TIMESTAMP NOT NULL,
  freshness_label VARCHAR NOT NULL,
  source_url VARCHAR NOT NULL,
  input_per_million DOUBLE,
  cached_input_per_million DOUBLE,
  output_per_million DOUBLE,
  cache_write_5m_per_million DOUBLE,
  cache_write_1h_per_million DOUBLE,
  cache_read_per_million DOUBLE,
  notes_json JSON,
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
  session_id VARCHAR PRIMARY KEY,
  ingest_id VARCHAR NOT NULL,
  provider VARCHAR NOT NULL,
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
  has_mcp BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS session_usage (
  session_id VARCHAR PRIMARY KEY,
  input_tokens BIGINT NOT NULL DEFAULT 0,
  output_tokens BIGINT NOT NULL DEFAULT 0,
  total_tokens BIGINT NOT NULL DEFAULT 0,
  cached_input_tokens BIGINT NOT NULL DEFAULT 0,
  reasoning_output_tokens BIGINT NOT NULL DEFAULT 0,
  cache_creation_input_tokens BIGINT NOT NULL DEFAULT 0,
  cache_creation_5m_tokens BIGINT NOT NULL DEFAULT 0,
  cache_creation_1h_tokens BIGINT NOT NULL DEFAULT 0,
  cache_read_tokens BIGINT NOT NULL DEFAULT 0,
  token_coverage VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS session_estimates (
  session_id VARCHAR PRIMARY KEY,
  snapshot_id VARCHAR,
  estimation_method VARCHAR NOT NULL,
  estimate_label VARCHAR NOT NULL,
  pricing_freshness VARCHAR NOT NULL,
  estimated_cost_usd DOUBLE,
  estimated_cache_savings_usd DOUBLE,
  excluded BOOLEAN NOT NULL DEFAULT FALSE,
  exclusion_reason VARCHAR,
  assumption_flags_json JSON
);
```

### Derived views

```sql
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
JOIN session_usage u USING (session_id)
LEFT JOIN session_estimates e USING (session_id)
GROUP BY 1;

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
  AVG(CASE WHEN e.estimate_label = 'Direct' THEN 1.0
           WHEN e.estimate_label = 'Approx' THEN 0.6
           WHEN e.estimate_label = 'Partial' THEN 0.3
           ELSE 0.0 END) AS coverage_ratio,
  SUM(CASE WHEN f.has_task_agent OR f.has_subagent THEN 1 ELSE 0 END) AS agent_sessions,
  SUM(CASE WHEN f.has_web THEN 1 ELSE 0 END) AS web_sessions,
  SUM(CASE WHEN f.has_edits THEN 1 ELSE 0 END) AS edit_sessions
FROM session_facts f
JOIN session_usage u USING (session_id)
LEFT JOIN session_estimates e USING (session_id)
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW workspace_rollups AS
SELECT
  f.workspace_id,
  w.workspace_label,
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
JOIN workspaces w ON w.workspace_id = f.workspace_id
JOIN session_usage u USING (session_id)
LEFT JOIN session_estimates e USING (session_id)
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW model_rollups AS
SELECT
  f.provider,
  f.model,
  COUNT(*) AS sessions,
  SUM(u.total_tokens) AS total_tokens,
  SUM(COALESCE(e.estimated_cost_usd, 0)) AS estimated_cost_usd
FROM session_facts f
JOIN session_usage u USING (session_id)
LEFT JOIN session_estimates e USING (session_id)
GROUP BY 1, 2;
```

## Ingestion Flow

### Ingest steps

1. Resolve source paths and timezone
2. Create an `ingest_runs` row
3. Discover Codex/OpenAI sessions
4. Discover Claude sessions
5. Normalize workspaces
6. Refresh pricing or load the last snapshot
7. Write `session_facts`
8. Write `session_usage`
9. Write `session_estimates`
10. Refresh derived views
11. Write `.dashboard/metadata.json`
12. Mark ingest complete

### Provider ingestion modules

`dashboard/providers/openai_local.py`

- wrap current Codex/OpenAI discovery code
- produce normalized session rows plus work-shape flags
- preserve current temp-workspace behavior

`dashboard/providers/claude_local.py`

- wrap current Claude discovery and enrichment code
- preserve transcript enrichment behavior
- preserve partial-parse recovery behavior

## Estimation Policy

### OpenAI / Codex

Formula:

```text
uncached_input = max(input_tokens - cached_input_tokens, 0)
estimated_cost =
  (uncached_input * input_rate
   + cached_input_tokens * cached_rate
   + output_tokens * output_rate) / 1_000_000
```

Cache savings:

```text
baseline_cost =
  (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
estimated_cache_savings = baseline_cost - estimated_cost
```

Rules:

- use official published standard rates
- if long-context or special tier cannot be reconstructed, do not create a second headline estimate
- attach `Approx` and an assumption flag instead

### Claude

Formula:

```text
estimated_cost =
  (input_tokens * input_rate
   + cache_creation_5m_tokens * cache_write_5m_rate
   + cache_creation_1h_tokens * cache_write_1h_rate
   + cache_read_tokens * cache_read_rate
   + output_tokens * output_rate) / 1_000_000
```

Rules:

- if only aggregate cache creation exists, allocate it to `5m` and mark `Approx`
- if model is unknown, exclude from estimate
- do not guess missing token classes

### Estimate labels

- `Direct`: model and all required token classes are present
- `Approx`: one explicit fallback assumption was applied
- `Partial`: some sessions in the filtered set were excluded

### Pricing behavior

- if live refresh succeeds, mark `Fresh`
- if live refresh fails but a snapshot exists, mark `Snapshot`
- if no pricing source exists, set estimate to excluded

## FastAPI App Structure

### Route map

- `GET /` -> overview page
- `GET /workspaces` -> workspaces page
- `GET /methodology` -> methodology page
- `GET /healthz` -> simple app health
- `GET /static/...` -> CSS and JS assets

No JSON API routes in v1 unless a concrete page needs them. Prefer server-rendered HTML plus embedded chart payloads.

### Query model

Shared query params across pages:

- `from=YYYY-MM-DD`
- `to=YYYY-MM-DD`
- `provider=openai|claude|all`
- `workspace=<workspace_id>`
- `model=<model>`
- `include_temp=0|1`
- `sort=<column>`
- `dir=asc|desc`
- `metric=cost|tokens|sessions`

Defaults:

- last 30 days
- `provider=all`
- `include_temp=0`
- `metric=cost`

### Template breakdown

`base.html`

- page shell
- nav
- shared filter bar slot
- shared trust banner slot

`partials/filter_bar.html`

- global filter form
- all filters submit as GET params

`partials/trust_banner.html`

- pricing freshness
- estimate coverage
- exclusions summary

`partials/metric_card.html`

- one title
- one value
- one quiet qualifier

`partials/panel.html`

- title
- subtitle
- body slot

`partials/workspace_table.html`

- ranked workspace table
- selected row highlight

`overview.html`

- headline cards
- cost trend chart
- provider mix chart
- model mix chart
- work-shape chart
- workspace table preview

`workspaces.html`

- full workspace table
- selected workspace detail panel
- selected workspace trend, model mix, provider mix

`methodology.html`

- formulas
- pricing snapshots
- exclusions
- local source paths
- doctor summary

### Page data contracts

`OverviewContext`

- `filters`
- `trust_banner`
- `headline_metrics`
- `cost_trend_series`
- `provider_mix_rows`
- `model_mix_rows`
- `work_shape_rows`
- `workspace_rows`

`WorkspacesContext`

- `filters`
- `trust_banner`
- `workspace_rows`
- `selected_workspace`
- `selected_workspace_metrics`
- `selected_workspace_trend`
- `selected_workspace_model_mix`
- `selected_workspace_provider_mix`
- `selected_workspace_work_shape`

`MethodologyContext`

- `filters`
- `pricing_summary`
- `estimate_rules`
- `coverage_summary`
- `exclusions_summary`
- `doctor_summary`
- `source_paths`

### Chart configuration

- cost trend: line or area chart, daily grain
- provider mix: stacked horizontal bar
- model mix: ranked horizontal bar
- work shape: grouped bar
- selected workspace trend: single line
- cache composition: stacked horizontal bar on overview when data exists

Do not use pies, donuts, gauges, treemaps, or sankeys.

### Minimal JS

`dashboard.js` should do only three things:

1. initialize ECharts from embedded JSON script tags
2. let the workspace table row click set the `workspace` query param
3. allow chart metric toggles between `cost`, `tokens`, and `sessions`

Do not build a client-side router or client-side state store.

## Query Layer

`dashboard/queries.py` should expose plain functions:

- `get_overview_context(db, filters)`
- `get_workspaces_context(db, filters)`
- `get_methodology_context(db, filters)`
- `get_trust_banner(db, filters)`
- `get_filter_options(db, filters)`

Rules:

- keep SQL close to the query functions
- one function per page or panel
- return plain dicts and lists ready for templates
- use early returns when filtered result sets are empty

## Migration Plan

### Phase 1: foundation

- create `dashboard/` package
- create DuckDB schema
- write `dashboard ingest`
- map current provider discovery into normalized rows
- preserve current report outputs for parity checking

### Phase 2: serve mode

- add FastAPI app and templates
- implement overview, workspaces, methodology pages
- embed chart payloads server-side
- add shared filter bar and trust banner

### Phase 3: generate mode

- render static snapshot to `.dashboard/snapshots/latest/`
- support workspace anonymization in generated output

### Phase 4: cleanup

- switch repo entrypoint to new CLI
- retire old one-shot renderer after parity is proven

## Validation And Testing

### Parity checks

Before deleting old code, compare old and new outputs for:

- session counts
- token totals
- top models
- top workspaces
- temp-session exclusion behavior
- pricing freshness behavior

### Tests

`test_ingest_openai.py`

- session discovery mapping
- temp workspace detection
- token fallback behavior
- work-shape flag extraction

`test_ingest_claude.py`

- transcript enrichment
- partial parse recovery
- unknown-model handling
- cache token mapping

`test_estimates.py`

- OpenAI estimate formula
- OpenAI snapshot fallback label
- Claude precise estimate
- Claude cache fallback estimate
- unsupported-model exclusion

`test_queries.py`

- overview query results
- workspace ranking
- selected workspace detail
- empty-state behavior

`test_routes.py`

- page render success
- filter propagation
- trust banner rendering
- methodology page content

`test_doctor.py`

- missing source paths
- stale pricing
- unsupported models
- partial parse counts
- excluded session reporting

### Acceptance criteria

- one command ingests local data into DuckDB
- one command serves the dashboard locally
- one command generates a static snapshot
- estimates render for both Codex/OpenAI and Claude
- trust labels and freshness states are always visible
- workspace ranking is stable and sortable
- no Copilot codepath exists in v1
- old and new totals match on parity fixtures

## Initial Build Order

Implement the rewrite in four small slices:

1. `schema + ingest skeleton`
- add `dashboard/`
- add `sql/schema.sql` and `sql/views.sql`
- add `dashboard ingest` that writes `ingest_runs`, `workspaces`, and raw-normalized session rows

2. `estimates + parity`
- add pricing snapshot persistence under `.dashboard/`
- compute `session_estimates`
- prove parity against the current aggregate output for sessions, tokens, top models, top workspaces, and estimated cost

3. `serve`
- add FastAPI app, templates, shared filter bar, and trust banner
- ship `Overview`, `Workspaces`, and `Methodology`

4. `generate + cleanup`
- render static snapshot from the same query layer
- wire `index.html` or `output/` compatibility if desired
- retire the old renderer only after parity is stable

## Definition Of Done

V1 is done when:

- `dashboard ingest` can rebuild the local database from Codex/OpenAI and Claude sources without manual steps
- `dashboard serve` renders the three pages with working filters and visible trust states
- `dashboard generate` exports a static snapshot from the same query path
- pricing fallback uses `Snapshot` rather than hiding estimates entirely
- unsupported or partial sessions are visible in coverage and exclusions
- the product still feels small, local, and intentionally boring

## Risks

- pricing page format changes
- Claude model attribution remains partial for some sessions
- too much detail sneaks into the UI
- session-level views grow into transcript-viewer behavior

Mitigations:

- snapshot fallback
- explicit estimate labels
- methodology page
- strict page count and chart count

## Definition of Done

v1 is done when:

- the new CLI is the default way to run the dashboard
- the app serves `Overview`, `Workspaces`, and `Methodology`
- Codex/OpenAI and Claude estimates are reliable and clearly labeled
- the UI feels calm, dense, and minimal
- the old static renderer can be removed without losing trust or coverage
