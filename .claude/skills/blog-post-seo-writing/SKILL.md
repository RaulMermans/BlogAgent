---
name: blog-post-seo-writing
description: >
  Structure and write SEO-ready blog post outputs for BlogAgent. Use this skill
  whenever the user wants to review, revise, improve, or evaluate a BlogAgent article
  output, write an Editor Agent prompt that specifies output format expectations,
  or check whether a generated draft is publish-ready. Also invoke it when the user
  asks about title formatting, slug conventions, meta descriptions, heading structure,
  or keyword density for BlogAgent articles. Do not use for pipeline configuration,
  provider selection, or factual accuracy checking (use blog-output-evaluator for that).
---

# Skill: blog-post-seo-writing

A structured writing standard for BlogAgent article outputs.

Every article package produced by BlogAgent must pass this standard before it can be considered publish-ready. Use this skill to apply, review, or explain the standard.

---

## Title

- 50–70 characters
- Front-loads the primary keyword
- Specific to the topic — no generic "A Complete Guide to X"
- No fabricated superlatives or clickbait

**Good:** `Why African Elephants Are the World's Largest Land Animals`
**Weak:** `Everything You Need to Know About Elephants`

---

## Slug

- Lowercase, hyphen-separated, URL-safe
- Derived from the title
- 3–8 meaningful words; drop stop words (the, a, an, of, to)

**Good:** `african-elephants-largest-land-animals`
**Weak:** `why-african-elephants-are-the-worlds-largest-land-animals-2024`

---

## Meta description

- 120–160 characters
- Summarises the article's main value for the reader
- Includes the primary SEO keyword naturally
- Written for a human scanning search results, not for a crawler

---

## Intro (first 80–150 words)

- Hook: 1–2 sentences on why the topic matters
- Scope: what the article covers
- No fabricated statistics — every number must exist in the evidence table
- Don't start with "In this article we will…"

---

## Heading structure

- Use `##` for major sections, `###` for subsections
- At least 3 `##` headings per article
- Headings are descriptive noun phrases or specific questions — not "Introduction", "Body", "Conclusion"
- Primary keyword appears in at least one `##` heading

---

## Body: source-grounded claims

- Every numerical claim (percentage, count, measurement, date) must appear in the evidence table
- Unsupported high-importance claims must be removed or rewritten as hedged statements ("Research suggests…", "Studies indicate…")
- Citation attribution is captured in the fact-check report, not by inline footnote links (MVP constraint)
- Do not draft new factual paragraphs without checking the evidence table first

---

## SEO keyword use

- 3–6 keywords in `seo_keywords`; all lowercase
- Primary keyword in title, at least one `##` heading, and the intro
- Secondary keywords appear naturally in the body — not crammed in
- Keyword density should feel human: if you notice a word appearing every other sentence, that's too much

---

## Conclusion

- 2–3 sentence summary of key takeaways
- Optional: single call to action aligned with the topic
- No new factual claims in the conclusion

---

## Final checklist before marking an article publish-ready

- [ ] `title` is 50–70 chars and topic-specific
- [ ] `slug` is URL-safe, 3–8 words
- [ ] `meta_description` is 120–160 chars
- [ ] Article has ≥3 `##` headings
- [ ] Article is ≥600 words
- [ ] All high-importance claims are `supported` or `partially_supported`
- [ ] `seo_keywords` has 3–6 lowercase terms
- [ ] No mock placeholder URLs (`.example.dev`) in the article body
- [ ] `revision_summary` reflects any changes made

---

## Reference files

- See `references/blog-output-template.md` for a fill-in-the-blanks article template
- See `references/examples.md` for annotated strong and weak output examples
