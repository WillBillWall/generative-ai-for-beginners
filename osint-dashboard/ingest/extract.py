"""Turn report text (ISW assessments, RUSI papers) into taxonomy-coded observations
with Claude structured outputs. Output rows still go through normalize.validate().
"""
from __future__ import annotations

import json

import anthropic

from .common import taxonomy

MODEL = "claude-opus-5-5"

SYSTEM = """You are an OSINT analyst coding military-analysis reports into a fixed taxonomy.
Record only tactical observations the text states or clearly assesses: who used which tactic,
where, when, how widely it is used, and whether the other side has countered it.
Paraphrase in at most 280 characters; never copy long passages.
Use '' for unknown sector or unit. Skip anything that does not fit the taxonomy.
Stages describe how widely the tactic is used and run in order: emerging, spreading,
widespread, fading (resurgent = back after fading). Set counter_reported to "yes" when the
text says the other side has found an effective answer; that is not a stage.
Taxonomy (category -> subtypes) and stages:
{taxonomy}"""


def _schema() -> dict:
    tax = taxonomy()
    subtypes = sorted({s for c in tax["categories"].values() for s in c["subtypes"]})
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["date", "side", "sector", "unit", "tactic_category",
                     "tactic_subtype", "stage", "counter_reported", "summary", "confidence"],
        "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD the observation refers to"},
            "side": {"enum": ["RU", "UA", "both"]},
            "sector": {"type": "string"},
            "unit": {"type": "string"},
            "tactic_category": {"enum": sorted(tax["categories"])},
            "tactic_subtype": {"enum": subtypes},
            "stage": {"enum": list(tax["stages"])},
            "counter_reported": {"enum": ["yes", "no"]},
            "summary": {"type": "string"},
            "confidence": {"enum": ["high", "medium", "low"]},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["observations"],
        "properties": {"observations": {"type": "array", "items": item}},
    }


def extract_observations(text: str, *, source_org: str, source_title: str, source_url: str,
                         report_date: str, client: anthropic.Anthropic | None = None) -> list[dict]:
    """Return observation dicts (without id) for one report."""
    client = client or anthropic.Anthropic()
    tax = taxonomy()
    tax_text = json.dumps({"categories": {k: list(v["subtypes"]) for k, v in tax["categories"].items()},
                           "stages": list(tax["stages"])})
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": _schema()}},
        system=[{"type": "text", "text": SYSTEM.format(taxonomy=tax_text),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content":
                   f"Source: {source_org} - {source_title} ({report_date})\n\n<report>\n{text}\n</report>"}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Extraction declined for {source_url}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"Extraction truncated for {source_url}; split the report")
    payload = json.loads(next(b.text for b in response.content if b.type == "text"))
    rows = []
    for obs in payload["observations"]:
        obs.update(source_org=source_org, source_title=source_title, source_url=source_url,
                   access="primary", date_precision="day")
        obs["summary"] = obs["summary"][:280]
        rows.append(obs)
    return rows
