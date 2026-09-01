from __future__ import annotations

import re
from typing import List


class CandidateAnalyzer:
    """Analyzes subject candidates to determine if they represent the same entity."""

    @staticmethod
    def are_synonymous(candidates: List[str]) -> bool:
        """Check if candidates are likely synonyms/expansions vs different meanings."""
        if len(candidates) < 2:
            return True

        # For 2 candidates, check if they're related
        if len(candidates) == 2:
            return CandidateAnalyzer._is_related(candidates[0], candidates[1])

        # For 3+ candidates, check if they form a consistent group
        # At least one pair must be related, and no pair should be clearly unrelated
        has_related_pair = False
        for i, c1 in enumerate(candidates):
            for c2 in candidates[i + 1 :]:
                if CandidateAnalyzer._is_related(c1, c2):
                    has_related_pair = True
                elif CandidateAnalyzer._are_clearly_different(c1, c2):
                    # Found clearly different meanings
                    return False

        return has_related_pair

    @staticmethod
    def _are_clearly_different(text1: str, text2: str) -> bool:
        """Check if two texts represent clearly different concepts."""
        t1 = str(text1 or "").strip().lower()
        t2 = str(text2 or "").strip().lower()

        if not t1 or not t2:
            return False

        # Extract meaningful words (exclude common words)
        tokens1 = set(re.findall(r"\w+", t1))
        tokens2 = set(re.findall(r"\w+", t2))

        # Remove the common acronym if present
        acronym_candidates = [t for t in [text1, text2] if len(t) <= 5 and t.isupper()]
        for acronym in acronym_candidates:
            tokens1.discard(acronym.lower())
            tokens2.discard(acronym.lower())

        # If no overlap in meaningful words, they're clearly different
        overlap = tokens1 & tokens2
        return len(overlap) == 0 and len(tokens1) > 0 and len(tokens2) > 0

    @staticmethod
    def _is_related(text1: str, text2: str) -> bool:
        """Check if two texts represent related concepts."""
        t1 = str(text1 or "").strip()
        t2 = str(text2 or "").strip()

        if not t1 or not t2:
            return False

        # Check acronym expansion
        if CandidateAnalyzer._is_acronym_expansion(t1, t2):
            return True

        # Check significant token overlap
        tokens1 = set(re.findall(r"\w+", t1.lower()))
        tokens2 = set(re.findall(r"\w+", t2.lower()))

        if not tokens1 or not tokens2:
            return False

        overlap = tokens1 & tokens2
        min_tokens = min(len(tokens1), len(tokens2))

        # 60% overlap threshold
        if overlap and len(overlap) >= min_tokens * 0.6:
            return True

        return False

    @staticmethod
    def _is_acronym_expansion(text1: str, text2: str) -> bool:
        """Check if one text is an acronym of the other."""
        t1 = str(text1 or "").strip()
        t2 = str(text2 or "").strip()

        if not t1 or not t2:
            return False

        # Identify potential acronym (shorter, uppercase, no spaces)
        if len(t1) < len(t2) and t1.isupper() and " " not in t1:
            acronym, expansion = t1, t2
        elif len(t2) < len(t1) and t2.isupper() and " " not in t2:
            acronym, expansion = t2, t1
        else:
            return False

        # Extract first letters from expansion
        words = re.findall(r"\b[A-Za-z]\w*", expansion)
        if not words:
            return False

        first_letters = "".join(w[0].upper() for w in words)

        # Check if acronym matches
        return acronym == first_letters

    @staticmethod
    def has_strong_context(user_query: str, channel: str = "", audience: str = "") -> bool:
        """Check if request has strong contextual signals indicating clear intent."""
        query = str(user_query or "").lower()
        ch = str(channel or "").lower()
        aud = str(audience or "").lower()

        # Technical context signals
        tech_keywords = ["技术", "开发", "程序", "工程", "ai", "developer", "tech", "engineering"]

        # Check if audience explicitly mentions technical context
        if any(kw in aud for kw in tech_keywords):
            return True

        # Check if channel name suggests technical content
        # Common patterns: tech/developer/engineering in channel name
        if any(kw in ch for kw in ["tech", "dev", "engineer", "code", "programming"]):
            return True

        # Explicit format/style requests indicate clear intent
        style_keywords = ["风格", "笔记", "文章", "教程", "爆款", "style", "tutorial"]
        if any(kw in query for kw in style_keywords):
            return True

        # Specific deliverable requests
        deliverable_keywords = ["生成", "写", "创作", "compose", "generate", "write"]
        if any(kw in query for kw in deliverable_keywords):
            return True

        return False
