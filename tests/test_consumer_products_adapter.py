from __future__ import annotations

from blogagent.tools.domain_adapters.consumer_products import GenericProductAdapter
from blogagent.tools.entity_candidate_ledger import build_candidate_ledger
from blogagent.workflow.query_contract import build_query_contract
from blogagent.workflow.state import EvidenceItem, SourcePacket


def _contract(count: int | None = 5):
    return build_query_contract(
        "5 best affordable luxury watches",
        is_recommendation=True,
        is_financial=False,
        requested_count=count,
    )


def _quality(url: str = "https://www.hodinkee.com/best-watches") -> list[dict]:
    return [
        {
            "url": url,
            "quality": "high",
            "title": "Best Affordable Watches",
            "source_type": "editorial",
        }
    ]


class TestGenericProductAdapter:
    def setup_method(self):
        self.adapter = GenericProductAdapter()
        self.contract = _contract()

    def test_accepts_known_specific_products(self):
        accepted = [
            "Tissot PRX Quartz",
            "Seiko 5 Sports",
            "Hamilton Khaki Field Mechanical",
            "Orient Bambino",
            "Citizen Tsuyosa",
            "Sony WH-1000XM5",
            "Away Bigger Carry-On",
            "Herman Miller Aeron",
        ]
        for name in accepted:
            assert self.adapter.is_valid_entity(name, self.contract) is True, name

    def test_rejects_generic_phrases(self):
        rejected = [
            "affordable luxury watches",
            "best luxury watches",
            "buying guide",
            "how we chose",
            "final takeaway",
            "shop now",
            "under $500",
            "watch brands",
        ]
        for name in rejected:
            assert self.adapter.is_valid_entity(name, self.contract) is False, name

    def test_canonicalizes_prices_and_sale_text(self):
        assert self.adapter.canonicalize("Tissot PRX Quartz - on sale $395") == (
            "Tissot PRX Quartz"
        )


class TestConsumerProductLedger:
    def test_ledger_with_five_clean_watch_candidates_is_strong(self):
        text = (
            "Tested affordable picks include **Tissot PRX Quartz**, **Seiko 5 Sports**, "
            "**Hamilton Khaki Field Mechanical**, **Orient Bambino**, and "
            "**Citizen Tsuyosa**. These reviewed watches are budget-friendly picks."
        )
        source = SourcePacket(
            url="https://www.hodinkee.com/best-watches",
            title="Best Affordable Watches",
            domain="hodinkee.com",
            extracted_text=text,
        )
        evidence = [
            EvidenceItem(
                fact=text,
                source_url=source.url,
                source_title=source.title,
                publisher_domain=source.domain,
                confidence=0.9,
                used_for="recommendation",
            )
        ]

        ledger = build_candidate_ledger(
            sources=[source],
            evidence_table=evidence,
            query_contract=_contract(5),
            source_quality_scores=_quality(source.url),
        )

        assert ledger.table_quality == "strong"
        assert ledger.usable_count == 5
        assert "Tissot PRX Quartz" in ledger.usable_names

    def test_ledger_with_generic_category_phrases_is_failed(self):
        text = (
            "**Affordable Luxury Watches** and **Best Luxury Watches** are headings. "
            "**Watch Brands** and **Under $500** are not specific products."
        )
        source = SourcePacket(
            url="https://www.hodinkee.com/best-watches",
            title="Best Affordable Watches",
            domain="hodinkee.com",
            extracted_text=text,
        )
        evidence = [
            EvidenceItem(
                fact=text,
                source_url=source.url,
                source_title=source.title,
                publisher_domain=source.domain,
                confidence=0.9,
                used_for="recommendation",
            )
        ]

        ledger = build_candidate_ledger(
            sources=[source],
            evidence_table=evidence,
            query_contract=_contract(5),
            source_quality_scores=_quality(source.url),
        )

        assert ledger.table_quality == "failed"
        assert ledger.usable_count == 0

    def test_ledger_with_three_clean_candidates_for_requested_five_is_limited(self):
        text = (
            "Tested picks include **Tissot PRX Quartz**, **Seiko 5 Sports**, "
            "and **Hamilton Khaki Field Mechanical**."
        )
        source = SourcePacket(
            url="https://www.hodinkee.com/best-watches",
            title="Best Affordable Watches",
            domain="hodinkee.com",
            extracted_text=text,
        )
        evidence = [
            EvidenceItem(
                fact=text,
                source_url=source.url,
                source_title=source.title,
                publisher_domain=source.domain,
                confidence=0.9,
                used_for="recommendation",
            )
        ]

        ledger = build_candidate_ledger(
            sources=[source],
            evidence_table=evidence,
            query_contract=_contract(5),
            source_quality_scores=_quality(source.url),
        )

        assert ledger.table_quality == "limited"
        assert ledger.usable_count == 3

    def test_counted_recommendation_empty_ledger_is_not_not_required(self):
        ledger = build_candidate_ledger(
            sources=[],
            evidence_table=[],
            query_contract=_contract(5),
            source_quality_scores=[],
        )

        assert ledger.table_quality == "failed"
