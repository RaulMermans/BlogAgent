"""AgentPulse telemetry client.

The client is intentionally best-effort: disabled configuration and network
failures never affect BlogAgent pipeline execution.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
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
_TRUE_VALUES = {"1", "true", "yes", "on"}

logger = logging.getLogger(__name__)

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
        enabled = _env_bool("AGENTPULSE_ENABLED")
        debug = _env_bool("AGENTPULSE_DEBUG")
        base_url = os.getenv("AGENTPULSE_URL", "").strip()
        ingest_key = os.getenv("AGENTPULSE_INGEST_KEY", "").strip()
        configured = enabled and bool(base_url) and bool(ingest_key)
        client = cls(
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
        if configured:
            logger.info(
                "AgentPulse enabled project_id=%s workflow_id=%s",
                client.project_id,
                client.workflow_id,
            )
        elif enabled:
            logger.warning(
                "AgentPulse requested but disabled: AGENTPULSE_URL and "
                "AGENTPULSE_INGEST_KEY are required"
            )
        return client

    @staticmethod
    def generate_run_id() -> str:
        return f"run_{uuid.uuid4().hex}"

    @staticmethod
    def generate_event_id() -> str:
        return f"evt_{uuid.uuid4().hex}"

    def start_run(
        self,
        *,
        input_summary: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        result = self._post_json(
            "/api/runs/start",
            {
                "project_id": self.project_id,
                "project_name": self.project_name,
                "workflow_id": self.workflow_id,
                "run_id": self.run_id,
                "summary": safe_summary(input_summary),
                "metadata": redact_metadata(dict(metadata or {})),
            },
        )
        if result is None:
            return False
        returned_run_id = result.get("run_id")
        if isinstance(returned_run_id, str) and returned_run_id:
            self.run_id = returned_run_id
        logger.info("AgentPulse startRun created run_id=%s", self.run_id)
        return True

    def complete_run(
        self,
        *,
        output_summary: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        result = self._post_json(
            "/api/runs/complete",
            {
                "run_id": self.run_id,
                "summary": safe_summary(output_summary),
                "metadata": redact_metadata(dict(metadata or {})),
            },
        )
        if result is None:
            return False
        logger.info("AgentPulse completeRun sent run_id=%s", self.run_id)
        return True

    def fail_run(self, *, error: str, metadata: Mapping[str, Any] | None = None) -> bool:
        if not self.enabled:
            return False
        result = self._post_json(
            "/api/runs/fail",
            {
                "run_id": self.run_id,
                "error_summary": safe_summary(error),
                "metadata": redact_metadata(dict(metadata or {})),
            },
        )
        if result is None:
            return False
        logger.info("AgentPulse failRun sent run_id=%s", self.run_id)
        return True

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
            "error",
            node_id=node_id,
            status="failed",
            output=safe_summary(metadata.get("error", "Model call failed")),
            metadata={"event_scope": "model_call", **dict(metadata)},
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
            "eval_completed",
            node_id=current_node_id(),
            status="failed",
            metadata={"eval_id": eval_id, "passed": False, **dict(metadata)},
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
            payload["input_summary"] = safe_summary(input)
        if output is not None:
            payload["output_summary"] = safe_summary(output)
        result = self._post_json("/api/traces/events", {"events": [payload]})
        if result is None:
            return False
        if result.get("rejected", 0):
            logger.warning(
                "AgentPulse event rejected: event_type=%s run_id=%s errors=%s",
                event_type,
                self.run_id,
                safe_summary(result.get("errors")),
            )
            return False
        logger.info("AgentPulse event sent: %s run_id=%s", event_type, self.run_id)
        return True

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            import httpx  # noqa: PLC0415

            response = httpx.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.ingest_key}",
                    "x-agentpulse-key": self.ingest_key,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            response_json = getattr(response, "json", None)
            if callable(response_json):
                data = response_json()
                if isinstance(data, dict):
                    return data
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AgentPulse telemetry failed path=%s error=%s: %s",
                path,
                type(exc).__name__,
                safe_summary(str(exc)),
                exc_info=self.debug,
            )
            return None


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


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES
