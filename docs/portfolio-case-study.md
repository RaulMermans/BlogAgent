# BlogAgent — Evidence-Aware Blog Drafting Workflow

> **Portfolio blurb:** BlogAgent is a hybrid deterministic/LLM editorial workflow that
> turns a topic into a source-grounded, copy-paste-ready blog draft. Deterministic
> Python code owns workflow order, schemas, validation, candidate locking, and the
> final publish-status decision; a small number of LLM-backed agents handle research
> synthesis, drafting, and revision inside those guardrails. The result is a draft a
> human can review and lightly edit — with a visible research trace, a locked
> candidate table for recommendation articles, and an explicit "copy-ready / needs
> review / needs revision" status — rather than an opaque wall of generated text.

---

## 1. Problem

Generic AI blog generators produce fluent text with no way to tell whether a claim,
citation, or recommended product is real. For "best X for Y" articles this is
especially risky: a fabricated product name, a dropped item from a promised count, or
a reviewer's name mistaken for a product ("Paul Altieri" instead of a watch) can end
up in a published draft and quietly damage editorial credibility.

At the same time, doing this work by hand — research, source scoring, evidence
tables, drafting, fact-checking, SEO metadata — is slow, and the verification steps
are the ones most likely to get skipped under time pressure.

The problem BlogAgent addresses is not "can an LLM write a blog post" (it can) but
"can the workflow *prove* that what it wrote is grounded in real sources, matches the
locked candidate set, and is internally consistent — before a human spends time
reviewing it."

## 2. Product goal

BlogAgent is an **internal editorial drafting tool**, not an autopublishing system, a
guaranteed-factuality engine, or a public SaaS product. The goal is narrow and
concrete:

- Turn a topic into a researched, source-grounded draft with SEO metadata (title,
  slug, meta description, keywords).
- Surface the research trail (sources, evidence table, candidate ledger, fact-check
  report) so a human reviewer can verify claims before publishing.
- For recommendation-style articles, guarantee the article can't silently invent or
  drop items from the validated candidate set.
- Give a clear, user-facing signal — copy-ready, copy-ready after light review, or
  needs revision — so a reviewer knows how much scrutiny a given draft needs.

A human always reviews, edits, and manually publishes. Nothing in the pipeline ever
calls out to a CMS, social platform, email provider, or scheduler.

## 3. Architecture decision

The guiding principle (from the project constitution) is: **keep the architecture
boring, make the evidence layer impressive.**

In practice that meant:

- **Deterministic code owns workflow order, schemas, validation, limits, and the
  final publish decision.** Search limits, revision limits, count checks, candidate
  validity, and the publish-status arbiter are all plain Python with tests — not
  prompts.
- **LLMs are used only where judgment is genuinely required**: research planning,
  outline generation, drafting, evaluator feedback, and revision.
- **Two agent roles, not many.** An Editor Agent (research plan, outline, draft,
  revision) and a Fact-Check Evaluator (claim extraction + judgment) cover the LLM
  surface area. New agents (e.g. the Reviewer/Revision authority layer) were added
  only after a *measured, repeated failure* — not speculatively.
- **Mock-first.** The default LLM and search providers are deterministic mocks with
  no API keys, so the entire pipeline and test suite (1,160+ tests) run for free and
  reproducibly. Live providers (Anthropic, OpenAI, Google) are opt-in, and every LLM
  stage records whether it actually ran live or fell back to mock
  (`provider_events`, `execution_mode`) — so "live" claims can be verified, not
  assumed.

## 4. Workflow design

The non-negotiable ordering rule is **evidence first, article second**:

```text
research questions
→ source search
→ source extraction
→ source scoring
→ evidence table
→ candidate pack (locked recommendation set)
→ outline
→ draft
→ writer-output audit
→ reviewer / revision
→ editorial polish
→ post-article grounding
→ final answer contract
→ final article package
```

The Editor Agent never drafts before the evidence table and candidate pack exist —
the locked candidate set is built *before* the writer is invoked, so the model is
writing inside a fixed skeleton (which entities, how many, in what structure) rather
than choosing the recommendation set itself. Everything after drafting
(audit → review → revision → polish → grounding → final contract) exists to verify
that the draft stayed inside that skeleton, and to repair it deterministically when
it didn't.

## 5. Agent roles

**Editor Agent**
- Generates research questions, the outline, the draft, and (when needed) revisions.
- Reads the evidence table and candidate pack before writing — it does not search for
  sources after the fact.
- Gated by `BLOGAGENT_USE_LLM_EDITOR` (default `false` → mock output).

**Fact-Check Evaluator**
- Extracts factual claims and classifies each as `supported`, `partially_supported`,
  or `unsupported` against the evidence table.
- Runs as a separate role from the drafter, for independence — it judges only the
  claims, citations, and sources it's given, and never invents sources.
- Gated by `BLOGAGENT_USE_LLM_FACTCHECK` (default `false` → deterministic heuristic).

Both roles are LLM-optional. In mock mode they produce structured, topic-aware output
deterministically, which is what the test suite and CI run against.

## 6. Deterministic guardrails

A few guardrails do most of the safety work, all in plain code:

- **`check_external_effects`** — the second step in the pipeline. If the topic
  contains publishing/posting/sending/scheduling language, `state.blocked = True` is
  set and the pipeline returns immediately without running the article workflow.
- **QueryContract** — built once, right after the guardrail, and locks
  `task_type`, `domain`, `requested_count`, and `answer_entity_type` for the rest of
  the run. A counted recommendation query can never silently degrade to
  `general/general_answer`.
- **AnswerCountSnapshot coherence invariants** — e.g. `allowed_candidates_count == 0`
  can never produce `count_status == "satisfied"`; `draft_candidate_compliance_passes
  == False` can never produce `"satisfied"`. These close "impossible state" bugs
  where the count math and the publish status disagreed.
- **Three deterministic validators** run before any article is considered complete:
  schema validity, minimum source count, and "no unsupported high-importance claims."

## 7. Candidate validation

For recommendation articles ("5 best affordable luxury watches"), the riskiest
failure mode isn't bad prose — it's recommending something that isn't a real,
evidence-backed product.

- **EntityCandidateLedger + Candidate Cleanliness Gate v2** require a non-empty
  canonical name, a matching answer-entity type, high/medium source quality, compact
  evidence spans, `clean_name_score >= 0.75`, and `evidence_score >= 0.65` before a
  candidate is marked `usable`.
- **CandidatePack** is the deduplicated, *locked* set the writer is allowed to use.
  Every later count and audit step measures against this set, not against whatever
  the model happens to produce.
- **CandidatePackQualityReport** is a pre-draft gate that catches invalid entities
  (people, bylines, dates, navigation fragments), dirty display names, light source
  coverage, and missing evidence — and assigns a `publish_ceiling` and
  `repair_action` *before* the writer ever sees the topic.

The concrete failure that motivated this layer: a watch-recommendation candidate list
that included **"Paul Altieri"** — a dealer/reviewer name, not a watch — alongside
real models like the Tissot PRX Quartz. The cleanliness gate and quality report now
catch this class of error deterministically, with a regression test
(`test_affordable_luxury_watches_no_paul_altieri`) locking the behavior in.

## 8. Reviewer/revision loop

Article-producing stages communicate through typed, validated artifacts rather than
free-form chat:

```text
WriterHandoff → WriterOutputAudit → ReviewPacket → RevisionPlan
→ RevisionOutputAudit → PolishHandoff → PolishOutputAudit
```

`WriterOutputAudit`, `RevisionOutputAudit`, and `PolishOutputAudit` are deterministic
proofs that locked candidate IDs, display names, Quick Picks, detail sections, count
mode, and source URLs survived each stage.

`ReviewPacket` is the Reviewer's authority. Beyond per-defect checks (missing locked
candidates, Quick Picks/count mismatches, unsupported entities), it also evaluates
the *CandidatePack itself*:

- `candidate_pack_valid` / `invalid_locked_candidates` — did the locked candidate set
  contain an invalid entity?
- `extra_recommendation_sections` / `missing_recommendation_sections` — does the
  article's section structure match the locked set exactly?
- `revision_mode` — one of `none`, `prose_polish`, `count_contract_repair`,
  `candidate_pack_rebuild`, or `evidence_report_required`.

If the CandidatePack itself is invalid, `build_revision_plan` forces
`revision_strategy = "full_rewrite"` and adds an explicit forbidden change: prose-only
polish is not allowed to paper over an invalid candidate pack — the pack has to be
rebuilt first. This loop is bounded: at most one revision pass and one polish pass
per run, by design.

## 9. Final answer contract

`FinalAnswerContract` is the single source of truth for `publish_ready_status`,
computed after polish and post-article grounding. It enforces invariants such as:

| Rule | Effect |
|---|---|
| `count_status == "failed"` | → `draft_only_not_publish_ready` (always) |
| `allowed_count == 0` and `article_count > 0` | → impossible state → `draft_only_not_publish_ready` |
| `quick_picks_count != final_article_count` | → structural mismatch → failure |
| `title_declared_count != final_article_count` | → title/body conflict → failure |
| `final_article_count < minimum_publishable_items` | → below floor → failure |

On top of those count/structure invariants, `FinalAnswerContract` now also accepts the
Reviewer's `ReviewPacket` as a veto: even an article that would otherwise score
100/100 on the quality gate is forced to `draft_only_not_publish_ready` if the
Reviewer found `candidate_pack_valid = False` or `revision_mode` in
`{candidate_pack_rebuild, evidence_report_required}`. A clean editorial score cannot
override a failed candidate pack.

The internal `publish_ready_status` enum is never shown to users directly. A small
presentation layer (`article_presentation.py`) maps it to copy-ready language:

| Internal status | User-facing label |
|---|---|
| `publish_ready` | "Copy-ready" |
| `publish_ready_with_editorial_review` / `publish_ready_with_warnings` | "Copy-ready after light review" |
| `draft_only_not_publish_ready` | "Needs revision before use" |

## 10. Safety model

- **No external side effects.** CMS publishing, social posting, email, and scheduling
  are all blocked by `check_external_effects` before the pipeline runs — there is no
  code path that reaches an external system.
- **High-risk topics degrade gracefully.** For financial/legal/medical topics where
  confidence is too low, the pipeline can fall back to an evidence report (sources +
  what was found + why it isn't publish-ready) instead of a polished draft that
  overstates certainty.
- **Debug vs. visible separation.** The visible article card shows only title, slug,
  meta description, SEO keywords, status badge, tone badge, and the article body.
  Internal artifacts — Query Contract, Candidate Ledger, CandidatePack internals,
  provider events, the raw `FinalAnswerContract`, editorial polish notes, and revision
  summaries — are confined to a separate Debug / Research & Candidate Trace view, and
  raw internal status enums are stripped from the visible markdown.
- **Worker secret is a demo gate, not auth.** Documented explicitly as not suitable
  for production without additional infrastructure (no accounts, sessions, or roles).

## 11. Evaluation approach

The eval suite (`blogagent/evals/runner.py`) covers eight topic types chosen to
exercise different failure modes:

- simple factual topic
- scientific explainer
- historical topic
- contradictory data topic
- current/recent topic
- weak-evidence topic
- no-research-needed topic
- unsafe publishing request

Tracked metrics include schema validity, fake URL rate, minimum source count,
unsupported high-importance claims, citation match accuracy, revision improvement,
latency, and (where available) cost per run.

Target standards: **0% fake URL rate, 100% final-package schema validity, 0
unsupported high-importance claims in final output, and at least 3 credible sources
for factual research topics.**

The broader test suite (1,160+ tests) runs entirely in mock mode in CI with no API
keys, covering the deterministic gates, agent handoffs, and presentation-layer rules
described above.

## 12. Limitations

This project is intentionally scoped, and the limitations are documented (see
[`docs/limitations.md`](limitations.md)) rather than hidden:

- **Mock-first.** All tests and CI runs use the mock LLM/search providers by default;
  live-provider output quality has not been benchmarked in the eval suite.
- **Heuristic citation matching.** The default matcher is a deterministic heuristic;
  an optional LLM semantic citation judge exists but is opt-in and still bounded by
  the provided source excerpt.
- **Bounded revision.** Total revision budget is one pass across quality,
  final-validation, and fact-check loops, plus at most one editorial polish pass.
  This keeps the system predictable but means some drafts will land in "needs
  revision before use" rather than being auto-fixed.
- **Candidate extraction is source-dependent and heuristic.** It cannot recover
  products that were never found in search results, and aliases/transliterations may
  not match.
- **No persistence layer.** `BlogRunState` is in-memory only; nothing is stored
  between runs.
- **Human review is still required**, even for `publish_ready` output. The contract
  guarantees structural and candidate-set consistency, not editorial quality or
  factual perfection.

## 13. What I learned

Most of the "AI quality" problems I ran into during this project were not actually
generation problems — they were **identity and bookkeeping problems**: did the
article recommend the things it was supposed to, in the count it promised, with the
structure it claimed? An LLM asked to "write 5 recommendations" will confidently
produce 4, or 6, or include something that isn't a product at all (a reviewer's
name), and no amount of prompt tuning reliably fixes that. Deterministic counting,
locking, and auditing fixed it immediately and is testable in a way prompts aren't.

The second lesson was about sequencing the guardrails themselves. Adding the
Reviewer/Revision authority layer and the `FinalAnswerContract` veto in response to a
*specific observed failure* (an invalid candidate sneaking through to a "100/100"
article) kept the system from growing speculative machinery. Each new check exists
because something specific got through without it, and each has a regression test
tied to that failure.

Finally, separating "what the system did" from "what the user needs to decide" turned
out to matter as much as the correctness work itself. A technically-correct article
that surfaces `FINAL ANSWER CONTRACT` and `publish_ready_with_editorial_review` to an
end user is confusing in a way that a "Copy-ready after light review" badge isn't —
even though the underlying guarantee is identical. Keeping that translation layer
separate from (and strictly additive to) the internal contract meant the safety
properties didn't have to change to make the tool usable.
