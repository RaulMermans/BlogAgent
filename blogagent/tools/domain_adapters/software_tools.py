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
        "claude",
        "gemini",
        "copilot",
        "github copilot",
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
    }
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

        if lower in _GENERIC_SOFTWARE_CATEGORIES:
            return False

        if lower in _KNOWN_SOFTWARE_PRODUCTS:
            return True

        if self._looks_like_software_product(lower):
            return True

        return False

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        base_reason = super().get_rejection_reason(name, query_contract)
        if base_reason:
            return base_reason

        lower = _normalize(name)
        if lower in _GENERIC_SOFTWARE_CATEGORIES:
            return "generic software category phrases do not count — need named product"

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
        if lower in _KNOWN_SOFTWARE_PRODUCTS:
            return "software_product"
        if self._looks_like_software_product(lower):
            return "software_product"
        return "unknown"

    def get_product_indicators(self) -> list[str]:
        return sorted(_SOFTWARE_INDICATORS)

    def get_known_brands_or_entities(self) -> list[str]:
        return sorted(_KNOWN_SOFTWARE_PRODUCTS)

    def _looks_like_software_product(self, lower: str) -> bool:
        words = lower.split()
        if len(words) < 1 or len(words) > 5:
            return False
        # Named products tend to start with capital letter (checked before normalization)
        # or match known patterns
        if any(ind in lower for ind in (".io", ".ai", ".com", ".co")):
            return True
        # Has capitalized proper noun form (checked via original text - available via name param)
        return False
