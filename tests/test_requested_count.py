"""Tests for extract_requested_count and normalize_number_words."""

from __future__ import annotations

from blogagent.workflow.recommendation import (
    extract_requested_count,
    normalize_number_words,
)


class TestNormalizeNumberWords:
    def test_seven_normalized(self):
        assert normalize_number_words("seven best perfumes") == "7 best perfumes"

    def test_ten_normalized(self):
        assert normalize_number_words("top ten fragrances") == "top 10 fragrances"

    def test_five_normalized(self):
        assert normalize_number_words("give me five options") == "give me 5 options"

    def test_twenty_normalized(self):
        assert normalize_number_words("twenty best hotels") == "20 best hotels"

    def test_no_number_word_unchanged(self):
        assert normalize_number_words("best perfumes for summer") == "best perfumes for summer"

    def test_case_insensitive(self):
        result = normalize_number_words("SEVEN best perfumes")
        assert "7" in result

    def test_digit_unchanged(self):
        assert normalize_number_words("7 best parfums") == "7 best parfums"


class TestExtractRequestedCount:
    # --- Must detect ---

    def test_7_best_parfums_for_summer(self):
        assert extract_requested_count("7 best parfums for summer") == 7

    def test_seven_best_perfumes(self):
        assert extract_requested_count("seven best perfumes") == 7

    def test_best_7_perfumes(self):
        assert extract_requested_count("best 7 perfumes") == 7

    def test_top_7_perfumes(self):
        assert extract_requested_count("top 7 perfumes") == 7

    def test_top_ten_perfumes(self):
        assert extract_requested_count("top ten perfumes") == 10

    def test_10_best_perfumes(self):
        assert extract_requested_count("10 best perfumes") == 10

    def test_a_list_of_7_perfumes(self):
        assert extract_requested_count("a list of 7 perfumes") == 7

    def test_list_of_5(self):
        assert extract_requested_count("list of 5 fragrances") == 5

    def test_recommend_5_summer_fragrances(self):
        assert extract_requested_count("recommend 5 summer fragrances") == 5

    def test_give_me_five_options(self):
        assert extract_requested_count("give me five options") == 5

    def test_top_10_best_perfumes_for_a_date(self):
        assert extract_requested_count("top 10 best perfumes for a date") == 10

    def test_best_twelve_skincare_products(self):
        assert extract_requested_count("best twelve skincare products") == 12

    def test_3_top_restaurants(self):
        assert extract_requested_count("3 top restaurants in Paris") == 3

    # --- Must NOT detect (false positive guards) ---

    def test_year_2025_not_detected(self):
        assert extract_requested_count("best perfumes for 2025") is None

    def test_year_2026_not_detected(self):
        assert extract_requested_count("top programming languages 2026") is None

    def test_price_50_not_detected(self):
        assert extract_requested_count("perfumes under 50 dollars") is None

    def test_price_under_100_not_detected(self):
        assert extract_requested_count("laptops under $100") is None

    def test_for_2_people_not_detected(self):
        assert extract_requested_count("best restaurants for 2 people") is None

    def test_standalone_2025_topic_no_count(self):
        assert extract_requested_count("2025 summer perfume trends") is None

    # --- Returns None when no count stated ---

    def test_no_count_in_topic(self):
        assert extract_requested_count("best perfumes for summer") is None

    def test_factual_topic_no_count(self):
        assert extract_requested_count("how mRNA vaccines work") is None


class TestPipelineRequestedCount:
    """Integration: check_external_effects sets requested_count from topic."""

    def test_7_best_parfums_pipeline(self):
        from blogagent.workflow.graph import run_pipeline

        state = run_pipeline("7 best parfums for summer")
        assert state.requested_count == 7, (
            f"Expected requested_count=7, got {state.requested_count}"
        )

    def test_seven_best_perfumes_pipeline(self):
        from blogagent.workflow.graph import run_pipeline

        state = run_pipeline("seven best perfumes")
        assert state.requested_count == 7

    def test_top_5_laptops_pipeline(self):
        from blogagent.workflow.graph import run_pipeline

        state = run_pipeline("top 5 laptops for students")
        assert state.requested_count == 5

    def test_no_count_pipeline_is_none(self):
        from blogagent.workflow.graph import run_pipeline

        state = run_pipeline("best perfumes for summer")
        assert state.requested_count is None

    def test_2025_topic_does_not_get_count(self):
        from blogagent.workflow.graph import run_pipeline

        state = run_pipeline("best AI tools 2025")
        assert state.requested_count is None

    def test_requested_count_in_api_response(self):
        """API response includes requested_count for a count-bearing topic."""
        from blogagent.workflow.graph import run_pipeline

        state = run_pipeline("7 best parfums for summer")
        # requested_count appears in state
        assert state.requested_count == 7
        # run_trace mentions the count
        trace_text = " ".join(state.run_trace)
        assert "7" in trace_text
