# Blog Output Examples

## Strong output

**Why it works:** specific title, grounded claims, clear heading structure, no mock sources in body.

```
title: Why African Elephants Are the World's Largest Land Animals
slug: african-elephants-largest-land-animals
meta_description: African elephants can weigh up to 7 tonnes and stand 4 metres tall.
  Discover the biology and evolution behind their record-breaking size.
seo_keywords: [african elephants, largest land animal, elephant size, elephant weight, savanna mammals]

## The Scale of African Elephants

African bush elephants (*Loxodonta africana*) are the largest terrestrial animals on Earth.
Adult males average 5–6 tonnes and can exceed 7 tonnes — roughly the weight of a loaded
school bus. Their closest rival, the Asian elephant, averages 3–5 tonnes.

## Why Size Matters for Survival

Large body mass helps elephants regulate temperature in sub-Saharan heat by reducing the
surface-area-to-volume ratio. Their outsized ears — up to 2 square metres — act as
radiators, pumping warm blood through a network of blood vessels to dissipate heat.

## Diet and the Energy Cost of Being Big

Maintaining that mass requires 150–300 kg of vegetation per day. Elephants spend up to
18 hours foraging, which in turn shapes savanna ecosystems: they uproot trees, clear
shrubland, and create water holes used by dozens of other species.

## Key Takeaways

- African bush elephants average 5–6 tonnes, making them the heaviest land animals.
- Large size is an adaptation for thermoregulation and resource competition.
- Their feeding behaviour makes them keystone species in savanna ecosystems.
```

---

## Weak output

**Why it fails:** generic title, fabricated percentage, mock-source URL in body, only one heading.

```
title: All About Elephants
slug: all-about-elephants-guide-2024
meta_description: Elephants are amazing animals. Learn everything about them in this guide.
seo_keywords: [elephants, animals, wildlife, nature]

## Introduction

Elephants are one of the most fascinating animals in the world. According to a recent study,
elephants are 300% more social than previously thought [source: mock-source-1.example.dev].
They are very big and eat a lot. In this article we will cover everything you need to know.

In conclusion, elephants are amazing and you should learn more about them.
```

**Issues to flag:**
- Title is generic (≤20 chars, no keyword specificity)
- Slug includes unnecessary year
- Meta description is vague and under 80 chars
- Only one heading (`## Introduction` — a forbidden generic name)
- "300% more social" is a fabricated statistic with a mock URL citation in body text
- Body is under 100 words
- Conclusion introduces no real takeaway
