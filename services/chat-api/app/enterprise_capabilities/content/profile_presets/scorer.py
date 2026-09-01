from __future__ import annotations

from app.enterprise_capabilities.content.profile_presets.contracts import PresetCandidate, ProfilePreset


class PresetScorer:
    def score(self, *, preset: ProfilePreset, fit_score: float, constraint_score: float, hard_conflicts: int, soft_conflicts: int) -> PresetCandidate:
        risk_penalty = min(0.8, 0.45 * max(0, hard_conflicts) + 0.06 * max(0, soft_conflicts))
        source_bonus = 0.01 if str(preset.source) == "user_db" else 0.0
        total = max(0.0, min(1.0, 0.68 * fit_score + 0.30 * constraint_score + source_bonus - risk_penalty))
        return PresetCandidate(
            preset=preset,
            fit_score=float(fit_score),
            constraint_score=float(constraint_score),
            risk_penalty=float(risk_penalty),
            total_score=float(total),
        )
