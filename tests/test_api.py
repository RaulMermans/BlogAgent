"""Tests for the Vercel/FastAPI API entry point (api/index.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

# Skip entire module if fastapi is not installed (avoids import error in envs without it)
fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi.testclient import TestClient  # noqa: E402 — after importorskip

from api.index import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=True)

# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_has_correct_fields():
    response = client.get("/health")
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "BlogAgent"
    assert body["mode"] == "mock-safe"


# ---------------------------------------------------------------------------
# POST /run — validation
# ---------------------------------------------------------------------------


def test_run_missing_topic_returns_400():
    response = client.post("/run", json={})
    assert response.status_code == 422  # FastAPI validation error for missing field


def test_run_empty_topic_returns_400():
    response = client.post("/run", json={"topic": "   "})
    assert response.status_code == 400


def test_run_empty_string_topic_returns_400():
    response = client.post("/run", json={"topic": ""})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /run — normal topic (mock mode)
# ---------------------------------------------------------------------------


def test_run_normal_topic_returns_200(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Why elephants are the heaviest land animals"})
    assert response.status_code == 200


def test_run_normal_topic_response_has_compact_fields(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Solar energy"})
    body = response.json()
    for field in (
        "blocked",
        "block_reason",
        "execution_mode",
        "title",
        "meta_description",
        "article_markdown",
        "source_count",
        "claim_status_counts",
        "revision_count",
        "warnings",
        "provider_events",
    ):
        assert field in body, f"Missing field: {field}"


def test_run_response_does_not_include_raw_source_text(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Solar energy"})
    body = response.json()
    body_str = str(body)
    assert "extracted_text" not in body_str
    assert "selected_sources" not in body_str


def test_run_claim_status_counts_has_correct_keys(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Climate change"})
    counts = response.json()["claim_status_counts"]
    assert "supported" in counts
    assert "partially_supported" in counts
    assert "unsupported" in counts


# ---------------------------------------------------------------------------
# POST /run — publishing topic must be blocked
# ---------------------------------------------------------------------------


def test_run_publishing_topic_returns_blocked(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Post this article to WordPress now"})
    assert response.status_code == 200
    body = response.json()
    assert body["blocked"] is True
    assert body["block_reason"] != ""


def test_run_blocked_response_has_empty_article(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Publish this to my blog"})
    body = response.json()
    assert body["article_markdown"] == ""
    assert body["source_count"] == 0


# ---------------------------------------------------------------------------
# Config file existence tests
# ---------------------------------------------------------------------------


_ROOT = Path(__file__).parent.parent


def test_ci_yml_exists():
    ci = _ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.exists(), "CI workflow file must exist"


def test_ci_yml_includes_ruff():
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "ruff" in ci


def test_ci_yml_includes_pytest():
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pytest" in ci


def test_ci_yml_includes_eval_runner():
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "evals.runner" in ci or "evals/runner" in ci


def test_ci_yml_sets_mock_providers():
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "BLOGAGENT_SEARCH_PROVIDER" in ci
    assert "BLOGAGENT_LLM_PROVIDER" in ci


def test_vercel_json_exists():
    assert (_ROOT / "vercel.json").exists(), "vercel.json must exist"


def test_api_entrypoint_exists():
    assert (_ROOT / "api" / "index.py").exists(), "api/index.py must exist"
