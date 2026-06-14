from __future__ import annotations

import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_fastapi_visible_ui_uses_copy_ready_language():
    source = (_ROOT / "api" / "index.py").read_text()

    required = (
        "Generated Blog Draft",
        "Generate Blog Draft",
        "Copy-readiness check",
        "Packaging draft — copy-ready",
        "Packaging draft — copy-ready after light review",
        "Packaging draft — needs revision before use",
        "Copy-ready after light review",
        "Needs revision before use",
    )
    forbidden = (
        "Packaging blog post — publish ready",
        "Packaging blog post — draft only",
        "✓ publish ready",
        "✗ draft only",
        "Final Answer Contract: Publish Ready",
        "Draft Only — Not Publish Ready",
        "Review recommended before publishing",
    )

    assert all(phrase in source for phrase in required)
    assert all(phrase not in source for phrase in forbidden)


def test_readme_uses_copy_readiness_positioning():
    readme = (_ROOT / "README.md").read_text()

    required = (
        "Copy-Readiness Pipeline",
        "copy-readiness layer",
        "Copy-ready status mapping",
        "human editorial review",
    )
    forbidden = (
        "### Publish-Ready Pipeline",
        "fully autonomous",
        "hands-free publishing",
    )

    assert all(phrase in readme for phrase in required)
    assert all(phrase not in readme for phrase in forbidden)


def test_public_docs_do_not_expose_local_claude_paths():
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    text_suffixes = {
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
    forbidden = (
        ".claude/projects/" + "-Users-",
        "/Users/" + "raulm/Desktop",
        "Desktop/GitHub/" + "BlogAgent",
    )

    violations: list[str] = []
    for relative_path in tracked:
        path = _ROOT / relative_path
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        text = path.read_text(errors="ignore")
        for phrase in forbidden:
            if phrase in text:
                violations.append(f"{relative_path}: {phrase}")

    assert not violations, "\n".join(violations)
