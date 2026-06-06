"""Recommendation candidate extractor.

Extracts named product/entity candidates from evidence items,
scores each for usability, and captures nearby sensory/contextual detail.

Permission class: read_only
All operations are deterministic — no LLM calls.

A usable recommendation candidate requires:
  - named product/entity
  - appears in a high or medium quality source, OR in 2+ sources
  - has at least one supporting context or sensory term
Low-quality-only single-source mentions are marked low_confidence and not usable.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel

from blogagent.workflow.query_contract import QueryContract
from blogagent.workflow.state import EvidenceItem

# ---------------------------------------------------------------------------
# Sensory / context term lists
# ---------------------------------------------------------------------------

_SCENT_TERMS: frozenset[str] = frozenset(
    {
        "notes",
        "base note",
        "top note",
        "heart note",
        "sillage",
        "longevity",
        "projection",
        "dry down",
        "scent family",
        "floral",
        "woody",
        "oriental",
        "fresh",
        "citrus",
        "musk",
        "amber",
        "oud",
        "spicy",
        "sweet",
        "powdery",
        "aquatic",
        "green",
        "leather",
        "sandalwood",
        "vetiver",
        "neroli",
        "rose",
        "jasmine",
        "orange blossom",
        "bergamot",
        "vanilla",
        "patchouli",
        "iris",
        "coconut",
        "marine",
        "clean",
        "earthy",
        "fruity",
        "musky",
        "smoky",
        "sea salt",
        "tiare",
        "ylang-ylang",
    }
)

_SUITABILITY_TERMS: frozenset[str] = frozenset(
    {
        "summer",
        "heat",
        "warm weather",
        "date night",
        "long-lasting",
        "budget",
        "overall",
        "chic",
        "light",
        "beach",
        "evening",
        "tested",
        "reviewed",
        "editor",
        "expert",
        "best for",
        "perfect for",
        "ideal for",
        "great for",
        "recommended",
        "award",
        "classic",
        "signature",
        "everyday",
        "office",
        "spring",
        "fall",
        "winter",
        "casual",
        "romantic",
        "daytime",
        "nighttime",
        "all-day",
        "office-friendly",
        "summer heat",
        "warm-weather",
        "affordable",
        "luxury",
        "picks",
        "recommendations",
        "under",
        "buying guide",
    }
)

# Stop-words that are never product names on their own
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "and",
        "or",
        "but",
        "with",
        "for",
        "from",
        "into",
        "onto",
        "about",
        "over",
        "under",
        "after",
        "before",
        "between",
        "during",
        "without",
        "through",
        "by",
        "at",
        "to",
        "in",
        "of",
        "our",
        "your",
        "their",
        "its",
        "all",
        "most",
        "some",
        "any",
        "when",
        "where",
        "which",
        "who",
        "what",
        "how",
        "if",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "best",
        "top",
        "good",
        "great",
        "well",
        "new",
        "old",
        "first",
        "last",
        "more",
        "most",
        "less",
        "few",
        "many",
        "much",
        "very",
        "too",
        "also",
        "just",
        "so",
        "then",
        "than",
        "other",
        "another",
        "each",
        "every",
        "here",
        "there",
        "now",
        "as",
        "us",
        "we",
        "it",
        "he",
        "she",
        "they",
    }
)

# Known brand prefixes for beauty/fragrance/lifestyle
_BRAND_PREFIXES: tuple[str, ...] = (
    "chanel",
    "dior",
    "gucci",
    "ysl",
    "yves saint laurent",
    "tom ford",
    "lancôme",
    "lancome",
    "armani",
    "versace",
    "burberry",
    "givenchy",
    "marc jacobs",
    "jo malone",
    "byredo",
    "le labo",
    "diptyque",
    "maison margiela",
    "aesop",
    "mugler",
    "hermes",
    "hermès",
    "prada",
    "valentino",
    "dolce & gabbana",
    "bulgari",
    "bvlgari",
    "calvin klein",
    "ralph lauren",
    "hugo boss",
    "clarins",
    "nars",
    "mac ",
    "charlotte tilbury",
    "rare beauty",
    "fenty beauty",
    "ouai",
    "olaplex",
    "cetaphil",
    "cerave",
    "la roche-posay",
    "tatcha",
    "drunk elephant",
    "paula's choice",
    "kilian",
    "by kilian",
    "glossier",
    "sol de janeiro",
    "guerlain",
    "maison francis kurkdjian",
    "giorgio armani",
    "tissot",
    "seiko",
    "hamilton",
    "orient",
    "citizen",
    "longines",
    "sony",
    "bose",
    "apple",
    "samsonite",
    "away",
    "travelpro",
    "fujifilm",
    "canon",
    "herman miller",
    "steelcase",
)

_BRAND_ONLY_NAMES: frozenset[str] = frozenset(
    {
        "kilian",
        "by kilian",
        "glossier",
        "sol de janeiro",
        "tom ford",
        "chanel",
        "dior",
        "gucci",
        "guerlain",
        "byredo",
        "jo malone",
        "jo malone london",
        "armani",
        "giorgio armani",
        "ysl",
        "yves saint laurent",
        "maison francis kurkdjian",
        "dolce & gabbana",
        "ouai",
        "prada",
        "versace",
    }
)

_PRODUCT_SIGNAL_TERMS: frozenset[str] = frozenset(
    {
        "eau",
        "parfum",
        "perfume",
        "cologne",
        "fragrance",
        "toilette",
        "edp",
        "edt",
        "absolute",
        "absolu",
        "intense",
        "elixir",
        "no.",
        "no",
        "light blue",
        "soleil",
        "blanc",
        "terracotta",
        "aqua",
        "universalis",
        "melrose",
        "ocean",
        "gioia",
        "wood sage",
        "sea salt",
        "replica",
        "beach walk",
        "philosykos",
    }
)

# Generic headings that are NOT product recommendation names
_NON_RECOMMENDATION_HEADINGS: frozenset[str] = frozenset(
    {
        "quick picks",
        "how we chose",
        "how we tested",
        "buying tips",
        "buying or choosing tips",
        "buying guide",
        "final takeaway",
        "conclusion",
        "sources",
        "references",
        "citations",
        "further reading",
        "introduction",
        "overview",
        "about",
        "summary",
        "key takeaways",
        "editor's note",
        "methodology",
        "what to look for",
        "faq",
        "frequently asked questions",
        "the bottom line",
        "our top",
        "choosing your",
        "summer parfums",
        "summer perfumes",
        "signature scent",
        "editor-vetted",
        "best summer",
        "best options",
        "top summer",
        "scent categories",
        "fragrance wardrobe",
        "recommendations",
        "guide",
        "affordable luxury watches",
        "best luxury watches",
        "top picks",
        "what makes a great watch",
        "shop now",
        "on sale",
        "luxury brands",
        "watch brands",
        "men's watches",
        "under $500",
        "what was searched",
        "validated candidates found",
        "why not publish-ready",
        "why this is not publish-ready",
        "what evidence is missing",
        "suggested next search or refinement",
    }
)

_NON_RECOMMENDATION_SUBSTRINGS: tuple[str, ...] = (
    "how we chose",
    "our top",
    "quick picks",
    "choosing your",
    "final takeaway",
    "buying tips",
    "buying or choosing tips",
    "conclusion",
    "introduction",
    "sources",
    "source",
    "recommendations",
    "guide",
    "summer parfums",
    "summer perfumes",
    "signature scent",
    "editor-vetted",
    "best summer",
    "best options",
    "top summer",
    "scent categories",
    "fragrance wardrobe",
    # Editorial heading patterns common in non-fragrance domains
    "navigating",
    "spotlight on",
    "our approach",
    "the shifting",
    "opportunities in",
    "players for",
    "landscape for",
    "identifying energy",
    "identifying ai",
    "key energy",
    "key ai",
    "for student success",
    "affordable luxury watches",
    "best luxury watches",
    "top picks",
    "what makes a great watch",
    "final takeaway",
    "shop now",
    "on sale",
    "luxury brands",
    "watch brands",
    "men's watches",
    "under $",
    "what was searched",
    "validated candidates found",
    "candidates found",
    "not publish-ready",
    "what evidence is missing",
    "suggested next search",
)

# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class RecommendationCandidate(BaseModel):
    name: str
    normalized_name: str = ""
    entity_type: Literal[
        "specific_product",
        "brand",
        "brand_cluster",
        "section_heading",
        "category",
        "source_title",
        "source_nav",
        "unknown",
    ] = "unknown"
    domain: str = "general"
    is_specific_product: bool = False
    source_urls: list[str]
    source_titles: list[str] = []
    source_quality: Literal["high", "medium", "low"]
    evidence_terms: list[str] = []
    supported_context: list[str]
    sensory_terms: list[str]
    usable: bool
    confidence: Literal["high", "medium", "low"] = "medium"
    reason: str
    rejection_reason: Optional[str] = None
    low_confidence: bool = False


class RecommendationAudit(BaseModel):
    article_recommendations_count: int
    grounded_recommendations_count: int
    invalid_recommendations: list[str] = []
    unsupported_recommendations: list[str] = []
    brand_only_recommendations: list[str] = []
    section_heading_false_positives: list[str] = []
    model_introduced_source_grounded: list[str] = []
    passes: bool


class ArticleRecommendation(BaseModel):
    """A named recommendation extracted from the final article markdown."""

    name: str
    section_title: str = ""
    quick_pick_label: str | None = None
    best_for: str | None = None
    why_it_works: str | None = None
    source_urls: list[str] = []
    evidence_terms: list[str] = []


class RecommendationGrounding(BaseModel):
    """Result of matching an article recommendation to source evidence."""

    name: str
    matched: bool
    confidence: Literal["high", "medium", "low"]
    matched_sources: list[str] = []
    support_reason: str
    source_quality: Literal["high", "medium", "low"] = "medium"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_candidate_entity(
    name: str,
    query_contract: QueryContract,
    *,
    source_title: str = "",
) -> tuple[str, bool, Optional[str]]:
    """Classify a candidate name against the query contract."""
    raw = _clean_rec_name(name)
    norm = normalize_recommendation_name(raw)
    if not norm:
        return "unknown", False, "empty candidate"

    if _looks_like_url_or_citation(raw):
        return "unknown", False, "URL/domain/citation artifact"

    if source_title and norm == normalize_recommendation_name(source_title):
        return "source_title", False, "source titles do not count"

    if _is_generic_heading(raw):
        entity = "section_heading" if _looks_like_heading(raw) else "category"
        return entity, False, "section headings/category phrases do not count"

    if query_contract.domain == "beauty_fragrance":
        asks_for_brand = query_contract.answer_entity_type == "fragrance_brand"
        if norm in _BRAND_ONLY_NAMES:
            if asks_for_brand:
                return "brand", True, None
            return "brand", False, "brand-only names do not count as product recommendations"

        if _is_source_title_phrase(raw):
            return "source_title", False, "source titles do not count"

        if _is_category_phrase(raw):
            return "category", False, "category phrases do not count"

        if _looks_like_specific_fragrance_product(raw):
            return "specific_product", True, None

        return "unknown", False, "not a specific fragrance product"

    # For all other recommendation domains, delegate to the domain adapter.
    # This ensures domain-specific rules (e.g., FinanceAdapter, SoftwareToolsAdapter)
    # are applied consistently during both extraction and auditing.
    if query_contract.task_type == "recommendation":
        from blogagent.tools.domain_adapters import get_adapter  # noqa: PLC0415

        adapter = get_adapter(query_contract.domain)
        if adapter.is_valid_entity(raw, query_contract):
            entity_type = adapter.classify_entity_type(raw, query_contract)
            if entity_type == "category":
                return "category", True, None
            return "specific_product", True, None
        entity_type = adapter.classify_entity_type(raw, query_contract)
        rejection = adapter.get_rejection_reason(raw, query_contract)
        classified_type = entity_type if entity_type != "unknown" else "unknown"
        reason = rejection or "not a valid recommendation item for this contract"
        return classified_type, False, reason

    return "unknown", False, "not a valid recommendation item for this contract"


def extract_candidates_from_sources(
    sources: list,
    evidence_table: list[EvidenceItem],
    query_contract: QueryContract,
    source_quality_scores: list[dict],
) -> list[RecommendationCandidate]:
    """Extract contract-classified recommendation candidates before drafting."""
    quality_map: dict[str, str] = {
        sq.get("url", ""): sq.get("quality", "medium")
        for sq in source_quality_scores
        if sq.get("url")
    }
    title_map: dict[str, str] = {}
    text_packets: list[tuple[str, str, str]] = []

    for item in evidence_table:
        if _is_placeholder(item.fact):
            continue
        title_map[item.source_url] = item.source_title
        text_packets.append((item.source_url, item.source_title, item.fact))

    for source in sources or []:
        url = getattr(source, "url", "") if not isinstance(source, dict) else source.get("url", "")
        title = (
            getattr(source, "title", "")
            if not isinstance(source, dict)
            else source.get("title", "")
        )
        text = (
            getattr(source, "extracted_text", "")
            if not isinstance(source, dict)
            else source.get("extracted_text", "")
        )
        if url and title:
            title_map[url] = title
            text_packets.append((url, title, title))
        if text and not _is_placeholder(text):
            text_packets.append((url, title, text[:2000]))

    name_data: dict[str, dict] = {}
    for url, title, text in text_packets:
        quality = quality_map.get(url, "medium")
        names = _extract_names_from_text(text)
        sensory = _extract_scent_terms(text)
        context = _extract_context_terms(text)
        for name in names:
            name_norm = normalize_recommendation_name(name)
            title_norm = normalize_recommendation_name(title)
            entity_type, is_specific, rejection = classify_candidate_entity(
                name,
                query_contract,
                source_title=title if name_norm == title_norm else "",
            )
            norm = name_norm
            if not norm:
                continue
            if norm not in name_data:
                name_data[norm] = {
                    "name": name,
                    "source_urls": [],
                    "source_titles": [],
                    "source_quality": quality,
                    "sensory_terms": set(),
                    "supported_context": set(),
                    "entity_type": entity_type,
                    "is_specific_product": is_specific,
                    "rejection_reason": rejection,
                }
            entry = name_data[norm]
            if len(name) > len(entry["name"]):
                entry["name"] = name
            if url and url not in entry["source_urls"]:
                entry["source_urls"].append(url)
            if title and title not in entry["source_titles"]:
                entry["source_titles"].append(title)
            if quality == "high":
                entry["source_quality"] = "high"
            elif quality == "medium" and entry["source_quality"] == "low":
                entry["source_quality"] = "medium"
            entry["sensory_terms"].update(sensory)
            entry["supported_context"].update(context)
            if is_specific:
                entry["entity_type"] = entity_type
                entry["is_specific_product"] = True
                entry["rejection_reason"] = None

    candidates: list[RecommendationCandidate] = []
    for norm, data in name_data.items():
        source_quality: Literal["high", "medium", "low"] = data["source_quality"]
        is_low_confidence = source_quality == "low" and len(data["source_urls"]) < 2
        evidence_terms = sorted(data["sensory_terms"])
        supported_context = sorted(data["supported_context"])
        contract_valid = bool(data["is_specific_product"])
        usable, reason = _decide_usable(
            source_quality=source_quality,
            supported_context=supported_context,
            sensory_terms=evidence_terms,
            is_low_confidence=is_low_confidence,
        )
        usable = bool(usable and contract_valid)
        rejection = data["rejection_reason"] if not usable else None
        if contract_valid and is_low_confidence:
            rejection = "low-confidence source support"
        if not contract_valid and not rejection:
            rejection = "candidate does not satisfy query contract"
        confidence: Literal["high", "medium", "low"]
        if source_quality == "high" and usable:
            confidence = "high"
        elif usable:
            confidence = "medium"
        else:
            confidence = "low"
        candidates.append(
            RecommendationCandidate(
                name=data["name"],
                normalized_name=norm,
                entity_type=data["entity_type"],
                domain=query_contract.domain,
                is_specific_product=bool(data["is_specific_product"]),
                source_urls=data["source_urls"],
                source_titles=data["source_titles"],
                source_quality=source_quality,
                evidence_terms=evidence_terms,
                supported_context=supported_context,
                sensory_terms=evidence_terms,
                usable=usable,
                confidence=confidence,
                reason=reason if usable else (rejection or reason),
                rejection_reason=rejection,
                low_confidence=is_low_confidence,
            )
        )

    return sorted(candidates, key=lambda c: (not c.usable, c.name.lower()))


def extract_recommendations_from_evidence(
    evidence_items: list[EvidenceItem],
    source_quality_scores: list[dict],
    topic: str = "",
) -> list[RecommendationCandidate]:
    """Extract named recommendation candidates from evidence items.

    Returns candidates with source quality, context, and usability data.
    Mock/placeholder evidence yields no candidates — correct for mock mode.
    """
    from blogagent.workflow.query_contract import build_query_contract  # noqa: PLC0415

    contract = build_query_contract(
        topic or "recommendations",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    if topic:
        return extract_candidates_from_sources([], evidence_items, contract, source_quality_scores)

    quality_map: dict[str, str] = {
        sq.get("url", ""): sq.get("quality", "medium")
        for sq in source_quality_scores
        if sq.get("url")
    }

    # Accumulate per-name data across all evidence items
    name_data: dict[str, dict] = {}

    for item in evidence_items:
        if _is_placeholder(item.fact):
            continue

        quality = quality_map.get(item.source_url, "medium")
        names = _extract_names_from_text(item.fact)
        sensory = _extract_scent_terms(item.fact)
        context = _extract_context_terms(item.fact)

        for name in names:
            if name not in name_data:
                name_data[name] = {
                    "source_urls": [],
                    "source_quality": quality,
                    "sensory_terms": set(),
                    "supported_context": set(),
                }
            entry = name_data[name]
            if item.source_url not in entry["source_urls"]:
                entry["source_urls"].append(item.source_url)
            # Upgrade quality if this source is better
            if quality == "high":
                entry["source_quality"] = "high"
            elif quality == "medium" and entry["source_quality"] == "low":
                entry["source_quality"] = "medium"
            entry["sensory_terms"].update(sensory)
            entry["supported_context"].update(context)

    candidates: list[RecommendationCandidate] = []
    for name, data in name_data.items():
        source_quality: Literal["high", "medium", "low"] = data["source_quality"]
        is_low_confidence = source_quality == "low" and len(data["source_urls"]) < 2
        usable, reason = _decide_usable(
            source_quality=source_quality,
            supported_context=list(data["supported_context"]),
            sensory_terms=list(data["sensory_terms"]),
            is_low_confidence=is_low_confidence,
        )
        candidates.append(
            RecommendationCandidate(
                name=name,
                normalized_name=normalize_recommendation_name(name),
                entity_type="specific_product",
                domain="general",
                is_specific_product=True,
                source_urls=data["source_urls"],
                source_titles=[],
                source_quality=source_quality,
                evidence_terms=sorted(data["sensory_terms"]),
                supported_context=sorted(data["supported_context"]),
                sensory_terms=sorted(data["sensory_terms"]),
                usable=usable,
                confidence="low" if is_low_confidence else source_quality,
                reason=reason,
                rejection_reason=None if usable else reason,
                low_confidence=is_low_confidence,
            )
        )

    return candidates


def build_candidates_summary(candidates: list[RecommendationCandidate]) -> dict:
    """Build a compact summary dict safe for API responses."""
    usable = [c for c in candidates if c.usable]
    low_conf = [c for c in candidates if c.low_confidence]
    rejected = [c for c in candidates if not c.usable]
    return {
        "evidence_candidates_count": len(candidates),
        "usable_count": len(usable),
        "low_confidence_count": len(low_conf),
        "names": [c.name for c in usable],
        "rejected_count": len(rejected),
        "rejected_names": [c.name for c in rejected[:10]],
    }


def build_grounded_candidates_summary(
    candidates: list[RecommendationCandidate],
    groundings: list[RecommendationGrounding],
) -> dict:
    """Build summary dict that combines pre-draft candidates and post-article grounding.

    When post-article grounding is available it takes precedence for usable_count,
    since the article is the ground truth and evidence matching is the proof layer.
    """
    evidence_usable = [c for c in candidates if c.usable]
    low_conf = [c for c in candidates if c.low_confidence]

    article_count = len(groundings)
    grounded = [g for g in groundings if g.matched]
    unmatched = [g.name for g in groundings if not g.matched]

    usable_count = len(evidence_usable) if candidates else len(grounded)
    names = [c.name for c in evidence_usable] if candidates else [g.name for g in grounded]

    return {
        "evidence_candidates_count": len(candidates),
        "article_recommendations_count": article_count,
        "grounded_recommendations_count": len(grounded),
        "usable_count": usable_count,
        "low_confidence_count": len(low_conf),
        "unmatched_names": unmatched,
        "names": names,
    }


# ---------------------------------------------------------------------------
# Article recommendation extraction
# ---------------------------------------------------------------------------


def extract_recommendations_from_article(markdown: str) -> list[ArticleRecommendation]:
    """Extract named recommendations from final article markdown.

    Detects:
    - Quick Picks bullets: ``- **Best X:** Product Name`` or ``- Product Name``
    - Numbered/label H2–H3 headings: ``## 1. Product`` / ``### Best X: Product``
    - Bold ``**Name**: Product`` fields inside recommendation sections
    - Linked names ``[Product](url)`` near recommendation sections

    Excludes generic section headings (How We Chose, Buying Tips, etc.) and
    deduplicates by normalised name.
    """
    # Strip the sources section to avoid counting source list entries
    body = re.split(
        r"\n#{1,3}\s*(?:Sources?|References?|Citations?|Further Reading)\s*\n",
        markdown,
        flags=re.IGNORECASE,
    )[0]

    recs: list[ArticleRecommendation] = []
    norm_to_index: dict[str, int] = {}

    def _add(rec: ArticleRecommendation) -> None:
        """Add a recommendation, merging metadata if the normalised name already exists."""
        norm = normalize_recommendation_name(rec.name)
        if not norm:
            return
        if norm in norm_to_index:
            # Merge metadata from this entry into the existing one (prefer non-None values)
            existing = recs[norm_to_index[norm]]
            if rec.best_for and not existing.best_for:
                recs[norm_to_index[norm]] = existing.model_copy(update={"best_for": rec.best_for})
                existing = recs[norm_to_index[norm]]
            if rec.why_it_works and not existing.why_it_works:
                recs[norm_to_index[norm]] = existing.model_copy(
                    update={"why_it_works": rec.why_it_works}
                )
                existing = recs[norm_to_index[norm]]
            if rec.quick_pick_label and not existing.quick_pick_label:
                recs[norm_to_index[norm]] = existing.model_copy(
                    update={"quick_pick_label": rec.quick_pick_label}
                )
                existing = recs[norm_to_index[norm]]
            if rec.source_urls:
                merged_urls = list(dict.fromkeys(existing.source_urls + rec.source_urls))
                recs[norm_to_index[norm]] = existing.model_copy(update={"source_urls": merged_urls})
            if rec.evidence_terms:
                merged_terms = list(dict.fromkeys(existing.evidence_terms + rec.evidence_terms))
                recs[norm_to_index[norm]] = existing.model_copy(
                    update={"evidence_terms": merged_terms}
                )
        else:
            norm_to_index[norm] = len(recs)
            recs.append(rec)

    # --- 1. Quick Picks section ---
    qp_m = re.search(
        r"#{1,3}\s*Quick\s*Picks?\s*\n(.*?)(?=\n#{1,3}|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if qp_m:
        section_text = qp_m.group(1)
        for line in section_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Pattern: "- **Best X:** Product Name — description"
            m = re.match(
                r"^[-*]\s+\*\*([^*:]+?)[:]\*\*\s+([^—–\n]+?)(?:\s*[—–]|$)",
                line,
            )
            if m:
                label = m.group(1).strip()
                name_raw = m.group(2).strip(" .,;:*")
                name = _clean_rec_name(name_raw)
                if name and _looks_like_product_name(name):
                    _add(ArticleRecommendation(name=name, quick_pick_label=label))
                continue

            # Pattern: "- **Best X:** Product Name" (no dash after)
            m = re.match(r"^[-*]\s+\*\*([^*:]+?)[:]\*\*\s+(.+)", line)
            if m:
                label = m.group(1).strip()
                name_raw = m.group(2).split("—")[0].split("–")[0].strip(" .,;:*")
                name = _clean_rec_name(name_raw)
                if name and _looks_like_product_name(name):
                    _add(ArticleRecommendation(name=name, quick_pick_label=label))
                continue

            # Pattern: "- Product Name — description" or "- Product Name"
            m = re.match(r"^[-*]\s+(.+?)(?:\s*[—–:]|\s*$)", line)
            if m:
                name_raw = m.group(1).strip(" .,;:*[]")
                # Strip markdown links: [Name](url) → Name
                name_raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", name_raw).strip()
                name = _clean_rec_name(name_raw)
                if (
                    name
                    and _looks_like_product_name(name)
                    and not _is_generic_heading(name)
                    and not _is_source_link_text(name)
                ):
                    _add(ArticleRecommendation(name=name))
                continue

            # Pattern: "1. Product Name — description"
            m = re.match(r"^\d+[.)]\s+(.+?)(?:\s*[—–:]|\s*$)", line)
            if m:
                name_raw = m.group(1).strip(" .,;:*[]")
                name_raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", name_raw).strip()
                name = _clean_rec_name(name_raw)
                if (
                    name
                    and _looks_like_product_name(name)
                    and not _is_generic_heading(name)
                    and not _is_source_link_text(name)
                ):
                    _add(ArticleRecommendation(name=name))

    # --- 2. Recommendation section headings ---
    # Split body into sections by H2/H3 headings
    sections = re.split(r"\n(#{2,3}\s+.+)", body)
    # sections is alternating: [text, heading, text, heading, text, ...]
    i = 1
    while i < len(sections):
        heading_line = sections[i].strip()
        section_body = sections[i + 1] if i + 1 < len(sections) else ""
        i += 2

        name, label = _parse_heading_as_recommendation(heading_line)
        if name is None or _is_generic_heading(name):
            continue

        # Extract metadata from section body
        best_for = _extract_field(section_body, ("Best for", "Best For", "best for"))
        why = _extract_field(section_body, ("Why it works", "Why It Works", "Why", "why it works"))
        urls = re.findall(r"\(https?://[^\s)]+\)", section_body)
        urls = [u.strip("()") for u in urls]
        terms = _extract_scent_terms(section_body) + _extract_context_terms(section_body)

        _add(
            ArticleRecommendation(
                name=name,
                section_title=heading_line,
                quick_pick_label=label,
                best_for=best_for,
                why_it_works=why,
                source_urls=urls,
                evidence_terms=list(set(terms)),
            )
        )

    # --- 3. **Name**: Product Name fields (fallback for unusual formats) ---
    if not recs:
        for m in re.finditer(r"\*\*Name\*\*[:\s]+([^\n*]{3,60})", body):
            name = _clean_rec_name(m.group(1))
            if name and _looks_like_product_name(name):
                _add(ArticleRecommendation(name=name))

    return recs


def normalize_recommendation_name(name: str) -> str:
    """Normalise a product name for deduplication and matching.

    Strips markdown link syntax, bold/italic markers, surrounding punctuation,
    collapses whitespace, and removes common leading articles.
    """
    name = name.strip()
    # Strip markdown links: [Name](url) → Name
    name = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", name)
    name = name.lower()
    # Strip markdown bold/italic markers
    name = re.sub(r"[*_`]", "", name)
    # Strip surrounding brackets / parentheses
    name = re.sub(r"[\[\](){}]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Remove leading articles
    for prefix in ("the ", "a ", "an "):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    return name


def match_article_recommendations_to_evidence(
    article_recs: list[ArticleRecommendation],
    evidence_candidates: list[dict],
    source_quality_scores: list[dict],
    evidence_table: list | None = None,
    source_scores: list | None = None,
) -> list[RecommendationGrounding]:
    """Match final article recommendations to source evidence.

    Matching hierarchy:
    1. Exact normalised name match against evidence candidates → high confidence
    2. Partial/containment match against candidate names → medium confidence
    3. Match against evidence table facts or source titles → medium confidence
    4. No match → low confidence / unmatched

    Returns a RecommendationGrounding for every article recommendation.
    """
    # Build quality map for source URLs
    quality_map: dict[str, str] = {
        sq.get("url", ""): sq.get("quality", "medium")
        for sq in source_quality_scores
        if sq.get("url")
    }

    # Normalised candidate names for fast lookup
    cand_norm: list[tuple[str, dict]] = [
        (normalize_recommendation_name(c.get("name", "")), c)
        for c in evidence_candidates
        if c.get("name")
    ]

    # Normalised source titles
    src_titles: list[tuple[str, str]] = []
    if source_scores:
        for s in source_scores:
            title = s.title if hasattr(s, "title") else s.get("title", "")
            url = s.url if hasattr(s, "url") else s.get("url", "")
            if title:
                src_titles.append((normalize_recommendation_name(title), url))

    # Evidence table facts for fallback matching
    evidence_texts: list[str] = []
    if evidence_table:
        for item in evidence_table:
            fact = item.fact if hasattr(item, "fact") else item.get("fact", "")
            evidence_texts.append(fact.lower())

    groundings: list[RecommendationGrounding] = []

    for rec in article_recs:
        norm_rec = normalize_recommendation_name(rec.name)
        if not norm_rec:
            groundings.append(
                RecommendationGrounding(
                    name=rec.name,
                    matched=False,
                    confidence="low",
                    support_reason="Empty normalised name",
                )
            )
            continue

        matched_sources: list[str] = []
        confidence: Literal["high", "medium", "low"] = "low"
        matched = False
        support_reason = "No matching evidence found"
        best_quality: Literal["high", "medium", "low"] = "medium"

        # 1. Exact match against candidate names
        for cand_n, cand in cand_norm:
            if norm_rec == cand_n:
                matched = True
                confidence = "high"
                matched_sources.extend(cand.get("source_urls", []))
                # Source quality from best source in candidate
                cq = cand.get("source_quality", "medium")
                if cq == "high":
                    best_quality = "high"
                support_reason = f"Exact product match in evidence: {cand.get('name')}"
                break

        # 2. Containment match against candidate names
        if not matched:
            for cand_n, cand in cand_norm:
                if not cand_n:
                    continue
                if norm_rec in cand_n or cand_n in norm_rec:
                    matched = True
                    confidence = "medium"
                    matched_sources.extend(cand.get("source_urls", []))
                    cq = cand.get("source_quality", "medium")
                    if cq == "high" and best_quality != "high":
                        best_quality = "high"
                    support_reason = f"Partial product name match in evidence: {cand.get('name')}"
                    break

        # 3. Brand prefix match (first word of rec matches first word of candidate)
        if not matched:
            rec_words = norm_rec.split()
            for cand_n, cand in cand_norm:
                cand_words = cand_n.split()
                if (
                    rec_words
                    and cand_words
                    and rec_words[0] == cand_words[0]
                    and len(set(rec_words) & set(cand_words)) >= 2
                ):
                    matched = True
                    confidence = "medium"
                    matched_sources.extend(cand.get("source_urls", []))
                    support_reason = f"Brand/product word overlap with evidence: {cand.get('name')}"
                    break

        # 4. Match against source title or evidence table text
        if not matched:
            for et in evidence_texts:
                if norm_rec in et or any(w in et for w in norm_rec.split() if len(w) > 4):
                    matched = True
                    confidence = "medium"
                    support_reason = "Product name found in evidence table facts"
                    break

        # 5. Match against source titles
        if not matched:
            for src_norm, src_url in src_titles:
                if norm_rec in src_norm or any(
                    w in src_norm for w in norm_rec.split() if len(w) > 4
                ):
                    matched = True
                    confidence = "low"
                    matched_sources.append(src_url)
                    support_reason = "Product name found in source title"
                    break

        # 6. Article citation URLs as evidence (if section has linked sources)
        if not matched and rec.source_urls:
            url_qualities = [quality_map.get(u, "medium") for u in rec.source_urls]
            if any(q in ("high", "medium") for q in url_qualities):
                matched = True
                confidence = "medium"
                matched_sources.extend(rec.source_urls)
                best_quality = max(  # type: ignore[assignment]
                    url_qualities, key=lambda q: {"high": 2, "medium": 1, "low": 0}.get(q, 0)
                )
                support_reason = "Recommendation section contains editorial source citations"

        groundings.append(
            RecommendationGrounding(
                name=rec.name,
                matched=matched,
                confidence=confidence,
                matched_sources=list(dict.fromkeys(matched_sources)),
                support_reason=support_reason,
                source_quality=best_quality,
            )
        )

    return groundings


def audit_article_recommendations(
    markdown: str,
    allowed_candidates: list[dict],
    query_contract: QueryContract,
    evidence_table: list[EvidenceItem],
    source_quality_scores: list[dict],
    source_scores: list | None = None,
) -> RecommendationAudit:
    """Audit final article recommendations against the validated candidate table."""
    article_recs = extract_recommendations_from_article(markdown)
    allowed_norms = {
        c.get("normalized_name") or normalize_recommendation_name(c.get("name", ""))
        for c in allowed_candidates
        if c.get("usable", True) and c.get("name")
    }
    allowed_norms.discard("")

    groundings = match_article_recommendations_to_evidence(
        article_recs=article_recs,
        evidence_candidates=allowed_candidates,
        source_quality_scores=source_quality_scores,
        evidence_table=evidence_table,
        source_scores=source_scores,
    )
    grounded_by_name = {normalize_recommendation_name(g.name): g for g in groundings}

    invalid: list[str] = []
    unsupported: list[str] = []
    brand_only: list[str] = []
    section_false: list[str] = []
    introduced_grounded: list[str] = []
    grounded_count = 0

    for rec in article_recs:
        norm = normalize_recommendation_name(rec.name)
        entity_type, is_specific, rejection = classify_candidate_entity(rec.name, query_contract)
        grounding = grounded_by_name.get(norm)
        is_allowed = norm in allowed_norms
        is_grounded = bool(grounding and grounding.matched)

        if entity_type == "brand" and not is_specific:
            brand_only.append(rec.name)
            invalid.append(rec.name)
            continue
        if entity_type in ("section_heading", "category", "source_title"):
            section_false.append(rec.name)
            invalid.append(rec.name)
            continue
        if rejection and not is_specific:
            invalid.append(rec.name)
            continue
        if not is_allowed:
            if is_grounded and is_specific:
                introduced_grounded.append(rec.name)
            else:
                unsupported.append(rec.name)
                continue
        if is_grounded:
            grounded_count += 1

    passes = (
        bool(article_recs)
        and not invalid
        and not unsupported
        and not brand_only
        and not section_false
    )
    return RecommendationAudit(
        article_recommendations_count=len(article_recs),
        grounded_recommendations_count=grounded_count,
        invalid_recommendations=list(dict.fromkeys(invalid)),
        unsupported_recommendations=list(dict.fromkeys(unsupported)),
        brand_only_recommendations=list(dict.fromkeys(brand_only)),
        section_heading_false_positives=list(dict.fromkeys(section_false)),
        model_introduced_source_grounded=list(dict.fromkeys(introduced_grounded)),
        passes=passes,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_placeholder(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return True
    lower = text.lower().strip()
    return (
        lower.startswith("information about")
        or "lorem ipsum" in lower
        or "[placeholder" in lower
        or "[insert" in lower
    )


def _is_generic_heading(name: str) -> bool:
    """Return True if the name is a generic section heading, not a product name."""
    lower = normalize_recommendation_name(name)
    return lower in _NON_RECOMMENDATION_HEADINGS or any(
        part in lower for part in _NON_RECOMMENDATION_SUBSTRINGS
    )


def _looks_like_heading(name: str) -> bool:
    lower = normalize_recommendation_name(name)
    return any(
        part in lower
        for part in (
            "how ",
            "why ",
            "what ",
            "choosing",
            "guide",
            "tips",
            "introduction",
            "conclusion",
        )
    )


def _looks_like_url_or_citation(name: str) -> bool:
    lower = name.lower()
    return (
        "http://" in lower
        or "https://" in lower
        or ".com" in lower
        or ".org" in lower
        or re.fullmatch(r"\[\d+\]|\(\d+\)", lower.strip()) is not None
    )


def _is_source_title_phrase(name: str) -> bool:
    lower = normalize_recommendation_name(name)
    return ("best" in lower or "top" in lower or "vetted" in lower or "editor" in lower) and any(
        t in lower for t in ("perfume", "parfum", "fragrance", "cologne", "scent")
    )


def _is_category_phrase(name: str) -> bool:
    lower = normalize_recommendation_name(name)
    if lower.startswith(("best options", "best perfumes", "best parfums", "best fragrances")):
        return True
    if lower in {"summer parfums", "summer perfumes", "signature scent", "fragrance wardrobe"}:
        return True
    if len(lower.split()) <= 4 and any(
        lower.endswith(t) for t in ("perfumes", "parfums", "fragrances", "scents")
    ):
        return True
    return False


def _looks_like_specific_fragrance_product(name: str) -> bool:
    lower = normalize_recommendation_name(name)
    words = lower.split()
    if len(words) < 2 or len(words) > 10:
        return False
    if lower in _BRAND_ONLY_NAMES:
        return False
    if any(signal in lower for signal in _PRODUCT_SIGNAL_TERMS):
        return True
    for brand in _BRAND_ONLY_NAMES:
        if lower.startswith(brand + " ") and len(words) > len(brand.split()):
            return True
    return False


def _is_source_link_text(name: str) -> bool:
    """Return True if the name looks like a source-link instruction rather than a product.

    Catches mock-mode source link bullets like:
    "See Mock Source 1 for specific recommendations"
    "Check the article for details"
    "Visit allure.com for recommendations"
    """
    lower = name.lower().strip()
    for prefix in ("see ", "check ", "visit ", "read ", "click ", "go to ", "find "):
        if lower.startswith(prefix):
            return True
    for suffix in (
        "for specific recommendations",
        "for recommendations",
        "for more information",
        "for details",
        "for more",
        "for info",
    ):
        if lower.endswith(suffix):
            return True
    return False


def _clean_rec_name(name: str) -> str:
    """Strip markdown formatting and extra whitespace from a recommendation name."""
    # Strip markdown links: [Name](url) → Name
    name = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", name)
    # Strip bold/italic
    name = re.sub(r"\*+", "", name)
    name = re.sub(r"_+", "", name)
    # Strip surrounding punctuation
    name = name.strip(" .,;:!?\"'`-–—[](){}")
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _parse_heading_as_recommendation(heading_line: str) -> tuple[str | None, str | None]:
    """Parse an H2/H3 heading to extract a product name and optional label.

    Returns (name, label) or (None, None) if not a recommendation heading.

    Handles patterns:
    - ``## 1. Tom Ford Soleil Blanc``  → ("Tom Ford Soleil Blanc", None)
    - ``### Best Solar Floral: Guerlain Terracotta`` →
      ("Guerlain Terracotta", "Best Solar Floral")
    - ``## Best Overall: Ouai Melrose Place``  → ("Ouai Melrose Place", "Best Overall")
    - ``## Tom Ford Soleil Blanc``  → ("Tom Ford Soleil Blanc", None)
    """
    # Strip heading markers
    heading = re.sub(r"^#{2,3}\s+", "", heading_line).strip()
    if not heading:
        return None, None

    # Pattern: "N. Product Name" (numbered)
    m = re.match(r"^\d+[.)]\s+(.+)$", heading)
    if m:
        name = _clean_rec_name(m.group(1))
        return (name, None) if name and _looks_like_product_name(name) else (None, None)

    # Pattern: "Label: Product Name" (label with colon)
    m = re.match(r"^([^:]{3,40}):\s+(.{3,80})$", heading)
    if m:
        label_part = m.group(1).strip()
        name_part = _clean_rec_name(m.group(2))
        # Check if label_part looks like a descriptive label (not a generic heading)
        label_lower = label_part.lower()
        if (
            name_part
            and _looks_like_product_name(name_part)
            and not _is_generic_heading(label_part)
            and not _is_generic_heading(name_part)
        ):
            # Detect "Best X", "Top Pick", "Why", "Caveat", etc.
            if any(
                w in label_lower
                for w in ("best", "top", "pick", "editor", "our", "perfect", "ideal")
            ):
                return name_part, label_part
            # Generic "N: Product" style where N isn't a label keyword — treat whole as name
            if _looks_like_product_name(heading):
                return _clean_rec_name(heading), None
            return name_part, label_part

    # Plain heading: whole heading is the product name
    name = _clean_rec_name(heading)
    if name and _looks_like_product_name(name) and not _is_generic_heading(name):
        return name, None

    return None, None


def _extract_field(text: str, field_names: tuple[str, ...]) -> str | None:
    """Extract the value of a bold field from text.

    Handles multiple formats:
    - ``**Best for:** value``  (colon inside bold)
    - ``**Best for**: value``  (colon after bold close)
    - ``**Best for** value``   (space after bold)
    - ``Best for: value``      (plain, not bold)
    """
    for fn in field_names:
        # Pattern 1: **Field:** value (colon INSIDE bold — most common in Gemini output)
        m = re.search(
            r"\*\*" + re.escape(fn) + r"[:\s]*\*\*\s*:?\s*([^\n*]{3,200})",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip(" .,;:")
        # Pattern 2: **Field**: value or **Field** value (colon/space outside bold)
        m = re.search(
            r"\*\*" + re.escape(fn) + r"\*\*[:\s]+([^\n*]{3,200})",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip(" .,;:")
        # Pattern 3: Field: value (plain, no bold)
        m = re.search(
            r"(?:^|\n)" + re.escape(fn) + r"[:\s]+([^\n]{3,200})",
            text,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip(" .,;:")
    return None


def _extract_names_from_text(text: str) -> list[str]:
    """Extract candidate product/brand names from a text snippet."""
    found: list[str] = []

    # Bold markdown: **Brand Name**
    for m in re.finditer(r"\*\*([A-Z][^*\n]{2,50})\*\*", text):
        name = m.group(1).strip(" .,;:")
        if _looks_like_product_name(name):
            found.append(name)

    # Numbered list: "1. Brand Name"  or "1) Brand Name"
    for m in re.finditer(
        r"^\s*\d+[.)]\s+([A-Z][^\n—–\-:,]{2,60}?)(?:\s*[—–\-:]|\s*$)",
        text,
        re.MULTILINE,
    ):
        name = m.group(1).strip(" .,;:")
        if _looks_like_product_name(name):
            found.append(name)

    # Bullet list: "- Brand Name" or "* Brand Name"
    for m in re.finditer(
        r"^\s*[-*•]\s+([A-Z][^\n—–:,]{2,60}?)(?:\s*[—–:]|\s*$)",
        text,
        re.MULTILINE,
    ):
        name = m.group(1).strip(" .,;:")
        if _looks_like_product_name(name):
            found.append(name)

    # Labeled list structures: "Best Overall: Sony WH-1000XM5".
    for m in re.finditer(
        r"(?:^|[\n.;])\s*(?:best|top|pick|affordable|budget|luxury|reviewed|tested)"
        r"[^:\n]{0,40}:\s+([A-Z][A-Za-z0-9&' .+/-]{2,60}?)(?:\s*[—–,;.]|\n|$)",
        text,
        re.IGNORECASE,
    ):
        name = m.group(1).strip(" .,;:")
        if _looks_like_product_name(name):
            found.append(name)

    # Known brand prefix scan: "Chanel Chance Eau Tendre ..."
    lower = text.lower()
    for prefix in _BRAND_PREFIXES:
        start = 0
        while True:
            idx = lower.find(prefix, start)
            if idx == -1:
                break
            # Capture up to 6 words starting from brand prefix in original case
            raw = text[idx : idx + 90]
            tokens = raw.split()[:6]
            candidate = " ".join(t.strip(".,;:!?\"'()") for t in tokens).strip()
            # Trim trailing stop words from the candidate
            candidate_words = candidate.split()
            while candidate_words and candidate_words[-1].lower() in _STOP_WORDS:
                candidate_words.pop()
            candidate = " ".join(candidate_words)
            if _looks_like_product_name(candidate):
                found.append(candidate)
            start = idx + len(prefix)

    # Comma-separated names in source titles/snippets.
    for m in re.finditer(
        r"\b([A-Z][A-Za-z]+(?:\s+[A-Z0-9][A-Za-z0-9&' .+/-]{1,24}){1,5})"
        r"(?=,|\sand\s|\.)",
        text,
    ):
        name = m.group(1).strip(" .,;:")
        if _looks_like_product_name(name):
            found.append(name)

    # Deduplicate preserving order; prefer longer/more specific names
    seen: set[str] = set()
    result: list[str] = []
    for name in found:
        key = name.lower().strip()
        if key not in seen and len(name) >= 4:
            seen.add(key)
            result.append(name)

    return result


def _looks_like_product_name(name: str) -> bool:
    """Return True if the string looks like a product/brand name."""
    name = name.strip()
    if len(name) < 3 or len(name) > 80:
        return False
    words = name.split()
    # Must have at least one capitalized word
    if not any(w and w[0].isupper() for w in words):
        return False
    # Must have at least one non-stop-word token
    clean = [w.lower().strip(".,;:!?\"'") for w in words]
    meaningful = [w for w in clean if w and w not in _STOP_WORDS]
    if not meaningful:
        return False
    # Reject strings that start with common generic heading words
    lower = name.lower()
    for skip in (
        "how to",
        "why ",
        "what ",
        "when ",
        "the best",
        "best ",
        "top ",
        "introduction",
        "overview",
        "conclusion",
        "section",
        "part ",
        "chapter ",
        # Editorial verbs that signal article headings, not product names
        "navigating",
        "exploring",
        "understanding the",
        "examining",
        "leveraging",
        "maximizing",
        "unlocking",
        "harnessing",
        "identifying",
        "spotlight on",
        "our approach",
    ):
        if lower.startswith(skip):
            return False
    return True


def _extract_scent_terms(text: str) -> list[str]:
    lower = text.lower()
    return [t for t in _SCENT_TERMS if t in lower]


def _extract_context_terms(text: str) -> list[str]:
    lower = text.lower()
    return [t for t in _SUITABILITY_TERMS if t in lower]


def _decide_usable(
    source_quality: str,
    supported_context: list[str],
    sensory_terms: list[str],
    is_low_confidence: bool,
) -> tuple[bool, str]:
    if is_low_confidence:
        return False, "Low-quality source only (single source) — not usable as core pick"
    has_context = bool(supported_context) or bool(sensory_terms)
    if source_quality in ("high", "medium"):
        if has_context:
            return True, (
                f"Named in {source_quality}-quality source with "
                f"{len(supported_context)} context / {len(sensory_terms)} sensory term(s)"
            )
        # High/medium source, no context — weakly usable
        return True, f"Named in {source_quality}-quality source (limited supporting detail)"
    # Low quality but multi-source
    if has_context:
        return True, "Named in multiple sources with supporting context (low-quality only)"
    return False, "Low-quality sources only with no supporting context"
