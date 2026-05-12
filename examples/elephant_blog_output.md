# Example BlogAgent Output — "African Elephants"

> **Note:** This is a sample output showing the expected format of a final `ArticlePackage`.
> The content below is illustrative. Real output requires live web search and LLM calls.

---

## Article

```markdown
# Understanding African Elephants

## Introduction

African elephants (*Loxodonta africana* and *Loxodonta cyclotis*) are the largest land
animals on Earth. They play a critical ecological role as "ecosystem engineers," shaping
the landscapes they inhabit through foraging, digging, and seed dispersal.

## Key Facts

- African elephants can weigh up to 6,000 kg and stand 3.3 m at the shoulder.
- They are classified as Vulnerable (*L. africana*) and Endangered (*L. cyclotis*) on
  the IUCN Red List.
- Elephant herds are matriarchal; the oldest female leads the group and holds
  decades of environmental memory.

## Recent Developments

Conservation efforts have intensified following poaching crises in the 2010s. Anti-poaching
technology, community-based conservation programs, and international ivory trade bans have
contributed to population stabilization in some regions, though habitat loss remains a
significant threat.

## Conclusion

African elephants are irreplaceable components of savanna and forest ecosystems. Their
continued survival depends on sustained international cooperation, habitat protection,
and community-level conservation incentives.
```

---

## Source List

| Title | URL | Domain | Overall Score |
|---|---|---|---|
| IUCN Red List — African Bush Elephant | https://www.iucnredlist.org/species/12392/3339343 | iucnredlist.org | 0.92 |
| WWF — African Elephant | https://www.worldwildlife.org/species/african-elephant | worldwildlife.org | 0.88 |
| National Geographic — Elephant | https://www.nationalgeographic.com/animals/mammals/facts/african-elephant | nationalgeographic.com | 0.85 |

---

## Fact-Check Report

```json
{
  "total_claims": 4,
  "supported_count": 3,
  "partially_supported_count": 1,
  "unsupported_count": 0,
  "passed": true,
  "blocking_issues": []
}
```

## Claim Support Statuses

| Claim | Importance | Status | Supporting Sources |
|---|---|---|---|
| African elephants can weigh up to 6,000 kg | high | supported | iucnredlist.org |
| Classified as Vulnerable / Endangered on IUCN Red List | high | supported | iucnredlist.org |
| Herds are matriarchal | medium | supported | nationalgeographic.com |
| Conservation improved after ivory trade bans | medium | partially_supported | worldwildlife.org |

---

## Revision Summary

No revisions required. All high-importance claims are supported. One medium claim
(ivory trade ban effectiveness) is partially supported; uncertainty is acknowledged
in the article text.
