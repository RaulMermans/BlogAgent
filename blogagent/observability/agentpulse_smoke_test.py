"""Emit a safe synthetic AgentPulse trace without running an LLM."""

from __future__ import annotations

from blogagent.observability.agentpulse_client import AgentPulseClient, use_client, use_node


def run_smoke_test() -> bool:
    client = AgentPulseClient.from_env()
    sent = False
    with use_client(client):
        sent = client.start_run(
            input_summary="AgentPulse smoke test",
            metadata={"mode": "smoke_test"},
        ) or sent
        with use_node("agentpulse_smoke_node"):
            sent = client.node_started("agentpulse_smoke_node") or sent
            sent = client.model_call_started(
                "agentpulse_smoke_node",
                {
                    "model_provider": "mock",
                    "model_name": "mock-1.0",
                    "agent": "agentpulse_smoke",
                },
            ) or sent
            sent = client.model_call_completed(
                "agentpulse_smoke_node",
                {
                    "model_provider": "mock",
                    "model_name": "mock-1.0",
                    "agent": "agentpulse_smoke",
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost_usd": None,
                    "latency_ms": 0,
                },
            ) or sent
            sent = client.eval_completed(
                "agentpulse_smoke_eval",
                {
                    "eval_name": "AgentPulse Smoke Eval",
                    "eval_type": "schema",
                    "passed": True,
                    "score": 1.0,
                    "findings": [],
                },
            ) or sent
            sent = client.artifact_created(
                {
                    "artifact_type": "article_markdown",
                    "artifact_ref": "agentpulse-smoke-test",
                    "artifact_size_bytes": 0,
                }
            ) or sent
            sent = client.node_completed("agentpulse_smoke_node", latency_ms=0) or sent
        sent = client.complete_run(
            output_summary="AgentPulse smoke test complete",
            metadata={"mode": "smoke_test"},
        ) or sent
    return sent


def main() -> None:
    sent = run_smoke_test()
    if sent:
        print("AgentPulse smoke test emitted events.")
    else:
        print("AgentPulse smoke test did not emit events; telemetry is disabled or unreachable.")


if __name__ == "__main__":
    main()
