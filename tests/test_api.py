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
# GET / — browser UI (main entry point)
# ---------------------------------------------------------------------------


def test_root_returns_200():
    response = client.get("/")
    assert response.status_code == 200


def test_root_returns_html():
    response = client.get("/")
    assert "text/html" in response.headers.get("content-type", "")


def test_root_and_app_return_same_content():
    root_resp = client.get("/")
    app_resp = client.get("/app")
    assert root_resp.text == app_resp.text


# ---------------------------------------------------------------------------
# GET /info — service info JSON
# ---------------------------------------------------------------------------


def test_info_returns_200():
    response = client.get("/info")
    assert response.status_code == 200


def test_info_returns_service_info():
    response = client.get("/info")
    body = response.json()
    assert body["service"] == "BlogAgent"
    assert body["status"] == "ok"
    assert "description" in body
    assert "endpoints" in body
    endpoints = body["endpoints"]
    assert "health" in endpoints
    assert "run_post" in endpoints
    assert "run_get" in endpoints
    assert "info" in endpoints
    assert "app" in endpoints


def test_info_remains_public_when_secret_configured(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.get("/info")
    assert response.status_code == 200


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
        "query_contract",
        "recommendation_audit",
    ):
        assert field in body, f"Missing field: {field}"


def test_run_recommendation_response_includes_query_contract(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "7 best parfums for summer"})
    body = response.json()
    contract = body["query_contract"]
    assert contract["task_type"] == "recommendation"
    assert contract["domain"] == "beauty_fragrance"
    assert contract["answer_entity_type"] == "specific_product"
    assert contract["entity_subtype"] == "fragrance_product"
    assert contract["requested_count"] == 7
    assert "recommendation_audit" in body


def test_run_generic_product_recommendation_uses_consumer_products_contract(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    response = client.post("/run", json={"topic": "5 best affordable luxury watches"})
    body = response.json()
    contract = body["query_contract"]
    ledger = body["candidate_ledger_summary"]
    final_contract = body["final_answer_contract"]

    assert response.status_code == 200
    assert contract["task_type"] == "recommendation"
    assert contract["domain"] == "consumer_products"
    assert contract["answer_entity_type"] == "specific_product"
    assert contract["entity_subtype"] == "watch"
    assert contract["requested_count"] == 5
    assert ledger["table_quality"] != "not_required"
    assert final_contract["final_count_mode"] != "not_applicable"
    assert final_contract["publish_status"] == "publish_ready_with_editorial_review"


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
# GET /app — browser UI (alias for /)
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


def test_app_uses_final_answer_contract_for_visible_status():
    response = client.get("/app")
    assert "Final Answer Contract" in response.text
    assert "facData.publish_status" in response.text
    assert "effectiveStatus = facData.publish_status" in response.text


def test_app_shows_consistency_error_for_not_required_recommendation_ledger():
    response = client.get("/app")
    assert "Internal consistency error" in response.text
    assert "candidate ledger as not_required" in response.text


def test_app_contains_generate_button():
    response = client.get("/app")
    assert "Generate" in response.text


# ---------------------------------------------------------------------------
# UI HTML — sessionStorage private-access-screen behaviour
# ---------------------------------------------------------------------------


def test_ui_html_uses_sessionstorage():
    response = client.get("/")
    assert "sessionStorage" in response.text


def test_ui_html_contains_login_button():
    response = client.get("/")
    assert "Login" in response.text


def test_ui_html_contains_logout_button():
    response = client.get("/")
    assert "Logout" in response.text


def test_ui_html_does_not_contain_secret_saved_locally():
    response = client.get("/")
    assert "Secret saved locally" not in response.text


def test_ui_html_does_not_contain_save_secret_button():
    response = client.get("/")
    assert "Save Secret" not in response.text


def test_ui_html_sends_x_blogagent_secret_header():
    response = client.get("/")
    assert "X-BlogAgent-Secret" in response.text


def test_ui_html_uses_sessionstorage_key_for_secret():
    response = client.get("/")
    text = response.text
    assert "blogagent_worker_secret" in text
    # The active storage path must be sessionStorage; ensure key is used with it.
    assert (
        "sessionStorage.getItem(SECRET_KEY)" in text
        or "sessionStorage.getItem('blogagent_worker_secret')" in text
    )


def test_ui_html_shows_access_screen_initially():
    response = client.get("/")
    assert "access-screen" in response.text


def test_ui_html_has_authenticated_app_container():
    response = client.get("/")
    assert "authenticated-app" in response.text


def test_ui_html_calls_auth_status_endpoint():
    response = client.get("/")
    assert "/auth-status" in response.text


def test_ui_html_calls_auth_verify_endpoint():
    response = client.get("/")
    assert "/auth/verify" in response.text


def test_ui_html_topic_textarea_hidden_until_authenticated():
    text = client.get("/").text
    auth_idx = text.find('id="authenticated-app"')
    topic_idx = text.find('id="topic"')
    assert auth_idx != -1 and topic_idx != -1
    assert auth_idx < topic_idx
    assert 'id="authenticated-app" style="display:none"' in text


def test_ui_html_has_private_access_copy():
    response = client.get("/")
    assert "Private demo access" in response.text


def test_ui_html_has_auth_state_element():
    response = client.get("/")
    assert 'id="auth-state"' in response.text


# ---------------------------------------------------------------------------
# GET /auth-status (always public)
# ---------------------------------------------------------------------------


def test_auth_status_returns_false_when_secret_unset(monkeypatch):
    monkeypatch.delenv("BLOGAGENT_WORKER_SECRET", raising=False)
    response = client.get("/auth-status")
    assert response.status_code == 200
    assert response.json() == {"worker_secret_required": False}


def test_auth_status_returns_true_when_secret_set(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.get("/auth-status")
    assert response.status_code == 200
    assert response.json() == {"worker_secret_required": True}


def test_auth_status_remains_public_when_secret_configured(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.get("/auth-status")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /auth/verify
# ---------------------------------------------------------------------------


def test_auth_verify_returns_200_when_no_secret_configured(monkeypatch):
    monkeypatch.delenv("BLOGAGENT_WORKER_SECRET", raising=False)
    response = client.post("/auth/verify", json={"worker_secret": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["worker_secret_required"] is False


def test_auth_verify_returns_200_when_no_secret_configured_ignores_input(monkeypatch):
    monkeypatch.delenv("BLOGAGENT_WORKER_SECRET", raising=False)
    response = client.post("/auth/verify", json={"worker_secret": "anything"})
    assert response.status_code == 200


def test_auth_verify_returns_401_when_secret_configured_and_missing(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.post("/auth/verify", json={})
    assert response.status_code == 401
    assert "worker secret" in response.json()["detail"].lower()


def test_auth_verify_returns_401_when_secret_configured_and_wrong(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.post("/auth/verify", json={"worker_secret": "wrong"})
    assert response.status_code == 401
    assert "worker secret" in response.json()["detail"].lower()


def test_auth_verify_returns_200_when_secret_configured_and_correct(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.post("/auth/verify", json={"worker_secret": "supersecret"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["worker_secret_required"] is True


def test_auth_verify_does_not_leak_expected_secret(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret-leak-canary")
    response = client.post("/auth/verify", json={"worker_secret": "wrong"})
    assert "supersecret-leak-canary" not in response.text


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
        _ROOT
        / ".claude"
        / "skills"
        / "blog-post-seo-writing"
        / "references"
        / "blog-output-template.md"
    )
    assert template.exists()


def test_blog_evaluator_rubric_exists():
    assert (
        _ROOT / ".claude" / "skills" / "blog-output-evaluator" / "references" / "rubric.md"
    ).exists()


# ---------------------------------------------------------------------------
# Browser UI — generate button and JS event wiring
# ---------------------------------------------------------------------------


def test_ui_html_has_generate_button_id():
    response = client.get("/")
    assert 'id="generateButton"' in response.text


def test_ui_html_has_status_div():
    response = client.get("/")
    assert 'id="status"' in response.text


def test_ui_html_has_debug_output():
    response = client.get("/")
    assert 'id="debugOutput"' in response.text


def test_ui_html_uses_addeventlistener_for_generate():
    response = client.get("/")
    assert "addEventListener" in response.text
    assert "generate" in response.text


def test_ui_html_uses_domcontentloaded():
    response = client.get("/")
    assert "DOMContentLoaded" in response.text


def test_ui_html_calls_fetch_run():
    response = client.get("/")
    assert "fetch('/run'" in response.text or 'fetch("/run"' in response.text


def test_ui_html_sends_x_blogagent_secret_in_fetch():
    response = client.get("/")
    assert "X-BlogAgent-Secret" in response.text


def test_ui_html_has_api_health_element():
    response = client.get("/")
    assert 'id="api-health"' in response.text


def test_generate_button_has_type_button():
    response = client.get("/")
    assert 'type="button"' in response.text


# ---------------------------------------------------------------------------
# UI state — access-screen / authenticated-app structure
# ---------------------------------------------------------------------------


def test_html_contains_access_screen_id():
    response = client.get("/")
    assert 'id="access-screen"' in response.text


def test_html_contains_authenticated_app_id():
    response = client.get("/")
    assert 'id="authenticated-app"' in response.text


def test_authenticated_app_starts_hidden():
    response = client.get("/")
    assert 'id="authenticated-app" style="display:none"' in response.text


def test_html_contains_show_access_screen():
    response = client.get("/")
    assert "showAccessScreen" in response.text


def test_html_contains_show_authenticated_app():
    response = client.get("/")
    assert "showAuthenticatedApp" in response.text


def test_show_authenticated_app_sets_display_block():
    response = client.get("/")
    assert "getElementById('authenticated-app').style.display = 'block'" in response.text


def test_show_authenticated_app_hides_access_screen():
    response = client.get("/")
    assert "getElementById('access-screen').style.display = 'none'" in response.text


def test_show_access_screen_hides_authenticated_app():
    response = client.get("/")
    assert "getElementById('authenticated-app').style.display = 'none'" in response.text


def test_successful_auth_path_calls_show_authenticated_app():
    response = client.get("/")
    html = response.text
    idx = html.find("function login()")
    assert idx != -1
    login_body = html[idx : idx + 800]
    assert "resp.ok" in login_body
    assert "showAuthenticatedApp" in login_body


def test_failed_auth_path_calls_show_access_screen():
    response = client.get("/")
    html = response.text
    idx = html.find("function login()")
    assert idx != -1
    login_body = html[idx : idx + 800]
    assert "showAccessScreen" in login_body


def test_topic_textarea_inside_authenticated_app():
    response = client.get("/")
    html = response.text
    idx_app = html.find('id="authenticated-app"')
    idx_topic = html.find('id="topic"')
    assert idx_app != -1
    assert idx_topic != -1
    assert idx_topic > idx_app


def test_generate_button_inside_authenticated_app():
    response = client.get("/")
    html = response.text
    idx_app = html.find('id="authenticated-app"')
    idx_btn = html.find('id="generateButton"')
    assert idx_app != -1
    assert idx_btn != -1
    assert idx_btn > idx_app


def test_auth_verify_accepts_secret_via_header(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.post(
        "/auth/verify",
        json={},
        headers={"X-BlogAgent-Secret": "supersecret"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /run still requires X-BlogAgent-Secret when configured
# ---------------------------------------------------------------------------


def test_run_requires_secret_header_when_configured(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_WORKER_SECRET", "supersecret")
    response = client.post("/run", json={"topic": "Solar energy"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Vercel dependency — google-genai
# ---------------------------------------------------------------------------


def test_requirements_vercel_contains_google_genai():
    req = (_ROOT / "requirements-vercel.txt").read_text()
    assert "google-genai" in req


def test_requirements_vercel_google_genai_has_version():
    req = (_ROOT / "requirements-vercel.txt").read_text()
    assert "google-genai>=1.0" in req


# ---------------------------------------------------------------------------
# UI HTML — output-section element
# ---------------------------------------------------------------------------


def test_html_contains_output_section_id():
    response = client.get("/")
    assert 'id="output-section"' in response.text


def test_html_output_section_has_generated_blog_draft_heading():
    response = client.get("/")
    assert "Generated Blog Draft" in response.text


def test_html_contains_raw_json_pre():
    response = client.get("/")
    assert 'id="raw-json"' in response.text


def test_html_contains_render_output_function():
    response = client.get("/")
    assert "renderOutput" in response.text


# ---------------------------------------------------------------------------
# UI HTML — generate() calls renderOutput
# ---------------------------------------------------------------------------


def test_generate_function_calls_render_output():
    response = client.get("/")
    html = response.text
    idx = html.find("async function generate()")
    assert idx != -1, "generate() function not found in HTML"
    gen_body = html[idx : idx + 3000]
    assert "renderOutput(data)" in gen_body


def test_generate_wraps_render_output_in_try_catch():
    response = client.get("/")
    html = response.text
    idx = html.find("async function generate()")
    assert idx != -1
    gen_body = html[idx : idx + 3000]
    assert "renderErr" in gen_body or "Render error" in gen_body


def test_generate_shows_render_error_message():
    response = client.get("/")
    assert "Render error" in response.text


# ---------------------------------------------------------------------------
# UI HTML — renderOutput behaviour
# ---------------------------------------------------------------------------


def test_render_output_sets_output_section_display_block():
    response = client.get("/")
    html = response.text
    idx = html.find("function renderOutput(")
    assert idx != -1, "renderOutput() function not found in HTML"
    render_body = html[idx : idx + 4000]
    assert "output-section" in render_body
    assert "display = 'block'" in render_body or 'display = "block"' in render_body


def test_render_output_renders_article_markdown_field():
    response = client.get("/")
    html = response.text
    idx = html.find("function renderOutput(")
    assert idx != -1
    render_body = html[idx : idx + 4000]
    assert "article_markdown" in render_body


def test_render_output_has_camel_case_article_markdown_fallback():
    response = client.get("/")
    html = response.text
    idx = html.find("function renderOutput(")
    assert idx != -1
    render_body = html[idx : idx + 4000]
    assert "articleMarkdown" in render_body


def test_render_output_has_content_fallback():
    response = client.get("/")
    html = response.text
    idx = html.find("function renderOutput(")
    assert idx != -1
    render_body = html[idx : idx + 4000]
    assert "data.content" in render_body or "|| ''" in render_body


def test_render_output_has_no_article_markdown_message():
    response = client.get("/")
    assert "No article markdown returned by API." in response.text


def test_render_output_calls_scroll_into_view():
    response = client.get("/")
    html = response.text
    idx = html.find("function renderOutput(")
    assert idx != -1
    render_body = html[idx : idx + 4000]
    assert "scrollIntoView" in render_body


def test_render_output_scroll_uses_smooth_behavior():
    response = client.get("/")
    html = response.text
    idx = html.find("function renderOutput(")
    assert idx != -1
    render_body = html[idx : idx + 4000]
    assert "smooth" in render_body


def test_raw_json_uses_json_stringify_with_indent():
    response = client.get("/")
    html = response.text
    assert "JSON.stringify(data, null, 2)" in html or "JSON.stringify(d, null, 2)" in html


# ---------------------------------------------------------------------------
# UI HTML — copy / download buttons
# ---------------------------------------------------------------------------


def test_html_has_copy_markdown_button():
    response = client.get("/")
    assert "Copy article markdown" in response.text


def test_html_has_download_md_button():
    response = client.get("/")
    assert "Download .md" in response.text


def test_html_has_download_json_button():
    response = client.get("/")
    assert "Download full JSON" in response.text


# ---------------------------------------------------------------------------
# POST /run — each required response field (explicit)
# ---------------------------------------------------------------------------


def test_run_returns_title_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "title" in body
    assert isinstance(body["title"], str)


def test_run_returns_meta_description_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "meta_description" in body
    assert isinstance(body["meta_description"], str)


def test_run_returns_article_markdown_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "article_markdown" in body
    assert isinstance(body["article_markdown"], str)


def test_run_returns_seo_keywords_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "seo_keywords" in body
    assert isinstance(body["seo_keywords"], list)


def test_run_returns_source_count_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "source_count" in body
    assert isinstance(body["source_count"], int)


def test_run_returns_claim_status_counts_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "claim_status_counts" in body
    counts = body["claim_status_counts"]
    assert "supported" in counts
    assert "partially_supported" in counts
    assert "unsupported" in counts


def test_run_returns_revision_count_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "revision_count" in body
    assert isinstance(body["revision_count"], int)


def test_run_returns_warnings_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "warnings" in body
    assert isinstance(body["warnings"], list)


def test_run_returns_provider_events_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "provider_events" in body
    assert isinstance(body["provider_events"], list)


def test_run_returns_execution_mode_field(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "execution_mode" in body
    assert isinstance(body["execution_mode"], str)


# ---------------------------------------------------------------------------
# RunResponse — new final-validation fields
# ---------------------------------------------------------------------------


def test_run_returns_final_validation_status(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "final_validation_status" in body
    assert isinstance(body["final_validation_status"], str)


def test_run_returns_final_validation_defects(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FATCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "final_validation_defects" in body
    assert isinstance(body["final_validation_defects"], list)


def test_run_returns_evidence_limited_count_accepted(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    body = client.post("/run", json={"topic": "Solar energy"}).json()
    assert "evidence_limited_count_accepted" in body
    assert isinstance(body["evidence_limited_count_accepted"], bool)


# ---------------------------------------------------------------------------
# UI HTML — staged workflow animation
# ---------------------------------------------------------------------------


def test_html_contains_workflow_panel_id():
    response = client.get("/")
    assert 'id="workflow-panel"' in response.text


def test_html_contains_agent_workflow_running():
    response = client.get("/")
    assert "Agent workflow running" in response.text


def test_html_contains_all_workflow_stage_labels():
    response = client.get("/")
    html = response.text
    stages = [
        "Checking access",
        "Detecting intent",
        "Selecting editorial skills",
        "Planning research",
        "Searching sources",
        "Scoring source quality",
        "Building evidence table",
        "Drafting article",
        "Evaluating quality",
        "Revising if needed",
        "Final validation",
        "Copy-readiness check",
        "Packaging draft",
    ]
    for stage in stages:
        assert stage in html, f"Stage label missing from HTML: {stage!r}"


def test_html_contains_start_workflow_animation():
    response = client.get("/")
    assert "startWorkflowAnimation" in response.text


def test_html_contains_complete_workflow_animation():
    response = client.get("/")
    assert "completeWorkflowAnimation" in response.text


def test_html_contains_fail_workflow_animation():
    response = client.get("/")
    assert "failWorkflowAnimation" in response.text


def test_html_workflow_steps_css_classes():
    response = client.get("/")
    html = response.text
    for cls in ("workflow-step", "step-icon", "step-pulse"):
        assert cls in html, f"CSS class missing from HTML: {cls!r}"


def test_html_generate_calls_start_workflow_animation():
    response = client.get("/")
    html = response.text
    idx = html.find("async function generate()")
    assert idx != -1, "generate() not found"
    gen_body = html[idx : idx + 2000]
    assert "startWorkflowAnimation" in gen_body


def test_html_generate_calls_complete_workflow_animation_on_success():
    response = client.get("/")
    html = response.text
    idx = html.find("async function generate()")
    assert idx != -1
    gen_body = html[idx : idx + 2000]
    assert "completeWorkflowAnimation" in gen_body


def test_html_generate_calls_fail_workflow_animation_on_error():
    response = client.get("/")
    html = response.text
    idx = html.find("async function generate()")
    assert idx != -1
    gen_body = html[idx : idx + 2000]
    assert "failWorkflowAnimation" in gen_body


def test_html_response_data_updates_workflow_panel():
    """completeWorkflowAnimation must accept data and annotate stages from it."""
    response = client.get("/")
    html = response.text
    idx = html.find("function completeWorkflowAnimation(")
    assert idx != -1, "completeWorkflowAnimation not found"
    fn_body = html[idx : idx + 3000]
    assert "final_validation_status" in fn_body or "fvStatus" in fn_body


def test_html_workflow_panel_hidden_initially():
    """workflow-panel must start hidden and be revealed by startWorkflowAnimation."""
    response = client.get("/")
    html = response.text
    assert "workflow-panel" in html
    assert "display: none" in html or "display:none" in html


def test_html_clear_output_hides_workflow_panel():
    """clearOutput() must call _hideWorkflowPanel()."""
    response = client.get("/")
    html = response.text
    idx = html.find("function clearOutput()")
    assert idx != -1
    clear_body = html[idx : idx + 900]
    assert "_hideWorkflowPanel" in clear_body or "workflow-panel" in clear_body
