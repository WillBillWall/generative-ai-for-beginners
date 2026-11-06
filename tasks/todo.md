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

# Territory + daily refresh (requested 2026-11-04)
- [x] `ingest/territory.py`: DeepStateMap daily occupied-area polygons (GitHub archive) → occupied km² per day, net daily/monthly change (geodesic area)
- [x] Tests: area of a known polygon, change series
- [x] Dashboard: "Front line" card with monthly net Russian gain, tactic reports marked on the same time axis, and a 30-day tile
- [x] `REFRESH.md` + `refresh.sh`: one command rebuilds everything; the steps say which file goes to which dashboard dataset
- [x] Scheduled task: daily fresh session that runs the refresh, commits and pushes, and updates the dashboard files

## Territory and refresh review
- DeepStateMap: 843 daily maps from 2024-07-08 to 2026-11-04, measured as geodesic area. Russian net gain in 2025 was about 4,330 km², close to widely reported totals. Gains slowed from about 15 km²/day in mid-2025 to 0.3–2 km²/day since May 2026.
- The largest single-day changes are +92 km² (2025-07-04) and -116 km² (2026-08-13). These are likely map redraws, and the chart caveat says so.
- Scheduled task `trig_01PfhzHd5Kw7MuP5HLafJpCn` runs daily at 04:55 UTC in a fresh session and follows REFRESH.md. Datasets carry `schedule` and `staleAfterHours: 48`.
- 16 tests pass. The first scheduled run has been fired by hand to prove it works end to end; see its report.

# Self-writing summary (requested 2026-11-04)
- [x] Every tactic subtype gets a plain-English phrase (`taxonomy.yaml: phrases`); a test checks they cover the whole list
- [x] The summary is drawn from data on every view: drone/tank levels and their 3-month direction; current Russian assault methods and what backs them, quoting the latest report; Ukraine's most recent measures and the latest countered tactic; and the 30-day territory pace vs the previous 30 days and the 18-month peak, with a conclusion chosen by that pace
- [x] Ran once against the real data in Node. This caught a CRLF bug (CSV rows ending "True\r") and a kill-zone misclassification; both fixed
- [x] Second manual run of the scheduled task: tests passed, no data change, correctly published nothing. A push is not yet exercised (nothing to commit)

# Stage model fix (option A, requested 2026-11-04)
- [x] Replace `phase` with an ordered `stage`: emerging → spreading → widespread → fading, plus `resurgent` (only after fading)
- [x] Separate `counter_reported` (yes/no) from stage
- [x] Recode the 33 seed rows; countered rows get the usage stage the source describes, plus counter_reported=yes
- [x] Rows per (tactic, side): RU, UA, or "both sides"
- [x] Order check in the build: within one row and the same sector, a stage may not go backwards unless it is `resurgent`; a different sector is a new place and may restart lower
- [x] Carry the change through: Claude extraction schema, adaptation metrics, dashboard timeline, legend, detail, table, summary, front-line ticks

## Stage model review
- The 33 seed rows were recoded mechanically: scaling→spreading, dominant→widespread, declining→fading. The three "countered" rows became widespread + counter_reported=yes: Ukraine's 2023 mechanized assaults, Ukraine's jamming in 2025, and Russia's Rubikon-driven kill zone in 2026.
- A "both sides" report is placed in the Russian and the Ukrainian row (`sides_of`). Without that, splitting by side broke continuity; for example, Russian fiber-optic FPVs never showed as spreading.
- The order check runs on every build. All 33 rows pass; the drops back are new-sector cases (glide bombs at the Fortress Belt, infiltration at Dobropillya).
- Adaptation per side: Ukraine's jamming spread, then was countered, after 8.8 months. The median months to spread is 20.5 for tactics first seen in 2023 (n=1), 6.5 for 2024 (n=4), and 4.3 for 2025 (n=3).
- 18 tests pass, including a new order-check test. The summary was re-run against the data.

# Tactics vs territory (requested 2026-11-04)
Question: which tactics went with territory changing hands, and who held the advantage?
- [x] Add UA MoD claimed Russian personnel losses (same mirror) to the monthly series
- [x] `ingest/correlate.py`:
  - monthly join, Jul 2024 onward: km²/day gained against per-day losses (personnel, tanks, armored vehicles, artillery, drones, logistics vehicles)
  - cost of advance: Russian personnel and armored vehicles lost per km² gained (3-month rolling)
  - correlations (Spearman, with the loss series leading by 0, 1 and 2 months), n reported, labelled indicative
  - before/after: for each tactic report, average km²/day over the 3 months before vs the 3 months after, per side
  - advantage periods: split the months into stretches where Russia was advancing cheaply, advancing expensively, or stalled
- [x] Tests with synthetic series and known answers
- [x] Dashboard section "What was working", with a summary written from the data
- [x] Caveats in the page: claimed losses, a small n, overlapping events, correlation is not cause

## Tactics vs territory review
- **First pass misleading:** level correlations of -0.7 to -0.8 for drones, logistics and artillery came from opposite trends alone. Month-to-month changes give |rho| at most 0.33 with n=26, i.e. no single loss type tracks the front.
- **Strongest signal is cost:** claimed Russian casualties per km² gained rose from about 90-100 (2024-25 fast phases) to about 890 (Jun-Oct 2026 stall), roughly 9 times, while daily Russian losses rose.
- **Advantage periods:** fast Aug 2024-Feb 2025, slow Mar-Apr 2025, fast May 2025-Feb 2026, slow Mar-May 2026, stalled since Jun 2026.
- **Tactical edge (timing only):** the May 2025 pick-up lines up with RU motorcycle assaults and fiber-optic FPVs spreading while UA jamming was countered. The 2026 slowdown and stall line up with RU's Rubikon kill zone being countered and UA strikes on drone units spreading.
- **Before/after limits:** RUSI reviews are excluded (retrospective dates), only turning-point reports are used, and winter windows are flagged. It is still confounded by season and by overlapping events.
- 22 tests pass; the summary logic was run against the real data.

# More detail (requested 2026-11-04)
1. Tactical metrics log
- [x] `schema/metric.schema.json` + `taxonomy.yaml: metrics` (key, label, unit, which direction is better for whom)
- [x] Seed `data/seed/metrics.csv` from web research: dated, sourced, with value or range, side, confidence. Only figures with a findable date and source.
- [x] Claude extraction can return metrics too (later, when ISW/RUSI are allowed)
2. Territory by direction
- [x] Monthly DeepState snapshots → gained/lost pieces (polygon difference) → each piece assigned to the nearest named front direction (Kupiansk, Pokrovsk, Huliaipole, …), with the anchors' coordinates documented
3. Front-line shape
- [x] Per month: number of separate gained pieces, the largest piece, the deepest advance (km from the previous line), and the share of gains in the top direction
4. Equipment mix
- [x] Monthly ground-robot, cruise-missile and special-equipment losses; tank losses by design decade from the Oryx 2023 snapshot (labelled as old)
5. [x] Dashboard "Granular view" section; tests; refresh runbook

## Granular review
- **Metrics log:** 24 dated, sourced figures across 8 metrics. Figures without a findable date were left out (RUSI's ~1-week drone lifespan, the UK MoD's 80% of casualties). Sensor-to-shooter time has only one dated point (Delta, ~20 → 3-5 min, Aug 2026).
- **Directions:** month-start map differences reconcile with the area series to within a few km²/month. Nov 2025-Oct 2026 net: Siversk +495, Huliaipole +486, Pokrovsk +334, Kostiantynivka +249 km²; net Ukrainian gains at Velyka Novosilka, Lyman and Novopavlivka.
- **Shape:** since mid-2026, about 18-23 separate small pieces a month, deepest push 4-8 km, the busiest direction only 23-34% of gains. That is broad, shallow pressure, not breakthroughs.
- **Oryx 2023:** 47% of confirmed tank losses were models designed or last modernised in the 1980s or earlier.
- 25 tests pass, including a geometry test with a known 3 km / 12 km² push.

# Front map (requested 2026-11-04)
- [x] `ingest/frontmap.py`: Ukraine border (Natural Earth 1:50m), latest Russian-held area, 12 months of gained/lost pieces, direction anchors and cities, as SVG paths in km (UTM 37N), 176 KB
- [x] Rendered the layers in a standalone SVG to check placement (gains along Siversk-Kostiantynivka, Pokrovsk-Dobropillya, Huliaipole; Ukrainian gains near Lyman, Kupiansk, Novopavlivka); fixed the Crimea crop and the duplicate Kherson label
- [x] Dashboard map card: 1/3/12-month window, bubbles sized by net change, collision-nudged labels, caption with totals; heat table retitled as the month-by-month detail

# Local-boundary map (requested 2026-11-05)
- [x] Boundaries: geoBoundaries gbOpen UKR (CC BY 4.0). These are pre-2020 units: 495 raions, 10,375 village/town councils (not the 1,469 post-2020 hromadas). The LFS files come via media.githubusercontent.com.
- [x] `data/reference/admin_east.json` (1.7 MB, committed): 263 raions in the map window and 1,528 councils within 30 km of the front line on the first or latest DeepState day, simplified, in UTM metres
- [x] `ingest/admin.py run`: per council, share under Russian control now / 1m / 3m / 12m ago / Jul 2024 → `local_map.json` (1.2 MB)
- [x] Check render matched the expected pattern; dashboard map replaced with a council choropleth (grey = Russian-held, white = Ukrainian-held, orange/blue intensity = share changed), with raion borders, a 4-way period choice, tooltips and a caption
- [x] Found: the 5 Nov scheduled refresh could not push (the routine has no repo credentials), so it published nothing. Runbook and routine prompt changed so a refused push no longer blocks the dashboard update. I ran the refresh by hand today and published the data to 2026-11-05.

# Network access (2026-11-06)
- [x] New personal environment `generative-ai-for-beginners` (env_0167wGKMjEk9yQRkRMuexESA), approved by the user. It allows understandingwar.org, www.criticalthreats.org, rusi.org, static.rusi.org, ukr.warspotting.net, firms.modaps.eosdis.nasa.gov, www.cfr.org, and raw/media.githubusercontent.com. This session moved onto it.
- [x] Verified: criticalthreats.org (ISW daily assessments) 200, rusi.org + PDFs 200, cfr.org 200, FIRMS API 200, WarSpotting stats + losses 200 (needs a User-Agent and a trailing slash; records carry geo, unit and weapon tags). understandingwar.org itself shows a bot check, so use the criticalthreats.org mirror.
- [x] Daily scheduled task recreated on the new environment (trig_016USCpWNhHPNAwNKZ8pKCbU, 04:55 UTC). The old one (trig_01PfhzHd5Kw7MuP5HLafJpCn) is disabled, not deleted, to keep its run history.
- [ ] FIRMS needs a free MAP_KEY, which goes in the URL path, so the proxy can't inject it as a header. The user has to add it to the environment themselves.
- [ ] ISW/RUSI extraction with Claude needs an Anthropic API key (api.anthropic.com, x-api-key header), which can be saved with the credential form.
- [ ] Next: WarSpotting ingest (types → classes, weapon tags), ISW daily extraction, RUSI paper extraction, CFR as a further-reading link
