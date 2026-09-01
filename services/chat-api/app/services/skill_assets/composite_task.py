"""Parse and expand composite_task skills.

A composite_task skill's ``skill_markdown`` carries an ordered step list
in YAML frontmatter. Each step is the minimal pair the author is asked to
fill in the editor::

    ---
    steps:
      - site_profile_id: abc123   # optional; resolves to auth/entry/hints
        kind: browser             # optional; inferred when absent
        instruction: 导出本周已完成订单，保存为 excel
      - instruction: 把刚才导出的 excel 作为附件发送给 finance@acme.com
    ---

The planner-facing output is a list of subtask dicts in the exact shape
``TaskNetworkPlanner._expand_mixed_subtasks`` already consumes (``kind``,
``task_id``, ``title``, ``objective``, ``depends_on``, ``meta``). No new
execution engine is introduced — the composite skill is "just" a curated
way to fill ``content_task_spec.subtasks``.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import yaml

from app.services.workflow_browser_node import (
    browser_node_target_name,
    browser_node_target_reference,
    browser_node_target_url,
)
from pydantic import BaseModel, Field
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision


logger = logging.getLogger(__name__)


_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _extract_frontmatter(markdown: str) -> Dict[str, Any]:
    text = str(markdown or "")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _infer_kind(instruction: str, has_site: bool) -> str:
    """Guess a task family from the instruction text.

    Returns one of ``browser | research | generation | file``. The kind is
    only a routing hint; the step is still driven by natural-language
    instruction. A site reference strongly implies a browser task.
    """
    if has_site:
        return "browser"
    text = str(instruction or "").lower()
    if not text:
        return "generation"
    research_cues = ("搜索", "查询", "检索", "搜", "google", "baidu", "search", "look up", "find ")
    file_cues = ("导出", "保存为", "另存为", "生成文件", "export", "save as", "download file")
    generation_cues = ("写", "撰写", "生成", "草拟", "起草", "编写", "改写", "draft", "compose", "write ")
    if any(c in text for c in research_cues):
        return "research"
    if any(c in text for c in file_cues):
        return "file"
    if any(c in text for c in generation_cues):
        return "generation"
    return "generation"


_LOCATOR_FIELDS = (
    "role", "name", "name_contains", "aria_label",
    "icon_class", "text", "ancestor_role", "ancestor_contains_text", "nth",
)


def _coerce_locator(raw: Any) -> Dict[str, Any]:
    """Normalise a locator dict, dropping empties and unknown keys.

    Returns ``{}`` when no usable signal is provided — callers treat
    that as "no locator" and fall through to the rule layer."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key in _LOCATOR_FIELDS:
        if key not in raw:
            continue
        val = raw.get(key)
        if key == "nth":
            try:
                out[key] = int(val)
            except Exception:
                continue
            continue
        s = str(val or "").strip()
        if s:
            out[key] = s
    return out


def _coerce_locator_bag(raw: Any) -> Dict[str, Dict[str, Any]]:
    """Map ``op → locator`` (e.g. ``{"update": {...}, "delete": {...}}``).

    Accepts either a pre-keyed dict or a single locator dict (treated
    as the ``primary`` locator; CRUD contexts can map it per-op)."""
    if not isinstance(raw, dict):
        return {}
    # Pre-keyed shape: keys are op names.
    known_ops = {"create", "read", "update", "delete", "confirm", "submit", "primary"}
    keys = {str(k).strip().lower() for k in raw.keys()}
    if keys and keys.issubset(known_ops):
        out: Dict[str, Dict[str, Any]] = {}
        for op, loc in raw.items():
            coerced = _coerce_locator(loc)
            if coerced:
                out[str(op).strip().lower()] = coerced
        return out
    # Single-locator shorthand — treat as primary.
    single = _coerce_locator(raw)
    return {"primary": single} if single else {}


def _coerce_step(raw: Any, index: int) -> Optional[Dict[str, Any]]:
    if isinstance(raw, str):
        raw = {"instruction": raw}
    if not isinstance(raw, dict):
        return None
    instruction = str(raw.get("instruction") or raw.get("objective") or raw.get("goal") or "").strip()
    if not instruction:
        return None
    out: Dict[str, Any] = {
        "id": str(raw.get("id") or raw.get("step_id") or "").strip(),
        "index": int(index),
        "instruction": instruction,
        "site_profile_id": str(raw.get("site_profile_id") or "").strip(),
        "kind": str(raw.get("kind") or "").strip().lower(),
        "title": str(raw.get("title") or "").strip(),
    }
    locators = _coerce_locator_bag(raw.get("locators") or raw.get("locator"))
    if locators:
        out["locators"] = locators
    vars_raw = raw.get("locator_vars")
    if isinstance(vars_raw, dict) and vars_raw:
        out["locator_vars"] = {str(k): str(v) for k, v in vars_raw.items()}
    # Action-specific signals emitted by the trajectory distiller (and
    # writable by hand in the YAML editor). Preserved verbatim so a
    # strict step-replay driver can reconstruct the exact tool call.
    # These were dropped before the Driver abstraction landed because
    # only the LLM planner consumed parsed steps and it didn't need
    # them — the SkillDriver does.
    if "fill_value" in raw:
        out["fill_value"] = str(raw.get("fill_value") or "")
    nav_url = str(raw.get("navigate_url") or "").strip()
    if nav_url:
        out["navigate_url"] = nav_url
    node_type = str(raw.get("node_type") or raw.get("type") or "").strip()
    if node_type:
        out["node_type"] = node_type
    semantic_config = raw.get("semantic_config") or raw.get("businessConfig") or raw.get("business_config")
    if isinstance(semantic_config, dict) and semantic_config:
        out["semantic_config"] = dict(semantic_config)
    bound_writing_skill_id = str(raw.get("bound_writing_skill_id") or raw.get("boundWritingSkillId") or "").strip()
    if bound_writing_skill_id:
        out["bound_writing_skill_id"] = bound_writing_skill_id
    output_alias = str(raw.get("output_alias") or raw.get("outputAlias") or "").strip()
    if output_alias:
        out["output_alias"] = output_alias
    return out


def parse_composite_skill(skill_markdown: str) -> Dict[str, Any]:
    """Return a dict with ``triggers`` (list[str]) and ``steps`` (list[dict]).

    Returns empty lists when the markdown is malformed or declares no steps
    — callers should treat that as "not a usable composite skill".
    """
    fm = _extract_frontmatter(skill_markdown)
    triggers_raw = fm.get("triggers") or fm.get("trigger_examples") or []
    triggers: List[str] = []
    if isinstance(triggers_raw, list):
        for item in triggers_raw:
            trimmed = str(item or "").strip()
            if trimmed:
                triggers.append(trimmed)
    elif isinstance(triggers_raw, str):
        for line in triggers_raw.splitlines():
            trimmed = line.strip().lstrip("-*").strip()
            if trimmed:
                triggers.append(trimmed)

    raw_steps = fm.get("steps") or []
    steps: List[Dict[str, Any]] = []
    if isinstance(raw_steps, list):
        for idx, raw in enumerate(raw_steps):
            step = _coerce_step(raw, idx)
            if step is not None:
                steps.append(step)
    return {"triggers": triggers, "steps": steps}


class CompositeSkillMatchDecision(DecisionOutput):
    """Structured output from the LLM-based composite skill ranker.

    ``selected_skill_id`` is the id of the best-matching skill, or empty
    string when no candidate fits. ``reason`` is a short rationale used
    purely for logging — never fed back into any downstream logic.
    """

    selected_skill_id: str = Field(
        default="",
        description="id of the best-matching composite_task skill, or empty string if none applies",
    )
    reason: str = Field(
        default="",
        description="one-sentence rationale in the user's language",
    )


_COMPOSITE_RANKER_SYSTEM = """你是技能选择器。用户的对话请求前端已经解析出意图，你现在要做一件事：判断用户当前这句话，是否应该触发下面这些自定义技能中的某一个。

技能是一份"操作手册"——它描述了一个具体的业务任务（比如"在 OA 提交请假"或"导出本周订单并发给财务"），会直接改变后续 LLM 的执行目标。

判断标准（严格，宁可不选，不能误选）：
- 技能的 name / description / trigger_examples 要和用户请求的**业务意图**高度吻合。
- **只沾边同一个系统或站点不算吻合**——比如一条"查 Token 消耗"的技能，在用户问"看员工数"时不能选，哪怕两者都在同一个后台。
- 当用户级 skill 与组织级 skill 语义同等匹配，或看起来是同一个 skill 的用户版本和组织版本时，优先选择 user scope 的 skill。
- 一个请求只能匹配一条技能（或零条）。
- 请求是闲聊、问询定义、讨论技术话题等非操作类意图时，一律返回空 id。

仅输出结构化 JSON（由 schema 强制）。reason 用用户的语言写一句话即可。"""


def _skill_card_for_ranker(skill: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a skill dict to the fields the ranker actually needs.

    Keeps the prompt small and prevents accidentally leaking internal
    fields (owner_user_id, skill_contract, etc.) into the LLM input.
    """
    parsed = parse_composite_skill(str(skill.get("skill_markdown") or ""))
    visibility = str(skill.get("visibility") or "").strip().lower()
    user_id = str(skill.get("user_id") or "").strip().lower()
    source_scope = "organization" if visibility == "organization" or user_id == "organization" or str(skill.get("id") or "").startswith("org_skill:") else "user"
    return {
        "id": str(skill.get("id") or ""),
        "source_scope": source_scope,
        "name": str(skill.get("name") or "")[:160],
        "description": str(skill.get("description") or skill.get("summary") or "")[:400],
        "triggers": [str(t)[:120] for t in (parsed.get("triggers") or [])][:8],
        "steps_preview": [
            str((s or {}).get("instruction") or "")[:160]
            for s in (parsed.get("steps") or [])[:4]
        ],
    }


async def rank_composite_skill_match(
    llm_client: Any,
    query: str,
    skills: List[Dict[str, Any]],
) -> CompositeSkillMatchDecision:
    """Ask the LLM which composite_task skill (if any) the query should trigger.

    Returns an empty-id decision when the list is empty or LLM invocation
    fails — callers should treat that as "no skill matched" and continue
    with the no-skill code path. This keeps the planner resilient if the
    provider is down or flaky.
    """
    if not skills:
        return CompositeSkillMatchDecision(selected_skill_id="", reason="no candidates")
    trimmed_query = str(query or "").strip()
    if not trimmed_query:
        return CompositeSkillMatchDecision(selected_skill_id="", reason="empty query")

    cards = [_skill_card_for_ranker(s) for s in skills if isinstance(s, dict)]
    cards = [c for c in cards if c["id"]]
    if not cards:
        return CompositeSkillMatchDecision(selected_skill_id="", reason="no candidates after filter")

    # Lazy-imported to avoid pulling llm types into module import graph.
    from app.llm.types import Message, Role

    user_content = json.dumps(
        {"user_request": trimmed_query, "candidates": cards},
        ensure_ascii=False,
    )
    messages = [
        Message(role=Role.SYSTEM, content=_COMPOSITE_RANKER_SYSTEM),
        Message(role=Role.USER, content=user_content),
    ]
    try:
        decision = await invoke_structured_decision(
            llm_client, CompositeSkillMatchDecision, messages,
            spec=DecisionTurnSpec(locale="", turn_id="skill.composite_match"),
        )
    except Exception as exc:
        logger.warning("composite ranker LLM call failed", extra={"event": "skill.composite_ranker_llm_failed", "error": str(exc), "candidates": len(cards)})
        return CompositeSkillMatchDecision(selected_skill_id="", reason=f"llm_error: {exc}")

    # Defensive: make sure the LLM returned one of our candidate ids, not a
    # hallucinated one. If it did, treat as no match.
    valid_ids = {c["id"] for c in cards}
    if decision.selected_skill_id and decision.selected_skill_id not in valid_ids:
        logger.warning("composite ranker returned unknown id", extra={"event": "skill.composite_ranker_unknown_id", "skill_id": decision.selected_skill_id, "valid": len(valid_ids)})
        return CompositeSkillMatchDecision(
            selected_skill_id="",
            reason=f"hallucinated_id:{decision.selected_skill_id}",
        )
    return decision


def build_subtasks(
    *,
    steps: List[Dict[str, Any]],
    site_profile_lookup: Dict[str, Dict[str, Any]],
    task_id_prefix: str = "cs",
    user_goal: str = "",
) -> List[Dict[str, Any]]:
    """Turn parsed steps into subtask dicts for ``_expand_mixed_subtasks``.

    Steps execute sequentially so each subtask depends on its predecessor.
    The user's actual request (``user_goal``) is prepended to every step's
    objective so the LLM sees *what the user wants* on top of the skill's
    navigation guidance — a skill authored for "check Token usage" must
    not silently rewrite a query about "employee count".

    Site knowledge is stashed into ``meta`` so downstream executors (today
    the browser executor) can surface it to the planner LLM without
    changing the subtask contract.
    """
    subtasks: List[Dict[str, Any]] = []
    prev_task_id = ""
    trimmed_user_goal = str(user_goal or "").strip()
    for idx, step in enumerate(steps):
        task_id = f"{task_id_prefix}_{idx + 1}"
        site_id = str(step.get("site_profile_id") or "").strip()
        site_profile = site_profile_lookup.get(site_id) if site_id else None
        has_site = bool(site_profile)
        instruction = str(step.get("instruction") or "").strip()
        semantic_config = step.get("semantic_config") if isinstance(step.get("semantic_config"), dict) else {}
        target_name = browser_node_target_name(semantic_config)
        target_url = browser_node_target_url(semantic_config)
        kind = str(step.get("kind") or "").strip().lower() or _infer_kind(instruction, has_site)
        title = str(step.get("title") or "").strip() or instruction[:80]

        # Compose objective as three layers so both user intent and skill
        # guidance survive. Layer 1 (user goal) gets precedence; the skill
        # step is "how", the user goal is "what".
        objective_parts: List[str] = []
        if trimmed_user_goal and idx == 0:
            # Only the first step echoes the full user goal (later steps
            # depend on the first and inherit its context via the graph).
            objective_parts.append(f"用户要求: {trimmed_user_goal}")
        if instruction:
            objective_parts.append(
                f"操作指引 (来自已选技能, 仅作为执行参考, 用户真实意图以上面为准):\n{instruction}"
                if trimmed_user_goal and idx == 0
                else instruction
            )
        if site_profile:
            entry_url = str(site_profile.get("entry_url") or "").strip()
            if entry_url:
                objective_parts.append(
                    f"[目标站点: {site_profile.get('name') or entry_url} ({entry_url})]"
                )
        else:
            target_reference = browser_node_target_reference(semantic_config)
            if target_reference:
                objective_parts.append(target_reference)
        objective = "\n\n".join(objective_parts) if objective_parts else instruction

        meta: Dict[str, Any] = {"composite_step_index": idx}
        step_locators = step.get("locators")
        if isinstance(step_locators, dict) and step_locators:
            meta["locators"] = step_locators
        step_vars = step.get("locator_vars")
        if isinstance(step_vars, dict) and step_vars:
            meta["locator_vars"] = step_vars
        for key in ("node_type", "semantic_config", "bound_writing_skill_id", "output_alias"):
            value = step.get(key)
            if value:
                meta[key] = value
        if site_profile:
            meta["site_profile_id"] = site_id
            meta["site_name"] = str(site_profile.get("name") or "")
            meta["site_domain"] = str(site_profile.get("domain") or "")
            meta["entry_url"] = str(site_profile.get("entry_url") or "")
            meta["site_hints"] = str(site_profile.get("hints") or "")
            meta["site_auth_method"] = str(site_profile.get("auth_method") or "")
        else:
            if target_name:
                meta["site_name"] = target_name
            if target_url:
                meta["entry_url"] = target_url

        subtask: Dict[str, Any] = {
            "task_id": task_id,
            "kind": kind,
            "title": title,
            "objective": objective,
            "depends_on": [prev_task_id] if prev_task_id else [],
            "meta": meta,
        }
        subtasks.append(subtask)
        prev_task_id = task_id
    return subtasks


def format_site_hints_for_goal(meta: Dict[str, Any]) -> str:
    """Build a short ``[已知站点]`` paragraph to prepend to the browser goal.

    Returns empty string when the meta dict carries no site info — callers
    should no-op in that case.
    """
    if not isinstance(meta, dict):
        return ""
    hints = str(meta.get("site_hints") or "").strip()
    entry_url = str(meta.get("entry_url") or "").strip()
    name = str(meta.get("site_name") or "").strip()
    auth = str(meta.get("site_auth_method") or "").strip()
    if not (hints or entry_url or name):
        return ""
    lines: List[str] = ["[已知站点]"]
    if name or entry_url:
        header = "- 站点: " + " / ".join([p for p in (name, entry_url) if p])
        lines.append(header)
    if auth:
        lines.append(f"- 登录: {auth}")
    if hints:
        lines.append("- 站点知识:")
        for line in hints.splitlines():
            trimmed = line.strip()
            if not trimmed:
                continue
            if not trimmed.startswith(("-", "*", "·")):
                trimmed = f"• {trimmed}"
            lines.append(f"  {trimmed}")
    return "\n".join(lines)
