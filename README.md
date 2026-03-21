# local-ai-usage-dashboard

Local static usage reporting for AI coding tools.

This repo stays intentionally boring:

- Static HTML only
- No server
- No build step
- No frontend framework
- No guessed spend
- No silent stale pricing

Right now it supports:

- Codex / OpenAI
- Claude

Copilot is intentionally deferred until there is trustworthy local telemetry for usage and pricing semantics.

## What it does

The reporter reads local usage data, aggregates it, checks official pricing when needed, and writes a single static HTML file.

Spend only appears when official pricing was checked live on that same run.

If pricing refresh fails, usage still renders and spend is hidden with a blunt status message.

## Usage

Generate the report:

```bash
python3 codex_usage_report.py
```

Useful flags:

```bash
python3 codex_usage_report.py --include-temp
python3 codex_usage_report.py --anonymize-workspaces
python3 codex_usage_report.py --codex-dir ~/.codex --claude-dir ~/.claude
python3 codex_usage_report.py --output ./index.html --timezone America/Los_Angeles
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Output and local state

Generated on each run:

- `index.html`

Local operator snapshot:

- `.pricing_snapshot.json`

If you want to share a sample report publicly, run with `--anonymize-workspaces` to replace rendered workspace and repo labels with placeholders like `workspace-01`.

## Layout

- `codex_usage_report.py`: small entrypoint and orchestration
- `usage_report_common.py`: shared helpers and snapshot handling
- `usage_report_providers.py`: provider-specific discovery, pricing, aggregation, spend logic
- `usage_report_render.py`: HTML rendering
- `tests/test_usage_report.py`: stdlib regression tests

## Trust rules

- OpenAI pricing comes from official OpenAI pages only.
- Claude pricing references come from official Anthropic pages only.
- Spend is hidden when freshness cannot be verified on the current run.
- Claude spend is intentionally unavailable in v1.
