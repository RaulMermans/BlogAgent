# BlogAgent

A source-grounded editorial agent that turns a user topic into a researched, fact-checked, SEO-ready blog post.

This is not a generic AI blog generator. It is an agentic editorial workflow with web research, source extraction, source scoring, evidence tables, claim extraction, citation matching, evaluator-based revision, and final article packaging.

**Primary goal:** produce trustworthy blog drafts with visible research traces and claim-level support.

---

## MVP Architecture

The pipeline uses a **hybrid deterministic workflow** with two model roles:

### Agents

| Agent | Role |
|---|---|
| **Editor Agent** | Research planning, outline, draft, revision |
| **Fact-Check Evaluator** | Claim extraction, citation classification |

### Tools

| Tool | Permission | Purpose |
|---|---|---|
| `web_search` | read_only | Search for sources on the topic |
| `webpage_extract` | read_only | Extract text from source URLs |
| `source_score` | read_only | Score sources for credibility and relevance |
| `claim_extractor` | read_only | Extract factual claims from the draft |
| `citation_matcher` | read_only | Match claims to evidence sources |
| `validators` | read_only | Deterministic validation of the final package |

### Workflow

```text
User Topic
→ Intake Parser
→ Editor Agent research plan
→ web_search
→ webpage_extract
→ source_score
→ Evidence Table Builder
→ Editor Agent outline
→ Editor Agent draft
→ Fact-Check Evaluator
→ claim_extractor
→ citation_matcher
→ blog_package_validator
→ Editor Agent revision if needed
→ Final Article Package
```

The final `ArticlePackage` always contains:
- Article markdown
- Source list with scores
- Fact-check report
- Claim support statuses
- Revision summary

---

## Install

Requires Python 3.11+.

```bash
# With uv (recommended)
uv sync

# With pip
pip install -e ".[dev]"
```

---

## Run Tests

```bash
# With uv
uv run pytest

# With pytest directly
pytest
```

---

## Run the App

```bash
# With uv
uv run streamlit run app/ui/streamlit_app.py

# With streamlit directly
streamlit run app/ui/streamlit_app.py
```

---

## Run Evals

```bash
python -m blogagent.evals.runner
```

---

## Current Limitations

All LLM calls (Editor Agent, Fact-Check Evaluator) and external tool calls (web search, webpage extraction, source scoring) are deterministic stubs. The scaffold produces valid placeholder output that exercises the full pipeline shape and passes all validators.

See [docs/limitations.md](docs/limitations.md) for the complete list of what is not yet implemented.

---

## Project Structure

```
blogagent/
  workflow/       State models, pipeline nodes, graph runner
  agents/         Editor Agent and Fact-Check Evaluator stubs + prompts
  tools/          Tool stubs + deterministic validators
  evals/          Eval cases, runner, and graders

app/ui/           Streamlit UI

tests/            Pytest test suite
docs/             Architecture, eval plan, limitations
examples/         Sample outputs and run traces
```
