# Ukraine War Tactics OSINT Dashboard — Plan

**Goal:** Pull open-source intelligence from ISW, Oryx/WarSpotting and RUSI into one normalized dataset and dashboard, to track how tactics and warfare are changing.
**Scope:** Feb 2022–present, aggregated by quarter.
**Focus:** drones and uncrewed systems · electronic warfare (EW) and counter-drone · assault tactics · equipment attrition.
**Deliverables:** a pipeline in `osint-dashboard/` on branch `ccr-3eae8c74-7zuky3`, plus a published dashboard page on claude.ai.

## 1. Schema & taxonomy
- [ ] `schema/observation.schema.json`: one row per observation (id, date, quarter, source, source_url, side, oblast/sector, unit, tactic_category, tactic_subtype, equipment_type, outcome, confidence [high/med/low], excerpt ≤ 280 chars)
- [ ] `schema/losses.schema.json`: equipment losses (date, side, equipment_class, model, status [destroyed/damaged/captured/abandoned], source, evidence_url)
- [ ] `taxonomy.yaml`: a fixed set of tactic categories and subtypes (FPV, fiber-optic FPV, long-range strike drone, recon drone, UGV, drone interceptor, jamming, spoofing, glide bomb, small-group infiltration, mechanized assault, motorcycle/light vehicle assault, etc.)

## 2. Seed dataset (researched now)
- [ ] Research ISW quarterly assessments → assault tactics and use of EW/drones, by sector and quarter
- [ ] Research Oryx/WarSpotting totals → losses by equipment class, side and quarter
- [ ] Research RUSI papers → milestones in how tactics evolved (when they appeared, spread or were countered)
- [ ] Normalize into `data/seed/*.csv` with a source URL on every row

## 3. Refresh pipeline (Python)
- [ ] `ingest/isw.py`: fetch daily ISW assessments, then use Claude to extract structured observations
- [ ] `ingest/losses.py`: pull WarSpotting API data and parse Oryx pages, mapping both to `losses` rows
- [ ] `ingest/rusi.py`: take RUSI PDF/HTML, extract with Claude, and map to the taxonomy
- [ ] `normalize.py`: deduplicate, validate against the schema, assign quarters, and write `data/processed/`
- [ ] Respect robots.txt and rate limits; store short excerpts and links only, never full copyrighted text

## 4. Dashboard (published page)
- [ ] Tactic-mix trend: share of each tactic category over time, by quarter
- [ ] Attrition: losses by equipment class and side, plus the tank:FPV ratio over time
- [ ] EW/counter-drone timeline of adoption milestones
- [ ] Assault tactics by sector (small-group vs mechanized)
- [ ] Filters: side, sector, category, source, confidence; every data point links to its source

## 5. Verification
- [ ] Schema validation passes on all seed and processed data
- [ ] Spot-check 20 random rows against their source URLs
- [ ] Unit tests for the normalizers; dashboard renders at phone and desktop widths in light and dark mode
- [ ] Data caveats listed in the dashboard (visually-confirmed losses only, so undercounted; source bias)

## Review
_(filled in on completion)_
