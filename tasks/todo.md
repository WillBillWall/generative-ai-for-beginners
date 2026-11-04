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

**RUSI role (confirmed by user):** RUSI papers are expert assessments (`evidence = assessed`) that go on the timeline and in the context notes. They never feed loss counts, and a test enforces this. There are 11 RUSI rows covering Nov 2022–Feb 2025; later RUSI work found so far is secondary or undated. The dashboard has a RUSI-only filter.

**Open:** allow network access to understandingwar.org, criticalthreats.org, rusi.org and ukr.warspotting.net, and add an Anthropic API key, so live ingest can run. Also add a Ukrainian loss series and ISW terrain data.

# Trend analysis (requested 2026-11-04)

- [x] `ingest/trends.py`: monthly per-day loss rates from the daily MoD series (shares the quarterly logic)
- [x] Growth/decline: log-linear fit per class, last 12 months vs the 12 before: % per quarter, doubling/halving time, R², year-over-year change
- [x] Shift points: binary segmentation of monthly log-rates (min 6-month segments, at most 3 breaks), each matched to tactic observations within ±3 months
- [x] Fires vs maneuver: artillery+MRL per armored vehicle, logistics vehicles per armored vehicle, drones per armored vehicle (monthly, 3-month rolling)
- [x] Adaptation speed: per tactic, months from first observation to first scaling, dominant and countered report
- [x] Tests for each calculation on synthetic series with known answers
- [x] Dashboard: one "Trends" section with four cards, every number from a dataset

## Trend review
- Last 12 months (Nov 2025–Oct 2026), as % change per quarter: drones +52.6% (doubling about every 4.9 months), logistics vehicles +63.9%, artillery +24.7%, tanks -6.2% (weak fit). In the 12 months before, armored vehicles fell 43.8% a quarter.
- Losses per armored vehicle destroyed: logistics vehicles rose from 0.4 (2022) to about 52 now, and artillery/rockets from 0.1 to about 6.
- 11 shift points found. The May 2025 drops in tank and armored-vehicle losses line up with the spread of motorcycle assaults, fiber-optic FPVs and interceptors. The January 2026 jump in drone losses may partly reflect a change in what the ministry counts.
- Adaptation speed: the median time for a tactic to spread fell from 20.5 months (2023, n=1) to about 4 months (2024 and 2025, n=3 each). This is indicative only.
- 13 tests pass, including known-answer tests for the trend fit, segmentation, monthly rates and adaptation. A float-noise bug in segmentation was caught by these tests and fixed.

# Readability fixes (feedback 2026-11-04)
- [x] Replace "per armored vehicle destroyed" everywhere with a growth index (1 = average daily rate Apr–Jun 2022), with direct end labels (e.g. "Drones ×280")
- [x] Adaptation: one labeled row per tactic, showing first seen → spread → countered on a shared time axis, the months written on the bar, and a table that names what countered it
- [x] Timeline: swimlane bars colored by stage (each stage lasts until the next report), category headers, side tags, plain legend
- [x] Answer: sources for daily updates, checked for reachability

## Readability review
- The growth index replaces every "per armored vehicle" ratio: headline, top tile, main chart, and the removed fires/logistics card. Current values: drones ×275, logistics vehicles ×30, artillery ×10, armored vehicles ×0.3, tanks ×0.2.
- The adaptation chart now has one labeled row per tactic, with the months written on each bar and the counter-report text in the table. Tactics with no counter report no longer show as "0 months".
- The timeline shows stage bars from one report to the next, under category headers, with side tags.
- Mistake caught: a substring match hit `dash.draw('timeline')` inside a click handler and corrupted the script. Restored from git, redone with anchored matching, and syntax-checked. Lesson added.
