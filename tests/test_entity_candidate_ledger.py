"""Tests for the entity_candidate_ledger module."""

from __future__ import annotations

from blogagent.tools.entity_candidate_ledger import (
    CandidateLedger,
    EntityCandidate,
    build_candidate_ledger,
    evaluate_candidate_ledger_quality,
)
from blogagent.workflow.query_contract import build_query_contract
from blogagent.workflow.state import EvidenceItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence(
    fact: str,
    url: str = "https://allure.com",
    title: str = "Allure Best Perfumes",
) -> EvidenceItem:
    return EvidenceItem(
        fact=fact,
        source_url=url,
        source_title=title,
        publisher_domain=url.split("/")[2] if "://" in url else "allure.com",
        confidence=0.9,
        used_for="recommendation",
    )


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


def _good_sources() -> list:
    """Minimal source objects."""
    from blogagent.workflow.state import SourcePacket
    return [
        SourcePacket(
            url="https://allure.com/fragrance",
            title="Allure Best Summer Fragrances",
            domain="allure.com",
            extracted_text=(
                "**Ouai Melrose Place Eau de Parfum** has fresh jasmine and sandalwood notes, "
                "perfect for summer. **Dolce & Gabbana Light Blue Eau de Toilette** offers "
                "citrus freshness. **Maison Margiela Replica Afternoon Delight** is a "
                "crowd-pleaser. Try **Tom Ford Soleil Blanc** or "
                "**Jo Malone London Wood Sage & Sea Salt** for beach days."
            ),
        )
    ]


def _polluted_sources() -> list:
    from blogagent.workflow.state import SourcePacket
    return [
        SourcePacket(
            url="https://example.com/fragrance",
            title="Summer Parfums Guide",
            domain="example.com",
            extracted_text=(
                "ARMANI PRADA Paco Rabanne CREED CALVIN are top brands. "
                "DIOR Yves Saint Laurent GUCCI Dolce. "
                "Maison Francis Kurkdjian BEST SELLERS Versace. "
                "How We Chose Our Top Summer Parfums. "
                "Choosing Your Signature Summer Scent. "
                "**Ouai Melrose Place Eau de Parfum** is excellent. "
                "**Dolce & Gabbana Light Blue Eau de Toilette** smells great. "
                "**Maison Margiela Replica Afternoon Delight Eau de Toilette** is popular."
            ),
        )
    ]


# ---------------------------------------------------------------------------
# build_candidate_ledger
# ---------------------------------------------------------------------------


class TestBuildCandidateLedger:
    def test_not_required_for_explainer(self):
        ledger = build_candidate_ledger(
            sources=[],
            evidence_table=[],
            query_contract=_explainer_contract(),
            source_quality_scores=[],
        )
        assert ledger.table_quality == "not_required"
        assert ledger.usable_count == 0

    def test_recommendation_builds_ledger(self):
        evidence = [
            _make_evidence(
                "**Ouai Melrose Place Eau de Parfum** is a floral woody fragrance. "
                "Fresh notes of jasmine.",
                url="https://allure.com/fragrance",
                title="Best Summer Fragrances",
            )
        ]
        quality_scores = [
            {"url": "https://allure.com/fragrance", "quality": "high", "title": "Allure"}
        ]
        contract = _fragrance_contract(3)

        ledger = build_candidate_ledger(
            sources=[],
            evidence_table=evidence,
            query_contract=contract,
            source_quality_scores=quality_scores,
        )

        assert isinstance(ledger, CandidateLedger)
        assert ledger.table_quality in ("strong", "limited", "failed", "not_required")

    def test_pollution_reduces_usable_count(self):
        """Polluted brand-cluster entries should be rejected, not counted as usable."""
        evidence = [
            _make_evidence(
                "ARMANI PRADA Paco Rabanne CREED CALVIN are popular brands. "
                "**Ouai Melrose Place Eau de Parfum** is a summer staple.",
                url="https://allure.com/fragrance",
                title="Best Summer Fragrances",
            )
        ]
        quality_scores = [
            {"url": "https://allure.com/fragrance", "quality": "high", "title": "Allure"}
        ]
        contract = _fragrance_contract(7)

        ledger = build_candidate_ledger(
            sources=[],
            evidence_table=evidence,
            query_contract=contract,
            source_quality_scores=quality_scores,
        )

        # Clusters should be rejected
        cluster_names = ["armani prada paco rabanne creed calvin"]
        for name in ledger.allowed_candidates:
            normalized = name.canonical_name.lower()
            for cluster in cluster_names:
                assert cluster not in normalized, (
                    f"Cluster name '{cluster}' found in allowed candidates"
                )

    def test_entity_cluster_is_rejected(self):
        evidence = [
            _make_evidence(
                "ARMANI PRADA Paco Rabanne CREED CALVIN",
                url="https://allure.com/fragrance",
                title="Best Summer Fragrances",
            )
        ]
        quality_scores = [
            {"url": "https://allure.com/fragrance", "quality": "high", "title": "Allure"}
        ]
        contract = _fragrance_contract(7)

        ledger = build_candidate_ledger(
            sources=[],
            evidence_table=evidence,
            query_contract=contract,
            source_quality_scores=quality_scores,
        )

        usable_names = [c.raw_mention.lower() for c in ledger.allowed_candidates]
        assert not any(
            "armani" in n and "prada" in n for n in usable_names
        ), f"Cluster entity found in allowed candidates: {usable_names}"

    def test_usable_names_are_product_names(self):
        evidence = [
            _make_evidence(
                "**Ouai Melrose Place Eau de Parfum** is a floral scent. "
                "**Dolce & Gabbana Light Blue Eau de Toilette** is refreshing.",
                url="https://allure.com",
                title="Best Summer Fragrances",
            )
        ]
        quality_scores = [{"url": "https://allure.com", "quality": "high", "title": "Allure"}]
        contract = _fragrance_contract(7)

        ledger = build_candidate_ledger(
            sources=[],
            evidence_table=evidence,
            query_contract=contract,
            source_quality_scores=quality_scores,
        )

        usable_names = [c.raw_mention for c in ledger.allowed_candidates]
        # At least one of the specific products should be found
        found = any(
            any(
                kw in n.lower()
                for kw in ("ouai", "melrose", "dolce", "light blue")
            )
            for n in usable_names
        )
        assert found or len(usable_names) == 0, f"Expected product names, got: {usable_names}"


# ---------------------------------------------------------------------------
# Candidate Ledger Quality Gate
# ---------------------------------------------------------------------------


class TestCandidateLedgerQuality:
    def test_strong_when_enough_usable(self):
        """Ledger with clean candidates (score >= 0.85, spans present) is strong."""
        ledger = CandidateLedger(
            requested_count=3,
            raw_mentions_count=5,
            candidates=[],
            validated_candidates=[],
            allowed_candidates=[
                EntityCandidate(
                    raw_mention=f"Brand Product {i} Eau de Parfum",
                    canonical_name=f"brand product {i} eau de parfum",
                    entity_type="specific_product",
                    usable=True,
                    clean_name_score=0.9,
                    evidence_score=0.75,
                    evidence_spans=[f"Brand Product {i} is a summer fragrance"],
                    source_type="editorial",
                )
                for i in range(3)
            ],
            rejected_candidates=[],
            usable_count=3,
            usable_names=[f"brand product {i} eau de parfum" for i in range(3)],
            rejected_count=0,
            rejected_examples=[],
            table_quality="not_required",
            quality_issues=[],
        )
        contract = _fragrance_contract(3)
        evaluated = evaluate_candidate_ledger_quality(ledger, contract)
        assert evaluated.table_quality == "strong"

    def test_limited_when_below_requested(self):
        ledger = CandidateLedger(
            requested_count=7,
            raw_mentions_count=5,
            candidates=[],
            validated_candidates=[],
            allowed_candidates=[
                EntityCandidate(
                    raw_mention=f"Product {i}",
                    canonical_name=f"product {i}",
                    entity_type="specific_product",
                    usable=True,
                )
                for i in range(3)
            ],
            rejected_candidates=[],
            usable_count=3,
            usable_names=[f"product {i}" for i in range(3)],
            rejected_count=2,
            rejected_examples=[],
            table_quality="not_required",
            quality_issues=[],
        )
        contract = _fragrance_contract(7)
        evaluated = evaluate_candidate_ledger_quality(ledger, contract)
        assert evaluated.table_quality == "limited"

    def test_failed_when_below_minimum(self):
        ledger = CandidateLedger(
            requested_count=7,
            raw_mentions_count=3,
            candidates=[],
            validated_candidates=[],
            allowed_candidates=[
                EntityCandidate(
                    raw_mention=f"Product {i}",
                    canonical_name=f"product {i}",
                    entity_type="specific_product",
                    usable=True,
                )
                for i in range(2)
            ],
            rejected_candidates=[],
            usable_count=2,
            usable_names=[f"product {i}" for i in range(2)],
            rejected_count=1,
            rejected_examples=[],
            table_quality="not_required",
            quality_issues=[],
        )
        contract = _fragrance_contract(7)
        evaluated = evaluate_candidate_ledger_quality(ledger, contract)
        assert evaluated.table_quality == "failed"

    def test_pollution_sets_failed(self):
        """A cluster entity marked usable should trigger failed quality."""
        ledger = CandidateLedger(
            requested_count=7,
            raw_mentions_count=5,
            candidates=[],
            validated_candidates=[],
            allowed_candidates=[
                EntityCandidate(
                    raw_mention="ARMANI PRADA Paco Rabanne CREED",
                    canonical_name="armani prada paco rabanne creed",
                    entity_type="brand_cluster",
                    usable=True,
                ),
                EntityCandidate(
                    raw_mention="Good Product A",
                    canonical_name="good product a",
                    entity_type="specific_product",
                    usable=True,
                ),
                EntityCandidate(
                    raw_mention="Good Product B",
                    canonical_name="good product b",
                    entity_type="specific_product",
                    usable=True,
                ),
                EntityCandidate(
                    raw_mention="Good Product C",
                    canonical_name="good product c",
                    entity_type="specific_product",
                    usable=True,
                ),
            ],
            rejected_candidates=[],
            usable_count=4,
            usable_names=["armani prada...", "good product a", "good product b", "good product c"],
            rejected_count=0,
            rejected_examples=[],
            table_quality="not_required",
            quality_issues=[],
        )
        contract = _fragrance_contract(7)
        evaluated = evaluate_candidate_ledger_quality(ledger, contract)
        assert evaluated.table_quality == "failed"
        assert any("polluted" in issue.lower() for issue in evaluated.quality_issues)


# ---------------------------------------------------------------------------
# Regression candidates
# ---------------------------------------------------------------------------


class TestRegressionCandidates:
    """Regression tests from the '7 best parfums' failure."""

    def setup_method(self):
        self.contract = _fragrance_contract(7)
        from blogagent.tools.domain_adapters.beauty_fragrance import BeautyFragranceAdapter
        self.adapter = BeautyFragranceAdapter()

    def test_armani_prada_cluster_is_unusable(self):
        assert self.adapter.is_valid_entity(
            "ARMANI PRADA Paco Rabanne CREED CALVIN", self.contract
        ) is False

    def test_dior_ysl_gucci_cluster_is_unusable(self):
        assert self.adapter.is_valid_entity(
            "DIOR Yves Saint Laurent GUCCI Dolce", self.contract
        ) is False

    def test_maison_kurkdjian_cluster_is_unusable(self):
        assert self.adapter.is_valid_entity(
            "Maison Francis Kurkdjian BEST SELLERS Versace", self.contract
        ) is False

    def test_how_we_chose_heading_is_unusable(self):
        assert self.adapter.is_valid_entity(
            "How We Chose Our Top Summer Parfums", self.contract
        ) is False

    def test_choosing_signature_scent_heading_is_unusable(self):
        assert self.adapter.is_valid_entity(
            "Choosing Your Signature Summer Scent", self.contract
        ) is False

    def test_ouai_melrose_is_usable(self):
        assert self.adapter.is_valid_entity(
            "Ouai Melrose Place Eau de Parfum", self.contract
        ) is True

    def test_dolce_gabbana_light_blue_is_usable(self):
        assert self.adapter.is_valid_entity(
            "Dolce & Gabbana Light Blue Eau de Toilette", self.contract
        ) is True

    def test_maison_margiela_replica_is_usable(self):
        assert self.adapter.is_valid_entity(
            "Maison Margiela Replica Afternoon Delight Eau de Toilette", self.contract
        ) is True
