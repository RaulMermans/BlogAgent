"""Tests for blogagent.evals.compare_outputs and the CLI compare command."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from blogagent.cli import _build_parser, cmd_compare
from blogagent.evals.compare_outputs import (
    MAX_SCORE,
    RUBRIC,
    compare_outputs,
    format_comparison_table,
    load_run_output,
    score_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
MOCK_FILE = EXAMPLES_DIR / "mock_elephants_output.json"
LIVE_FILE = EXAMPLES_DIR / "live_elephants_output.json"


def _minimal_package(**overrides) -> dict:
    """Return a minimal valid ArticlePackage dict."""
    base: dict = {
        "title": "Test Title",
        "meta_description": "A test meta description for the article.",
        "article_markdown": "# Heading\n\n" + "word " * 650,
        "revision_summary": "No issues found.",
        "source_list": [
            {"url": f"https://example.com/{i}", "title": f"Source {i}", "domain": "example.com",
             "credibility_score": 0.8, "relevance_score": 0.8, "recency_score": 0.8,
             "overall_score": 0.8, "notes": "", "is_mock": False}
            for i in range(3)
        ],
        "fact_check_report": {
            "total_claims": 2,
            "supported_count": 2,
            "partially_supported_count": 0,
            "unsupported_count": 0,
            "passed": True,
            "blocking_issues": [],
            "matches": [],
        },
        "claim_support_statuses": [],
        "slug": "test-title",
        "seo_keywords": ["test"],
        "run_id": "test-run-id",
        "created_at": "2026-01-01T00:00:00+00:00",
        "topic": "Test Topic",
    }
    base.update(overrides)
    return base


def _mock_only_package() -> dict:
    """Return a package where all sources have is_mock=True."""
    base = _minimal_package()
    for s in base["source_list"]:
        s["is_mock"] = True
    return base


# ---------------------------------------------------------------------------
# score_output — quality rubric
# ---------------------------------------------------------------------------


def test_score_output_perfect_score():
    score, notes = score_output(_minimal_package())
    assert score == MAX_SCORE == 100
    assert notes == []


def test_score_output_is_deterministic():
    data = _minimal_package()
    s1, n1 = score_output(data)
    s2, n2 = score_output(data)
    assert s1 == s2
    assert n1 == n2


def test_score_output_missing_title_deducted():
    score, notes = score_output(_minimal_package(title=""))
    assert score == MAX_SCORE - RUBRIC["valid_title"]
    assert any("title" in n for n in notes)


def test_score_output_missing_meta_description_deducted():
    score, notes = score_output(_minimal_package(meta_description=""))
    assert score == MAX_SCORE - RUBRIC["valid_meta_description"]
    assert any("meta" in n for n in notes)


def test_score_output_no_headings_deducted():
    # Use enough words to pass the 600-word check; no # heading
    score, notes = score_output(_minimal_package(article_markdown="word " * 700))
    assert score == MAX_SCORE - RUBRIC["has_headings"]
    assert any("heading" in n for n in notes)


def test_score_output_under_600_words_deducted():
    score, notes = score_output(_minimal_package(article_markdown="# Head\n\nShort article."))
    assert score == MAX_SCORE - RUBRIC["over_600_words"]
    assert any("600" in n for n in notes)


def test_score_output_fewer_than_3_sources_deducted():
    pkg = _minimal_package()
    pkg["source_list"] = pkg["source_list"][:2]
    score, notes = score_output(pkg)
    assert score == MAX_SCORE - RUBRIC["at_least_3_sources"]
    assert any("source" in n for n in notes)


def test_score_output_unsupported_high_importance_deducted():
    pkg = _minimal_package()
    pkg["claim_support_statuses"] = [
        {
            "claim": {"text": "Bad claim", "importance": "high", "section": "Intro"},
            "status": "unsupported",
            "supporting_sources": [],
            "notes": "",
        }
    ]
    score, notes = score_output(pkg)
    assert score == MAX_SCORE - RUBRIC["no_unsupported_high_importance"]
    assert any("unsupported" in n for n in notes)


def test_score_output_high_importance_supported_not_penalised():
    pkg = _minimal_package()
    pkg["claim_support_statuses"] = [
        {
            "claim": {"text": "Good claim", "importance": "high", "section": "Intro"},
            "status": "supported",
            "supporting_sources": ["https://example.com/1"],
            "notes": "",
        }
    ]
    score, _ = score_output(pkg)
    assert score == MAX_SCORE


def test_score_output_mock_only_sources_deducted():
    score, notes = score_output(_mock_only_package())
    assert score == MAX_SCORE - RUBRIC["not_pure_mock"]
    assert any("mock" in n for n in notes)


def test_score_output_mixed_sources_not_penalised():
    pkg = _mock_only_package()
    pkg["source_list"][0]["is_mock"] = False  # at least one real source
    score, notes = score_output(pkg)
    assert score == MAX_SCORE
    assert not any("mock" in n for n in notes)


def test_score_output_empty_revision_summary_deducted():
    score, notes = score_output(_minimal_package(revision_summary=""))
    assert score == MAX_SCORE - RUBRIC["clear_revision_summary"]
    assert any("revision" in n for n in notes)


def test_score_output_nonempty_revision_summary_scores_full():
    score, _ = score_output(_minimal_package(revision_summary="No revision performed."))
    assert score == MAX_SCORE


def test_score_output_max_is_100():
    assert MAX_SCORE == 100


# ---------------------------------------------------------------------------
# load_run_output — file loading
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_error():
    metrics, data = load_run_output(Path("/nonexistent/path/file.json"))
    assert metrics.load_error != ""
    assert data is None


def test_load_invalid_json_returns_error(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json {{{")
    metrics, data = load_run_output(bad)
    assert metrics.load_error != ""
    assert data is None


def test_load_non_object_json_returns_error(tmp_path: Path):
    arr = tmp_path / "array.json"
    arr.write_text("[1, 2, 3]")
    metrics, data = load_run_output(arr)
    assert metrics.load_error != ""
    assert data is None


def test_load_valid_file_returns_metrics(tmp_path: Path):
    f = tmp_path / "output.json"
    f.write_text(json.dumps(_minimal_package()))
    metrics, data = load_run_output(f)
    assert metrics.load_error == ""
    assert data is not None
    assert metrics.has_title is True
    assert metrics.word_count >= 600


def test_load_file_extracts_execution_mode(tmp_path: Path):
    pkg = _minimal_package()
    pkg["execution_mode"] = "live"
    f = tmp_path / "out.json"
    f.write_text(json.dumps(pkg))
    metrics, _ = load_run_output(f)
    assert metrics.execution_mode == "live"


def test_load_file_defaults_execution_mode_unknown(tmp_path: Path):
    f = tmp_path / "out.json"
    f.write_text(json.dumps(_minimal_package()))
    metrics, _ = load_run_output(f)
    assert metrics.execution_mode == "unknown"


def test_load_file_extracts_mock_source_count(tmp_path: Path):
    pkg = _mock_only_package()
    f = tmp_path / "out.json"
    f.write_text(json.dumps(pkg))
    metrics, _ = load_run_output(f)
    assert metrics.mock_source_count == 3
    assert metrics.source_count == 3


def test_load_file_extracts_claim_counts(tmp_path: Path):
    pkg = _minimal_package()
    pkg["fact_check_report"]["supported_count"] = 2
    pkg["fact_check_report"]["partially_supported_count"] = 1
    pkg["fact_check_report"]["unsupported_count"] = 0
    pkg["fact_check_report"]["total_claims"] = 3
    f = tmp_path / "out.json"
    f.write_text(json.dumps(pkg))
    metrics, _ = load_run_output(f)
    assert metrics.supported_count == 2
    assert metrics.partially_supported_count == 1
    assert metrics.unsupported_count == 0
    assert metrics.total_claims == 3


# ---------------------------------------------------------------------------
# compare_outputs
# ---------------------------------------------------------------------------


def test_compare_outputs_returns_one_metrics_per_path(tmp_path: Path):
    f1 = tmp_path / "a.json"
    f2 = tmp_path / "b.json"
    f1.write_text(json.dumps(_minimal_package(title="A")))
    f2.write_text(json.dumps(_minimal_package(title="B")))
    results = compare_outputs([f1, f2])
    assert len(results) == 2


def test_compare_outputs_missing_file_in_list(tmp_path: Path):
    f1 = tmp_path / "good.json"
    f1.write_text(json.dumps(_minimal_package()))
    missing = tmp_path / "missing.json"
    results = compare_outputs([f1, missing])
    assert results[0].load_error == ""
    assert results[1].load_error != ""


# ---------------------------------------------------------------------------
# format_comparison_table
# ---------------------------------------------------------------------------


def test_format_table_contains_filenames(tmp_path: Path):
    f = tmp_path / "myoutput.json"
    f.write_text(json.dumps(_minimal_package()))
    metrics = compare_outputs([f])
    table = format_comparison_table(metrics)
    assert "myoutput.json" in table


def test_format_table_contains_score(tmp_path: Path):
    f = tmp_path / "out.json"
    f.write_text(json.dumps(_minimal_package()))
    metrics = compare_outputs([f])
    table = format_comparison_table(metrics)
    assert "100" in table


def test_format_table_shows_error_for_missing_file():
    metrics = compare_outputs([Path("/nonexistent/file.json")])
    table = format_comparison_table(metrics)
    assert "ERROR" in table or "error" in table.lower()


def test_format_table_shows_all_sections(tmp_path: Path):
    f = tmp_path / "out.json"
    f.write_text(json.dumps(_minimal_package()))
    metrics = compare_outputs([f])
    table = format_comparison_table(metrics)
    for section in ("METADATA", "ARTICLE", "SOURCES", "CLAIMS", "QUALITY"):
        assert section in table, f"Missing section: {section}"


def test_format_table_column_headers_not_glued_together(tmp_path: Path):
    """Column headers for two adjacent files must have visible space between them."""
    f1 = tmp_path / "mock_output.json"
    f2 = tmp_path / "live_output.json"
    f1.write_text(json.dumps(_minimal_package()))
    f2.write_text(json.dumps(_minimal_package()))
    metrics = compare_outputs([f1, f2])
    table = format_comparison_table(metrics)
    # The two filenames must not appear immediately adjacent (no space between them)
    assert "mock_output.jsonlive_output.json" not in table


def test_format_table_two_files_both_filenames_visible(tmp_path: Path):
    """Both filenames should appear in the header row of a two-file comparison."""
    f1 = tmp_path / "alpha_run.json"
    f2 = tmp_path / "beta_run.json"
    f1.write_text(json.dumps(_minimal_package()))
    f2.write_text(json.dumps(_minimal_package()))
    metrics = compare_outputs([f1, f2])
    table = format_comparison_table(metrics)
    assert "alpha_run.json" in table
    assert "beta_run.json" in table


def test_format_table_live_supported_shows_citation_judge_warning(tmp_path: Path):
    """Live mode with supported claims should emit a citation judge warning."""
    pkg = _minimal_package()
    pkg["execution_mode"] = "live"
    pkg["fact_check_report"]["supported_count"] = 2
    f = tmp_path / "live_run.json"
    f.write_text(json.dumps(pkg))
    metrics = compare_outputs([f])
    table = format_comparison_table(metrics)
    assert "BLOGAGENT_USE_LLM_CITATION_JUDGE" in table


def test_format_table_mock_mode_no_citation_judge_warning(tmp_path: Path):
    """Mock mode should not show the citation judge warning."""
    pkg = _minimal_package()
    pkg["execution_mode"] = "mock"
    f = tmp_path / "mock_run.json"
    f.write_text(json.dumps(pkg))
    metrics = compare_outputs([f])
    table = format_comparison_table(metrics)
    assert "BLOGAGENT_USE_LLM_CITATION_JUDGE" not in table


# ---------------------------------------------------------------------------
# Mock-only sources do not score as production-grounded
# ---------------------------------------------------------------------------


def test_mock_only_sources_lose_not_pure_mock_points():
    score_mock, _ = score_output(_mock_only_package())
    score_real, _ = score_output(_minimal_package())
    assert score_real - score_mock == RUBRIC["not_pure_mock"]


def test_mock_output_quality_score_less_than_live(tmp_path: Path):
    mock_pkg = _mock_only_package()
    mock_pkg["article_markdown"] = "# Head\n\nShort mock article."
    live_pkg = _minimal_package()

    f_mock = tmp_path / "mock.json"
    f_live = tmp_path / "live.json"
    f_mock.write_text(json.dumps(mock_pkg))
    f_live.write_text(json.dumps(live_pkg))

    results = compare_outputs([f_mock, f_live])
    assert results[0].quality_score < results[1].quality_score


# ---------------------------------------------------------------------------
# Example files (integration-style)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not MOCK_FILE.exists() or not LIVE_FILE.exists(),
    reason="Example files not found",
)
def test_example_mock_file_loads_cleanly():
    metrics, data = load_run_output(MOCK_FILE)
    assert metrics.load_error == ""
    assert data is not None
    assert metrics.has_title


@pytest.mark.skipif(
    not MOCK_FILE.exists() or not LIVE_FILE.exists(),
    reason="Example files not found",
)
def test_example_live_file_scores_higher_than_mock():
    results = compare_outputs([MOCK_FILE, LIVE_FILE])
    mock_m, live_m = results
    assert mock_m.load_error == ""
    assert live_m.load_error == ""
    assert live_m.quality_score > mock_m.quality_score


@pytest.mark.skipif(
    not MOCK_FILE.exists() or not LIVE_FILE.exists(),
    reason="Example files not found",
)
def test_example_mock_file_has_all_mock_sources():
    metrics, _ = load_run_output(MOCK_FILE)
    assert metrics.source_count > 0
    assert metrics.mock_source_count == metrics.source_count


@pytest.mark.skipif(
    not MOCK_FILE.exists() or not LIVE_FILE.exists(),
    reason="Example files not found",
)
def test_example_live_file_has_no_mock_sources():
    metrics, _ = load_run_output(LIVE_FILE)
    assert metrics.mock_source_count == 0


# ---------------------------------------------------------------------------
# CLI compare command
# ---------------------------------------------------------------------------


def _run_compare(argv: list[str]) -> tuple[int, str]:
    parser = _build_parser()
    args = parser.parse_args(argv)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cmd_compare(args)
    return code, buf.getvalue()


def test_cli_compare_exits_zero_with_valid_files(tmp_path: Path):
    f1 = tmp_path / "a.json"
    f2 = tmp_path / "b.json"
    f1.write_text(json.dumps(_minimal_package(title="A", execution_mode="mock")))
    f2.write_text(json.dumps(_minimal_package(title="B", execution_mode="live")))
    code, _ = _run_compare(["compare", str(f1), str(f2)])
    assert code == 0


def test_cli_compare_prints_table(tmp_path: Path):
    f1 = tmp_path / "a.json"
    f1.write_text(json.dumps(_minimal_package()))
    _, output = _run_compare(["compare", str(f1)])
    assert "QUALITY" in output or "score" in output.lower()


def test_cli_compare_exits_nonzero_for_missing_file(tmp_path: Path):
    f1 = tmp_path / "good.json"
    f1.write_text(json.dumps(_minimal_package()))
    missing = tmp_path / "missing.json"
    code, _ = _run_compare(["compare", str(f1), str(missing)])
    assert code != 0


def test_cli_compare_exits_2_when_all_files_missing(tmp_path: Path):
    code, _ = _run_compare(["compare", str(tmp_path / "x.json"), str(tmp_path / "y.json")])
    assert code == 2


@pytest.mark.skipif(
    not MOCK_FILE.exists() or not LIVE_FILE.exists(),
    reason="Example files not found",
)
def test_cli_compare_example_files_exits_zero():
    code, output = _run_compare(["compare", str(MOCK_FILE), str(LIVE_FILE)])
    assert code == 0
    assert "mock_elephants" in output
    assert "live_elephants" in output
