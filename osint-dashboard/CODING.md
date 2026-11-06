# Coding ISW and RUSI reports into observations

Used by Claude in the daily task (and for backfills). The output goes through
`python normalize.py add-observations <file.json>`, which checks it against
`schema/observation.schema.json`, `taxonomy.yaml` and the stage-order rule.

1. Get the text: `python normalize.py isw-digest YYYY-MM-DD` (ISW) or read the RUSI paper.
2. Record only **tactical observations the text states or clearly assesses**: a tactic
   in `taxonomy.yaml` being used, spreading, fading or countered. Skip strategic
   commentary, diplomacy, casualty claims and single strikes with no tactical point.
   Typically 0–5 observations per daily report. Zero is fine.
3. One JSON object per observation:
   - `date`: the date the report describes (YYYY-MM-DD); `side`: RU, UA or both
   - `sector`: the direction as the report names it (e.g. "Pokrovsk direction"), or "Theatre-wide"
   - `unit`: only if named; else ""
   - `tactic_category` / `tactic_subtype`: from taxonomy.yaml
   - `stage`: how widely it is used: emerging, spreading, widespread, fading, resurgent.
     Must not go back from the previous report for the same tactic, side and sector:
     if it truly has, use another sector name or `resurgent` (only after fading).
   - `counter_reported`: "yes" only if the text says the other side found an effective answer
   - `summary`: your paraphrase, ≤280 characters, no long quotes
   - `confidence`: high (ISW assessment or geolocated footage), medium (official claims ISW reports),
     low (milblogger claims only)
   - `source_org` "ISW" or "RUSI", `source_title`, `source_url` (from the digest header)
4. Save the list to a .json file and run `add-observations`. If it rejects a row, fix that
   row; never weaken the rules.
