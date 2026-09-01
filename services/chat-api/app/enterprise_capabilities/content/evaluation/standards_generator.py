"""Stage 1: turn a user request into 5-8 verifiable standards.

The generator NEVER sees the produced content — only the user's request.
This keeps standards from being silently tailored to whatever the writer
happened to produce.
"""
from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, decision_commentary_dict, invoke_structured_decision
from app.llm.types import Message, Role
from app.enterprise_capabilities.content.evaluation.contracts import Severity, Standard
from app.enterprise_capabilities.content.evaluation.outcomes import EvaluationStageOutcome
from app.enterprise_capabilities.content.profile_presets.prompt_constraints import CONTENT_REVIEW_VISUAL_BOUNDARY


class _GeneratedStandard(BaseModel):
    severity: Severity = "major"
    description: str = ""
    anti_example: str = ""


class _GeneratedStandards(DecisionOutput):
    standards: List[_GeneratedStandard] = Field(min_length=5, max_length=8)


_SYSTEM_PROMPT = (
    "You are a content quality reviewer. Given a user's content request, "
    "produce 5-8 VERIFIABLE evaluation standards that the resulting content "
    "must satisfy. Quality > quantity — five strong standards beat eight weak "
    "ones.\n"
    "\n"
    "Each standard:\n"
    "  - severity: critical (deliverable fundamentally fails without it), "
    "    major (clearly wrong but not deal-breaking), minor (polish).\n"
    "  - description: ONE concrete sentence a reviewer can decide pass/fail "
    "    on by looking at the content. NOT subjective ('内容应清晰' is bad). "
    "    Concrete ('包含联系方式且至少给出电话与邮箱' is good).\n"
    "  - anti_example: optional one-line example of failing this standard.\n"
    "\n"
    "Tailor standards to the deliverable type. A resume needs different "
    "standards than a research report or an internal email. Use the user's "
    "request to infer the type — do not assume.\n"
    "\n"
    "If a selected writing skill/profile context is provided in the user "
    "message, treat it as writing requirements for this task, not as source "
    "material to quote. Incorporate its structure, required elements, "
    "forbidden elements, tone, and scenario into the standards when relevant. "
    "Priority order: explicit user request > selected user writing skill > "
    "organization writing skill > dynamic/generated profile. If the user "
    "explicitly conflicts with the skill/profile, follow the user request and "
    "do not create a standard for the overridden lower-priority rule.\n"
    "\n"
    "Skip standards about cover page, TOC, numbering style, fonts, or any "
    "rendering concerns — those are handled elsewhere. Focus on what makes "
    "the CONTENT itself good for its purpose.\n"
    "Do NOT generate content-quality standards about export completion, "
    "download links, attachment availability, or final file formats such as "
    ".docx/.doc/.pdf/.pptx/.xlsx. Those are artifact/render requirements "
    "checked after content repair/export; this stage evaluates only the "
    "written content.\n"
    "For article or document requests, do NOT create standards requiring generated illustrations, image counts, image slots, or image placement. Generated visuals are deferred until after the written body passes this content review. Visual-only deliverables are not covered by this exception.\n"
    "\n"
    "Interpret count constraints carefully: phrases like 'include/包含 N "
    "sections/headings/items' mean the content must cover those N requested "
    "items, not that it may contain ONLY or EXACTLY N items. Generate an "
    "exclusive/exact-count standard only when the user explicitly says "
    "'only', 'exactly', '仅', '只', '仅包含', '只有', '不要其他', or an equivalent "
    "exclusion phrase.\n"
    "\n"
    "CRITICAL — do NOT fabricate or anchor 'facts' from system traces. The "
    "user's request is the ONLY source of facts. Anything that looks like a "
    "tool output / internal status / debug log / pipeline trace (e.g. "
    "'Completed research_collection_skill: All steps in current frame "
    "completed', 'Subagent N_S1 succeeded', 'Plan resolved with confidence "
    "0.92', or any English/JSON-shaped status sentence that doesn't read "
    "like natural user prose) MUST be ignored. Never produce a standard "
    "that requires the content to quote, cite, or anchor such a string. If "
    "the user's request itself doesn't supply a factual claim, do NOT "
    "invent one and require the content to honor it.\n"
    "\n"
    "Language: write standards in the same language as the user's request "
    "(zh in, zh out; en in, en out).\n"
    "\n"
    "Return strict JSON with shape {\"standards\": [...]}."
) + "\n\n" + CONTENT_REVIEW_VISUAL_BOUNDARY


def _few_shot_examples() -> str:
    """Concrete examples to anchor the LLM on what 'verifiable' means."""
    return (
        "Examples (do not copy verbatim — adapt to each new request):\n"
        "\n"
        "Request: '帮我写一份后端工程师简历，5年经验'\n"
        "Standards:\n"
        "  - critical | 包含完整联系方式（至少姓名 + 电话/邮箱二选一）\n"
        "  - critical | 包含工作经历且按时间倒序排列\n"
        "  - major | 工作经历每项至少 1 条量化业绩（QPS/性能提升/规模数字）\n"
        "  - major | 技能栈与岗位方向匹配（后端工程师应出现 Java/Go/数据库等）\n"
        "  - minor | 教育背景信息含学校与专业\n"
        "\n"
        "Request: '帮我写一份产品故障分析报告'\n"
        "Standards:\n"
        "  - critical | 明确说明故障现象、影响范围、发生时间窗口\n"
        "  - critical | 给出根因分析，不只是描述现象\n"
        "  - major | 提供已采取的临时缓解措施与后续根治方案\n"
        "  - major | 包含时间线（发现 → 定位 → 缓解 → 恢复）\n"
        "  - minor | 给出改进建议或预防措施\n"
        "\n"
        "Request: '帮我写一封请假邮件给领导'\n"
        "Standards:\n"
        "  - critical | 含称呼与落款（敬上/此致敬礼）\n"
        "  - critical | 明确请假原因与时间段\n"
        "  - major | 说明工作安排或交接\n"
        "  - minor | 字数控制在 80-300 字之间\n"
    )


class StandardsGenerator:
    """Generates a list of Standards from the user's request."""

    def __init__(self) -> None:
        self._llm = get_request_scoped_llm_client(streaming=False, stage="planning")

    async def generate_outcome(
        self,
        *,
        user_request: str,
        skill_context: Optional[Dict[str, Any]] = None,
        commentary_sink: Optional[Callable[[Dict[str, str]], Awaitable[None] | None]] = None,
    ) -> EvaluationStageOutcome[Standard]:
        request = (user_request or "").strip()
        if not request:
            return EvaluationStageOutcome()

        system = _SYSTEM_PROMPT + "\n\n" + _few_shot_examples()
        user_payload = request
        if isinstance(skill_context, dict) and skill_context:
            compact_context = json.dumps(skill_context, ensure_ascii=False, default=str)[:6000]
            user_payload = (
                f"User request:\n{request}\n\n"
                "Selected writing skill/profile context for standards generation "
                "(requirements, not source facts):\n"
                f"{compact_context}\n\n"
                "Generate the standards from both the user request and this context, "
                "using the priority rules from the system message."
            )
        try:
            res = await invoke_structured_decision(
                self._llm,
                _GeneratedStandards,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=user_payload),
                ],
                spec=DecisionTurnSpec(
                    locale=detect_language(request),
                    turn_id="quality.standards",
                    sink=commentary_sink,
                ),
            )
        except Exception as exc:
            log_print(f"[content_evaluation][standards] generation failed: {exc}", flush=True)
            return EvaluationStageOutcome.failed(exc)

        if not isinstance(res, _GeneratedStandards):
            return EvaluationStageOutcome.failed(TypeError("invalid standards response"))

        out: List[Standard] = []
        for idx, item in enumerate(res.standards or [], start=1):
            desc = (item.description or "").strip()
            if not desc:
                continue
            out.append(
                Standard(
                    id=f"std_{idx:03d}",
                    severity=item.severity or "major",
                    description=desc,
                    anti_example=(item.anti_example or "").strip(),
                )
            )
        try:
            log_print(
                "[content_evaluation][standards] generated count=%s severities=%s"
                % (
                    len(out),
                    json.dumps([s.severity for s in out]),
                ),
                flush=True,
            )
            for s in out:
                log_print(
                    "[content_evaluation][standards]   %s [%s] %s"
                    % (s.id, s.severity, s.description),
                    flush=True,
                )
        except Exception:
            pass
        return EvaluationStageOutcome(items=out, commentary=decision_commentary_dict(res.commentary))

    async def generate(self, *, user_request: str, skill_context: Optional[Dict[str, Any]] = None) -> List[Standard]:
        outcome = await self.generate_outcome(user_request=user_request, skill_context=skill_context)
        return list(outcome.items)


def detect_language(text: str) -> str:
    """Used by downstream stages to keep prompt language consistent."""
    return "zh" if re.search(r"[一-鿿]", text or "") else "en"
