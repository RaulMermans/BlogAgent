"""source_score tool.

Permission class: read_only

Deterministic scoring based on:
- Domain credibility (known trusted domains, .edu/.gov TLDs)
- Text length (proxy for content depth)
- Keyword overlap with the topic (relevance)

Mock sources receive low uniform scores and are flagged is_mock=True.
No LLM scoring in MVP.
"""

from __future__ import annotations

from pydantic import BaseModel

from blogagent.workflow.state import SourcePacket, SourceScore

_TRUSTED_DOMAINS = frozenset(
    {
        "wikipedia.org",
        "nature.com",
        "science.org",
        "ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "britannica.com",
        "bbc.com",
        "reuters.com",
        "apnews.com",
        "nytimes.com",
        "theguardian.com",
        "washingtonpost.com",
        "sciencedirect.com",
        "arxiv.org",
        "ieee.org",
        "acm.org",
        "jstor.org",
        "who.int",
        "cdc.gov",
        "nih.gov",
        "nasa.gov",
        "noaa.gov",
    }
)

_MODERATE_DOMAINS = frozenset(
    {
        "medium.com",
        "substack.com",
        "forbes.com",
        "wired.com",
        "techcrunch.com",
        "arstechnica.com",
        "theatlantic.com",
        "vox.com",
        "slate.com",
        "salon.com",
    }
)

_HIGH_TEXT_THRESHOLD = 2_000
_LOW_TEXT_THRESHOLD = 200


class ScoreInput(BaseModel):
    packet: SourcePacket
    topic: str


def source_score(input: ScoreInput) -> SourceScore:
    """Score a source deterministically. Mock sources return low uniform scores."""
    packet = input.packet

    if packet.is_mock or packet.extraction_status == "mock":
        return SourceScore(
            url=packet.url,
            title=packet.title,
            domain=packet.domain,
            credibility_score=0.3,
            relevance_score=0.3,
            recency_score=0.5,
            overall_score=0.3,
            notes="Mock source — scores are placeholders, not real assessments.",
            is_mock=True,
        )

    if packet.extraction_status == "failed":
        return SourceScore(
            url=packet.url,
            title=packet.title,
            domain=packet.domain,
            credibility_score=0.0,
            relevance_score=0.0,
            recency_score=0.0,
            overall_score=0.0,
            notes=f"Extraction failed — cannot score. Error: {packet.error_message}",
            is_mock=False,
        )

    credibility = _score_credibility(packet.domain)
    relevance = _score_relevance(packet.extracted_text, input.topic)
    recency = _score_recency(packet.date)
    overall = round((credibility * 0.4 + relevance * 0.4 + recency * 0.2), 3)

    notes = (
        f"Credibility: {credibility:.2f} (domain: {packet.domain}), "
        f"Relevance: {relevance:.2f}, Recency: {recency:.2f}"
    )

    return SourceScore(
        url=packet.url,
        title=packet.title,
        domain=packet.domain,
        credibility_score=credibility,
        relevance_score=relevance,
        recency_score=recency,
        overall_score=overall,
        notes=notes,
        is_mock=False,
    )


def _score_credibility(domain: str) -> float:
    d = domain.lower().strip()
    for trusted in _TRUSTED_DOMAINS:
        if trusted in d:
            return 0.9
    for moderate in _MODERATE_DOMAINS:
        if moderate in d:
            return 0.6
    if d.endswith(".edu") or d.endswith(".gov"):
        return 0.85
    if d.endswith(".org"):
        return 0.55
    if d.endswith(".com") or d.endswith(".net"):
        return 0.4
    return 0.35


def _score_relevance(text: str, topic: str) -> float:
    if not text or not topic:
        return 0.0
    topic_words = {w.lower() for w in topic.split() if len(w) > 3}
    if not topic_words:
        return 0.5
    text_lower = text.lower()
    matches = sum(1 for w in topic_words if w in text_lower)
    base = matches / len(topic_words)
    length_bonus = 0.1 if len(text) >= _HIGH_TEXT_THRESHOLD else 0.0
    length_penalty = -0.1 if len(text) < _LOW_TEXT_THRESHOLD else 0.0
    return min(max(base + length_bonus + length_penalty, 0.0), 1.0)


def _score_recency(date: str) -> float:
    """Return a score based on parsed year if available; 0.5 otherwise."""
    if not date:
        return 0.5
    import re  # noqa: PLC0415

    m = re.search(r"(20\d{2})", date)
    if not m:
        return 0.5
    year = int(m.group(1))
    if year >= 2023:
        return 0.9
    if year >= 2020:
        return 0.7
    if year >= 2015:
        return 0.5
    return 0.3
