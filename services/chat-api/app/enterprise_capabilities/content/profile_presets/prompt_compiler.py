from __future__ import annotations

from typing import Any, Dict, List

from app.enterprise_capabilities.content.planning import body_plan_titles
from app.enterprise_capabilities.content.body_projection import body_only_formatting_rules, strip_visual_placeholder_directives
from app.enterprise_capabilities.content.profile_presets.contracts import ComposeProfile, ProfilePreset


class PresetPromptCompiler:
    """Compile preset + profile into prompt-contract consumable by writer engine."""

    def compile(self, *, compose_profile: ComposeProfile, preset: ProfilePreset, output_spec: Dict[str, Any]) -> Dict[str, Any]:
        compose = dict(preset.compose_policy or {})
        structure = dict(preset.structure_contract or {})
        evidence = dict(preset.evidence_policy or {})
        visual = dict((preset.visual_contract.model_dump() if hasattr(preset.visual_contract, "model_dump") else preset.visual_contract) or {})
        gates = dict(preset.quality_gates or {})
        forbidden = [str(x).strip() for x in (preset.forbidden_patterns or []) if str(x).strip()]
        identity = str(preset.identity or "").strip()
        style_ref = dict(preset.style_reference or {})
        anti = dict(preset.anti_patterns or {})
        formatting = body_only_formatting_rules(dict(preset.formatting_rules or {}))
        must_include = [str(x).strip() for x in (preset.must_include or []) if str(x).strip()]
        content_plan = output_spec.get("content_plan") if isinstance(output_spec.get("content_plan"), dict) else {}
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        argument_pack = output_spec.get("argument_pack") if isinstance(output_spec.get("argument_pack"), dict) else {}
        visual_semantics = output_spec.get("visual_semantics") if isinstance(output_spec.get("visual_semantics"), dict) else {}
        fw = [str(x).strip() for x in (anti.get("forbidden_words") or []) if str(x).strip()]
        if fw:
            forbidden = list(dict.fromkeys(forbidden + fw))
        forbidden = [x for x in forbidden if x][:24]

        voice_axes = {
            "tone": str(compose.get("tone") or ""),
            "audience": str(compose.get("audience") or ""),
            "content_form": str(compose.get("content_form") or ""),
            "style_axes": dict(compose_profile.style_axes or {}),
        }
        deliverable_signature = strip_visual_placeholder_directives(str(compose_profile.deliverable_signature or "").strip())
        structure_axes = {
            "required_blocks": [str(x).strip() for x in (structure.get("required_blocks") or []) if str(x).strip()],
            "depth": int((compose_profile.hard_constraints or {}).get("depth") or 0),
            "hierarchy": str((compose_profile.hard_constraints or {}).get("hierarchy") or ""),
            "planned_sections": body_plan_titles(structure=structure, content_plan=content_plan)[:12],
        }
        evidence_axes = {
            "citation_required": bool(evidence.get("citation_required", False)),
            "verifiability": str((compose_profile.hard_constraints or {}).get("verifiability") or ""),
        }

        visual_plan = dict(content_task_spec.get("visual_plan") or {})
        preferred_roles = [str(x).strip() for x in list(visual_plan.get("preferred_roles") or []) if str(x).strip()]
        planned_assets = [dict(item) for item in list(visual_plan.get("assets") or []) if isinstance(item, dict)]
        visual_axes = {
            "required_total": int(visual_plan.get("min_assets") or 0),
            "max_total": int(visual_plan.get("max_assets") or 0),
            "type_mix": preferred_roles[:8],
            "anchor_policy": str(visual_plan.get("anchor_policy") or "").strip(),
            "fallback_policy": {"repair_if_missing": bool(visual_plan.get("repair_if_missing"))},
            "semantic_roles": [
                str(item.get("role") or "").strip()
                for item in list(visual_semantics.get("roles") or [])
                if isinstance(item, dict) and str(item.get("role") or "").strip()
            ][:8] or [str(item.get("role") or "").strip() for item in planned_assets if str(item.get("role") or "").strip()][:8],
        }
        argument_axes = {
            "definitions": len(list(argument_pack.get("definitions") or [])),
            "boundaries": len(list(argument_pack.get("boundaries") or [])),
            "use_cases": len(list(argument_pack.get("use_cases") or [])),
            "relationships": len(list(argument_pack.get("relationships") or [])),
        }

        body_quality_gates = {
            "min_words": int(gates.get("min_words") or 0),
            "max_words": int(gates.get("max_words") or 0),
            "style_consistency_min": float(gates.get("style_consistency_min") or 0.65),
            "structure_coverage_min": float(gates.get("structure_coverage_min") or 0.75),
        }
        production_quality_gates = {
            "visual_coverage_min": float(gates.get("visual_coverage_min") or 0.6),
        }

        # Full contract markdown (diagnostic-rich).
        lines: List[str] = [
            "# Prompt Contract",
            f"- intent_statement: {compose_profile.intent_statement}",
            f"- deliverable_signature: {deliverable_signature}",
            f"- audience_model: {compose_profile.audience_model}",
            f"- identity: {identity}",
            f"- tone: {voice_axes.get('tone')}",
            f"- audience: {voice_axes.get('audience')}",
            f"- content_form: {voice_axes.get('content_form')}",
        ]
        rb = list(structure_axes.get("required_blocks") or [])
        if rb:
            lines.append("- required_blocks: " + " | ".join(rb))
        planned = list(structure_axes.get("planned_sections") or [])
        if planned:
            lines.append("- planned_sections: " + " | ".join(planned))
        if evidence_axes.get("citation_required"):
            lines.append("- citation_required: true")
        if any(int(v or 0) > 0 for v in argument_axes.values()):
            lines.append("- argument_pack: " + str(argument_axes))
        if must_include:
            lines.append("- must_include: " + " | ".join(must_include))
        if str(style_ref.get("positive") or "").strip():
            lines.append("- style_ref_positive: " + str(style_ref.get("positive") or "").strip())
        if str(style_ref.get("negative") or "").strip():
            lines.append("- style_ref_negative: " + str(style_ref.get("negative") or "").strip())
        if formatting:
            lines.append("- formatting_rules: " + str(formatting))
        if forbidden:
            lines.append("- forbidden_patterns: " + " | ".join(forbidden))

        # Compact contract markdown (for model prompt injection to avoid repeated blocks).
        compact_lines: List[str] = [
            "# Protocol Axes",
            f"- tone: {voice_axes.get('tone')}",
            f"- audience: {voice_axes.get('audience')}",
            f"- content_form: {voice_axes.get('content_form')}",
        ]
        if evidence_axes.get("citation_required"):
            compact_lines.append("- citation_required: true")
        if planned:
            compact_lines.append("- planned_sections: " + " | ".join(planned))
        body_contract = {
            "voice_axes": voice_axes,
            "structure_axes": structure_axes,
            "evidence_axes": evidence_axes,
            "quality_gates": body_quality_gates,
            "forbidden_patterns": forbidden,
            "identity": identity,
            "style_reference": style_ref,
            "must_include": must_include,
            "anti_patterns": anti,
            "formatting_rules": formatting,
            "style_markdown": "\n".join(lines).strip(),
            "style_markdown_compact": "\n".join(compact_lines).strip(),
        }
        production_contract = {
            "visual_axes": visual_axes,
            "quality_gates": production_quality_gates,
            "visual_semantics": {
                "roles": [
                    {"role": role}
                    for role in list(visual_axes.get("semantic_roles") or [])
                    if str(role).strip()
                ],
            },
        }
        return {
            "body_contract": body_contract,
            "production_contract": production_contract,
        }
