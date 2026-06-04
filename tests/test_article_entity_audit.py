"""Tests for the article_entity_audit module."""

from __future__ import annotations

from blogagent.tools.article_entity_audit import (
    audit_article_entities,
)
from blogagent.workflow.query_contract import build_query_contract
from blogagent.workflow.state import EvidenceItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fragrance_contract(count: int = 7):
    return build_query_contract(
        f"{count} best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=count,
    )


def _explainer_contract():
    return build_query_contract(
        "why elephants are heavy",
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
    )


def _make_evidence(
    fact: str,
    url: str = "https://allure.com",
    title: str = "Test",
) -> EvidenceItem:
    return EvidenceItem(
        fact=fact,
        source_url=url,
        source_title=title,
        publisher_domain=url.split("/")[2] if "://" in url else "allure.com",
        confidence=0.9,
        used_for="recommendation",
    )


_3_PICK_ARTICLE = """# 3 Best Perfumes for Summer

These fragrances stood out in our evidence-backed testing.

## Quick Picks

- Ouai Melrose Place Eau de Parfum — best for summer days
- Dolce & Gabbana Light Blue Eau de Toilette — best for freshness
- Maison Margiela Replica Afternoon Delight — best for romance

## How We Chose

We reviewed top editorial sources.

## Final Takeaway

These three represent the strongest evidence-backed picks.
"""

_7_PICK_ARTICLE = """# 7 Best Perfumes for Summer

## Quick Picks

- Ouai Melrose Place Eau de Parfum — summer floral
- Dolce & Gabbana Light Blue Eau de Toilette — citrus fresh
- Maison Margiela Replica Afternoon Delight Eau de Toilette
- Tom Ford Soleil Blanc — solar warmth
- Jo Malone London Wood Sage & Sea Salt — coastal
- Chanel Chance Eau Tendre — floral classic
- Dior Miss Dior Blooming Bouquet — romantic

## Final Takeaway

All seven are editorial picks.
"""


_ALLOWED_CANDIDATES = [
    {
        "name": "Ouai Melrose Place Eau de Parfum",
        "normalized_name": "ouai melrose place eau de parfum",
        "entity_type": "specific_product",
        "usable": True,
        "source_urls": ["https://allure.com"],
        "source_quality": "high",
    },
    {
        "name": "Dolce & Gabbana Light Blue Eau de Toilette",
        "normalized_name": "dolce & gabbana light blue eau de toilette",
        "entity_type": "specific_product",
        "usable": True,
        "source_urls": ["https://allure.com"],
        "source_quality": "high",
    },
    {
        "name": "Maison Margiela Replica Afternoon Delight Eau de Toilette",
        "normalized_name": "maison margiela replica afternoon delight eau de toilette",
        "entity_type": "specific_product",
        "usable": True,
        "source_urls": ["https://allure.com"],
        "source_quality": "high",
    },
]


# ---------------------------------------------------------------------------
# audit_article_entities
# ---------------------------------------------------------------------------


class TestAuditArticleEntities:
    def test_explainer_skips_audit(self):
        audit = audit_article_entities(
            article_markdown="Some text about elephants.",
            allowed_candidates=[],
            query_contract=_explainer_contract(),
            evidence_table=[],
            source_quality_scores=[],
        )
        assert audit.passes is True
        assert audit.article_entities_count == 0

    def test_counts_3_recommendations(self):
        evidence = [_make_evidence("Ouai Melrose Dolce Gabbana Maison Margiela", "https://allure.com")]
        quality = [{"url": "https://allure.com", "quality": "high", "title": "Allure"}]

        audit = audit_article_entities(
            article_markdown=_3_PICK_ARTICLE,
            allowed_candidates=_ALLOWED_CANDIDATES,
            query_contract=_fragrance_contract(3),
            evidence_table=evidence,
            source_quality_scores=quality,
        )

        assert audit.article_entities_count == 3, (
            f"Expected 3 recommendations, got {audit.article_entities_count}"
        )

    def test_no_section_headings_counted(self):
        article = """# Best Perfumes

## Quick Picks

- Ouai Melrose Place Eau de Parfum — summer pick
- Dolce & Gabbana Light Blue Eau de Toilette — fresh pick

## How We Chose

Our methodology.

## Final Takeaway

These are the picks.
"""
        evidence = [_make_evidence("Ouai Melrose Dolce Gabbana", "https://allure.com")]
        quality = [{"url": "https://allure.com", "quality": "high", "title": "Allure"}]
        audit = audit_article_entities(
            article_markdown=article,
            allowed_candidates=_ALLOWED_CANDIDATES[:2],
            query_contract=_fragrance_contract(2),
            evidence_table=evidence,
            source_quality_scores=quality,
        )
        # Section headings (How We Chose, Final Takeaway) must not be counted
        assert "How We Chose" not in (audit.section_heading_false_positives or [])
        assert audit.article_entities_count == 2

    def test_7_pick_article_counts_7(self):
        candidates_7 = _ALLOWED_CANDIDATES + [
            {
                "name": "Tom Ford Soleil Blanc",
                "normalized_name": "tom ford soleil blanc",
                "entity_type": "specific_product",
                "usable": True,
                "source_urls": ["https://allure.com"],
                "source_quality": "high",
            },
            {
                "name": "Jo Malone London Wood Sage & Sea Salt",
                "normalized_name": "jo malone london wood sage & sea salt",
                "entity_type": "specific_product",
                "usable": True,
                "source_urls": ["https://allure.com"],
                "source_quality": "high",
            },
            {
                "name": "Chanel Chance Eau Tendre",
                "normalized_name": "chanel chance eau tendre",
                "entity_type": "specific_product",
                "usable": True,
                "source_urls": ["https://allure.com"],
                "source_quality": "high",
            },
            {
                "name": "Dior Miss Dior Blooming Bouquet",
                "normalized_name": "dior miss dior blooming bouquet",
                "entity_type": "specific_product",
                "usable": True,
                "source_urls": ["https://allure.com"],
                "source_quality": "high",
            },
        ]
        evidence = [_make_evidence("multiple perfumes", "https://allure.com")]
        quality = [{"url": "https://allure.com", "quality": "high", "title": "Allure"}]
        audit = audit_article_entities(
            article_markdown=_7_PICK_ARTICLE,
            allowed_candidates=candidates_7,
            query_contract=_fragrance_contract(7),
            evidence_table=evidence,
            source_quality_scores=quality,
        )
        assert audit.article_entities_count == 7
