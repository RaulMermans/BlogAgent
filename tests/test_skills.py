"""Tests for the runtime skill registry and deterministic skill selection."""

from __future__ import annotations

from blogagent.skills.loader import select_skills
from blogagent.skills.registry import get_skill_brief, get_skill_briefs
from blogagent.skills.specs import SKILL_SPECS


def test_skill_specs_non_empty():
    assert len(SKILL_SPECS) >= 6
    for name, spec in SKILL_SPECS.items():
        assert "name" in spec
        assert "brief" in spec
        assert spec["name"] == name


def test_get_skill_brief_known():
    brief = get_skill_brief("citation-grounding")
    assert isinstance(brief, str)
    assert len(brief) > 10


def test_get_skill_brief_unknown_returns_empty():
    assert get_skill_brief("nonexistent-skill") == ""


def test_get_skill_briefs_multiple():
    result = get_skill_briefs(["citation-grounding", "seo-blog-writing"])
    assert "citation-grounding" in result
    assert "seo-blog-writing" in result
    assert "\n" in result


def test_get_skill_briefs_empty_list():
    assert get_skill_briefs([]) == ""


def test_select_skills_recommendation():
    skills = select_skills("best laptops for students", is_recommendation=True, is_financial=False)
    assert "recommendation-writing" in skills
    assert "citation-grounding" in skills
    assert len(skills) >= 3


def test_select_skills_financial():
    skills = select_skills("top ETFs for retirement", is_recommendation=False, is_financial=True)
    assert "financial-safety" in skills
    assert "citation-grounding" in skills


def test_select_skills_factual():
    skills = select_skills("How photosynthesis works", is_recommendation=False, is_financial=False)
    assert "citation-grounding" in skills
    assert "seo-blog-writing" in skills
    assert "financial-safety" not in skills
    assert "recommendation-writing" not in skills


def test_select_skills_returns_list():
    result = select_skills("climate change overview", is_recommendation=False, is_financial=False)
    assert isinstance(result, list)
    assert all(isinstance(s, str) for s in result)


def test_get_skill_briefs_all_specs():
    all_names = list(SKILL_SPECS.keys())
    result = get_skill_briefs(all_names)
    for name in all_names:
        assert name in result
