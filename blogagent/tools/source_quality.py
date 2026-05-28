"""Source quality classification — deterministic heuristic based on domain.

Permission class: read_only

Classifies each scored source as high / medium / low quality based on domain
reputation heuristics. This is separate from source_score (which computes
credibility/relevance/recency) and provides a simpler editorial quality label
used by the quality evaluator.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from blogagent.workflow.state import SourceScore

# User-generated / social platforms — low editorial authority.
_LOW_QUALITY_DOMAINS: frozenset[str] = frozenset(
    {
        "quora.com",
        "reddit.com",
        "instagram.com",
        "tiktok.com",
        "pinterest.com",
        "twitter.com",
        "x.com",
        "facebook.com",
        "tumblr.com",
        "yelp.com",
        "answers.yahoo.com",
        "ask.com",
    }
)

# Recognised editorial / expert / official publications — high authority.
_HIGH_QUALITY_DOMAINS: frozenset[str] = frozenset(
    {
        # General editorial
        "wikipedia.org",
        "britannica.com",
        "bbc.com",
        "reuters.com",
        "apnews.com",
        "nytimes.com",
        "theguardian.com",
        "washingtonpost.com",
        "theatlantic.com",
        "wired.com",
        # Science / academic
        "nature.com",
        "science.org",
        "ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "sciencedirect.com",
        "arxiv.org",
        "ieee.org",
        "acm.org",
        "jstor.org",
        # Government / health
        "who.int",
        "cdc.gov",
        "nih.gov",
        "nasa.gov",
        "noaa.gov",
        # Consumer / product review editorial
        "wirecutter.com",
        "pcmag.com",
        "techradar.com",
        "rtings.com",
        "goodhousekeeping.com",
        "byrdie.com",
        "allure.com",
        "seriouseats.com",
        "epicurious.com",
        "thespruce.com",
        "nymag.com",
        "fragrantica.com",
        "basenotes.net",
    }
)


class SourceQuality(BaseModel):
    url: str
    title: str
    quality: Literal["high", "medium", "low"]
    reason: str


def classify_source_quality(source: SourceScore) -> SourceQuality:
    """Classify a scored source as high / medium / low quality."""
    domain = source.domain.lower().strip()

    # Mock placeholder sources — always low quality.
    if source.is_mock:
        return SourceQuality(
            url=source.url,
            title=source.title,
            quality="low",
            reason="Mock placeholder source — not a real publication",
        )

    for low_domain in _LOW_QUALITY_DOMAINS:
        if low_domain in domain:
            return SourceQuality(
                url=source.url,
                title=source.title,
                quality="low",
                reason=(
                    f"{domain} is a user-generated or social platform "
                    "with low editorial authority"
                ),
            )

    for high_domain in _HIGH_QUALITY_DOMAINS:
        if high_domain in domain:
            return SourceQuality(
                url=source.url,
                title=source.title,
                quality="high",
                reason=f"{domain} is a recognised editorial or expert publication",
            )

    if domain.endswith(".edu"):
        return SourceQuality(
            url=source.url,
            title=source.title,
            quality="high",
            reason=f"{domain} is an accredited educational institution",
        )
    if domain.endswith(".gov"):
        return SourceQuality(
            url=source.url,
            title=source.title,
            quality="high",
            reason=f"{domain} is a government domain",
        )

    return SourceQuality(
        url=source.url,
        title=source.title,
        quality="medium",
        reason=f"{domain} is an unclassified source — quality not confirmed",
    )
