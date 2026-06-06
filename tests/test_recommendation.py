"""Tests for recommendation topic detection, guardrails, and prompt content.

Requirements covered:
- is_recommendation_topic detects all listed keywords
- is_financial_topic detects financial keywords
- "Best parfums for summer" is detected as recommendation
- mock search + recommendation topic adds warning (limited response)
- tavily search + recommendation topic does NOT add the mock-search warning
- investment topics add financial disclaimer warning
- recommendation prompts contain Quick Picks / forbid unsupported products
- existing factual topics still work
"""

from __future__ import annotations

from blogagent.agents import prompts
from blogagent.workflow.graph import run_pipeline
from blogagent.workflow.recommendation import (
    is_financial_topic,
    is_real_search_active,
    is_recommendation_topic,
)

# ---------------------------------------------------------------------------
# is_recommendation_topic
# ---------------------------------------------------------------------------


def test_best_parfums_is_recommendation():
    assert is_recommendation_topic("Best parfums for summer") is True


def test_best_keyword_detected():
    assert is_recommendation_topic("Best laptops for students 2025") is True


def test_top_keyword_detected():
    assert is_recommendation_topic("Top restaurants in Barcelona") is True


def test_recommended_keyword_detected():
    assert is_recommendation_topic("Recommended skincare routine") is True


def test_recommendations_keyword_detected():
    assert is_recommendation_topic("Gift recommendations for parents") is True


def test_products_keyword_detected():
    assert is_recommendation_topic("Hair care products for curly hair") is True


def test_perfumes_keyword_detected():
    assert is_recommendation_topic("Best perfumes for men") is True


def test_parfums_keyword_detected():
    assert is_recommendation_topic("Parfums de Marly review guide") is True


def test_fragrances_keyword_detected():
    assert is_recommendation_topic("Best fragrances for summer 2025") is True


def test_makeup_keyword_detected():
    assert is_recommendation_topic("Best makeup for sensitive skin") is True


def test_skincare_keyword_detected():
    assert is_recommendation_topic("Skincare routine for dry skin") is True


def test_tools_keyword_detected():
    assert is_recommendation_topic("Best developer tools 2026") is True


def test_laptops_keyword_detected():
    assert is_recommendation_topic("Laptops under $1000") is True


def test_shoes_keyword_detected():
    assert is_recommendation_topic("Best running shoes for beginners") is True


def test_restaurants_keyword_detected():
    assert is_recommendation_topic("Best restaurants in Paris") is True


def test_hotels_keyword_detected():
    assert is_recommendation_topic("Best hotels in Tokyo for couples") is True


def test_stocks_keyword_detected():
    assert is_recommendation_topic("Best stocks to buy in 2025") is True


def test_invest_keyword_detected():
    assert is_recommendation_topic("How to invest in ETFs") is True


def test_current_keyword_detected():
    assert is_recommendation_topic("Current trends in AI") is True


def test_recent_keyword_detected():
    assert is_recommendation_topic("Recent advances in battery technology") is True


def test_2025_keyword_detected():
    assert is_recommendation_topic("Best AI tools 2025") is True


def test_2026_keyword_detected():
    assert is_recommendation_topic("Top programming languages 2026") is True


def test_case_insensitive():
    assert is_recommendation_topic("BEST parfums for summer") is True
    assert is_recommendation_topic("Best Parfums For Summer") is True


# Topics that should NOT be recommendation
def test_water_cycle_not_recommendation():
    assert is_recommendation_topic("The water cycle") is False


def test_mrna_vaccines_not_recommendation():
    assert is_recommendation_topic("How mRNA vaccines work") is False


def test_printing_press_not_recommendation():
    assert is_recommendation_topic("The invention of the printing press") is False


def test_coffee_health_not_recommendation():
    assert is_recommendation_topic("Coffee and health effects") is False


def test_python_for_loop_not_recommendation():
    assert is_recommendation_topic("How to write a for loop in Python") is False


def test_moon_cycles_not_recommendation():
    assert is_recommendation_topic("The health effects of moon cycles") is False


# ---------------------------------------------------------------------------
# is_financial_topic
# ---------------------------------------------------------------------------


def test_stocks_is_financial():
    assert is_financial_topic("Best stocks to buy now") is True


def test_invest_is_financial():
    assert is_financial_topic("How to invest in index funds") is True


def test_investment_is_financial():
    assert is_financial_topic("Investment strategies for 2025") is True


def test_crypto_is_financial():
    assert is_financial_topic("Best crypto to invest in") is True


def test_trading_is_financial():
    assert is_financial_topic("Day trading strategies for beginners") is True


def test_perfumes_not_financial():
    assert is_financial_topic("Best parfums for summer") is False


def test_laptops_not_financial():
    assert is_financial_topic("Top laptops for developers") is False


def test_water_cycle_not_financial():
    assert is_financial_topic("The water cycle") is False


def test_mrna_not_financial():
    assert is_financial_topic("How mRNA vaccines work") is False


# ---------------------------------------------------------------------------
# is_real_search_active
# ---------------------------------------------------------------------------


def test_default_search_is_not_real(monkeypatch):
    monkeypatch.delenv("BLOGAGENT_SEARCH_PROVIDER", raising=False)
    assert is_real_search_active() is False


def test_mock_search_is_not_real(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    assert is_real_search_active() is False


def test_tavily_search_is_real(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "tavily")
    assert is_real_search_active() is True


def test_case_insensitive_provider(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "TAVILY")
    assert is_real_search_active() is True


# ---------------------------------------------------------------------------
# Pipeline guardrails — mock search + recommendation topics
# ---------------------------------------------------------------------------


def test_recommendation_topic_mock_search_adds_warning():
    """Mock search + recommendation topic → limited-response with warning (not full block)."""
    state = run_pipeline("Best parfums for summer")
    assert any("Real search is required" in w for w in state.warnings), (
        f"Expected mock-search warning; got warnings: {state.warnings}"
    )


def test_recommendation_topic_mock_search_is_not_fully_blocked():
    """Mock search + recommendation topic → still produces an article package."""
    state = run_pipeline("Best parfums for summer")
    assert state.blocked is False
    assert state.final_article_package is not None


def test_recommendation_topic_mock_draft_uses_curated_known_products():
    """Editorial mock drafts may use the adapter's curated known-entity universe."""
    state = run_pipeline("Best parfums for summer")
    assert state.final_article_package is not None
    article = state.final_article_package.article_markdown
    assert "Our Picks" in article
    assert state.publish_ready_status == "publish_ready_with_editorial_review"
    assert all(
        candidate["candidate_basis"] == "known_entity"
        for candidate in state.allowed_candidates
    )


def test_recommendation_topic_below_minimum_uses_evidence_report_structure():
    """Below-minimum drafts must not pretend to be normal best-of lists."""
    state = run_pipeline("Best laptops for students")
    assert state.final_article_package is not None
    article = state.final_article_package.article_markdown
    assert "Evidence Report" in article
    assert "Candidates Found" in article
    assert "Quick Picks" not in article
    assert state.publish_ready_status == "draft_only_not_publish_ready"


def test_tavily_recommendation_topic_does_not_add_mock_warning(monkeypatch):
    """Real search configured (even if it falls back) → no mock-search warning is added.

    The guardrail fires before search runs; it trusts BLOGAGENT_SEARCH_PROVIDER=tavily.
    Even if Tavily has no API key and falls back to mock results, the warning should
    not be injected because the user configured a real provider.
    """
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "tavily")
    state = run_pipeline("Best parfums for summer")
    assert not any("Real search is required" in w for w in state.warnings), (
        f"Mock-search warning incorrectly added with tavily provider; warnings: {state.warnings}"
    )


# ---------------------------------------------------------------------------
# Pipeline guardrails — financial topics
# ---------------------------------------------------------------------------


def test_investment_topic_adds_financial_warning():
    state = run_pipeline("Best stocks to invest in 2025")
    assert any("financial" in w.lower() for w in state.warnings), (
        f"Expected financial warning; got warnings: {state.warnings}"
    )


def test_invest_topic_adds_financial_disclaimer():
    state = run_pipeline("How to invest in index funds")
    assert any("financial" in w.lower() for w in state.warnings)


def test_crypto_topic_adds_financial_warning():
    state = run_pipeline("Best crypto to buy 2025")
    assert any("financial" in w.lower() for w in state.warnings)


def test_financial_topic_is_not_blocked():
    """Financial topics should not be fully blocked — only warned."""
    state = run_pipeline("Best stocks to invest in 2025")
    assert state.blocked is False
    assert state.final_article_package is not None


def test_financial_draft_contains_disclaimer():
    """The mock draft for a financial topic must include a disclaimer."""
    state = run_pipeline("Best stocks to invest in 2025")
    assert state.final_article_package is not None
    article = state.final_article_package.article_markdown
    assert (
        "disclaimer" in article.lower()
        or "not financial advice" in article.lower()
        or "educational" in article.lower()
    )


# ---------------------------------------------------------------------------
# State flags
# ---------------------------------------------------------------------------


def test_is_recommendation_flag_set_for_recommendation_topic():
    state = run_pipeline("Best parfums for summer")
    assert state.is_recommendation is True


def test_is_recommendation_flag_false_for_factual_topic():
    state = run_pipeline("The water cycle")
    assert state.is_recommendation is False


def test_is_financial_flag_set_for_financial_topic():
    state = run_pipeline("Best stocks to invest in 2025")
    assert state.is_financial is True


def test_is_financial_flag_false_for_non_financial_topic():
    state = run_pipeline("The water cycle")
    assert state.is_financial is False


# ---------------------------------------------------------------------------
# Prompt content
# ---------------------------------------------------------------------------


def test_recommendation_draft_prompt_contains_quick_picks():
    assert "Quick Picks" in prompts.RECOMMENDATION_DRAFT_PROMPT


def test_recommendation_draft_prompt_forbids_inventing_products():
    """Draft prompt must state that only products from evidence may be named."""
    p = prompts.RECOMMENDATION_DRAFT_PROMPT.lower()
    assert "may only" in p or "only name" in p or "only those found" in p


def test_recommendation_draft_prompt_states_source_grounding_rule():
    assert "evidence" in prompts.RECOMMENDATION_DRAFT_PROMPT.lower()


def test_recommendation_draft_prompt_includes_fallback_language():
    """Draft prompt must tell the model what to do when sources lack named products."""
    assert "did not provide" in prompts.RECOMMENDATION_DRAFT_PROMPT.lower()


def test_recommendation_outline_prompt_contains_quick_picks():
    assert "Quick Picks" in prompts.RECOMMENDATION_OUTLINE_PROMPT


def test_recommendation_outline_prompt_mentions_named_products():
    p = prompts.RECOMMENDATION_OUTLINE_PROMPT.lower()
    assert "named" in p


def test_recommendation_research_plan_prompt_targets_named_entities():
    p = prompts.RECOMMENDATION_RESEARCH_PLAN_PROMPT.lower()
    assert "named" in p


def test_financial_draft_addendum_contains_not_financial_advice():
    p = prompts.FINANCIAL_DRAFT_ADDENDUM.lower()
    assert "not financial advice" in p or "financial advice" in p


def test_financial_draft_addendum_avoids_buy_language():
    p = prompts.FINANCIAL_DRAFT_ADDENDUM.lower()
    assert "buy this stock" in p or "do not" in p or "avoid" in p


# ---------------------------------------------------------------------------
# Existing factual topics still work
# ---------------------------------------------------------------------------


def test_water_cycle_still_produces_package():
    state = run_pipeline("The water cycle")
    assert state.final_article_package is not None
    assert state.blocked is False


def test_mrna_vaccines_still_produces_package():
    state = run_pipeline("How mRNA vaccines work")
    assert state.final_article_package is not None
    assert state.blocked is False


def test_printing_press_still_produces_package():
    state = run_pipeline("The invention of the printing press")
    assert state.final_article_package is not None
    assert state.blocked is False


def test_coffee_health_still_produces_package():
    state = run_pipeline("Coffee and health effects")
    assert state.final_article_package is not None
    assert state.blocked is False


def test_python_for_loop_still_produces_package():
    state = run_pipeline("How to write a for loop in Python")
    assert state.final_article_package is not None
    assert state.blocked is False


def test_factual_topic_no_recommendation_warning():
    state = run_pipeline("The water cycle")
    assert not any("Real search is required" in w for w in state.warnings)


def test_factual_topic_no_financial_warning():
    state = run_pipeline("The water cycle")
    assert not any("financial" in w.lower() for w in state.warnings)


def test_external_side_effect_still_blocked():
    """Existing external-effect guardrail must not be disrupted."""
    state = run_pipeline("Post this article to WordPress immediately")
    assert state.blocked is True
    assert state.final_article_package is None


# ---------------------------------------------------------------------------
# Research questions in recommendation mode (mock)
# ---------------------------------------------------------------------------


def test_recommendation_research_questions_mention_named_products():
    """Mock research plan for recommendation topics should target named options."""
    state = run_pipeline("Best parfums for summer")
    questions = " ".join(state.research_questions).lower()
    # At least one question should reference named/specific options
    assert "named" in questions or "specific" in questions or "brand" in questions
