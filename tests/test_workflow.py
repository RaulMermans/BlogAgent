from blogagent.workflow.graph import run_pipeline, validate_final_state
from blogagent.workflow.state import CitationStatus, ClaimImportance, CitationMatch, Claim


def test_pipeline_returns_state_with_correct_topic():
    state = run_pipeline("Climate Change")
    assert state.topic == "Climate Change"


def test_pipeline_strips_topic_whitespace():
    state = run_pipeline("  Solar Energy  ")
    assert state.topic == "Solar Energy"


def test_pipeline_produces_research_questions():
    state = run_pipeline("The Water Cycle")
    assert len(state.research_questions) >= 1


def test_pipeline_produces_source_scores():
    state = run_pipeline("The History of the Internet")
    assert len(state.source_scores) >= 3


def test_pipeline_produces_evidence_table():
    state = run_pipeline("Renewable Energy")
    assert len(state.evidence_table) >= 1


def test_pipeline_produces_outline():
    state = run_pipeline("Quantum Computing")
    assert state.outline is not None
    assert state.outline.title
    assert len(state.outline.sections) >= 1


def test_pipeline_produces_non_empty_draft():
    state = run_pipeline("The Solar System")
    assert state.draft.strip() != ""


def test_pipeline_produces_article_package():
    state = run_pipeline("The History of Writing")
    assert state.final_article_package is not None
    pkg = state.final_article_package
    assert pkg.article_markdown.strip()
    assert pkg.source_list
    assert pkg.fact_check_report is not None
    assert pkg.revision_summary.strip()
    assert pkg.topic == "The History of Writing"


def test_pipeline_passes_all_validators():
    state = run_pipeline("The Solar System")
    errors = validate_final_state(state)
    assert errors == [], f"Validation errors: {errors}"


def test_validate_final_state_fails_when_package_is_none():
    from blogagent.workflow.state import BlogRunState
    state = BlogRunState(topic="X")
    errors = validate_final_state(state)
    assert errors != []


def test_pipeline_run_id_is_set():
    state = run_pipeline("Photosynthesis")
    assert state.run_id != ""
    assert state.final_article_package is not None
    assert state.final_article_package.run_id == state.run_id
