"""Tests for the LLM client layer and agent functions.

All tests run in mock mode and do not require any API key.
"""

from __future__ import annotations

import pytest

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


def test_mock_provider_configured_provider_is_mock():
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.configured_provider == "mock"


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


def test_mock_result_has_no_warning():
    """Intentional mock mode (provider=mock) must produce no fallback warning."""
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.warning is None


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


def test_missing_anthropic_key_configured_provider_is_anthropic(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.configured_provider == "anthropic"
    assert result.provider == "mock"


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


def test_missing_google_key_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.is_mock is True
    assert result.warning is not None
    assert "GOOGLE_API_KEY" in result.warning


def test_missing_google_key_configured_provider_is_google(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.configured_provider == "google"
    assert result.provider == "mock"


def test_missing_google_key_still_returns_data(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
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
# Google model selection
# ---------------------------------------------------------------------------


def test_google_model_selection_respects_blogagent_google_model(monkeypatch):
    """BLOGAGENT_GOOGLE_MODEL is used when BLOGAGENT_LLM_MODEL is not set."""
    from blogagent.llm.client import _build_provider

    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    monkeypatch.setenv("BLOGAGENT_GOOGLE_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.delenv("BLOGAGENT_LLM_MODEL", raising=False)

    provider = _build_provider("google")
    assert provider._model == "gemini-2.5-flash-lite"


def test_google_model_selection_llm_model_overrides(monkeypatch):
    """BLOGAGENT_LLM_MODEL takes priority over BLOGAGENT_GOOGLE_MODEL."""
    from blogagent.llm.client import _build_provider

    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    monkeypatch.setenv("BLOGAGENT_LLM_MODEL", "gemini-2.5-pro")
    monkeypatch.setenv("BLOGAGENT_GOOGLE_MODEL", "gemini-2.5-flash-lite")

    provider = _build_provider("google")
    assert provider._model == "gemini-2.5-pro"


def test_google_model_default_is_flash(monkeypatch):
    """Default Google model is gemini-2.5-flash when no model vars are set."""
    from blogagent.llm.client import _build_provider

    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    monkeypatch.delenv("BLOGAGENT_LLM_MODEL", raising=False)
    monkeypatch.delenv("BLOGAGENT_GOOGLE_MODEL", raising=False)

    provider = _build_provider("google")
    assert provider._model == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Google provider monkeypatching — live success path (no real API key)
# ---------------------------------------------------------------------------


def test_google_provider_can_return_structured_output(monkeypatch):
    """Monkeypatch GoogleProvider.generate to verify the full success path."""
    import json  # noqa: PLC0415

    from blogagent.llm.providers import GoogleProvider, ProviderResponse  # noqa: PLC0415

    def fake_generate(self, system_prompt, user_prompt, temperature=0.2):
        data = ResearchPlanOutput(
            research_questions=["What makes Gemini fast?", "How does structured output work?"]
        )
        return ProviderResponse(
            text=json.dumps(data.model_dump()),
            model="gemini-2.5-flash",
            provider="google",
        )

    monkeypatch.setattr(GoogleProvider, "generate", fake_generate)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.is_mock is False
    assert result.provider == "google"
    assert result.configured_provider == "google"
    assert isinstance(result.data, ResearchPlanOutput)
    assert len(result.data.research_questions) == 2


# ---------------------------------------------------------------------------
# .env.example completeness
# ---------------------------------------------------------------------------


def test_env_example_has_google_api_key():
    from pathlib import Path

    env_example = (Path(__file__).parent.parent / ".env.example").read_text()
    assert "GOOGLE_API_KEY" in env_example


def test_env_example_has_google_model():
    from pathlib import Path

    env_example = (Path(__file__).parent.parent / ".env.example").read_text()
    assert "BLOGAGENT_GOOGLE_MODEL" in env_example


# ---------------------------------------------------------------------------
# Editor Agent functions — now return LLMResult
# ---------------------------------------------------------------------------


def test_editor_generate_research_plan_returns_llm_result():
    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Climate Change")
    assert isinstance(result, LLMResult)


def test_editor_generate_research_plan_returns_questions():
    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Climate Change")
    assert len(result.data.research_questions) >= 1
    assert all(isinstance(q, str) for q in result.data.research_questions)


def test_editor_generate_research_plan_mentions_topic():
    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Quantum Computing")
    combined = " ".join(result.data.research_questions).lower()
    assert "quantum computing" in combined


def test_editor_generate_research_plan_is_mock_in_default_mode():
    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Topic")
    assert result.is_mock is True
    assert result.configured_provider == "mock"


def test_editor_generate_research_plan_no_warning_in_mock_mode():
    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Topic")
    assert result.warning is None


def test_editor_generate_outline_returns_llm_result():
    from blogagent.agents.editor_agent import generate_outline

    result = generate_outline(topic="Solar Energy", evidence_table=[], source_scores=[])
    assert isinstance(result, LLMResult)


def test_editor_generate_outline_returns_valid_outline():
    from blogagent.agents.editor_agent import generate_outline

    result = generate_outline(topic="Solar Energy", evidence_table=[], source_scores=[])
    assert result.data.title != ""
    assert len(result.data.sections) >= 1
    assert result.data.target_word_count > 0


def test_editor_generate_outline_title_contains_topic():
    from blogagent.agents.editor_agent import generate_outline

    result = generate_outline(topic="Solar Energy", evidence_table=[], source_scores=[])
    assert "Solar Energy" in result.data.title


def test_editor_write_article_draft_returns_llm_result():
    from blogagent.agents.editor_agent import generate_outline, write_article_draft

    outline_result = generate_outline(topic="Photosynthesis", evidence_table=[], source_scores=[])
    result = write_article_draft(
        topic="Photosynthesis",
        outline=outline_result.data,
        evidence_table=[],
        source_scores=[],
    )
    assert isinstance(result, LLMResult)


def test_editor_write_article_draft_returns_markdown():
    from blogagent.agents.editor_agent import generate_outline, write_article_draft

    outline_result = generate_outline(topic="Photosynthesis", evidence_table=[], source_scores=[])
    result = write_article_draft(
        topic="Photosynthesis",
        outline=outline_result.data,
        evidence_table=[],
        source_scores=[],
    )
    assert result.data.article_markdown.strip() != ""
    assert "#" in result.data.article_markdown


def test_editor_write_article_draft_returns_meta_description():
    from blogagent.agents.editor_agent import generate_outline, write_article_draft

    outline_result = generate_outline(topic="Photosynthesis", evidence_table=[], source_scores=[])
    result = write_article_draft(
        topic="Photosynthesis",
        outline=outline_result.data,
        evidence_table=[],
        source_scores=[],
    )
    assert result.data.meta_description.strip() != ""


def test_editor_revise_article_returns_llm_result():
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
    assert isinstance(result, LLMResult)
    assert isinstance(result.data.revised_markdown, str)
    assert isinstance(result.data.revision_summary, str)
    assert result.data.revision_summary.strip() != ""


# ---------------------------------------------------------------------------
# Editor Agent fallback transparency when USE_LLM_EDITOR=true but key missing
# ---------------------------------------------------------------------------


def test_editor_research_plan_fallback_warning_when_anthropic_key_missing(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "true")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Test Topic")

    assert result.is_mock is True
    assert result.configured_provider == "anthropic"
    assert result.provider == "mock"
    assert result.warning is not None
    assert "ANTHROPIC_API_KEY" in result.warning


def test_editor_research_plan_fallback_warning_when_google_key_missing(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "true")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Test Topic")

    assert result.is_mock is True
    assert result.configured_provider == "google"
    assert result.provider == "mock"
    assert result.warning is not None
    assert "GOOGLE_API_KEY" in result.warning


# ---------------------------------------------------------------------------
# Fallback transparency: provider_events in pipeline state
# ---------------------------------------------------------------------------


def test_pipeline_provider_events_include_configured_and_actual_provider():
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Solar Energy")
    # Default mock mode: all events should have configured_provider=mock actual_provider=mock
    llm_events = [e for e in state.provider_events if "actual_provider=" in e]
    assert len(llm_events) >= 1
    for event in llm_events:
        assert "configured_provider=mock" in event
        assert "actual_provider=mock" in event
        assert "fallback=false" in event


def test_pipeline_provider_events_show_fallback_when_anthropic_key_missing(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Test Topic")
    editor_events = [e for e in state.provider_events if e.startswith("editor.")]
    assert len(editor_events) >= 1
    for event in editor_events:
        assert "configured_provider=anthropic" in event
        assert "actual_provider=mock" in event
        assert "fallback=true" in event


def test_pipeline_warnings_include_fallback_reason_when_key_missing(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Test Topic")
    assert any("ANTHROPIC_API_KEY" in w for w in state.warnings)


def test_pipeline_warnings_empty_in_pure_mock_mode():
    """In default mock mode, no provider falls back — warnings list must be empty."""
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Solar Energy")
    # Filter out search fallback warnings; we only care about LLM fallback warnings
    llm_warnings = [w for w in state.warnings if "ANTHROPIC_API_KEY" in w or "GOOGLE_API_KEY" in w]
    assert llm_warnings == []


# ---------------------------------------------------------------------------
# execution_mode semantics: computed from actual provider_events
# ---------------------------------------------------------------------------


def test_execution_mode_is_mock_in_default_mode():
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Climate Change")
    assert state.execution_mode == "mock"


def test_execution_mode_is_mock_when_live_provider_falls_back(monkeypatch):
    """When configured live provider falls back to mock, execution_mode must be 'mock'
    (no live provider succeeded — this run is not a valid live benchmark)."""
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Test Topic")
    # All actual LLM calls used mock (key missing); search is also mock.
    assert state.execution_mode == "mock"


def test_execution_mode_not_derived_from_env_vars_alone(monkeypatch):
    """execution_mode must reflect actual providers, not env var configuration."""
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "true")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Test Topic")
    # Despite env vars requesting live, all fell back to mock.
    assert state.execution_mode == "mock"


# ---------------------------------------------------------------------------
# Fact-check evaluator (mock mode — BLOGAGENT_USE_LLM_FACTCHECK=false)
# ---------------------------------------------------------------------------


def test_evaluate_draft_returns_llm_result():
    from blogagent.agents.fact_check_evaluator import evaluate_draft

    result = evaluate_draft(
        topic="Solar Energy",
        draft="# Solar\n\nFacts here.",
        claims=[],
        citation_matches=[],
        source_scores=[],
    )
    assert isinstance(result, LLMResult)


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
    assert result.data.passed is False
    assert result.data.revision_required is True
    assert len(result.data.blocking_issues) >= 1


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
    assert result.data.passed is True


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
    assert result.data.passed is True
    assert len(result.data.blocking_issues) == 0


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
    assert state.revision_count <= 1
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


# ---------------------------------------------------------------------------
# Regression: mock mode is clean, tests don't need real API keys
# ---------------------------------------------------------------------------


def test_mock_mode_has_no_llm_fallback_warning():
    """Pure mock mode must not produce fallback warnings — they indicate unexpected fallback."""
    from blogagent.agents.editor_agent import generate_research_plan

    result = generate_research_plan("Test")
    assert result.warning is None


def test_pipeline_completes_without_api_keys(monkeypatch):
    """Pipeline must complete in mock mode with no API keys."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")

    from blogagent.workflow.graph import run_pipeline, validate_final_state

    state = run_pipeline("Photosynthesis")
    assert state.final_article_package is not None
    errors = validate_final_state(state)
    assert errors == []


# ---------------------------------------------------------------------------
# parse_json_object — fences, surrounding text, strict
# ---------------------------------------------------------------------------


def test_parse_json_object_strict():
    from blogagent.llm.client import parse_json_object

    data = parse_json_object('{"key": "value"}')
    assert data == {"key": "value"}


def test_parse_json_object_strips_json_fence():
    from blogagent.llm.client import parse_json_object

    fenced = '```json\n{"research_questions": ["q1", "q2"]}\n```'
    data = parse_json_object(fenced)
    assert data == {"research_questions": ["q1", "q2"]}


def test_parse_json_object_strips_plain_fence():
    from blogagent.llm.client import parse_json_object

    fenced = '```\n{"key": 1}\n```'
    data = parse_json_object(fenced)
    assert data == {"key": 1}


def test_parse_json_object_extracts_from_surrounding_text():
    from blogagent.llm.client import parse_json_object

    surrounded = 'Here is the result:\n{"answer": 42}\nHope that helps!'
    data = parse_json_object(surrounded)
    assert data == {"answer": 42}


def test_parse_json_object_raises_on_invalid():
    import json

    from blogagent.llm.client import parse_json_object

    with pytest.raises(json.JSONDecodeError):
        parse_json_object("not json at all")


# ---------------------------------------------------------------------------
# JSON repair retry — malformed → repair → success keeps is_mock=False
# ---------------------------------------------------------------------------


def test_malformed_json_triggers_repair_before_mock_fallback(monkeypatch):
    """First call returns malformed JSON; second (repair) call returns valid JSON.
    Result must be is_mock=False with structured_output_repaired=true warning."""
    from blogagent.llm.providers import GoogleProvider, ProviderResponse

    call_count = [0]

    def fake_generate(self, system_prompt, user_prompt, temperature=0.2):
        call_count[0] += 1
        if call_count[0] == 1:
            # Missing comma → JSONDecodeError
            return ProviderResponse(
                text='{"research_questions": ["q1" "q2"]}',
                model="gemini-2.5-flash",
                provider="google",
            )
        # Repair call returns valid JSON
        return ProviderResponse(
            text='{"research_questions": ["q1", "q2"]}',
            model="gemini-2.5-flash",
            provider="google",
        )

    monkeypatch.setattr(GoogleProvider, "generate", fake_generate)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert call_count[0] == 2, "Repair call was not attempted"
    assert result.is_mock is False
    assert result.warning == "structured_output_repaired=true"


def test_repair_success_preserves_live_provider_data(monkeypatch):
    """After a successful repair, the returned data is from the live provider (not mock)."""
    from blogagent.llm.providers import GoogleProvider, ProviderResponse

    def fake_generate(self, system_prompt, user_prompt, temperature=0.2):
        if temperature == 0.0:
            # repair call
            return ProviderResponse(
                text='{"research_questions": ["repaired q1", "repaired q2"]}',
                model="gemini-2.5-flash",
                provider="google",
            )
        # first call — malformed
        return ProviderResponse(
            text="INVALID {research_questions: [broken",
            model="gemini-2.5-flash",
            provider="google",
        )

    monkeypatch.setattr(GoogleProvider, "generate", fake_generate)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.is_mock is False
    assert result.provider == "google"
    assert result.data.research_questions == ["repaired q1", "repaired q2"]


def test_failed_repair_falls_back_to_mock(monkeypatch):
    """Both parse and repair fail → is_mock=True with error set."""
    from blogagent.llm.providers import GoogleProvider, ProviderResponse

    def always_bad(self, system_prompt, user_prompt, temperature=0.2):
        return ProviderResponse(
            text="not json at all",
            model="gemini-2.5-flash",
            provider="google",
        )

    monkeypatch.setattr(GoogleProvider, "generate", always_bad)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=ResearchPlanOutput,
    )
    assert result.is_mock is True
    assert result.error is not None
    assert "repair" in result.error.lower() or "failed" in result.error.lower()


# ---------------------------------------------------------------------------
# Recommendation prompt — exact count rule
# ---------------------------------------------------------------------------


def test_recommendation_draft_prompt_includes_exact_count_rule():
    """Draft prompt must instruct the model to obey the exact requested count."""
    from blogagent.agents import prompts

    p = prompts.RECOMMENDATION_DRAFT_PROMPT.lower()
    assert "exactly" in p or "exact" in p, (
        "RECOMMENDATION_DRAFT_PROMPT is missing an exact-count rule"
    )


def test_recommendation_draft_prompt_forbids_one_more():
    """Prompt must explicitly say 'not one more'."""
    from blogagent.agents import prompts

    p = prompts.RECOMMENDATION_DRAFT_PROMPT.lower()
    assert (
        "not one more" in p
        or "not more" in p
        or "not 1 more" in p
        or "not exceed" in p
        or ("exactly" in p and "more" in p)
    ), "Prompt must guard against producing one extra item"


def test_mock_recommendation_quick_picks_does_not_exceed_requested_count():
    """Mock draft for 'Top 10' topic must not produce more than 10 Quick Picks bullets."""
    import re

    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Top 10 running shoes for beginners")
    assert state.final_article_package is not None
    article = state.final_article_package.article_markdown

    match = re.search(r"## Quick Picks\n(.*?)(?=\n##|\Z)", article, re.DOTALL)
    if match:
        bullets = re.findall(r"^[-*]", match.group(1), re.MULTILINE)
        assert len(bullets) <= 10, (
            f"Quick Picks has {len(bullets)} bullets for a 'Top 10' topic — must be ≤10"
        )


# ---------------------------------------------------------------------------
# Repeated-text guardrail
# ---------------------------------------------------------------------------


def test_detect_repeated_excerpts_catches_repeated_sentences():
    """detect_repeated_excerpts flags a sentence that appears in 3+ sections."""
    from blogagent.llm.client import detect_repeated_excerpts

    repeated = "This is a very long sentence that appears in multiple sections of the article text."
    article = "\n".join(
        [
            "## Section One",
            f"Some intro. {repeated}",
            "",
            "## Section Two",
            f"More content. {repeated}",
            "",
            "## Section Three",
            f"Even more. {repeated}",
        ]
    )
    warnings = detect_repeated_excerpts(article, min_phrase_length=30, threshold=3)
    assert len(warnings) >= 1
    assert any("repeated" in w.lower() for w in warnings)


def test_detect_repeated_excerpts_no_false_positive():
    """detect_repeated_excerpts should not flag short or non-repeated text."""
    from blogagent.llm.client import detect_repeated_excerpts

    article = "\n".join(
        [
            "## Introduction",
            "Solar energy is a renewable resource that powers homes and businesses worldwide.",
            "",
            "## Key Facts",
            "Photovoltaic cells convert sunlight into electricity using semiconductor materials.",
            "",
            "## Conclusion",
            "Continued investment in solar infrastructure is essential for a sustainable future.",
        ]
    )
    warnings = detect_repeated_excerpts(article, threshold=3)
    assert warnings == []


def test_detect_repeated_excerpts_threshold_two():
    """A phrase in exactly 2 sections is not flagged with threshold=3."""
    from blogagent.llm.client import detect_repeated_excerpts

    repeated = "This is a very specific sentence that appears more than once in the document here."
    article = "\n".join(
        [
            "## Section One",
            repeated,
            "",
            "## Section Two",
            repeated,
            "",
            "## Section Three",
            "Something completely different and unrelated to the earlier content.",
        ]
    )
    warnings = detect_repeated_excerpts(article, min_phrase_length=30, threshold=3)
    assert warnings == []


def test_pipeline_repeated_text_guardrail_does_not_break_pipeline():
    """Pipeline must complete normally even when the repeated-text guardrail fires."""
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("The water cycle")
    assert state.final_article_package is not None
    assert state.blocked is False


# ---------------------------------------------------------------------------
# clean_article_markdown — fence stripping
# ---------------------------------------------------------------------------


def test_clean_article_markdown_strips_markdown_fence():
    from blogagent.llm.client import clean_article_markdown

    fenced = "```markdown\n# Title\n\nContent here.\n```"
    result = clean_article_markdown(fenced)
    assert result.startswith("# Title")
    assert "```" not in result


def test_clean_article_markdown_strips_plain_fence():
    from blogagent.llm.client import clean_article_markdown

    fenced = "```\n# Title\n\nContent here.\n```"
    result = clean_article_markdown(fenced)
    assert result.startswith("# Title")
    assert "```" not in result


def test_clean_article_markdown_preserves_no_fence_content():
    from blogagent.llm.client import clean_article_markdown

    article = "# Title\n\nContent here."
    result = clean_article_markdown(article)
    assert result == article


def test_clean_article_markdown_preserves_internal_code_fences():
    from blogagent.llm.client import clean_article_markdown

    article = "# Title\n\n```python\nprint('hi')\n```\n\nMore content."
    result = clean_article_markdown(article)
    assert "```python" in result


def test_clean_article_markdown_empty_returns_empty():
    from blogagent.llm.client import clean_article_markdown

    assert clean_article_markdown("") == ""


# ---------------------------------------------------------------------------
# DraftOutput missing-field completion — no mock fallback when article exists
# ---------------------------------------------------------------------------


def test_missing_meta_description_does_not_cause_mock_fallback(monkeypatch):
    """Gemini returns article_markdown but omits meta_description → no mock fallback."""
    import json

    from blogagent.llm.providers import GoogleProvider, ProviderResponse

    def fake_generate(self, system_prompt, user_prompt, temperature=0.2):
        # Missing meta_description intentionally
        payload = {
            "article_markdown": "# Great Perfumes\n\nPerfume is wonderful for summer use.",
            "seo_keywords": ["perfume", "summer"],
        }
        return ProviderResponse(
            text=json.dumps(payload),
            model="gemini-2.5-flash",
            provider="google",
        )

    monkeypatch.setattr(GoogleProvider, "generate", fake_generate)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=DraftOutput,
    )
    assert result.is_mock is False, f"Should not fall back to mock: error={result.error}"
    assert result.provider == "google"
    assert result.data is not None
    assert result.data.article_markdown.startswith("# Great Perfumes")
    assert result.data.meta_description.strip() != ""
    assert result.warning == "structured_output_completed_missing_fields=true"


def test_missing_meta_description_synthesised_from_article(monkeypatch):
    """Synthesised meta_description should come from first prose paragraph."""
    import json

    from blogagent.llm.providers import GoogleProvider, ProviderResponse

    def fake_generate(self, system_prompt, user_prompt, temperature=0.2):
        payload = {
            "article_markdown": (
                "# Summer Scents\n\n"
                "Perfume is a wonderful way to express yourself in summer heat. "
                "The right fragrance can lift your mood and leave a lasting impression."
            ),
        }
        return ProviderResponse(
            text=json.dumps(payload),
            model="gemini-2.5-flash",
            provider="google",
        )

    monkeypatch.setattr(GoogleProvider, "generate", fake_generate)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=DraftOutput,
    )
    assert result.is_mock is False
    desc = result.data.meta_description
    assert "Perfume" in desc or "summer" in desc.lower()


def test_no_article_markdown_still_falls_back_to_mock(monkeypatch):
    """When article_markdown is empty, field completion cannot help → mock fallback."""
    from blogagent.llm.providers import GoogleProvider, ProviderResponse

    def fake_generate(self, system_prompt, user_prompt, temperature=0.2):
        # No article_markdown either
        return ProviderResponse(
            text="not json at all",
            model="gemini-2.5-flash",
            provider="google",
        )

    monkeypatch.setattr(GoogleProvider, "generate", fake_generate)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=DraftOutput,
    )
    assert result.is_mock is True


def test_article_markdown_fence_stripped_in_draft_output(monkeypatch):
    """article_markdown wrapped in ```markdown fences should be stripped."""
    import json

    from blogagent.llm.providers import GoogleProvider, ProviderResponse

    def fake_generate(self, system_prompt, user_prompt, temperature=0.2):
        payload = {
            "article_markdown": "```markdown\n# Summer Scents\n\nContent here.\n```",
            "meta_description": "A guide to summer scents.",
            "seo_keywords": ["summer", "scents"],
        }
        return ProviderResponse(
            text=json.dumps(payload),
            model="gemini-2.5-flash",
            provider="google",
        )

    monkeypatch.setattr(GoogleProvider, "generate", fake_generate)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    result = generate_structured(
        system_prompt="s",
        user_prompt="u",
        output_model=DraftOutput,
    )
    assert result.is_mock is False
    assert not result.data.article_markdown.startswith("```"), (
        f"Fences not stripped: {result.data.article_markdown[:50]!r}"
    )
    assert result.data.article_markdown.startswith("# Summer Scents")


# ---------------------------------------------------------------------------
# Post-article recommendation grounding integration
# ---------------------------------------------------------------------------


def test_pipeline_grounds_recommendations_for_recommendation_topic():
    """Pipeline should populate article_recommendations_count in candidates summary."""
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("7 best perfumes for summer")
    cs = state.recommendation_candidates_summary
    # article_recommendations_count should be present (even if 0 in mock mode)
    assert "article_recommendations_count" in cs

    # grounded_recommendations_count should also be present
    assert "grounded_recommendations_count" in cs


def test_pipeline_non_recommendation_topic_skips_grounding():
    """Non-recommendation topics should not have article recommendation grounding."""
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("How photosynthesis works")
    assert not state.is_recommendation
    # recommendation_candidates_summary should be empty (no grounding ran)
    cs = state.recommendation_candidates_summary
    assert cs == {} or cs.get("article_recommendations_count") is None
