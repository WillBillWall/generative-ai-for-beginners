# Ukraine War Tactics Tracker

Combines open-source intelligence on the Russo-Ukrainian war into one consistent
dataset, then shows how tactics change over time: drones, electronic warfare (EW)
and counter-drone, assault methods, and equipment losses.

Live dashboard: https://claude.ai/artifact/TgMA151TVV89RJkWmBQi8q (private until shared)

## Sources

| Source | Used for | How | Method |
|---|---|---|---|
| Ukraine MoD daily totals (via [PetroIvaniuk mirror](https://github.com/PetroIvaniuk/2022-Ukraine-Russia-War-Dataset)) | Russian loss rates by quarter | `ingest/losses.py` | claimed |
| Oryx (same mirror, snapshot of 2023-02-05) | Visually confirmed Russian losses, by model | `ingest/losses.py` | visually confirmed |
| WarSpotting API | Dated confirmed losses for both sides | `ingest/losses.py` (`fetch_warspotting`) | visually confirmed |
| ISW daily assessments | Tactical observations | `ingest/reports.py` and Claude extraction | assessed |
| RUSI papers | Expert assessments of how tactics evolve (EW, drones, assaults); timeline and context only, never loss counts | `ingest/reports.py` and Claude extraction | assessed |
| DeepStateMap daily maps ([archive](https://github.com/cyterat/deepstate-map-data)) | Area under Russian control per day since July 2024 | `ingest/territory.py` | mapped (volunteer OSINT) |
| Curated seed | 33 observations Feb 2022–Oct 2026 | `data/seed/observations.csv` | analytic |

## The data model

- `taxonomy.yaml`: the fixed lists of tactic categories and subtypes, lifecycle phases
  (emerging → scaling → dominant → countered → declining) and equipment classes.
- `schema/observation.schema.json`: one dated, sourced, paraphrased observation.
  `access: secondary` means the claim was read in coverage of the source, not the source itself.
- `schema/losses.schema.json`: a count of losses per side, class and period, with
  `method` (claimed or visually confirmed).

## Run it

```bash
pip install -r requirements.txt
python normalize.py build --refresh                 # download loss data, rebuild data/processed/
python normalize.py isw 2026-10-17                  # code one ISW assessment (needs ANTHROPIC_API_KEY)
python normalize.py rusi <pdf_url> "<title>" 2025-02-14
python -m pytest
```

`build` writes the trend tables from `ingest/trends.py` (`monthly.csv`, `trend_rates.csv`, `shift_points.csv`, `adaptation.csv`, `adaptation_by_year.csv`), plus `observations.csv`, `losses_quarterly.csv`, `tactic_shift.csv`,
`oryx_models.csv`, `oryx_by_class.csv` and `claimed_vs_confirmed.csv` to `data/processed/`.
To refresh the dashboard, upload the new CSVs to its Sources panel.

## Daily refresh

`./refresh.sh` rebuilds everything, downloading only new DeepState days. A scheduled task runs it every day at 04:55 UTC and republishes the dashboard data; the steps are in `REFRESH.md`.

## Trend methods

- **Growth and decline:** a least-squares fit of ln(per-day losses) against month, over the last 12 complete months and the 12 before. Reported as % per quarter, doubling or halving time, and R². Fits with R² below 0.3 are shown as no clear trend.
- **Shift points:** binary segmentation of the monthly log-rate into straight-line segments of at least 6 months, with at most 3 breaks per series. A break is kept only if it removes at least 25% of the segment's squared error. Each break lists the observations within ±3 months.
- **Fires and logistics vs maneuver:** 3-month rolling sums of artillery and rocket launchers, logistics vehicles, and drones, each divided by tanks plus armored vehicles.
- **Adaptation speed:** months from a tactic's first observation to its first report at a higher stage (emerging, then scaling, then dominant), and to its first countered or declining report.

## Known gaps

- ISW, RUSI, Oryx and WarSpotting were blocked from the build environment. The ISW/RUSI
  fetchers and the WarSpotting parser are tested on fixtures only, and the seed
  observations were checked against search-result summaries, not the original pages.
- The Oryx mirror stopped updating in February 2023; current confirmed totals need
  WarSpotting or Oryx directly.
- No Ukrainian loss series and no ISW control-of-terrain data yet.
- Claude extraction is tested with a fake client, not a live API call.
