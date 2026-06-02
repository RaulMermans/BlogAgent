"""AgentPulse telemetry client.

The client is intentionally best-effort: disabled configuration and network
failures never affect BlogAgent pipeline execution.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import uuid
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from typing import Any

_SENSITIVE_KEY_PARTS = (
    "key",
    "secret",
    "token",
    "password",
    "credential",
    "authorization",
    "api_key",
)
_MAX_TEXT_LEN = 240

_current_client: contextvars.ContextVar["AgentPulseClient | None"] = contextvars.ContextVar(
    "agentpulse_client",
    default=None,
)
_current_node_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agentpulse_node_id",
    default=None,
)


class AgentPulseClient:
    """Small AgentPulse runtime ingestion client."""

    def __init__(
        self,
        *,
        base_url: str,
        ingest_key: str,
        project_id: str = "blog-agent",
        project_name: str = "Blog Agent",
        workflow_id: str = "blog-agent-v1",
        enabled: bool = True,
        debug: bool = False,
        timeout_seconds: float = 5.0,
        run_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.ingest_key = ingest_key
        self.project_id = project_id
        self.project_name = project_name
        self.workflow_id = workflow_id
        self.enabled = enabled
        self.debug = debug
        self.timeout_seconds = timeout_seconds
        self.run_id = run_id or self.generate_run_id()

    @classmethod
    def from_env(cls, *, run_id: str | None = None) -> "AgentPulseClient":
        enabled = os.getenv("AGENTPULSE_ENABLED", "false").strip().lower() == "true"
        debug = os.getenv("AGENTPULSE_DEBUG", "false").strip().lower() == "true"
        base_url = os.getenv("AGENTPULSE_URL", "").strip()
        ingest_key = os.getenv("AGENTPULSE_INGEST_KEY", "").strip()
        configured = enabled and bool(base_url) and bool(ingest_key)
        return cls(
            base_url=base_url,
            ingest_key=ingest_key,
            project_id=os.getenv("AGENTPULSE_PROJECT_ID", "blog-agent").strip() or "blog-agent",
            project_name=os.getenv("AGENTPULSE_PROJECT_NAME", "Blog Agent").strip()
            or "Blog Agent",
            workflow_id=os.getenv("AGENTPULSE_WORKFLOW_ID", "blog-agent-v1").strip()
            or "blog-agent-v1",
            enabled=configured,
            debug=debug,
            run_id=run_id,
        )

    @staticmethod
    def generate_run_id() -> str:
        return f"run_{uuid.uuid4().hex}"

    @staticmethod
    def generate_event_id() -> str:
        return f"evt_{uuid.uuid4().hex}"

    @property
    def ingest_url(self) -> str:
        return f"{self.base_url}/api/traces/events"

    def start_run(
        self,
        *,
        input_summary: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.emit_event(
            "run_started",
            status="started",
            input=input_summary,
            metadata=metadata,
        )

    def complete_run(
        self,
        *,
        output_summary: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.emit_event(
            "run_completed",
            status="completed",
            output=output_summary,
            metadata=metadata,
        )

    def fail_run(self, *, error: str, metadata: Mapping[str, Any] | None = None) -> bool:
        merged = {"error": safe_summary(error), **dict(metadata or {})}
        return self.emit_event("run_failed", status="failed", metadata=merged)

    def node_started(self, node_id: str, metadata: Mapping[str, Any] | None = None) -> bool:
        return self.emit_event(
            "node_started",
            node_id=node_id,
            status="started",
            metadata=metadata,
        )

    def node_completed(
        self,
        node_id: str,
        *,
        latency_ms: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        merged = dict(metadata or {})
        if latency_ms is not None:
            merged["latency_ms"] = latency_ms
        return self.emit_event(
            "node_completed",
            node_id=node_id,
            status="completed",
            metadata=merged,
        )

    def model_call_started(self, node_id: str | None, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "model_call_started",
            node_id=node_id,
            status="started",
            metadata=metadata,
        )

    def model_call_completed(self, node_id: str | None, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "model_call_completed",
            node_id=node_id,
            status="completed",
            metadata=metadata,
        )

    def model_call_failed(self, node_id: str | None, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "model_call_failed",
            node_id=node_id,
            status="failed",
            metadata=metadata,
        )

    def tool_call_started(self, tool_name: str, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "tool_call_started",
            node_id=current_node_id(),
            status="started",
            metadata={"tool_name": tool_name, **dict(metadata)},
        )

    def tool_call_completed(self, tool_name: str, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "tool_call_completed",
            node_id=current_node_id(),
            status="completed",
            metadata={"tool_name": tool_name, **dict(metadata)},
        )

    def tool_call_failed(self, tool_name: str, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "tool_call_failed",
            node_id=current_node_id(),
            status="failed",
            metadata={"tool_name": tool_name, **dict(metadata)},
        )

    def eval_started(self, eval_id: str, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "eval_started",
            node_id=current_node_id(),
            status="started",
            metadata={"eval_id": eval_id, **dict(metadata)},
        )

    def eval_completed(self, eval_id: str, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "eval_completed",
            node_id=current_node_id(),
            status="completed",
            metadata={"eval_id": eval_id, **dict(metadata)},
        )

    def eval_failed(self, eval_id: str, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "eval_failed",
            node_id=current_node_id(),
            status="failed",
            metadata={"eval_id": eval_id, **dict(metadata)},
        )

    def artifact_created(self, metadata: Mapping[str, Any]) -> bool:
        return self.emit_event(
            "artifact_created",
            node_id=current_node_id(),
            status="completed",
            metadata=metadata,
        )

    def emit_event(
        self,
        event_type: str,
        *,
        node_id: str | None = None,
        status: str | None = None,
        input: str | None = None,
        output: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        payload = {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "event_id": self.generate_event_id(),
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": redact_metadata(dict(metadata or {})),
        }
        if status is not None:
            payload["status"] = status
        if node_id is not None:
            payload["node_id"] = node_id
        if input is not None:
            payload["input"] = safe_summary(input)
        if output is not None:
            payload["output"] = safe_summary(output)
        return self._post(payload)

    def _post(self, payload: dict[str, Any]) -> bool:
        try:
            import httpx  # noqa: PLC0415

            response = httpx.post(
                self.ingest_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.ingest_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001
            if self.debug:
                print(
                    "AgentPulse telemetry failed: "
                    f"{type(exc).__name__}: {safe_summary(str(exc))}"
                )
            return False


def current_client() -> AgentPulseClient | None:
    client = _current_client.get()
    if client is not None and client.enabled:
        return client
    return None


def current_node_id() -> str | None:
    return _current_node_id.get()


@contextlib.contextmanager
def use_client(client: AgentPulseClient | None) -> Iterator[None]:
    token = _current_client.set(client)
    try:
        yield
    finally:
        _current_client.reset(token)


@contextlib.contextmanager
def use_node(node_id: str) -> Iterator[None]:
    token = _current_node_id.set(node_id)
    try:
        yield
    finally:
        _current_node_id.reset(token)


def redact_metadata(value: Any) -> Any:
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return redact_metadata(value.model_dump())
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if _is_sensitive_key(key_str):
                redacted[key_str] = "[REDACTED]"
            else:
                redacted[key_str] = redact_metadata(item)
        return redacted
    if isinstance(value, list):
        return [redact_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [redact_metadata(item) for item in value]
    if isinstance(value, str):
        return safe_summary(value)
    return value


def safe_summary(value: Any, *, max_len: int = _MAX_TEXT_LEN) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(part in lower for part in _SENSITIVE_KEY_PARTS)
