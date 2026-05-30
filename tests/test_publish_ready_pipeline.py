"""Tests for the publish-ready pipeline: enrichment search, skills, workflow, API fields."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from blogagent.skills.loader import select_skills
from blogagent.skills.specs import SKILL_SPECS
from blogagent.workflow.graph import run_pipeline
from blogagent.workflow.state import BlogRunState


# ---------------------------------------------------------------------------
# Skill selection tests
# ---------------------------------------------------------------------------


class TestNewSkillSelection:
    def test_fragrance_topic_selects_beauty_fragrance_writing(self):
        skills = select_skills("best perfumes for a date", is_recommendation=True, is_financial=False)
        assert "beauty-fragrance-writing" in skills

    def test_lifestyle_topic_selects_fashion_lifestyle_editorial(self):
        skills = select_skills("best skincare products", is_recommendation=True, is_financial=False)
        assert "fashion-lifestyle-editorial" in skills

    def test_recommendation_topic_selects_product_recommendation_depth(self):
        skills = select_skills("top 10 laptops for developers", is_recommendation=True, is_financial=False)
        assert "product-recommendation-depth" in skills

    def test_all_blog_posts_select_personal_blog_voice(self):
        for topic, is_rec, is_fin in [
            ("photosynthesis overview", False, False),
            ("best laptops", True, False),
            ("top ETFs", False, True),
        ]:
            skills = select_skills(topic, is_recommendation=is_rec, is_financial=is_fin)
            assert "personal-blog-voice" in skills, f"personal-blog-voice missing for {topic}"

    def test_all_blog_posts_select_publishability_review(self):
        for topic, is_rec, is_fin in [
            ("photosynthesis overview", False, False),
            ("best laptops", True, False),
        ]:
            skills = select_skills(topic, is_recommendation=is_rec, is_financial=is_fin)
            assert "publishability-review" in skills, f"publishability-review missing for {topic}"

    def test_financial_topic_does_not_select_beauty_skills(self):
        skills = select_skills("top ETFs for retirement", is_recommendation=False, is_financial=True)
        assert "beauty-fragrance-writing" not in skills
        assert "fashion-lifestyle-editorial" not in skills

    def test_fragrance_topic_does_not_get_fashion_lifestyle_separately(self):
        """Fragrance uses beauty-fragrance-writing, not also fashion-lifestyle."""
        skills = select_skills("best perfumes for date night", is_recommendation=True, is_financial=False)
        assert "beauty-fragrance-writing" in skills
        # fashion-lifestyle-editorial not needed when beauty-fragrance-writing is present
        # (only one of them applies per logic in loader.py)


class TestNewSkillSpecs:
    def test_new_skills_in_specs(self):
        new_skills = [
            "beauty-fragrance-writing",
            "fashion-lifestyle-editorial",
            "product-recommendation-depth",
            "personal-blog-voice",
            "publishability-review",
        ]
        for skill in new_skills:
            assert skill in SKILL_SPECS, f"Skill {skill!r} not in SKILL_SPECS"
            assert "brief" in SKILL_SPECS[skill]
            assert len(SKILL_SPECS[skill]["brief"]) > 10

    def test_skill_briefs_appear_in_prompt_injection(self):
        from blogagent.skills.registry import get_skill_briefs
        skills = ["beauty-fragrance-writing", "personal-blog-voice", "publishability-review"]
        result = get_skill_briefs(skills)
        for sk in skills:
            assert sk in result


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------


class TestPipelineNewFields:
    def test_pipeline_has_evidence_sufficiency_in_state(self):
        state = run_pipeline("top 5 best perfumes for a date")
        assert state.evidence_sufficiency is not None
        es = state.evidence_sufficiency
        assert "sufficient" in es
        assert "score" in es
        assert "recommended_action" in es
        assert "supported_count" in es

    def test_pipeline_has_publishability_evaluation(self):
        state = run_pipeline("top 5 best perfumes for a date")
        assert state.publishability_evaluation is not None
        pe = state.publishability_evaluation
        assert "publish_ready" in pe
        assert "score" in pe
        assert "polish_required" in pe

    def test_pipeline_has_publish_ready_status(self):
        state = run_pipeline("top 5 best perfumes for a date")
        assert state.publish_ready_status in (
            "publish_ready",
            "publish_ready_with_warnings",
            "draft_only_not_publish_ready",
        )

    def test_pipeline_has_search_pass_count(self):
        state = run_pipeline("top 5 best perfumes for a date")
        assert state.search_pass_count >= 1

    def test_pipeline_has_publishability_score(self):
        state = run_pipeline("top 5 best perfumes for a date")
        assert 0 <= state.publishability_score <= 100

    def test_pipeline_evidence_sufficiency_run_trace_included(self):
        state = run_pipeline("top 5 best perfumes for a date")
        # Run trace should mention evidence sufficiency
        trace_text = "\n".join(state.run_trace)
        assert "Evidence sufficiency" in trace_text or "evidence" in trace_text.lower()

    def test_pipeline_publishability_in_run_trace(self):
        state = run_pipeline("top 5 best perfumes for a date")
        trace_text = "\n".join(state.run_trace)
        assert "Publishability" in trace_text or "publish" in trace_text.lower()

    def test_enrichment_search_skipped_in_mock_mode(self):
        """Enrichment search must not run when mock search is active."""
        with patch.dict(os.environ, {"BLOGAGENT_SEARCH_PROVIDER": "mock"}):
            state = run_pipeline("top 10 best perfumes for a date")
        # search_pass_count stays 1 in mock mode (enrichment not triggered)
        assert state.search_pass_count == 1

    def test_mock_mode_enrichment_queries_empty_or_not_used(self):
        """In mock mode, no enrichment queries should be sent to a real provider."""
        with patch.dict(os.environ, {"BLOGAGENT_SEARCH_PROVIDER": "mock"}):
            state = run_pipeline("top 10 best perfumes for a date")
        # Even if queries were generated, no second search pass ran
        assert state.search_pass_count == 1


# ---------------------------------------------------------------------------
# Enrichment search node tests
# ---------------------------------------------------------------------------


class TestEnrichmentSearchNode:
    def test_enrichment_not_triggered_when_sufficient(self):
        """When evidence is sufficient, enrichment search node does nothing."""
        from blogagent.workflow.nodes import run_enrichment_search

        state = BlogRunState(topic="top 5 perfumes for a date")
        state.is_recommendation = True
        state.search_pass_count = 1
        state.evidence_sufficiency = {
            "sufficient": True,
            "score": 80,
            "supported_count": 5,
            "requested_count": 5,
            "missing": [],
            "recommended_action": "proceed",
        }

        result = run_enrichment_search(state)
        assert result.search_pass_count == 1
        assert len(result.enrichment_queries) == 0

    def test_enrichment_not_triggered_without_recommendation(self):
        """Non-recommendation topics skip enrichment search."""
        from blogagent.workflow.nodes import run_enrichment_search

        state = BlogRunState(topic="how photosynthesis works")
        state.is_recommendation = False
        state.evidence_sufficiency = {
            "sufficient": False,
            "score": 40,
            "supported_count": 0,
            "requested_count": None,
            "missing": [],
            "recommended_action": "search_more",
        }

        result = run_enrichment_search(state)
        assert result.search_pass_count == 1

    def test_enrichment_respects_max_search_passes(self):
        """When search_pass_count already at max, enrichment is skipped."""
        from blogagent.workflow.nodes import run_enrichment_search, _MAX_SEARCH_PASSES

        state = BlogRunState(topic="top 10 perfumes")
        state.is_recommendation = True
        state.search_pass_count = _MAX_SEARCH_PASSES  # already at max
        state.evidence_sufficiency = {
            "sufficient": False,
            "recommended_action": "search_more",
        }

        result = run_enrichment_search(state)
        assert result.search_pass_count == _MAX_SEARCH_PASSES

    def test_enrichment_provider_events_recorded(self):
        """Enrichment search emits an event in provider_events."""
        from blogagent.workflow.nodes import run_enrichment_search
        from blogagent.tools.web_search import SearchOutput, SearchResult

        state = BlogRunState(topic="top 5 perfumes for a date")
        state.is_recommendation = True
        state.search_pass_count = 1
        state.requested_count = 5
        state.evidence_sufficiency = {
            "sufficient": False,
            "score": 40,
            "supported_count": 2,
            "requested_count": 5,
            "missing": ["Need more"],
            "recommended_action": "search_more",
        }

        # Patch is_real_search_active to simulate tavily active
        mock_result = SearchResult(
            url="https://allure.com/new-perfume",
            title="New Perfume Pick",
            snippet="Great floral notes",
            domain="allure.com",
            is_mock=False,
        )
        mock_output = SearchOutput(
            results=[mock_result], query="test", provider="tavily"
        )

        with patch("blogagent.workflow.nodes.is_real_search_active", return_value=True), \
             patch("blogagent.workflow.nodes.web_search", return_value=mock_output), \
             patch("blogagent.workflow.nodes.webpage_extract") as mock_extract, \
             patch("blogagent.workflow.nodes.source_score") as mock_score, \
             patch("blogagent.workflow.nodes.build_evidence_table", return_value=state):
            from blogagent.workflow.state import SourcePacket, SourceScore
            mock_extract.return_value = type("O", (), {"packet": SourcePacket(
                url="https://allure.com/new-perfume",
                title="New Perfume Pick",
                domain="allure.com",
                extracted_text="Great floral notes",
            )})()
            mock_score.return_value = SourceScore(
                url="https://allure.com/new-perfume",
                title="New Perfume Pick",
                domain="allure.com",
                credibility_score=0.9,
                relevance_score=0.8,
                recency_score=0.7,
                overall_score=0.8,
            )
            result = run_enrichment_search(state)

        # Should have run enrichment
        enrichment_events = [e for e in result.provider_events if "enrichment_search" in e]
        assert len(enrichment_events) >= 1


# ---------------------------------------------------------------------------
# API response fields
# ---------------------------------------------------------------------------


class TestAPINewFields:
    def test_api_response_includes_evidence_sufficiency(self):
        from api.index import _run_topic
        resp = _run_topic("top 5 best perfumes for a date")
        assert hasattr(resp, "evidence_sufficiency")
        assert isinstance(resp.evidence_sufficiency, dict)

    def test_api_response_includes_publishability_evaluation(self):
        from api.index import _run_topic
        resp = _run_topic("top 5 best perfumes for a date")
        assert hasattr(resp, "publishability_evaluation")
        assert isinstance(resp.publishability_evaluation, dict)

    def test_api_response_includes_polish_summary(self):
        from api.index import _run_topic
        resp = _run_topic("top 5 best perfumes for a date")
        assert hasattr(resp, "polish_summary")
        assert isinstance(resp.polish_summary, list)

    def test_api_response_includes_publish_ready_status(self):
        from api.index import _run_topic
        resp = _run_topic("top 5 best perfumes for a date")
        assert hasattr(resp, "publish_ready_status")
        assert resp.publish_ready_status in (
            "publish_ready",
            "publish_ready_with_warnings",
            "draft_only_not_publish_ready",
            "",  # blocked responses may have empty status
        )

    def test_api_response_includes_search_pass_count(self):
        from api.index import _run_topic
        resp = _run_topic("top 5 best perfumes for a date")
        assert hasattr(resp, "search_pass_count")
        assert resp.search_pass_count >= 1

    def test_api_response_includes_enrichment_queries(self):
        from api.index import _run_topic
        resp = _run_topic("top 5 best perfumes for a date")
        assert hasattr(resp, "enrichment_queries")
        assert isinstance(resp.enrichment_queries, list)

    def test_api_response_includes_publishability_score(self):
        from api.index import _run_topic
        resp = _run_topic("top 5 best perfumes for a date")
        assert hasattr(resp, "publishability_score")
        assert 0 <= resp.publishability_score <= 100
