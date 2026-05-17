# Blog Output Quality Rubric

Score each dimension 0, 1, or 2. Total maximum: 18.

---

## 1. Factual grounding

Is every factual claim traceable to a source in the evidence table?

| Score | Criteria |
|---|---|
| 2 | All claims supported or partially supported; at least 3 real sources |
| 1 | Most claims supported; minor gaps; at least 1 real source |
| 0 | All sources are mock placeholders, or no sources exist |

---

## 2. Clarity

Is the language precise, concrete, and free of vague filler?

| Score | Criteria |
|---|---|
| 2 | Sentences are direct; no repetition; terminology is consistent |
| 1 | Occasional vague phrases or minor repetition; does not obscure meaning |
| 0 | Heavy filler ("very", "amazing", "incredibly important"); repeated phrases |

---

## 3. Structure

Does the heading hierarchy guide the reader through a logical argument?

| Score | Criteria |
|---|---|
| 2 | ≥3 `##` headings; logical section order; `###` used appropriately |
| 1 | ≥2 `##` headings; order is reasonable but not optimal |
| 0 | Fewer than 2 headings; generic headings ("Introduction", "Conclusion") only |

---

## 4. SEO quality

Do title, slug, meta description, and keywords meet the blog-post-seo-writing standard?

| Score | Criteria |
|---|---|
| 2 | Title 50–70 chars; slug 3–8 words; meta description 120–160 chars; 3–6 keywords |
| 1 | 1–2 fields slightly out of range but not egregiously wrong |
| 0 | Title <30 chars or generic; meta description <80 chars or missing; no keywords |

---

## 5. Originality

Does the article go beyond restating the topic name or headline?

| Score | Criteria |
|---|---|
| 2 | Adds context, explanation, or analysis not obvious from the topic alone |
| 1 | Mostly on-topic but lean on insight; reads like a padded definition |
| 0 | Article body is nearly identical to the title rephrased; no added value |

---

## 6. Source transparency

Is the research trace visible to the reader and the evaluator?

| Score | Criteria |
|---|---|
| 2 | `source_count` ≥3; `execution_mode` is `live` or `hybrid`; no mock URLs in body text |
| 1 | `source_count` ≥3 but all are mock; or body mentions mock URLs in passing |
| 0 | `source_count` <3; or `execution_mode=mock` with no disclosure in the evaluation |

---

## 7. Unsupported claim risk

Are all high-importance claims supported or hedged?

| Score | Criteria |
|---|---|
| 2 | Zero unsupported high-importance claims |
| 1 | One unsupported medium-importance claim (hedged or low-stakes) |
| 0 | One or more unsupported high-importance claims remain in the final output |

**This is the most critical dimension.** A score of 0 here is always a blocking issue.

---

## 8. Readability

Is the article a comfortable length and written at an appropriate reading level?

| Score | Criteria |
|---|---|
| 2 | ≥600 words; paragraphs ≤5 sentences; no walls of text |
| 1 | 400–599 words; or a few long paragraphs but otherwise readable |
| 0 | <400 words; or multiple paragraphs >8 sentences with no breaks |

---

## 9. Usefulness

Does a reader gain something actionable or informative from the article?

| Score | Criteria |
|---|---|
| 2 | Reader walks away with at least 2–3 concrete takeaways |
| 1 | Article is informative but abstract; takeaways are implied, not stated |
| 0 | Article states the obvious; a reader learns nothing they didn't already know |
