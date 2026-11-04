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


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    body = soup.find("article") or soup.find("main") or soup.body or soup
    lines = (ln.strip() for ln in body.get_text("\n").splitlines())
    return "\n".join(ln for ln in lines if ln)


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
