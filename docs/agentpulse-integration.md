# AgentPulse Integration

BlogAgent can emit best-effort runtime trace events to AgentPulse. Telemetry is
disabled by default and never changes article generation behavior.

## Required Environment Variables

```bash
AGENTPULSE_ENABLED=true
AGENTPULSE_URL=http://localhost:3000
AGENTPULSE_INGEST_KEY=your_ingest_key
AGENTPULSE_PROJECT_ID=blog-agent
AGENTPULSE_PROJECT_NAME="Blog Agent"
AGENTPULSE_WORKFLOW_ID=blog-agent-v1
```

Optional:

```bash
AGENTPULSE_DEBUG=false
```

Telemetry is disabled unless `AGENTPULSE_ENABLED` is exactly `true` and both
`AGENTPULSE_URL` and `AGENTPULSE_INGEST_KEY` are present. Disabled telemetry is
silent unless debug mode is enabled.

## Smoke Test

The smoke test emits synthetic safe events and does not call any LLM provider:

```bash
uv run python -m blogagent.observability.agentpulse_smoke_test
```

Expected AgentPulse events:

- `run_started`
- `node_started`
- `model_call_started`
- `model_call_completed`
- `eval_completed`
- `artifact_created`
- `node_completed`
- `run_completed`

## Real BlogAgent Run

Run BlogAgent normally after setting the AgentPulse variables:

```bash
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

With live providers enabled, use the existing BlogAgent provider variables, for example:

```bash
BLOGAGENT_LLM_PROVIDER=google \
BLOGAGENT_USE_LLM_EDITOR=true \
GOOGLE_API_KEY=your_google_key \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

## Where To Check

Open AgentPulse and inspect `/dashboard/runs`. The run detail should show:

- Run lifecycle events
- Pipeline node start/completion events
- Model call events from the centralized LLM client
- Tool call events for search, extraction, source scoring, claim extraction, and citation matching
- Eval summaries for evidence sufficiency, quality, fact check, publishability, and publish contract
- A final article artifact reference

## Troubleshooting

- Env vars alone do not send events; a smoke test or real BlogAgent run must execute.
- AgentPulse must be reachable at `AGENTPULSE_URL`.
- `AGENTPULSE_INGEST_KEY` must match the AgentPulse integration configuration.
- Telemetry failures are best-effort and do not fail BlogAgent.
- Secrets are redacted from event metadata; do not place credentials in topics or source text.
- Missing token or cost details are sent as `null`; BlogAgent does not invent usage data.

## Limitations

- Token counts and cost are currently `null` because the provider wrapper does not expose
  normalized usage fields yet.
- The final article content is not uploaded. BlogAgent sends only a logical artifact reference,
  artifact type, title, and size.
- AgentPulse payload field names follow the `/api/traces/events` shape provided for this task.
