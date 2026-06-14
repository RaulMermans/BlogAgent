"""Tests for Candidate Cleanliness Gate v2.

Verifies that malformed, prose-fragment, and social-residue candidates are
rejected with precise reasons, and that clean product names pass.

Regression: "7 best parfums for summer" — several candidates were incorrectly
marked usable because clean_name_score always returned 1.0 and evidence spans
were not required.
"""

from __future__ import annotations

from blogagent.tools.domain_adapters.beauty_fragrance import BeautyFragranceAdapter
from blogagent.tools.entity_candidate_ledger import (
    CandidateLedger,
    EntityCandidate,
    _apply_cleanliness_gate_v2,
    _detect_prose_fragment,
    evaluate_candidate_ledger_quality,
    score_clean_candidate_name,
)
from blogagent.workflow.query_contract import build_query_contract


def _fragrance_contract(count: int = 7):
    return build_query_contract(
        f"{count} best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=count,
    )


# ---------------------------------------------------------------------------
# Score clean candidate name
# ---------------------------------------------------------------------------


class TestScoreCleanCandidateName:
    def test_clean_product_names_score_high(self):
        """Well-formed product names should score >= 0.75."""
        clean_names = [
            "Chanel Chance Eau Tendre",
            "Dior Miss Dior Blooming Bouquet",
            "Ouai Melrose Place Eau de Parfum",
            "Dolce & Gabbana Light Blue Eau de Toilette",
            "Maison Margiela Replica Afternoon Delight",
            "Tom Ford Soleil Blanc",
            "Jo Malone London Wood Sage & Sea Salt",
            "Guerlain Mon Guerlain",
            "Diptyque Philosykos Eau de Parfum",
        ]
        for name in clean_names:
            score = score_clean_candidate_name(name)
            assert score >= 0.75, f"Expected score >= 0.75 for '{name}', got {score:.2f}"

    def test_prose_fragments_score_low(self):
        """Sentence fragments and prose should score < 0.75."""
        bad_names = [
            'Dior " Fragrances with fruity',
            "Gucci Flora will always",
            "Valentino I went down a rabbit",
            "Armani can't get enough",
            "Tom Ford but on me it wasn't",
            "By Kilian 💕 Reply by wildevoodoo",
            "Kilian 💕 Reply by wildevoodoo Member",
            "Tom Ford 🌴🥥💕",
            "Dior but on me it wasn't",
        ]
        for name in bad_names:
            score = score_clean_candidate_name(name)
            assert score < 0.75, f"Expected score < 0.75 for '{name}', got {score:.2f}"

    def test_incomplete_candidates_score_low(self):
        """Truncated candidates ending with incomplete tokens should score < 0.75."""
        incomplete = [
            "Tom Ford Neroli Portofino Eau de",  # ends with "Eau de" (incomplete)
        ]
        for name in incomplete:
            score = score_clean_candidate_name(name)
            assert score < 0.75, f"Expected score < 0.75 for '{name}', got {score:.2f}"

    def test_emoji_scores_very_low(self):
        assert score_clean_candidate_name("Tom Ford 🌴🥥💕") < 0.3
        assert score_clean_candidate_name("By Kilian 💕 Reply by wildevoodoo") < 0.3

    def test_price_penalised_but_not_hard_rejected(self):
        """Price artifacts penalise score but don't necessarily make it < 0.75."""
        score_with_price = score_clean_candidate_name("Diptyque Philosykos Eau de Parfum $260")
        # The score should be penalised but the canonical version would strip the price
        assert score_with_price < 1.0

    def test_first_person_scores_low(self):
        assert score_clean_candidate_name("Dior I went down") < 0.75
        assert score_clean_candidate_name("Valentino my favorite") < 0.75

    def test_empty_name_scores_zero(self):
        assert score_clean_candidate_name("") == 0.0

    def test_all_caps_cluster_scores_low(self):
        assert score_clean_candidate_name("ARMANI PRADA CREED") < 0.75


# ---------------------------------------------------------------------------
# Detect prose fragment
# ---------------------------------------------------------------------------


class TestDetectProseFragment:
    def test_emoji_detected(self):
        reason = _detect_prose_fragment("Tom Ford 🌴🥥💕")
        assert reason is not None

    def test_social_residue_detected(self):
        reason = _detect_prose_fragment("By Kilian 💕 Reply by wildevoodoo")
        assert reason is not None

    def test_first_person_detected(self):
        reason = _detect_prose_fragment("Valentino I went down a rabbit")
        assert reason is not None

    def test_prose_verb_after_brand(self):
        reason = _detect_prose_fragment("Gucci Flora will always")
        assert reason is not None, "Expected prose fragment detection for 'will always'"

    def test_clean_name_no_fragment(self):
        reason = _detect_prose_fragment("ouai melrose place eau de parfum")
        assert reason is None

    def test_incomplete_ending_detected(self):
        reason = _detect_prose_fragment("tom ford neroli portofino eau de")
        assert reason is not None


# ---------------------------------------------------------------------------
# Beauty fragrance adapter — prose fragment rejection
# ---------------------------------------------------------------------------


class TestBeautyFragranceAdapterClean:
    def setup_method(self):
        self.adapter = BeautyFragranceAdapter()
        self.contract = _fragrance_contract(7)

    def test_prose_fragment_rejected(self):
        assert self.adapter.is_valid_entity("Gucci Flora will always", self.contract) is False

    def test_prose_fragment_with_first_person_rejected(self):
        assert self.adapter.is_valid_entity(
            "Valentino I went down a rabbit", self.contract
        ) is False

    def test_armani_cant_get_enough_rejected(self):
        assert self.adapter.is_valid_entity("Armani can't get enough", self.contract) is False

    def test_incomplete_eau_de_rejected(self):
        assert self.adapter.is_valid_entity(
            "Tom Ford Neroli Portofino Eau de", self.contract
        ) is False

    def test_valid_products_accepted(self):
        valid = [
            "Ouai Melrose Place Eau de Parfum",
            "Dolce & Gabbana Light Blue Eau de Toilette",
            "Maison Margiela Replica Afternoon Delight",
            "Tom Ford Soleil Blanc",
            "Dior Miss Dior Blooming Bouquet",
        ]
        for name in valid:
            assert self.adapter.is_valid_entity(name, self.contract) is True, (
                f"Expected {name!r} to be valid"
            )


# ---------------------------------------------------------------------------
# EntityCandidate cleanliness gate v2
# ---------------------------------------------------------------------------


class TestEntityCandidateCleanlinessGate:
    def setup_method(self):
        self.contract = _fragrance_contract(7)

    def _make_candidate(
        self,
        raw_mention: str,
        usable: bool = True,
        clean_name_score: float = 0.9,
        evidence_score: float = 0.75,
        evidence_spans: list[str] | None = None,
        supported_context: list[str] | None = None,
    ) -> EntityCandidate:
        return EntityCandidate(
            raw_mention=raw_mention,
            canonical_name=raw_mention.lower(),
            name=raw_mention.lower(),
            entity_type="specific_product",
            usable=usable,
            clean_name_score=clean_name_score,
            evidence_score=evidence_score,
            evidence_spans=evidence_spans or [],
            supported_context=supported_context or ["summer"],
        )

    def test_low_clean_name_score_rejects(self):
        cand = self._make_candidate("Gucci Flora will always", clean_name_score=0.4)
        result = _apply_cleanliness_gate_v2(cand, self.contract)
        assert result.usable is False
        assert "clean_name_score" in (result.rejection_reason or "")

    def test_low_evidence_score_is_reviewable_in_editorial_mode(self):
        cand = self._make_candidate("Dior Sauvage", evidence_score=0.5)
        result = _apply_cleanliness_gate_v2(cand, self.contract)
        assert result.usable is True
        assert result.candidate_confidence == "low"
        assert result.needs_review is True

    def test_empty_evidence_spans_are_reviewable_in_editorial_mode(self):
        cand = self._make_candidate("Chanel No 5", evidence_spans=[])
        result = _apply_cleanliness_gate_v2(cand, self.contract)
        assert result.usable is True
        assert result.candidate_confidence == "low"
        assert result.needs_review is True

    def test_clean_candidate_with_spans_passes(self):
        cand = self._make_candidate(
            "Ouai Melrose Place Eau de Parfum",
            evidence_spans=["Ouai Melrose Place is a popular summer fragrance"],
            clean_name_score=0.9,
            evidence_score=0.75,
        )
        result = _apply_cleanliness_gate_v2(cand, self.contract)
        assert result.usable is True

    def test_prose_fragment_in_name_rejects(self):
        # Score would be computed as < 0.75 before gate
        cand = self._make_candidate(
            "Valentino I went down a rabbit",
            clean_name_score=0.2,  # would be low after real scoring
            evidence_spans=["some text"],
        )
        result = _apply_cleanliness_gate_v2(cand, self.contract)
        assert result.usable is False


# ---------------------------------------------------------------------------
# Watch-topic candidates: bylines, nav/heading residue
# ---------------------------------------------------------------------------


def _watch_contract(count: int = 5):
    return build_query_contract(
        f"{count} best affordable luxury watches",
        is_recommendation=True,
        is_financial=False,
        requested_count=count,
    )


class TestWatchCandidateCleanlinessGate:
    def setup_method(self):
        self.contract = _watch_contract(5)

    def test_watch_candidate_gate_rejects_author_person(self):
        """A reviewer byline ("Written By John Smith...") must not be locked as a product."""
        cand = EntityCandidate(
            raw_mention="John Smith",
            canonical_name="John Smith",
            name="John Smith",
            entity_type="specific_product",
            usable=True,
            clean_name_score=0.9,
            evidence_score=0.8,
            evidence_spans=[
                "Written By John Smith, our senior watch reviewer covers affordable "
                "luxury picks."
            ],
            supported_context=["watches"],
        )
        result = _apply_cleanliness_gate_v2(cand, self.contract)
        assert result.usable is False
        assert result.entity_type == "person"
        assert "byline" in (result.rejection_reason or "").lower()

    def test_watch_candidate_gate_rejects_navigation_and_noise(self):
        """A heading/navigation fragment like "How To Choose The Best Watch" must be rejected."""
        name = "How To Choose The Best Watch"
        cand = EntityCandidate(
            raw_mention=name,
            canonical_name=name,
            name=name,
            entity_type="specific_product",
            usable=True,
            clean_name_score=score_clean_candidate_name(name),
            evidence_score=0.8,
            evidence_spans=["How to choose the best watch for everyday wear."],
            supported_context=["watches"],
        )
        result = _apply_cleanliness_gate_v2(cand, self.contract)
        assert result.usable is False
        assert "clean_name_score" in (result.rejection_reason or "")


# ---------------------------------------------------------------------------
# Source type propagation
# ---------------------------------------------------------------------------


class TestSourceTypePropagation:
    def test_source_type_inherited_from_quality_scores(self):
        from blogagent.tools.entity_candidate_ledger import build_candidate_ledger
        from blogagent.workflow.state import EvidenceItem, SourcePacket

        contract = _fragrance_contract(3)
        sources = [
            SourcePacket(
                url="https://allure.com/fragrance",
                title="Allure Best Perfumes",
                domain="allure.com",
                extracted_text=(
                    "**Ouai Melrose Place Eau de Parfum** is a floral woody summer fragrance. "
                    "**Dolce & Gabbana Light Blue Eau de Toilette** offers citrus freshness. "
                    "**Maison Margiela Replica Afternoon Delight** is a crowd favorite."
                ),
            )
        ]
        evidence = [
            EvidenceItem(
                fact="Ouai Melrose Place Eau de Parfum has fresh jasmine notes, ideal for summer.",
                source_url="https://allure.com/fragrance",
                source_title="Allure Best Perfumes",
                publisher_domain="allure.com",
                confidence=0.9,
                used_for="recommendation",
            )
        ]
        quality_scores = [
            {
                "url": "https://allure.com/fragrance",
                "quality": "high",
                "source_type": "editorial",
                "title": "Allure",
            }
        ]

        ledger = build_candidate_ledger(
            sources=sources,
            evidence_table=evidence,
            query_contract=contract,
            source_quality_scores=quality_scores,
        )

        # Any allowed candidate from allure.com should have source_type=editorial
        for cand in ledger.allowed_candidates:
            if "allure.com" in cand.source_urls:
                assert cand.source_type == "editorial", (
                    f"Expected source_type=editorial for {cand.canonical_name}"
                )


# ---------------------------------------------------------------------------
# Candidate ledger quality gate — clean candidates required for "strong"
# ---------------------------------------------------------------------------


class TestLedgerQualityGateClean:
    def setup_method(self):
        self.contract = _fragrance_contract(7)

    def _make_ledger(self, candidates: list[EntityCandidate]) -> CandidateLedger:
        allowed = [c for c in candidates if c.usable]
        rejected = [c for c in candidates if not c.usable]
        return CandidateLedger(
            requested_count=7,
            raw_mentions_count=len(candidates),
            candidates=candidates,
            validated_candidates=allowed,
            allowed_candidates=allowed,
            rejected_candidates=rejected,
            usable_count=len(allowed),
            usable_names=[c.canonical_name for c in allowed],
            rejected_count=len(rejected),
            rejected_examples=[],
            table_quality="not_required",
            quality_issues=[],
        )

    def test_ledger_with_7_clean_candidates_is_strong(self):
        candidates = [
            EntityCandidate(
                raw_mention=f"Fragrance Product {i}",
                canonical_name=f"fragrance product {i}",
                name=f"fragrance product {i}",
                entity_type="specific_product",
                usable=True,
                clean_name_score=0.9,
                evidence_score=0.75,
                evidence_spans=[f"Product {i} is a summer staple"],
                source_type="editorial",
            )
            for i in range(7)
        ]
        ledger = self._make_ledger(candidates)
        result = evaluate_candidate_ledger_quality(ledger, self.contract)
        assert result.table_quality == "strong", (
            f"Expected strong, got {result.table_quality}. Issues: {result.quality_issues}"
        )

    def test_ledger_with_malformed_allowed_candidate_is_not_strong(self):
        candidates = [
            EntityCandidate(
                raw_mention=f"Good Product {i}",
                canonical_name=f"good product {i}",
                name=f"good product {i}",
                entity_type="specific_product",
                usable=True,
                clean_name_score=0.9,
                evidence_score=0.75,
                evidence_spans=[f"Product {i} mentioned in source"],
                source_type="editorial",
            )
            for i in range(6)
        ]
        # Add a malformed candidate
        candidates.append(
            EntityCandidate(
                raw_mention="Gucci Flora will always",
                canonical_name="gucci flora will always",
                name="gucci flora will always",
                entity_type="specific_product",
                usable=True,
                clean_name_score=0.3,  # low — prose fragment
                evidence_score=0.75,
                evidence_spans=["some text"],
                source_type="editorial",
            )
        )
        ledger = self._make_ledger(candidates)
        result = evaluate_candidate_ledger_quality(ledger, self.contract)
        # Should not be strong because avg clean_name_score < 0.85
        assert result.table_quality != "strong", (
            "Expected non-strong quality due to malformed candidate"
        )

    def test_ledger_with_empty_spans_is_not_strong(self):
        candidates = [
            EntityCandidate(
                raw_mention=f"Good Product {i}",
                canonical_name=f"good product {i}",
                name=f"good product {i}",
                entity_type="specific_product",
                usable=True,
                clean_name_score=0.9,
                evidence_score=0.75,
                evidence_spans=[],  # empty spans
                source_type="editorial",
            )
            for i in range(7)
        ]
        ledger = self._make_ledger(candidates)
        result = evaluate_candidate_ledger_quality(ledger, self.contract)
        assert result.table_quality != "strong", (
            "Expected non-strong because all candidates have empty evidence_spans"
        )
        assert any("light source coverage" in issue for issue in result.quality_issues)

    def test_ledger_with_3_candidates_for_7_requested_is_limited(self):
        candidates = [
            EntityCandidate(
                raw_mention=f"Good Product {i}",
                canonical_name=f"good product {i}",
                name=f"good product {i}",
                entity_type="specific_product",
                usable=True,
                clean_name_score=0.9,
                evidence_score=0.75,
                evidence_spans=[f"Product {i} is mentioned in sources"],
                source_type="editorial",
            )
            for i in range(3)
        ]
        ledger = self._make_ledger(candidates)
        result = evaluate_candidate_ledger_quality(ledger, self.contract)
        assert result.table_quality == "limited", (
            f"Expected limited for 3/{self.contract.requested_count} candidates"
        )

    def test_ledger_with_fewer_than_minimum_is_failed(self):
        candidates = [
            EntityCandidate(
                raw_mention=f"Good Product {i}",
                canonical_name=f"good product {i}",
                name=f"good product {i}",
                entity_type="specific_product",
                usable=True,
                clean_name_score=0.9,
                evidence_score=0.75,
                evidence_spans=[f"Product {i}"],
                source_type="editorial",
            )
            for i in range(2)  # below minimum_publishable_items=3
        ]
        ledger = self._make_ledger(candidates)
        result = evaluate_candidate_ledger_quality(ledger, self.contract)
        assert result.table_quality == "failed"


# ---------------------------------------------------------------------------
# AnswerCountSnapshot status logic
# ---------------------------------------------------------------------------


class TestAnswerCountSnapshotLogic:
    def setup_method(self):
        self.contract = _fragrance_contract(7)

    def _make_allowed(self, count: int) -> list[dict]:
        return [
            {
                "candidate_id": f"cand{i}",
                "canonical_name": f"product {i}",
                "name": f"product {i}",
                "usable": True,
                "source_quality": "high",
                "source_type": "editorial",
            }
            for i in range(count)
        ]

    def test_allowed_9_article_2_is_failed_not_evidence_limited(self):
        from blogagent.tools.article_entity_audit import (
            EntityAudit,
            build_answer_count_snapshot,
        )
        from blogagent.tools.draft_candidate_compliance import DraftCandidateCompliance

        allowed = self._make_allowed(9)
        audit = EntityAudit(
            article_entities_count=2,
            grounded_entities_count=1,
            allowed_entities_count=9,
            passes=False,
        )
        compliance = DraftCandidateCompliance(
            passes=False,
            requested_count=7,
            allowed_count=9,
            recommended_count=2,
            allowed_recommended_count=2,
            has_quick_picks=False,
            failure_reason="draft_candidate_compliance_failed",
        )
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=allowed,
            entity_audit=audit,
            query_contract=self.contract,
            minimum_publishable_items=3,
            draft_candidate_compliance=compliance,
        )
        assert snapshot.count_status == "failed", (
            f"Expected failed, got {snapshot.count_status}"
        )
        assert snapshot.evidence_limited is False, (
            "Should NOT be evidence_limited when allowed >= requested"
        )
        assert snapshot.draft_candidate_compliance_passes is False

    def test_allowed_3_article_3_is_evidence_limited(self):
        from blogagent.tools.article_entity_audit import (
            EntityAudit,
            build_answer_count_snapshot,
        )

        allowed = self._make_allowed(3)
        audit = EntityAudit(
            article_entities_count=3,
            grounded_entities_count=3,
            allowed_entities_count=3,
            passes=True,
        )
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=allowed,
            entity_audit=audit,
            query_contract=self.contract,
            minimum_publishable_items=3,
        )
        assert snapshot.count_status == "evidence_limited", (
            f"Expected evidence_limited, got {snapshot.count_status}"
        )
        assert snapshot.evidence_limited is True

    def test_allowed_7_article_7_is_satisfied(self):
        from blogagent.tools.article_entity_audit import (
            EntityAudit,
            build_answer_count_snapshot,
        )
        from blogagent.tools.draft_candidate_compliance import DraftCandidateCompliance

        allowed = self._make_allowed(7)
        audit = EntityAudit(
            article_entities_count=7,
            grounded_entities_count=7,
            allowed_entities_count=7,
            passes=True,
        )
        compliance = DraftCandidateCompliance(
            passes=True,
            requested_count=7,
            allowed_count=7,
            recommended_count=7,
            allowed_recommended_count=7,
            has_quick_picks=True,
        )
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=allowed,
            entity_audit=audit,
            query_contract=self.contract,
            minimum_publishable_items=3,
            draft_candidate_compliance=compliance,
        )
        assert snapshot.count_status == "satisfied"
        assert snapshot.evidence_limited is False
        assert snapshot.draft_candidate_compliance_passes is True
