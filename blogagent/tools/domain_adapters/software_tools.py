"""Software/Tools domain adapter.

Valid: named apps, platforms, tools, software products.
Invalid: generic category phrases like 'productivity tools', section headings.

Permission class: read_only
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blogagent.tools.domain_adapters.base import DomainAdapter, _normalize

if TYPE_CHECKING:
    from blogagent.workflow.query_contract import QueryContract

# Known software products — helps validate candidates
_KNOWN_SOFTWARE_PRODUCTS: frozenset[str] = frozenset(
    {
        "notion",
        "notion ai",
        "chatgpt",
        "gpt-4",
        "gpt-4o",
        "claude",
        "claude ai",
        "gemini",
        "google gemini",
        "copilot",
        "github copilot",
        "microsoft copilot",
        "perplexity",
        "perplexity ai",
        "canva",
        "figma",
        "slack",
        "zoom",
        "teams",
        "microsoft teams",
        "discord",
        "grammarly",
        "quillbot",
        "jasper",
        "jasper ai",
        "otter.ai",
        "otter",
        "loom",
        "calendly",
        "airtable",
        "trello",
        "asana",
        "jira",
        "linear",
        "monday.com",
        "clickup",
        "todoist",
        "obsidian",
        "roam research",
        "logseq",
        "raycast",
        "alfred",
        "zapier",
        "make",
        "n8n",
        "midjourney",
        "stable diffusion",
        "dall-e",
        "adobe firefly",
        "cursor",
        "vs code",
        "visual studio code",
        "webflow",
        "framer",
        "bubble",
        "supabase",
        "firebase",
        "vercel",
        "netlify",
        "heroku",
        # Student/education AI tools
        "quizlet",
        "khanmigo",
        "studley ai",
        "studley",
        "duolingo max",
        "duolingo",
        "wolfram alpha",
        "elicit",
        "consensus",
        "scholarcy",
        "paperpal",
        "research rabbit",
        "connected papers",
        "scite",
        "iris.ai",
        "poe",
        "character.ai",
        "copy.ai",
        "writesonic",
        "rytr",
        "tome",
        "gamma",
        "beautiful.ai",
        "socratic",
        "photomath",
        "mathway",
        "chegg",
        "course hero",
        "anki",
        "remnote",
        "notion student",
        "evernote",
        "google docs",
        "microsoft word",
        "google scholar",
        "zotero",
        "mendeley",
        "readwise",
        "speechify",
        "otter ai",
        "fireflies.ai",
        "krisp",
        "notta",
        "supernormal",
        "microsoft loop",
        "coda",
        "roam",
    }
)

# Generic category phrases that are NOT specific products
_GENERIC_SOFTWARE_CATEGORIES: frozenset[str] = frozenset(
    {
        "productivity tools",
        "ai tools",
        "writing tools",
        "design tools",
        "project management tools",
        "collaboration tools",
        "automation tools",
        "no-code tools",
        "developer tools",
        "analytics tools",
        "marketing tools",
        "communication tools",
        "task management tools",
        "note-taking apps",
        "ai assistants",
        "chatbots",
        # Student/education generic phrases
        "study tools",
        "education technology",
        "learning ai",
        "edtech tools",
        "student tools",
        "educational tools",
        "learning tools",
        "online tools",
        "free tools",
        "best tools",
        "top tools",
        "ai learning",
        "smart tools",
        "digital tools",
        "virtual tools",
        "teaching tools",
        "homework help",
        "study aids",
        "academic tools",
    }
)

# Substrings that indicate an editorial section heading, not a product name
_SOFTWARE_HEADING_SUBSTRINGS: tuple[str, ...] = (
    "navigating",
    "the ai landscape",
    "landscape for",
    "for student success",
    "for students",
    "spotlight on",
    "our approach",
    "the shifting",
    "opportunities in",
    "key ai",
    "choosing the",
    "how to choose",
    "tips for",
    "guide to",
    "overview of",
    "introduction to",
)

# Software product signal terms
_SOFTWARE_INDICATORS: frozenset[str] = frozenset(
    {
        "app",
        "platform",
        "tool",
        "software",
        "extension",
        "plugin",
        "api",
        "sdk",
        "cli",
        "ide",
        "editor",
        "suite",
        "workspace",
        "dashboard",
        "ai",
        ".io",
        ".ai",
        ".com",
    }
)


class SoftwareToolsAdapter(DomainAdapter):
    """Domain adapter for software tools and applications."""

    domain: str = "software_tools"

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        if not super().is_valid_entity(name, query_contract):
            return False

        lower = _normalize(name)

        # Reject generic category phrases
        if lower in _GENERIC_SOFTWARE_CATEGORIES:
            return False

        # Reject domain-specific section headings
        if self._is_software_heading(lower):
            return False

        # Accept known products
        if lower in _KNOWN_SOFTWARE_PRODUCTS:
            return True

        # Accept domain-style names (.io, .ai, .com)
        if any(ind in lower for ind in (".io", ".ai", ".com", ".co")):
            words = lower.split()
            if len(words) <= 3:
                return True

        # Accept short properly capitalized product names (1-3 words, not a heading)
        if self._looks_like_named_software_product(name, lower):
            return True

        return False

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        base_reason = super().get_rejection_reason(name, query_contract)
        if base_reason:
            return base_reason

        lower = _normalize(name)
        if lower in _GENERIC_SOFTWARE_CATEGORIES:
            return "generic software category phrases do not count — need named product"

        if self._is_software_heading(lower):
            return "section headings do not count as software products"

        if not self.is_valid_entity(name, query_contract):
            return "not a named software product or tool"

        return None

    def classify_entity_type(self, name: str, query_contract: "QueryContract") -> str:
        base_type = super().classify_entity_type(name, query_contract)
        if base_type not in ("unknown",):
            return base_type

        lower = _normalize(name)
        if lower in _GENERIC_SOFTWARE_CATEGORIES:
            return "category"
        if self._is_software_heading(lower):
            return "section_heading"
        if lower in _KNOWN_SOFTWARE_PRODUCTS:
            return "software_product"
        if any(ind in lower for ind in (".io", ".ai", ".com", ".co")):
            return "software_product"
        return "unknown"

    def get_product_indicators(self) -> list[str]:
        return sorted(_SOFTWARE_INDICATORS)

    def get_known_brands_or_entities(self) -> list[str]:
        return sorted(_KNOWN_SOFTWARE_PRODUCTS)

    def _is_software_heading(self, lower: str) -> bool:
        """Return True if the text is a section heading, not a product name."""
        return any(sub in lower for sub in _SOFTWARE_HEADING_SUBSTRINGS)

    def _looks_like_named_software_product(self, original_name: str, lower: str) -> bool:
        """Return True if the original name looks like a proper named software product."""
        words = lower.split()
        original_words = original_name.strip().split()

        # Must be 1-4 words to be a product name (not a sentence/heading)
        if not (1 <= len(words) <= 4):
            return False

        # First word must be capitalized in the original
        if not original_words or not original_words[0]:
            return False
        first_char = original_words[0][0]
        if not first_char.isupper():
            return False

        # Reject if first word is a generic heading word
        _HEADING_STARTERS = frozenset(
            {
                "the",
                "a",
                "an",
                "how",
                "why",
                "what",
                "when",
                "where",
                "navigating",
                "exploring",
                "understanding",
                "best",
                "top",
                "new",
                "great",
                "good",
                "free",
                "better",
                "worst",
                "all",
                "our",
                "your",
                "their",
                "this",
                "that",
                "these",
                "those",
            }
        )
        if original_words[0].lower() in _HEADING_STARTERS:
            return False

        # Must have a meaningful (non-stop-word) token
        _STOP = frozenset({"the", "a", "an", "and", "or", "for", "in", "of", "to", "with"})
        meaningful = [w for w in words if w not in _STOP]
        if not meaningful:
            return False

        return True
