from __future__ import annotations

import pytest

from blogagent.tools.tone_profile import resolve_tone_profile


def test_explicit_tone_profile_id_maps_to_profile():
    profile = resolve_tone_profile("luxury_premium", "beauty_fragrance")
    assert profile.id == "luxury_premium"
    assert profile.label == "Luxury / Premium"


def test_invalid_tone_profile_falls_back_to_domain_default():
    profile = resolve_tone_profile("invalid", "finance")
    assert profile.id == "expert_analyst"


def test_domain_defaults_are_bounded():
    assert resolve_tone_profile(None, "consumer_products").id == "practical_buying_guide"
    assert resolve_tone_profile(None, "general").id == "seo_neutral"


def test_api_accepts_tone_and_returns_profile(monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    assert fastapi is not None
    from fastapi.testclient import TestClient

    from api.index import app

    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    client = TestClient(app)
    response = client.post(
        "/run",
        json={"topic": "Solar energy", "tone_profile_id": "personal_blog"},
    )
    assert response.status_code == 200
    assert response.json()["tone_profile"]["id"] == "personal_blog"


def test_html_contains_tone_selector():
    from api.index import _build_app_html

    html = _build_app_html()
    assert 'id="tone-profile"' in html
    assert "Editorial Magazine" in html
    assert "tone_profile_id" in html
