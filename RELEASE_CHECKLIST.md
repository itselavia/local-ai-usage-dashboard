# Release Checklist

Use this before calling the `dashboard/` path release-ready.

## Setup

- install dependencies with `python3 -m pip install -r requirements.txt`
- confirm local source directories exist or are intentionally absent:
  - `~/.codex`
  - `~/.claude`

## Data

- run `python3 -m dashboard.cli ingest`
- run `python3 -m dashboard.cli doctor`
- confirm:
  - latest ingest timestamp is current
  - session counts look plausible
  - excluded and unsupported sessions are explained
  - pricing freshness is visible

## Product

- run `python3 -m dashboard.cli serve`
- check:
  - `Overview` renders
  - `Workspaces` renders
  - `Methodology` renders
  - filters persist in query params
  - metric toggle changes charts and rankings
  - empty states remain readable

## Snapshot

- if you want fresh data first, run `python3 -m dashboard.cli ingest`
- run `python3 -m dashboard.cli generate --latest`
- run `python3 -m dashboard.cli generate --anonymize-workspaces --latest`
- confirm these files exist:
  - `.dashboard/snapshots/latest/index.html`
  - `.dashboard/snapshots/latest/overview.html`
  - `.dashboard/snapshots/latest/workspaces.html`
  - `.dashboard/snapshots/latest/methodology.html`
  - `.dashboard/snapshots/latest/static/dashboard.css`
  - `.dashboard/snapshots/latest/static/dashboard.js`
- confirm the anonymized export contains no raw `/Users/...` paths or real workspace labels

## Tests

- run `python3 -m unittest discover -s tests -v`
- confirm dashboard tests and legacy regression tests both pass

## Docs

- `README.md` matches the actual workflow and file layout
- `IMPLEMENTATION_SPEC.md` matches the actual repo state
- `PHASE3_PLAN.md` still matches the intended next step

## Final Check

- the `dashboard/` path can be described as the primary product interface
- the anonymized export flow is the one to use for any public GitHub commit
- the remaining work is polish and parity hardening, not missing core functionality
