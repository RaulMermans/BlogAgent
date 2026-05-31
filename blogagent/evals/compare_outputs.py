"""Deterministic comparison of BlogAgent run output files.

Loads two or more saved ArticlePackage (or enriched run) JSON files and
reports per-file metrics plus a 0–100 quality score based on deterministic
heuristic checks.  No LLM judge is used.

Accepted JSON format
--------------------
Minimum: any ArticlePackage dump produced by ``python -m blogagent.cli run --output``.
Optional extra top-level keys (written when --output is used with the CLI):
  execution_mode, revision_count, blocked, block_reason, provider_events, warnings

Quality rubric (max 100 points)
--------------------------------
  valid title              +10
  valid meta description   +10
  article has headings     +10
  article over 600 words   +15
  at least 3 sources       +15
  no unsupported high-imp  +20
  not pure mock sources    +10
  clear revision summary   +10
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rubric
# ---------------------------------------------------------------------------

RUBRIC: dict[str, int] = {
    "valid_title": 10,
    "valid_meta_description": 10,
    "has_headings": 10,
    "over_600_words": 15,
    "at_least_3_sources": 15,
    "no_unsupported_high_importance": 20,
    "not_pure_mock": 10,
    "clear_revision_summary": 10,
}

MAX_SCORE = sum(RUBRIC.values())  # 100


# ---------------------------------------------------------------------------
# Metrics dataclass
# ---------------------------------------------------------------------------


@dataclass
class RunMetrics:
    filename: str
    # Article fields
    has_title: bool = False
    title: str = ""
    has_meta_description: bool = False
    meta_description_len: int = 0
    word_count: int = 0
    heading_count: int = 0
    # Sources
    source_count: int = 0
    mock_source_count: int = 0
    # Claims
    supported_count: int = 0
    partially_supported_count: int = 0
    unsupported_count: int = 0
    total_claims: int = 0
    # State-level (optional — present when --output writes enriched JSON)
    revision_count: int = 0
    blocked: bool = False
    execution_mode: str = "unknown"
    provider_events: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Quality score
    quality_score: int = 0
    quality_notes: list[str] = field(default_factory=list)
    # Load error (non-empty means the file could not be parsed)
    load_error: str = ""


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------


def score_output(data: dict[str, Any]) -> tuple[int, list[str]]:
    """Compute a 0–100 quality score from a raw JSON dict.

    Returns (score, deduction_notes).  Always deterministic — same input
    produces same output.
    """
    score = 0
    notes: list[str] = []

    # valid_title: +10 if title is non-empty
    title = (data.get("title") or "").strip()
    if title:
        score += RUBRIC["valid_title"]
    else:
        notes.append("missing title")

    # valid_meta_description: +10 if meta_description is non-empty
    meta = (data.get("meta_description") or "").strip()
    if meta:
        score += RUBRIC["valid_meta_description"]
    else:
        notes.append("missing meta description")

    # has_headings: +10 if article_markdown has ≥1 ATX heading
    article = data.get("article_markdown") or ""
    if re.search(r"^#{1,6}\s", article, re.MULTILINE):
        score += RUBRIC["has_headings"]
    else:
        notes.append("no markdown headings")

    # over_600_words: +15
    word_count = len(article.split()) if article else 0
    if word_count >= 600:
        score += RUBRIC["over_600_words"]
    else:
        notes.append(f"under 600 words ({word_count})")

    # at_least_3_sources: +15
    sources = data.get("source_list") or []
    if len(sources) >= 3:
        score += RUBRIC["at_least_3_sources"]
    else:
        notes.append(f"fewer than 3 sources ({len(sources)})")

    # no_unsupported_high_importance: +20
    statuses = data.get("claim_support_statuses") or []
    has_blocking = any(
        m.get("status") == "unsupported" and (m.get("claim") or {}).get("importance") == "high"
        for m in statuses
    )
    if not has_blocking:
        score += RUBRIC["no_unsupported_high_importance"]
    else:
        notes.append("has unsupported high-importance claim(s)")

    # not_pure_mock: +10 if not all sources carry is_mock=True
    all_mock = bool(sources) and all(s.get("is_mock", True) for s in sources)
    if not all_mock:
        score += RUBRIC["not_pure_mock"]
    else:
        notes.append("all sources are mock placeholders")

    # clear_revision_summary: +10 if revision_summary is non-empty
    revision_summary = (data.get("revision_summary") or "").strip()
    if revision_summary:
        score += RUBRIC["clear_revision_summary"]
    else:
        notes.append("revision summary is empty")

    return score, notes


# ---------------------------------------------------------------------------
# Metrics extraction
# ---------------------------------------------------------------------------


def _extract_metrics(path: Path, data: dict[str, Any]) -> RunMetrics:
    m = RunMetrics(filename=path.name)

    title = (data.get("title") or "").strip()
    m.has_title = bool(title)
    m.title = title

    meta = (data.get("meta_description") or "").strip()
    m.has_meta_description = bool(meta)
    m.meta_description_len = len(meta)

    article = data.get("article_markdown") or ""
    m.word_count = len(article.split()) if article else 0
    m.heading_count = len(re.findall(r"^#{1,6}\s", article, re.MULTILINE))

    sources = data.get("source_list") or []
    m.source_count = len(sources)
    m.mock_source_count = sum(1 for s in sources if s.get("is_mock", False))

    fcr = data.get("fact_check_report") or {}
    m.supported_count = fcr.get("supported_count", 0)
    m.partially_supported_count = fcr.get("partially_supported_count", 0)
    m.unsupported_count = fcr.get("unsupported_count", 0)
    m.total_claims = fcr.get("total_claims", 0)

    # Optional state-level fields — gracefully absent in pure ArticlePackage dumps
    m.revision_count = data.get("revision_count", 0)
    m.blocked = data.get("blocked", False)
    m.execution_mode = data.get("execution_mode", "unknown")
    m.provider_events = list(data.get("provider_events") or [])
    m.warnings = list(data.get("warnings") or [])

    m.quality_score, m.quality_notes = score_output(data)
    return m


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_run_output(path: Path) -> tuple[RunMetrics, dict[str, Any] | None]:
    """Load a run output JSON file.  Returns (metrics, raw_data).

    If the file is missing or contains invalid JSON, metrics.load_error is set
    and raw_data is None.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        m = RunMetrics(filename=path.name, load_error=f"file not found: {path}")
        return m, None
    except OSError as exc:
        m = RunMetrics(filename=path.name, load_error=f"OS error: {exc}")
        return m, None

    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        m = RunMetrics(filename=path.name, load_error=f"invalid JSON: {exc}")
        return m, None

    if not isinstance(data, dict):
        m = RunMetrics(filename=path.name, load_error="expected a JSON object at root")
        return m, None

    return _extract_metrics(path, data), data


def compare_outputs(paths: list[Path]) -> list[RunMetrics]:
    """Load and compare multiple run output files.  Returns a RunMetrics per path."""
    return [load_run_output(p)[0] for p in paths]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_COL_W = 30  # column width per file (extra space keeps headers readable)
_COL_GAP = 2  # minimum gap between adjacent column values


def _pad(value: str, width: int = _COL_W) -> str:
    return value[: width - _COL_GAP].ljust(width)


def _row(label: str, *values: str, label_w: int = 34) -> str:
    return label.ljust(label_w) + "".join(_pad(v) for v in values)


def format_comparison_table(metrics_list: list[RunMetrics]) -> str:
    """Return a human-readable side-by-side comparison table string."""
    lines: list[str] = []

    # Report load errors first
    error_metrics = [m for m in metrics_list if m.load_error]
    ok_metrics = [m for m in metrics_list if not m.load_error]

    for m in error_metrics:
        lines.append(f"ERROR  {m.filename}: {m.load_error}")

    if not ok_metrics:
        return "\n".join(lines) or "No valid outputs to compare."

    sep_len = 34 + _COL_W * len(ok_metrics) + 2
    sep = "-" * sep_len

    lines.append("")
    lines.append("BlogAgent Output Comparison")
    lines.append(sep)

    # Column headers
    lines.append(_row("", *[m.filename for m in ok_metrics]))
    lines.append(sep)

    # --- METADATA ---
    lines.append("METADATA")
    lines.append(_row("  execution_mode", *[m.execution_mode for m in ok_metrics]))
    lines.append(_row("  blocked", *[str(m.blocked) for m in ok_metrics]))
    lines.append(_row("  revision_count", *[str(m.revision_count) for m in ok_metrics]))
    lines.append(_row("  provider_events", *[str(len(m.provider_events)) for m in ok_metrics]))
    lines.append(_row("  warnings", *[str(len(m.warnings)) for m in ok_metrics]))

    # --- ARTICLE ---
    lines.append("")
    lines.append("ARTICLE")
    lines.append(_row("  has_title", *[_yn(m.has_title) for m in ok_metrics]))
    lines.append(_row("  has_meta_description", *[_yn(m.has_meta_description) for m in ok_metrics]))
    lines.append(_row("  word_count", *[str(m.word_count) for m in ok_metrics]))
    lines.append(_row("  heading_count", *[str(m.heading_count) for m in ok_metrics]))

    # --- SOURCES ---
    lines.append("")
    lines.append("SOURCES")
    lines.append(_row("  total", *[str(m.source_count) for m in ok_metrics]))
    lines.append(_row("  mock", *[str(m.mock_source_count) for m in ok_metrics]))
    lines.append(
        _row(
            "  real",
            *[str(m.source_count - m.mock_source_count) for m in ok_metrics],
        )
    )

    # --- CLAIMS ---
    lines.append("")
    lines.append("CLAIMS")
    lines.append(_row("  total", *[str(m.total_claims) for m in ok_metrics]))
    lines.append(_row("  supported", *[str(m.supported_count) for m in ok_metrics]))
    lines.append(
        _row("  partially_supported", *[str(m.partially_supported_count) for m in ok_metrics])
    )
    lines.append(_row("  unsupported", *[str(m.unsupported_count) for m in ok_metrics]))

    # --- QUALITY SCORE ---
    lines.append("")
    lines.append("QUALITY SCORE  (max 100)")
    lines.append(_row("  score", *[str(m.quality_score) for m in ok_metrics]))

    # Collect all unique deduction notes
    all_notes: list[str] = []
    seen: set[str] = set()
    for m in ok_metrics:
        for note in m.quality_notes:
            if note not in seen:
                seen.add(note)
                all_notes.append(note)

    if all_notes:
        lines.append("  deductions:")
        for note in sorted(all_notes):
            applicability = "    ".join(
                f"{'[x]' if note in m.quality_notes else '[ ]'} {m.filename[:22]}"
                for m in ok_metrics
            )
            lines.append(f"    {note:<38}{applicability}")

    # Warn when live/hybrid runs have supported claims but citation judge was not active.
    live_runs_with_supported = [
        m for m in ok_metrics if m.execution_mode in ("live", "hybrid") and m.supported_count > 0
    ]
    if live_runs_with_supported:
        lines.append(
            "NOTE: Live/hybrid runs with 'supported' claims used heuristic citation matching."
        )
        lines.append("      Set BLOGAGENT_USE_LLM_CITATION_JUDGE=true for semantic verification.")

    lines.append(sep)
    lines.append("")

    return "\n".join(lines)


def _yn(val: bool) -> str:
    return "yes" if val else "no"
