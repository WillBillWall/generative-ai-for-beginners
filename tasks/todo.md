# Ukraine War Tactics OSINT Dashboard — Plan

**Goal:** Pull open-source intelligence from ISW, Oryx/WarSpotting and RUSI into one normalized dataset and dashboard, to track how tactics and warfare are changing.
**Scope:** Feb 2022–present, aggregated by quarter.
**Focus:** drones and uncrewed systems · electronic warfare (EW) and counter-drone · assault tactics · equipment attrition.
**Deliverables:** a pipeline in `osint-dashboard/` on branch `ccr-3eae8c74-7zuky3`, plus a published dashboard page on claude.ai.

## 1. Schema & taxonomy
- [x] `schema/observation.schema.json`: one row per observation (id, date, quarter, source, source_url, side, oblast/sector, unit, tactic_category, tactic_subtype, equipment_type, outcome, confidence [high/med/low], excerpt ≤ 280 chars)
- [x] `schema/losses.schema.json`: equipment losses (date, side, equipment_class, model, status [destroyed/damaged/captured/abandoned], source, evidence_url)
- [x] `taxonomy.yaml`: a fixed set of tactic categories and subtypes (FPV, fiber-optic FPV, long-range strike drone, recon drone, UGV, drone interceptor, jamming, spoofing, glide bomb, small-group infiltration, mechanized assault, motorcycle/light vehicle assault, etc.)

## 2. Seed dataset (researched now)
- [x] Research ISW quarterly assessments → assault tactics and use of EW/drones, by sector and quarter
- [x] Research Oryx/WarSpotting totals → losses by equipment class, side and quarter
- [x] Research RUSI papers → milestones in how tactics evolved (when they appeared, spread or were countered)
- [x] Normalize into `data/seed/*.csv` with a source URL on every row

## 3. Refresh pipeline (Python)
- [x] `ingest/isw.py`: fetch daily ISW assessments, then use Claude to extract structured observations
- [x] `ingest/losses.py`: pull WarSpotting API data and parse Oryx pages, mapping both to `losses` rows
- [x] `ingest/rusi.py`: take RUSI PDF/HTML, extract with Claude, and map to the taxonomy
- [x] `normalize.py`: deduplicate, validate against the schema, assign quarters, and write `data/processed/`
- [x] Respect robots.txt and rate limits; store short excerpts and links only, never full copyrighted text

## 4. Dashboard (published page)
- [x] Tactic-mix trend: shown as a tactic lifecycle timeline, plus quarterly loss rates
- [x] Attrition: losses by equipment class and side, plus the tank:FPV ratio over time
- [x] EW/counter-drone timeline of adoption milestones
- [ ] Assault tactics by sector (small-group vs mechanized). Partly done: assault tactics are lanes in the timeline, and sector appears only in each observation's detail
- [~] Filters: side and search are done, and every data point links to its source; sector, category, source and confidence filters are not built yet

## 5. Verification
- [x] Schema validation passes on all seed and processed data
- [~] Spot-check rows against sources: checked against search summaries only, because the source sites are blocked
- [x] Unit tests for the normalizers (8 passing)
- [ ] Dashboard viewed at phone and desktop widths in light and dark mode: not checked yet, needs the user to open it
- [x] Data caveats listed in the dashboard (visually-confirmed losses only, so undercounted; source bias)

## Review
**Built:** `osint-dashboard/` (pipeline, 8 passing tests) and the dashboard at https://claude.ai/artifact/TgMA151TVV89RJkWmBQi8q

**Changes from the plan**
- ISW/RUSI fetch and Claude extraction are in `ingest/reports.py` + `ingest/extract.py` (one module for both, not separate isw/rusi files).
- The timeline shows all tactics on one chart (lanes per tactic, colored by phase) instead of a separate per-sector assault view; sector is in each observation's detail.
- Filters: side chips and a search box. There are no category or confidence filters yet.
- The 20-row spot check was done against search-result summaries, because the source sites are blocked from this environment.

**Findings so far**
- Claimed Russian drones downed per armored vehicle destroyed rose from 0.2 (2022 Q2) to about 170 (2026 Q3).
- On 2023-02-05, MoD claims ran 1.9× Oryx-confirmed losses for tanks and 4.5× for artillery.

**Open:** allow network access to understandingwar.org, criticalthreats.org, rusi.org and ukr.warspotting.net, and add an Anthropic API key, so live ingest can run. Also add a Ukrainian loss series and ISW terrain data.
