# Phase 3 Plan

Phase 3 is not a new product expansion. It is the polish and release-hardening pass for the existing three-page local dashboard.

## Goals

- make the phase-2 dashboard feel production-ready for a fresh open-source clone
- harden trust against the legacy report before deprecating more of the old path
- improve clarity and density without adding extra product surface
- tighten release ergonomics so `ingest -> doctor -> serve/generate` is the obvious workflow

## Non-Goals

- no new providers
- no new pages
- no transcript browser or session explorer
- no React migration
- no background sync
- no commits, pushes, line-change, or productivity metrics

## Workstreams

### 1. Parity hardening

- add explicit parity checks between the legacy aggregate path and `dashboard/`
- compare sessions, total tokens, estimated cost, top models, and top workspaces
- add fixed fixtures for:
  - unsupported models
  - partial parses
  - empty windows
  - temp workspaces
  - anonymization

### 2. UX polish

- tighten chart titles and supporting copy
- standardize metric names and display labels across pages
- improve filter state visibility
- make selected workspace state more legible
- keep the design calmer and denser, not more decorative

### 3. Snapshot and shareability

- verify generated snapshots read well without the live app context
- keep snapshot filenames stable and predictable
- make `dashboard generate --anonymize-workspaces` the obvious public-sharing path
- ensure anonymized exports do not leak raw workspace labels, repo names, or source paths
- decide whether CDN-hosted ECharts is acceptable for snapshot output
- if needed, bundle the minimal chart asset locally

### 4. Documentation and release hygiene

- finish the README as a real clone-and-run guide
- keep the implementation spec aligned to the actual repo state
- add a short release checklist for pre-release verification
- make Make targets and dependency declarations match the real workflow

### 5. Operability

- tighten `doctor` as the canonical preflight check
- make common failure modes obvious:
  - missing source directories
  - empty database
  - snapshot-only pricing
  - unsupported models
  - excluded sessions

## Sequencing

1. Documentation and release hygiene
2. Parity hardening
3. UX polish
4. Snapshot and shareability
5. Final readiness pass

## Readiness Criteria

- a new user can follow `README.md` without guessing
- `dashboard/` is demonstrably trustworthy against the legacy path on the agreed core metrics
- `python3 -m unittest discover -s tests -v` is green
- `python3 -m dashboard.cli doctor` is green on a representative local setup
- `python3 -m dashboard.cli generate --latest` produces a clean snapshot
- the three shipped pages feel complete enough that adding a fourth page would be harder to justify than useful

## Exit Condition

Phase 3 is done when the repo can present `dashboard/` as the default product path with confidence, not as an in-progress alternative.
