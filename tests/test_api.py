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
# GET /
# ---------------------------------------------------------------------------


def test_root_returns_200():
    response = client.get("/")
    assert response.status_code == 200


def test_root_returns_service_info():
    response = client.get("/")
    body = response.json()
    assert body["service"] == "BlogAgent"
    assert body["status"] == "ok"
    assert "description" in body
    assert "endpoints" in body
    endpoints = body["endpoints"]
    assert "health" in endpoints
    assert "run_post" in endpoints
    assert "run_get" in endpoints


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
# GET /run — browser-friendly route
# ---------------------------------------------------------------------------


def test_get_run_no_topic_returns_200():
    response = client.get("/run")
    assert response.status_code == 200


def test_get_run_no_topic_returns_usage_hint():
    response = client.get("/run")
    body = response.json()
    assert "detail" in body
    assert "example_get" in body
    assert "example_post_body" in body


def test_get_run_empty_topic_returns_usage_hint():
    response = client.get("/run?topic=")
    body = response.json()
    assert "detail" in body


def test_get_run_with_topic_returns_200(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.get("/run?topic=Why elephants are the heaviest land animals")
    assert response.status_code == 200


def test_get_run_with_topic_has_compact_fields(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.get("/run?topic=Solar energy")
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


def test_get_run_publishing_topic_returns_blocked(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.get("/run?topic=Post this article to WordPress now")
    assert response.status_code == 200
    body = response.json()
    assert body["blocked"] is True
    assert body["block_reason"] != ""


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


# ---------------------------------------------------------------------------
# GET /app — browser UI
# ---------------------------------------------------------------------------


def test_app_returns_200():
    response = client.get("/app")
    assert response.status_code == 200


def test_app_returns_html():
    response = client.get("/app")
    assert "text/html" in response.headers.get("content-type", "")


def test_app_contains_worker_secret_input():
    response = client.get("/app")
    assert "secret" in response.text.lower()
    assert 'type="password"' in response.text


def test_app_contains_topic_input():
    response = client.get("/app")
    assert "topic" in response.text.lower()
    assert "<textarea" in response.text


def test_app_contains_generate_button():
    response = client.get("/app")
    assert "Generate" in response.text


# ---------------------------------------------------------------------------
# Worker secret — unprotected (BLOGAGENT_WORKER_SECRET unset)
# ---------------------------------------------------------------------------


def test_run_works_without_secret_when_env_unset(monkeypatch):
    monkeypatch.delenv("BLOGAGENT_WORKER_SECRET", raising=False)
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Solar energy"})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Worker secret — protected (BLOGAGENT_WORKER_SECRET set)
# ---------------------------------------------------------------------------


def test_run_returns_401_when_secret_configured_and_missing(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.post("/run", json={"topic": "Solar energy"})
    assert response.status_code == 401
    assert "worker secret" in response.json()["detail"].lower()


def test_run_returns_401_when_secret_configured_and_wrong(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.post(
        "/run",
        json={"topic": "Solar energy"},
        headers={"X-BlogAgent-Secret": "wrong"},
    )
    assert response.status_code == 401


def test_run_succeeds_when_secret_correct_via_header(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post(
        "/run",
        json={"topic": "Solar energy"},
        headers={"X-BlogAgent-Secret": "supersecret"},
    )
    assert response.status_code == 200


def test_get_run_succeeds_with_correct_worker_secret_query_param(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.get("/run?topic=Solar energy&worker_secret=supersecret")
    assert response.status_code == 200


def test_get_run_returns_401_with_wrong_worker_secret(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.get("/run?topic=Solar energy&worker_secret=wrong")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Public routes stay public when secret is configured
# ---------------------------------------------------------------------------


def test_health_remains_public_when_secret_configured(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.get("/health")
    assert response.status_code == 200


def test_root_remains_public_when_secret_configured(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.get("/")
    assert response.status_code == 200


def test_app_remains_public_when_secret_configured(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.get("/app")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# RunResponse includes slug and seo_keywords
# ---------------------------------------------------------------------------


def test_run_response_includes_slug(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Solar energy"})
    body = response.json()
    assert "slug" in body


def test_run_response_includes_seo_keywords(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "Solar energy"})
    body = response.json()
    assert "seo_keywords" in body
    assert isinstance(body["seo_keywords"], list)


# ---------------------------------------------------------------------------
# Skill file existence tests
# ---------------------------------------------------------------------------


def test_skill_creator_exists():
    assert (_ROOT / ".claude" / "skills" / "skill-creator" / "SKILL.md").exists()


def test_blog_seo_skill_exists():
    assert (_ROOT / ".claude" / "skills" / "blog-post-seo-writing" / "SKILL.md").exists()


def test_blog_evaluator_skill_exists():
    assert (_ROOT / ".claude" / "skills" / "blog-output-evaluator" / "SKILL.md").exists()


def test_blog_output_template_exists():
    template = (
        _ROOT / ".claude" / "skills" / "blog-post-seo-writing"
        / "references" / "blog-output-template.md"
    )
    assert template.exists()


def test_blog_evaluator_rubric_exists():
    assert (
        _ROOT / ".claude" / "skills" / "blog-output-evaluator" / "references" / "rubric.md"
    ).exists()
