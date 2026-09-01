from __future__ import annotations

from typing import Any, Dict, List

from app.enterprise_capabilities.content.profile_presets.contracts import ProfilePreset


class PresetCatalog:
    def _builtin(self, output_spec: Dict[str, Any]) -> List[ProfilePreset]:
        # Builtin channel presets stay empty here. Channel-specific style should be
        # expressed through semantic delivery profiles or explicit user skills, not
        # through hidden runtime branches with implicit visual defaults.
        return []

    @staticmethod
    def _has_writing_contract(skill: Dict[str, Any]) -> bool:
        advanced = skill.get("advanced") if isinstance(skill.get("advanced"), dict) else {}
        policy = advanced.get("policy") if isinstance(advanced.get("policy"), dict) else {}
        compose = policy.get("compose_policy") if isinstance(policy.get("compose_policy"), dict) else {}
        contract = skill.get("skill_contract") if isinstance(skill.get("skill_contract"), dict) else {}
        structure = contract.get("structure") if isinstance(contract.get("structure"), dict) else {}
        visual = contract.get("visual_policy") if isinstance(contract.get("visual_policy"), dict) else {}
        return bool(compose or structure or visual)

    @classmethod
    def _selected_writing_skills(cls, output_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Use the writing sources already resolved by the planning layer."""
        raw_candidates: List[Dict[str, Any]] = []
        for raw in list(output_spec.get("selected_style_skills") or []):
            if isinstance(raw, dict):
                raw_candidates.append(raw)
        for key in (
            "manual_selected_style_skill",
            "selected_skill",
            "selected_workflow_skill",
            "selected_user_skill",
        ):
            raw = output_spec.get(key)
            if isinstance(raw, dict):
                raw_candidates.append(raw)

        selected: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for skill in raw_candidates:
            if not bool(skill.get("is_active", True)) or not cls._has_writing_contract(skill):
                continue
            identity = str(skill.get("id") or skill.get("name") or "").strip()
            if not identity or identity in seen:
                continue
            seen.add(identity)
            selected.append(skill)
        return selected

    def _from_user_skills(self, skills: List[Dict[str, Any]]) -> List[ProfilePreset]:
        out: List[ProfilePreset] = []
        for s in skills:
            if not isinstance(s, dict) or not bool(s.get("is_active", True)):
                continue
            sid = str(s.get("name") or "").strip()
            if not sid:
                continue
            adv = s.get("advanced") if isinstance(s.get("advanced"), dict) else {}
            policy = adv.get("policy") if isinstance(adv.get("policy"), dict) else {}
            cp = policy.get("compose_policy") if isinstance(policy.get("compose_policy"), dict) else {}
            rp = policy.get("research_policy") if isinstance(policy.get("research_policy"), dict) else {}
            contract = s.get("skill_contract") if isinstance(s.get("skill_contract"), dict) else {}
            structure = contract.get("structure") if isinstance(contract.get("structure"), dict) else {}
            visual = contract.get("visual_policy") if isinstance(contract.get("visual_policy"), dict) else {}
            out.append(
                ProfilePreset(
                    preset_id=sid,
                    source="user_db",
                    compose_policy=cp,
                    structure_contract={"required_blocks": list(structure.get("required_blocks") or [])},
                    evidence_policy=rp,
                    visual_contract=visual if isinstance(visual, dict) else {},
                    quality_gates={},
                    forbidden_patterns=list((cp.get("forbidden_patterns") or [])) if isinstance(cp, dict) else [],
                    output_contract={"format": "markdown"},
                    metadata={"role": str(s.get("role") or "")},
                )
            )
        return out

    def list_candidates(self, *, output_spec: Dict[str, Any]) -> List[ProfilePreset]:
        # Do not re-rank every active skill during writing. Workflow/style
        # selection was completed upstream; absent a selected writing contract,
        # the resolver will synthesize a dynamic preset instead.
        selected = self._selected_writing_skills(output_spec)
        return self._from_user_skills(selected) + self._builtin(output_spec)
