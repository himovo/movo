from __future__ import annotations

from .expert_validator import is_expert_package, validate_expert_package
from .validator import ValidatedSkillPackage, validate_skill_zip


def validate_skill_package(content: bytes) -> ValidatedSkillPackage:
    if is_expert_package(content):
        return validate_expert_package(content)
    return validate_skill_zip(content)
