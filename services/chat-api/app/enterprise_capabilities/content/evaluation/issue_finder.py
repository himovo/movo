"""Stage 2: read content with the standards as a rubric, list violations.

The finder is told to be honest about pass/fail. It does not rate the
content on a 0-1 scale — it lists which standards are violated and how.
The verdict is derived from issue severities, not from a number.
"""
from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, decision_commentary_dict, invoke_structured_decision
from app.llm.types import Message, Role
from app.enterprise_capabilities.content.evaluation.contracts import Issue, Severity, Standard
from app.enterprise_capabilities.content.evaluation.outcomes import EvaluationStageOutcome


class _FoundIssue(BaseModel):
    standard_id: str = ""
    severity: Severity = "major"
    location: str = "全文"
    finding: str = ""
    fix_suggestion: str = ""


class _FoundIssues(DecisionOutput):
    issues: List[_FoundIssue]


_SYSTEM_PROMPT_DOCUMENT = (
    "You are a strict content reviewer. You will be given:\n"
    "  - a list of standards (each with id, severity, description)\n"
    "  - a piece of content (markdown)\n"
    "\n"
    "Identify which standards the content FAILS to meet. Be honest: if the "
    "content meets all standards, return an empty issues array. Do NOT invent "
    "issues to look thorough.\n"
    "\n"
    "For each violated standard, return one Issue:\n"
    "  - standard_id: the id of the standard (must match exactly)\n"
    "  - severity: copy the standard's severity unless the actual violation "
    "    is clearly less severe than the rule (then you may downgrade)\n"
    "  - location: where in the content (section name, or '全文' if it's a "
    "    document-wide problem)\n"
    "  - finding: ONE concrete sentence on what is wrong\n"
    "  - fix_suggestion: ONE concrete sentence on how to fix it\n"
    "\n"
    "Skip standards that are met. Do not list passes.\n"
    "Language: match the content's language for finding/fix_suggestion.\n"
    "\n"
    "Return strict JSON with shape {\"issues\": [...]}."
)


_SYSTEM_PROMPT_SECTION = (
    "You are reviewing ONE section of a longer document, not the whole thing.\n"
    "\n"
    "You will be given:\n"
    "  - a list of standards written for the FULL document\n"
    "  - the markdown of a SINGLE section\n"
    "\n"
    "CRITICAL: only flag standards this section can be reasonably expected to\n"
    "satisfy. SKIP standards that are inherently document-wide and cannot be\n"
    "judged from one section alone. Examples of standards to SKIP at section\n"
    "scope:\n"
    "  - total word count / overall length / 篇幅\n"
    "  - structural completeness (\"必须包含板块 A B C D\")\n"
    "  - opening / closing structure (\"开头必须是 X\" / \"结尾必须给出建议\")\n"
    "  - cross-section coherence (\"前后呼应\" / \"判断框架贯穿全文\")\n"
    "Standards to EVALUATE at section scope:\n"
    "  - factual accuracy / evidence usage WITHIN this section's claims\n"
    "  - clarity / specificity / concreteness of THIS section's content\n"
    "  - this section addressing what its own title implies\n"
    "  - tone / register WITHIN this section\n"
    "  - presence of vague filler / placeholder phrasing in this section\n"
    "\n"
    "Be honest: if this section satisfies the standards that apply to it,\n"
    "return an empty issues array. Do NOT invent issues, and do NOT flag\n"
    "document-level standards just because this section alone doesn't satisfy\n"
    "them.\n"
    "\n"
    "For each violated standard return one Issue (same shape as document review):\n"
    "  - standard_id, severity, location (section name or specific paragraph),\n"
    "  - finding (one concrete sentence), fix_suggestion (one concrete sentence).\n"
    "\n"
    "Language: match the content's language. Return strict JSON {\"issues\": [...]}."
)


class IssueFinder:
    """Returns a list of Issues for a given content + standards bundle."""

    def __init__(self) -> None:
        self._llm = get_request_scoped_llm_client(streaming=False, stage="planning")

    async def find_outcome(
        self,
        *,
        content: str,
        standards: List[Standard],
        scope: str = "document",
        commentary_sink: Optional[Callable[[Dict[str, str]], Awaitable[None] | None]] = None,
    ) -> EvaluationStageOutcome[Issue]:
        """Find issues against the given standards.

        scope:
          "document" — content is the full deliverable. All standards apply.
          "section"  — content is one section of a longer document. The LLM
                       is instructed to skip document-level standards (total
                       length, full structural completeness, opening/closing
                       structure) that a single section cannot satisfy.
        """
        body = (content or "").strip()
        if not body or not standards:
            return EvaluationStageOutcome()

        # Truncate very long content to keep prompt cost bounded. Issues found
        # in the first 8000 chars are usually representative; we'll re-evaluate
        # after repair anyway.
        truncated = body[:8000]

        system_prompt = (
            _SYSTEM_PROMPT_SECTION if scope == "section" else _SYSTEM_PROMPT_DOCUMENT
        )
        payload = {
            "standards": [s.model_dump() for s in standards],
            "content": truncated,
        }
        try:
            res = await invoke_structured_decision(
                self._llm,
                _FoundIssues,
                [
                    Message(role=Role.SYSTEM, content=system_prompt),
                    Message(
                        role=Role.USER,
                        content=json.dumps(payload, ensure_ascii=False),
                    ),
                ],
                spec=DecisionTurnSpec(
                    locale="zh" if any("\u4e00" <= char <= "\u9fff" for char in body) else "en",
                    turn_id=f"quality.issues.{scope}",
                    sink=commentary_sink,
                ),
            )
        except Exception as exc:
            log_print(f"[content_evaluation][issues] find failed: {exc}", flush=True)
            return EvaluationStageOutcome.failed(exc)

        if not isinstance(res, _FoundIssues):
            return EvaluationStageOutcome.failed(TypeError("invalid issues response"))

        valid_ids = {s.id for s in standards}
        out: List[Issue] = []
        for item in res.issues or []:
            sid = (item.standard_id or "").strip()
            if sid not in valid_ids:
                # Drop hallucinated standard ids — keeps the contract honest.
                continue
            finding = (item.finding or "").strip()
            if not finding:
                continue
            out.append(
                Issue(
                    standard_id=sid,
                    severity=item.severity or "major",
                    location=(item.location or "全文").strip() or "全文",
                    finding=finding,
                    fix_suggestion=(item.fix_suggestion or "").strip(),
                )
            )

        try:
            log_print(
                "[content_evaluation][issues] found count=%s severities=%s"
                % (
                    len(out),
                    json.dumps([i.severity for i in out]),
                ),
                flush=True,
            )
            for i in out:
                log_print(
                    "[content_evaluation][issues]   %s [%s] @ %s — %s"
                    % (i.standard_id, i.severity, i.location, i.finding),
                    flush=True,
                )
        except Exception:
            pass
        return EvaluationStageOutcome(items=out, commentary=decision_commentary_dict(res.commentary))

    async def find(
        self,
        *,
        content: str,
        standards: List[Standard],
        scope: str = "document",
    ) -> List[Issue]:
        outcome = await self.find_outcome(content=content, standards=standards, scope=scope)
        return list(outcome.items)
