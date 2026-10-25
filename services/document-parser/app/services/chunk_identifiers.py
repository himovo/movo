"""Stable identifiers used for exact knowledge lookups."""

from __future__ import annotations

import re


IDENTIFIER = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?![A-Za-z0-9])")


def extract_identifiers(text: str) -> list[str]:
    return list(dict.fromkeys(
        token.upper()
        for match in IDENTIFIER.finditer(text)
        if (token := match.group()) and len(token.replace("-", "")) >= 4 and any(char.isdigit() for char in token)
    ))
