# local-ai-usage-dashboard

Local, estimate-first dashboard for Codex/OpenAI and Claude usage.

This repo is for one job: turn rich local AI session telemetry into a calm, high-signal view of estimated cost, token flow, cache behavior, and workspace concentration.

The product stays intentionally boring:

- local files only
- open source and clone-and-run
- server-rendered UI
- no desktop wrapper
- no background daemon
- no Copilot in v1
- no fake billing claims

## Status

- phase 1: complete
- phase 2: complete
- phase 3: planned, not started

The current repo is ready for real local use. `ingest`, `serve`, `generate`, and `doctor` are all live.

## Product

The dashboard is built around three questions:

- where did AI usage happen?
- what did it likely cost?
- what kind of work was it?

It answers those questions across two providers today:

- Codex / OpenAI
- Claude

Copilot is intentionally deferred from v1 so the product can stay coherent and the estimation model can stay trustworthy.

## Pages

- `Overview`: top-line metrics, trend, mix, and top workspaces
- `Workspaces`: ranked workspace table plus a selected-workspace detail view
- `Methodology`: estimate rules, exclusions, pricing snapshots, coverage, and doctor summary

## What It Shows

- estimated cost
- sessions
- total tokens
- cache savings estimate
- provider mix
- model mix
- workspace concentration
- work-shape flags such as tools, web, agents, edits, and MCP
- pricing freshness and coverage

## Quickstart

Requirements:

- Python `3.10+`
- local Codex/OpenAI data under `~/.codex`
- local Claude data under `~/.claude`

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Ingest local logs into DuckDB:

```bash
python3 -m dashboard.cli ingest
```

Run the local dashboard:

```bash
python3 -m dashboard.cli serve
```

By default the app serves at [http://127.0.0.1:8000](http://127.0.0.1:8000).

Generate a static snapshot:

```bash
python3 -m dashboard.cli generate
```

Run the local health check:

```bash
python3 -m dashboard.cli doctor
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Typical Workflow

For normal local use:

```bash
python3 -m dashboard.cli ingest
python3 -m dashboard.cli serve
```

For a shareable static export:

```bash
python3 -m dashboard.cli generate --anonymize-workspaces
```

If you want fresh data first, run `python3 -m dashboard.cli ingest` before the command above.

For public sharing, use the anonymized generate command above and verify the output before committing it.
The anonymized export should not contain raw `/Users/...` paths or real workspace labels.
The safe export lives under `.dashboard/snapshots/latest/` unless you override `--output-dir`.

For a quick data-quality check:

```bash
python3 -m dashboard.cli doctor
```

## Data Sources And Local State

The dashboard reads local files by default from:

- `~/.codex`
- `~/.claude`

Generated and derived state lives under repo-local `.dashboard/`:

- `.dashboard/dashboard.duckdb`
- `.dashboard/pricing_snapshot.json`
- `.dashboard/metadata.json`
- `.dashboard/snapshots/latest/index.html`
- `.dashboard/snapshots/latest/overview.html`
- `.dashboard/snapshots/latest/workspaces.html`
- `.dashboard/snapshots/latest/methodology.html`
- `.dashboard/snapshots/latest/static/`

You can override the source and output paths with CLI flags:

```bash
python3 -m dashboard.cli ingest --codex-dir /path/to/.codex --claude-dir /path/to/.claude --db /path/to/dashboard.duckdb
python3 -m dashboard.cli serve --db /path/to/dashboard.duckdb --port 8080
python3 -m dashboard.cli generate --db /path/to/dashboard.duckdb --output-dir ./out
```

Useful ingest options:

```bash
python3 -m dashboard.cli ingest --pricing-mode snapshot
python3 -m dashboard.cli ingest --include-temp
python3 -m dashboard.cli ingest --timezone America/Los_Angeles
```

Useful serve option for local development:

```bash
python3 -m dashboard.cli serve --reload
```

## Command Surface

`dashboard ingest`

- discovers local Codex/OpenAI and Claude sessions
- refreshes pricing when possible
- writes normalized rows into DuckDB
- updates metadata and pricing snapshots

`dashboard serve`

- runs the local FastAPI app against DuckDB
- keeps UI state in query params
- renders server-side HTML with a small amount of JS for charts

`dashboard generate`

- renders a static snapshot from DuckDB
- writes `index.html`, `overview.html`, `workspaces.html`, and `methodology.html`
- copies the dashboard static assets alongside the snapshot

`dashboard doctor`

- checks source path presence
- reports ingest health
- surfaces partial parses, exclusions, unsupported models, and pricing freshness

## Trust Model

This is an estimate-first product, not a billing product.

- OpenAI and Claude costs are estimated from local usage plus official pricing.
- Pricing freshness stays visible as `Fresh`, `Snapshot`, or `Unavailable`.
- Unsupported models are excluded from estimated cost instead of guessed.
- Partial parses remain visible rather than silently dropped.
- Cache savings are shown as an estimate, not a provider invoice number.

The goal is to make the estimate honest and useful, not to pretend it is your actual enterprise bill.

## Architecture

The `dashboard/` package is now the primary product path:

- `dashboard/cli.py`: command parsing and dispatch
- `dashboard/ingest.py`: normalize local logs into DuckDB
- `dashboard/generate.py`: write a static snapshot from DuckDB
- `dashboard/doctor.py`: report local source and coverage health
- `dashboard/app.py`: FastAPI app factory
- `dashboard/routes.py`: thin web routes
- `dashboard/queries.py`: page query layer
- `dashboard/db.py`: DuckDB connection and schema helpers
- `dashboard/estimates.py`: cost estimation and pricing snapshots
- `dashboard/providers/`: Codex/OpenAI and Claude adapters

The repo still keeps the legacy one-shot path for comparison:

- `codex_usage_report.py`
- `usage_report_common.py`
- `usage_report_providers.py`
- `usage_report_render.py`

That path is retained as a migration reference, but `dashboard/` is the primary shipped interface now.

## Public Sharing

If you want to publish a dashboard snapshot to GitHub, use the anonymized dashboard path:

```bash
python3 -m dashboard.cli generate --anonymize-workspaces
```

If you want to refresh the data first, run `python3 -m dashboard.cli ingest` before generating the public snapshot.

Before committing, confirm the snapshot does not contain:

- raw `/Users/...` paths
- real workspace names
- repo names that identify private projects
- source-path sections that reveal local machine layout

The sample `index.html` in the repo is a reference artifact. The legacy script now writes to `.dashboard/legacy/` by default so local runs do not overwrite the tracked sample.

## Documentation

- [`IMPLEMENTATION_SPEC.md`](./IMPLEMENTATION_SPEC.md): phase 1 and phase 2 architecture, data model, and implementation details
- [`PHASE3_PLAN.md`](./PHASE3_PLAN.md): phase 3 scope, priorities, sequencing, and readiness criteria

## Development

Helpful make targets:

```bash
make test
make dashboard-ingest
make dashboard-serve
make dashboard-generate
make dashboard-doctor
```

The current tests cover:

- legacy report behavior
- provider adapters
- pricing and estimate logic
- ingest writes and metadata
- query-layer context generation
- route rendering
- doctor summary behavior
