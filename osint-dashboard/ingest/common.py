"""Shared helpers: paths, taxonomy, polite HTTP, quarter maths."""
from __future__ import annotations

import time
from datetime import date
from functools import lru_cache
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
SEED = DATA / "seed"
PROCESSED = DATA / "processed"
SCHEMA = ROOT / "schema"

USER_AGENT = "osint-tactics-dashboard/0.1 (research; respects robots.txt)"
WAR_START = date(2022, 2, 24)


@lru_cache(maxsize=1)
def taxonomy() -> dict:
    return yaml.safe_load((ROOT / "taxonomy.yaml").read_text())


def sides_of(obs: dict) -> list[str]:
    """Rows are per side: a report about both sides belongs to the Russian and the Ukrainian row."""
    return ["RU", "UA"] if obs["side"] == "both" else [obs["side"]]


def quarter_of(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def quarter_bounds(q: str) -> tuple[date, date]:
    year, n = int(q[:4]), int(q[-1])
    start = date(year, 3 * (n - 1) + 1, 1)
    end_month = 3 * n
    end = date(year + (end_month == 12), end_month % 12 + 1, 1)
    return start, date.fromordinal(end.toordinal() - 1)


def quarters_between(start: date, end: date) -> list[str]:
    out, y, n = [], start.year, (start.month - 1) // 3 + 1
    while (y, n) <= (end.year, (end.month - 1) // 3 + 1):
        out.append(f"{y}Q{n}")
        y, n = (y + 1, 1) if n == 4 else (y, n + 1)
    return out


_last_request: dict[str, float] = {}


def polite_get(url: str, *, min_interval: float = 2.0, timeout: float = 30.0) -> requests.Response:
    """GET with a per-host rate limit and an identifying User-Agent."""
    host = url.split("/")[2]
    wait = _last_request.get(host, 0) + min_interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    _last_request[host] = time.monotonic()
    resp.raise_for_status()
    return resp
