from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
import re
from typing import Any, Dict, List

from app.enterprise_capabilities.content.body_projection import is_visual_or_production_requirement as shared_is_visual_or_production_requirement
from app.enterprise_capabilities.content.compose_access import resolve_compose_policy
from app.enterprise_capabilities.content.profile_presets.contracts import ComposeProfile, ProfilePreset, VisualContract

def _extract_compose_policy(output_spec: Dict[str, Any]) -> Dict[str, Any]:
    return resolve_compose_policy(output_spec)


def _extract_content_task_spec(output_spec: Dict[str, Any]) -> Dict[str, Any]:
    raw = output_spec.get("content_task_spec")
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _extract_content_schema(output_spec: Dict[str, Any]) -> Dict[str, Any]:
    raw = output_spec.get("content_schema")
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _normalize_delivery_profile(value: Any, *, fallback_channel: str) -> Dict[str, str]:
    raw = dict(value or {}) if isinstance(value, dict) else {}
    channel = str(raw.get("channel") or "").strip().lower()
    if not channel:
        channel = str(fallback_channel or "generic").strip().lower() or "generic"
    rhetoric_style = str(raw.get("rhetoric_style") or "").strip()
    opening_pattern = str(raw.get("opening_pattern") or "").strip()
    narrative_density = str(raw.get("narrative_density") or "").strip().lower()
    if narrative_density not in {"low", "medium", "high"}:
        narrative_density = ""
    opinion_strength = str(raw.get("opinion_strength") or "").strip().lower()
    if opinion_strength not in {"low", "medium", "high"}:
        opinion_strength = ""
    scannability = str(raw.get("scannability") or "").strip().lower()
    if scannability not in {"low", "medium", "high"}:
        scannability = ""
    return {
        "channel": channel,
        "rhetoric_style": rhetoric_style,
        "opening_pattern": opening_pattern,
        "narrative_density": narrative_density,
        "opinion_strength": opinion_strength,
        "scannability": scannability,
    }


def _build_style_description_by_priority(
    *,
    delivery_profile: Dict[str, str],
    compose_style_description: str,
    preset_style_fallback: str,
) -> str:
    # Priority: delivery_profile > compose_policy.style_description > preset defaults
    has_delivery_signal = any(
        bool(str(delivery_profile.get(k) or "").strip())
        for k in ["rhetoric_style", "opening_pattern", "narrative_density", "opinion_strength", "scannability"]
    )
    if has_delivery_signal:
        parts = [
            f"channel={delivery_profile.get('channel') or 'generic'}",
            f"rhetoric_style={delivery_profile.get('rhetoric_style') or 'balanced_explainer'}",
            f"opening_pattern={delivery_profile.get('opening_pattern') or 'problem_then_solution'}",
            f"narrative_density={delivery_profile.get('narrative_density') or 'medium'}",
            f"opinion_strength={delivery_profile.get('opinion_strength') or 'medium'}",
            f"scannability={delivery_profile.get('scannability') or 'high'}",
        ]
        return "delivery_profile: " + ", ".join(parts)
    if str(compose_style_description or "").strip():
        return str(compose_style_description or "").strip()
    return str(preset_style_fallback or "").strip()


def _default_required_blocks(*, channel: str, content_form: str, task_mode: str) -> List[str]:
    return ["核心内容"]


def _normalize_requirement_token(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    out: List[str] = []
    for ch in raw:
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
    return "".join(out)


def _is_visual_only_requirement(value: str) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return False
    visual_markers = [
        "配图",
        "图片",
        "图示",
        "图注",
        "image",
        "visual",
        "infographic",
        "gallery",
        "cover",
        "illustration",
    ]
    return any(marker in raw for marker in visual_markers)


def _is_production_only_requirement(value: str) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return False
    markers = [
        "配图脚本",
        "图文脚本",
        "图文生产",
        "production brief",
        "visual brief",
        "配图点位",
        "图注脚本",
        "画面脚本",
    ]
    return any(marker in raw for marker in markers)


def _sanitize_reader_facing_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    replacements = [
        "（含配图脚本）",
        "(含配图脚本)",
        "含配图脚本",
        "配图脚本",
        "图文脚本",
    ]
    for token in replacements:
        text = text.replace(token, "")
    return " ".join(text.split()).strip(" -_：:") or str(value or "").strip()


def _parse_explicit_visual_count(requirement: str) -> Dict[str, int]:
    raw = str(requirement or "").strip().lower()
    if not raw:
        return {"min_images": 0, "max_images": 0}
    patterns = [
        r"(\d{1,2})\s*[-~到至]\s*(\d{1,2})\s*(?:张|个)?(?:配图|图片|图|images?)",
        r"(\d{1,2})\s*[-~to]+\s*(\d{1,2})\s*images?",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if not match:
            continue
        low = max(0, int(match.group(1) or 0))
        high = max(low, int(match.group(2) or 0))
        return {"min_images": low, "max_images": high}
    single_patterns = [
        r"(\d{1,2})\s*(?:张|个)?(?:配图|图片|图)",
        r"(\d{1,2})\s*images?",
    ]
    for pattern in single_patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if not match:
            continue
        count = max(0, int(match.group(1) or 0))
        return {"min_images": count, "max_images": count}
    return {"min_images": 0, "max_images": 0}


def _infer_visual_density_targets(
    *,
    compose_policy: Dict[str, Any],
    content_task_spec: Dict[str, Any],
    min_words: int,
    max_words: int,
    is_dynamic_source: bool = False,
) -> Dict[str, int]:
    compose_visual = str(compose_policy.get("visual_requirements") or "").strip()
    visual_preferences = compose_policy.get("visual_preferences") if isinstance(compose_policy.get("visual_preferences"), dict) else {}
    visual_preferences = dict(visual_preferences or {})
    assembly = compose_policy.get("assembly_profile") if isinstance(compose_policy.get("assembly_profile"), dict) else {}
    visual_density = str(assembly.get("visual_density") or "").strip().lower()
    pref_density = str(visual_preferences.get("density") or "").strip().lower()
    if pref_density in {"low", "medium", "high"}:
        visual_density = pref_density
    scannability = str(assembly.get("scannability") or "").strip().lower()
    length_band = str(assembly.get("length_band") or "").strip().lower()
    visual_plan = content_task_spec.get("visual_plan") if isinstance(content_task_spec.get("visual_plan"), dict) else {}
    explicit = _parse_explicit_visual_count(compose_visual)
    pref_min = max(0, int(visual_preferences.get("min_images") or 0))
    pref_max = max(pref_min, int(visual_preferences.get("max_images") or 0))
    # Dynamic preset (unknown type — resume, email, manual): default to no
    # auto-injected visuals unless the user/synth explicitly requested them.
    # Otherwise word-count inflation can flip mobile_short=False and silently
    # add 2-4 cover images to a resume.
    if is_dynamic_source and not compose_visual and pref_min == 0 and not explicit["min_images"]:
        cts_min = max(0, int(visual_plan.get("min_assets") or 0))
        cts_max = max(0, int(visual_plan.get("max_assets") or 0))
        if cts_min == 0 and cts_max == 0:
            return {"min_images": 0, "max_images": 0}
    cts_min = max(0, int(visual_plan.get("min_assets") or 0))
    cts_max = max(0, int(visual_plan.get("max_assets") or 0))
    mobile_short = (
        length_band == "short"
        or max_words <= 1200
        or min_words <= 1000
        or scannability == "high"
    )
    inferred_min = 0
    inferred_max = 0
    if pref_min > 0:
        inferred_min = pref_min
        inferred_max = pref_max or pref_min
    elif explicit["min_images"] > 0:
        inferred_min = explicit["min_images"]
        inferred_max = explicit["max_images"] or explicit["min_images"]
    elif compose_visual:
        inferred_min = 3 if mobile_short else 2
        inferred_max = inferred_min + 2
    elif visual_density == "high":
        inferred_min = 4 if mobile_short else 3
        inferred_max = inferred_min + 2
    elif visual_density == "medium":
        inferred_min = 3 if mobile_short else 2
        inferred_max = inferred_min + 2
    elif visual_density == "low":
        inferred_min = 1 if compose_visual else 0
        inferred_max = inferred_min
    min_images = max(cts_min, inferred_min)
    max_images = max(cts_max, inferred_max, min_images)
    return {"min_images": min_images, "max_images": max_images}


def _collect_visual_or_production_signals(
    *,
    content_task_spec: Dict[str, Any],
    compose_policy: Dict[str, Any],
    content_schema: Dict[str, Any],
) -> List[str]:
    signals: List[str] = []
    cts_visual = content_task_spec.get("visual_plan") if isinstance(content_task_spec.get("visual_plan"), dict) else {}
    for asset in list(cts_visual.get("assets") or []):
        if not isinstance(asset, dict):
            continue
        for key in ["role", "description", "anchor"]:
            value = _normalize_requirement_token(str(asset.get(key) or ""))
            if value:
                signals.append(value)
    visual_requirements = str(compose_policy.get("visual_requirements") or "").strip()
    if visual_requirements:
        signals.append(_normalize_requirement_token(visual_requirements))
    for block in list(content_schema.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        hint = _normalize_requirement_token(str(block.get("visual_hint") or ""))
        if hint and hint != "none":
            signals.append(hint)
    return [x for x in dict.fromkeys(signals) if x]


def _is_visual_or_production_requirement(
    value: str,
    *,
    source: str,
    visual_signals: List[str],
) -> bool:
    normalized = _normalize_requirement_token(value)
    if not normalized:
        return False
    if source in {"visual_requirement", "production_requirement"}:
        return True
    if shared_is_visual_or_production_requirement(value):
        return True
    if any(signal and (signal in normalized or normalized in signal) for signal in visual_signals):
        return True
    return _is_visual_only_requirement(value) or _is_production_only_requirement(value)


def _infer_intent_channel(output_spec: Dict[str, Any]) -> str:
    semantic = output_spec.get("semantic_delivery_profile") if isinstance(output_spec.get("semantic_delivery_profile"), dict) else {}
    ch = str(semantic.get("publish_channel") or "").strip().lower()
    if ch:
        return ch
    cts = _extract_content_task_spec(output_spec)
    medium = cts.get("medium") if isinstance(cts.get("medium"), dict) else {}
    ch = str(medium.get("channel") or "").strip().lower()
    if ch:
        return ch
    compose = _extract_compose_policy(output_spec)
    ch = str(compose.get("publish_channel") or "").strip().lower()
    if ch:
        return ch
    gp = output_spec.get("generation_policy") if isinstance(output_spec.get("generation_policy"), dict) else {}
    ch = str(gp.get("publish_channel") or "").strip().lower()
    if ch:
        return ch
    return "generic"


def _infer_channel(output_spec: Dict[str, Any], preset: ProfilePreset) -> str:
    compose_policy = _extract_compose_policy(output_spec)
    semantic = output_spec.get("semantic_delivery_profile") if isinstance(output_spec.get("semantic_delivery_profile"), dict) else {}
    publish_context = str(semantic.get("publish_context") or "").strip()
    semantic_channel = str(semantic.get("publish_channel") or "").strip().lower()
    delivery_profile = compose_policy.get("delivery_profile") if isinstance(compose_policy.get("delivery_profile"), dict) else {}
    dp_channel = str(delivery_profile.get("channel") or "").strip().lower()
    if publish_context:
        return semantic_channel or "generic"
    if dp_channel and dp_channel != "generic":
        return dp_channel
    intent_channel = _infer_intent_channel(output_spec)
    compose = dict(preset.compose_policy or {})
    preset_channel = str(compose.get("publish_channel") or "").strip().lower()
    # Intent channel wins when explicitly known; dynamic preset should not override user intent.
    if intent_channel and intent_channel != "generic":
        return intent_channel
    return preset_channel or intent_channel or "generic"


def _infer_content_form(output_spec: Dict[str, Any], preset: ProfilePreset) -> str:
    semantic = output_spec.get("semantic_delivery_profile") if isinstance(output_spec.get("semantic_delivery_profile"), dict) else {}
    semantic_shape = str(semantic.get("delivery_shape") or "").strip().lower()
    semantic_form = str(semantic.get("content_form") or "").strip().lower()
    cts = _extract_content_task_spec(output_spec)
    schema = cts.get("schema") if isinstance(cts.get("schema"), dict) else {}
    medium = cts.get("medium") if isinstance(cts.get("medium"), dict) else {}
    schema_type = str(schema.get("type") or "").strip().lower()
    category = str(cts.get("category") or "").strip().lower()
    channel = _infer_intent_channel(output_spec)
    short_forms = {"brief", "memo", "notice", "email", "letter", "announcement", "summary"}
    task_ir = output_spec.get("task_ir") if isinstance(output_spec.get("task_ir"), dict) else {}
    goal = cts.get("goal") if isinstance(cts.get("goal"), dict) else {}
    report_signal_text = " ".join(
        str(x or "")
        for x in [
            output_spec.get("workflow_skill"),
            output_spec.get("selected_skill"),
            output_spec.get("skill"),
            output_spec.get("user_question"),
            output_spec.get("latest_user_request"),
            task_ir.get("goal"),
            cts.get("title"),
            cts.get("summary"),
            goal.get("primary_objective") if isinstance(goal, dict) else "",
            goal.get("primary_action") if isinstance(goal, dict) else "",
            schema.get("name"),
            schema.get("type"),
        ]
    ).lower()
    if any(token in report_signal_text for token in ("专报", "情况专报", "report brief", "special report")):
        return "report"
    if semantic_shape == "publishable_article":
        return "article"
    if semantic_form in {"document_scale", "prd"}:
        return "report"
    if semantic_form in short_forms:
        return "brief" if semantic_form in {"notice", "email", "letter", "announcement"} else semantic_form
    if category in short_forms:
        return "brief" if category in {"notice", "email", "letter", "announcement"} else category
    if schema_type in short_forms:
        return "brief" if schema_type in {"notice", "email", "letter", "announcement"} else schema_type
    if channel in {"email", "notice", "announcement"}:
        return "brief"
    if semantic_shape == "report":
        return "report"
    if semantic_form:
        return semantic_form
    primary_action = str(goal.get("primary_action") or "").strip().lower()
    schema_name = str(schema.get("name") or "").strip().lower()
    surface = str(medium.get("surface") or "").strip().lower()
    if primary_action in {"article", "compose_article"} or schema_name == "sectioned_content":
        return "article"
    if primary_action in {"report", "compose_report", "document_scale", "prd"}:
        return "report"
    compose = _extract_compose_policy(output_spec)
    intent_form = str(compose.get("content_form") or "").strip().lower()
    if intent_form in {"document_scale", "prd"}:
        return "report"
    if intent_form in short_forms:
        return "brief" if intent_form in {"notice", "email", "letter", "announcement"} else intent_form
    compose = dict(preset.compose_policy or {})
    preset_form = str(compose.get("content_form") or "").strip().lower()
    if preset_form in {"document_scale", "prd"}:
        return "report"
    if preset_form in short_forms:
        return "brief" if preset_form in {"notice", "email", "letter", "announcement"} else preset_form
    if surface == "document":
        if intent_form and intent_form != "report":
            return intent_form
        if preset_form and preset_form != "report":
            return preset_form
        return "article"
    if semantic_shape == "document":
        if intent_form and intent_form != "report":
            return intent_form
        if preset_form and preset_form != "report":
            return preset_form
        return "article"
    return intent_form or preset_form or "article"


def _infer_required_blocks(preset: ProfilePreset, output_spec: Dict[str, Any], channel: str, content_form: str, task_mode: str) -> List[str]:
    ob = [str(x).strip() for x in (output_spec.get("required_blocks") or []) if str(x).strip()]
    if not ob:
        gp = output_spec.get("generation_policy") if isinstance(output_spec.get("generation_policy"), dict) else {}
        ob = [str(x).strip() for x in (gp.get("required_sections") or []) if str(x).strip()]
    if ob:
        return ob

    # Dynamic-source presets: synth's structure_contract.required_blocks is
    # the authoritative voice on what the deliverable's sections are. The
    # rest of this function looks at upstream signals (compose.required_sections,
    # content_schema, publish_narrative) that for dynamic deliverables are
    # either missing or stamped with a single deliverable-description string
    # like ["撰写用于求职投递与面试评估的专业简历文档report"]. Letting those win
    # collapses synth's 6-7 resume sections back into one bogus block.
    if str(getattr(preset, "source", "") or "").strip().lower() == "dynamic":
        synth_blocks = [
            str(x).strip()
            for x in (dict(preset.structure_contract or {}).get("required_blocks") or [])
            if str(x).strip()
        ]
        if synth_blocks:
            return synth_blocks
    cts = _extract_content_task_spec(output_spec)
    publish_narrative = cts.get("publish_narrative") if isinstance(cts.get("publish_narrative"), dict) else {}
    if str(publish_narrative.get("publish_class") or "").strip():
        schema = cts.get("schema") if isinstance(cts.get("schema"), dict) else {}
        pattern = [str(x).strip() for x in (schema.get("section_or_step_pattern") or []) if str(x).strip()]
        if len(pattern) >= 3:
            return pattern
    compose_policy = _extract_compose_policy(output_spec)
    structure = dict(preset.structure_contract or {})
    from_compose = [str(x).strip() for x in (compose_policy.get("required_sections") or []) if str(x).strip()]
    if from_compose:
        return from_compose
    content_schema = _extract_content_schema(output_spec)
    schema_required = [str(x).strip() for x in (content_schema.get("required_blocks") or []) if str(x).strip()]
    if schema_required:
        return schema_required
    schema = cts.get("schema") if isinstance(cts.get("schema"), dict) else {}
    pattern = [str(x).strip() for x in (schema.get("section_or_step_pattern") or []) if str(x).strip()]
    if pattern:
        return pattern
    rb = [str(x).strip() for x in (structure.get("required_blocks") or []) if str(x).strip()]
    if rb:
        return rb
    return _default_required_blocks(channel=channel, content_form=content_form, task_mode=task_mode)


def _normalize_title_token(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    out = []
    for ch in raw:
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
    return "".join(out)


def _project_body_blocks(required_blocks: List[str], schema_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    projected: List[Dict[str, Any]] = []
    available = [dict(item) for item in schema_blocks if isinstance(item, dict)]
    used = [False] * len(available)

    for title in required_blocks:
        clean_title = str(title or "").strip()
        if not clean_title:
            continue
        normalized_title = _normalize_title_token(clean_title)
        match: Dict[str, Any] | None = None
        for idx, item in enumerate(available):
            if used[idx]:
                continue
            candidate_title = str(item.get("title") or "").strip()
            normalized_candidate = _normalize_title_token(candidate_title)
            if not normalized_candidate or not normalized_title:
                continue
            if normalized_title in normalized_candidate or normalized_candidate in normalized_title:
                match = item
                used[idx] = True
                break
        projected.append(
            {
                "title": clean_title,
                "objective": str((match or {}).get("purpose") or (match or {}).get("objective") or "").strip(),
                "key_points": [str(x).strip() for x in ((match or {}).get("key_points") or []) if str(x).strip()][:8],
                "evidence_focus": [str(x).strip() for x in ((match or {}).get("evidence_focus") or []) if str(x).strip()][:8],
                "visual_hint": str((match or {}).get("visual_hint") or "none").strip().lower(),
            }
        )
    return projected


def normalize_minimal_spec(
    *,
    preset: ProfilePreset,
    compose_profile: ComposeProfile,
    output_spec: Dict[str, Any],
    task_ir: Dict[str, Any],
) -> ProfilePreset:
    p = preset.model_copy(deep=True)
    cts = _extract_content_task_spec(output_spec)
    content_schema = _extract_content_schema(output_spec)
    compose_policy = _extract_compose_policy(output_spec)
    task_mode = str((task_ir or {}).get("deliverable_mode") or "").strip().lower()
    channel = _infer_channel(output_spec, p)
    content_form = _infer_content_form(output_spec, p)
    try:
        _semantic = output_spec.get("semantic_delivery_profile") if isinstance(output_spec.get("semantic_delivery_profile"), dict) else {}
        _cts = _extract_content_task_spec(output_spec)
        _schema = _cts.get("schema") if isinstance(_cts.get("schema"), dict) else {}
        _medium = _cts.get("medium") if isinstance(_cts.get("medium"), dict) else {}
        _compose_for_log = _extract_compose_policy(output_spec)
        log_print(
            "[minimal_spec][content_form] final=%s channel=%s semantic_shape=%s semantic_form=%s "
            "cts_category=%s schema_type=%s surface=%s compose_form=%s preset_form=%s"
            % (
                content_form,
                channel,
                str(_semantic.get("delivery_shape") or ""),
                str(_semantic.get("content_form") or ""),
                str(_cts.get("category") or ""),
                str(_schema.get("type") or ""),
                str(_medium.get("surface") or ""),
                str(_compose_for_log.get("content_form") or ""),
                str((p.compose_policy or {}).get("content_form") or ""),
            ),
            flush=True,
        )
    except Exception:
        pass

    compose = dict(p.compose_policy or {})
    structure = dict(p.structure_contract or {})
    quality = dict(p.quality_gates or {})
    evidence = dict(p.evidence_policy or {})
    output = dict(p.output_contract or {})
    delivery_profile = _normalize_delivery_profile(compose_policy.get("delivery_profile"), fallback_channel=channel)
    visual_signals = _collect_visual_or_production_signals(
        content_task_spec=cts,
        compose_policy=compose_policy,
        content_schema=content_schema,
    )

    cts_audience = cts.get("audience") if isinstance(cts.get("audience"), dict) else {}
    cts_medium = cts.get("medium") if isinstance(cts.get("medium"), dict) else {}
    audience = str(
        compose_policy.get("audience")
        or compose.get("audience")
        or cts_audience.get("primary")
        or compose_profile.audience_model
        or "通用读者"
    ).strip()
    identity = str(p.identity or "").strip() or f"面向{audience}的{(content_form or 'article')}写作者，强调清晰、准确、可执行。"
    style_reference = dict(p.style_reference or {})
    style_desc = _build_style_description_by_priority(
        delivery_profile=delivery_profile,
        compose_style_description=str(compose_policy.get("style_description") or ""),
        preset_style_fallback=str(style_reference.get("positive") or compose_profile.intent_statement or ""),
    )
    style_reference["positive"] = _sanitize_reader_facing_text(str(
        style_desc
        or style_reference.get("positive")
        or "先回答问题，再结构化展开，并给出可执行建议。"
    )).strip()
    if not str(style_reference.get("negative") or "").strip():
        style_reference["negative"] = "避免空泛结论、术语堆砌和无依据判断。"

    anti_patterns = dict(p.anti_patterns or {})
    fw = [str(x).strip() for x in (anti_patterns.get("forbidden_words") or []) if str(x).strip()]
    if not fw:
        fw = ["绝对领先", "保证100%", "革命性颠覆"]
    anti_patterns["forbidden_words"] = fw
    if "meta_discourse_banned" not in anti_patterns:
        anti_patterns["meta_discourse_banned"] = False

    formatting_rules = dict(p.formatting_rules or {})
    if not formatting_rules:
        formatting_rules = {
            "max_paragraph_sentences": 4,
            "list_density": "medium",
            "emphasis_style": "minimal",
            "use_emojis": "none",
        }
    attention_budget = str(cts_audience.get("attention_budget") or "").strip().lower()
    consumption_mode = str(cts_medium.get("consumption_mode") or "").strip().lower()
    if attention_budget in {"mobile_medium", "short", "brief"} or consumption_mode == "mobile_read":
        formatting_rules["max_paragraph_sentences"] = min(3, int(formatting_rules.get("max_paragraph_sentences") or 3))
        formatting_rules["list_density"] = "high"

    required_blocks = _infer_required_blocks(p, output_spec, channel, content_form, task_mode)
    structure["required_blocks"] = required_blocks
    structure["section_count"] = int(structure.get("section_count") or len(required_blocks))
    structure.setdefault("outline_depth", 2)
    schema_blocks = list(content_schema.get("blocks") or []) if isinstance(content_schema, dict) else []
    normalized_blocks = _project_body_blocks(required_blocks, schema_blocks)
    if normalized_blocks:
        structure["blocks"] = normalized_blocks
        structure["schema_name"] = str(content_schema.get("schema_name") or "")
        structure["schema_type"] = str(content_schema.get("schema_type") or "")
        structure["schema_planning_mode"] = str(content_schema.get("planning_mode") or "")

    must_include_entries: List[Dict[str, str]] = [
        {"value": str(x).strip(), "source": "preset"}
        for x in (p.must_include or [])
        if str(x).strip()
    ]
    cts_constraints = cts.get("constraints") if isinstance(cts.get("constraints"), dict) else {}
    cts_required = [str(x).strip() for x in (cts_constraints.get("required_elements") or []) if str(x).strip()]
    if cts_required:
        must_include_entries.extend({"value": item, "source": "constraint"} for item in cts_required)
    writing_instructions = [str(x).strip() for x in (compose_policy.get("writing_instructions") or []) if str(x).strip()]
    if writing_instructions:
        must_include_entries.extend({"value": item, "source": "writing_instruction"} for item in writing_instructions)
    if not must_include_entries:
        must_include_entries = [
            {"value": "关键概念解释", "source": "fallback"},
            {"value": "可执行建议", "source": "fallback"},
        ]
    must_include: List[str] = []
    seen_must_include = set()
    for entry in must_include_entries:
        item = str(entry.get("value") or "").strip()
        if not item or item in seen_must_include:
            continue
        if _is_visual_or_production_requirement(
            item,
            source=str(entry.get("source") or ""),
            visual_signals=visual_signals,
        ):
            continue
        seen_must_include.add(item)
        must_include.append(item)

    compose["publish_channel"] = channel
    compose["content_form"] = content_form or "article"
    compose["delivery_profile"] = delivery_profile
    compose["tone"] = str(compose_policy.get("tone") or compose.get("tone") or "professional")
    compose["audience"] = str(
        compose_policy.get("audience")
        or compose.get("audience")
        or cts_audience.get("primary")
        or compose_profile.audience_model
        or ""
    )
    compose["style_description"] = _sanitize_reader_facing_text(str(
        style_desc
        or compose.get("style_description")
        or compose_profile.intent_statement
        or ""
    ))
    if str(cts_medium.get("delivery_expectation") or "").strip():
        compose["delivery_expectation"] = str(cts_medium.get("delivery_expectation") or "").strip()

    tc = output_spec.get("task_contract") if isinstance(output_spec.get("task_contract"), dict) else {}
    compose_citation = compose_policy.get("citation_required")
    if compose_citation is not None:
        evidence["citation_required"] = bool(compose_citation)
    else:
        cts_research = cts.get("research_requirements") if isinstance(cts.get("research_requirements"), dict) else {}
        if cts_research:
            evidence["citation_required"] = bool(cts_research.get("required"))
        base_evidence_mode = str(tc.get("evidence_mode") or "").strip().lower()
        if base_evidence_mode == "required":
            evidence["citation_required"] = True
        elif base_evidence_mode in ["optional", "none", ""]:
            evidence["citation_required"] = bool(evidence.get("citation_required"))
        elif "citation_required" not in evidence:
            evidence["citation_required"] = False

    gp = output_spec.get("generation_policy") if isinstance(output_spec.get("generation_policy"), dict) else {}
    cts_constraints_hard = cts_constraints.get("hard_constraints") if isinstance(cts_constraints, dict) else {}
    # When the preset was synthesised dynamically, the synthesiser sized
    # quality_gates for the deliverable type (e.g. resume 350-700). Letting
    # the upstream compose_policy / generation_policy defaults override that
    # was the root of "everything ends up in document_scale_compose at
    # 2600 target_words" — a hard-coded long-form preset shape leaking back
    # into short-form deliverables. For dynamic source, synth wins.
    is_dynamic_source = str(getattr(p, "source", "") or "").strip().lower() == "dynamic"
    synth_min = quality.get("min_words")
    synth_max = quality.get("max_words")
    # Widen: for dynamic preset, respect synth as long as EITHER side is set.
    # Previously required both — when synth set only one, fell back to the
    # 1200/2600 (or 1400/4500) article/report defaults and silently inflated
    # short-form deliverables (resume, email) into long-form shape.
    if is_dynamic_source and (synth_min is not None or synth_max is not None):
        if synth_min is not None and synth_max is not None:
            target_min = synth_min
            target_max = synth_max
        elif synth_min is not None:
            target_min = synth_min
            target_max = max(int(synth_min) * 2, int(synth_min) + 300)
        else:
            target_max = synth_max
            target_min = max(int(synth_max) // 2, max(1, int(synth_max) - 300))
    else:
        target_min = compose_policy.get("min_words") if compose_policy.get("min_words") is not None else gp.get("min_words")
        target_max = compose_policy.get("max_words") if compose_policy.get("max_words") is not None else gp.get("max_words")
        if target_min is None and isinstance(cts_constraints_hard, dict) and cts_constraints_hard.get("min_words") is not None:
            target_min = cts_constraints_hard.get("min_words")
        if target_max is None and isinstance(cts_constraints_hard, dict) and cts_constraints_hard.get("max_words") is not None:
            target_max = cts_constraints_hard.get("max_words")

    if target_min is not None:
        min_words = int(target_min)
    elif is_dynamic_source:
        # Dynamic source with no synth/upstream signal: use a conservative
        # short-form floor rather than article/report defaults, so unknown
        # types (resume, email, manual) don't get pushed into long-form.
        min_words = int(quality.get("min_words") or 400)
    else:
        min_words = int(quality.get("min_words") or (1400 if content_form == "report" else 1200))

    if target_max is not None:
        max_words = int(target_max)
    elif is_dynamic_source:
        max_words = int(quality.get("max_words") or 1200)
    else:
        max_words = int(quality.get("max_words") or (4500 if content_form == "report" else 2600))

    if max_words < min_words:
        max_words = min_words + 600
        
    quality["min_words"] = min_words
    quality["max_words"] = max_words
    quality.setdefault("style_consistency_min", 0.72)
    quality.setdefault("structure_coverage_min", 0.85)
    quality["must_include"] = must_include

    visual_contract = dict((p.visual_contract.model_dump() if hasattr(p.visual_contract, "model_dump") else p.visual_contract) or {})
    density = dict(visual_contract.get("density") or {})
    if not density:
        density = {}
    inferred_density = _infer_visual_density_targets(
        compose_policy=compose_policy,
        content_task_spec=cts,
        min_words=min_words,
        max_words=max_words,
        is_dynamic_source=is_dynamic_source,
    )
    min_images = max(0, int(density.get("min_images") or 0), int(inferred_density.get("min_images") or 0))
    max_images = max(0, int(density.get("max_images") or 0), int(inferred_density.get("max_images") or 0))
    if max_images and min_images and max_images < min_images:
        max_images = min_images
    density["min_images"] = min_images
    density["max_images"] = max_images
    visual_contract["density"] = density
    style_constraints = dict(visual_contract.get("style_constraints") or {})
    style_constraints.pop("required_visual_types", None)
    style_constraints.pop("optional_visual_types", None)
    style_constraints["require_images"] = bool(min_images > 0)
    visual_contract["style_constraints"] = style_constraints

    output.setdefault("format", "markdown")
    deliverable = str(task_ir.get("deliverable_mode") or output.get("deliverable") or compose.get("content_form") or "").strip().lower()
    if content_form == "report" or deliverable in {"report", "document", "document_scale", "prd", "whitepaper", "handbook"}:
        output["deliverable"] = "report"
    elif content_form == "plan":
        output["deliverable"] = "plan"
    elif content_form == "brief" or deliverable in {"brief", "memo"}:
        output["deliverable"] = "brief"
    else:
        output["deliverable"] = deliverable or "article"

    forbidden_patterns = [str(x).strip() for x in (p.forbidden_patterns or []) if str(x).strip()]
    forbidden_patterns.extend([x for x in fw if x])
    forbidden_patterns = list(dict.fromkeys(forbidden_patterns))

    p.identity = identity
    p.style_reference = style_reference
    p.must_include = must_include
    p.anti_patterns = anti_patterns
    p.formatting_rules = formatting_rules
    p.compose_policy = compose
    p.structure_contract = structure
    p.evidence_policy = evidence
    p.visual_contract = VisualContract.model_validate(visual_contract)
    p.quality_gates = quality
    p.output_contract = output
    p.forbidden_patterns = forbidden_patterns
    p.metadata = dict(p.metadata or {})
    p.metadata["spec_mode"] = "minimal_v1"
    try:
        log_print(
            "[minimal_spec][exit] source=%s content_form=%s min/max=%s/%s "
            "section_count=%s numbering=%s blocks=%s min_imgs=%s"
            % (
                str(getattr(p, "source", "") or ""),
                str(content_form or ""),
                quality.get("min_words"),
                quality.get("max_words"),
                structure.get("section_count"),
                structure.get("numbering_style"),
                json.dumps(list(structure.get("required_blocks") or []), ensure_ascii=False),
                density.get("min_images"),
            ),
            flush=True,
        )
    except Exception:
        pass
    return p
