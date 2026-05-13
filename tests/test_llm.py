"""Tests for the LLM client layer.

All tests run in mock mode and do not require any API key.
"""

from __future__ import annotations

from blogagent.llm.client import generate_structured
from blogagent.llm.schemas import (
    ClaimExtractionOutput,
    DraftOutput,
    FactCheckJudgmentOutput,
    LLMResult,
    OutlineOutput,
    ResearchPlanOutput,
    RevisionOutput,
)

# ---------------------------------------------------------------------------
# Mock provider — default, no API key required
# ---------------------------------------------------------------------------


def test_mock_provider_returns_llm_result():
    result = generate_structured(
        system_prompt="You are a researcher.",
        user_prompt="Generate questions.",
        output_model=ResearchPlanOutput,
    )
    assert isinstance(result, LLMResult)


def test_mock_provider_is_mock():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.is_mock is True


def test_mock_provider_name():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.provider == "mock"


def test_mock_research_plan_returns_questions():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert isinstance(result.data, ResearchPlanOutput)
    assert len(result.data.research_questions) >= 1


def test_mock_outline_returns_valid_outline():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=OutlineOutput,
    )
    assert isinstance(result.data, OutlineOutput)
    assert result.data.title != ""
    assert len(result.data.sections) >= 1


def test_mock_draft_returns_markdown_and_meta():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=DraftOutput,
    )
    assert isinstance(result.data, DraftOutput)
    assert result.data.article_markdown.strip() != ""
    assert result.data.meta_description.strip() != ""


def test_mock_claim_extraction_returns_claims():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ClaimExtractionOutput,
    )
    assert isinstance(result.data, ClaimExtractionOutput)
    assert len(result.data.claims) >= 1


def test_mock_fact_check_judgment_returns_judgment():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=FactCheckJudgmentOutput,
    )
    assert isinstance(result.data, FactCheckJudgmentOutput)
    assert isinstance(result.data.passed, bool)


def test_mock_revision_returns_revision():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=RevisionOutput,
    )
    assert isinstance(result.data, RevisionOutput)
    assert result.data.revised_markdown.strip() != ""
    assert result.data.revision_summary.strip() != ""


def test_mock_result_has_no_error():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.error is None


# ---------------------------------------------------------------------------
# Missing API key — fall back to mock with warning, no crash
# ---------------------------------------------------------------------------


def test_missing_anthropic_key_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.is_mock is True
    assert result.warning is not None
    assert "ANTHROPIC_API_KEY" in result.warning


def test_missing_anthropic_key_still_returns_data(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert isinstance(result.data, ResearchPlanOutput)


def test_missing_openai_key_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.is_mock is True
    assert result.warning is not None
    assert "OPENAI_API_KEY" in result.warning


def test_missing_openai_key_still_returns_data(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert isinstance(result.data, ResearchPlanOutput)


def test_unknown_provider_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "unknown_provider_xyz")
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.is_mock is True


# ---------------------------------------------------------------------------
# Editor Agent functions (mock mode — BLOGAGENT_USE_LLM_EDITOR=false)
# ---------------------------------------------------------------------------


def test_editor_generate_research_plan_returns_questions():
    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Climate Change")
    assert len(result.research_questions) >= 1
    assert all(isinstance(q, str) for q in result.research_questions)


def test_editor_generate_research_plan_mentions_topic():
    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Quantum Computing")
    combined = " ".join(result.research_questions).lower()
    assert "quantum computing" in combined


def test_editor_generate_outline_returns_valid_outline():
    from blogagent.agents.editor_agent import generate_outline

    result = generate_outline(topic="Solar Energy", evidence_table=[], source_scores=[])
    assert result.title != ""
    assert len(result.sections) >= 1
    assert result.target_word_count > 0


def test_editor_generate_outline_title_contains_topic():
    from blogagent.agents.editor_agent import generate_outline

    result = generate_outline(topic="Solar Energy", evidence_table=[], source_scores=[])
    assert "Solar Energy" in result.title


def test_editor_write_article_draft_returns_markdown():
    from blogagent.agents.editor_agent import generate_outline, write_article_draft

    outline = generate_outline(topic="Photosynthesis", evidence_table=[], source_scores=[])
    result = write_article_draft(
        topic="Photosynthesis",
        outline=outline,
        evidence_table=[],
        source_scores=[],
    )
    assert result.article_markdown.strip() != ""
    assert "#" in result.article_markdown


def test_editor_write_article_draft_returns_meta_description():
    from blogagent.agents.editor_agent import generate_outline, write_article_draft

    outline = generate_outline(topic="Photosynthesis", evidence_table=[], source_scores=[])
    result = write_article_draft(
        topic="Photosynthesis",
        outline=outline,
        evidence_table=[],
        source_scores=[],
    )
    assert result.meta_description.strip() != ""


def test_editor_revise_article_returns_revision():
    from blogagent.agents.editor_agent import revise_article
    from blogagent.workflow.state import FactCheckReport

    report = FactCheckReport(
        total_claims=1,
        supported_count=0,
        partially_supported_count=0,
        unsupported_count=1,
        passed=False,
        blocking_issues=["Unsupported high-importance claim: 'X is 99% accurate'"],
    )
    result = revise_article(
        topic="Test Topic",
        draft="# Test\n\nX is 99% accurate.",
        fact_check_report=report,
        citation_matches=[],
    )
    assert isinstance(result.revised_markdown, str)
    assert isinstance(result.revision_summary, str)
    assert result.revision_summary.strip() != ""


# ---------------------------------------------------------------------------
# Fact-check evaluator (mock mode — BLOGAGENT_USE_LLM_FACTCHECK=false)
# ---------------------------------------------------------------------------


def test_evaluate_draft_unsupported_high_claim_triggers_blocking():
    from blogagent.agents.fact_check_evaluator import evaluate_draft
    from blogagent.workflow.state import (
        CitationMatch,
        CitationStatus,
        Claim,
        ClaimImportance,
    )

    claim = Claim(
        text="Solar energy costs have fallen by 90%.",
        importance=ClaimImportance.high,
        section="Key Facts",
    )
    match = CitationMatch(claim=claim, status=CitationStatus.unsupported, notes="No source found")
    result = evaluate_draft(
        topic="Solar Energy",
        draft="# Solar Energy\n\nSolar energy costs have fallen by 90%.",
        claims=[claim],
        citation_matches=[match],
        source_scores=[],
    )
    assert result.passed is False
    assert result.revision_required is True
    assert len(result.blocking_issues) >= 1


def test_evaluate_draft_supported_claim_passes():
    from blogagent.agents.fact_check_evaluator import evaluate_draft
    from blogagent.workflow.state import (
        CitationMatch,
        CitationStatus,
        Claim,
        ClaimImportance,
    )

    claim = Claim(
        text="Solar panels convert sunlight to electricity.",
        importance=ClaimImportance.medium,
        section="Introduction",
    )
    match = CitationMatch(
        claim=claim,
        status=CitationStatus.supported,
        supporting_sources=["https://example.com"],
    )
    result = evaluate_draft(
        topic="Solar Energy",
        draft="# Solar Energy\n\nSolar panels convert sunlight to electricity.",
        claims=[claim],
        citation_matches=[match],
        source_scores=[],
    )
    assert result.passed is True


def test_evaluate_draft_unsupported_medium_claim_does_not_block():
    from blogagent.agents.fact_check_evaluator import evaluate_draft
    from blogagent.workflow.state import (
        CitationMatch,
        CitationStatus,
        Claim,
        ClaimImportance,
    )

    claim = Claim(
        text="Solar energy is popular.",
        importance=ClaimImportance.medium,
        section="Introduction",
    )
    match = CitationMatch(claim=claim, status=CitationStatus.unsupported)
    result = evaluate_draft(
        topic="Solar Energy",
        draft="# Solar Energy\n\nSolar energy is popular.",
        claims=[claim],
        citation_matches=[match],
        source_scores=[],
    )
    assert result.passed is True
    assert len(result.blocking_issues) == 0


# ---------------------------------------------------------------------------
# Revision count cap
# ---------------------------------------------------------------------------


def test_revision_count_never_exceeds_one(monkeypatch):
    """The pipeline revision loop runs at most once, even if the final fact-check still fails."""
    import blogagent.workflow.graph as _graph
    from blogagent.workflow.graph import run_pipeline
    from blogagent.workflow.state import FactCheckReport

    call_order: list[str] = []
    original_run_fact_check = _graph.run_fact_check

    def patched_fact_check(state):
        call_order.append("fact_check")
        if len(call_order) == 1:
            # Force failure on first call to trigger revision.
            state.fact_check_report = FactCheckReport(
                total_claims=1,
                supported_count=0,
                partially_supported_count=0,
                unsupported_count=1,
                passed=False,
                blocking_issues=["Unsupported high-importance claim: 'X'"],
            )
            return state
        return original_run_fact_check(state)

    monkeypatch.setattr(_graph, "run_fact_check", patched_fact_check)

    state = run_pipeline("Climate Change")
    # revision_count must be 0 or 1, never higher
    assert state.revision_count <= 1
    # Revision was triggered: fact_check called twice (initial + after revision)
    assert len(call_order) == 2


def test_revision_summary_set_after_revision(monkeypatch):
    """When revision happens, revision_summary is non-empty."""
    import blogagent.workflow.graph as _graph
    from blogagent.workflow.graph import run_pipeline
    from blogagent.workflow.state import FactCheckReport

    original_run_fact_check = _graph.run_fact_check
    call_count = [0]

    def patched_fact_check(state):
        call_count[0] += 1
        if call_count[0] == 1:
            state.fact_check_report = FactCheckReport(
                total_claims=1,
                supported_count=0,
                partially_supported_count=0,
                unsupported_count=1,
                passed=False,
                blocking_issues=["Unsupported claim"],
            )
            return state
        return original_run_fact_check(state)

    monkeypatch.setattr(_graph, "run_fact_check", patched_fact_check)

    state = run_pipeline("Climate Change")
    assert state.revision_summary.strip() != ""
