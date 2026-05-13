"""Tests for blogagent.cli — smoke-test command."""

from __future__ import annotations

import json
from pathlib import Path

from blogagent.cli import _build_parser, cmd_run

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(argv: list[str]) -> tuple[int, str]:
    """Parse argv and call cmd_run; capture stdout and return (exit_code, output)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cmd_run(args)
    return code, buf.getvalue()


# ---------------------------------------------------------------------------
# Basic smoke tests
# ---------------------------------------------------------------------------


def test_cli_mock_run_exits_zero():
    code, _ = _run(["run", "Why elephants are the heaviest land animals"])
    assert code == 0


def test_cli_mock_run_prints_title():
    _, output = _run(["run", "Photosynthesis"])
    assert "Title:" in output


def test_cli_mock_run_prints_source_count():
    _, output = _run(["run", "Photosynthesis"])
    assert "Sources:" in output


def test_cli_mock_run_prints_execution_mode():
    _, output = _run(["run", "Photosynthesis"])
    assert "Execution mode:" in output
    assert "mock" in output


def test_cli_mock_run_prints_validation_ok():
    _, output = _run(["run", "Photosynthesis"])
    assert "OK" in output


# ---------------------------------------------------------------------------
# --show-trace
# ---------------------------------------------------------------------------


def test_cli_show_trace_prints_trace_section():
    _, output = _run(["run", "Photosynthesis", "--show-trace"])
    assert "Run Trace" in output


def test_cli_show_trace_prints_provider_events():
    _, output = _run(["run", "Photosynthesis", "--show-trace"])
    assert "[INFO]" in output


def test_cli_show_trace_prints_stage_timings():
    _, output = _run(["run", "Photosynthesis", "--show-trace"])
    assert "Stage timings" in output


# ---------------------------------------------------------------------------
# --json flag
# ---------------------------------------------------------------------------


def test_cli_json_flag_produces_parseable_json():
    _, output = _run(["run", "Solar energy", "--json"])
    parsed = json.loads(output)
    assert isinstance(parsed, dict)


def test_cli_json_output_has_article_markdown():
    _, output = _run(["run", "Solar energy", "--json"])
    parsed = json.loads(output)
    assert "article_markdown" in parsed
    assert parsed["article_markdown"].strip() != ""


def test_cli_json_output_has_fact_check_report():
    _, output = _run(["run", "Solar energy", "--json"])
    parsed = json.loads(output)
    assert "fact_check_report" in parsed


def test_cli_json_exit_code_zero_on_success():
    code, _ = _run(["run", "Solar energy", "--json"])
    assert code == 0


# ---------------------------------------------------------------------------
# --output flag
# ---------------------------------------------------------------------------


def test_cli_output_flag_writes_file(tmp_path: Path):
    out_file = tmp_path / "smoke_output.json"
    _run(["run", "Climate change", "--output", str(out_file)])
    assert out_file.exists()


def test_cli_output_file_contains_valid_json(tmp_path: Path):
    out_file = tmp_path / "smoke_output.json"
    _run(["run", "Climate change", "--output", str(out_file)])
    data = json.loads(out_file.read_text())
    assert isinstance(data, dict)


def test_cli_output_file_has_article_markdown(tmp_path: Path):
    out_file = tmp_path / "smoke_output.json"
    _run(["run", "Climate change", "--output", str(out_file)])
    data = json.loads(out_file.read_text())
    assert "article_markdown" in data


# ---------------------------------------------------------------------------
# Blocked publishing request
# ---------------------------------------------------------------------------


def test_cli_blocked_topic_exits_nonzero():
    code, _ = _run(["run", "Publish this article to WordPress immediately"])
    assert code != 0


def test_cli_blocked_topic_prints_blocked():
    _, output = _run(["run", "Publish this article to WordPress immediately"])
    assert "BLOCKED" in output


def test_cli_blocked_topic_shows_trace_when_requested():
    _, output = _run(["run", "Post this article to Medium", "--show-trace"])
    assert "BLOCKED" in output
    assert "Run Trace" in output


# ---------------------------------------------------------------------------
# Streamlit caption no longer stale
# ---------------------------------------------------------------------------


def test_streamlit_caption_does_not_say_not_implemented():
    caption_file = Path(__file__).parent.parent / "app" / "ui" / "streamlit_app.py"
    content = caption_file.read_text()
    assert "Real LLM calls are not implemented yet" not in content


def test_streamlit_caption_mentions_mock_mode():
    caption_file = Path(__file__).parent.parent / "app" / "ui" / "streamlit_app.py"
    content = caption_file.read_text()
    assert "Mock mode" in content or "mock mode" in content


def test_streamlit_caption_mentions_no_publishing():
    caption_file = Path(__file__).parent.parent / "app" / "ui" / "streamlit_app.py"
    content = caption_file.read_text()
    assert "publishing" in content.lower()
