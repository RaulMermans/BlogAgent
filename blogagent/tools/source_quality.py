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
        "youtube.com",  # video platform — low editorial authority for written product rec
    }
)

# Fragrantica forum path patterns — community content, not editorial reviews.
# The domain may be high-authority editorial OR a user forum; URL path disambiguates.
_FRAGRANTICA_FORUM_PATHS: tuple[str, ...] = (
    "/forum/",
    "/community/",
    "/board/",
    "/thread/",
    "/user/",
    "/member/",
)

# Retailer/editorial hybrids and niche databases — medium quality
_MEDIUM_QUALITY_DOMAINS: frozenset[str] = frozenset(
    {
        "scentbird.com",
        "fragrantica.com",  # community/database — medium; editorial content only
        "perfumania.com",
        "thebeautylookbook.com",  # retailer-editorial hybrid
        "beautybay.com",
        "sephora.com",
        "ulta.com",
        "nordstrom.com",
        "cultbeauty.co.uk",
        "spacenk.com",
        "bluemercury.com",  # prestige retailer with editorial content
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
        "realsimple.com",
        "seriouseats.com",
        "epicurious.com",
        "thespruce.com",
        "nymag.com",
        "basenotes.net",
        # Beauty / lifestyle / fragrance editorial
        "byrdie.com",
        "allure.com",
        "allure.ph",
        "vogue.com",
        "harpersbazaar.com",
        "elle.com",
        "cosmopolitan.com",
        "thecut.com",
        "whowhatwear.com",
        "gq.com",
        "esquire.com",
        "the-independent.com",
        "independent.co.uk",
        "marieclaire.com",
        "editorialist.com",
    }
)


SourceType = Literal["editorial", "retailer_editorial", "forum", "social", "video", "unknown"]


class SourceQuality(BaseModel):
    url: str
    title: str
    quality: Literal["high", "medium", "low"]
    reason: str
    source_type: SourceType = "unknown"


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
            source_type="unknown",
        )

    for low_domain in _LOW_QUALITY_DOMAINS:
        if low_domain in domain:
            source_type: Literal["social", "video"] = (
                "video" if "youtube.com" in domain else "social"
            )
            return SourceQuality(
                url=source.url,
                title=source.title,
                quality="low",
                reason=(
                    f"{domain} is a user-generated or social platform with low editorial authority"
                ),
                source_type=source_type,
            )

    # Fragrantica forum/community pages: community content, not editorial — medium quality.
    url_lower = source.url.lower()
    if "fragrantica.com" in domain:
        is_forum = any(p in url_lower for p in _FRAGRANTICA_FORUM_PATHS)
        quality = "low" if is_forum else "medium"
        reason = (
            "fragrantica.com forum/community page — user-generated content"
            if is_forum
            else "fragrantica.com is a fragrance database with mixed editorial/community content"
        )
        return SourceQuality(
            url=source.url,
            title=source.title,
            quality=quality,  # type: ignore[arg-type]
            reason=reason,
            source_type="forum" if is_forum else "retailer_editorial",
        )

    for high_domain in _HIGH_QUALITY_DOMAINS:
        if high_domain in domain:
            return SourceQuality(
                url=source.url,
                title=source.title,
                quality="high",
                reason=f"{domain} is a recognised editorial or expert publication",
                source_type="editorial",
            )

    for med_domain in _MEDIUM_QUALITY_DOMAINS:
        if med_domain in domain:
            return SourceQuality(
                url=source.url,
                title=source.title,
                quality="medium",
                reason=f"{domain} is a retailer/editorial hybrid with moderate authority",
                source_type="retailer_editorial",
            )

    if domain.endswith(".edu"):
        return SourceQuality(
            url=source.url,
            title=source.title,
            quality="high",
            reason=f"{domain} is an accredited educational institution",
            source_type="editorial",
        )
    if domain.endswith(".gov"):
        return SourceQuality(
            url=source.url,
            title=source.title,
            quality="high",
            reason=f"{domain} is a government domain",
            source_type="editorial",
        )

    return SourceQuality(
        url=source.url,
        title=source.title,
        quality="medium",
        reason=f"{domain} is an unclassified source — quality not confirmed",
        source_type="unknown",
    )
