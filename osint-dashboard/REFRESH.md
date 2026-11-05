# Daily refresh runbook

The dashboard is https://claude.ai/artifact/TgMA151TVV89RJkWmBQi8q, a Dashboard-type
artifact whose datasets are attached CSV files. To refresh it:

1. `./osint-dashboard/refresh.sh`. If it fails, stop and report the error; publish nothing.
2. Commit the changed `osint-dashboard/data/processed/*` files and try to push to the working branch. If the push is refused (scheduled sessions may have read-only access), note it in the report and carry on: the dashboard update below doesn't depend on it.
3. For each dataset below whose CSV changed: upload the CSV as an asset of the artifact.
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

Sources that need network access first (not yet in the refresh): ISW
(understandingwar.org / criticalthreats.org), WarSpotting (ukr.warspotting.net),
NASA FIRMS (firms.modaps.eosdis.nasa.gov, free key), ACLED (acleddata.com, free account).
