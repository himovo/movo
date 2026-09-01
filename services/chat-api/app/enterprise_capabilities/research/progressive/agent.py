from __future__ import annotations

import inspect
import json
import logging
from typing import Any

from app.llm.factory import get_request_scoped_llm_client
from app.llm.decision_turn import DecisionTurnSpec, invoke_json_decision
from app.llm.types import Message, Role
from app.enterprise_capabilities.research.progressive.json_utils import coerce_json_object, unique_strings
from app.enterprise_capabilities.research.progressive.models import (
    EvidenceItem,
    ProgressiveResearchResult,
    RejectedSource,
    ResearchTurnDecision,
    SearchCandidate,
)
from app.enterprise_capabilities.research.progressive.provider_router import ProviderRouter
from app.enterprise_capabilities.research.progressive.decision_guard import (
    is_semantically_empty_decision,
    recovery_queries,
)
from app.enterprise_capabilities.research.progressive.evidence_store import ResearchEvidenceStore
from app.infrastructure.execution_events.operation import operation_event
from app.enterprise_capabilities.research.progressive.temporal_context import (
    build_research_temporal_context,
    evidence_judging_temporal_guidance,
    query_planning_temporal_guidance,
)


logger = logging.getLogger(__name__)


class ProgressiveResearchAgent:
    def __init__(
        self,
        *,
        provider_router: ProviderRouter | None = None,
        llm: Any | None = None,
        max_rounds: int = 3,
        max_queries_per_round: int = 4,
        max_results_per_query: int = 8,
        max_evidence: int = 16,
        freshness_days: int = 30,
        progress_callback: Any | None = None,
    ) -> None:
        self.provider_router = provider_router or ProviderRouter()
        self.llm = llm or get_request_scoped_llm_client(
            streaming=False,
            intent="task",
            stage="progressive_research",
        )
        self.max_rounds = max(1, min(6, int(max_rounds or 3)))
        self.max_queries_per_round = max(1, min(8, int(max_queries_per_round or 4)))
        self.max_results_per_query = max(1, min(20, int(max_results_per_query or 8)))
        self.max_evidence = max(1, min(40, int(max_evidence or 16)))
        self.temporal_context = build_research_temporal_context(freshness_days=freshness_days)
        self.progress_callback = progress_callback

    async def run(self, *, query: str, user_query: str = "", language: str = "zh") -> ProgressiveResearchResult:
        original_query = str(user_query or query or "").strip()
        seed_query = str(query or user_query or "").strip()
        if not original_query and not seed_query:
            return ProgressiveResearchResult(ok=False, error="empty_query")

        evidence_store = ResearchEvidenceStore(output_limit=self.max_evidence)
        accepted = evidence_store.items
        rejected: list[RejectedSource] = []
        trace: list[dict[str, Any]] = []
        providers_used: set[str] = set()
        next_queries = await self._plan_initial_queries(original_query or seed_query, language=language)
        if not next_queries:
            next_queries = [seed_query or original_query]
        seen_queries: set[str] = set()
        logger.info(
            "progressive_research_started query=%r initial_queries=%s max_rounds=%s",
            (original_query or seed_query)[:200],
            next_queries,
            self.max_rounds,
            extra={
                "event": "progressive_research.started",
                "query": (original_query or seed_query)[:500],
                "initial_queries": list(next_queries),
                "max_rounds": self.max_rounds,
                "max_results_per_query": self.max_results_per_query,
            },
        )
        await self._emit_progress(
            language=language,
            message=(
                f"开始深度研究：规划了 {len(next_queries)} 个搜索问题"
                if str(language or "").startswith("zh")
                else f"Starting progressive research with {len(next_queries)} search questions"
            ),
            detail="progressive_research_started",
        )

        rounds = 0
        done = False
        budget_exhausted = False
        for round_index in range(1, self.max_rounds + 1):
            queries = []
            for q in unique_strings(next_queries, limit=self.max_queries_per_round):
                key = q.lower()
                if key in seen_queries:
                    continue
                seen_queries.add(key)
                queries.append(q)
            if not queries:
                logger.info(
                    "progressive_research_round_skipped round=%s reason=no_new_queries",
                    round_index,
                    extra={"event": "progressive_research.round_skipped", "round": round_index, "reason": "no_new_queries"},
                )
                break

            rounds = round_index
            logger.info(
                "progressive_research_round_started round=%s queries=%s accepted_so_far=%s",
                round_index,
                queries,
                len(accepted),
                extra={
                    "event": "progressive_research.round_started",
                    "round": round_index,
                    "queries": list(queries),
                    "accepted_so_far": len(accepted),
                },
            )
            await self._emit_progress(
                language=language,
                message=(
                    f"第 {round_index} 轮研究：搜索 {len(queries)} 个问题"
                    if str(language or "").startswith("zh")
                    else f"Research round {round_index}: searching {len(queries)} questions"
                ),
                detail="progressive_research_round_started",
            )
            search_operation_id = f"operation_research_search_{round_index}"
            await self._emit_operation(
                state="started",
                operation_id=search_operation_id,
                label=queries[0],
                category="search",
                detail={"round": round_index, "query_count": len(queries), "queries": list(queries)},
            )
            candidates, provider_trace = await self.provider_router.search(
                queries,
                max_results_per_query=self.max_results_per_query,
            )
            trace.extend([{"round": round_index, **item} for item in provider_trace])
            providers_used.update(str(item.get("provider") or "") for item in provider_trace if item.get("provider"))
            await self._emit_operation(
                state="completed",
                operation_id=search_operation_id,
                label=queries[0],
                category="search",
                detail={"round": round_index, "candidate_count": len(candidates)},
            )
            if not candidates:
                logger.info(
                    "progressive_research_round_no_candidates round=%s provider_trace=%s",
                    round_index,
                    provider_trace,
                    extra={
                        "event": "progressive_research.round_no_candidates",
                        "round": round_index,
                        "provider_trace": provider_trace,
                    },
                )
                next_queries = []
                continue
            await self._emit_progress(
                language=language,
                message=(
                    f"第 {round_index} 轮检索完成：获得 {len(candidates)} 条候选资料"
                    if str(language or "").startswith("zh")
                    else f"Round {round_index} search complete: {len(candidates)} candidate sources"
                ),
                detail="progressive_research_candidates_ready",
            )

            review_operation_id = f"operation_research_review_{round_index}"
            review_label = "筛选候选资料" if str(language or "").startswith("zh") else "Review candidate sources"
            await self._emit_operation(
                state="started",
                operation_id=review_operation_id,
                label=review_label,
                category="verify",
                detail={"round": round_index, "candidate_count": len(candidates)},
            )
            decision = await self._judge_turn(
                original_query=original_query or seed_query,
                language=language,
                round_index=round_index,
                candidates=candidates,
                accepted=accepted,
            )
            await self._emit_operation(
                state="completed",
                operation_id=review_operation_id,
                label=review_label,
                category="verify",
                detail={"round": round_index, "accepted_count": len(decision.accepted_evidence), "done": bool(decision.done)},
            )
            if is_semantically_empty_decision(decision):
                logger.warning(
                    "progressive_research_invalid_empty_decision round=%s candidates=%s",
                    round_index,
                    len(candidates),
                    extra={
                        "event": "progressive_research.invalid_empty_decision",
                        "round": round_index,
                        "candidate_count": len(candidates),
                    },
                )
                if round_index < self.max_rounds:
                    next_queries = recovery_queries(
                        research_goal=seed_query or original_query,
                        attempted_queries=seen_queries,
                        language=language,
                        limit=self.max_queries_per_round,
                    )
                    await self._emit_progress(
                        language=language,
                        message=(
                            "本轮未形成有效证据判断，正在调整检索方向"
                            if str(language or "").startswith("zh")
                            else "No valid evidence decision was produced; adjusting the research direction"
                        ),
                        detail="progressive_research_decision_recovery",
                    )
                    if next_queries:
                        continue
                decision = ResearchTurnDecision(
                    accepted_evidence=self._fallback_evidence(candidates),
                    done=True,
                    rationale="invalid_judge_response_fallback",
                )
            accepted_before = len(accepted)
            evidence_store.extend(decision.accepted_evidence)
            rejected.extend(decision.rejected_sources[:20])
            next_queries = decision.next_queries
            done = done or bool(decision.done)
            if self._should_continue_despite_done(
                done=done,
                next_queries=next_queries,
                round_index=round_index,
                max_rounds=self.max_rounds,
                budget_exhausted=False,
            ):
                logger.info(
                    "progressive_research_done_overridden round=%s next_queries=%s rationale=%s",
                    round_index,
                    next_queries,
                    decision.rationale[:300],
                    extra={
                        "event": "progressive_research.done_overridden",
                        "round": round_index,
                        "next_queries": list(next_queries),
                        "rationale": decision.rationale[:800],
                    },
                )
                done = False
            if done and next_queries and round_index >= self.max_rounds:
                done = False
                budget_exhausted = True
            logger.info(
                "progressive_research_round_judged round=%s candidates=%s accepted_new=%s accepted_total=%s rejected=%s done=%s next_queries=%s",
                round_index,
                len(candidates),
                len(accepted) - accepted_before,
                len(accepted),
                len(decision.rejected_sources),
                done,
                next_queries,
                extra={
                    "event": "progressive_research.round_judged",
                    "round": round_index,
                    "candidate_count": len(candidates),
                    "accepted_new": len(accepted) - accepted_before,
                    "accepted_total": len(accepted),
                    "rejected_count": len(decision.rejected_sources),
                    "done": done,
                    "next_queries": list(next_queries),
                    "rationale": decision.rationale[:800],
                },
            )
            await self._emit_progress(
                language=language,
                message=(
                    f"第 {round_index} 轮搜索结果质量检查完成：新增采纳 {len(accepted) - accepted_before} 条，累计 {len(accepted)} 条"
                    if str(language or "").startswith("zh")
                    else f"Round {round_index} review complete: accepted {len(accepted) - accepted_before} new, {len(accepted)} total"
                ),
                detail="progressive_research_round_judged",
            )
            if done:
                break

        round_limit_reached = bool(rounds >= self.max_rounds and not done)
        result_budget_exhausted = bool(budget_exhausted or round_limit_reached)
        evidence_sufficient = bool(done)
        result = ProgressiveResearchResult(
            ok=bool(accepted),
            query=original_query or seed_query,
            rounds=rounds,
            providers=sorted(p for p in providers_used if p),
            results=[self._evidence_to_result(item) for item in evidence_store.output()],
            rejected_sources=[item.model_dump() for item in rejected[:40]],
            search_trace=trace,
            summary=self._summary(accepted, trace, budget_exhausted=result_budget_exhausted),
            error="" if accepted else "no_accepted_evidence",
            evidence_sufficient=evidence_sufficient,
            budget_exhausted=result_budget_exhausted,
            stop_reason=(
                "evidence_sufficient" if evidence_sufficient
                else "budget_exhausted" if result_budget_exhausted
                else "no_more_queries"
            ),
        )
        logger.info(
            "progressive_research_finished ok=%s rounds=%s providers=%s evidence=%s rejected=%s",
            result.ok,
            result.rounds,
            result.providers,
            len(result.results),
            len(result.rejected_sources),
            extra={
                "event": "progressive_research.finished",
                "ok": result.ok,
                "rounds": result.rounds,
                "providers": result.providers,
                "evidence_count": len(result.results),
                "rejected_count": len(result.rejected_sources),
                "error": result.error,
            },
        )
        await self._emit_progress(
            language=language,
            message=self._finish_progress_message(
                language=language,
                rounds=rounds,
                evidence_count=len(result.results),
                evidence_sufficient=evidence_sufficient,
                budget_exhausted=bool(result_budget_exhausted and not evidence_sufficient),
            ),
            detail="progressive_research_finished",
        )
        return result

    @staticmethod
    def _finish_progress_message(
        *,
        language: str,
        rounds: int,
        evidence_count: int,
        evidence_sufficient: bool,
        budget_exhausted: bool,
    ) -> str:
        if str(language or "").startswith("zh"):
            if evidence_sufficient:
                return f"深度研究完成：证据已足够，共 {rounds} 轮，采纳 {evidence_count} 条证据"
            if budget_exhausted:
                return f"深度研究完成：达到研究轮次上限，共 {rounds} 轮，采纳 {evidence_count} 条证据"
            return f"深度研究完成：共 {rounds} 轮，采纳 {evidence_count} 条证据"
        if evidence_sufficient:
            return f"Research complete: evidence is sufficient after {rounds} rounds, {evidence_count} accepted evidence items"
        if budget_exhausted:
            return f"Research complete: round limit reached after {rounds} rounds, {evidence_count} accepted evidence items"
        return f"Research complete: {rounds} rounds, {evidence_count} accepted evidence items"

    async def _plan_initial_queries(self, query: str, *, language: str) -> list[str]:
        schema = (
            '{"next_queries":["query 1","query 2"],"rationale":"internal planning rationale"}'
        )
        prompt = (
            "You are a research search planner. Plan the first round of public-web queries from the user request.\n"
            f"{query_planning_temporal_guidance(self.temporal_context)}\n"
            "Plan from the request semantics rather than fixed entity rules. Queries may cover languages, "
            "competitors, time periods, prices, documents, benchmarks, and official sources, but every query "
            "must serve the user's goal.\n"
            f"输出严格 JSON，形如：{schema}\n"
            f"用户语言：{language}\n"
            f"用户需求：{query[:3000]}"
        )
        try:
            data = await invoke_json_decision(
                self.llm,
                [Message(role=Role.USER, content=prompt)],
                parser=coerce_json_object,
                spec=DecisionTurnSpec(
                    locale=language,
                    turn_id="research.plan",
                    sink=self._decision_commentary_sink(),
                ),
            )
            queries = unique_strings(list(data.get("next_queries") or []), limit=self.max_queries_per_round)
            logger.info(
                "progressive_research_initial_queries_planned count=%s queries=%s",
                len(queries),
                queries,
                extra={
                    "event": "progressive_research.initial_queries_planned",
                    "query_count": len(queries),
                    "queries": queries,
                    "rationale": str(data.get("rationale") or "")[:800],
                },
            )
            return queries
        except Exception as exc:
            logger.warning("progressive_research_initial_plan_failed error=%s", exc)
            return []

    async def _judge_turn(
        self,
        *,
        original_query: str,
        language: str,
        round_index: int,
        candidates: list[SearchCandidate],
        accepted: list[EvidenceItem],
    ) -> ResearchTurnDecision:
        payload = {
            "user_request": original_query[:4000],
            "round": round_index,
            "language": language,
            "existing_evidence": [item.model_dump() for item in accepted[-8:]],
            "candidates": [item.model_dump() for item in candidates[:40]],
        }
        system = (
            "You are a progressive research agent. Evaluate whether search results can support the final output and decide whether another search round is required.\n"
            f"{evidence_judging_temporal_guidance(self.temporal_context)}\n"
            "不要靠代码规则过滤；请基于用户需求、来源标题、URL、摘要内容判断相关性、可用性、覆盖缺口和可信度。\n"
            "只接受和用户需求直接相关、信息足够具体、可作为事实依据的证据。拒绝泛泛营销页、内容缺失、主题跑偏、摘要不足以支撑结论的来源。\n"
            "如果证据覆盖还不够，请给出下一轮 query；如果足够，请 done=true。\n"
            "输出严格 JSON：{\n"
            '  "accepted_evidence":[{"title":"","url":"","content":"","provider":"","query":"","confidence":0.0,"rationale":""}],\n'
            '  "rejected_sources":[{"title":"","url":"","reason":""}],\n'
            '  "next_queries":[""], "done":false, "rationale":""\n'
            "}\n"
            "accepted_evidence.content 必须是你从候选摘要中整理出的可引用证据文字，不要编造候选里没有的信息。"
        )
        try:
            data = await invoke_json_decision(
                self.llm,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ],
                parser=coerce_json_object,
                spec=DecisionTurnSpec(
                    locale=language,
                    turn_id=f"research.review.{round_index}",
                    sink=self._decision_commentary_sink(),
                ),
            )
            decision = ResearchTurnDecision.model_validate(data)
            decision.next_queries = unique_strings(decision.next_queries, limit=self.max_queries_per_round)
            return decision
        except Exception as exc:
            logger.warning("progressive_research_judge_failed error=%s", exc)
            return ResearchTurnDecision(
                accepted_evidence=self._fallback_evidence(candidates),
                rejected_sources=[],
                next_queries=[],
                done=True,
                rationale="judge_failed_fallback",
            )

    def _fallback_evidence(self, candidates: list[SearchCandidate]) -> list[EvidenceItem]:
        rows: list[EvidenceItem] = []
        for item in candidates:
            if not item.snippet:
                continue
            rows.append(
                EvidenceItem(
                    title=item.title,
                    url=item.url,
                    content=item.snippet,
                    provider=item.provider,
                    query=item.query,
                    confidence=item.score,
                    rationale="search_provider_snippet",
                )
            )
            if len(rows) >= min(6, self.max_evidence):
                break
        return rows

    @staticmethod
    def _evidence_to_result(item: EvidenceItem) -> dict[str, Any]:
        return {
            "tool": "progressive_research",
            "title": item.title,
            "source": item.url,
            "source_url": item.url,
            "content": item.content,
            "summary": item.content,
            "score": item.confidence,
            "meta": {
                "provider": item.provider,
                "query": item.query,
                "rationale": item.rationale,
            },
        }

    async def _emit_progress(self, *, language: str, message: str, detail: str) -> None:
        # Operation lifecycles below are the only user-visible work channel.
        return None

    def _decision_commentary_sink(self):
        callback = self.progress_callback
        if callback is None:
            return None

        async def sink(payload: dict[str, str]) -> None:
            maybe = callback({"type": "commentary", "content": payload})
            if inspect.isawaitable(maybe):
                await maybe

        return sink

    async def _emit_operation(
        self,
        *,
        state: str,
        operation_id: str,
        label: str,
        category: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        callback = self.progress_callback
        if callback is None:
            return
        event = operation_event(
            state,
            operation_id=operation_id,
            label=label,
            category=category,
            detail=detail,
        )
        try:
            maybe = callback(event)
            if inspect.isawaitable(maybe):
                await maybe
        except Exception as exc:
            logger.debug("progressive_research_operation_callback_failed error=%s", exc)

    @staticmethod
    def _should_continue_despite_done(
        *,
        done: bool,
        next_queries: list[str],
        round_index: int,
        max_rounds: int,
        budget_exhausted: bool = False,
    ) -> bool:
        return bool(done and next_queries and round_index < max_rounds and not budget_exhausted)

    @staticmethod
    def _summary(accepted: list[EvidenceItem], trace: list[dict[str, Any]], *, budget_exhausted: bool = False) -> str:
        suffix = " 已达到最大研究轮次，仍有未继续执行的候选查询。" if budget_exhausted else ""
        return (
            f"渐进式研究完成：采纳 {len(accepted)} 条证据，"
            f"执行 {len([x for x in trace if x.get('event') != 'no_provider'])} 次 provider 搜索。"
            f"{suffix}"
        )
