"""Execute a browser task via the connected desktop Local Agent.

Selected by the runtime dispatcher when ``agent_registry.get(user_id)``
reports an active WebSocket connection. Uses the same planner as the
generic ``browser_task`` skill but emits events in the subagent runtime's
``(event_dict, meta_dict)`` shape so the graph orchestrator can treat
the output through the standard runtime event contract.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Dict, List, Set, Tuple
from urllib.parse import urlparse

from app.browser.local_bridge import AgentNotConnected, LocalBridge
from app.browser.loop_policy import BROWSER_MAX_READS_PER_STATE, BROWSER_MAX_STEPS
from app.browser.tools import is_browser_tool, is_control_tool
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs
from app.enterprise_capabilities.browser.engine.action_contracts import (
    blocks_whole_node_replay as action_contract_blocks_whole_node_replay,
    describe_for_agent as action_contract_describe_for_agent,
    validate_data as action_contract_validate_data,
)
from app.services.skill_assets.publish_channels import publish_channel_registry
from app.services.skill_assets.composite_task import format_site_hints_for_goal
from app.services.site_profiles import site_profile_service
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision, Observation, StepRecord,
)
from app.enterprise_capabilities.browser.engine.contexts import factory as context_factory
from app.enterprise_capabilities.browser.engine.contexts.action_transition import BrowserActionTransition
from app.enterprise_capabilities.browser.engine.contexts.done_recovery import DoneBlockRecovery
from app.enterprise_capabilities.browser.engine.drivers import (
    apply_driver_resume_signal,
    notify_driver_rejection,
    notify_effect_receipt,
    notify_step_completed,
    prepare_driver_dispatch,
    select_driver,
)
from app.enterprise_capabilities.browser.engine.form_input import BrowserInputContext
from app.enterprise_capabilities.browser.engine.form_input.fill_retry import FillRetryPolicy, is_fill_reconciliation
from app.enterprise_capabilities.browser.engine.form_input.observation_update import apply_confirmed_fill
from app.enterprise_capabilities.browser.engine.form_input.target_preflight import (
    is_stale_fill_target_error,
    validate_fill_target,
)
from app.enterprise_capabilities.browser.engine.post_action_observation import (
    observation_retry_required,
    reconcile_post_action_observation,
)
from app.enterprise_capabilities.browser.engine.click_outcome import (
    ClickOutcome,
    ClickOutcomePolicy,
    effect_verification_eligible,
)
from app.enterprise_capabilities.browser.engine.interaction_target_recovery import (
    InteractionTargetRecovery,
    bind_coordinate_action,
    is_stale_interaction_target_error,
)
from app.enterprise_capabilities.browser.engine.transition_stabilizer import stabilize_transition_observation
from app.enterprise_capabilities.browser.engine.stagnation_budget import StagnationBudget
from app.browser.tool_deadlines import timeout_for_tool
from app.enterprise_capabilities.browser.engine.skill_fast_path import execute_skill_fast_path, prepare_skill_fast_path
from app.enterprise_capabilities.browser.engine.result_presenter import render_browser_result
from app.enterprise_capabilities.browser.engine.result_artifact import build_browser_result
from app.enterprise_capabilities.browser.engine.execution_budget import (
    BrowserExecutionBudget,
    BrowserExecutionBudgetExpired,
    build_budget_continuation,
    interrupted_effect_requires_handoff,
    unknown_effect_verification_question,
)
from app.enterprise_capabilities.browser.engine.operation_result_projection import (
    project_verified_operation_result,
)
from app.enterprise_capabilities.browser.engine.effect_receipt_flow import (
    applied_effect_task_outcome,
    apply_effect_receipt,
    build_effect_completion,
    build_effect_failure,
)
from app.enterprise_capabilities.browser.engine.effect_business_failure import build_effect_business_failure_events
from app.enterprise_capabilities.browser.engine.action_history import BrowserActionHistory
from app.enterprise_capabilities.browser.engine.business_action import BusinessActionLedger
from app.enterprise_capabilities.browser.engine.observation_freshness import (
    complete_observation,
    invalidate_observation,
    requires_fresh_observation,
)
from app.enterprise_capabilities.browser.engine.initial_observation import acquire_initial_observation
from app.enterprise_capabilities.browser.engine.progress_signature import browser_progress_signature
from app.enterprise_capabilities.browser.engine.loop_observation_policy import (
    READ_ONLY_TOOLS,
    post_action_observation_check,
    read_count_for_current_state,
)
from app.enterprise_capabilities.browser.engine.loop_recovery import recovery_decision_after_guard_failure
from app.enterprise_capabilities.browser.engine.exploration_stagnation import assess_exploration_stagnation
from app.enterprise_capabilities.browser.engine.human_assistance_policy import (
    BrowserHumanAssistance,
    EXPLORATION_STAGNATION,
    NAVIGATION_STAGNATION,
    NAVIGATION_TARGET_BLOCKED,
    READ_BUDGET,
    browser_human_assistance,
)
from app.enterprise_capabilities.browser.engine.media_upload_assistance import (
    augment_form_assistance_handoff,
    build_media_upload_handoff,
    completed_media_candidate_ids,
    is_media_delivery_handoff_error,
    media_upload_assistance_decision,
)
from app.enterprise_capabilities.browser.engine.form_human_assistance import (
    FORM_COMMIT_CATEGORY,
    FORM_EFFECT_VERIFY_CATEGORY,
    FORM_TASK_COMPLETION_CATEGORY,
    build_effect_verification_decision,
    build_fill_assistance_decision,
    build_task_completion_confirmation_decision,
    manual_commit_receipt,
    manual_effect_receipt,
    resume_contract,
    resume_outcome,
)
from app.enterprise_capabilities.browser.engine.human_commit_reconciliation import (
    assess_human_commit_reconciliation,
)
from app.enterprise_capabilities.browser.engine.recovery_router import (
    INTERACTION_BLOCKED,
    LOOP_EXHAUSTED,
    MODEL_FAILURE,
    OUTPUT_CONTRACT_EXHAUSTED,
    RESUME_RECONCILIATION_UNAVAILABLE,
    BrowserRecoveryPlan,
    route_browser_recovery,
)
from app.enterprise_capabilities.browser.engine.navigation_provenance import assess_navigation_provenance
from app.enterprise_capabilities.browser.engine.visual_observation_guard import (
    redundant_visual_observation,
)
from app.enterprise_capabilities.browser.engine.auth_state import (
    AuthTransitionTracker,
    assessment_from_payload,
    site_scope,
)
from app.enterprise_capabilities.browser.engine.auth_intervention import (
    BrowserAuthIntervention,
    authentication_resume_is_blocked,
    suspend_browser_authentication,
)
from app.enterprise_capabilities.browser.engine.intervention_suspension import (
    browser_resume_context,
    suspend_browser_intervention,
)
from app.enterprise_capabilities.browser.engine.checkpoint import BrowserCheckpointSession
from app.enterprise_capabilities.browser.engine.wait_for_cache import (
    WaitForClickTarget,
    can_reuse_click_target,
    confirmed_click_target,
)
from app.enterprise_capabilities.browser.engine.workflow_cache import browser_workflow_cache
from app.enterprise_capabilities.browser.engine.workflow_cache.identity import site_id_for_node
from app.enterprise_capabilities.browser.engine.workflow_cache.learning_trace import WorkflowLearningTrace
from app.enterprise_capabilities.browser.engine.workflow_cache.admission import terminal_effect_allows_cache
from app.enterprise_capabilities.browser.engine.recording import human_recording_store
from app.enterprise_capabilities.browser.engine.entry_candidates import extract_candidate_entries
from app.enterprise_capabilities.browser.engine.business_site_scope import (
    resolve_business_site_scope,
    scope_node,
)
from app.enterprise_capabilities.browser.engine.action_resolution import resolve_wait_for_action
from app.enterprise_capabilities.browser.engine.wait_action_policy import should_resolve_wait_action
from app.enterprise_capabilities.browser.engine.human_recording_handoff import begin_recorded_human_handoff
from app.enterprise_capabilities.browser.engine.effect_verification import (
    enforce_commit_preconditions,
    EffectReceipt,
    EffectTracker,
    FormTransactionTracker,
    PreparedEffect,
    SemanticActionRejected,
    assess_effect_completion,
    resolve_effect_target,
)
from app.enterprise_capabilities.browser.engine.run_request import resolve_run_original_request


logger = logging.getLogger(__name__)


# Complex multi-page tasks need room for re-observation, navigation and
# bounded recovery. The stagnation and repeated-read guards below stop a
# single action pattern from monopolising the overall step budget.
MAX_STEPS = BROWSER_MAX_STEPS
MAX_CONSECUTIVE_FAILURES = 3
# Per-domain safe-URL recovery budget. When a login signal fires on an
# already-authenticated domain we bounce once to the last safe URL instead
# of re-entering the login flow. If the same domain keeps surfacing a
# DOM-level login form this many times in a row, we assume the session
# genuinely expired, drop the domain from the authenticated set, and fall
# through to the real login intervention. Intentionally small — one false
# positive bounce is cheap; letting a truly expired session spin is not.
MAX_LOGIN_RECOVERY_ATTEMPTS = 2
SPA_EMPTY_OBSERVE_RETRIES = 2
SPA_EMPTY_OBSERVE_WAIT_SECONDS = 1.2

# Landing-page URLs that the xiaohongshu creator SPA often returns
# before hydration. Any navigate to one of these during a publish flow
# gets rewritten to the resolved publish_url so the planner doesn't
# stall on the empty shell.
_XHS_LANDING_URLS: frozenset[str] = frozenset(
    {
        "https://creator.xiaohongshu.com",
        "https://creator.xiaohongshu.com/login",
        "https://creator.xiaohongshu.com/new/home",
    }
)

# Matches an explicit publish-page URL the user embedded in their goal
# (e.g. "打开 https://creator.xiaohongshu.com/publish/publish?target=video").
# Such a URL overrides the yaml default for this task only.
_XHS_USER_PUBLISH_URL_RE = re.compile(
    r"https?://creator\.xiaohongshu\.com/publish/[^\s'\"<>)，。；]+",
    re.IGNORECASE,
)


def _detect_language(inputs: CapabilityInputs) -> str:
    explicit = str(getattr(inputs, "language", "") or "").strip().lower().replace("_", "-")
    if explicit.startswith("zh"):
        return "zh"
    if explicit.startswith("en"):
        return "en"
    for msg in reversed(list(inputs.messages or [])):
        text = str(getattr(msg, "content", "") or "")
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
    for msg in reversed(list(inputs.raw_messages or [])):
        text = str((msg or {}).get("content") or "") if isinstance(msg, dict) else ""
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
    if re.search(r"[\u4e00-\u9fff]", str(inputs.intent or "")):
        return "zh"
    return "en"


def _effect_timeline_message(status: str, reason: str, *, lang: str) -> str:
    if lang != "zh":
        return f"Operation result: {status} ({reason})"
    status_label = {
        "confirmed_success": "已确认成功",
        "confirmed_failure": "已确认失败",
        "pending_verification": "等待复核",
        "unknown": "结果待确认",
    }.get(str(status or ""), "结果待确认")
    reason_text = str(reason or "").strip()
    # Internal English diagnostics belong in logs, not a Chinese Timeline.
    suffix = f"（{reason_text}）" if re.search(r"[\u4e00-\u9fff]", reason_text) else ""
    return f"操作结果：{status_label}{suffix}"


def _extract_goal(node: CapabilityTask, inputs: CapabilityInputs) -> str:
    goal = str(getattr(node, "goal", "") or "").strip()
    if goal:
        return goal
    for msg in reversed(list(inputs.messages or [])):
        role = str(getattr(msg, "role", "") or "").lower()
        if role in ("user", "human"):
            text = str(getattr(msg, "content", "") or "").strip()
            if text:
                return text
    return ""


def _domain(url: str) -> str | None:
    try:
        host = urlparse(str(url)).hostname
        return host or None
    except Exception:
        return None


def _build_enterprise_sites_map(profiles: List[Dict[str, Any]]) -> Dict[str, str]:
    """Turn the user-visible site profiles into the flat {name: line} shape
    that ``system_prompt(enterprise_sites=...)`` formats.

    Each site collapses into one line that surfaces everything the LLM
    needs to navigate without guessing: host, entry URL, auth method,
    and a clipped hints blurb. This is *unconditional* context — the
    LLM should know where the user's intranet systems live regardless
    of whether a composite skill was also selected for this turn.
    """
    out: Dict[str, str] = {}
    for p in profiles or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        host = str(p.get("domain") or "").strip()
        entry_url = str(p.get("entry_url") or "").strip()
        auth = str(p.get("auth_method") or "").strip()
        hints = str(p.get("hints") or "").strip()
        parts: List[str] = []
        if host:
            parts.append(host)
        if entry_url and entry_url != host:
            parts.append(f"入口 {entry_url}")
        if auth:
            parts.append(f"登陆 {auth}")
        if hints:
            flat = " ".join(line.strip() for line in hints.splitlines() if line.strip())
            if flat:
                parts.append(f"说明 {flat[:220]}")
        out[name] = " | ".join(parts) or name
    return out


def _digest(tool: str, result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    if tool == "browser_observe":
        return f"{result.get('url','')} [{len(result.get('elements') or [])} els]"
    if tool == "browser_navigate":
        return str(result.get("url") or "")
    if tool == "browser_wait_for":
        # Surface matched_ref / clickable_ref in history digest so subsequent
        # LLM turns see "my last wait_for gave me ref=X" instead of a blank
        # success — otherwise the model loops on the same text because it
        # can't remember that a ref came back.
        m = result.get("matched_ref") or ""
        c = result.get("clickable_ref") or ""
        f = result.get("fillable_ref") or ""
        txt = str(result.get("matched_text") or "")[:60]
        if c or f or m:
            parts = []
            if c:
                parts.append(f"click-ref={c}")
            if f:
                parts.append(f"fill-ref={f}")
            if m and m != c:
                parts.append(f"ref={m}")
            if txt:
                parts.append(f"text={txt!r}")
            return "matched: " + ", ".join(parts)
        if result.get("model_required"):
            candidates = list(result.get("candidates") or [])[:6]
            compact = [
                {
                    "ref": item.get("ref"),
                    "role": item.get("role"),
                    "name": item.get("name") or item.get("text"),
                }
                for item in candidates
                if isinstance(item, dict)
            ]
            return (
                f"model_required: {result.get('reason') or 'local_rule_unresolved'}; "
                f"candidates={json.dumps(compact, ensure_ascii=False)}"
            )
        return ""
    if tool == "browser_read_text":
        # LLM explicitly asked to read page text — it needs the content,
        # not an 80-char teaser. Keep up to ~6000 chars so the planner can
        # actually extract the displayed values on its next turn. (Agent
        # side caps at 50KB; we trim down to a prompt-safe length here.)
        return str(result.get("text") or "")[:6000]
    if tool == "browser_fill":
        receipt = result.get("fill_receipt")
        if isinstance(receipt, dict):
            return (
                f"fill={str(receipt.get('status') or 'unknown')}; "
                f"verification={str(receipt.get('verification') or 'unknown')}"
            )
    return ""


def _obs_from_payload(payload: Any) -> Observation | None:
    if not isinstance(payload, dict):
        return None
    nested = payload.get("observation")
    if isinstance(nested, dict):
        merged = dict(nested)
        if payload.get("screenshot") and not merged.get("screenshot"):
            merged["screenshot"] = payload.get("screenshot")
        if payload.get("screenshot_metadata") and not merged.get("screenshot_metadata"):
            merged["screenshot_metadata"] = payload.get("screenshot_metadata")
        return _obs_from_payload(merged)
    # The Tauri agent (agent/src/browser/observer.ts) sends `pageText` for
    # every observe / navigate response; older clients that don't yet
    # populate it fall back to empty string, which matches the dataclass
    # default and keeps the planner prompt shape stable.
    page_text = str(
        payload.get("pageText")
        or payload.get("page_text")
        or payload.get("page_text_snippet")
        or ""
    )
    return complete_observation(Observation(
        url=str(payload.get("url") or ""),
        title=str(payload.get("title") or ""),
        elements=list(payload.get("elements") or []),
        revision=str(payload.get("revision") or ""),
        screenshot=payload.get("screenshot"),
        clean_dom=payload.get("cleanDom") or payload.get("clean_dom"),
        dom_diff=payload.get("domDiff") or payload.get("dom_diff"),
        page_text=page_text,
        auth=payload.get("auth") if isinstance(payload.get("auth"), dict) else None,
        frame_count=max(1, int(payload.get("frameCount") or payload.get("frame_count") or 1)),
        interaction=payload.get("interaction") if isinstance(payload.get("interaction"), dict) else None,
        effects=list(payload.get("effects") or []),
        diagnostics=payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else None,
        viewport=payload.get("viewport") if isinstance(payload.get("viewport"), dict) else None,
        screenshot_metadata=(
            payload.get("screenshot_metadata")
            if isinstance(payload.get("screenshot_metadata"), dict)
            else None
        ),
    ))


def _update_obs(current: Observation, tool: str, result: Any) -> Observation:
    if not isinstance(result, dict):
        return current
    if tool == "browser_observe":
        return _obs_from_payload(result) or current
    if tool == "browser_navigate":
        # The agent (see agent/src/tools/browser_tools.ts::browser_navigate)
        # nests the full PageObservation under ``result.observation`` — that's
        # the only place ``pageText`` / ``elements`` live after a navigate.
        # The top level only carries url/title/screenshot/loginDetected.
        nested = result.get("observation")
        if isinstance(nested, dict):
            fresh = _obs_from_payload(nested)
            if fresh is not None:
                return fresh
        # A navigate response without a nested snapshot has no valid refs for
        # the destination. Keep only location and force a fresh observation.
        return invalidate_observation(
            current,
            url=str(result.get("url") or ""),
            title=str(result.get("title") or ""),
        )
    # State-changing tools (click/fill/press/select/scroll) ship a fresh
    # observation under result.observation so the planner sees the post-
    # action page state on its next turn.
    fresh = _obs_from_payload(result.get("observation"))
    if fresh is not None:
        return fresh
    if requires_fresh_observation(tool):
        return invalidate_observation(current)
    return current


def _extract_screenshot(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    s = result.get("screenshot")
    if isinstance(s, str) and s:
        return s
    obs = result.get("observation")
    if isinstance(obs, dict):
        s2 = obs.get("screenshot")
        if isinstance(s2, str) and s2:
            return s2
    return None


def _login_detected(result: Any) -> bool:
    return assessment_from_payload(result).get("state") in {
        "required", "registration_required", "authenticating", "failed",
    }


def _format_upstream_artifacts(node: CapabilityTask, inputs: CapabilityInputs, lang: str) -> str:
    """Render predecessor node artifacts as a text block appended to the
    browser task goal. Lets the planner LLM see what upstream produced.

    Returns empty string when there are no upstream artifacts (single-task
    or first node in a graph) — keeps single-task behavior unchanged.
    """
    graph_artifacts = (inputs.output_spec or {}).get("graph_artifacts") or {}
    if not isinstance(graph_artifacts, dict) or not graph_artifacts:
        return ""
    deps = list(node.depends_on or [])
    if not deps:
        return ""
    pieces: List[str] = []
    for dep_id in deps:
        art = graph_artifacts.get(dep_id)
        if not isinstance(art, dict):
            continue
        # Strip internal bookkeeping keys and heavy blobs.
        cleaned = {}
        for k, v in art.items():
            if k.startswith("_"):
                continue
            if k in ("browser_receipt", "skill_state", "skill_finalize", "answer"):
                continue
            if isinstance(v, str) and len(v) > 8000:
                v = v[:8000] + "...<truncated>"
            cleaned[k] = v
        if cleaned:
            pieces.append(f"# {dep_id}\n{json.dumps(cleaned, ensure_ascii=False, indent=2)}")
    if not pieces:
        return ""
    header = ("【上游节点产出（可作为本次任务输入）】" if str(lang).startswith("zh")
              else "UPSTREAM ARTIFACTS (inputs from prior nodes):")
    return header + "\n" + "\n\n".join(pieces)


def _format_candidate_entries(
    candidates: List[Dict[str, str]], lang: str,
) -> str:
    if not candidates:
        return ""
    is_zh = str(lang or "").startswith("zh")
    lines: List[str] = []
    for idx, c in enumerate(candidates, 1):
        url = c.get("url") or ""
        src = c.get("source") or ""
        name = c.get("name") or ""
        if src == "user_request":
            tag = "用户原文给出" if is_zh else "from user request"
        elif src == "site_scope":
            tag = "来自任务目标站点" if is_zh else "from task site scope"
        else:
            tag = (f"来自站点设置「{name}」" if is_zh
                   else f"from site profile '{name}'")
        lines.append(f"  {idx}. {url}  ({tag})")
    header = (
        "【候选入口 URL（来自用户原文 + 站点设置）】"
        if is_zh else
        "CANDIDATE ENTRY URLS (from user request + site profiles):"
    )
    rule = (
        "⛔ 禁止调用 browser_ask_user 索要 URL —— 必须先从上面列表里挑一个 browser_navigate 过去。"
        "\n多条候选时按用户原文的语义/顺序选（例如「在 A 查询、到 B 上传」→查询步用 A、上传步用 B）。"
        if is_zh else
        "⛔ Do NOT call browser_ask_user for a URL — pick one from the list above and browser_navigate to it."
        "\nWith multiple candidates, match by semantic role/order in the user request "
        "(e.g. 'query on A, upload to B' → read step uses A, upload step uses B)."
    )
    return f"{header}\n" + "\n".join(lines) + "\n" + rule


def _extract_original_user_request(inputs: CapabilityInputs) -> str:
    """Return the immutable request bound to this graph run.

    Old runs may not have the persisted field, so the compatibility fallback
    uses the latest user message. It must never use the conversation's first
    user message because that may belong to an earlier task in the session.
    """
    return resolve_run_original_request(
        output_spec=inputs.output_spec,
        messages=inputs.raw_messages or inputs.messages or [],
    )


def _upstream_is_empty(node: CapabilityTask, upstream_block: str) -> bool:
    """A node declared upstream deps but the rendered block is empty —
    means predecessors didn't emit any concrete data beyond the stripped
    bookkeeping fields. The caller prepends an explicit warning so the
    LLM doesn't quietly assume the work is already done.
    """
    return bool(node.depends_on) and not upstream_block.strip()


def _format_downstream_expectations(node: CapabilityTask, lang: str) -> str:
    """Render downstream consumers from ``node.meta.downstream_consumers``.

    Gives the LLM a structural view of "what will consume my output and
    what shape does it expect". Empty string when no consumers are
    recorded (terminal node or single-node graph).
    """
    meta = node.meta if isinstance(node.meta, dict) else {}
    consumers = meta.get("downstream_consumers")
    if not isinstance(consumers, list) or not consumers:
        return ""
    lines: List[str] = []
    for c in consumers:
        if not isinstance(c, dict):
            continue
        node_id = str(c.get("node_id") or "").strip()
        objective = str(c.get("objective") or "").strip()
        required_inputs = [str(x).strip() for x in (c.get("required_inputs") or []) if str(x).strip()]
        agent = str(c.get("assigned_agent") or "").strip()
        header_parts: List[str] = []
        if node_id:
            header_parts.append(f"`{node_id}`")
        if agent:
            header_parts.append(f"({agent})")
        header = "- " + (" ".join(header_parts) if header_parts else "consumer")
        lines.append(header)
        if objective:
            lines.append(f"  目标: {objective}" if str(lang).startswith("zh") else f"  goal: {objective}")
        if required_inputs:
            keys = ", ".join(required_inputs[:8])
            lines.append(
                (f"  需要你提供的 artifact 键: {keys}" if str(lang).startswith("zh")
                 else f"  expects artifact keys from you: {keys}")
            )
    if not lines:
        return ""
    header_text = (
        "【下游节点在等你交付的东西】(影响你的 browser_done.data 应该放什么)"
        if str(lang).startswith("zh")
        else "DOWNSTREAM CONSUMERS (shape your browser_done.data to serve them):"
    )
    return header_text + "\n" + "\n".join(lines)


_LOGIN_URL_RE = re.compile(r"login|signin|sign-in|auth|sso|cas|oauth|登录|登入", re.I)


def _is_login_like_url(url: str) -> bool:
    return bool(_LOGIN_URL_RE.search(str(url or "")))


def _login_detected_from_obs(obs: "Observation") -> bool:
    state = str((obs.auth or {}).get("state") or "")
    return state in {"required", "registration_required", "authenticating", "failed"} or (
        not state and _is_login_like_url(obs.url or "")
    )


def _looks_like_empty_spa_observation(obs: "Observation") -> bool:
    url = str(obs.url or "").strip()
    if not url or _is_login_like_url(url):
        return False
    title = str(obs.title or "").strip().lower()
    # Generic JS app shells often have a proper title but no interactive
    # elements during the first paint / hydration window.
    return len(list(obs.elements or [])) == 0 and bool(title)


def _is_xiaohongshu_publish_goal(goal: str) -> bool:
    text = str(goal or "").lower()
    return (
        "creator.xiaohongshu.com" in text
        and any(token in text for token in ("新建图文笔记", "新建笔记", "图文笔记", "article_markdown", "保存为草稿", "保存草稿"))
    )


def _resolve_xiaohongshu_publish_url(goal: str) -> str:
    """Return the target publish URL for a xiaohongshu publish run.

    Priority:
      1. Explicit URL embedded in the user's goal (e.g. the user said
         "go to https://creator.xiaohongshu.com/publish/publish?target=video")
      2. The yaml-configured default (``publish_channels.yaml``)
      3. Empty string — caller should interpret this as "no default, don't
         rewrite", letting the planner's own navigate call stand.
    """
    match = _XHS_USER_PUBLISH_URL_RE.search(goal or "")
    if match:
        candidate = match.group(0).strip().rstrip("/")
        # Reject landing URLs accidentally matched as "user-specified".
        if candidate not in _XHS_LANDING_URLS:
            return match.group(0).strip()
    return publish_channel_registry.publish_url_for("xiaohongshu")


class DesktopAgentBrowserExecutor:
    def __init__(
        self,
        user_id: str,
        session_id: str = "default",
        *,
        checkpoint_session: BrowserCheckpointSession | None = None,
    ) -> None:
        self.user_id = user_id
        self.session_id = session_id or "default"
        self.bridge = LocalBridge(user_id, self.session_id)
        self.checkpoint_session = checkpoint_session

    async def _retry_empty_spa_observation(
        self,
        *,
        current_obs: Observation,
        lang: str,
        step: int,
    ) -> tuple[Observation, bool, str | None]:
        """Give JS-heavy SPA pages a short hydration window before the
        planner reacts to a zero-element observation.

        Returns the possibly refreshed observation, whether it stabilized,
        and an optional screenshot from the last retry observation.
        """
        if not _looks_like_empty_spa_observation(current_obs):
            return current_obs, False, None

        import asyncio as _asyncio

        latest = current_obs
        latest_screenshot: str | None = None
        for attempt in range(1, SPA_EMPTY_OBSERVE_RETRIES + 1):
            logger.debug(
                "empty SPA observation retry",
                extra={"event": "browser.empty_spa_retry", "attempt": attempt, "max_attempts": SPA_EMPTY_OBSERVE_RETRIES, "url": latest.url, "title": latest.title[:120]},
            )
            await _asyncio.sleep(SPA_EMPTY_OBSERVE_WAIT_SECONDS)
            re_result, re_ok, _re_err = await self._dispatch(Decision(
                tool="browser_observe",
                args={},
                rationale="retry observe after short hydration wait on empty SPA page",
            ))
            if not re_ok or not isinstance(re_result, dict):
                continue
            refreshed = _obs_from_payload(re_result)
            latest_screenshot = _extract_screenshot(re_result)
            if refreshed is not None:
                latest = refreshed
            if latest.elements:
                logger.info(
                    "empty SPA observation stabilized",
                    extra={"event": "browser.empty_spa_stabilized", "step": step, "url": latest.url, "elements": len(list(latest.elements or []))},
                )
                return latest, True, latest_screenshot
        return latest, False, latest_screenshot

    async def execute(
        self,
        *,
        node: CapabilityTask,
        inputs: CapabilityInputs,
    ) -> AsyncIterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
        lang = _detect_language(inputs)
        goal = _extract_goal(node, inputs)
        resume_checkpoint = self.checkpoint_session.checkpoint if self.checkpoint_session else None
        subagent_id = self.checkpoint_session.subagent_id if self.checkpoint_session else f"sa_{uuid.uuid4().hex[:12]}"

        # Prepend composite_task site knowledge so the planner LLM starts
        # with auth / navigation / entry-URL hints already in context,
        # instead of rediscovering them via trial-and-error.
        site_context = (node.meta or {}).get("site_context") if isinstance(node.meta, dict) else None
        if isinstance(site_context, dict):
            site_hints_block = format_site_hints_for_goal(site_context)
            if site_hints_block:
                goal = f"{site_hints_block}\n\n{goal}" if goal else site_hints_block

        # Multi-node data-flow context. Every graph node's LLM needs three
        # things in addition to its own step goal:
        #   1. the user's original request (so it knows the global intent)
        #   2. actual data the upstream nodes produced (not just artifact
        #      ids — real values; empty values get an explicit warning so
        #      the LLM doesn't pretend work is done)
        #   3. what downstream consumers expect (so browser_done.data is
        #      shaped to serve the next node, not just literally close
        #      out this step)
        # This is the "blood flow" between graph nodes — without it the
        # graph is just a skeleton and each node delivers its narrow
        # subgoal regardless of whether the overall request is served.
        original_user_request = _extract_original_user_request(inputs)
        runtime_output_spec = getattr(inputs, "output_spec", None) or {}
        input_context = BrowserInputContext.from_runtime(
            original_request=original_user_request,
            node=node,
            output_spec=runtime_output_spec,
        )
        authoritative_form_values = input_context.authoritative_form_values()
        requires_authoritative_form_input = bool(authoritative_form_values)
        has_form_handoff_payload = bool(
            requires_authoritative_form_input
            or any(item.value_kind == "file" for item in input_context.candidates)
        )
        # Load visible site profiles up front so we can extract entry-URL
        # candidates from them (names the user mentioned in the request)
        # and render the candidate list into the prompt below. Same profiles
        # are reused further down as `enterprise_sites` for the planner.
        try:
            visible_sites = await site_profile_service.list_for_user(self.user_id)
        except Exception as exc:
            logger.warning("site profiles load failed", extra={"event": "browser.site_profiles_load_failed", "error": str(exc)})
            visible_sites = []
        site_resolution = resolve_business_site_scope(
            node,
            original_request=original_user_request,
            visible_sites=visible_sites,
        )
        node = scope_node(node, site_resolution)
        resolved_site_id = site_id_for_node(node, input_context=input_context)
        logger.info(
            "browser business site resolved",
            extra={
                "event": "browser.business_site_resolved",
                "site_id": resolved_site_id,
                "source": site_resolution.source,
                "confidence": site_resolution.confidence,
            },
        )
        # Task context — picks form / scrape / general based on the
        # content_task_spec.schema.category enum. The executor only talks
        # to the BrowserTaskContext ABC from here on; each category's
        # behaviour lives in its own contexts/*.py file.
        task_context = context_factory.maybe_init(
            node=node,
            output_spec=getattr(inputs, "output_spec", None) or {},
            original_user_request=original_user_request,
            goal=goal,
            lang=lang,
            input_context=input_context,
        )
        if resume_checkpoint and resume_checkpoint.context_state:
            task_context.restore_checkpoint_state(resume_checkpoint.context_state)
        resume_workflow_id = str(
            (resume_checkpoint.driver_state if resume_checkpoint else {}).get("workflow_id") or ""
        )
        learned_workflow = None
        if not resume_checkpoint or resume_workflow_id:
            # Resume only the exact workflow version whose cursor was saved.
            # An exploration-only task must not acquire a newly-created cache
            # halfway through its run.
            learned_workflow = await browser_workflow_cache.lookup(
                user_id=self.user_id,
                main_id=str(runtime_output_spec.get("main_id") or "default"),
                node=node,
                input_context=input_context,
                preferred_workflow_id=resume_workflow_id,
                allow_quarantined_preferred=bool(
                    resume_workflow_id
                    and not bool((resume_checkpoint.driver_state or {}).get("replay_failed"))
                ),
            )
        context_tracks_state = bool(
            task_context.active or getattr(task_context, "stateful", False)
        )
        candidate_entries = extract_candidate_entries(
            original_user_request,
            visible_sites,
            expected_site=resolved_site_id,
        )
        candidate_block = _format_candidate_entries(candidate_entries, lang)
        logger.debug(
            "browser candidate entries resolved",
            extra={"event": "browser.candidate_entries", "count": len(candidate_entries), "request_len": len(original_user_request or ""), "preview": [(c.get("source"), c.get("url")) for c in candidate_entries[:3]]},
        )
        upstream_context = _format_upstream_artifacts(node, inputs, lang)
        downstream_block = _format_downstream_expectations(node, lang)
        # Per-capability produce contract: the planner picks a capability
        # per browser step (browser.read / submit / modify / …); each has
        # a declared produce shape we'll validate against at browser_done
        # time. Show it to the LLM so it knows exactly what to put in data.
        action_capability_id = str((node.meta or {}).get("capability_id") or "").strip().lower()
        contract_hint = action_contract_describe_for_agent(action_capability_id, lang)
        logger.debug(
            "browser node capability resolved",
            extra={"event": "browser.node_capability", "capability_id": action_capability_id or "<untyped>", "hint_injected": bool(contract_hint)},
        )

        # Remember the narrow step goal separately from the augmented
        # prompt. The UI banner / activity messages should show the
        # human-meaningful "what this step does" text, not the full
        # context envelope we feed the planner LLM.
        step_goal_for_display = goal

        goal_sections: List[str] = []
        if original_user_request and original_user_request != goal:
            header = "【用户最终要的（所有节点共享的原始请求）】" if lang == "zh" \
                     else "USER'S ORIGINAL REQUEST (shared by all graph nodes):"
            goal_sections.append(f"{header}\n{original_user_request}")
        if candidate_block:
            goal_sections.append(candidate_block)
        if upstream_context:
            goal_sections.append(upstream_context)
        elif _upstream_is_empty(node, upstream_context):
            # Plan-A soft fallback: upstream declared deps but left no data.
            # Tell the LLM honestly so it re-fetches instead of assuming
            # the work was already done.
            warn = ("⚠ 上游节点没有给你留下具体数据 —— 不要假装已有，需要从头抓取。"
                    if lang == "zh"
                    else "⚠ Upstream nodes produced no concrete data — don't assume it's done; fetch from scratch.")
            goal_sections.append(warn)
        if downstream_block:
            goal_sections.append(downstream_block)
        # Capability contract hint sits right before the step goal so the
        # LLM reads "you're doing a READ / SUBMIT / etc., data must look
        # like this" immediately before deciding its first action.
        if contract_hint:
            goal_sections.append(contract_hint)
        if goal_sections:
            # The step goal goes last so the LLM sees context first, then
            # the specific action it should take now.
            goal_sections.append(
                ("【你这一步要做的】\n" + goal) if lang == "zh" else ("THIS STEP:\n" + goal)
            )
            goal = "\n\n".join(goal_sections)

        if not goal:
            yield {"type": "activity", "content": {
                "kind": "error",
                "message": ("浏览器任务缺少目标描述" if lang == "zh" else "Missing task goal"),
            }}, {}
            yield {"type": "subagent_done", "content": {
                "subagent_id": subagent_id, "node_id": node.node_id, "status": "failed_terminal",
            }}, {}
            return

        # Signal the desktop workspace before the Skill fast path runs. This
        # event deliberately contains no screenshot: desktop clients connect
        # to the sidecar's local CDP screencast, while web clients may use the
        # existing backend stream as a compatibility fallback.
        yield {"type": "browser.preview", "content": {
            "mode": "local",
            "transport": "native_cdp",
            "session_id": self.session_id,
        }}, {}

        fast_path_seed: Dict[str, Any] | None = None
        fast_path_request = None if (resume_checkpoint or learned_workflow is not None) else prepare_skill_fast_path(
            node=node,
            inputs=inputs,
            goal=goal,
        )
        fast_path = None
        # An unavailable sidecar means there is no real dispatch to present;
        # preserve the existing model fallback without a synthetic failure.
        if fast_path_request is not None and self.bridge.available():
            yield {"type": "tool_requested", "content": {
                "tool": "browser_execute_workflow",
                "args": fast_path_request.args,
            }}, {}
            fast_path = await execute_skill_fast_path(
                bridge=self.bridge,
                request=fast_path_request,
            )
            yield {"type": "tool_completed", "content": {
                "tool": "browser_execute_workflow",
                "ok": bool(fast_path and fast_path.completed),
                "result": fast_path.result if fast_path is not None else {},
                **({"error": "local browser agent unavailable"} if fast_path is None else {}),
            }}, {}
        if fast_path is not None:
            if fast_path.completed:
                fast_path_artifacts = fast_path.artifacts(
                    str((node.meta or {}).get("capability_id") or "")
                )
                yield {"type": "activity", "content": {
                    "kind": "complete",
                    "message": (
                        "浏览器 Skill 已通过本地规则完成，未调用模型"
                        if lang == "zh"
                        else "Browser Skill completed by local rules without a model"
                    ),
                }}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": subagent_id,
                    "node_id": node.node_id,
                    "status": "succeeded",
                }}, {
                    "browser_receipt": {
                        "status": "ok",
                        "summary": "skill_fast_path_completed",
                        "steps": int(fast_path.result.get("completed_actions") or 0),
                    },
                    "browser_result": build_browser_result(
                        objective=str(node.goal or goal or ""),
                        summary="skill_fast_path_completed",
                        data={"workflow_result": fast_path.result, **fast_path_artifacts},
                    ),
                    **fast_path_artifacts,
                }
                return
            yield {"type": "activity", "content": {
                "kind": "analyze",
                "message": (
                    "本地 Skill/DOM 规则遇到未知状态，转入模型探索"
                    if lang == "zh"
                    else "Local Skill/DOM rules reached an unknown state; escalating to model exploration"
                ),
            }}, {}
            fast_path_seed = fast_path.result

        yield {"type": "activity", "content": {
            "kind": "analyze",
            "message": (
                (f"继续浏览器任务：{step_goal_for_display[:80]}" if resume_checkpoint else
                 f"命中已学习流程，优先快速执行：{step_goal_for_display[:80]}" if learned_workflow is not None else
                 f"开始浏览器任务：{step_goal_for_display[:80]}")
                if lang == "zh"
                else (f"Resuming browser task: {step_goal_for_display[:80]}" if resume_checkpoint else
                      f"Learned workflow matched; replaying first: {step_goal_for_display[:80]}" if learned_workflow is not None else
                      f"Starting browser task: {step_goal_for_display[:80]}")
            ),
        }}, {}

        # Site profiles were loaded earlier (for candidate extraction);
        # reuse them here as the planner's enterprise_sites map. Site
        # knowledge is unconditional — the LLM should know where the
        # user's intranet systems live even when no composite skill was
        # selected for this turn.
        enterprise_sites = _build_enterprise_sites_map(visible_sites)
        logger.debug(
            "enterprise sites injected",
            extra={"event": "browser.enterprise_sites_injected", "count": len(enterprise_sites), "names": list(enterprise_sites.keys())[:8]},
        )

        # Driver selection — picks SkillDriver if upstream resolved a
        # composite_task skill with replayable steps, otherwise the
        # plain ExplorationDriver (LLM planner). Variable kept as
        # ``planner`` for minimal call-site diff; it remains a drop-in
        # replacement at the .next_step interface.
        planner = select_driver(
            lang=lang,
            enterprise_sites=enterprise_sites or None,
            output_spec=runtime_output_spec,
            input_context=input_context,
            capability_id=action_capability_id,
            learned_workflow=learned_workflow,
            on_learned_workflow_failure=browser_workflow_cache.failure_reporter(learned_workflow),
        )
        if resume_checkpoint and resume_checkpoint.driver_state:
            planner.restore_checkpoint_state(resume_checkpoint.driver_state)
        logger.info("browser driver selected", extra={"event": "browser.driver_selected", "driver": planner.kind})
        history: List[StepRecord] = resume_checkpoint.restore_history() if resume_checkpoint else []
        learning_trace = WorkflowLearningTrace.restore(
            resume_checkpoint.learning_trace if resume_checkpoint else None,
            history_size=len(history),
        )
        active_human_recording_id = str(
            (
                (resume_checkpoint.browser_runtime_state or {})
                if resume_checkpoint else {}
            ).get("human_recording_id") or ""
        )
        current_obs = Observation(
            url=resume_checkpoint.current_url if resume_checkpoint else "about:blank",
            title=resume_checkpoint.current_title if resume_checkpoint else "",
            elements=[],
            revision=resume_checkpoint.current_revision if resume_checkpoint else "",
            fresh=False,
        )
        if isinstance(fast_path_seed, dict):
            seed_observation = fast_path_seed.get("observation")
            if isinstance(seed_observation, dict):
                seed_payload = dict(seed_observation)
                if fast_path_seed.get("screenshot"):
                    seed_payload["screenshot"] = fast_path_seed.get("screenshot")
                current_obs = _obs_from_payload(seed_payload) or current_obs
        # Cross-node state handoff: probe the browser for whatever page the
        # previous graph node left behind. Without this, every new browser
        # node starts with current_obs==about:blank, so the planner LLM
        # sees "I'm on a blank page" and re-navigates from the enterprise
        # site map — undoing any progress an upstream node made (e.g.
        # landed on wisdom.test.askbot.cn, next node restarts from portal).
        # A no-domain browser_observe falls through to getLastActivePage
        # on the agent side, returning the actual tab state if one exists.
        initial_probe = await acquire_initial_observation(
            current_obs,
            dispatch=self._dispatch,
            parse_observation=_obs_from_payload,
        )
        if initial_probe.adopted:
            current_obs = initial_probe.observation
            logger.info(
                "browser initial probe succeeded",
                extra={
                    "event": "browser.initial_probe",
                    "url": current_obs.url,
                    "elements": len(current_obs.elements or []),
                    "page_text_len": len(current_obs.page_text or ""),
                    "attempts": initial_probe.attempts,
                },
            )
        else:
            logger.warning(
                "browser initial probe failed",
                extra={
                    "event": "browser.initial_probe_failed",
                    "error": initial_probe.error,
                    "attempts": initial_probe.attempts,
                },
            )
        if active_human_recording_id:
            # Stop only after the fresh probe so the last human-side DOM/effect
            # transition is available to the recorder. Events are durable and
            # are merged before any resumed Agent action can run.
            try:
                await self.bridge.send_command(
                    "recording_stop",
                    recording_id=active_human_recording_id,
                )
                stopped = await human_recording_store.wait_stopped(
                    active_human_recording_id,
                )
                recorded_events = await human_recording_store.list(
                    active_human_recording_id,
                )
                learning_trace.capture_recorded(
                    recorded_events,
                    input_context=input_context,
                )
                await human_recording_store.purge(active_human_recording_id)
                logger.info(
                    "browser human recording merged",
                    extra={
                        "event": "browser.human_recording_merged",
                        "recording_id": active_human_recording_id,
                        "events": len(recorded_events),
                        "stopped": bool(stopped),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "browser human recording merge failed",
                    extra={
                        "event": "browser.human_recording_merge_failed",
                        "recording_id": active_human_recording_id,
                        "error": str(exc),
                    },
                )
            active_human_recording_id = ""
        driver_resume_reconciled = not bool(resume_checkpoint)
        if resume_checkpoint and current_obs.fresh:
            # Human interaction can change the page, active form and refs.
            # Reconcile the signal only after the live tab has been observed.
            apply_driver_resume_signal(
                planner,
                dict(runtime_output_spec.get("resume_signal") or {}),
                current_obs,
            )
            driver_resume_reconciled = True

        consecutive_failures = resume_checkpoint.consecutive_failures if resume_checkpoint else 0
        # Soft-recovery flag: when consecutive_failures hits the ceiling for
        # the first time, we inject one fresh browser_observe to re-ground
        # the LLM on the current DOM (stale refs are the most common cause
        # of a triple-click miss) instead of terminating the whole node.
        # Only granted once per run so a genuinely stuck flow still exits.
        soft_recovery_used = resume_checkpoint.soft_recovery_used if resume_checkpoint else False
        # Stagnation detector: tools can return ok=True while the page makes
        # no observable progress — a dispatched click on a disabled or
        # non-interactive target can still report success, so `ok` alone doesn't catch
        # "I clicked 5 times and nothing happened" loops. We track a cheap
        # page-state signature (url, element count, page_text hash) across
        # progress-expected tool calls; if the signature is identical for
        # too many consecutive turns we inject a synthetic StepRecord with
        # a "page didn't change" hint so the planner LLM switches tactics
        # (fill required fields, re-scan attributes for disabled state,
        # etc.) instead of spinning.
        last_progress_signature: tuple[Any, ...] | None = (
            tuple(resume_checkpoint.last_progress_signature)  # type: ignore[arg-type]
            if resume_checkpoint and resume_checkpoint.last_progress_signature
            else None
        )
        no_progress_streak = resume_checkpoint.no_progress_streak if resume_checkpoint else 0
        stagnation_notices = 0
        stagnation_budget = StagnationBudget(max_notices=3)
        click_outcome_policy = ClickOutcomePolicy()
        interaction_target_recovery = InteractionTargetRecovery()
        NO_PROGRESS_STREAK_LIMIT = 3
        # the primary fix for "LLM spams wait_for on same
        # text" lives in the agent: wait_for now returns the matched ref
        # so the LLM can click immediately instead of re-waiting. This
        # counter is the safety net — if the LLM keeps invoking
        # wait_for on the same text (regardless of ok status), redirect
        # it. Count INVOCATIONS, not failures, because the real bad
        # pattern is "already confirmed the text is there but still
        # calling wait_for instead of using the returned ref".
        wait_for_text_calls: Dict[str, int] = dict(resume_checkpoint.wait_for_text_calls) if resume_checkpoint else {}
        # Cache of (text → clickable_ref) populated from every successful
        # browser_wait_for. Enables P1-hard: when LLM re-waits on the same
        # text and we already know the ref, we auto-rewrite the decision
        # into browser_click(ref=…) in-place. Eliminates the loop entirely.
        current_refs = {
            str(item.get("ref") or "")
            for item in list(current_obs.elements or [])
            if isinstance(item, dict) and str(item.get("ref") or "")
        }
        checkpoint_url = resume_checkpoint.current_url if resume_checkpoint else ""
        wait_for_text_refs: Dict[str, str] = {
            str(text): str(ref)
            for text, ref in dict(resume_checkpoint.wait_for_text_refs if resume_checkpoint else {}).items()
            if str(ref) in current_refs and current_obs.url == checkpoint_url
        }
        # Rich metadata is intentionally not restored from checkpoints: refs
        # are observation-local and must be freshly rule-confirmed after resume.
        wait_for_click_targets: Dict[str, WaitForClickTarget] = {}
        WAIT_FOR_TEXT_MAX_CALLS = 2
        is_xhs_publish_goal = _is_xiaohongshu_publish_goal(goal)
        # Resolve once per run: user-supplied URL (in goal) wins over the
        # yaml default. Empty string means "no default available — skip
        # the landing-page rewrite entirely and trust the planner".
        xhs_publish_url = _resolve_xiaohongshu_publish_url(goal) if is_xhs_publish_goal else ""
        # Track the last URL the LLM explicitly asked to navigate to.
        # If login is detected, we return here after the user logs in.
        # Never set to a login-like URL (would poison the resume URL and
        # trap the login wait loop polling /login against itself).
        last_navigate_target: str | None = resume_checkpoint.last_navigate_target if resume_checkpoint else None
        # Session-scoped auth fact table. Once a domain successfully exits
        # the login wait loop (user completed sign-in) we mark it here.
        # Any later login signal on the same domain is treated as a false
        # positive (stale URL match, transient DOM glitch, or LLM-driven
        # re-navigation to a login URL) and gets redirected to the last
        # safe URL instead of re-entering the login flow.
        authenticated_domains: Set[str] = set(resume_checkpoint.authenticated_domains) if resume_checkpoint else set()
        auth_tracker = AuthTransitionTracker()
        # Per-domain last known non-login URL. Used as the resume target
        # after login completes, and as the recovery target when a
        # spurious login signal fires on an authenticated domain.
        last_safe_url_by_domain: Dict[str, str] = dict(resume_checkpoint.last_safe_url_by_domain) if resume_checkpoint else {}
        # Per-domain counter of consecutive safe-URL recovery attempts
        # against a login signal on an already-authenticated domain. When
        # this hits MAX_LOGIN_RECOVERY_ATTEMPTS we treat the domain as
        # truly re-authentication-needed: drop it from authenticated_domains
        # and fall through to the real login flow. Reset whenever we
        # observe a healthy non-login page for that domain.
        login_recovery_failures: Dict[str, int] = dict(resume_checkpoint.login_recovery_failures) if resume_checkpoint else {}
        # Most recent DOM-level loginDetected flag from an executed dispatch.
        # Used by the ask_user branch to distinguish URL-only matches (stale
        # sub-string hits like /login-history) from genuine login forms.
        last_dom_login_flag: bool = False
        # A wait-for resolution is consumed before the planner on the next
        # loop. This keeps locate -> click free of another planning turn while
        # still routing the click through the executor's normal validation,
        # context policy, accounting, failure recovery, and activity pipeline.
        pending_resolved_decision: Decision | None = None
        effect_tracker = EffectTracker(
            goal=step_goal_for_display,
            capability_id=action_capability_id,
            lang=lang,
            original_request=original_user_request,
        )
        from app.infrastructure.runtime_services import action_receipt_store
        action_history = BrowserActionHistory(
            actor_id=self.user_id,
            attempt_id=(
                f"{str(runtime_output_spec.get('run_id') or '')}:"
                f"{node.node_id}:{subagent_id}"
            ),
            store=action_receipt_store,
            goal=step_goal_for_display,
            original_request=original_user_request,
            lang=lang,
        )
        business_actions = BusinessActionLedger()
        form_transaction = FormTransactionTracker()
        fill_retry_policy = FillRetryPolicy()
        runtime_checkpoint_state = (
            dict(resume_checkpoint.browser_runtime_state or {})
            if resume_checkpoint else {}
        )
        automatic_assistance_counts = {
            str(key): max(0, int(value))
            for key, value in dict(
                runtime_checkpoint_state.get("automatic_assistance_counts") or {}
            ).items()
        }
        business_actions.restore_state(
            dict(runtime_checkpoint_state.get("business_actions") or {}),
        )
        effect_tracker.restore_state(
            dict(runtime_checkpoint_state.get("effect_tracker") or {}),
        )
        form_transaction.restore_state(
            dict(runtime_checkpoint_state.get("form_transaction") or {}),
        )
        fill_retry_policy.restore_state(
            dict(runtime_checkpoint_state.get("fill_retry_policy") or {}),
        )
        deferred_payload = runtime_checkpoint_state.get("deferred_success_receipt")
        deferred_success_receipt: Any | None = (
            EffectReceipt.model_validate(deferred_payload)
            if isinstance(deferred_payload, dict) else None
        )
        replay_guard_emitted = False

        def browser_failure_receipt(*, error: str, status: str = "failed") -> Dict[str, Any]:
            return build_effect_failure(
                error=error,
                receipts=effect_tracker.receipts(),
                status=status,
            )

        async def persist_confirmed_effect(receipt: Any, observation: Observation) -> None:
            try:
                persisted = await action_history.record(receipt, observation)
                if persisted is not None:
                    logger.info(
                        "browser action history persisted",
                        extra={
                            "event": "browser.action_history_persisted",
                            "business_key": persisted.business_key,
                            "operation": persisted.operation_id,
                            "target": persisted.target_id,
                        },
                    )
            except Exception as exc:
                # The action has already happened and was independently
                # verified. History storage must not turn it into a failure.
                logger.warning(
                    "browser action history persist failed",
                    extra={"event": "browser.action_history_persist_failed", "error": str(exc)},
                )

        visible_tool_step = resume_checkpoint.visible_tool_step if resume_checkpoint else 0
        start_step = resume_checkpoint.next_step if resume_checkpoint else 1

        async def save_checkpoint(*, phase: str, next_step: int, status: str = "running") -> None:
            if not self.checkpoint_session:
                return
            learning_trace.capture_new(history)
            await self.checkpoint_session.capture_and_save(
                phase=phase,
                next_step=next_step,
                visible_tool_step=visible_tool_step,
                observation=current_obs,
                history=history,
                authenticated_domains=authenticated_domains,
                last_safe_url_by_domain=last_safe_url_by_domain,
                login_recovery_failures=login_recovery_failures,
                wait_for_text_calls=wait_for_text_calls,
                wait_for_text_refs=wait_for_text_refs,
                last_navigate_target=last_navigate_target,
                consecutive_failures=consecutive_failures,
                soft_recovery_used=soft_recovery_used,
                no_progress_streak=no_progress_streak,
                last_progress_signature=last_progress_signature,
                driver_state=planner.export_checkpoint_state(),
                context_state=task_context.export_checkpoint_state(),
                browser_runtime_state={
                    "business_actions": business_actions.export_state(),
                    "effect_tracker": effect_tracker.export_state(),
                    "form_transaction": form_transaction.export_state(),
                    "fill_retry_policy": fill_retry_policy.export_state(),
                    "automatic_assistance_counts": dict(automatic_assistance_counts),
                    "human_recording_id": active_human_recording_id,
                    "deferred_success_receipt": (
                        deferred_success_receipt.model_dump(mode="json")
                        if deferred_success_receipt is not None else None
                    ),
                },
                learning_trace=learning_trace.export(),
                status=status,
            )

        def schedule_workflow_capture() -> None:
            receipts = [
                item for item in effect_tracker.receipts()
                if isinstance(item, dict)
            ]
            # Admission is tied to the terminal business effect, not to any
            # earlier successful click/open action in the same run.
            if not terminal_effect_allows_cache(action_capability_id, receipts):
                logger.info(
                    "browser workflow cache skipped unverified terminal effect",
                    extra={
                        "event": "browser.workflow_cache_skipped",
                        "reason": "terminal_effect_not_confirmed",
                    },
                )
                return
            learning_trace.capture_new(history)
            distilled_path = learning_trace.distill(
                site_id=site_id_for_node(node),
            )
            learned_history = learning_trace.successful_path(
                site_id=site_id_for_node(node),
            )
            logger.info(
                "browser workflow success path distilled",
                extra={
                    "event": "browser.workflow_cache_path_distilled",
                    "retained_steps": len(distilled_path.entries),
                    "dropped_events": distilled_path.dropped_events,
                    "critical_gaps": len(distilled_path.critical_gaps),
                    "critical_gap_reasons": [
                        f"{gap.tool}:{gap.reason}"
                        for gap in distilled_path.critical_gaps[:10]
                    ],
                },
            )
            browser_workflow_cache.schedule_success_capture(
                user_id=self.user_id,
                main_id=str(runtime_output_spec.get("main_id") or "default"),
                node=node,
                input_context=input_context,
                history=learned_history,
                run_id=str(runtime_output_spec.get("run_id") or ""),
                replayed=bool(getattr(
                    planner,
                    "replay_completed",
                    getattr(planner, "replayed_any", False),
                )),
                matched_workflow=learned_workflow,
                trace_complete=(
                    distilled_path.complete
                    and learning_trace.legacy_gap_count == 0
                ),
                replay_failed=bool(getattr(planner, "replay_failed", False)),
            )

        async def suspend_for_authentication(
            *,
            category: str,
            source: str,
            next_step: int,
            question: str = "",
        ) -> AsyncIterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
            run_id = str((inputs.output_spec or {}).get("run_id") or "")
            interaction = current_obs.interaction if isinstance(current_obs.interaction, dict) else {}
            tab_id = str(interaction.get("tabId") or interaction.get("tab_id") or "")
            logger.info(
                "browser login intervention emitted",
                extra={
                    "event": "browser.login_intervention",
                    "source": source,
                    "authenticated": False,
                    "domain": _domain(current_obs.url) or "",
                    "url": current_obs.url,
                    "question": question[:160],
                    "dom_login": bool(last_dom_login_flag),
                },
            )
            request = BrowserAuthIntervention(
                run_id=run_id,
                node_id=node.node_id,
                user_id=self.user_id,
                chat_session_id=self.session_id,
                browser_session_id=self.session_id,
                subagent_id=subagent_id,
                tab_id=tab_id,
                category=category,
                url=current_obs.url,
                domain=_domain(current_obs.url) or "",
                next_step=next_step,
                source=source,
                lang=lang,
                question=question,
            )
            async for event in suspend_browser_authentication(
                bridge=self.bridge,
                save_checkpoint=save_checkpoint,
                request=request,
            ):
                yield event

        def automatic_assistance_available(
            assistance: BrowserHumanAssistance | None,
        ) -> bool:
            return bool(
                assistance
                and automatic_assistance_counts.get(assistance.dedupe_key, 0) < 1
            )

        async def suspend_for_human_assistance(
            *,
            question: str,
            next_step: int,
            assistance: BrowserHumanAssistance | None = None,
            category: str = "browser",
            handoff: Dict[str, Any] | None = None,
        ) -> AsyncIterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
            nonlocal consecutive_failures
            nonlocal soft_recovery_used
            nonlocal no_progress_streak
            nonlocal last_progress_signature
            nonlocal active_human_recording_id

            handoff = augment_form_assistance_handoff(
                handoff,
                context=input_context,
                completed_candidate_ids=completed_media_candidate_ids(
                    planner.export_checkpoint_state(),
                ),
                user_id=self.user_id,
            )

            if assistance is not None:
                automatic_assistance_counts[assistance.dedupe_key] = (
                    automatic_assistance_counts.get(assistance.dedupe_key, 0) + 1
                )

            # Human action changes the live page state. Preserve business,
            # form and effect ledgers, but do not restore stale loop-failure
            # counters and immediately fail again after the fresh observation.
            consecutive_failures = 0
            soft_recovery_used = False
            no_progress_streak = 0
            last_progress_signature = None

            run_id = str((inputs.output_spec or {}).get("run_id") or "")
            active_human_recording_id = (
                f"assist_{run_id}_{node.node_id}_{uuid.uuid4().hex[:12]}"
                if run_id else f"assist_{uuid.uuid4().hex}"
            )
            try:
                # Start before transferring ownership so the first human click
                # cannot fall into the handoff race window.
                active_human_recording_id = await begin_recorded_human_handoff(
                    self.bridge,
                    recording_id=active_human_recording_id,
                    run_id=run_id,
                    node_id=node.node_id,
                    category=category,
                )
            except Exception as exc:
                active_human_recording_id = ""
                logger.warning(
                    "browser human ownership handoff failed",
                    extra={
                        "event": "browser.human_ownership_handoff_failed",
                        "error": str(exc),
                    },
                )

            interaction = (
                current_obs.interaction
                if isinstance(current_obs.interaction, dict)
                else {}
            )
            tab_id = str(
                interaction.get("tabId") or interaction.get("tab_id") or ""
            )
            resume_context: Dict[str, Any] = {}
            if run_id and self.checkpoint_session:
                await save_checkpoint(
                    phase="waiting_human",
                    next_step=next_step,
                    status="suspended_waiting_approval",
                )
                suspension = await suspend_browser_intervention(
                    run_id=run_id,
                    task_id=self.session_id,
                    node_id=node.node_id,
                    user_id=self.user_id,
                    subagent_id=subagent_id,
                    browser_session_id=self.session_id,
                    tab_id=tab_id,
                    category=category,
                    reason=question,
                    url=current_obs.url,
                    handoff=handoff,
                    mission={
                        "objective": step_goal_for_display,
                        "operation": str((node.meta or {}).get("capability_id") or "browser.read").removeprefix("browser."),
                        "target_name": str(((node.meta or {}).get("semantic_config") or {}).get("targetName") or ""),
                        "target_url": str(((node.meta or {}).get("semantic_config") or {}).get("targetUrl") or ""),
                        "language": lang,
                    },
                )
                resume_context = browser_resume_context(suspension)

            yield {"type": "intervention_required", "content": {
                "category": category,
                "reason": question,
                "url": current_obs.url,
                "domain": _domain(current_obs.url) or "",
                **({"handoff": handoff} if handoff else {}),
                **resume_context,
            }}, {}
            logger.info(
                "browser intervention required",
                extra={
                    "event": "browser.intervention_required",
                    "source": assistance.source if assistance else "ask_user",
                    "domain": _domain(current_obs.url) or "",
                    "url": current_obs.url,
                    "question": question[:160],
                },
            )
            yield {"type": "subagent_done", "content": {
                "subagent_id": subagent_id,
                "node_id": node.node_id,
                "status": "suspended_waiting_approval",
            }}, {
                "gateway": "SUSPEND",
                "browser_receipt": {
                    "status": "intervention_required",
                    "reason": question,
                },
                **(
                    {"intervention_suspension": resume_context}
                    if resume_context else {}
                ),
            }

        def terminal_recovery_plan(
            *,
            source: str,
            error: str,
            prebuilt_assistance: Decision | None = None,
            preserved_handoff: Dict[str, Any] | None = None,
        ) -> BrowserRecoveryPlan:
            return route_browser_recovery(
                source=source,
                observation=current_obs,
                lang=lang,
                error=error,
                has_form_payload=has_form_handoff_payload,
                effect_statuses=tuple(
                    str(item.get("status") or "")
                    for item in effect_tracker.receipts()
                    if isinstance(item, dict)
                ),
                prebuilt_assistance=prebuilt_assistance,
                preserved_handoff=preserved_handoff,
            )

        def recovery_assistance_available(plan: BrowserRecoveryPlan) -> bool:
            return bool(
                plan.can_assist
                and automatic_assistance_available(plan.assistance)
            )

        async def suspend_for_recovery(
            plan: BrowserRecoveryPlan,
            *,
            next_step: int,
        ) -> AsyncIterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
            assert plan.decision is not None
            args = dict(plan.decision.args or {})
            handoff = args.get("handoff")
            async for event in suspend_for_human_assistance(
                question=str(args.get("question") or plan.reason),
                next_step=next_step,
                assistance=plan.assistance,
                category=str(args.get("category") or "browser"),
                handoff=dict(handoff) if isinstance(handoff, dict) else None,
            ):
                yield event

        # A resumed auth checkpoint is only considered authenticated after
        # a fresh observation proves that the blocking page is gone. The old
        # implementation marked the scope authenticated unconditionally,
        # which allowed a manual "hand back" on an unchanged login page to
        # resume the planner with a false auth fact.
        if resume_checkpoint and resume_checkpoint.phase == "waiting_auth":
            resume_signal = dict((inputs.output_spec or {}).get("resume_signal") or {})
            explicit_auth_state = str((current_obs.auth or {}).get("state") or "")
            if authentication_resume_is_blocked(
                auth_state=explicit_auth_state,
                url_looks_blocked=_is_login_like_url(current_obs.url or ""),
                resume_signal=resume_signal,
            ):
                auth_category = (
                    "registration"
                    if explicit_auth_state == "registration_required"
                    else "login"
                )
                async for event in suspend_for_authentication(
                    category=auth_category,
                    source="resume_validation",
                    next_step=start_step,
                ):
                    yield event
                return
            resumed_scope = site_scope(current_obs.url) or _domain(current_obs.url)
            if resumed_scope:
                authenticated_domains.add(resumed_scope)
                last_safe_url_by_domain[resumed_scope] = current_obs.url

        resume_signal = dict(runtime_output_spec.get("resume_signal") or {})
        assistance_contract = resume_contract(resume_signal)
        assistance_kind = str(assistance_contract.get("kind") or "")
        if (
            assistance_kind in {
                FORM_COMMIT_CATEGORY,
                FORM_EFFECT_VERIFY_CATEGORY,
                FORM_TASK_COMPLETION_CATEGORY,
            }
            and not current_obs.fresh
        ):
            reason = (
                "人工操作后无法读取最新页面，因此没有采纳旧页面状态，也不会重复保存/提交。"
                if lang == "zh" else
                "The live page could not be read after human action; stale state was not accepted and the commit will not be replayed."
            )
            recovery = terminal_recovery_plan(
                source=RESUME_RECONCILIATION_UNAVAILABLE,
                error=reason,
                preserved_handoff={"contract": assistance_contract},
            )
            if recovery_assistance_available(recovery):
                async for event in suspend_for_recovery(
                    recovery,
                    next_step=start_step,
                ):
                    yield event
                return
            yield {"type": "activity", "content": {"kind": "warning", "message": reason}}, {}
            yield {"type": "subagent_done", "content": {
                "subagent_id": subagent_id,
                "node_id": node.node_id,
                "status": "failed_terminal",
            }}, {"browser_receipt": browser_failure_receipt(error=reason, status="resume_reconciliation_unavailable")}
            return
        human_commit_reconciliation = assess_human_commit_reconciliation(
            capability_id=action_capability_id,
            assistance_kind=assistance_kind,
            human_outcome=str(resume_signal.get("human_outcome") or ""),
            before_url=resume_checkpoint.current_url if resume_checkpoint else "",
            after=current_obs,
            form_state=form_transaction.export_state(),
            existing_receipts=effect_tracker.receipts(),
        )
        if human_commit_reconciliation.should_ask:
            confirmation = build_task_completion_confirmation_decision(
                reason=human_commit_reconciliation.reason,
                evidence=human_commit_reconciliation.evidence,
                lang=lang,
            )
            async for event in suspend_for_human_assistance(
                question=str(confirmation.args.get("question") or ""),
                next_step=start_step,
                category=FORM_TASK_COMPLETION_CATEGORY,
                handoff=dict(confirmation.args.get("handoff") or {}),
            ):
                yield event
            return
        manual_receipt: EffectReceipt | None = None
        if assistance_kind == FORM_EFFECT_VERIFY_CATEGORY:
            outcome = resume_outcome(
                resume_signal,
                expected_kind=FORM_EFFECT_VERIFY_CATEGORY,
            )
            contract_key = str(
                dict(assistance_contract.get("payload") or {}).get("contract_key") or ""
            )
            previous_receipt = effect_tracker.receipt(contract_key)
            if outcome and previous_receipt is not None:
                manual_receipt = manual_effect_receipt(
                    previous=previous_receipt,
                    outcome=outcome,
                    observation=current_obs,
                )
                effect_tracker.adopt_manual_receipt(manual_receipt)
        elif assistance_kind == FORM_COMMIT_CATEGORY:
            outcome = resume_outcome(
                resume_signal,
                expected_kind=FORM_COMMIT_CATEGORY,
            )
            if outcome == "completed":
                manual_receipt = manual_commit_receipt(
                    contract=assistance_contract,
                    observation=current_obs,
                )
                effect_tracker.adopt_manual_receipt(manual_receipt)
        elif assistance_kind == FORM_TASK_COMPLETION_CATEGORY:
            outcome = resume_outcome(
                resume_signal,
                expected_kind=FORM_TASK_COMPLETION_CATEGORY,
            )
            if outcome == "task_completed":
                manual_receipt = manual_commit_receipt(
                    contract=assistance_contract,
                    observation=current_obs,
                )
                effect_tracker.adopt_manual_receipt(manual_receipt)

        if manual_receipt is not None:
            business_actions.record(manual_receipt)
            form_transaction.after_effect(manual_receipt, current_obs)
            await persist_confirmed_effect(manual_receipt, current_obs)
            apply_effect_receipt(
                context=task_context,
                tracks_context_state=context_tracks_state,
                receipt=manual_receipt,
                observation=current_obs,
            )
            if manual_receipt.status == "confirmed_success":
                # Reuse the normal verified-effect completion path after one
                # fresh read, instead of duplicating result construction here.
                deferred_success_receipt = manual_receipt
                pending_resolved_decision = Decision(
                    tool="browser_observe",
                    args={},
                    rationale="reconcile live page after human-confirmed form completion",
                )
            elif manual_receipt.status == "confirmed_failure":
                _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                for failure_event in build_effect_business_failure_events(
                    receipt=manual_receipt,
                    objective=str(node.goal or ""),
                    steps=len(history),
                    lang=lang,
                    result_data=project_verified_operation_result(
                        receipt=manual_receipt,
                        context=task_context,
                        form_state=form_transaction.export_state(),
                        observation=current_obs,
                    ),
                    subagent_id=subagent_id,
                    node_id=node.node_id,
                    emit_answer=not bool(_topology),
                ):
                    yield failure_event
                return
            else:
                # The human explicitly chose "uncertain". Preserve the replay
                # block and stop safely instead of asking the model to submit again.
                reason = (
                    "人工确认结果仍不确定；为避免重复提交，任务已安全停止。"
                    if lang == "zh" else
                    "The outcome remains uncertain; the task stopped safely without replaying the commit."
                )
                yield {"type": "activity", "content": {"kind": "warning", "message": reason}}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": subagent_id,
                    "node_id": node.node_id,
                    "status": "failed_terminal",
                }}, {"browser_receipt": browser_failure_receipt(error=reason, status="unknown_side_effect")}
                return

        if assistance_kind in {
            FORM_COMMIT_CATEGORY,
            FORM_EFFECT_VERIFY_CATEGORY,
            FORM_TASK_COMPLETION_CATEGORY,
        }:
            outcome = str(resume_signal.get("human_outcome") or "").strip().lower()
            if outcome in {"unable", "uncertain"}:
                reason = (
                    "人工协助后仍无法确认或完成该表单操作，任务已停止且不会重复提交。"
                    if lang == "zh" else
                    "The form action could not be completed or confirmed after assistance; it will not be replayed."
                )
                yield {"type": "activity", "content": {"kind": "warning", "message": reason}}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": subagent_id,
                    "node_id": node.node_id,
                    "status": "failed_terminal",
                }}, {"browser_receipt": browser_failure_receipt(error=reason, status="human_assistance_unresolved")}
                return

        step = start_step - 1
        execution_budget = BrowserExecutionBudget.start(
            float((inputs.output_spec or {}).get("execution_budget_seconds") or 270)
        )
        execution_budget_exhausted = False
        execution_budget_effect_unknown = False
        done_block_recovery = DoneBlockRecovery()
        for step in range(start_step, MAX_STEPS + 1):
            if execution_budget.expired:
                execution_budget_exhausted = True
                break
            if resume_checkpoint and current_obs.fresh and not driver_resume_reconciled:
                apply_driver_resume_signal(planner, resume_signal, current_obs)
                driver_resume_reconciled = True
            if not current_obs.fresh:
                pending_resolved_decision = Decision(
                    tool="browser_observe",
                    args={},
                    rationale="system freshness barrier: refresh DOM before the next decision",
                )
            # Stateful contexts may inject a synthetic record before planning.
            if context_tracks_state and current_obs.fresh:
                injected = task_context.before_decision(history, current_obs)
                if injected is not None:
                    history.append(injected)
                    _msg = task_context.timeline_for_record(injected) or str(injected.result_digest or '')[:180]
                    for _line in [x.strip() for x in str(_msg or "").splitlines() if x.strip()]:
                        yield {"type": "activity", "content": {
                            "kind": "analyze",
                            "message": _line,
                        }}, {}
                    continue

            # First-step short-circuit: if we're sitting on about:blank and
            # exactly one entry URL candidate was resolved (either a user-
            # typed URL or a named-site from the profile registry), navigate
            # there directly instead of letting the planner potentially ask
            # the user for a URL we already know. Only fires on step 1 and
            # only when there's no ambiguity — multi-candidate cases go
            # through the planner so it can pick by user-request semantics.
            forced_decision = pending_resolved_decision
            pending_resolved_decision = None
            if forced_decision is None:
                forced_decision = recovery_decision_after_guard_failure(
                    history,
                    current_obs,
                    lang=lang,
                )
            if (
                forced_decision is None
                and step == 1
                and len(candidate_entries) == 1
                and str(current_obs.url or "").strip() in ("", "about:blank")
            ):
                forced_url = candidate_entries[0]["url"]
                try:
                    forced_domain = urlparse(forced_url).hostname or ""
                except Exception:
                    forced_domain = ""
                forced_decision = Decision(
                    tool="browser_navigate",
                    args={"url": forced_url, "domain": forced_domain},
                    rationale=(
                        "auto-navigate from single resolved entry "
                        f"(source={candidate_entries[0].get('source')})"
                    ),
                )
                logger.info("browser first step short-circuit", extra={"event": "browser.first_step_short_circuit", "url": forced_url, "source": candidate_entries[0].get("source")})
            # System-owned navigation: when the flow requires a known
            # page (e.g. after create lands on a detail route and the
            # next sub-phase needs the list), let the context synthesize
            # the navigate decision instead of hoping the LLM figures it
            # out. Preempts the planner call entirely.
            if context_tracks_state and forced_decision is None:
                try:
                    nav = task_context.maybe_force_navigation(current_obs)
                except Exception:
                    nav = None
                if nav is not None:
                    forced_decision = nav
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": task_context.timeline_text("forced_nav"),
                    }}, {}

            # Rules layer: before paying for an LLM turn, try to resolve
            # the current phase's action from deterministic rules. A
            # unique candidate → auto-click; ambiguous / missing → fall
            # through to the planner with the usual ledger context.
            if context_tracks_state and forced_decision is None:
                try:
                    rule_dec = task_context.suggest_next_action(current_obs)
                except Exception:
                    rule_dec = None
                if rule_dec is not None:
                    forced_decision = rule_dec
                    logger.info(
                        "browser context rule auto execution",
                        extra={"event": "browser.context_rule_autoexec", "tool": rule_dec.tool, "ref": str((rule_dec.args or {}).get("ref") or ""), "rationale": rule_dec.rationale[:120]},
                    )
                    if "nav" in locals() and nav is not None:
                        logger.info("browser context forced navigation", extra={"event": "browser.context_forced_navigation", "url": str(nav.args.get("url") or "")})
            # pass the state ledger to the planner every turn.
            # The LLM reads an authoritative "where are we / what's next /
            # what's off-limits" card instead of inferring from history.
            _ledger = None
            try:
                _ledger = task_context.build_state_ledger(current_obs) if context_tracks_state else None
            except Exception:
                _ledger = None
            scope_state = form_transaction.interaction_scope_state(current_obs)
            if scope_state is not None:
                _ledger = dict(_ledger or {})
                constraints = list(_ledger.get("action_constraints") or [])
                constraints.append(scope_state["constraint"])
                notes = list(_ledger.get("notes") or [])
                notes.append(scope_state["note"])
                pinned_refs = list(_ledger.get("pinned_refs") or [])
                pinned_refs.extend(scope_state["allowed_refs"])
                _ledger.update({
                    "action_constraints": constraints,
                    "notes": notes,
                    "pinned_refs": list(dict.fromkeys(pinned_refs)),
                })
            decision_is_system_owned = forced_decision is not None
            decision = forced_decision or await planner.next_step(
                goal, history, current_obs, state_ledger=_ledger,
            )
            done_block_recovery.record_action(decision)
            # Reuse an immediately preceding screenshot when the page and
            # capture scope are unchanged. This runs before timeline emission,
            # so a planner retry does not become another visible/tool step.
            visual_reuse = redundant_visual_observation(
                decision,
                current=current_obs,
                history=history,
            )
            if visual_reuse.blocked:
                history.append(StepRecord(
                    observation=current_obs,
                    decision=decision,
                    ok=False,
                    error=visual_reuse.reason,
                    result_digest="existing screenshot retained",
                ))
                logger.info(
                    "duplicate visual observation reused",
                    extra={
                        "event": "browser.visual_observation_reused",
                        "tool": decision.tool,
                        "url": current_obs.url,
                        "state_fingerprint": current_obs.state_fingerprint,
                    },
                )
                continue

            # Xiaohongshu creator console is a JS-heavy SPA and the root
            # /login /new/home entry often yields empty observations before
            # hydration. For publish flows, jump straight to the resolved
            # publish URL (user-supplied > yaml default) instead of letting
            # the planner guess.
            if (
                is_xhs_publish_goal
                and xhs_publish_url
                and decision.tool == "browser_navigate"
                and str(decision.args.get("url") or "").strip().rstrip("/") in _XHS_LANDING_URLS
            ):
                decision = Decision(
                    tool=decision.tool,
                    args={**dict(decision.args or {}), "url": xhs_publish_url},
                    rationale=(decision.rationale or "") + " | rewritten to resolved xiaohongshu publish route",
                )
                logger.info("xiaohongshu navigate rewritten", extra={"event": "browser.xhs_navigate_rewritten", "url": xhs_publish_url})

            # Only model exploration is provenance-gated. Context-owned
            # routing, recorded skill steps and auth recovery carry their own
            # authoritative URL source; browser redirects never create a
            # Decision and therefore never reach this gate.
            if decision.tool in ("browser_navigate", "browser_tab_new"):
                skill_owned = str(decision.rationale or "").startswith("[skill_driver]")
                provenance = assess_navigation_provenance(
                    target_url=str(decision.args.get("url") or "").strip(),
                    current_observation=current_obs,
                    history_observations=(record.observation for record in history),
                    original_user_request=original_user_request,
                    site_profiles=visible_sites,
                    trusted_urls=(xhs_publish_url,) if xhs_publish_url else (),
                    system_owned=decision_is_system_owned or skill_owned,
                )
                if provenance.audit_only:
                    logger.warning(
                        "browser URL provenance audit",
                        extra={
                            "event": "browser.url_provenance_audit",
                            "url": str(decision.args.get("url") or "")[:160],
                            "reason": provenance.reason,
                        },
                    )
                if not provenance.allowed:
                    hint = (
                        "目标 URL 没有可靠来源：不要根据按钮文字猜站内路径；请点击页面中已观察到的链接，或使用用户/站点设置给出的完整 URL。"
                        if lang == "zh" else
                        "The target URL is not grounded: do not invent a site route from button text; click an observed link or use an explicit user/site URL."
                    )
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=decision,
                        ok=False,
                        error=f"{hint} ({provenance.reason})",
                        result_digest="",
                    ))
                    notify_driver_rejection(
                        planner,
                        decision,
                        current_obs,
                        category="navigation_provenance",
                        reason=provenance.reason,
                    )
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": hint,
                    }}, {}
                    logger.warning(
                        "browser URL provenance blocked",
                        extra={
                            "event": "browser.url_provenance_blocked",
                            "url": str(decision.args.get("url") or "")[:160],
                            "reason": provenance.reason,
                        },
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        break
                    continue

            visible_tool_step += 1
            yield {"type": "activity", "content": {
                "kind": "analyze",
                "message": (f"步骤 {visible_tool_step}: {decision.tool}" if lang == "zh"
                            else f"Step {visible_tool_step}: {decision.tool}"),
                "visibility": "debug",
            }}, {}

            if (
                not replay_guard_emitted
                and action_contract_blocks_whole_node_replay(action_capability_id)
                and decision.tool in {
                    "browser_fill", "browser_type_at", "browser_select",
                    "browser_click", "browser_click_at", "browser_press",
                    "browser_upload_file", "browser_paste_image",
                    "browser_execute_workflow",
                }
            ):
                replay_guard_emitted = True
                yield {"type": "runtime_status", "content": {
                    "side_effect_guard": {
                        "status": "mutation_started",
                        "blocks_replay": True,
                        "capability_id": action_capability_id,
                        "reason": "browser write mission has started; resume or verify instead of replaying the whole node",
                    },
                }}, {}

            # Terminal / control tools
            if decision.tool == "browser_done":
                # A write can be confirmed only after a later observation. Sync
                # that delayed receipt before consulting the task-level ledger;
                # otherwise the effect tracker and context disagree forever.
                done_refreshed_receipts = await effect_tracker.refresh_pending(
                    after=current_obs,
                    supplemental_evidence=form_transaction.outcome_evidence(current_obs),
                )
                for refreshed_receipt in done_refreshed_receipts:
                    business_actions.record(refreshed_receipt)
                    notify_effect_receipt(planner, refreshed_receipt)
                    await persist_confirmed_effect(refreshed_receipt, current_obs)
                    form_transaction.after_effect(refreshed_receipt, current_obs)
                    receipt_application = apply_effect_receipt(
                        context=task_context,
                        tracks_context_state=context_tracks_state,
                        receipt=refreshed_receipt,
                        observation=current_obs,
                    )
                    if receipt_application.error:
                        logger.warning(
                            "browser context delayed effect hook failed",
                            extra={
                                "event": "browser.context_delayed_effect_hook_failed",
                                "error": receipt_application.error,
                            },
                        )
                    logger.info(
                        "browser pending effect refreshed before done",
                        extra={
                            "event": "browser.effect_refreshed_before_done",
                            "contract_key": refreshed_receipt.contract_key,
                            "status": refreshed_receipt.status,
                            "action": refreshed_receipt.action_name,
                            "completes_goal": refreshed_receipt.completes_goal,
                            "goal_completed": receipt_application.goal_completed,
                        },
                    )
                    if refreshed_receipt.status == "confirmed_failure":
                        _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                        for failure_event in build_effect_business_failure_events(
                            receipt=refreshed_receipt,
                            objective=str(node.goal or ""),
                            steps=len(history),
                            lang=lang,
                            result_data=project_verified_operation_result(
                                receipt=refreshed_receipt,
                                context=task_context,
                                form_state=form_transaction.export_state(),
                                observation=current_obs,
                            ),
                            subagent_id=subagent_id,
                            node_id=node.node_id,
                            emit_answer=not bool(_topology),
                        ):
                            yield failure_event
                        return
                    if receipt_application.goal_completed:
                        summary, completion_meta = build_effect_completion(
                            receipt=refreshed_receipt,
                            objective=str(node.goal or ""),
                            steps=len(history),
                            lang=lang,
                            result_data=project_verified_operation_result(
                                receipt=refreshed_receipt,
                                context=task_context,
                                form_state=form_transaction.export_state(),
                                observation=current_obs,
                            ),
                        )
                        _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                        if not _topology:
                            yield {"type": "answer", "content": summary}, {}
                        schedule_workflow_capture()
                        yield {"type": "subagent_done", "content": {
                            "subagent_id": subagent_id,
                            "node_id": node.node_id,
                            "status": "succeeded",
                        }}, completion_meta
                        return
                # Stateful contexts may reject browser_done until their
                # task-specific completion conditions have been verified.
                if context_tracks_state and not task_context.ready_to_done():
                    blocked_hint = task_context.done_blocked_hint(current_obs)
                    history.append(blocked_hint)
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": str(blocked_hint.error or blocked_hint.result_digest or "browser_done blocked"),
                    }}, {}
                    logger.info(
                        "browser context done blocked",
                        extra={
                            "event": "browser.context_done_blocked",
                            "context": type(task_context).__name__,
                            "phase": str(getattr(task_context, "phase", "")),
                        },
                    )
                    recovery = done_block_recovery.blocked(
                        fingerprint=(
                            f"{type(task_context).__name__}:"
                            f"{getattr(task_context, 'phase', '')}:"
                            f"{blocked_hint.error or blocked_hint.result_digest or ''}"
                        ),
                    )
                    if recovery.terminal:
                        reason = (
                            "浏览器多次尝试结束，但任务上下文在刷新页面后仍缺少必要证据；"
                            "已安全停止，避免继续重复操作。"
                            if lang == "zh" else
                            "The browser repeatedly tried to finish, but required context evidence "
                            "remained missing after fresh observations; stopped safely to avoid a loop."
                        )
                        yield {"type": "activity", "content": {
                            "kind": "error", "message": reason,
                        }}, {}
                        yield {"type": "subagent_done", "content": {
                            "subagent_id": subagent_id,
                            "node_id": node.node_id,
                            "status": "failed_terminal",
                        }}, {"browser_receipt": browser_failure_receipt(
                            error=reason,
                            status="context_evidence_incomplete",
                        )}
                        return
                    pending_resolved_decision = recovery.retry
                    continue
                # ─── check-before-done gate ────────────────────────
                # Any conclusion (positive or negative) after a state-
                # changing action MUST be backed by a fresh page read.
                # Walk history: if the most recent mutation (click/fill/
                # select/press/upload) happened after the most recent
                # observation tool (observe/read_text/navigate/scroll/
                # screenshot/tab_new/back/forward), the LLM is calling
                # done on a stale snapshot. Reject and force a re-read.
                # Zero keyword matching — pure structural invariant.
                _post_action_check = post_action_observation_check(history)
                if _post_action_check.required:
                    _hint = (
                        "⛔ 不允许在动作之后不重观察就 browser_done。"
                        "\n你最近一次动作（fill/click/select/press/upload）之后还没有任何"
                        " browser_observe / browser_read_text / browser_navigate / "
                        "browser_scroll 等产生新快照的步骤 —— 当前 observation 是"
                        "**动作之前**的旧快照，任何结论（成功/失败/bug）都是基于陈旧信息。"
                        "\n下一步必须先做一次 browser_observe（或 read_text / scroll）"
                        "拿到动作后的真实页面状态，再决定是不是 browser_done。"
                        "\n注意：browser_wait_for 不算重观察 —— 它不返回 DOM 快照。"
                        if lang == "zh" else
                        "⛔ browser_done not allowed without a post-action observation."
                        "\nYour most recent mutation (fill/click/select/press/upload) has"
                        " no following snapshot-producing step (browser_observe / read_text /"
                        " navigate / scroll / screenshot). The current observation reflects"
                        " the page BEFORE the mutation; any conclusion you draw (success/"
                        "failure/bug) is based on stale information."
                        "\nYour next step MUST be a fresh read (browser_observe / read_text /"
                        " scroll) so you see the post-action state, THEN decide whether to"
                        " browser_done."
                        "\nNote: browser_wait_for does NOT count — it does not return a DOM"
                        " snapshot."
                    )
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=Decision(
                            tool="__check_required__", args={},
                            rationale="system: mutation without post-action observation",
                        ),
                        ok=False, error=_hint, result_digest="",
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": (
                            "未在动作后重观察，已拦截 browser_done —— 请先 observe"
                            if lang == "zh" else
                            "browser_done blocked: no post-action observation — observe first"
                        ),
                    }}, {}
                    logger.info("browser done blocked for missing check", extra={"event": "browser.done_blocked_need_check", "last_mutation_step": _post_action_check.last_mutation_index, "last_observation_step": _post_action_check.last_fresh_index})
                    # Auto-observe injection. Without this, observed
                    # behaviour is: LLM calls done → blocked → next turn
                    # LLM calls done AGAIN (ignoring the hint) → blocked
                    # → ... → step budget exhausted (we saw 9 consecutive
                    # done attempts in one run). Inject a real observe
                    # ourselves right now so the gate condition flips
                    # (last_obs > last_mut) — LLM's next done attempt
                    # will pass through, AND the resulting report carries
                    # the post-action snapshot the gate was protecting.
                    # Net cost: same one wasted step the LLM was going
                    # to burn anyway, but now it produces useful
                    # observation data instead of a no-op.
                    try:
                        _auto_obs_args: Dict[str, Any] = {}
                        if (
                            task_context.active
                            and getattr(task_context, "round", 0) == 1
                            and getattr(task_context, "round1_op_idx", 0) in (2, 3)
                        ):
                            _auto_obs_args["with_hover_reveal"] = True
                        _auto_obs_dec = Decision(
                            tool="browser_observe", args=_auto_obs_args,
                            rationale="system: auto-observe after done-blocked (post-mutation guard)",
                        )
                        _auto_res, _auto_ok, _auto_err = await self._dispatch(_auto_obs_dec)
                        _fresh = _update_obs(current_obs, "browser_observe", _auto_res)
                        history.append(StepRecord(
                            observation=_fresh,
                            decision=_auto_obs_dec,
                            ok=_auto_ok,
                            error=_auto_err,
                            result_digest=_digest("browser_observe", _auto_res),
                        ))
                        current_obs = _fresh
                        logger.info("auto observe after done-blocked", extra={"event": "browser.done_blocked_auto_observe", "ok": bool(_auto_ok), "url": getattr(_fresh, "url", "")})
                    except Exception as exc:
                        logger.warning("auto observe after done-blocked failed", extra={"event": "browser.done_blocked_auto_observe_failed", "error": str(exc)})
                    continue
                # ─────────────────────────────────────────────────────
                refreshed_effects = await effect_tracker.refresh_pending(
                    after=current_obs,
                    supplemental_evidence=form_transaction.outcome_evidence(current_obs),
                )
                exhausted_effect = next((
                    item for item in refreshed_effects
                    if bool((item.fingerprint or {}).get("verification_exhausted"))
                ), None)
                if exhausted_effect is not None:
                    verification = build_effect_verification_decision(
                        exhausted_effect,
                        lang=lang,
                    )
                    async for event in suspend_for_human_assistance(
                        question=str(verification.args.get("question") or ""),
                        next_step=step + 1,
                        category=FORM_EFFECT_VERIFY_CATEGORY,
                        handoff=dict(verification.args.get("handoff") or {}),
                    ):
                        yield event
                    return
                pending_effects = effect_tracker.pending_receipts()
                if pending_effects:
                    pending_hint = (
                        "提交动作已经发生，但业务结果尚未核验。请读取结果页或根据业务对象回查，"
                        "不要重复提交，也不要直接结束任务。"
                        if lang == "zh" else
                        "The commit occurred, but its business result is still unverified. "
                        "Inspect or look up the resulting object; do not resubmit or finish yet."
                    )
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=decision,
                        ok=False,
                        error=pending_hint,
                        result_digest=json.dumps(
                            [item.model_dump(mode="json") for item in pending_effects],
                            ensure_ascii=False,
                        )[:6000],
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "analyze", "message": pending_hint,
                    }}, {}
                    logger.info(
                        "browser done blocked by pending effect",
                        extra={
                            "event": "browser.done_blocked_pending_effect",
                            "contracts": [item.contract_key for item in pending_effects],
                        },
                    )
                    continue
                effect_completion = assess_effect_completion(
                    action_capability_id,
                    effect_tracker.receipts(),
                    lang=lang,
                )
                if not effect_completion.allowed:
                    if (
                        not effect_tracker.receipts()
                        and assistance_kind in {"form_fill", "form_media", "form_commit"}
                        and str(resume_signal.get("human_outcome") or "").strip().lower() == "completed"
                    ):
                        confirmation = build_task_completion_confirmation_decision(
                            reason=(
                                "人工操作后 Agent 判断任务可以结束，但系统没有人工提交动作的回执"
                            ),
                            evidence=("browser_done reached without an agent-side effect receipt",),
                            lang=lang,
                        )
                        async for event in suspend_for_human_assistance(
                            question=str(confirmation.args.get("question") or ""),
                            next_step=step + 1,
                            category=FORM_TASK_COMPLETION_CATEGORY,
                            handoff=dict(confirmation.args.get("handoff") or {}),
                        ):
                            yield event
                        return
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=decision,
                        ok=False,
                        error=effect_completion.reason,
                        result_digest=json.dumps(effect_tracker.receipts(), ensure_ascii=False)[:6000],
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": effect_completion.reason,
                    }}, {}
                    logger.info(
                        "browser done blocked without confirmed side effect",
                        extra={
                            "event": "browser.done_blocked_unconfirmed_effect",
                            "capability": action_capability_id,
                        },
                    )
                    continue
                summary = str(decision.args.get("summary") or "")
                # Structured data returned by the LLM (e.g. scraped news
                # items, form submission receipts, etc.). Written to the
                # node artifact so downstream nodes can read it via
                # predecessor_artifacts / input_artifacts in their payload.
                data = decision.args.get("data")
                if not isinstance(data, dict):
                    data = {}
                # ─── action-contract gate ───────────────────────────
                # The planner labels each browser step with a concrete
                # capability (browser.read / submit / modify / …); every
                # capability declares a structural produce shape. Reject
                # browser_done whose data doesn't match the declared
                # shape and loop back — LLM sees the reason in the next
                # turn's history and either scans more or calls fail.
                cap_id = str((node.meta or {}).get("capability_id") or "").strip().lower()
                contract = action_contract_validate_data(cap_id, data)
                # Diagnostic: log every contract outcome so you can trace
                # whether the action taxonomy is actually firing in prod.
                logger.debug(
                    "browser done contract checked",
                    extra={"event": "browser.contract_check", "capability": cap_id or "<untyped>", "ok": contract.ok, "data_keys": list(data.keys())[:6] if isinstance(data, dict) else [], "reason": (contract.reason or "")[:180]},
                )
                if not contract.ok:
                    missing_preview = ", ".join(contract.missing[:6])
                    reason = contract.reason or "contract violation"
                    logger.warning(
                        "browser done rejected by contract",
                        extra={"event": "browser.done_contract_rejected", "capability": cap_id or "<untyped>", "reason": reason, "missing": missing_preview},
                    )
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=decision,
                        ok=False,
                        error=(
                            f"browser_done rejected by contract ({cap_id}): {reason}. "
                            f"Missing/empty: {missing_preview}. "
                            "Either keep scanning the page to capture the real values, "
                            "or call browser_fail explaining which piece is unavailable."
                        ),
                        result_digest="",
                    ))
                    consecutive_failures += 1
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": (
                            f"browser_done 被合同拒绝（{cap_id}）：{reason}"
                            if lang == "zh"
                            else f"browser_done rejected by contract ({cap_id}): {reason}"
                        ),
                    }}, {}
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        recovery = terminal_recovery_plan(
                            source=OUTPUT_CONTRACT_EXHAUSTED,
                            error=reason,
                        )
                        if recovery_assistance_available(recovery):
                            async for event in suspend_for_recovery(
                                recovery,
                                next_step=step + 1,
                            ):
                                yield event
                            return
                        yield {"type": "activity", "content": {
                            "kind": "error",
                            "message": (
                                f"⚠ 无法满足本步契约（{cap_id}）：{reason}"
                                if lang == "zh"
                                else f"⚠ Could not satisfy step contract ({cap_id}): {reason}"
                            ),
                        }}, {}
                        yield {"type": "subagent_done", "content": {
                            "subagent_id": subagent_id, "node_id": node.node_id,
                            "status": "failed_terminal",
                        }}, {"browser_receipt": {
                            **browser_failure_receipt(error=reason, status="failed_contract"),
                            "capability_id": cap_id,
                            "reason": reason,
                        }}
                        return
                    continue  # back to the planner loop, LLM sees the rejection
                if context_tracks_state:
                    summary, data = task_context.finalize(summary, data)
                answer_content = render_browser_result(
                    summary=summary,
                    data=data,
                    lang=lang,
                ) or ("任务完成" if lang == "zh" else "Task completed")
                _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                if not _topology:
                    yield {"type": "answer", "content": answer_content}, {}
                effect_receipts = effect_tracker.receipts()
                meta: Dict[str, Any] = {"browser_receipt": {
                    "status": "ok",
                    "summary": summary,
                    "steps": len(history),
                    **({"effect_receipts": effect_receipts} if effect_receipts else {}),
                }}
                # Flatten structured data into meta so it becomes part of
                # the node artifact. Existing browser_receipt field is kept
                # untouched for backward compatibility.
                for k, v in data.items():
                    if k == "browser_receipt":
                        continue  # don't let LLM overwrite our receipt
                    meta[k] = v
                meta["browser_result"] = build_browser_result(
                    objective=str(node.goal or ""),
                    summary=summary,
                    data=data,
                )
                schedule_workflow_capture()
                yield {"type": "subagent_done", "content": {
                    "subagent_id": subagent_id, "node_id": node.node_id, "status": "succeeded",
                }}, meta
                return

            if decision.tool == "browser_ask_user":
                q = str(decision.args.get("question") or "")
                ask_category = str(decision.args.get("category") or "browser")
                ask_handoff = decision.args.get("handoff")
                if not isinstance(ask_handoff, dict):
                    ask_handoff = None
                automatic_assistance: BrowserHumanAssistance | None = None
                if decision.rationale == "deterministic recovery after read-budget exhaustion":
                    automatic_assistance = browser_human_assistance(
                        source=READ_BUDGET,
                        observation=current_obs,
                        lang=lang,
                    )
                    if not automatic_assistance_available(automatic_assistance):
                        reason = (
                            "当前页面在人工协助后仍无法找到可靠的下一步"
                            if lang == "zh" else
                            "The page still has no reliable next step after human assistance"
                        )
                        yield {"type": "activity", "content": {
                            "kind": "error",
                            "message": reason,
                        }}, {}
                        yield {"type": "subagent_done", "content": {
                            "subagent_id": subagent_id,
                            "node_id": node.node_id,
                            "status": "failed_terminal",
                        }}, {"browser_receipt": browser_failure_receipt(error=reason)}
                        return
                    q = automatic_assistance.question
                ask_domain = _domain(current_obs.url) or ""
                ask_scope = site_scope(current_obs.url) or ask_domain
                # URL says login. Three cases, in order:
                #   1) Domain not authenticated yet → real login intervention
                #      (let the next iteration enter the login wait loop).
                #   2) Authenticated, URL-only match (no DOM form) → stale
                #      substring hit (e.g. /login-history); fall through to
                #      the normal ask_user suspend below.
                #   3) Authenticated AND DOM confirms a login form → genuine
                #      re-auth OR LLM mis-navigation. Try safe-URL recovery
                #      first; on exhausted budget downgrade to real login
                #      (clear the authenticated flag + surface intervention).
                explicit_auth_request = ask_category in {
                    "login", "authentication", "runtime_authentication",
                }
                if explicit_auth_request or _login_detected_from_obs(current_obs):
                    is_authenticated = bool(ask_scope) and ask_scope in authenticated_domains
                    if not is_authenticated:
                        auth_category = (
                            "registration"
                            if str((current_obs.auth or {}).get("state") or "") == "registration_required"
                            else "login"
                        )
                        async for event in suspend_for_authentication(
                            category=auth_category,
                            source="ask_user",
                            next_step=step + 1,
                            question=q,
                        ):
                            yield event
                        return
                    if last_dom_login_flag:
                        attempts = login_recovery_failures.get(ask_scope, 0)
                        if attempts < MAX_LOGIN_RECOVERY_ATTEMPTS:
                            login_recovery_failures[ask_scope] = attempts + 1
                            safe_url = (
                                last_safe_url_by_domain.get(ask_scope)
                                or (last_navigate_target if last_navigate_target and not _is_login_like_url(last_navigate_target) else "")
                                or (f"https://{ask_domain}/" if ask_domain else "")
                            )
                            remaining = MAX_LOGIN_RECOVERY_ATTEMPTS - attempts - 1
                            yield {"type": "activity", "content": {
                                "kind": "analyze",
                                "message": (
                                    f"已登录的 {ask_domain} 出现登录表单，尝试恢复回 {safe_url}（剩余 {remaining} 次）"
                                    if lang == "zh"
                                    else f"Login form on authenticated {ask_domain}; recovering to {safe_url} (remaining {remaining})"
                                ),
                            }}, {}
                            if safe_url:
                                try:
                                    re_result = await self._dispatch(Decision(
                                        tool="browser_navigate",
                                        args={"url": safe_url},
                                        rationale="safe-URL recovery on authenticated domain (ask_user branch)"))
                                    re_data = re_result[0]
                                    if isinstance(re_data, dict):
                                        new_obs = _obs_from_payload(re_data.get("observation") or re_data)
                                        if new_obs:
                                            current_obs = new_obs
                                        last_dom_login_flag = bool(_login_detected(re_data))
                                        if not last_dom_login_flag and not _is_login_like_url(current_obs.url):
                                            yield {"type": "intervention_cleared", "content": {
                                                "category": "login",
                                                "url": current_obs.url,
                                                "domain": ask_domain,
                                                "reason": "authenticated_domain_recovery_succeeded",
                                            }}, {}
                                except Exception:
                                    pass
                            continue
                        # Budget exhausted — real session expiry. Downgrade
                        # the domain and surface a real login intervention.
                        authenticated_domains.discard(ask_scope)
                        login_recovery_failures.pop(ask_scope, None)
                        yield {"type": "activity", "content": {
                            "kind": "analyze",
                            "message": (
                                f"{ask_domain} 恢复重试已用尽，判定为真实登录过期，走正常重新登录"
                                if lang == "zh"
                                else f"Recovery budget for {ask_domain} exhausted; treating as real session expiry"
                            ),
                        }}, {}
                        async for event in suspend_for_authentication(
                            category="login",
                            source="ask_user_recovery_exhausted",
                            next_step=step + 1,
                            question=q,
                        ):
                            yield event
                        return
                    # Authenticated + URL-only match, no DOM login form:
                    # fall through to normal ask_user suspend below.
                async for event in suspend_for_human_assistance(
                    question=q,
                    next_step=step + 1,
                    assistance=automatic_assistance,
                    category=ask_category,
                    handoff=ask_handoff,
                ):
                    yield event
                return

            if decision.tool == "browser_fail":
                reason = str(decision.args.get("reason") or "")
                recovery = terminal_recovery_plan(
                    source=MODEL_FAILURE,
                    error=reason,
                )
                if recovery_assistance_available(recovery):
                    async for event in suspend_for_recovery(
                        recovery,
                        next_step=step + 1,
                    ):
                        yield event
                    return
                yield {"type": "activity", "content": {
                    "kind": "error",
                    "message": (
                        f"⚠️ 无法继续：{reason}" if lang == "zh"
                        else f"⚠️ Cannot continue: {reason}"
                    ),
                }}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": subagent_id, "node_id": node.node_id, "status": "failed_terminal",
                }}, {"browser_receipt": browser_failure_receipt(error=reason)}
                return

            # Hard-cap repetitive read-only tools on the same URL. The
            # planner LLM tends to loop on read_text/screenshot/observe
            # without making progress — detect the pattern and force it
            # to either call browser_done or navigate elsewhere.
            if (
                decision.tool in READ_ONLY_TOOLS
                and current_obs.url
                and not is_fill_reconciliation(decision)
            ):
                same_count = read_count_for_current_state(history, current_obs)
                if same_count >= BROWSER_MAX_READS_PER_STATE:
                    yield {"type": "activity", "content": {
                        "kind": "error",
                        "message": (
                            f"已对 {current_obs.url} 做过 {same_count} 次读取。立即调 browser_done"
                            f"（把已有数据交棒），或 navigate 到其他页面。"
                            if lang == "zh"
                            else f"Already read {current_obs.url} {same_count} times. "
                                 f"Call browser_done now or navigate elsewhere."
                        ),
                    }}, {}
                    # Synthesize a failure so the loop feeds back negative
                    # signal to the planner instead of executing yet another read.
                    history.append(StepRecord(
                        observation=current_obs, decision=decision, ok=False,
                        error=f"read-budget exhausted on {current_obs.url}",
                        result_digest="",
                    ))
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        assistance = browser_human_assistance(
                            source=READ_BUDGET,
                            observation=current_obs,
                            lang=lang,
                        )
                        if automatic_assistance_available(assistance):
                            async for event in suspend_for_human_assistance(
                                question=assistance.question,
                                next_step=step + 1,
                                assistance=assistance,
                            ):
                                yield event
                            return
                        yield {"type": "activity", "content": {
                            "kind": "error",
                            "message": (
                                "读取循环无法自拔，且本页面的人工协助机会已使用"
                                if lang == "zh" else
                                "The read loop remained stuck after human assistance"
                            ),
                        }}, {}
                        yield {"type": "subagent_done", "content": {
                            "subagent_id": subagent_id,
                            "node_id": node.node_id,
                            "status": "failed_terminal",
                        }}, {"browser_receipt": browser_failure_receipt(error="read loop")}
                        return
                    continue

            exploration_stagnation = assess_exploration_stagnation(
                decision,
                history,
                current_obs,
            )
            if exploration_stagnation.blocked:
                hint = (
                    "连续滚动或纯等待后页面与滚动位置都没有变化；请更换目标、方向或操作策略。"
                    if lang == "zh" else
                    "Repeated scroll/delay produced no page or viewport progress; choose a different target, direction, or strategy."
                )
                history.append(StepRecord(
                    observation=current_obs,
                    decision=decision,
                    ok=False,
                    error=exploration_stagnation.reason,
                    result_digest="",
                ))
                yield {"type": "activity", "content": {
                    "kind": "warning",
                    "message": hint,
                }}, {}
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    assistance = browser_human_assistance(
                        source=EXPLORATION_STAGNATION,
                        observation=current_obs,
                        decision=decision,
                        lang=lang,
                    )
                    if automatic_assistance_available(assistance):
                        async for event in suspend_for_human_assistance(
                            question=assistance.question,
                            next_step=step + 1,
                            assistance=assistance,
                        ):
                            yield event
                        return
                    break
                continue

            # Real browser tool → dispatch via LocalBridge
            if not is_browser_tool(decision.tool) and not is_control_tool(decision.tool):
                yield {"type": "activity", "content": {
                    "kind": "error",
                    "message": (f"未识别工具：{decision.tool}" if lang == "zh"
                                else f"Unknown tool: {decision.tool}"),
                }}, {}
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    break
                continue

            # Same-URL navigation is pure step waste. Reject it before
            # dispatch so planner jitter / duplicated first-step
            # shortcut doesn't burn the step budget.
            if decision.tool == "browser_navigate" and isinstance(decision.args, dict):
                nav_url = str(decision.args.get("url") or "").strip()
                cur_url = str(getattr(current_obs, "url", "") or "").strip()
                if nav_url and cur_url and nav_url == cur_url:
                    hint = (
                        f"已在当前页面 {cur_url}，不要重复 browser_navigate 到同一 URL。"
                        if lang == "zh" else
                        f"Already on {cur_url}; do not browser_navigate to the same URL again."
                    )
                    history.append(StepRecord(
                        observation=current_obs, decision=decision, ok=False,
                        error=hint, result_digest="",
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": hint,
                    }}, {}
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        break
                    continue

            # Pre-dispatch gate: reject repeated browser_wait_for on a
            # text query we've already missed MAX times. Otherwise the
            # LLM burns MAX_STEPS × 10s on the same impossible lookup.
            if (
                decision.tool == "browser_wait_for"
                and isinstance(decision.args, dict)
            ):
                _wait_text = str(decision.args.get("text") or "").strip()
                # count INVOCATIONS of wait_for-text, not just
                # failures. The primary fix is in the agent (wait_for now
                # returns matched_ref). This counter catches the residual
                # anti-pattern where LLM still re-waits after already
                # getting ok+ref back — strongly directs it to click instead.
                _per_text_calls = wait_for_text_calls.get(_wait_text, 0) if _wait_text else 0
                _total_calls = sum(wait_for_text_calls.values())
                _per_text_tripped = bool(_wait_text and _per_text_calls >= WAIT_FOR_TEXT_MAX_CALLS)
                _cross_text_tripped = _total_calls >= WAIT_FOR_TEXT_MAX_CALLS * 2
                # P1-hard · When we already have a cached ref for this text,
                # rewrite the decision into browser_click(ref=…) so the LLM's
                # intent ("confirm that thing exists → proceed") is fulfilled
                # in a single step, instead of endlessly re-waiting. The LLM
                # usually can't remember prior returned refs across turns,
                # so we remember for it. Generic — works for any site that
                # returns ref from wait_for. Never triggers on the FIRST
                # wait_for; only kicks in on the 2nd attempt of the same text.
                _cached_target = wait_for_click_targets.get(_wait_text) if _wait_text else None
                _cached_ref = _cached_target.ref if _cached_target else None
                if (
                    _cached_target
                    and _per_text_calls >= 1
                    and can_reuse_click_target(_cached_target, current_obs)
                ):
                    rewrite_note = (
                        f"browser_wait_for text={_wait_text!r} 第 {_per_text_calls + 1} 次调用，"
                        f"系统已自动重写为 browser_click(ref={_cached_ref})"
                        if lang == "zh"
                        else f"browser_wait_for text={_wait_text!r} (call #{_per_text_calls + 1})"
                             f" auto-rewritten to browser_click(ref={_cached_ref})"
                    )
                    decision = Decision(
                        tool="browser_click",
                        args={"ref": _cached_ref},
                        rationale=rewrite_note,
                    )
                    yield {"type": "activity", "content": {
                        "kind": "analyze", "message": rewrite_note[:160],
                    }}, {}
                    logger.info("wait_for rewritten to click", extra={"event": "browser.wait_for_rewrite_to_click", "text": _wait_text, "ref": _cached_ref})
                    # Fall through to normal dispatch with the rewritten decision.
                elif _per_text_tripped or _cross_text_tripped:
                    hint = (
                        f"⚠ `browser_wait_for text=\"{_wait_text}\"` 已调用 "
                        f"{_per_text_calls} 次 —— 该 API 在 ok=True 时已返回匹配元素的"
                        " `matched_ref` 和 `clickable_ref`，直接用那个 ref 做 browser_click/"
                        "fill 即可，不要再 wait_for 相同文字。若历次返回里没见到 ref，"
                        "说明该文字不在可点击元素上，换 browser_observe 扫 elements 或"
                        " browser_read_text 找 <a href=...>。"
                        if lang == "zh"
                        else
                        f"⚠ `browser_wait_for text=\"{_wait_text}\"` invoked "
                        f"{_per_text_calls} times. Successful wait_for returns `matched_ref`"
                        " and `clickable_ref` — use that ref directly with browser_click/fill."
                        " If no ref was returned, the text isn't on a clickable element;"
                        " switch to browser_observe or browser_read_text."
                    )
                    history.append(StepRecord(
                        observation=current_obs, decision=decision, ok=False,
                        error=hint, result_digest="",
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": (
                            f"browser_wait_for 被拦截：text={_wait_text!r} 已调用 "
                            f"{_per_text_calls} 次，应使用返回的 ref 做下一步"
                            if lang == "zh"
                            else f"browser_wait_for blocked: text={_wait_text!r} invoked "
                                 f"{_per_text_calls}x, use the returned ref instead"
                        ),
                    }}, {}
                    logger.warning("wait_for text blocked", extra={"event": "browser.wait_for_text_blocked", "text": _wait_text, "calls": _per_text_calls})
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        break
                    continue
                # Count this invocation upfront (not only on failure).
                if _wait_text:
                    wait_for_text_calls[_wait_text] = _per_text_calls + 1

            # Bind visual coordinates to the latest DOM ref before any state
            # or form validation. The rewritten semantic action must pass the
            # same mission guards as a planner-produced ref action.
            coordinate_binding = bind_coordinate_action(decision, current_obs)
            if coordinate_binding.blocked:
                history.append(StepRecord(
                    observation=current_obs,
                    decision=decision,
                    ok=False,
                    error=coordinate_binding.reason,
                    result_digest="",
                ))
                yield {"type": "activity", "content": {
                    "kind": "warning", "message": coordinate_binding.reason,
                }}, {}
                pending_resolved_decision = Decision(
                    tool="browser_observe",
                    args={},
                    rationale="coordinate input must be rebound against the latest editable DOM target",
                )
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    break
                continue
            if coordinate_binding.decision != decision:
                logger.info(
                    "browser coordinate action rebound to live DOM target",
                    extra={
                        "event": "browser.coordinate_action_rebound",
                        "from_tool": decision.tool,
                        "to_tool": coordinate_binding.decision.tool,
                        "target_ref": str((coordinate_binding.decision.args or {}).get("ref") or ""),
                    },
                )
                decision = coordinate_binding.decision

            # Pre-flight action validation. The planner has the state
            # ledger in its prompt; this layer enforces the same rules
            # even when the LLM disregards them.
            if context_tracks_state:
                try:
                    verdict, new_decision, v_hint = task_context.validate_action(decision, current_obs)
                except Exception:
                    verdict, new_decision, v_hint = ("allow", decision, "")
                if verdict == "rewrite" and new_decision is not None:
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": v_hint,
                    }}, {}
                    decision = new_decision
                elif verdict == "reject":
                    history.append(StepRecord(
                        observation=current_obs, decision=decision, ok=False,
                        error=v_hint, result_digest="",
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": v_hint,
                    }}, {}
                    logger.info("browser context action rejected", extra={"event": "browser.context_action_rejected", "tool": decision.tool, "hint": v_hint[:120]})
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        break
                    continue

            # A hidden browser has no renderer-side focus guarantee. Bind key
            # actions to the current form field before scope/dependency checks
            # and let the local agent restore focus immediately before input.
            decision = form_transaction.bind_interaction_target(
                decision,
                current_obs,
            )
            prepared_decision = prepare_driver_dispatch(
                planner,
                decision,
                current_obs,
            )
            if prepared_decision != decision:
                logger.info(
                    "browser decision changed by final driver dispatch guard",
                    extra={
                        "event": "browser.driver_dispatch_guard",
                        "driver": planner.kind,
                        "from_tool": decision.tool,
                        "to_tool": prepared_decision.tool,
                        "from_ref": str((decision.args or {}).get("ref") or ""),
                        "to_ref": str((prepared_decision.args or {}).get("ref") or ""),
                    },
                )
                decision = prepared_decision
            recovery_blocker = interaction_target_recovery.blocker(decision, current_obs)
            if recovery_blocker is not None:
                history.append(StepRecord(
                    observation=current_obs,
                    decision=decision,
                    ok=False,
                    error=recovery_blocker,
                    result_digest="",
                ))
                yield {"type": "activity", "content": {
                    "kind": "warning", "message": recovery_blocker,
                }}, {}
                pending_resolved_decision = Decision(
                    tool="browser_observe",
                    args={},
                    rationale="quarantined target requires a fresh strategy from current DOM",
                )
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    assistance = browser_human_assistance(
                        source=NAVIGATION_TARGET_BLOCKED,
                        observation=current_obs,
                        decision=decision,
                        lang=lang,
                    )
                    if automatic_assistance_available(assistance):
                        async for event in suspend_for_human_assistance(
                            question=assistance.question,
                            next_step=step + 1,
                            assistance=assistance,
                        ):
                            yield event
                        return
                    break
                continue
            click_blocker = click_outcome_policy.blocker(decision, current_obs)
            if click_blocker is not None:
                history.append(StepRecord(
                    observation=current_obs,
                    decision=decision,
                    ok=False,
                    error=click_blocker,
                    result_digest="",
                ))
                yield {"type": "activity", "content": {
                    "kind": "warning", "message": click_blocker,
                }}, {}
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    assistance = browser_human_assistance(
                        source=NAVIGATION_TARGET_BLOCKED,
                        observation=current_obs,
                        decision=decision,
                        lang=lang,
                    )
                    if automatic_assistance_available(assistance):
                        async for event in suspend_for_human_assistance(
                            question=assistance.question,
                            next_step=step + 1,
                            assistance=assistance,
                        ):
                            yield event
                        return
                    break
                continue

            scope_blocker = form_transaction.interaction_scope_blocker(
                decision,
                current_obs,
            )
            if scope_blocker is not None:
                scope_hint = (
                    "已阻止跨表单操作：当前正在编辑的表单尚未完成。"
                    "请继续操作当前表单内的字段或按钮；表单提交、关闭或页面切换后会自动解除限制。"
                    if lang == "zh" else
                    "Cross-form interaction blocked while the current form is still active. "
                    "Continue inside that form; the lock is released after submit, close, or navigation."
                )
                history.append(StepRecord(
                    observation=current_obs,
                    decision=decision,
                    ok=False,
                    error=scope_hint,
                    result_digest=json.dumps({
                        "active_scope": scope_blocker.active_scope,
                        "target_scope": scope_blocker.target_scope,
                    }, ensure_ascii=False),
                ))
                yield {"type": "activity", "content": {
                    "kind": "warning", "message": scope_hint,
                }}, {}
                logger.warning(
                    "browser cross-form interaction blocked",
                    extra={
                        "event": "browser.form_scope_blocked",
                        "tool": decision.tool,
                        "ref": str((decision.args or {}).get("ref") or ""),
                        "active_scope": scope_blocker.active_scope,
                        "target_scope": scope_blocker.target_scope,
                    },
                )
                try:
                    notify_driver_rejection(
                        planner,
                        decision,
                        current_obs,
                        category=(
                            "scope_target_unresolved"
                            if scope_blocker.target_scope == "unresolved"
                            else "cross_form_target"
                        ),
                        reason=scope_blocker.reason,
                    )
                except Exception as exc:
                    logger.warning(
                        "browser driver rejection hook failed",
                        extra={
                            "event": "browser.driver_rejection_hook_failed",
                            "category": "form_scope",
                            "error": str(exc),
                        },
                    )
                pending_resolved_decision = Decision(
                    tool="browser_observe",
                    args={},
                    rationale=(
                        "form target was rejected before dispatch; refresh the "
                        "DOM and resolve the field inside the active scope"
                    ),
                )
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    break
                continue

            dependency_target = form_transaction.resolve_interaction_target(
                decision,
                current_obs,
            )
            dependency_blocker = form_transaction.dependent_action_blocker(
                current_obs,
                tool=decision.tool,
                target=dependency_target,
                key=str((decision.args or {}).get("key") or ""),
            )
            if dependency_blocker is not None:
                blocked_fields = "、".join(dependency_blocker.fields)
                dependency_hint = (
                    f"已阻止继续操作：字段“{blocked_fields}”尚未确认写入。"
                    "必须先重新填写并确认该字段，再点击按钮或按回车。"
                    if lang == "zh" else
                    f"Dependent action blocked: fields {', '.join(dependency_blocker.fields)} "
                    "are not confirmed. Refill and verify them before clicking a button or pressing Enter."
                )
                history.append(StepRecord(
                    observation=current_obs,
                    decision=decision,
                    ok=False,
                    error=dependency_hint,
                    result_digest="",
                ))
                yield {"type": "activity", "content": {
                    "kind": "warning", "message": dependency_hint,
                }}, {}
                logger.warning(
                    "browser dependent action blocked by unverified fill",
                    extra={
                        "event": "browser.dependent_action_blocked_unverified_fill",
                        "tool": decision.tool,
                        "fields": list(dependency_blocker.fields),
                    },
                )
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    break
                continue

            prepared_effect: PreparedEffect | None = None
            submit_press = bool(
                decision.tool == "browser_press"
                and str((decision.args or {}).get("key") or "").strip().lower() in {"enter", "return"}
                and form_transaction.has_confirmed_fill()
            )
            if (
                (
                    decision.tool in {"browser_click", "browser_click_at"}
                    or submit_press
                )
                and isinstance(decision.args, dict)
            ):
                effect_target = (
                    resolve_effect_target(decision, current_obs)
                    if decision.tool in {"browser_click", "browser_click_at"}
                    else dependency_target
                )
                if effect_target is not None:
                    try:
                        prepared_effect = (
                            await effect_tracker.prepare_click(
                                target=effect_target,
                                before=current_obs,
                            )
                            if not submit_press else
                            effect_tracker.prepare_submit_press(
                                key=str((decision.args or {}).get("key") or ""),
                                target=effect_target,
                                before=current_obs,
                            )
                        )
                    except SemanticActionRejected as exc:
                        alignment = exc.alignment
                        semantic_hint = (
                            "已阻止与任务业务对象不一致的点击："
                            f"目标需要“{alignment.intended.entity or alignment.intended.operation}”，"
                            f"当前元素表示“{alignment.observed.entity or alignment.observed.operation}”。"
                            "请重新观察并选择与目标一致的元素。"
                            if lang == "zh" else
                            "Blocked a click whose business object conflicts with the task: "
                            f"expected {alignment.intended.entity or alignment.intended.operation!r}, "
                            f"target represents {alignment.observed.entity or alignment.observed.operation!r}. "
                            "Observe again and select a semantically compatible element."
                        )
                        history.append(StepRecord(
                            observation=current_obs,
                            decision=decision,
                            ok=False,
                            error=semantic_hint,
                            result_digest=json.dumps(
                                alignment.model_dump(mode="json"),
                                ensure_ascii=False,
                            )[:4000],
                        ))
                        yield {"type": "activity", "content": {
                            "kind": "warning", "message": semantic_hint,
                        }}, {}
                        logger.warning(
                            "browser semantic action rejected",
                            extra={
                                "event": "browser.semantic_action_rejected",
                                "intended_entity": alignment.intended.entity,
                                "observed_entity": alignment.observed.entity,
                                "confidence": alignment.confidence,
                            },
                        )
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            break
                        continue
                    if prepared_effect is not None:
                        enriched_contract = form_transaction.enrich_contract(
                            prepared_effect.contract,
                            target=effect_target,
                            purpose_override=(
                                task_context.interaction_purpose(decision, current_obs)
                                if context_tracks_state else ""
                            ),
                        )
                        precondition = enforce_commit_preconditions(
                            enriched_contract,
                            requires_form_input=requires_authoritative_form_input,
                            has_confirmed_form_input=bool(
                                dict(enriched_contract.fingerprint or {}).get(
                                    "confirmed_fill_count",
                                )
                            ) or form_transaction.has_confirmed_value(
                                authoritative_form_values,
                            ),
                        )
                        if precondition.downgraded:
                            logger.info(
                                "browser commit downgraded to entry transition",
                                extra={
                                    "event": "browser.commit_precondition_downgraded",
                                    "action": enriched_contract.action_name,
                                    "reason": precondition.reason,
                                    "intended_operation": (
                                        enriched_contract.intended_operation
                                    ),
                                },
                            )
                        contract = precondition.contract
                        if contract.is_commit:
                            contract = business_actions.bind_contract(
                                contract,
                                current_obs,
                                target_hint=task_context.business_target_hint(current_obs),
                            )
                        prepared_effect = effect_tracker.update_contract(
                            prepared_effect,
                            contract,
                        )
                        if prepared_effect is None:
                            logger.info(
                                "browser click excluded from business effect tracking",
                                extra={
                                    "event": "browser.effect_tracking_cancelled",
                                    "reason": "confirmed non-business interaction purpose",
                                },
                            )
                        context_effect_blocker = (
                            task_context.business_effect_blocker(prepared_effect.contract)
                            if prepared_effect is not None and context_tracks_state
                            else ""
                        )
                        if context_effect_blocker:
                            history.append(StepRecord(
                                observation=current_obs,
                                decision=decision,
                                ok=False,
                                error=context_effect_blocker,
                                result_digest=str(
                                    prepared_effect.contract.business_action_id or ""
                                ),
                            ))
                            yield {"type": "activity", "content": {
                                "kind": "warning",
                                "message": context_effect_blocker,
                            }}, {}
                            pending_resolved_decision = Decision(
                                tool="browser_observe",
                                args={},
                                rationale="verify the already confirmed business effect before any new commit",
                            )
                            logger.info(
                                "browser context blocked additional business effect",
                                extra={
                                    "event": "browser.context_business_effect_blocked",
                                    "contract_key": prepared_effect.contract.key(),
                                },
                            )
                            continue
                        commit_blocker = (
                            form_transaction.commit_blocker(
                                current_obs,
                                target=effect_target,
                            )
                            if prepared_effect is not None else None
                        )
                        if prepared_effect is not None and commit_blocker is not None:
                            blocked_fields = "、".join(commit_blocker.fields)
                            commit_hint = (
                                f"已阻止提交：字段“{blocked_fields}”的填写结果尚未确认。"
                                "请重新观察并确认字段值，必要时重新填写，再执行提交。"
                                if lang == "zh" else
                                f"Commit blocked: fill results for {', '.join(commit_blocker.fields)} "
                                "are not confirmed. Observe and verify or refill before committing."
                            )
                            history.append(StepRecord(
                                observation=current_obs,
                                decision=decision,
                                ok=False,
                                error=commit_hint,
                                result_digest=json.dumps(
                                    form_transaction.summaries(),
                                    ensure_ascii=False,
                                )[:4000],
                            ))
                            yield {"type": "activity", "content": {
                                "kind": "warning",
                                "message": commit_hint,
                            }}, {}
                            logger.warning(
                                "browser commit blocked by unverified fill",
                                extra={
                                    "event": "browser.commit_blocked_unverified_fill",
                                    "fields": list(commit_blocker.fields),
                                },
                            )
                            consecutive_failures += 1
                            continue
                        replay_blocker = (
                            effect_tracker.replay_blocker(prepared_effect)
                            if prepared_effect is not None else None
                        )
                        business_replay = (
                            business_actions.replay_blocker(prepared_effect.contract)
                            if prepared_effect is not None else None
                        )
                        if replay_blocker is None and business_replay is not None:
                            replay_hint = (
                                "同一业务对象上的相同操作已经执行或正在验收，"
                                "已阻止因页面重渲染产生的重复提交；请只验证结果。"
                                if lang == "zh" else
                                "The same operation on this business object is already executed or pending verification; "
                                "the re-rendered control will not be submitted again."
                            )
                            history.append(StepRecord(
                                observation=current_obs,
                                decision=decision,
                                ok=False,
                                error=replay_hint,
                                result_digest=business_replay.identity.business_action_id,
                            ))
                            yield {"type": "activity", "content": {
                                "kind": "warning", "message": replay_hint,
                            }}, {}
                            pending_resolved_decision = Decision(
                                tool="browser_observe",
                                args={},
                                rationale="verify the pending business action instead of replaying it",
                            )
                            consecutive_failures += 1
                            continue
                        if replay_blocker is not None:
                            replay_hint = (
                                f"操作“{replay_blocker.action_name}”已有状态 {replay_blocker.status}，"
                                "已阻止重复提交；请只验证结果，不要再次执行该操作。"
                                if lang == "zh" else
                                f"Action {replay_blocker.action_name!r} already has status "
                                f"{replay_blocker.status}; replay blocked. Verify the result instead."
                            )
                            history.append(StepRecord(
                                observation=current_obs,
                                decision=decision,
                                ok=False,
                                error=replay_hint,
                                result_digest=json.dumps(
                                    replay_blocker.model_dump(mode="json"),
                                    ensure_ascii=False,
                                )[:4000],
                            ))
                            yield {"type": "activity", "content": {
                                "kind": "warning", "message": replay_hint,
                            }}, {}
                            logger.warning(
                                "browser side effect replay blocked",
                                extra={
                                    "event": "browser.effect_replay_blocked",
                                    "contract_key": replay_blocker.contract_key,
                                    "status": replay_blocker.status,
                                },
                            )
                            consecutive_failures += 1
                            continue
                        history_preflight = (
                            await action_history.preflight(
                                contract=prepared_effect.contract,
                                observation=current_obs,
                            )
                            if prepared_effect is not None else None
                        )
                        if history_preflight is not None and history_preflight.blocked:
                            history_hint = (
                                f"{history_preflight.reason} 请离开当前业务对象并选择其他未处理目标。"
                                if lang == "zh" else
                                f"{history_preflight.reason} Leave this object and choose another unprocessed target."
                            )
                            history.append(StepRecord(
                                observation=current_obs,
                                decision=Decision(
                                    tool="__business_replay_skipped__",
                                    args={
                                        "business_key": history_preflight.intent.business_key,
                                        "target": history_preflight.intent.target_id,
                                    },
                                    rationale="cross-run business replay guard",
                                ),
                                ok=True,
                                error=None,
                                result_digest=history_hint,
                            ))
                            yield {"type": "activity", "content": {
                                "kind": "analyze",
                                "message": history_hint,
                            }}, {}
                            logger.info(
                                "browser cross-run action replay skipped",
                                extra={
                                    "event": "browser.action_history_blocked",
                                    "business_key": history_preflight.intent.business_key,
                                    "operation": history_preflight.intent.operation_id,
                                    "target": history_preflight.intent.target_id,
                                },
                            )
                            consecutive_failures = 0
                            continue

            if decision.tool == "browser_fill":
                fill_preflight = validate_fill_target(
                    current_obs,
                    dict(decision.args or {}),
                )
                if not fill_preflight.ok:
                    stale_fill_hint = (
                        "填写目标已不属于当前页面中的可编辑字段，已停止使用旧元素编号；"
                        "正在重新读取页面并定位输入框。"
                        if lang == "zh" else
                        "The fill target is not an editable field in the latest page state. "
                        "The stale element ref was rejected; observing again before resolving the field."
                    )
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=decision,
                        ok=False,
                        error=stale_fill_hint,
                        result_digest=fill_preflight.reason,
                    ))
                    pending_resolved_decision = Decision(
                        tool="browser_observe",
                        args={},
                        rationale="fill target preflight failed; refresh DOM before resolving the field again",
                    )
                    yield {"type": "activity", "content": {
                        "kind": "warning", "message": stale_fill_hint,
                    }}, {}
                    logger.warning(
                        "browser fill target rejected before dispatch",
                        extra={
                            "event": "browser.fill_target_preflight_rejected",
                            "ref": fill_preflight.ref,
                            "reason": fill_preflight.reason,
                        },
                    )
                    try:
                        notify_driver_rejection(
                            planner,
                            decision,
                            current_obs,
                            category="stale_fill_target",
                            reason=fill_preflight.reason,
                        )
                    except Exception as exc:
                        logger.warning(
                            "browser driver rejection hook failed",
                            extra={
                                "event": "browser.driver_rejection_hook_failed",
                                "category": "stale_fill_target",
                                "error": str(exc),
                            },
                        )
                    continue

            superseded_receipts = effect_tracker.supersede_pending_for_action(
                decision,
                preserve_contract_key=(
                    prepared_effect.contract.key()
                    if prepared_effect is not None else ""
                ),
            )
            for superseded_receipt in superseded_receipts:
                business_actions.record(superseded_receipt)
            if superseded_receipts:
                logger.info(
                    "browser pending verification window superseded",
                    extra={
                        "event": "browser.pending_effect_superseded",
                        "tool": decision.tool,
                        "contracts": [
                            item.contract_key for item in superseded_receipts
                        ],
                    },
                )

            dispatch_before_obs = current_obs
            click_outcome = ClickOutcome(ok=True)
            # Lifecycle starts immediately before the real sidecar dispatch.
            # Post-action observation and stabilization remain part of this
            # same operation, so the row stays active until they finish.
            yield {"type": "tool_requested", "content": {
                "tool": decision.tool, "args": decision.args,
                "rationale": decision.rationale,
                "rationale_source": decision.rationale_source,
            }}, {}
            try:
                result, ok, err = await execution_budget.wait_for(
                    self._dispatch(decision)
                )
            except BrowserExecutionBudgetExpired:
                execution_budget_exhausted = True
                execution_budget_effect_unknown = interrupted_effect_requires_handoff(
                    capability_id=action_capability_id,
                    tool=decision.tool,
                    final_commit_control=bool(
                        prepared_effect is not None
                        and prepared_effect.contract.is_commit
                    ),
                )
                break
            if ok and observation_retry_required(result):
                yield {"type": "activity", "content": {
                    "kind": "analyze",
                    "message": (
                        "点击已执行，正在单独刷新页面状态" if lang == "zh"
                        else "The click was dispatched; refreshing page state separately"
                    ),
                }}, {}
                probe_result, probe_ok, probe_err = await self._dispatch(
                    Decision(
                        tool="browser_observe",
                        args={},
                        rationale="post-action observation retry without replaying mutation",
                    )
                )
                if probe_ok and isinstance(result, dict):
                    result = reconcile_post_action_observation(result, probe_result)
                    logger.info(
                        "post-action observation recovered",
                        extra={"event": "browser.post_action_observation_recovered", "tool": decision.tool},
                    )
                else:
                    pending_resolved_decision = Decision(
                        tool="browser_observe",
                        args={},
                        rationale="action dispatched; observation still pending and must be refreshed before another mutation",
                    )
                    logger.warning(
                        "post-action observation remains pending",
                        extra={
                            "event": "browser.post_action_observation_pending",
                            "tool": decision.tool,
                            "error": str(probe_err or "observation retry failed"),
                        },
                    )
            if ok:
                result = await stabilize_transition_observation(
                    decision=decision,
                    before=dispatch_before_obs,
                    result=result,
                    dispatch=self._dispatch,
                )
            if ok:
                click_outcome = click_outcome_policy.evaluate(
                    decision,
                    result,
                    dispatch_before_obs,
                )
                if not click_outcome.ok:
                    ok = False
                    err = click_outcome.error
            if decision.tool == "browser_click":
                if ok:
                    interaction_target_recovery.record_success(decision, dispatch_before_obs)
                else:
                    interaction_target_recovery.record_failure(decision, dispatch_before_obs, err)
            yield {"type": "tool_completed", "content": {
                "tool": decision.tool, "ok": ok, "result": result,
                **({"error": err} if not ok and err else {}),
            }}, {}

            # A successful text lookup is only useful if its resolved target
            # is acted on before SPA re-rendering invalidates the ref. Local
            # high-confidence rules click directly; ambiguous/unknown matches
            # go through a constrained candidate-only picker. The follow-up is
            # queued here and consumed before the general planner gets another
            # turn. The normal pre-dispatch gates still apply to the click.
            if should_resolve_wait_action(decision, ok=ok, result=result):
                _wait_observation = _update_obs(current_obs, decision.tool, result)
                _resolved_action = await resolve_wait_for_action(
                    goal=goal,
                    query=str(decision.args.get("text") or ""),
                    result=result,
                    observation=_wait_observation,
                    domain=str(decision.args.get("domain") or _domain(_wait_observation.url) or ""),
                    lang=lang,
                )
                if _resolved_action.decision is not None:
                    _source_text = (
                        "本地规则已确认目标，下一步直接执行点击"
                        if _resolved_action.source == "local_rule" and lang == "zh"
                        else "候选已确认，下一步执行受约束点击"
                        if lang == "zh"
                        else "Local rule resolved target; click queued"
                        if _resolved_action.source == "local_rule"
                        else "Candidate selected; constrained click queued"
                    )
                    yield {"type": "activity", "content": {
                        "kind": "analyze", "message": _source_text,
                    }}, {}
                    pending_resolved_decision = _resolved_action.decision

            # Post-dispatch bookkeeping for wait_for: cache any returned
            # ref keyed by the queried text (for P1-hard rewrite on the
            # next call) + debug log. Invocation counter is already
            # maintained in the pre-gate block.
            if (
                decision.tool == "browser_wait_for"
                and isinstance(decision.args, dict)
            ):
                _wait_text_after = str(decision.args.get("text") or "").strip()
                if _wait_text_after and ok and isinstance(result, dict):
                    _target = confirmed_click_target(result)
                    if _target is not None:
                        wait_for_click_targets[_wait_text_after] = _target
                        wait_for_text_refs[_wait_text_after] = _target.ref
                    else:
                        wait_for_click_targets.pop(_wait_text_after, None)
                        wait_for_text_refs.pop(_wait_text_after, None)
                if _wait_text_after:
                    logger.debug(
                        "wait_for text call",
                        extra={"event": "browser.wait_for_text_call", "text": _wait_text_after, "ok": bool(ok), "count": wait_for_text_calls.get(_wait_text_after, 0), "max": WAIT_FOR_TEXT_MAX_CALLS, "cached_ref": wait_for_text_refs.get(_wait_text_after, "")},
                    )

            current_obs = _update_obs(current_obs, decision.tool, result)
            if (
                decision.tool in {"browser_upload_file", "browser_paste_image"}
                and not ok
                and is_media_delivery_handoff_error(tool=decision.tool, error=err)
            ):
                driver_state = planner.export_checkpoint_state()
                handoff = build_media_upload_handoff(
                    context=input_context,
                    completed_candidate_ids=completed_media_candidate_ids(driver_state),
                    user_id=self.user_id,
                )
                if handoff:
                    pending_resolved_decision = media_upload_assistance_decision(
                        handoff,
                        lang=lang,
                    )
            form_transaction.after_action(
                decision,
                before=dispatch_before_obs,
                after=current_obs,
                ok=ok,
            )
            if decision.tool in {"browser_click", "browser_click_at"} and not ok and is_stale_interaction_target_error(err):
                pending_resolved_decision = Decision(
                    tool="browser_observe",
                    args={},
                    rationale="click target changed during dispatch; refresh DOM before resolving another target",
                )
                yield {"type": "activity", "content": {
                    "kind": "warning",
                    "message": (
                        "点击目标已发生变化，正在重新读取当前页面，不再使用旧元素编号"
                        if lang == "zh" else
                        "The click target changed; refreshing the page instead of reusing the stale ref"
                    ),
                }}, {}
            elif decision.tool == "browser_fill" and not ok and is_stale_fill_target_error(err):
                # The DOM changed after the backend preflight but before the
                # sidecar mutation. This is a stale target, not a failed
                # business-field write, so do not poison the form transaction.
                pending_resolved_decision = Decision(
                    tool="browser_observe",
                    args={},
                    rationale="fill target changed during dispatch; refresh DOM and resolve it again",
                )
                yield {"type": "activity", "content": {
                    "kind": "warning",
                    "message": (
                        "输入框在填写前发生变化，已重新读取页面，避免继续使用旧元素编号"
                        if lang == "zh" else
                        "The input changed before fill; observing again instead of reusing the stale ref"
                    ),
                }}, {}
            elif decision.tool == "browser_fill":
                current_obs = apply_confirmed_fill(
                    current_obs,
                    args=dict(decision.args or {}),
                    result=result,
                    ok=ok,
                )
                fill_receipt = form_transaction.record_fill(
                    args=dict(decision.args or {}),
                    result=result,
                    ok=ok,
                    error=err,
                    before=dispatch_before_obs,
                    after=current_obs,
                )
                if fill_receipt.status != "confirmed":
                    fill_hint = (
                        f"字段“{fill_receipt.label}”填写后尚未确认，提交前将重新核验"
                        if lang == "zh" else
                        f"Fill for {fill_receipt.label!r} is unverified and must be checked before commit"
                    )
                    yield {"type": "activity", "content": {
                        "kind": "warning", "message": fill_hint,
                    }}, {}
                retry_decision = fill_retry_policy.after_result(
                    decision,
                    ok=ok,
                    error=err,
                    before=dispatch_before_obs,
                )
                if retry_decision is not None:
                    pending_resolved_decision = retry_decision
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": (
                            "填写结果未返回，正在先读取字段当前值，避免重复输入"
                            if lang == "zh" else
                            "Fill was not confirmed; observing the current value before any retry"
                        ),
                    }}, {}
                elif not ok and fill_retry_policy.assistance_required(
                    decision,
                    error=err,
                    before=dispatch_before_obs,
                ):
                    pending_resolved_decision = build_fill_assistance_decision(
                        decision=decision,
                        before=dispatch_before_obs,
                        error=str(err or ""),
                        lang=lang,
                    )
            elif decision.tool == "browser_observe" and ok:
                reconciled_retry = fill_retry_policy.after_observation(current_obs)
                if reconciled_retry is not None:
                    pending_resolved_decision = reconciled_retry
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": (
                            "最新页面确认字段仍未写入，将对同一字段进行有限重试"
                            if lang == "zh" else
                            "Fresh state confirms the field is still empty; retrying the same field"
                        ),
                    }}, {}
            history.append(StepRecord(
                observation=current_obs, decision=decision, ok=ok, error=err,
                result_digest=_digest(decision.tool, result),
                decision_observation=dispatch_before_obs,
            ))

            if (
                prepared_effect is not None
                and ok
                and not current_obs.fresh
            ):
                deferred_receipt = effect_tracker.defer_until_fresh_observation(
                    prepared=prepared_effect,
                    reason="post-action observation unavailable; verification deferred",
                )
                business_actions.record(deferred_receipt)
                pending_resolved_decision = Decision(
                    tool="browser_observe",
                    args={},
                    rationale="verify the dispatched business action from a fresh DOM snapshot",
                )
            elif effect_verification_eligible(
                prepared_effect=prepared_effect,
                action_ok=ok,
                click_outcome=click_outcome,
            ):
                effect_receipt = await effect_tracker.record(
                    prepared=prepared_effect,
                    after=current_obs,
                    supplemental_evidence=form_transaction.outcome_evidence(current_obs),
                )
                if effect_receipt is None:
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": (
                            "已进入可编辑状态，继续填写后再提交"
                            if lang == "zh" else
                            "An editable surface opened; fill it before submitting"
                        ),
                    }}, {}
                else:
                    business_actions.record(effect_receipt)
                    notify_effect_receipt(planner, effect_receipt)
                    await persist_confirmed_effect(effect_receipt, current_obs)
                    if effect_receipt.status == "confirmed_success":
                        deferred_success_receipt = effect_receipt
                    elif effect_receipt.status in {"pending", "unknown"}:
                        pending_resolved_decision = Decision(
                            tool="browser_observe",
                            args={},
                            rationale="recheck the dispatched business effect before planning another action",
                        )
                    form_transaction.after_effect(effect_receipt, current_obs)
                    receipt_application = apply_effect_receipt(
                        context=task_context,
                        tracks_context_state=context_tracks_state,
                        receipt=effect_receipt,
                        observation=current_obs,
                    )
                    if receipt_application.error:
                        logger.warning(
                            "browser context effect hook failed",
                            extra={
                                "event": "browser.context_effect_hook_failed",
                                "error": receipt_application.error,
                            },
                        )
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=Decision(
                            tool="__effect_verification__",
                            args={"contract_key": effect_receipt.contract_key},
                            rationale="system effect verification",
                        ),
                        ok=effect_receipt.status == "confirmed_success",
                        error=None if effect_receipt.status == "confirmed_success" else effect_receipt.reason,
                        result_digest=json.dumps(effect_receipt.model_dump(mode="json"), ensure_ascii=False)[:6000],
                    ))
                    effect_message = _effect_timeline_message(
                        effect_receipt.status,
                        effect_receipt.reason,
                        lang=lang,
                    )
                    yield {"type": "activity", "content": {
                        "kind": "complete" if effect_receipt.status == "confirmed_success" else "analyze",
                        "message": effect_message[:240],
                    }}, {}
                    yield {"type": "runtime_status", "content": {
                        "side_effect_guard": {
                            "status": effect_receipt.status,
                            "blocks_replay": effect_receipt.blocks_replay,
                            "contract_key": effect_receipt.contract_key,
                            "action_name": effect_receipt.action_name,
                            "receipt": effect_receipt.model_dump(mode="json"),
                        },
                    }}, {}
                    logger.info(
                        "browser effect verified",
                        extra={
                            "event": "browser.effect_verified",
                            "contract_key": effect_receipt.contract_key,
                            "status": effect_receipt.status,
                            "confidence": effect_receipt.confidence,
                            "action": effect_receipt.action_name,
                        },
                    )
                    if effect_receipt.status == "confirmed_failure":
                        _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                        for failure_event in build_effect_business_failure_events(
                            receipt=effect_receipt,
                            objective=str(node.goal or ""),
                            steps=len(history),
                            lang=lang,
                            result_data=project_verified_operation_result(
                                receipt=effect_receipt,
                                context=task_context,
                                form_state=form_transaction.export_state(),
                                observation=current_obs,
                            ),
                            subagent_id=subagent_id,
                            node_id=node.node_id,
                            emit_answer=not bool(_topology),
                        ):
                            yield failure_event
                        return
                    if receipt_application.goal_completed:
                        summary, completion_meta = build_effect_completion(
                            receipt=effect_receipt,
                            objective=str(node.goal or ""),
                            steps=len(history),
                            lang=lang,
                            result_data=project_verified_operation_result(
                                receipt=effect_receipt,
                                context=task_context,
                                form_state=form_transaction.export_state(),
                                observation=current_obs,
                            ),
                        )
                        _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                        if not _topology:
                            yield {"type": "answer", "content": summary}, {}
                        schedule_workflow_capture()
                        yield {"type": "subagent_done", "content": {
                            "subagent_id": subagent_id,
                            "node_id": node.node_id,
                            "status": "succeeded",
                        }}, completion_meta
                        return

            if prepared_effect is None and ok and decision.tool in {
                "browser_observe", "browser_read_text", "browser_navigate",
                "browser_scroll", "browser_back", "browser_forward",
            }:
                refreshed_receipts = await effect_tracker.refresh_pending(
                    after=current_obs,
                    supplemental_evidence=form_transaction.outcome_evidence(current_obs),
                )
                for refreshed_receipt in refreshed_receipts:
                    business_actions.record(refreshed_receipt)
                    notify_effect_receipt(planner, refreshed_receipt)
                    await persist_confirmed_effect(refreshed_receipt, current_obs)
                    if refreshed_receipt.status == "confirmed_success":
                        deferred_success_receipt = refreshed_receipt
                    form_transaction.after_effect(refreshed_receipt, current_obs)
                    receipt_application = apply_effect_receipt(
                        context=task_context,
                        tracks_context_state=context_tracks_state,
                        receipt=refreshed_receipt,
                        observation=current_obs,
                    )
                    if receipt_application.error:
                        logger.warning(
                            "browser context delayed effect hook failed",
                            extra={
                                "event": "browser.context_delayed_effect_hook_failed",
                                "error": receipt_application.error,
                            },
                        )
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=Decision(
                            tool="__effect_reverification__",
                            args={"contract_key": refreshed_receipt.contract_key},
                            rationale="system pending effect reverification",
                        ),
                        ok=refreshed_receipt.status == "confirmed_success",
                        error=(
                            None if refreshed_receipt.status == "confirmed_success"
                            else refreshed_receipt.reason
                        ),
                        result_digest=json.dumps(
                            refreshed_receipt.model_dump(mode="json"),
                            ensure_ascii=False,
                        )[:6000],
                    ))
                    yield {"type": "activity", "content": {
                        "kind": (
                            "complete" if refreshed_receipt.status == "confirmed_success"
                            else "analyze"
                        ),
                        "message": (
                            f"操作复核：{refreshed_receipt.status}（{refreshed_receipt.reason}）"
                            if lang == "zh" else
                            f"Operation recheck: {refreshed_receipt.status} ({refreshed_receipt.reason})"
                        )[:240],
                    }}, {}
                    if refreshed_receipt.status == "confirmed_failure":
                        _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                        for failure_event in build_effect_business_failure_events(
                            receipt=refreshed_receipt,
                            objective=str(node.goal or ""),
                            steps=len(history),
                            lang=lang,
                            result_data=project_verified_operation_result(
                                receipt=refreshed_receipt,
                                context=task_context,
                                form_state=form_transaction.export_state(),
                                observation=current_obs,
                            ),
                            subagent_id=subagent_id,
                            node_id=node.node_id,
                            emit_answer=not bool(_topology),
                        ):
                            yield failure_event
                        return
                    if bool((refreshed_receipt.fingerprint or {}).get("verification_exhausted")):
                        pending_resolved_decision = build_effect_verification_decision(
                            refreshed_receipt,
                            lang=lang,
                        )
                        yield {"type": "activity", "content": {
                            "kind": "warning",
                            "message": (
                                "自动复核已用尽，将请你确认保存/提交结果；系统不会重复执行该动作。"
                                if lang == "zh" else
                                "Automatic verification is exhausted. Human confirmation is required; the action will not be replayed."
                            ),
                        }}, {}
                        break
                    if receipt_application.goal_completed:
                        summary, completion_meta = build_effect_completion(
                            receipt=refreshed_receipt,
                            objective=str(node.goal or ""),
                            steps=len(history),
                            lang=lang,
                            result_data=project_verified_operation_result(
                                receipt=refreshed_receipt,
                                context=task_context,
                                form_state=form_transaction.export_state(),
                                observation=current_obs,
                            ),
                        )
                        _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                        if not _topology:
                            yield {"type": "answer", "content": summary}, {}
                        schedule_workflow_capture()
                        yield {"type": "subagent_done", "content": {
                            "subagent_id": subagent_id,
                            "node_id": node.node_id,
                            "status": "succeeded",
                        }}, completion_meta
                        return

            # Let the selected context update its durable state from the
            # observed action transition.
            if context_tracks_state:
                try:
                    task_context.after_transition(
                        BrowserActionTransition.capture(
                            decision,
                            before=dispatch_before_obs,
                            after=current_obs,
                        ),
                        result,
                        ok,
                        error=err,
                    )
                except Exception as exc:
                    logger.warning(
                        "browser context after step failed",
                        extra={
                            "event": "browser.context_after_step_failed",
                            "context": type(task_context).__name__,
                            "error": str(exc),
                        },
                    )

            effect_task_outcome = applied_effect_task_outcome(
                context=task_context,
                tracks_context_state=context_tracks_state,
                receipt=deferred_success_receipt,
            )
            if effect_task_outcome.terminal:
                summary, completion_meta = build_effect_completion(
                    receipt=deferred_success_receipt,
                    objective=str(node.goal or ""),
                    steps=len(history),
                    lang=lang,
                    outcome=effect_task_outcome,
                    result_data=project_verified_operation_result(
                        receipt=deferred_success_receipt,
                        context=task_context,
                        form_state=form_transaction.export_state(),
                        observation=current_obs,
                    ),
                )
                _topology = (getattr(inputs, "output_spec", None) or {}).get("graph_topology") or []
                if not _topology:
                    yield {"type": "answer", "content": summary}, {}
                schedule_workflow_capture()
                yield {"type": "subagent_done", "content": {
                    "subagent_id": subagent_id,
                    "node_id": node.node_id,
                    "status": "succeeded",
                }}, completion_meta
                return

            # Driver hook — lets stateful drivers (SkillDriver script
            # cursor, future drivers' internal state) react to
            # whatever decision actually executed. Errors here MUST
            # NOT break the main loop: the driver might be holding
            # invalid internal state but the executor and contexts
            # are still functioning.
            try:
                notify_step_completed(planner, decision, ok, current_obs, result)
            except Exception as exc:
                logger.warning("browser driver after-step hook failed", extra={"event": "browser.driver_after_step_failed", "error": str(exc)})

            # Stagnation check — only meaningful for tools that SHOULD
            # advance page state. Reads / waits don't count (they're
            # supposed to leave the page alone). browser_navigate also
            # skipped because URL change is its own, stronger signal.
            _progress_tools = {
                "browser_click", "browser_press", "browser_select",
                "browser_fill", "browser_upload_file",
                "browser_paste_image",
            }
            if ok and decision.tool in _progress_tools:
                post_action_ledger = None
                if context_tracks_state:
                    try:
                        post_action_ledger = task_context.build_state_ledger(current_obs)
                    except Exception:
                        post_action_ledger = None
                signature = browser_progress_signature(
                    current_obs,
                    state_ledger=post_action_ledger,
                )
                if last_progress_signature is not None and signature == last_progress_signature:
                    no_progress_streak += 1
                else:
                    no_progress_streak = 0
                    last_progress_signature = signature
                    stagnation_notices = 0
                if no_progress_streak >= NO_PROGRESS_STREAK_LIMIT:
                    hint = (
                            "⚠ 已连续 {n} 步操作返回 ok=True，但页面 URL / 元素数 / 文本 "
                            "都没有任何变化 —— 说明操作没有真正推进业务状态。"
                        "\n可能原因（按常见度）："
                        "\n  1. 必填字段（带 * 的 textbox）还没填 —— 检查 elements 里所有 role=textbox 的 name 含 '*' 或 '必填'，先 browser_fill"
                        "\n  2. 目标按钮被禁用（disabled / aria-disabled） —— 事件虽已分发，但业务不会响应"
                        "\n  3. 点到了装饰性 div / span，不是真正可交互控件"
                        "\n立即换策略："
                        "\n  - 先 browser_observe 重新扫一遍当前 elements（含 attributes），看谁是 disabled"
                        "\n  - 找齐所有必填项 browser_fill 之后再点提交"
                        "\n  - 如果按钮真的被禁用就 browser_fail 说明哪个前置条件没满足"
                    ).format(n=no_progress_streak + 1) if lang == "zh" else (
                        "⚠ {n} consecutive ok=True actions but page URL / element "
                        "count / text have not changed at all — the operations are "
                        "not actually advancing the business state."
                        "\nLikely causes:"
                        "\n  1. Required fields (textbox with '*' in name) not filled yet — a disabled submit can ignore a dispatched click"
                        "\n  2. Target button is disabled (attributes.disabled / aria-disabled)"
                        "\n  3. You clicked a decorative div/span, not an interactive control"
                        "\nSwitch tactics now:"
                        "\n  - browser_observe to rescan elements (attributes included), find who is disabled"
                        "\n  - browser_fill all required inputs, THEN click submit"
                        "\n  - if the button is truly disabled, browser_fail and name the missing precondition"
                    ).format(n=no_progress_streak + 1)
                    history.append(StepRecord(
                        observation=current_obs,
                        decision=Decision(tool="__stagnation_notice__", args={},
                                          rationale="system stagnation detector"),
                        ok=False, error=hint, result_digest="",
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": (
                            f"检测到 {no_progress_streak + 1} 步操作未推进页面状态，已提示换策略"
                            if lang == "zh"
                            else f"{no_progress_streak + 1} actions without page-state progress — nudging planner to switch tactics"
                        ),
                    }}, {}
                    logger.warning(
                        "browser stagnation noticed",
                        extra={"event": "browser.stagnation_notice", "streak": no_progress_streak + 1, "url": signature[0], "elements": signature[1]},
                    )
                    stagnation_notices += 1
                    stagnation_budget_exhausted = stagnation_budget.record_notice(signature[0])
                    if stagnation_notices >= 2 or stagnation_budget_exhausted:
                        assistance = browser_human_assistance(
                            source=NAVIGATION_STAGNATION,
                            observation=current_obs,
                            decision=decision,
                            lang=lang,
                        )
                        if automatic_assistance_available(assistance):
                            async for event in suspend_for_human_assistance(
                                question=assistance.question,
                                next_step=step + 1,
                                assistance=assistance,
                            ):
                                yield event
                            return
                        if assistance is None:
                            blocked_reason = (
                                "页面连续多轮没有推进，自动恢复已经用尽"
                                if lang == "zh" else
                                "The page did not advance across repeated automatic recovery cycles"
                            )
                            recovery = terminal_recovery_plan(
                                source=INTERACTION_BLOCKED,
                                error=blocked_reason,
                            )
                            if recovery_assistance_available(recovery):
                                async for event in suspend_for_recovery(
                                    recovery,
                                    next_step=step + 1,
                                ):
                                    yield event
                                return
                        reason = (
                            "页面连续多轮没有推进，已停止重复操作；需要重新观察或人工介入"
                            if lang == "zh" else
                            "The page did not advance across repeated recovery cycles; stopping duplicate actions"
                        )
                        yield {"type": "activity", "content": {
                            "kind": "error", "message": reason,
                        }}, {}
                        yield {"type": "subagent_done", "content": {
                            "subagent_id": subagent_id,
                            "node_id": node.node_id,
                            "status": "failed_terminal",
                        }}, {"browser_receipt": browser_failure_receipt(error=reason)}
                        return
                    no_progress_streak = 0
                    last_progress_signature = None

            # Track navigate targets for post-login redirect. Skip login-like
            # URLs so an LLM-driven navigate to /login can't poison the resume
            # target (which would trap the login wait loop polling /login
            # against itself forever).
            if decision.tool in ("browser_navigate", "browser_tab_new"):
                target = str(decision.args.get("url") or "")
                if target and not _is_login_like_url(target):
                    last_navigate_target = target

            # Remember the last non-login URL for each domain. Used as the
            # resume target after login, and as the recovery URL when a
            # spurious login signal fires on an already-authenticated domain.
            # A healthy (non-login) observation also resets the domain's
            # recovery budget — the session is clearly working fine right
            # now, so any later login glitch deserves a fresh retry window.
            _cur_domain = _domain(current_obs.url) or ""
            _cur_scope = site_scope(current_obs.url) or _cur_domain
            if _cur_domain and current_obs.url and not _is_login_like_url(current_obs.url):
                last_safe_url_by_domain[_cur_scope] = current_obs.url
                login_recovery_failures.pop(_cur_scope, None)

            # Capture the DOM-level login flag from the latest dispatch
            # result so the ask_user branch can tell a URL-substring match
            # (stale / harmless) from a genuine login form.
            last_dom_login_flag = bool(_login_detected(result))

            # JS-heavy SPA backends like creator consoles often land on a
            # fully valid non-login URL before the first interactive
            # elements hydrate. If we feed a transient 0-element snapshot
            # straight back into the planner, it tends to misdiagnose the
            # page as broken or unauthenticated and navigate to /login.
            # Give the page a short, bounded re-observe window first.
            stabilized_obs, stabilized, _retry_screenshot = await self._retry_empty_spa_observation(
                current_obs=current_obs,
                lang=lang,
                step=step,
            )
            if stabilized_obs is not current_obs:
                current_obs = stabilized_obs
                if current_obs.url:
                    _cur_domain = _domain(current_obs.url) or ""
                    _cur_scope = site_scope(current_obs.url) or _cur_domain
                    if _cur_domain and not _is_login_like_url(current_obs.url) and current_obs.elements:
                        last_safe_url_by_domain[_cur_scope] = current_obs.url
                        login_recovery_failures.pop(_cur_scope, None)
                if stabilized:
                    last_dom_login_flag = False
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": (
                            f"页面已完成渲染，检测到 {len(list(current_obs.elements or []))} 个可交互元素"
                            if lang == "zh"
                            else f"Page hydration completed; found {len(list(current_obs.elements or []))} interactive elements"
                        ),
                    }}, {}

            # Login detection: persist the exact browser state and end this
            # run as suspended. The session-bound auth watcher marks the
            # suspension ready; a later run resumes from this checkpoint.
            if _login_detected(result):
                login_domain = _domain(current_obs.url) or ""
                login_scope = site_scope(current_obs.url) or login_domain
                initial_auth = assessment_from_payload(result)
                auth_tracker.observe(
                    url=current_obs.url,
                    assessment=initial_auth,
                    has_page_evidence=bool(current_obs.elements or current_obs.page_text or current_obs.title),
                )
                # Authenticated-domain recovery path: once a domain has
                # completed login this session, give it a bounded number of
                # chances to be recovered via a safe-URL bounce before we
                # concede that the session genuinely expired. Without this
                # budget, a real cookie expiry on an "authenticated" domain
                # would trap us in a silent bounce loop.
                if login_scope and login_scope in authenticated_domains:
                    attempts = login_recovery_failures.get(login_scope, 0)
                    if attempts < MAX_LOGIN_RECOVERY_ATTEMPTS:
                        login_recovery_failures[login_scope] = attempts + 1
                        safe_url = (
                            last_safe_url_by_domain.get(login_scope)
                            or (last_navigate_target if last_navigate_target and not _is_login_like_url(last_navigate_target) else "")
                            or (f"https://{login_domain}/" if login_domain else "")
                        )
                        remaining = MAX_LOGIN_RECOVERY_ATTEMPTS - attempts - 1
                        yield {"type": "activity", "content": {
                            "kind": "analyze",
                            "message": (
                                f"已登录的 {login_domain} 上出现登录信号，尝试恢复回 {safe_url}（剩余 {remaining} 次）"
                                if lang == "zh"
                                else f"Login signal on authenticated {login_domain}; recovering to {safe_url} (remaining {remaining})"
                            ),
                        }}, {}
                        if safe_url:
                            try:
                                re_result = await self._dispatch(Decision(
                                    tool="browser_navigate",
                                    args={"url": safe_url},
                                    rationale="safe-URL recovery on authenticated domain"))
                                re_data = re_result[0]
                                if isinstance(re_data, dict):
                                    new_obs = _obs_from_payload(re_data.get("observation") or re_data)
                                    if new_obs:
                                        current_obs = new_obs
                                    last_dom_login_flag = bool(_login_detected(re_data))
                                    # If the recovery landed on a non-login
                                    # page, dismiss any stale login modal
                                    # left over from a prior wait loop on
                                    # this domain.
                                    if not last_dom_login_flag and not _is_login_like_url(current_obs.url):
                                        yield {"type": "intervention_cleared", "content": {
                                            "category": "login",
                                            "url": current_obs.url,
                                            "domain": login_domain,
                                            "reason": "authenticated_domain_recovery_succeeded",
                                        }}, {}
                            except Exception:
                                pass
                        continue
                    # Budget exhausted — session really expired. Drop the
                    # authenticated flag + counter and fall through to the
                    # real login flow below.
                    authenticated_domains.discard(login_scope)
                    login_recovery_failures.pop(login_scope, None)
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": (
                            f"{login_domain} 恢复重试已用尽，判定为真实登录过期，走正常重新登录"
                            if lang == "zh"
                            else f"Recovery budget for {login_domain} exhausted; treating as real session expiry"
                        ),
                    }}, {}

                auth_category = "registration" if initial_auth.get("state") == "registration_required" else "login"
                async for event in suspend_for_authentication(
                    category=auth_category,
                    source="login_detected",
                    next_step=step + 1,
                ):
                    yield event
                return

            if not ok:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    # First-hit at the ceiling: try one forced observation to
                    # refresh DOM state (stale refs are the usual triple-fail
                    # cause). Reset the counter once and let the planner see
                    # the refreshed snapshot in the next turn.
                    if not soft_recovery_used:
                        soft_recovery_used = True
                        yield {"type": "activity", "content": {
                            "kind": "warning",
                            "message": (
                                "连续 3 步失败，先刷新页面状态再继续" if lang == "zh"
                                else "3 consecutive failures — refreshing page state before retrying"
                            ),
                        }}, {}
                        try:
                            probe_result, probe_ok, _probe_err = await self._dispatch(
                                Decision(tool="browser_observe", args={},
                                         rationale="soft recovery after 3 consecutive failures"),
                            )
                            if probe_ok and isinstance(probe_result, dict):
                                refreshed = _obs_from_payload(probe_result)
                                if refreshed:
                                    current_obs = refreshed
                            history.append(StepRecord(
                                observation=current_obs,
                                decision=Decision(tool="browser_observe", args={},
                                                  rationale="system soft-recovery"),
                                ok=bool(probe_ok),
                                error=None if probe_ok else "soft-recovery observe also failed",
                                result_digest="",
                            ))
                            logger.info("browser soft recovery probe completed", extra={"event": "browser.soft_recovery", "probe_ok": bool(probe_ok), "url": str(getattr(current_obs, "url", "") or "")})
                        except Exception as exc:
                            logger.warning("browser soft recovery failed", extra={"event": "browser.soft_recovery_failed", "error": str(exc)})
                        consecutive_failures = 0
                        await save_checkpoint(phase="running", next_step=step + 1)
                        continue
                    # Recovery was already spent and we're still failing —
                    # genuine terminal. Emit as an activity warning (not a
                    # final-answer string) so it doesn't leak into the
                    # downstream compose node's rendered output.
                    assistance = browser_human_assistance(
                        source=NAVIGATION_TARGET_BLOCKED,
                        observation=current_obs,
                        decision=decision,
                        lang=lang,
                    )
                    if automatic_assistance_available(assistance):
                        async for event in suspend_for_human_assistance(
                            question=assistance.question,
                            next_step=step + 1,
                            assistance=assistance,
                        ):
                            yield event
                        return
                    if assistance is None:
                        recovery = terminal_recovery_plan(
                            source=LOOP_EXHAUSTED,
                            error=str(err or "repeated browser action failures"),
                        )
                        if recovery_assistance_available(recovery):
                            async for event in suspend_for_recovery(
                                recovery,
                                next_step=step + 1,
                            ):
                                yield event
                            return
                    yield {"type": "activity", "content": {
                        "kind": "error",
                        "message": (
                            "连续失败 3 次，且恢复尝试未成功，已中止浏览器任务" if lang == "zh"
                            else "3 consecutive failures after soft recovery — aborting browser task"
                        ),
                    }}, {}
                    yield {"type": "subagent_done", "content": {
                        "subagent_id": subagent_id, "node_id": node.node_id, "status": "failed_terminal",
                    }}, {"browser_receipt": browser_failure_receipt(error=err or "repeated failures")}
                    return
            else:
                consecutive_failures = 0

            await save_checkpoint(phase="running", next_step=step + 1)

        if execution_budget_exhausted:
            if execution_budget_effect_unknown:
                async for event in suspend_for_human_assistance(
                    question=unknown_effect_verification_question(lang),
                    next_step=max(start_step, step),
                    category=FORM_EFFECT_VERIFY_CATEGORY,
                ):
                    yield event
                return
            await save_checkpoint(
                phase="execution_budget_reached",
                next_step=max(start_step, step),
                status="failed_retryable",
            )
            continuation = build_budget_continuation(
                context=task_context,
                observation=current_obs,
                tracks_context_state=context_tracks_state,
                lang=lang,
                objective=str(node.goal or goal or ""),
                steps=len(history),
            )
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": continuation.summary,
            }}, {}
            yield {"type": "subagent_done", "content": {
                "subagent_id": subagent_id,
                "node_id": node.node_id,
                "status": "partial_success",
            }}, continuation.artifacts
            return

        # A policy/failure break may happen well before the configured budget.
        # Keep that distinct from genuine budget exhaustion in user-visible
        # output and receipts.
        exhausted_step_budget = step >= MAX_STEPS
        unresolved_effect = next((
            EffectReceipt.model_validate(item)
            for item in reversed(effect_tracker.receipts())
            if str(item.get("status") or "") in {"pending", "unknown"}
        ), None)
        if unresolved_effect is not None:
            verification = build_effect_verification_decision(
                unresolved_effect,
                lang=lang,
            )
            async for event in suspend_for_human_assistance(
                question=str(verification.args.get("question") or ""),
                next_step=step + 1,
                category=FORM_EFFECT_VERIFY_CATEGORY,
                handoff=dict(verification.args.get("handoff") or {}),
            ):
                yield event
            return
        terminal_error = str(
            (history[-1].error if history else "")
            or (
                "max steps exhausted"
                if exhausted_step_budget
                else "browser loop stopped after repeated blocked or failed actions"
            )
        )
        recovery = terminal_recovery_plan(
            source=LOOP_EXHAUSTED,
            error=terminal_error,
        )
        if recovery_assistance_available(recovery):
            async for event in suspend_for_recovery(
                recovery,
                next_step=step + 1,
            ):
                yield event
            return
        loop_failure_reason = (
            "max steps exhausted"
            if exhausted_step_budget
            else "browser loop stopped after repeated blocked or failed actions"
        )
        yield {"type": "activity", "content": {
            "kind": "warning",
            "message": (
                (
                    f"达到最大步数 {MAX_STEPS}"
                    if exhausted_step_budget
                    else "连续操作被拦截或失败，浏览器任务已停止"
                )
                if lang == "zh"
                else (
                    f"Reached max steps {MAX_STEPS}"
                    if exhausted_step_budget
                    else "Browser task stopped after repeated blocked or failed actions"
                )
            ),
        }}, {}
        yield {"type": "subagent_done", "content": {
            "subagent_id": subagent_id, "node_id": node.node_id, "status": "failed_terminal",
        }}, {"browser_receipt": browser_failure_receipt(error=loop_failure_reason)}

    async def _dispatch(self, decision: Decision):
        args = dict(decision.args or {})
        # `domain` is a meta field — which pool context the call runs against —
        # not a tool arg. Pull it out of args and promote it to the frame's
        # top-level ``domain`` so the agent can key the right browser context.
        # Precedence: explicit LLM-declared domain > host derived from url >
        # agent-side lastDomain fallback (see BrowserPool.getLastActivePage).
        declared = args.pop("domain", None)
        domain = str(declared).strip() if isinstance(declared, str) else None
        if not domain and decision.tool in ("browser_navigate", "browser_tab_new"):
            domain = _domain(str(args.get("url") or ""))
        try:
            result = await self.bridge.execute(
                decision.tool,
                args,
                domain=domain,
                timeout=timeout_for_tool(decision.tool),
            )
            ok = bool(result.get("ok"))
            err = result.get("error") if not ok else None
            return result.get("result"), ok, err
        except AgentNotConnected:
            return None, False, "agent-disconnected"
        except Exception as exc:
            return None, False, f"dispatch-error: {exc}"
