"""Skill registry — look up and format skill briefs for prompt injection."""

from __future__ import annotations

from blogagent.skills.specs import SKILL_SPECS


def get_skill_brief(skill_name: str) -> str:
    """Return the compressed brief for a skill, or empty string if not found."""
    spec = SKILL_SPECS.get(skill_name)
    if spec is None:
        return ""
    return spec.get("brief", "")


def get_skill_briefs(skill_names: list[str]) -> str:
    """Return a formatted block of skill briefs for prompt injection.

    Each line is prefixed with the skill name so the model knows which
    skill each rule comes from.
    """
    lines: list[str] = []
    for name in skill_names:
        brief = get_skill_brief(name)
        if brief:
            lines.append(f"[{name}] {brief}")
    return "\n".join(lines)
