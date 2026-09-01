"""Story planner for presentation pipeline.

Migrated from V4 story_planner — identical planning logic, but all imports
point to contracts and llm_utils so the pipeline no longer depends
on any V4 module.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.services.presentation.contracts import StoryDeckPlan, StoryPageSpec
from app.services.presentation.llm_utils import invoke_structured

logger = logging.getLogger(__name__)


class _StoryGroundingReview(BaseModel):
    faithful: bool = True
    issues: List[str] = Field(default_factory=list)
    corrected_plan: StoryDeckPlan | None = None


def _truncate(value: Any, limit: int | None) -> str:
    raw = str(value or "").strip()
    if limit is None or limit <= 0 or len(raw) <= limit:
        return raw
    return raw[:limit] + "...<truncated>"


# Default caps are intentionally generous; callers that want to stream a full
# internal knowledge base as the sole factual ground can set the limits to 0
# (unlimited) via output_spec.tool_observations_policy.
_DEFAULT_MAX_OBSERVATIONS = 64
_DEFAULT_MAX_SUMMARY_CHARS = 2000
_DEFAULT_MAX_SOURCE_CHARS = 240
_DEFAULT_MAX_TOOL_CHARS = 80


def _observation_policy(output_spec: Dict[str, Any] | None) -> Dict[str, int]:
    """Resolve observation compaction limits. 0 or negative means unlimited.

    Read from output_spec.tool_observations_policy so callers (e.g. enterprise
    deployments that want to ground fully on internal RAG) can override caps.
    """
    policy = (output_spec or {}).get("tool_observations_policy")
    if not isinstance(policy, dict):
        policy = {}

    def _coerce(key: str, default: int) -> int:
        try:
            return int(policy.get(key, default))
        except (TypeError, ValueError):
            return default

    return {
        "max_items": _coerce("max_items", _DEFAULT_MAX_OBSERVATIONS),
        "summary_chars": _coerce("summary_chars", _DEFAULT_MAX_SUMMARY_CHARS),
        "source_chars": _coerce("source_chars", _DEFAULT_MAX_SOURCE_CHARS),
        "tool_chars": _coerce("tool_chars", _DEFAULT_MAX_TOOL_CHARS),
    }


def _document_observation_items(output_spec: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    """Convert uploaded documents in output_spec.documents.parsed_documents
    into tool-observation-shaped dicts so the grounding layer can treat
    them identically to web_search / RAG evidence. Produces raw (un-truncated)
    items; compaction limits are applied by the caller.
    """
    if not isinstance(output_spec, dict):
        return []
    documents = output_spec.get("documents")
    if not isinstance(documents, dict):
        return []
    parsed = documents.get("parsed_documents")
    if not isinstance(parsed, list):
        return []

    items: List[Dict[str, Any]] = []
    for idx, doc in enumerate(parsed, start=1):
        if not isinstance(doc, dict):
            continue
        if str(doc.get("parse_status") or "").strip() not in {"", "parsed", "ready", "ok"}:
            continue
        profile = doc.get("profile") if isinstance(doc.get("profile"), dict) else {}
        # Prefer the full markdown body so the deck can be grounded on the
        # actual document content. Fallbacks keep us useful when the parser
        # only returned a brief.
        body = (
            doc.get("markdown")
            or doc.get("inline_markdown")
            or profile.get("active_context_brief")
            or profile.get("summary")
            or ""
        )
        if not str(body).strip():
            continue
        asset_id = str(doc.get("asset_id") or "").strip()
        evidence_id = f"doc_{asset_id}" if asset_id else f"doc_{idx}"
        title = (
            str(profile.get("title") or "").strip()
            or str(doc.get("filename") or "").strip()
            or str(doc.get("source_url") or "").strip()
            or evidence_id
        )
        items.append(
            {
                "evidence_id": evidence_id,
                "tool": "uploaded_document",
                "summary": str(body),
                "source_label": title,
            }
        )
    return items


def compact_tool_observations(
    observations: List[Dict[str, Any]],
    *,
    output_spec: Dict[str, Any] | None = None,
) -> List[Dict[str, str]]:
    """Normalize upstream tool observations (web search, RAG, etc.) into a
    uniform per-item form suitable for LLM prompts.

    Limits are read from output_spec.tool_observations_policy; set any limit to
    0 (or negative) to disable the corresponding cap — useful for enterprises
    that want to ground fully on internal data without losing fidelity.
    """
    policy = _observation_policy(output_spec)
    max_items = policy["max_items"]
    summary_chars = policy["summary_chars"] or None
    source_chars = policy["source_chars"] or None
    tool_chars = policy["tool_chars"] or None

    # Sentinel strings emitted by tools when a search/retrieval produced no
    # results. These must not be forwarded to the LLM as evidence — they
    # actively mislead the model into thinking a second source exists.
    _EMPTY_SENTINELS = (
        "no valid information found",
        "no results found",
        "search returned no results",
        "未找到有效信息",
        "未检索到",
        "没有找到相关",
        "no information found",
    )

    def _is_empty_evidence_text(text: str) -> bool:
        t = (text or "").strip().lower()
        if len(t) < 20:
            return True
        return any(sentinel in t for sentinel in _EMPTY_SENTINELS)

    items: List[Dict[str, str]] = []
    for idx, item in enumerate(observations or [], start=1):
        if not isinstance(item, dict):
            continue
        # Tools invoked via the subagent delegate path emit shape
        # ``{"tool": <name>, "result": <raw tool output>}`` where ``result`` is
        # the authoritative payload. For web_search it is a formatted markdown
        # digest string; for RAG it may be a dict or list. Coerce that into a
        # single summary string so downstream prompts see the actual evidence
        # text instead of an empty placeholder.
        result_obj = item.get("result")
        result_summary = ""
        result_source = ""
        if isinstance(result_obj, str):
            result_summary = result_obj
        elif isinstance(result_obj, dict):
            result_summary = (
                str(result_obj.get("summary") or "")
                or str(result_obj.get("answer") or "")
                or str(result_obj.get("content") or "")
                or str(result_obj.get("text") or "")
            )
            result_source = (
                str(result_obj.get("source_label") or "")
                or str(result_obj.get("source") or "")
                or str(result_obj.get("title") or "")
                or str(result_obj.get("url") or "")
            )
            if not result_summary:
                # Last-resort: serialise the whole dict so the LLM at least sees
                # the raw structured evidence.
                try:
                    import json as _json
                    result_summary = _json.dumps(result_obj, ensure_ascii=False)[:4000]
                except Exception:
                    result_summary = ""
        elif isinstance(result_obj, list):
            try:
                import json as _json
                result_summary = _json.dumps(result_obj, ensure_ascii=False)[:4000]
            except Exception:
                result_summary = ""

        merged_summary = (
            item.get("summary")
            or item.get("content")
            or item.get("observation")
            or result_summary
            or ""
        )
        # Drop empty / failure-sentinel evidence so downstream prompts don't
        # get confused by phantom sources.
        if _is_empty_evidence_text(str(merged_summary)):
            continue

        items.append(
            {
                "evidence_id": str(item.get("evidence_id") or f"ev_{idx}"),
                "tool": _truncate(item.get("tool") or item.get("name") or "", tool_chars),
                "summary": _truncate(merged_summary, summary_chars),
                "source_label": _truncate(
                    item.get("source_label")
                    or item.get("source")
                    or item.get("title")
                    or result_source
                    or "",
                    source_chars,
                ),
            }
        )
        if max_items and len(items) >= max_items:
            break
    return items


def _log_grounding_resolution(explicit: str, writing_mode: str, resolved: str) -> None:
    logger.info(
        "presentation_grounding_strictness resolved=%s explicit_from_compose_policy=%s writing_mode=%s",
        resolved,
        explicit or "(empty)",
        writing_mode or "(empty)",
    )


def _log_llm_grounding_dump(*, stage: str, payload: Dict[str, Any]) -> None:
    """Dump a compact preview of the grounding evidence that is about to be
    sent to an LLM call. Emits WARNING level so it is visible under the
    default backend log filter.

    Shows:
      * count of observations
      * each observation's evidence_id + tool + source_label
      * a short prefix of the summary so it is obvious the actual search /
        document text is reaching the model (not just the tag metadata).
    """
    runtime_hints = payload.get("runtime_hints") if isinstance(payload, dict) else None
    if not isinstance(runtime_hints, dict):
        return
    observations = runtime_hints.get("tool_observations")
    if not isinstance(observations, list):
        return
    strictness = runtime_hints.get("grounding_strictness") or "(n/a)"
    previews: List[str] = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        ev = str(obs.get("evidence_id") or "")
        tool = str(obs.get("tool") or "")
        src = str(obs.get("source_label") or "")
        summary = str(obs.get("summary") or "").replace("\n", " ")
        summary_preview = summary[:160] + ("…" if len(summary) > 160 else "")
        previews.append(
            f"[{ev}] tool={tool or '-'} source={src or '-'} summary={summary_preview!r}"
        )
    logger.debug(
        "presentation_llm_grounding_dump stage=%s strictness=%s observation_count=%s\n  %s",
        stage,
        strictness,
        len(previews),
        "\n  ".join(previews) if previews else "(none)",
    )


def resolve_grounding_strictness(output_spec: Dict[str, Any] | None) -> str:
    """Resolve the grounding policy for the current request.

    Returns one of ``"strict"`` / ``"hybrid"`` / ``"free"``. Sources, in
    priority order:

    1. Explicit ``compose_policy.grounding_strictness`` extracted by the
       upstream semantic-policy LLM (set when the user's message explicitly
       demands or waives strict grounding).
    2. Upstream ``content_task_spec.writing_mode`` — ``evidence_bound`` is
       treated as strict (user uploaded documents or cited a specific source).
    3. Default ``"hybrid"`` — evidence binds specific facts, LLM supplies
       narrative scaffolding and commonsense framing.
    """
    if not isinstance(output_spec, dict):
        return "hybrid"
    compose = output_spec.get("compose_policy") if isinstance(output_spec.get("compose_policy"), dict) else {}
    explicit = str(compose.get("grounding_strictness") or "").strip().lower()
    content_task_spec = (
        output_spec.get("content_task_spec")
        if isinstance(output_spec.get("content_task_spec"), dict)
        else {}
    )
    writing_mode = str(content_task_spec.get("writing_mode") or "").strip().lower()
    if explicit in {"strict", "hybrid", "free"}:
        _log_grounding_resolution(explicit, writing_mode, explicit)
        return explicit
    if writing_mode == "evidence_bound":
        _log_grounding_resolution(explicit, writing_mode, "strict")
        return "strict"
    _log_grounding_resolution(explicit, writing_mode, "hybrid")
    return "hybrid"


def collect_grounding_observations(
    output_spec: Dict[str, Any] | None,
) -> List[Dict[str, str]]:
    """Gather every piece of factual grounding available in output_spec and
    return them as a uniform list of compacted tool-observation dicts.

    Merges (in priority order):
      1. output_spec.tool_observations  — web_search / RAG / other tool hits
      2. output_spec.documents.parsed_documents  — user-uploaded files
         (.docx / .pdf / etc.) converted into observation-shaped items whose
         `summary` carries the full parsed markdown body.

    Both streams go through the same compaction policy
    (output_spec.tool_observations_policy), so enterprise deployments can set
    `summary_chars=0, max_items=0` to feed full uploaded documents into the
    PPT pipeline without truncation.
    """
    if not isinstance(output_spec, dict):
        return []
    raw_observations: List[Dict[str, Any]] = []
    existing = output_spec.get("tool_observations")
    tool_count = 0
    if isinstance(existing, list):
        tool_hits = [x for x in existing if isinstance(x, dict)]
        raw_observations.extend(tool_hits)
        tool_count = len(tool_hits)
    doc_items = _document_observation_items(output_spec)
    raw_observations.extend(doc_items)
    compacted = compact_tool_observations(raw_observations, output_spec=output_spec)
    logger.info(
        "presentation_grounding_observations tool_hits=%s document_items=%s compacted=%s "
        "sample_sources=%s",
        tool_count,
        len(doc_items),
        len(compacted),
        [str(o.get("source_label") or o.get("evidence_id") or "")[:60] for o in compacted[:5]],
    )
    return compacted


class StoryPlanner:
    def _last_user_text(self, messages: List[Any], output_spec: Dict[str, Any]) -> str:
        for message in reversed(list(messages or [])):
            if not isinstance(message, dict):
                continue
            if str(message.get("role") or "").strip() != "user":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                parts: List[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("type") or "").strip() != "text":
                        continue
                    text = str(item.get("text") or "").strip()
                    if text:
                        parts.append(text)
                if parts:
                    return "\n".join(parts).strip()
        return str((output_spec or {}).get("user_request") or "").strip()

    def _content_task_context(self, output_spec: Dict[str, Any]) -> Dict[str, Any]:
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        schema = content_task_spec.get("schema") if isinstance(content_task_spec.get("schema"), dict) else {}
        audience = content_task_spec.get("audience") if isinstance(content_task_spec.get("audience"), dict) else {}
        goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
        medium = content_task_spec.get("medium") if isinstance(content_task_spec.get("medium"), dict) else {}
        section_specs: List[Dict[str, Any]] = []
        for item in list(schema.get("section_specs") or []):
            if not isinstance(item, dict):
                continue
            section_specs.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "role": str(item.get("role") or "").strip(),
                    "purpose": str(item.get("purpose") or "").strip(),
                    "must_cover_topics": [str(x).strip() for x in list(item.get("must_cover_topics") or []) if str(x).strip()][:8],
                    "visual_need": str(item.get("visual_need") or "").strip(),
                }
            )
        return {
            "execution_kind": str(content_task_spec.get("execution_kind") or "").strip(),
            "writing_mode": str(content_task_spec.get("writing_mode") or "").strip(),
            "audience": {
                "primary": str(audience.get("primary") or "").strip(),
                "expertise_level": str(audience.get("expertise_level") or "").strip(),
                "decision_role": str(audience.get("decision_role") or "").strip(),
                "attention_budget": str(audience.get("attention_budget") or "").strip(),
            },
            "goal": {
                "primary_action": str(goal.get("primary_action") or "").strip(),
                "goal_type": str(goal.get("goal_type") or "").strip(),
                "outcome": str(goal.get("outcome") or "").strip(),
            },
            "medium": {
                "channel": str(medium.get("channel") or "").strip(),
                "surface": str(medium.get("surface") or "").strip(),
                "consumption_mode": str(medium.get("consumption_mode") or "").strip(),
            },
            "schema": {
                "name": str(schema.get("name") or "").strip(),
                "rationale": str(schema.get("rationale") or "").strip(),
                "section_specs": section_specs[:12],
                "section_or_step_pattern": [str(x).strip() for x in list(schema.get("section_or_step_pattern") or []) if str(x).strip()][:16],
            },
        }

    def _runtime_hints(self, output_spec: Dict[str, Any]) -> Dict[str, Any]:
        compose_policy = output_spec.get("compose_policy") if isinstance(output_spec.get("compose_policy"), dict) else {}
        answer_plan = output_spec.get("answer_plan") if isinstance(output_spec.get("answer_plan"), dict) else {}
        goal_contract = output_spec.get("goal_contract") if isinstance(output_spec.get("goal_contract"), dict) else {}
        return {
            "language": str(output_spec.get("language") or "").strip(),
            "target_audience": str(output_spec.get("target_audience") or "").strip(),
            "deck_goal": str(output_spec.get("deck_goal") or "").strip(),
            "presentation_context": str(output_spec.get("presentation_context") or "").strip(),
            "use_agenda": output_spec.get("use_agenda"),
            "compose_policy": {
                "audience": str(compose_policy.get("audience") or "").strip(),
                "content_form": str(compose_policy.get("content_form") or "").strip(),
                "required_sections": [str(x).strip() for x in list(compose_policy.get("required_sections") or []) if str(x).strip()][:16],
                "writing_instructions": [str(x).strip() for x in list(compose_policy.get("writing_instructions") or []) if str(x).strip()][:12],
            },
            "answer_plan_sections": list(answer_plan.get("sections") or []),
            "goal_contract": goal_contract,
            "tool_observations": collect_grounding_observations(output_spec),
            "grounding_strictness": resolve_grounding_strictness(output_spec),
        }

    def _payload(self, *, messages: List[Any], output_spec: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "user_request": self._last_user_text(messages, output_spec),
            "content_task_spec": self._content_task_context(output_spec),
            "runtime_hints": self._runtime_hints(output_spec),
            "allowed_page_types": ["cover", "agenda", "section_divider", "content", "thank_you"],
            "allowed_page_intents": [
                "introduce_topic",
                "frame_problem",
                "explain_solution",
                "compare_options",
                "show_architecture",
                "show_process",
                "show_roadmap",
                "show_metrics",
                "show_case",
                "ask_for_decision",
                "close_gratitude",
            ],
            "v4_principles": {
                "composition_driven": True,
                "no_page_templates": True,
                "special_pages_are_allowed": True,
            },
        }

    def _prompt(self) -> str:
        return (
            "You are the story planner for Presentation Pipeline.\n"
            "Return JSON only matching StoryDeckPlan.\n"
            "Plan a spoken slide deck narrative, not an article outline.\n"
            "Principles:\n"
            "- The deck will be built by LLM-selected atomic components, not fixed page templates.\n"
            "- Your job is to produce the narrative plan only: page intent, page role, density, evidence mode, and sequence.\n"
            "Hard rules:\n"
            "- Use only the allowed page_type and page_intent values provided in the payload.\n"
            "- The first page must be cover.\n"
            "- If an agenda page is used, it must appear immediately after cover.\n"
            "- The last page must be thank_you.\n"
            "- Use at most one agenda page.\n"
            "- Every page must have one communication_goal, key_message, visual_intent, and narrative_role.\n"
            "- Preserve the user's actual topic, language, and audience. Do not genericize a concrete topic into a vague project deck.\n"
            "- If content_task_spec contains explicit section specs, preserve their coverage unless they directly conflict with the user request.\n"
            "- Keep page count tight. No padding pages.\n"
            "- Prefer concrete scenario, evidence, comparison, process, roadmap, case, and decision pages when relevant.\n"
            "- Distinguish adjacent pages by narrative function. Avoid repeating the same job across neighboring pages.\n"
            "- cover and thank_you are special pages; all other pages should be content-driving and composable.\n"
            "- Honor the user's requested page count and deck structure regardless of grounding mode. "
            "The grounding policy controls what facts may appear INSIDE each page, not whether a page exists. "
            "If the user asked for 10 pages, produce 10 pages.\n"
            "- Grounding policy applies only when runtime_hints.tool_observations is non-empty. "
            "If there are no observations, treat the deck as a free-composition task driven by the user request and content_task_spec alone. "
            "When observations exist, follow runtime_hints.grounding_strictness — applied at the fact level, never to override page count:\n"
            "    • strict — every specific factual claim (numbers, names, dates, direct quotes, concrete events) on every page MUST be "
            "directly supported by runtime_hints.tool_observations or the explicit user request. To fill the user's requested page count, "
            "use: multiple complementary angles on the same evidence, structural framing (context/implication/outlook), paraphrased "
            "restatements, and visual compositions. You may introduce neutral organizing language (e.g. 'the following sources indicate', "
            "'based on the available record') but never invent a figure, name, date, event, or claim that is not in the evidence. "
            "If a specific fact is genuinely not in the evidence, omit that fact — do not mark the whole page as 'no data found'.\n"
            "    • hybrid (default when empty) — tool_observations bind specific facts (numbers, names, direct claims); you may still "
            "supply narrative structure, commonsense framing, and genre-standard scaffolding. Do not invent figures, names, or claims "
            "beyond evidence, user request, or content_task_spec.\n"
            "    • free — tool_observations are a helpful reference; you may elaborate beyond them where it improves the deck.\n"
            "- The evidence_id tokens (ev_1, ev_2, doc_XXX, …) are reference tags for your internal reasoning only — never surface them "
            "to the audience, never paste them into any page content, title, subtitle, key_message, or narrative text. "
            "Phrase the grounded facts in natural language as if the data came from your own synthesis.\n"
        )

    def _grounding_prompt(self) -> str:
        return (
            "You review a story plan for grounding fidelity.\n"
            "Return JSON only matching _StoryGroundingReview.\n"
            "Set faithful=false if the plan drifts from the user's concrete topic, audience, language, or requested structure.\n"
            "If not faithful, provide corrected_plan that fully fixes the drift while keeping the rules.\n"
        )

    def _normalize(self, plan: StoryDeckPlan, *, user_request: str) -> StoryDeckPlan:
        deck_id = str(plan.deck_id or "").strip()
        if not deck_id:
            plan.deck_id = f"deck_{uuid.uuid4().hex[:10]}"
        if not str(plan.language or "").strip():
            plan.language = "zh-CN" if re.search(r"[\u4e00-\u9fff]", user_request) else "en-US"
        normalized_pages: List[StoryPageSpec] = []
        for index, page in enumerate(list(plan.pages or []), start=1):
            page.page_index = index
            if not str(page.page_id or "").strip():
                page.page_id = f"page_{index:02d}"
            normalized_pages.append(page)
        plan.pages = normalized_pages
        if not str(plan.deck_goal or "").strip():
            plan.deck_goal = user_request[:120] or "Presentation"
        if not str(plan.target_audience or "").strip():
            plan.target_audience = "general audience"
        return plan

    async def build(self, *, messages: List[Any], output_spec: Dict[str, Any]) -> StoryDeckPlan:
        payload = self._payload(messages=messages, output_spec=output_spec)
        _log_llm_grounding_dump(stage="story_planner", payload=payload)
        plan = await invoke_structured(
            model_cls=StoryDeckPlan,
            system_prompt=self._prompt(),
            payload=payload,
            stage="presentation_story",
            intent="generation",
        )
        review = await invoke_structured(
            model_cls=_StoryGroundingReview,
            system_prompt=self._grounding_prompt(),
            payload={
                "user_request": payload.get("user_request"),
                "story_plan": plan.model_dump(),
                "content_task_spec": payload.get("content_task_spec"),
                "runtime_hints": payload.get("runtime_hints"),
            },
            stage="presentation_story_grounding",
            intent="quality",
        )
        if not review.faithful and review.corrected_plan and review.corrected_plan.pages:
            plan = review.corrected_plan
        return self._normalize(plan, user_request=str(payload.get("user_request") or ""))
