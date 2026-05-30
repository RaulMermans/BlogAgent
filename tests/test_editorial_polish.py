"""Tests for the editorial polish agent."""

from __future__ import annotations

import os

import pytest

from blogagent.agents.editorial_polish_agent import (
    EditorialPolishOutput,
    polish_article,
)
from blogagent.workflow.state import EvidenceItem, SourceScore

_DRAFT = """# Best Perfumes for a Date Night

## Quick Picks

- Chanel Chance Eau Tendre
- Dior Miss Dior

## How We Chose

Based on available sources.

## Final Takeaway

These are good choices.
"""

_EVAL_POLISH_REQUIRED = {
    "publish_ready": False,
    "score": 62,
    "polish_required": True,
    "defects": [
        {
            "type": "weak_sensory_detail",
            "severity": "high",
            "message": "Fragrance article mentions only 1 sensory term.",
        }
    ],
    "summary": "Score: 62/100.",
}

_EVAL_NO_POLISH = {
    "publish_ready": True,
    "score": 85,
    "polish_required": False,
    "defects": [],
    "summary": "Score: 85/100. Article meets publish standards.",
}


class TestEditorialPolishAgent:
    def test_mock_mode_runs_without_llm(self):
        """Mock mode returns unchanged article with summary."""
        result = polish_article(
            article_markdown=_DRAFT,
            topic="best perfumes for a date",
            publishability_evaluation=_EVAL_POLISH_REQUIRED,
            evidence_table_summary="Allure: Chanel Chance has citrus notes.",
            selected_skills=["beauty-fragrance-writing", "personal-blog-voice"],
            is_recommendation=True,
            requested_count=None,
            evidence_sufficiency=None,
        )
        assert result.is_mock is True
        polish_out: EditorialPolishOutput = result.data
        assert isinstance(polish_out, EditorialPolishOutput)
        assert isinstance(polish_out.polished_markdown, str)
        assert len(polish_out.polished_markdown) > 0
        assert isinstance(polish_out.polish_summary, list)
        assert len(polish_out.polish_summary) >= 1

    def test_mock_preserves_citations(self):
        """Mock polish doesn't strip inline citations."""
        draft_with_citations = _DRAFT + "\n\nAccording to [Allure](https://allure.com): Chanel Chance is fresh."
        result = polish_article(
            article_markdown=draft_with_citations,
            topic="best perfumes for a date",
            publishability_evaluation=_EVAL_POLISH_REQUIRED,
            evidence_table_summary="",
            selected_skills=[],
            is_recommendation=True,
            requested_count=None,
            evidence_sufficiency=None,
        )
        polish_out: EditorialPolishOutput = result.data
        assert "[Allure]" in polish_out.polished_markdown

    def test_polish_summary_appears_in_output(self):
        """polish_summary is a non-empty list when polish ran."""
        result = polish_article(
            article_markdown=_DRAFT,
            topic="best perfumes for a date",
            publishability_evaluation=_EVAL_POLISH_REQUIRED,
            evidence_table_summary="",
            selected_skills=["personal-blog-voice"],
            is_recommendation=True,
            requested_count=5,
            evidence_sufficiency={"recommended_action": "evidence_limited"},
        )
        polish_out: EditorialPolishOutput = result.data
        assert isinstance(polish_out.polish_summary, list)
        assert len(polish_out.polish_summary) >= 1

    def test_publishability_confidence_in_valid_range(self):
        """publishability_confidence is between 0 and 1."""
        result = polish_article(
            article_markdown=_DRAFT,
            topic="best perfumes",
            publishability_evaluation=_EVAL_POLISH_REQUIRED,
            evidence_table_summary="",
            selected_skills=[],
            is_recommendation=False,
            requested_count=None,
            evidence_sufficiency=None,
        )
        polish_out: EditorialPolishOutput = result.data
        assert 0.0 <= polish_out.publishability_confidence <= 1.0

    def test_remaining_issues_is_list(self):
        """remaining_issues is always a list."""
        result = polish_article(
            article_markdown=_DRAFT,
            topic="best perfumes",
            publishability_evaluation=_EVAL_POLISH_REQUIRED,
            evidence_table_summary="",
            selected_skills=[],
            is_recommendation=False,
            requested_count=None,
            evidence_sufficiency=None,
        )
        polish_out: EditorialPolishOutput = result.data
        assert isinstance(polish_out.remaining_issues, list)
