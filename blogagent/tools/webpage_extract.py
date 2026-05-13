"""webpage_extract tool.

Permission class: read_only (network read)

Extracts title, domain, author, date, and a bounded text excerpt from a URL.

- Mock URLs (*.example.dev, *.example.com, *.example.org, *.example.net)
  return a clearly-marked mock SourcePacket without any network call.
- Real URLs use httpx + BeautifulSoup4.
  Requires: uv add httpx beautifulsoup4
- Extraction is bounded to MAX_CHARS characters of text.
- Failures return an error SourcePacket; they do not raise.
"""

from __future__ import annotations

import os
import re
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from blogagent.workflow.state import SourcePacket

MAX_CHARS = 10_000
_MOCK_DOMAINS = re.compile(
    r"(example\.dev|example\.com|example\.org|example\.net|mock-source-\d+\.)",
    re.IGNORECASE,
)


class ExtractInput(BaseModel):
    url: str
    title: str
    domain: str


class ExtractOutput(BaseModel):
    packet: Optional[SourcePacket] = None
    error: Optional[str] = None
    warning: Optional[str] = None


def webpage_extract(input: ExtractInput) -> ExtractOutput:
    """Extract text from a URL. Falls back to mock for mock/example URLs."""
    if _is_mock_url(input.url):
        return _mock_extract(input)
    return _real_extract(input)


# ---------------------------------------------------------------------------
# Mock extraction
# ---------------------------------------------------------------------------

def _is_mock_url(url: str) -> bool:
    return bool(_MOCK_DOMAINS.search(url))


def _mock_extract(input: ExtractInput) -> ExtractOutput:
    packet = SourcePacket(
        url=input.url,
        title=input.title,
        domain=input.domain,
        publisher=input.domain,
        extracted_text=(
            f"[MOCK] Placeholder extracted content for '{input.title}'. "
            f"This is development/test data only and does not represent a real source."
        ),
        word_count=20,
        is_mock=True,
        extraction_status="mock",
    )
    return ExtractOutput(packet=packet)


# ---------------------------------------------------------------------------
# Real extraction via httpx + BeautifulSoup4
# ---------------------------------------------------------------------------

def _real_extract(input: ExtractInput) -> ExtractOutput:
    try:
        import httpx  # noqa: PLC0415
        from bs4 import BeautifulSoup  # noqa: PLC0415
    except ImportError as exc:
        return ExtractOutput(
            packet=_error_packet(input, "mock", f"Missing dependency: {exc}. Run: uv sync"),
            warning=f"httpx/beautifulsoup4 not installed; returning mock packet. {exc}",
        )

    timeout = int(os.getenv("BLOGAGENT_HTTP_TIMEOUT_SECONDS", "15"))
    domain = urlparse(input.url).netloc or input.domain

    try:
        resp = httpx.get(
            input.url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "BlogAgent/0.1 (research bot; non-commercial)"},
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        title = _extract_title(soup, input.title)
        author = _extract_author(soup)
        date = _extract_date(soup)
        text = _extract_text(soup)

        packet = SourcePacket(
            url=input.url,
            title=title,
            domain=domain,
            publisher=domain,
            extracted_text=text,
            word_count=len(text.split()),
            author=author,
            date=date,
            is_mock=False,
            extraction_status="success",
        )
        return ExtractOutput(packet=packet)

    except Exception as exc:
        err = str(exc)
        return ExtractOutput(
            packet=_error_packet(input, domain, err),
            error=err,
        )


def _error_packet(input: ExtractInput, domain: str, error: str) -> SourcePacket:
    return SourcePacket(
        url=input.url,
        title=input.title,
        domain=domain,
        publisher=domain,
        extracted_text="",
        word_count=0,
        is_mock=False,
        extraction_status="failed",
        error_message=error,
    )


def _extract_title(soup: "BeautifulSoup", fallback: str) -> str:  # type: ignore[name-defined]
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return str(og["content"]).strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return fallback


def _extract_author(soup: "BeautifulSoup") -> str:  # type: ignore[name-defined]
    for attr in ("author", "article:author"):
        tag = soup.find("meta", attrs={"name": attr}) or soup.find("meta", property=attr)
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    tag = soup.find(attrs={"class": re.compile(r"author", re.I)})
    if tag:
        return tag.get_text(strip=True)[:100]
    return ""


def _extract_date(soup: "BeautifulSoup") -> str:  # type: ignore[name-defined]
    for attr in ("article:published_time", "datePublished"):
        tag = soup.find("meta", property=attr) or soup.find("meta", attrs={"name": attr})
        if tag and tag.get("content"):
            return str(tag["content"])[:20]
    time_tag = soup.find("time")
    if time_tag:
        return (time_tag.get("datetime") or time_tag.get_text(strip=True))[:20]
    return ""


def _extract_text(soup: "BeautifulSoup") -> str:  # type: ignore[name-defined]
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    return text[:MAX_CHARS]
