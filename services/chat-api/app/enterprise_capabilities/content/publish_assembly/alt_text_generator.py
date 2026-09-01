"""
Alt text generator for visual assets.

Generates reader-friendly alt text from slot metadata when section titles are unavailable.
"""
from __future__ import annotations

from typing import Optional


class AltTextGenerator:
    """Generates descriptive alt text for visual assets."""

    @classmethod
    def generate(
        cls,
        *,
        section_title: str,
        slot_role: str,
        slot_description: str,
        fallback_index: int,
    ) -> str:
        """
        Generate alt text with fallback chain:
        1. Use section_title if available
        2. Use slot_description if available
        3. Humanize slot_role to readable text
        4. Use generic "Visual {index}"

        Args:
            section_title: Title of the section this visual belongs to
            slot_role: Internal role identifier (e.g., "hook_3_lines")
            slot_description: Semantic description of the visual
            fallback_index: Index for generic fallback

        Returns:
            Reader-friendly alt text
        """
        # Priority 1: Section title
        title = str(section_title or "").strip()
        if title:
            return title

        # Priority 2: Slot description
        desc = str(slot_description or "").strip()
        if desc:
            return desc

        # Priority 3: Humanize role identifier
        # Convert "hook_3_lines" -> "Hook visual"
        # Convert "problem_statement" -> "Problem statement visual"
        role = str(slot_role or "").strip()
        if role:
            readable = cls._humanize_role(role)
            if readable:
                return readable

        # Priority 4: Generic fallback
        return f"Visual {fallback_index}"

    @staticmethod
    def _humanize_role(role: str) -> str:
        """
        Convert internal role identifier to readable text.

        Examples:
            "hook_3_lines" -> "Hook visual"
            "problem_statement" -> "Problem statement visual"
            "key_benefit_1" -> "Key benefit visual"
        """
        # Remove trailing numbers and underscores
        cleaned = role.rstrip("0123456789_")

        # Replace underscores with spaces
        words = cleaned.replace("_", " ")

        # Capitalize first letter of each word
        capitalized = " ".join(word.capitalize() for word in words.split())

        # Add "visual" suffix if not already descriptive enough
        if capitalized and len(capitalized) > 2:
            return f"{capitalized} visual"

        return ""
