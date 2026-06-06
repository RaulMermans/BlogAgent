from __future__ import annotations

import logging

import pytest

from blogagent.observability.agentpulse_client import (
    AgentPulseClient,
    redact_metadata,
)
from blogagent.observability.agentpulse_smoke_test import run_smoke_test


class _OKResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def _enable_agentpulse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTPULSE_ENABLED", "true")
    monkeypatch.setenv("AGENTPULSE_URL", "https://agentpulse.test")
    monkeypatch.setenv("AGENTPULSE_INGEST_KEY", "test-ingest-key")
    monkeypatch.setenv("AGENTPULSE_PROJECT_ID", "blog-agent")
    monkeypatch.setenv("AGENTPULSE_PROJECT_NAME", "Blog Agent")
    monkeypatch.setenv("AGENTPULSE_WORKFLOW_ID", "blog-agent-v1")


def test_both_auth_headers_are_sent(monkeypatch):
    _enable_agentpulse(monkeypatch)
    captured_headers = {}

    def capture_post(*args, **kwargs):
        captured_headers.update(kwargs.get("headers", {}))
        return _OKResponse()

    monkeypatch.setattr("httpx.post", capture_post)
    client = AgentPulseClient.from_env(run_id="run_headers")
    assert client.start_run(input_summary="header check")
    assert captured_headers.get("Authorization") == "Bearer test-ingest-key"
    assert captured_headers.get("x-agentpulse-key") == "test-ingest-key"
    assert captured_headers.get("Content-Type") == "application/json"


def test_agentpulse_disables_when_env_missing(monkeypatch):
    monkeypatch.delenv("AGENTPULSE_URL", raising=False)
    monkeypatch.delenv("AGENTPULSE_INGEST_KEY", raising=False)
    monkeypatch.setenv("AGENTPULSE_ENABLED", "true")
    client = AgentPulseClient.from_env()
    assert client.enabled is False
    assert client.start_run(input_summary="test") is False


def test_agentpulse_network_failure_does_not_raise(monkeypatch):
    _enable_agentpulse(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("httpx.post", boom)
    client = AgentPulseClient.from_env()
    assert client.start_run(input_summary="test") is False


def test_agentpulse_redacts_sensitive_metadata():
    redacted = redact_metadata(
        {
            "api_key": "abc",
            "nested": {"Authorization": "Bearer secret", "safe": "ok"},
            "items": [{"refresh_token": "secret"}],
        }
    )
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["Authorization"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "ok"
    assert redacted["items"][0]["refresh_token"] == "[REDACTED]"


def test_agentpulse_event_payload_includes_required_fields(monkeypatch):
    _enable_agentpulse(monkeypatch)
    requests = []

    def capture_post(url, **kwargs):
        requests.append((url, kwargs["json"]))
        if url.endswith("/api/runs/start"):
            return _OKResponse({"run_id": kwargs["json"]["run_id"]})
        return _OKResponse({"accepted": 1, "rejected": 0, "errors": []})

    monkeypatch.setattr("httpx.post", capture_post)
    client = AgentPulseClient.from_env(run_id="run_test")
    assert client.start_run(input_summary="test")
    assert client.node_started("intake_request_parsing")

    start_payload = next(body for url, body in requests if url.endswith("/api/runs/start"))
    assert start_payload["project_id"] == "blog-agent"
    assert start_payload["project_name"] == "Blog Agent"
    assert start_payload["workflow_id"] == "blog-agent-v1"
    assert start_payload["run_id"] == "run_test"
    assert start_payload["summary"] == "test"

    trace_body = next(body for url, body in requests if url.endswith("/api/traces/events"))
    assert list(trace_body) == ["events"]
    payload = trace_body["events"][0]
    assert payload["project_id"] == "blog-agent"
    assert payload["project_name"] == "Blog Agent"
    assert payload["workflow_id"] == "blog-agent-v1"
    assert payload["run_id"] == "run_test"
    assert payload["event_type"] == "node_started"
    assert payload["event_id"].startswith("evt_")
    assert payload["timestamp"]


def test_agentpulse_smoke_test_emits_safe_events(monkeypatch):
    _enable_agentpulse(monkeypatch)
    requests = []

    def capture_post(url, **kwargs):
        requests.append((url, kwargs["json"]))
        if url.endswith("/api/runs/start"):
            return _OKResponse({"run_id": kwargs["json"]["run_id"]})
        if url.endswith("/api/traces/events"):
            return _OKResponse({"accepted": 1, "rejected": 0, "errors": []})
        return _OKResponse()

    monkeypatch.setattr("httpx.post", capture_post)
    assert run_smoke_test() is True
    event_types = [
        event["event_type"]
        for url, body in requests
        if url.endswith("/api/traces/events")
        for event in body["events"]
    ]
    assert any(url.endswith("/api/runs/start") for url, _ in requests)
    assert "model_call_started" in event_types
    assert "model_call_completed" in event_types
    assert "eval_completed" in event_types
    assert "artifact_created" in event_types
    assert any(url.endswith("/api/runs/complete") for url, _ in requests)


def test_model_wrapper_emits_started_and_completed(monkeypatch):
    from blogagent.llm.client import generate_structured
    from blogagent.llm.schemas import ResearchPlanOutput
    from blogagent.observability.agentpulse_client import use_client, use_node

    _enable_agentpulse(monkeypatch)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    requests = []

    def capture_post(url, **kwargs):
        requests.append((url, kwargs["json"]))
        return _OKResponse({"accepted": 1, "rejected": 0, "errors": []})

    monkeypatch.setattr("httpx.post", capture_post)
    client = AgentPulseClient.from_env(run_id="run_model")
    with use_client(client), use_node("editor_agent"):
        result = generate_structured("system", "user", ResearchPlanOutput)
    assert result.is_mock is True
    payloads = [
        event
        for url, body in requests
        if url.endswith("/api/traces/events")
        for event in body["events"]
    ]
    event_types = [p["event_type"] for p in payloads]
    assert "model_call_started" in event_types
    assert "model_call_completed" in event_types
    completed = next(p for p in payloads if p["event_type"] == "model_call_completed")
    assert completed["node_id"] == "editor_agent"
    assert completed["metadata"]["model_provider"] == "mock"


def test_failed_pipeline_emits_run_failed(monkeypatch):
    _enable_agentpulse(monkeypatch)
    requests = []

    def capture_post(url, **kwargs):
        requests.append((url, kwargs["json"]))
        if url.endswith("/api/runs/start"):
            return _OKResponse({"run_id": kwargs["json"]["run_id"]})
        return _OKResponse()

    def boom(state):
        raise RuntimeError("forced failure")

    monkeypatch.setattr("httpx.post", capture_post)
    import blogagent.workflow.graph as graph

    monkeypatch.setattr(graph, "_PRE_FACTCHECK", [boom])
    with pytest.raises(RuntimeError, match="forced failure"):
        graph.run_pipeline("Telemetry failure test")
    fail_payload = next(body for url, body in requests if url.endswith("/api/runs/fail"))
    assert fail_payload["error_summary"] == "RuntimeError: forced failure"


def test_real_pipeline_emits_agentpulse_run_and_trace(monkeypatch, caplog):
    _enable_agentpulse(monkeypatch)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    requests = []

    def capture_post(url, **kwargs):
        requests.append((url, kwargs["json"]))
        if url.endswith("/api/runs/start"):
            return _OKResponse({"run_id": kwargs["json"]["run_id"]})
        if url.endswith("/api/traces/events"):
            return _OKResponse(
                {
                    "accepted": len(kwargs["json"]["events"]),
                    "rejected": 0,
                    "errors": [],
                }
            )
        return _OKResponse()

    monkeypatch.setattr("httpx.post", capture_post)
    caplog.set_level(logging.INFO, logger="blogagent.observability.agentpulse_client")

    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("How photosynthesis works")

    start_payload = next(body for url, body in requests if url.endswith("/api/runs/start"))
    assert start_payload["project_id"] == "blog-agent"
    assert start_payload["workflow_id"] == "blog-agent-v1"
    assert not start_payload["run_id"].startswith("test-run_")
    assert "photosynthesis" in start_payload["summary"].lower()
    assert start_payload["run_id"] == state.run_id

    events = [
        event
        for url, body in requests
        if url.endswith("/api/traces/events")
        for event in body["events"]
    ]
    event_types = {event["event_type"] for event in events}
    node_ids = {event.get("node_id") for event in events}
    assert "node_started" in event_types
    assert "model_call_started" in event_types
    assert "model_call_completed" in event_types
    assert {
        "intake_request_parsing",
        "topic_product_research",
        "outline_generation",
        "draft_writing",
        "reviewer_critic_pass",
        "seo_optimization",
        "final_article_packaging",
    } <= node_ids

    complete_payload = next(
        body for url, body in requests if url.endswith("/api/runs/complete")
    )
    assert complete_payload["run_id"] == state.run_id
    assert "photosynthesis" in complete_payload["summary"].lower()

    messages = [record.getMessage() for record in caplog.records]
    assert any(message.startswith("AgentPulse enabled") for message in messages)
    assert any("AgentPulse startRun created run_id=" in message for message in messages)
    assert any("AgentPulse event sent:" in message for message in messages)
    assert any("AgentPulse completeRun sent" in message for message in messages)
