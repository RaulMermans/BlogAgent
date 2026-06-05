"""Tests for _PolishOutput structured completion in llm/client.py.

Verifies that:
- polished_markdown present + missing fields → synthesize, no fallback
- polished_markdown missing → falls back to mock correctly
- synthesized summary is deterministic and non-empty
"""

from __future__ import annotations

import json

from blogagent.agents.editorial_polish_agent import EditorialPolishOutput
from blogagent.llm.client import _try_complete_polish_output

_SAMPLE_MARKDOWN = (
    "# Best AI Tools for Students\n\n"
    "## Quick Picks\n\n"
    "- **Best Overall:** ChatGPT\n"
    "- **Best Writing:** Grammarly\n\n"
    "## ChatGPT\n\nExcellent research assistant.\n\n"
    "## Final Takeaway\n\nGreat options for students.\n"
)


class TestTryCompletePolishOutput:
    """_try_complete_polish_output handles partial Gemini responses."""

    def test_polished_markdown_with_missing_polish_summary_completes(self):
        """polished_markdown present but polish_summary missing → synthesize summary."""
        raw = json.dumps(
            {
                "polished_markdown": _SAMPLE_MARKDOWN,
                # polish_summary missing
                "remaining_issues": [],
                "publishability_confidence": 0.8,
            }
        )
        result, ok = _try_complete_polish_output(raw, EditorialPolishOutput)
        assert ok is True
        assert result is not None
        assert result.polished_markdown == _SAMPLE_MARKDOWN
        assert isinstance(result.polish_summary, list)
        assert len(result.polish_summary) > 0
        assert "synthesized" in result.polish_summary[0].lower()

    def test_polished_markdown_with_empty_polish_summary_completes(self):
        """polished_markdown present but polish_summary is empty → synthesize."""
        raw = json.dumps(
            {
                "polished_markdown": _SAMPLE_MARKDOWN,
                "polish_summary": [],  # empty list
                "remaining_issues": [],
                "publishability_confidence": 0.75,
            }
        )
        # Empty list is falsy, so it should be synthesized
        result, ok = _try_complete_polish_output(raw, EditorialPolishOutput)
        assert ok is True
        assert result is not None
        # polish_summary should be synthesized since it was empty
        assert isinstance(result.polish_summary, list)

    def test_polished_markdown_missing_falls_back(self):
        """polished_markdown missing → cannot complete, returns (None, False)."""
        raw = json.dumps(
            {
                # polished_markdown missing
                "polish_summary": ["polish applied"],
                "remaining_issues": [],
                "publishability_confidence": 0.8,
            }
        )
        result, ok = _try_complete_polish_output(raw, EditorialPolishOutput)
        assert ok is False
        assert result is None

    def test_empty_polished_markdown_falls_back(self):
        """Empty polished_markdown → cannot complete."""
        raw = json.dumps(
            {
                "polished_markdown": "",
                "polish_summary": [],
                "remaining_issues": [],
                "publishability_confidence": 0.5,
            }
        )
        result, ok = _try_complete_polish_output(raw, EditorialPolishOutput)
        assert ok is False

    def test_invalid_json_falls_back(self):
        """Invalid JSON → cannot complete."""
        result, ok = _try_complete_polish_output("{invalid json}", EditorialPolishOutput)
        assert ok is False
        assert result is None

    def test_wrong_output_model_falls_back(self):
        """Wrong output model → returns (None, False)."""
        from blogagent.llm.schemas import RevisionOutput

        raw = json.dumps(
            {
                "polished_markdown": _SAMPLE_MARKDOWN,
                "polish_summary": [],
                "remaining_issues": [],
                "publishability_confidence": 0.8,
            }
        )
        result, ok = _try_complete_polish_output(raw, RevisionOutput)
        assert ok is False

    def test_missing_remaining_issues_synthesized(self):
        """remaining_issues missing → default to empty list."""
        raw = json.dumps(
            {
                "polished_markdown": _SAMPLE_MARKDOWN,
                "polish_summary": ["Applied polish"],
                # remaining_issues missing
                "publishability_confidence": 0.85,
            }
        )
        result, ok = _try_complete_polish_output(raw, EditorialPolishOutput)
        assert ok is True
        assert result is not None
        assert isinstance(result.remaining_issues, list)

    def test_missing_publishability_confidence_synthesized(self):
        """publishability_confidence missing → default to 0.7."""
        raw = json.dumps(
            {
                "polished_markdown": _SAMPLE_MARKDOWN,
                "polish_summary": ["Applied polish"],
                "remaining_issues": [],
                # publishability_confidence missing
            }
        )
        result, ok = _try_complete_polish_output(raw, EditorialPolishOutput)
        assert ok is True
        assert result is not None
        assert result.publishability_confidence == 0.7

    def test_all_fields_present_validates_normally(self):
        """Complete JSON → validates normally without synthesis."""
        raw = json.dumps(
            {
                "polished_markdown": _SAMPLE_MARKDOWN,
                "polish_summary": ["Improved intro clarity", "Tightened conclusion"],
                "remaining_issues": ["Consider adding more sources"],
                "publishability_confidence": 0.82,
            }
        )
        result, ok = _try_complete_polish_output(raw, EditorialPolishOutput)
        assert ok is True
        assert result is not None
        assert result.polish_summary == ["Improved intro clarity", "Tightened conclusion"]
        assert result.publishability_confidence == 0.82

    def test_synthesized_summary_mentions_polished_markdown(self):
        """The synthesized summary must explain what happened."""
        raw = json.dumps(
            {
                "polished_markdown": _SAMPLE_MARKDOWN,
                "remaining_issues": [],
                "publishability_confidence": 0.7,
                # polish_summary missing
            }
        )
        result, ok = _try_complete_polish_output(raw, EditorialPolishOutput)
        assert ok is True
        assert result is not None
        # The summary should mention that it was synthesized
        summary_text = " ".join(result.polish_summary).lower()
        assert "synthesized" in summary_text or "polished" in summary_text
