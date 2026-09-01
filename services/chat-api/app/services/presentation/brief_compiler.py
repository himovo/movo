from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.services.presentation.contracts import (
    StoryDeckPlan,
    ConstraintBundle,
    DeckBrief,
    FreeformPageBlueprint,
    PageBrief,
    SkillConstraint,
)
from app.services.presentation.story_planner import (
    collect_grounding_observations,
    resolve_grounding_strictness,
)


class BriefCompiler:
    """Compile internal structured state into natural-language briefs for LLM calls."""

    _BASE_RULES = [
        "Every page must be renderable and visibly complete.",
        "Preserve strong hierarchy, clear focal points, and deck-level continuity.",
        "Respect the user's requested outline, order, and generation intent.",
        "Avoid empty pages, invisible structures, and layout drift across the deck.",
    ]
    _BASE_DECK_GUIDANCE = [
        "Treat the deck as one coherent narrative rather than isolated pages.",
        "Keep terminology, argument progression, and visual language consistent.",
        "Vary composition rhythm across nearby pages while preserving the same design language.",
    ]
    _BASE_PAGE_GUIDANCE = [
        "Each page needs a headline zone, a dominant visual move, and supporting evidence or explanation.",
        "Use graphics, shapes, containers, or structure to make the page presentation-ready instead of text-only.",
        "Make the visible blocks carry the page; do not rely on metadata to imply layout.",
        "Use renderer-native style language such as background, border color, border radius, text alignment, vertical alignment, shadows, and line weight.",
        "For connector lines, think in real endpoints and directional structure rather than tiny decorative ticks.",
    ]
    _BASE_ANTI_PATTERNS = [
        "Do not produce text-only report pages.",
        "Do not repeat the same composition on adjacent pages.",
        "Do not use weak equal-weight mirrored layouts unless the brief clearly demands it.",
        "Do not use decorative title underline accent lines.",
        "Do not default to center-radial teaching diagrams unless the page truly requires a hub-and-spoke concept map.",
    ]
    _BASE_QA_CHECKS = [
        "The page should have visible hierarchy and no effectively empty groups.",
        "Text should stay readable with strong contrast and sensible size contrast.",
        "Avoid wireframe-like layouts, oversized empty areas, and unclear visual anchors.",
        "The page should feel filled and presentation-ready, not sparse or under-occupied.",
    ]

    def build_constraint_bundle(
        self,
        *,
        output_spec: Dict[str, Any],
        user_outline: str,
        user_generation_guidance: str,
        user_message_context: str,
    ) -> ConstraintBundle:
        bundle = ConstraintBundle(
            user_outline=user_outline,
            user_generation_guidance=user_generation_guidance,
            user_message_context=user_message_context,
            base_rules=list(self._BASE_RULES),
            deck_guidance=list(self._BASE_DECK_GUIDANCE),
            page_guidance=list(self._BASE_PAGE_GUIDANCE),
            anti_patterns=list(self._BASE_ANTI_PATTERNS),
            qa_checks=list(self._BASE_QA_CHECKS),
            skill_constraints=self._extract_skill_constraints(output_spec),
            tool_observations=collect_grounding_observations(output_spec),
        )

        compose_policy = output_spec.get("compose_policy") if isinstance(output_spec.get("compose_policy"), dict) else {}
        effective_policy = output_spec.get("effective_policy") if isinstance(output_spec.get("effective_policy"), dict) else {}
        effective_compose = effective_policy.get("compose_policy") if isinstance(effective_policy.get("compose_policy"), dict) else {}
        generation_policy = output_spec.get("generation_policy") if isinstance(output_spec.get("generation_policy"), dict) else {}
        presentation_policy = compose_policy.get("presentation_policy") if isinstance(compose_policy.get("presentation_policy"), dict) else {}
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        schema = content_task_spec.get("schema") if isinstance(content_task_spec.get("schema"), dict) else {}
        section_specs = [
            item for item in list(schema.get("section_specs") or [])
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]

        writing_instructions = self._listify(compose_policy.get("writing_instructions"))
        required_sections = self._listify(compose_policy.get("required_sections"))
        generation_style = [
            self._scalar_line("Content form", compose_policy.get("content_form")),
            self._scalar_line("Publish channel", compose_policy.get("publish_channel")),
            self._scalar_line("Delivery rhetoric", (compose_policy.get("delivery_profile") or {}).get("rhetoric_style") if isinstance(compose_policy.get("delivery_profile"), dict) else ""),
            self._scalar_line("Narrative density", (compose_policy.get("delivery_profile") or {}).get("narrative_density") if isinstance(compose_policy.get("delivery_profile"), dict) else ""),
            self._scalar_line("Scannability", (compose_policy.get("delivery_profile") or {}).get("scannability") if isinstance(compose_policy.get("delivery_profile"), dict) else ""),
            self._scalar_line("Presentation design intent", presentation_policy.get("design_intent")),
            self._scalar_line("Presentation theme mode", presentation_policy.get("theme_mode")),
            self._scalar_line("Generation tone", generation_policy.get("tone")),
        ]
        for item in generation_style:
            if item:
                bundle.deck_guidance.append(item)

        if writing_instructions:
            bundle.deck_guidance.append(f"Runtime writing instructions: {' | '.join(writing_instructions[:10])}.")
            bundle.page_guidance.append(f"Per-page writing instructions to preserve: {' | '.join(writing_instructions[:10])}.")
        if required_sections:
            bundle.deck_guidance.append(f"Required deck sections or blocks: {' | '.join(required_sections[:10])}.")
        if section_specs:
            bundle.deck_guidance.append(
                "Section plan from upstream contract: "
                + " | ".join(
                    f"{idx}. {str(item.get('title') or '').strip()}"
                    for idx, item in enumerate(section_specs, start=1)
                )
                + "."
            )
        if effective_compose:
            delivery = effective_compose.get("delivery_profile") if isinstance(effective_compose.get("delivery_profile"), dict) else {}
            semantic = delivery.get("semantic_profile") if isinstance(delivery, dict) else {}
            semantic_lines = [
                self._scalar_line("Resolved content form", effective_compose.get("content_form")),
                self._scalar_line("Resolved publish channel", effective_compose.get("publish_channel")),
                self._scalar_line("Resolved hook strength", delivery.get("hook_strength") if isinstance(delivery, dict) else ""),
                self._scalar_line("Resolved visual density", delivery.get("visual_density") if isinstance(delivery, dict) else ""),
                self._scalar_line("Resolved semantic audience", semantic.get("audience") if isinstance(semantic, dict) else ""),
                self._scalar_line("Resolved semantic outcome", semantic.get("target_outcome") if isinstance(semantic, dict) else ""),
            ]
            for item in semantic_lines:
                if item:
                    bundle.deck_guidance.append(item)

        strictness = resolve_grounding_strictness(output_spec)
        # Grounding policy only activates when there are actually observations
        # to ground on. No search hits + no uploaded documents → the LLM has
        # to write from its own knowledge; strict/free/hybrid all collapse to
        # "free composition" in that case, so emit no grounding guidance.
        if bundle.tool_observations:
            if strictness == "strict":
                bundle.deck_guidance.append(
                    "Grounding policy: STRICT. Every specific factual claim (numbers, names, dates, direct quotes, concrete events) on every "
                    "page must be directly supported by the upstream tool observations listed in the constraint brief or by the explicit user "
                    "request. The user's requested page count and deck structure must still be honored — strict mode is a fact-level rule, "
                    "not a page-count rule. Fill each page using: multiple complementary angles on the same evidence, structural framing "
                    "(context / implication / outlook), paraphrased restatements, and visual compositions. Never invent a figure, name, date, "
                    "event, or claim that is absent from the evidence. If a specific fact is genuinely missing, omit that fact — do not mark "
                    "the whole page as 'no data found'."
                )
            elif strictness == "free":
                bundle.deck_guidance.append(
                    "Grounding policy: FREE. Tool observations are a helpful reference; you may elaborate beyond them where it improves "
                    "the deck. Still avoid fabricating specific numbers or direct quotes that aren't in the evidence."
                )
            else:
                bundle.deck_guidance.append(
                    "Grounding policy: HYBRID. Factual statements across the deck must be grounded in the upstream tool observations; "
                    "paraphrase them rather than inventing unsourced figures, names, or claims. You may still supply narrative structure "
                    "and commonsense framing."
                )
            bundle.deck_guidance.append(
                "The evidence_id tokens shown in the constraint brief (ev_1, ev_2, doc_XXX, …) are internal reference labels for your reasoning only. "
                "Never write them into any slide content: not in page_title, page_subtitle, key_message, headline, bullet, caption, or narrative. "
                "Readers must never see strings such as '(ev_1)', '[ev_2]', or 'ev_3'. Render every grounded fact in natural, audience-ready prose."
            )
            if strictness == "strict":
                bundle.qa_checks.append(
                    "Every specific factual statement (number, name, date, quote, concrete event) on every page must map to a tool observation "
                    "or the explicit user request. Unsupported specific claims must be rewritten to paraphrase what the evidence actually says, "
                    "or removed entirely — but pages themselves must not be dropped unless the user also asked to reduce page count."
                )
            else:
                bundle.qa_checks.append(
                    "No factual claim may contradict the tool observations or go materially beyond what they support."
                )
            bundle.qa_checks.append(
                "No rendered text on any page may contain the raw evidence_id tokens (ev_1, ev_2, doc_*, …)."
            )
        bundle.deck_guidance = self._dedupe(bundle.deck_guidance)
        bundle.page_guidance = self._dedupe(bundle.page_guidance)
        bundle.anti_patterns = self._dedupe(bundle.anti_patterns)
        bundle.qa_checks = self._dedupe(bundle.qa_checks)
        return bundle

    def compile_story_plan_brief(self, story_plan: StoryDeckPlan) -> str:
        lines = [
            f"Deck id: {story_plan.deck_id}",
            f"Deck goal: {story_plan.deck_goal}",
            f"Audience: {story_plan.target_audience}",
            f"Context: {story_plan.presentation_context}",
            f"Language: {story_plan.language}",
        ]
        if list(story_plan.narrative_outline or []):
            lines.append(
                "Narrative outline: " + " -> ".join(str(item).strip() for item in list(story_plan.narrative_outline or []) if str(item).strip())
            )
        page_lines: List[str] = []
        for page in list(story_plan.pages or []):
            page_lines.append(
                (
                    f"{page.page_index}. {page.page_id} | type={page.page_type} | "
                    f"intent={page.page_intent} | goal={page.communication_goal} | "
                    f"message={page.key_message} | visual={page.visual_intent} | role={page.narrative_role}"
                ).strip()
            )
        if page_lines:
            lines.append("Planned page sequence:\n" + "\n".join(page_lines))
        return "\n".join(line for line in lines if str(line or "").strip()).strip()

    def compile_constraint_brief(self, bundle: ConstraintBundle) -> str:
        lines = [
            "Base engine rules:",
            *[f"- {item}" for item in bundle.base_rules],
        ]
        if bundle.user_outline:
            lines.extend(["User outline to honor:", bundle.user_outline])
        if bundle.user_generation_guidance:
            lines.extend(["User generation guidance to honor:", bundle.user_generation_guidance])
        if bundle.user_message_context:
            lines.extend(["Recent user message context:", bundle.user_message_context])
        if bundle.tool_observations:
            lines.append("Upstream tool observations (search/RAG evidence — ground claims here, do not fabricate):")
            for obs in bundle.tool_observations:
                ev = str(obs.get("evidence_id") or "").strip()
                tool = str(obs.get("tool") or "").strip()
                src = str(obs.get("source_label") or "").strip()
                summary = str(obs.get("summary") or "").strip()
                header = f"- [{ev}]"
                if tool:
                    header += f" tool={tool}"
                if src:
                    header += f" source={src}"
                lines.append(header)
                if summary:
                    lines.append(f"    {summary}")
        if bundle.deck_guidance:
            lines.extend(["Deck-level creative guidance:"] + [f"- {item}" for item in bundle.deck_guidance])
        if bundle.page_guidance:
            lines.extend(["Page-level creative guidance:"] + [f"- {item}" for item in bundle.page_guidance])
        if bundle.qa_checks:
            lines.extend(["Quality bar:"] + [f"- {item}" for item in bundle.qa_checks])
        for item in sorted(bundle.skill_constraints, key=lambda entry: entry.priority, reverse=True):
            lines.extend(self._skill_constraint_lines(item))
        return "\n".join(line for line in lines if str(line or "").strip()).strip()

    def compile_deck_creative_brief(self, deck_brief: DeckBrief, bundle: ConstraintBundle) -> str:
        tokens = deck_brief.design_tokens
        lines = [
            f"Deck goal: {deck_brief.deck_goal}",
            f"Audience: {deck_brief.target_audience}",
            f"Context: {deck_brief.presentation_context}",
            f"User outline: {deck_brief.user_outline}",
            f"User generation guidance: {deck_brief.user_generation_guidance}",
        ]
        if deck_brief.theme_factory_name:
            lines.append(f"Theme factory selection: {deck_brief.theme_factory_name}")
        if deck_brief.theme_factory_rationale:
            lines.append(f"Theme rationale: {deck_brief.theme_factory_rationale}")
        if deck_brief.theme_factory_colors:
            lines.append(
                "Theme color palette: "
                + ", ".join(
                    f"{k}={v}" for k, v in deck_brief.theme_factory_colors.items() if str(v).strip()
                )
            )
        if deck_brief.theme_factory_typography:
            lines.append(
                "Theme typography: "
                + ", ".join(
                    f"{k}={v}" for k, v in deck_brief.theme_factory_typography.items() if str(v).strip()
                )
            )
        if list(deck_brief.narrative_arc or []):
            lines.append("Narrative arc: " + " -> ".join(str(item).strip() for item in list(deck_brief.narrative_arc or []) if str(item).strip()))
        if list(deck_brief.continuity_rules or []):
            lines.append("Continuity rules: " + " | ".join(str(item).strip() for item in list(deck_brief.continuity_rules or []) if str(item).strip()))
        if list(deck_brief.visual_direction or []):
            lines.append("Deck-level design language: " + " | ".join(str(item).strip() for item in list(deck_brief.visual_direction or []) if str(item).strip()))
        lines.append(
            "Theme palette reference (guidance, not rigid lock): "
            f"primary {tokens.primary_color}, secondary {tokens.secondary_color}, accent {tokens.accent_color}, "
            f"recommended page background {tokens.page_background}, optional surface tint {tokens.surface_background}, "
            f"title color {tokens.title_color}, body color {tokens.body_color}, muted color {tokens.muted_color}. "
            "Use these as a coherent palette family, but choose page-level combinations by content readability and hierarchy."
        )
        lines.append(
            "Style baseline reference: "
            f"title size about {tokens.title_font_size}px, subtitle size about {tokens.subtitle_font_size}px, body size about {tokens.body_font_size}px, "
            f"border radius about {tokens.card_border_radius}px, border width about {tokens.border_width}px, line weight about {tokens.line_weight}px, "
            f"shadow style {tokens.shadow_style}, font family {tokens.font_family}, layout density {tokens.layout_density}."
        )
        lines.extend(["Compiled constraint brief:", self.compile_constraint_brief(bundle)])
        return "\n".join(line for line in lines if str(line or "").strip()).strip()

    def compile_page_creative_brief(
        self,
        *,
        page_brief: PageBrief,
        previous_page: PageBrief | None,
        next_page: PageBrief | None,
        prior_pages: List[FreeformPageBlueprint],
        bundle: ConstraintBundle,
    ) -> str:
        lines = [f"Current page id: {page_brief.page_id}"]
        def add_labeled(label: str, value: str) -> None:
            if str(value or "").strip():
                lines.append(f"{label}: {str(value).strip()}")

        add_labeled("Page mission", page_brief.page_goal)
        add_labeled("Key takeaway", page_brief.key_takeaway)
        add_labeled("Visual intent", page_brief.visual_intent)
        add_labeled("Composition intent", page_brief.composition_intent)
        add_labeled("Narrative role", page_brief.narrative_role)
        add_labeled("Visual center", page_brief.visual_center)
        add_labeled("Dominant move", page_brief.dominant_move)
        add_labeled("Validation profile", page_brief.validation_profile)
        if page_brief.must_visualize:
            lines.append("Must visualize: " + " | ".join(item for item in page_brief.must_visualize if item))
        if page_brief.must_include:
            lines.append("Must include: " + " | ".join(item for item in page_brief.must_include if item))
        page_avoid = self._dedupe(list(page_brief.must_avoid or []) + list(bundle.anti_patterns or []))
        if page_avoid:
            lines.append("Must avoid: " + " | ".join(page_avoid))
        continuity_notes = self._dedupe(list(page_brief.continuity_notes or []))
        if continuity_notes:
            lines.append("Continuity notes: " + " | ".join(continuity_notes))
        if page_brief.source_outline_section:
            lines.append(f"Relevant outline section: {page_brief.source_outline_section}")
        if page_brief.source_user_intent:
            lines.append(f"Relevant user intent: {page_brief.source_user_intent}")
        if previous_page is not None:
            lines.append(
                f"Previous page context: {previous_page.page_id} advances '{previous_page.key_takeaway}' using '{previous_page.composition_intent}'."
            )
        if next_page is not None:
            lines.append(
                f"Next page context: {next_page.page_id} will advance '{next_page.key_takeaway}' using '{next_page.composition_intent}'."
            )
        if prior_pages:
            lines.append(
                "Recent realized page patterns to vary away from: "
                + " | ".join(self._page_pattern(page) for page in prior_pages[-3:])
            )
        if bundle.page_guidance:
            lines.append("Page-level guidance: " + " | ".join(bundle.page_guidance))
        if bundle.qa_checks:
            lines.append("Quality checks before you finish: " + " | ".join(bundle.qa_checks))
        return "\n".join(line for line in lines if str(line or "").strip()).strip()

    def compile_critic_brief(self, *, page_brief: PageBrief, bundle: ConstraintBundle) -> str:
        lines = [f"Critique this page for page id {page_brief.page_id}."]
        if str(page_brief.page_goal or "").strip():
            lines.append(f"The page's mission is: {page_brief.page_goal}")
        if str(page_brief.key_takeaway or "").strip():
            lines.append(f"The key takeaway must be: {page_brief.key_takeaway}")
        if str(page_brief.visual_intent or "").strip():
            lines.append(f"Visual intent: {page_brief.visual_intent}")
        if bundle.qa_checks:
            lines.append("Quality checklist: " + " | ".join(bundle.qa_checks))
        return "\n".join(line for line in lines if str(line or "").strip()).strip()

    def _extract_skill_constraints(self, output_spec: Dict[str, Any]) -> List[SkillConstraint]:
        constraints: List[SkillConstraint] = []
        for item in list(output_spec.get("skill_constraints") or []):
            if isinstance(item, dict):
                constraints.append(self._constraint_from_payload(item, source="explicit_skill_constraints"))
        selected_user_skill = output_spec.get("selected_user_skill")
        if isinstance(selected_user_skill, dict) and selected_user_skill:
            constraints.append(self._constraint_from_payload(selected_user_skill, source="selected_user_skill"))
        selected_skill = output_spec.get("selected_skill")
        if isinstance(selected_skill, dict) and selected_skill:
            constraints.append(self._constraint_from_payload(selected_skill, source="selected_skill"))
        compose_policy = output_spec.get("compose_policy") if isinstance(output_spec.get("compose_policy"), dict) else {}
        presentation_policy = compose_policy.get("presentation_policy") if isinstance(compose_policy.get("presentation_policy"), dict) else {}
        if presentation_policy:
            constraints.append(
                SkillConstraint(
                    source="presentation_policy",
                    skill_name=str(compose_policy.get("presentation_skill_name") or compose_policy.get("write_skill_name") or "presentation").strip(),
                    intent_rules=self._collect_strings(
                        presentation_policy,
                        keys=("design_intent", "production_mode", "theme_mode"),
                    ),
                    priority=60,
                )
            )
        return [item for item in constraints if self._constraint_has_content(item)]

    def _constraint_from_payload(self, payload: Dict[str, Any], *, source: str) -> SkillConstraint:
        return SkillConstraint(
            source=source,
            skill_name=str(
                payload.get("skill_name")
                or payload.get("name")
                or payload.get("title")
                or payload.get("id")
                or source
            ).strip(),
            intent_rules=self._collect_strings(payload, keys=("intent_rules", "rules", "constraints", "instructions", "guidance")),
            style_guidance=self._collect_strings(payload, keys=("style_guidance", "design_guidance", "visual_guidance", "description")),
            layout_preferences=self._collect_strings(payload, keys=("layout_preferences", "layout_guidance", "preferred_layouts")),
            anti_patterns=self._collect_strings(payload, keys=("anti_patterns", "avoid", "must_avoid")),
            qa_checks=self._collect_strings(payload, keys=("qa_checks", "quality_checks", "acceptance_checks")),
            priority=int(payload.get("priority") or 50),
        )

    def _skill_constraint_lines(self, item: SkillConstraint) -> List[str]:
        lines = [f"Active skill constraint from {item.source} ({item.skill_name}):"]
        if item.intent_rules:
            lines.extend(f"- {entry}" for entry in item.intent_rules)
        if item.style_guidance:
            lines.append("Style guidance from this skill:")
            lines.extend(f"- {entry}" for entry in item.style_guidance)
        if item.layout_preferences:
            lines.append("Layout preferences from this skill:")
            lines.extend(f"- {entry}" for entry in item.layout_preferences)
        if item.anti_patterns:
            lines.append("Avoid because of this skill:")
            lines.extend(f"- {entry}" for entry in item.anti_patterns)
        if item.qa_checks:
            lines.append("Quality checks from this skill:")
            lines.extend(f"- {entry}" for entry in item.qa_checks)
        return lines

    def _constraint_has_content(self, item: SkillConstraint) -> bool:
        return bool(
            item.intent_rules
            or item.style_guidance
            or item.layout_preferences
            or item.anti_patterns
            or item.qa_checks
        )

    def _collect_strings(self, payload: Dict[str, Any], *, keys: Iterable[str]) -> List[str]:
        values: List[str] = []
        for key in keys:
            raw = payload.get(key)
            values.extend(self._listify(raw))
        return self._dedupe(values)

    def _listify(self, raw: Any) -> List[str]:
        values: List[str] = []
        if isinstance(raw, str):
            text = raw.strip()
            if text:
                values.append(text)
        elif isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(value, (str, int, float)) and str(value).strip():
                    values.append(f"{str(key).strip()}: {str(value).strip()}")
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    values.append(item.strip())
                elif isinstance(item, dict):
                    for key, value in item.items():
                        if isinstance(value, (str, int, float)) and str(value).strip():
                            values.append(f"{str(key).strip()}: {str(value).strip()}")
        return self._dedupe(values)

    def _dedupe(self, values: Iterable[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    def _scalar_line(self, label: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return f"{label}: {text}."

    def _page_pattern(self, page: FreeformPageBlueprint) -> str:
        block_types = [str(block.type or "").strip().lower() for block in list(page.blocks or [])[:6]]
        return (
            f"{str(page.page_id or '').strip()} uses layout '{str(page.layout_type or '').strip()}' "
            f"with blocks {', '.join(block_types)}"
        ).strip()
