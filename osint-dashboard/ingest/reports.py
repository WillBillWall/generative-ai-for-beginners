"""Fetch ISW daily assessments and RUSI papers, extract text, code with Claude.

ISW: Russian Offensive Campaign Assessments are published daily on
understandingwar.org and mirrored on criticalthreats.org.
RUSI: papers are HTML pages with PDF downloads; pass the PDF URL.
Both hosts were blocked in the build environment; text extraction is tested
on fixtures. Respect each site's terms: store paraphrased observations and
links only, never the full report text (raw text stays in data/raw, gitignored).
"""
from __future__ import annotations

import hashlib
import io
from datetime import date

from bs4 import BeautifulSoup

from .common import RAW, polite_get
from .extract import extract_observations

ISW_URL = "https://www.criticalthreats.org/analysis/russian-offensive-campaign-assessment-{slug}"


def isw_slug(d: date) -> str:
    return f"{d.strftime('%B').lower()}-{d.day}-{d.year}"


def html_paragraphs(html: str) -> list[str]:
    """Every paragraph and list item of the page body, in order (works on the JS-templated ISW mirror)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    out = []
    for el in soup.find_all(["p", "li", "h1", "h2", "h3"]):
        text = " ".join(el.get_text(" ").split())
        if text and "{{" not in text and (not out or out[-1] != text):
            out.append(text)
    return out


def html_to_text(html: str) -> str:
    return "\n".join(html_paragraphs(html))


TACTIC_KEYWORDS = (
    "drone", "uav", "fpv", "fiber", "fibre", "interceptor", "shahed", "geran", "electronic warfare", " ew ",
    "jamm", "infiltrat", "motorcycle", "glide bomb", "kab", "mechanized", "armored", "assault group",
    "small group", "robot", "unmanned ground", "ugv", "logistic", "kill zone", "rubikon", "artillery",
    "counteroffensive", "counterattack", "cope cage", "turtle",
)


SKIP_KEYWORDS = ("iran", "refinery", "oil ", "diesel", "trump", "kremlin is", "milblogger for his coverage",
                 "war crimes", "sanction", "negotiat", "ceasefire talks", "humanitarian aid station")


def tactic_digest(html: str, max_chars: int = 5500) -> str:
    """ISW's Key Takeaways plus front-line paragraphs that mention a tactic keyword, capped in length.

    This is what a reader (Claude in the daily task) codes into observations, so a
    long daily report becomes a few thousand characters of tactic-relevant text.
    Section headers, the standing war-crimes notice and strategic/diplomatic items are left out.
    """
    paras = html_paragraphs(html)
    takeaways, body, in_takeaways = [], [], False
    for p in paras:
        low = f" {p.lower()} "
        if low.strip().startswith("key takeaways"):
            in_takeaways = True
            continue
        is_sentence = p.rstrip().endswith(".") and len(p) > 40
        if in_takeaways:
            if is_sentence and not any(k in low for k in SKIP_KEYWORDS) and "we do not report" not in low:
                takeaways.append("TAKEAWAY: " + p)
            elif not is_sentence:
                in_takeaways = False
            continue
        if len(p) > 80 and any(k in low for k in TACTIC_KEYWORDS) and not any(k in low for k in SKIP_KEYWORDS):
            body.append(p)
    text, total = [], 0
    for p in takeaways + body:
        if total + len(p) > max_chars:
            continue
        text.append(p)
        total += len(p)
    return "\n\n".join(text)


def pdf_to_text(data: bytes) -> str:
    # Imported here: pypdf pulls in `cryptography`, which is broken in some fresh
    # containers; only RUSI PDF parsing needs it, so it must not block the daily refresh.
    from pypdf import PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def _cached(url: str) -> bytes:
    path = RAW / "reports" / hashlib.sha1(url.encode()).hexdigest()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(polite_get(url, min_interval=5.0).content)
    return path.read_bytes()


def isw_day(d: date) -> list[dict]:
    url = ISW_URL.format(slug=isw_slug(d))
    text = html_to_text(_cached(url).decode("utf-8", "replace"))
    return extract_observations(text, source_org="ISW",
                                source_title=f"Russian Offensive Campaign Assessment, {d:%B} {d.day}, {d.year}",
                                source_url=url, report_date=d.isoformat())


def rusi_paper(pdf_url: str, title: str, published: date) -> list[dict]:
    text = pdf_to_text(_cached(pdf_url))
    return extract_observations(text, source_org="RUSI", source_title=title,
                                source_url=pdf_url, report_date=published.isoformat())
