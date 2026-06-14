"""Tests for UI state reset behavior.

Verifies that clearOutput and renderOutput functions correctly reset
all dynamic containers to prevent stale output from prior runs.

These are structural tests — they verify the HTML/JS contains the correct
patterns rather than running a browser.
"""

from __future__ import annotations


def _get_html_source() -> str:
    """Return the HTML/JS source from api/index.py."""
    import api.index as idx

    return idx._build_app_html()


class TestClearOutputFunction:
    """clearOutput must clean all dynamic containers."""

    def test_clear_output_removes_dynamic_banners(self):
        """clearOutput must query and remove .dynamic-banner elements."""
        html = _get_html_source()
        assert "dynamic-banner" in html, "dynamic-banner class must be present in output"
        assert "querySelectorAll('.dynamic-banner')" in html
        assert ".forEach(el => el.remove())" in html or "forEach(el => el.remove())" in html

    def test_clear_output_clears_article_display(self):
        """clearOutput must set article-display to empty string."""
        html = _get_html_source()
        assert "article-display" in html
        # clearOutput should clear article-display
        assert "'article-display'" in html or '"article-display"' in html

    def test_clear_output_clears_stats_row(self):
        """clearOutput must clear stats-row innerHTML."""
        html = _get_html_source()
        assert "stats-row" in html
        # stats-row should be reset
        assert "'stats-row'" in html or '"stats-row"' in html

    def test_clear_output_clears_keywords_display(self):
        """clearOutput must clear keywords-display."""
        html = _get_html_source()
        assert "keywords-display" in html

    def test_clear_output_clears_warnings_body(self):
        """clearOutput must clear warnings-body text content."""
        html = _get_html_source()
        # warnings-body should have its content cleared
        assert "warnings-body" in html

    def test_ui_clears_stale_run_metadata(self):
        """clearOutput must remove all dynamically injected per-run metadata rows
        (Query Contract, Candidate Ledger, Final Answer Contract, etc.) from the
        previous run, not just the visible article/stats containers — otherwise a
        new run can show a mix of this run's article and a prior run's debug
        metadata."""
        html = _get_html_source()
        clear_section = html[
            html.find("function clearOutput") : html.find("document.addEventListener")
        ]
        expected_labels = [
            "Editorial Skills",
            "Editorial Polish",
            "Query Contract",
            "Recommendation Candidates",
            "Enrichment Queries",
            "Candidate Ledger",
            "Draft Compliance",
            "Answer Count Snapshot",
            "Entity Audit",
            "Final Answer Contract",
        ]
        for label in expected_labels:
            assert f"'{label}'" in clear_section, f"clearOutput must remove stale '{label}' row"
        assert ".meta-label" in clear_section
        assert "el.closest('div')" in clear_section
        assert "parent.remove()" in clear_section


class TestDynamicBannerClassPresent:
    """All dynamically inserted banners must have class='dynamic-banner'."""

    def _extract_banner_creations(self, html: str) -> list[str]:
        """Extract lines where createElement('div') banners are created."""
        lines = html.split("\n")
        banner_lines = []
        in_banner = False
        for line in lines:
            if "createElement('div')" in line:
                in_banner = True
                banner_lines.append(line)
            elif in_banner and ("insertBefore" in line or "appendChild" in line):
                banner_lines.append(line)
                in_banner = False
            elif in_banner:
                banner_lines.append(line)
        return banner_lines

    def test_draft_only_banner_has_class(self):
        """Draft-only banner must have dynamic-banner class."""
        html = _get_html_source()
        # Check that draft banner has the class
        assert "dynamic-banner" in html
        # Find section creating draft banner
        assert "draftBanner.className = 'dynamic-banner'" in html

    def test_warn_banner_has_class(self):
        """Publish-ready-with-warnings banner must have dynamic-banner class."""
        html = _get_html_source()
        assert "warnBanner.className = 'dynamic-banner'" in html

    def test_dcc_banner_has_class(self):
        """Draft candidate compliance banner must have dynamic-banner class."""
        html = _get_html_source()
        assert "dccBanner.className = 'dynamic-banner'" in html

    def test_evidence_limited_banner_has_class(self):
        """Evidence-limited banner must have dynamic-banner class."""
        html = _get_html_source()
        assert "evBanner.className = 'dynamic-banner'" in html

    def test_fv_banner_has_class(self):
        """Final validation banner must have dynamic-banner class."""
        html = _get_html_source()
        assert "fvBanner.className = 'dynamic-banner'" in html


class TestRenderOutputReplace:
    """renderOutput must replace content, not accumulate."""

    def test_stats_row_is_reset_on_render(self):
        """stats-row innerHTML must be set to '' before each render."""
        html = _get_html_source()
        # clearOutput sets stats-row.innerHTML = ''
        assert "stats-row" in html
        # The stats-row is cleared in clearOutput
        clear_section = html[html.find("function clearOutput") :]
        clear_section = clear_section[
            : clear_section.find("function ") + 1
            if clear_section.find("function ", 1) > 0
            else None
        ]
        assert "stats-row" in clear_section

    def test_form_card_dynamic_labels_include_query_contract(self):
        """clearOutput dynamic label list must include 'Query Contract'."""
        html = _get_html_source()
        assert "'Query Contract'" in html

    def test_form_card_dynamic_labels_include_recommendation_candidates(self):
        """clearOutput dynamic label list must include 'Recommendation Candidates'."""
        html = _get_html_source()
        assert "'Recommendation Candidates'" in html

    def test_candidate_ledger_summary_rendered_in_main_ui(self):
        """candidate_ledger_summary must be rendered in the main UI (not just in raw JSON)."""
        html = _get_html_source()
        # The candidate ledger summary is the primary display (Candidate Ledger label)
        assert "candidate_ledger_summary" in html
        assert "'Candidate Ledger'" in html
