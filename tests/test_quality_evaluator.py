"""Tests for the deterministic quality evaluator."""

from __future__ import annotations

from blogagent.agents.quality_evaluator import (
    QualityEvaluationOutput,
    _count_quick_picks,
    _has_financial_disclaimer,
    _has_title,
    _has_useful_headings,
    _is_generic_output,
    count_recommendations,
    evaluate_quality,
)
from blogagent.workflow.state import EvidenceItem, SourceScore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GOOD_DRAFT = """# Understanding Photosynthesis

## Introduction

Photosynthesis is the process by which plants convert sunlight into energy.
It is one of the most important biological processes on Earth.

## How It Works

Chlorophyll in plant leaves absorbs sunlight and uses it to convert carbon dioxide
and water into glucose and oxygen.

## Conclusion

Photosynthesis underpins virtually all life on Earth by producing the oxygen we breathe.
"""

_RECOMMENDATION_DRAFT = """# Best Telescopes for Beginners

## Quick Picks

- Celestron NexStar 5SE
- Orion StarBlast 4.5
- Sky-Watcher Evostar 80

## How We Chose

We evaluated telescopes based on aperture, mount quality, and ease of use.

## Final Takeaway

These telescopes represent the best value for beginning astronomers.
"""

_FINANCIAL_DRAFT_SAFE = """# Best Index Funds

> **Disclaimer**: This article is for educational purposes only and does not constitute
> financial advice. Consult a qualified financial adviser before making investment decisions.

## Introduction

Index funds track a market index and offer diversified exposure at low cost.

## Evaluation Criteria

Consider expense ratio, tracking error, and fund size.

## Conclusion

Index funds are a foundational tool for long-term portfolio building.
"""


def _make_evidence() -> list[EvidenceItem]:
    return [
        EvidenceItem(
            fact="Photosynthesis converts light into chemical energy.",
            source_url="https://example.com/1",
            source_title="Example Source",
            publisher_domain="example.com",
            confidence=0.9,
            used_for="background context",
        )
    ]


def _make_source_score(is_mock: bool = True) -> SourceScore:
    return SourceScore(
        url="https://example.dev/mock-1",
        title="Mock Source",
        domain="example.dev",
        credibility_score=0.5,
        relevance_score=0.5,
        recency_score=0.5,
        overall_score=0.5,
        is_mock=is_mock,
    )


# ---------------------------------------------------------------------------
# Helpers unit tests
# ---------------------------------------------------------------------------


def test_count_quick_picks_correct():
    assert _count_quick_picks(_RECOMMENDATION_DRAFT) == 3


def test_count_quick_picks_none():
    assert _count_quick_picks("## Introduction\n\nSome text.") == 0


def test_has_financial_disclaimer_true():
    assert _has_financial_disclaimer(_FINANCIAL_DRAFT_SAFE)


def test_has_financial_disclaimer_false():
    assert not _has_financial_disclaimer("## Introduction\n\nSome text.")


def test_has_title():
    assert _has_title("# My Title\n\nContent.")
    assert not _has_title("## Subtitle\n\nContent.")


def test_has_useful_headings():
    assert _has_useful_headings(_GOOD_DRAFT)
    assert not _has_useful_headings("# Title\n\nJust some text.")


def test_is_generic_output_too_short():
    assert _is_generic_output("Short.")


def test_is_generic_output_placeholder():
    assert _is_generic_output("[Placeholder text here]\n\nMore.")


def test_is_generic_output_good_draft():
    assert not _is_generic_output(_GOOD_DRAFT)


# ---------------------------------------------------------------------------
# evaluate_quality integration tests
# ---------------------------------------------------------------------------


def test_good_draft_passes():
    result = evaluate_quality(
        topic="Photosynthesis",
        draft=_GOOD_DRAFT,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
        selected_skills=[],
    )
    assert isinstance(result, QualityEvaluationOutput)
    assert result.passes
    assert result.score >= 60
    assert not result.revision_required


def test_recommendation_top_n_mismatch():
    draft = _RECOMMENDATION_DRAFT  # has 3 picks
    result = evaluate_quality(
        topic="best 5 telescopes",
        draft=draft,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=True,
        is_financial=False,
        requested_count=5,
        selected_skills=[],
    )
    top_n_defects = [d for d in result.defects if d.type == "top_n_mismatch"]
    assert top_n_defects, "Expected top_n_mismatch defect"
    assert top_n_defects[0].severity == "high"
    assert result.revision_required


def test_recommendation_no_quick_picks():
    draft = "# Best Laptops\n\n## How We Chose\n\nSome criteria.\n\n## Final Takeaway\n\nDone.\n"
    result = evaluate_quality(
        topic="best laptops",
        draft=draft,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
        selected_skills=[],
    )
    missing = [d for d in result.defects if d.type == "missing_structure"]
    assert any("Quick Picks" in d.message for d in missing)
    assert result.revision_required


def test_financial_missing_disclaimer():
    draft = (
        "# Best Stocks\n\n## Introduction\n\nHere are some stocks.\n\n"
        "## Criteria\n\nLook at P/E.\n"
    )
    result = evaluate_quality(
        topic="best investment stocks",
        draft=draft,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=False,
        is_financial=True,
        requested_count=None,
        selected_skills=[],
    )
    fin_defects = [d for d in result.defects if d.type == "financial_safety"]
    assert fin_defects
    assert result.revision_required


def test_financial_safe_draft_passes():
    result = evaluate_quality(
        topic="index funds overview",
        draft=_FINANCIAL_DRAFT_SAFE,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=False,
        is_financial=True,
        requested_count=None,
        selected_skills=[],
    )
    fin_defects = [d for d in result.defects if d.type == "financial_safety"]
    assert not fin_defects, f"Unexpected financial defects: {fin_defects}"


def test_weak_source_dominance():
    low_sources = [{"quality": "low"} for _ in range(4)] + [{"quality": "medium"}]
    result = evaluate_quality(
        topic="Best skincare",
        draft=_GOOD_DRAFT,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=low_sources,
        warnings=[],
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
        selected_skills=[],
    )
    dom_defects = [d for d in result.defects if d.type == "weak_source_dominance"]
    assert dom_defects


def test_repeated_text_warning_propagated():
    result = evaluate_quality(
        topic="Photosynthesis",
        draft=_GOOD_DRAFT,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=["repeated-text: paragraph repeated in sections 2 and 4"],
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
        selected_skills=[],
    )
    rep_defects = [d for d in result.defects if d.type == "repeated_text"]
    assert rep_defects


# ---------------------------------------------------------------------------
# Score cap policy
# ---------------------------------------------------------------------------


def test_high_severity_defect_caps_score_at_69():
    """A single high-severity defect must prevent score > 69."""
    draft = _RECOMMENDATION_DRAFT  # has 3 picks
    result = evaluate_quality(
        topic="best 10 telescopes",
        draft=draft,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=True,
        is_financial=False,
        requested_count=10,
        selected_skills=[],
    )
    high_defects = [d for d in result.defects if d.severity == "high"]
    assert high_defects, "Expected at least one high-severity defect"
    assert result.score <= 69, f"Score {result.score} exceeds 69 despite high-severity defect"
    assert not result.passes


def test_high_severity_defect_sets_revision_required():
    draft = _RECOMMENDATION_DRAFT  # has 3 picks, requested 5
    result = evaluate_quality(
        topic="best 5 telescopes",
        draft=draft,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=True,
        is_financial=False,
        requested_count=5,
        selected_skills=[],
    )
    assert result.revision_required
    assert not result.passes


def test_top_n_mismatch_with_numbered_quick_picks():
    """Numbered Quick Picks items should be detected (not counted as 0)."""
    draft = """# Top 5 Perfumes

## Quick Picks

1. Chanel No. 5
2. Lancôme La Vie Est Belle
3. Yves Saint Laurent Libre
4. Dior Miss Dior
5. Guerlain Mon Guerlain

## Final Takeaway

Great choices for a date.
"""
    result = evaluate_quality(
        topic="top 5 perfumes",
        draft=draft,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=True,
        is_financial=False,
        requested_count=5,
        selected_skills=[],
    )
    top_n_defects = [d for d in result.defects if d.type == "top_n_mismatch"]
    assert not top_n_defects, (
        f"No top_n_mismatch expected for 5 numbered picks vs requested 5; defects: {result.defects}"
    )


def test_top_n_mismatch_when_quick_picks_has_wrong_numbered_count():
    """10 requested but Quick Picks has 5 numbered items → top_n_mismatch."""
    draft = """# Top 10 Perfumes

## Quick Picks

1. Chanel No. 5
2. Lancôme La Vie Est Belle
3. Yves Saint Laurent Libre
4. Dior Miss Dior
5. Guerlain Mon Guerlain

## Final Takeaway

Only 5 listed here.
"""
    result = evaluate_quality(
        topic="top 10 perfumes",
        draft=draft,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=True,
        is_financial=False,
        requested_count=10,
        selected_skills=[],
    )
    top_n_defects = [d for d in result.defects if d.type == "top_n_mismatch"]
    assert top_n_defects, "Expected top_n_mismatch for 5 items vs 10 requested"
    assert top_n_defects[0].severity == "high"
    assert result.revision_required
    assert result.score <= 69


def test_top_n_mismatch_when_quick_picks_exists_but_has_no_items():
    """Quick Picks section exists but with 0 countable items → top_n_mismatch."""
    draft = """# Top 10 Perfumes

## Quick Picks

Real search is required for specific product names.

## Final Takeaway

Enable Tavily for named recommendations.
"""
    result = evaluate_quality(
        topic="top 10 perfumes",
        draft=draft,
        evidence_table=_make_evidence(),
        source_scores=[_make_source_score()],
        source_quality_scores=[{"quality": "medium"}],
        warnings=[],
        is_recommendation=True,
        is_financial=False,
        requested_count=10,
        selected_skills=[],
    )
    top_n_defects = [d for d in result.defects if d.type == "top_n_mismatch"]
    assert top_n_defects, "Expected top_n_mismatch when Quick Picks has 0 items but exists"
    assert top_n_defects[0].severity == "high"


# ---------------------------------------------------------------------------
# count_recommendations in evaluator context
# ---------------------------------------------------------------------------


def test_count_recommendations_bullet_picks_matches_evaluator():
    """count_recommendations should return 3 for the 3-bullet test draft."""
    assert count_recommendations(_RECOMMENDATION_DRAFT) == 3
