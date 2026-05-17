---
name: blog-output-evaluator
description: >
  Evaluate the quality of a BlogAgent article output against a structured rubric.
  Use this skill when the user wants to score, grade, or audit a generated blog post,
  compare two article outputs, identify weaknesses in a draft, or decide whether a
  BlogAgent run produced a publish-ready result. Also invoke it when the user asks
  "is this good enough?", "what's wrong with this article?", or "how does this compare
  to the live run?". Do not use for writing new articles (use blog-post-seo-writing)
  or for pipeline configuration.
---

# Skill: blog-output-evaluator

A rubric-based evaluator for BlogAgent article outputs.

Run this evaluation after any BlogAgent run you want to audit. It produces a structured
score and a list of specific issues to fix. Use the rubric in `references/rubric.md` as
the scoring source of truth.

---

## What this evaluator checks

Nine dimensions, each scored 0–2 (0 = fail, 1 = partial, 2 = pass):

| Dimension | What it measures |
|---|---|
| **Factual grounding** | Claims are backed by sources in the evidence table |
| **Clarity** | Language is precise, not vague or repetitive |
| **Structure** | Heading hierarchy and section order make sense |
| **SEO quality** | Title, slug, meta description, and keywords meet the standard |
| **Originality** | Prose goes beyond restating the topic name or headline |
| **Source transparency** | Source count, mock vs real sources, execution_mode are visible |
| **Unsupported claim risk** | No high-importance unsupported claims in the final output |
| **Readability** | ≥600 words, appropriate reading level, no run-on paragraphs |
| **Usefulness** | A reader gains something actionable or informative from the article |

---

## How to run an evaluation

1. Load the article output (from JSON or `/run` response).
2. Score each dimension against the rubric in `references/rubric.md`.
3. Compute total score: sum of all dimension scores, max 18.
4. Flag any dimension scoring 0 as a **blocking issue**.
5. Report using the output format below.

---

## Output format

```
## BlogAgent Output Evaluation

**Topic:** <topic>
**Execution mode:** <mock|hybrid|live>
**Source count:** <n> (<n real>, <n mock>)

| Dimension              | Score | Note |
|------------------------|-------|------|
| Factual grounding      | 2/2   |      |
| Clarity                | 1/2   | Repeated phrasing in section 2 |
| Structure              | 2/2   |      |
| SEO quality            | 1/2   | Meta description is 88 chars (too short) |
| Originality            | 2/2   |      |
| Source transparency    | 2/2   |      |
| Unsupported claim risk | 0/2   | BLOCKING: 1 unsupported high-importance claim |
| Readability            | 2/2   |      |
| Usefulness             | 2/2   |      |

**Total: 14/18**

### Blocking issues
- [ ] Unsupported high-importance claim: "<claim text>" — revise or hedge

### Recommended fixes
- Meta description: expand to 120–160 chars
- Section 2: rewrite repeated phrasing around "<phrase>"
```

---

## Blocking threshold

An article fails evaluation if **any** of these conditions are true:

- `unsupported_claim_risk` score = 0 (any high-importance claim is unsupported)
- `factual_grounding` score = 0 (no sources, or all sources are mock placeholders)
- Total score < 10/18

A failing article must not be marked publish-ready until all blocking issues are resolved.

---

## Reference files

- See `references/rubric.md` for the full scoring rubric with per-score definitions
