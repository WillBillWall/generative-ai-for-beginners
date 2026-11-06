# Daily refresh runbook

The dashboard is https://claude.ai/artifact/TgMA151TVV89RJkWmBQi8q, a Dashboard-type
artifact whose datasets are attached CSV files. To refresh it:

0. **Restore saved observations.** With ArtifactData, list the dashboard's `coded` collection
   (all documents). Concatenate every document's `rows` into one JSON list, save it to a file, and run
   `cd osint-dashboard && python3 normalize.py restore-extracted <file>`. (Scheduled sessions may not
   be able to push, so coded observations are kept in the dashboard database, not only in git.)
1. `./osint-dashboard/refresh.sh`. If it fails, stop and report the error; publish nothing. In a fresh container the first WarSpotting fetch takes about 11 minutes (one request a second, their limit is 10 per 10 s); give the command a long timeout or run it in the background.
1b. **Code new ISW reports.** The coded dates are the `coded` document ids (`isw-YYYY-MM-DD`) plus the
   ISW dates in `data/extracted/*.jsonl`. For each date after the latest coded one, up to yesterday
   (at most 7 dates): run `python3 normalize.py isw-digest YYYY-MM-DD` (a failure for that date usually
   means ISW published no report: skip it). Code the digest as `osint-dashboard/CODING.md` describes,
   save the list (possibly empty) to `isw-YYYY-MM-DD.json`, and run
   `python3 normalize.py add-observations isw-YYYY-MM-DD.json --name daily`. Fix any rejected row and
   rerun; never loosen a rule. Then save the rows it wrote (`isw-YYYY-MM-DD.added.json`) with ArtifactData
   `set` collection `coded`, doc id `isw-YYYY-MM-DD`, data `{rows: [...], edit: {via: "claude", at}}`.
   An empty list still gets its document, so the date counts as done.
1c. **RUSI, Mondays only.** Search rusi.org for Ukraine land-warfare publications newer than the latest
   RUSI date in the observations. Code any new paper's tactical findings the same way, with
   `--name daily` and a `coded` document `rusi-<slug>`. Skip papers about other countries' force design.
1d. Rebuild without downloading again: `python3 normalize.py build`, then `python3 -m pytest -q`.
2. Commit the changed `osint-dashboard/data/processed/*` files and try to push to the working branch. If the push is refused (scheduled sessions may have read-only access), note it in the report and carry on: the dashboard update below doesn't depend on it.
3. For each dataset below whose file changed (after 1d this includes `observations`, `adaptation`, `adaptation_by_year`, `tactic_before_after` and `advantage_periods` when new observations were added): upload the CSV as an asset of the artifact.
   Then update that dataset document (collection `datasets`, read it first and pin `if_version`):
   set `source.url` to the new `/_blob/…` url and `source.name`, `updated: {at, by: "daily refresh"}`,
   and `edit: {via: "claude", at}`.
4. Don't change `files/index.html`, and don't touch `claimed_vs_confirmed` or `oryx_tank_age` (fixed 2023 snapshots).
5. Report what changed: latest date per source, and any test or download failures.

| Dataset id | File in `data/processed/` | Source |
|---|---|---|
| `tactic_shift` | `tactic_shift.csv` | UA MoD daily (GitHub mirror) |
| `monthly` | `monthly.csv` | UA MoD daily |
| `trend_rates` | `trend_rates.csv` | derived |
| `shift_points` | `shift_points.csv` | derived |
| `observations` | `observations.csv` | seed + extracted ISW/RUSI |
| `adaptation` | `adaptation.csv` | derived |
| `adaptation_by_year` | `adaptation_by_year.csv` | derived |
| `territory_daily` | `territory_daily.csv` | DeepStateMap (GitHub archive) |
| `territory_monthly` | `territory_monthly.csv` | DeepStateMap |
| `territory_vs_losses` | `territory_vs_losses.csv` | derived (DeepStateMap + UA MoD) |
| `loss_correlations` | `loss_correlations.csv` | derived |
| `tactic_before_after` | `tactic_before_after.csv` | derived |
| `advantage_periods` | `advantage_periods.csv` | derived |
| `metrics` | `metrics.csv` | seed (`data/seed/metrics.csv`), changes only when new figures are added |
| `territory_by_direction` | `territory_by_direction.csv` | DeepStateMap (month-start maps) |
| `front_shape` | `front_shape.csv` | DeepStateMap (month-start maps) |
| `equipment_monthly` | `equipment_monthly.csv` | UA MoD daily |
| `front_map` | `front_map.json` | DeepStateMap + Natural Earth borders (upload as JSON) |
| `local_map` | `local_map.json` | DeepStateMap + geoBoundaries council areas (`data/reference/admin_east.json`, upload as JSON) |
| `warspotting_monthly` | `warspotting_monthly.csv` | WarSpotting API (aggregates only; raw records stay in data/raw) |
| `warspotting_adaptations` | `warspotting_adaptations.csv` | WarSpotting API tags |
| `claimed_vs_confirmed_live` | `claimed_vs_confirmed_live.csv` | UA MoD + WarSpotting |

Sources that need network access first (not yet in the refresh): ISW
(understandingwar.org / criticalthreats.org), WarSpotting (ukr.warspotting.net),
NASA FIRMS (firms.modaps.eosdis.nasa.gov, free key), ACLED (acleddata.com, free account).
