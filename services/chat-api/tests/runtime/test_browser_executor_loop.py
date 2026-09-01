from __future__ import annotations

import asyncio
from types import MethodType, SimpleNamespace

from app.enterprise_capabilities.browser.engine import desktop_agent_executor as executor_module
from app.enterprise_capabilities.browser.engine.desktop_agent_executor import DesktopAgentBrowserExecutor
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract, EffectReceipt
from app.enterprise_capabilities.browser.engine.effect_verification.tracker import PreparedEffect
from app.enterprise_capabilities.browser.engine.effect_verification.form_scope import ScopeBlocker
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision


class _Driver:
    kind = "test"

    def __init__(self) -> None:
        self.decisions = [
            Decision(tool="browser_fill", args={"ref": "search-v1", "value": "AI助手"}),
            Decision(tool="browser_click", args={"ref": "post-v3"}),
            Decision(tool="browser_fill", args={"ref": "comment-v4", "value": "真实而有价值的评论"}),
            Decision(tool="browser_click", args={"ref": "publish-v5"}),
            Decision(tool="browser_done", args={"summary": "unexpected extra step"}),
        ]
        self.calls = 0

    async def next_step(self, goal, history, observation, state_ledger=None):
        decision = self.decisions[self.calls]
        self.calls += 1
        return decision

    def on_step_completed(self, decision, ok, observation):
        return None

    def export_checkpoint_state(self):
        return {"calls": self.calls}

    def restore_checkpoint_state(self, payload):
        self.calls = int((payload or {}).get("calls") or 0)


class _AskUserDriver:
    kind = "test"

    def __init__(self) -> None:
        self.calls = 0

    async def next_step(self, goal, history, observation, state_ledger=None):
        self.calls += 1
        return Decision(
            tool="browser_ask_user",
            args={"question": "请完成登录"},
        )

    def on_step_completed(self, decision, ok, observation):
        return None

    def export_checkpoint_state(self):
        return {"calls": self.calls}

    def restore_checkpoint_state(self, payload):
        self.calls = int((payload or {}).get("calls") or 0)


class _UnknownSaveDriver:
    kind = "test"

    def __init__(self) -> None:
        self.calls = 0

    async def next_step(self, goal, history, observation, state_ledger=None):
        del goal, history, observation, state_ledger
        self.calls += 1
        if self.calls == 1:
            return Decision(tool="browser_click", args={"ref": "save"})
        return Decision(tool="browser_done", args={"summary": "草稿已保存"})

    def on_step_completed(self, decision, ok, observation):
        del decision, ok, observation

    def export_checkpoint_state(self):
        return {"calls": self.calls}

    def restore_checkpoint_state(self, payload):
        self.calls = int((payload or {}).get("calls") or 0)


class _RejectedFillDriver:
    kind = "test"

    def __init__(self) -> None:
        self.rejections = []

    async def next_step(self, goal, history, observation, state_ledger=None):
        del goal, history, observation, state_ledger
        if self.rejections:
            return Decision(
                tool="browser_fail",
                args={"reason": "stop after recovery probe"},
            )
        return Decision(
            tool="browser_fill",
            args={"ref": "note", "value": "待提交内容"},
        )

    def on_decision_rejected(
        self,
        decision,
        observation,
        *,
        category,
        reason,
    ):
        del decision, observation
        self.rejections.append((category, reason))

    def on_step_completed(self, decision, ok, observation):
        del decision, ok, observation

    def export_checkpoint_state(self):
        return {}

    def restore_checkpoint_state(self, payload):
        del payload


class _HallucinatedRouteDriver:
    kind = "test"

    def __init__(self) -> None:
        self.calls = 0
        self.rejections = []

    async def next_step(self, goal, history, observation, state_ledger=None):
        del goal, history, observation, state_ledger
        self.calls += 1
        return Decision(
            tool="browser_navigate",
            args={"url": "https://example.test/#/statistics"},
            rationale="guessed from the 统计分析 button label",
        )

    def on_decision_rejected(self, decision, observation, *, category, reason):
        del decision, observation
        self.rejections.append((category, reason))

    def on_step_completed(self, decision, ok, observation):
        del decision, ok, observation

    def export_checkpoint_state(self):
        return {}

    def restore_checkpoint_state(self, payload):
        del payload


def _payload(url: str, title: str, revision: str, elements, page_text: str = "", effects=None):
    return {
        "url": url,
        "title": title,
        "revision": revision,
        "elements": elements,
        "pageText": page_text,
        "effects": effects or [],
        "frameCount": 1,
    }


def test_executor_loop_converges_after_one_verified_business_commit(monkeypatch) -> None:
    home = _payload(
        "https://example.test/explore",
        "Explore",
        "tab:1",
        [{
            "ref": "search-v1", "role": "searchbox", "name": "Search",
            "editable": True, "semanticPurpose": "search", "scopeId": "search-form",
        }],
    )
    search_filled = _payload(
        home["url"], home["title"], "tab:2",
        [{
            **home["elements"][0],
            "ref": "search-v2",
            "value": "AI助手",
            "focused": True,
        }],
    )
    results = _payload(
        "https://example.test/search?q=AI助手",
        "Results",
        "tab:3",
        [{
            "ref": "post-v3", "role": "link", "name": "高赞帖子",
            "href": "https://example.test/post/1",
        }],
        "AI助手 高赞帖子",
    )
    detail = _payload(
        "https://example.test/post/1",
        "高赞帖子",
        "tab:4",
        [
            {
                "ref": "comment-v4", "role": "textbox", "name": "写评论",
                "editable": True, "scopeId": "comment-form",
            },
            {
                "ref": "publish-v4", "role": "button", "name": "发布",
                "scopeId": "comment-form", "disabled": True,
            },
        ],
        "这是帖子正文，包含可供评论使用的信息。",
    )
    comment_filled = _payload(
        detail["url"], detail["title"], "tab:5",
        [
            {
                **detail["elements"][0],
                "ref": "comment-v5",
                "value": "真实而有价值的评论",
                "focused": True,
            },
            {
                **detail["elements"][1],
                "ref": "publish-v5",
                "disabled": False,
            },
        ],
        detail["pageText"],
    )
    published = _payload(
        detail["url"], detail["title"], "tab:6",
        [{"ref": "posted", "role": "article", "text": "真实而有价值的评论"}],
        f"{detail['pageText']} 真实而有价值的评论 评论成功",
        [{"kind": "dom_added", "role": "status", "text": "评论成功"}],
    )

    driver = _Driver()
    monkeypatch.setattr(executor_module, "select_driver", lambda **kwargs: driver)

    def no_fast_path(**kwargs):
        return None

    async def no_sites(user_id):
        return []

    async def no_history_preflight(self, *, contract, observation):
        return SimpleNamespace(blocked=False)

    async def no_history_record(self, receipt, observation):
        return None

    def _receipt(prepared, *, status: str, reason: str) -> EffectReceipt:
        contract = prepared.contract
        return EffectReceipt(
            contract_key=contract.key(),
            status=status,
            confidence=0.99 if status == "confirmed_success" else 0.4,
            action_name=contract.action_name,
            operation_family=contract.operation_family,
            entity=contract.entity,
            side_effect=contract.side_effect,
            completes_goal=contract.completes_goal,
            fingerprint=contract.fingerprint,
            intended_operation=contract.intended_operation,
            intended_entity=contract.intended_entity,
            target_operation=contract.target_operation,
            target_entity=contract.target_entity,
            business_action_id=contract.business_action_id,
            action_attempt_id=contract.action_attempt_id,
            business_target_id=contract.business_target_id,
            observation_revision=contract.observation_revision,
            reason=reason,
        )

    async def pending_record(self, *, prepared, after, supplemental_evidence=None):
        receipt = _receipt(
            prepared,
            status="unknown",
            reason="initial post-action snapshot is not sufficient",
        )
        self._receipts[receipt.contract_key] = receipt
        self._pending[receipt.contract_key] = prepared
        return receipt

    async def confirm_pending(self, *, after, supplemental_evidence=None):
        refreshed = []
        for contract_key, prepared in list(self._pending.items()):
            receipt = _receipt(
                prepared,
                status="confirmed_success",
                reason="confirmed by the forced fresh observation",
            )
            self._receipts[contract_key] = receipt
            self._pending.pop(contract_key, None)
            refreshed.append(receipt)
        return refreshed

    monkeypatch.setattr(executor_module, "prepare_skill_fast_path", no_fast_path)
    monkeypatch.setattr(executor_module.site_profile_service, "list_for_user", no_sites)
    monkeypatch.setattr(executor_module.BrowserActionHistory, "preflight", no_history_preflight)
    monkeypatch.setattr(executor_module.BrowserActionHistory, "record", no_history_record)
    monkeypatch.setattr(executor_module.EffectTracker, "record", pending_record)
    monkeypatch.setattr(executor_module.EffectTracker, "refresh_pending", confirm_pending)

    executor = DesktopAgentBrowserExecutor("user-1", "session-1")
    state = {
        "observation": home,
        "tools": [],
        "requested_counts": {},
        "dispatched_counts": {},
    }

    async def dispatch(self, decision):
        tool = decision.tool
        if tool in {"browser_fill", "browser_click"}:
            requested = state["requested_counts"].get(tool, 0)
            dispatched = state["dispatched_counts"].get(tool, 0)
            assert requested > dispatched, "tool_requested must be yielded before real dispatch"
            state["dispatched_counts"][tool] = dispatched + 1
        state["tools"].append(tool)
        if tool == "browser_observe":
            return state["observation"], True, None
        if tool == "browser_fill":
            state["observation"] = (
                search_filled if decision.args["ref"] == "search-v1" else comment_filled
            )
            return {
                "observation": state["observation"],
                "fill_receipt": {"status": "confirmed", "reason": "value applied"},
            }, True, None
        if tool == "browser_press":
            state["observation"] = results
            return {"observation": results}, True, None
        if tool == "browser_click":
            state["observation"] = detail if decision.args["ref"] == "post-v3" else published
            return {"observation": state["observation"]}, True, None
        raise AssertionError(f"unexpected dispatch: {tool}")

    executor._dispatch = MethodType(dispatch, executor)
    goal = "搜索AI助手，进入帖子读取内容并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    inputs = CapabilityInputs(
        messages=[SimpleNamespace(role="user", content=goal)],
        raw_messages=[{"role": "user", "content": goal}],
        intent="browser_automation",
        output_spec={"run_id": "run-1"},
        language="zh",
    )

    async def collect():
        collected = []
        async for item in executor.execute(node=node, inputs=inputs):
            event, _meta = item
            if event.get("type") == "tool_requested":
                tool = event["content"]["tool"]
                state["requested_counts"][tool] = state["requested_counts"].get(tool, 0) + 1
            collected.append(item)
        return collected

    events = asyncio.run(collect())
    open_tools = []
    for event, _meta in events:
        event_type = event.get("type")
        if event_type == "tool_requested":
            open_tools.append(event["content"]["tool"])
        elif event_type in {"tool_completed", "tool_failed"}:
            assert open_tools, "a browser tool terminal event must follow its started event"
            assert open_tools.pop() == event["content"]["tool"]
    assert open_tools == []
    terminal = [
        (event, meta)
        for event, meta in events
        if event.get("type") == "subagent_done"
    ]

    assert terminal[-1][0]["content"]["status"] == "succeeded"
    assert terminal[-1][1]["browser_receipt"]["status"] == "ok"
    # Search submission is now a deterministic context action, so the model
    # driver is not called for the Enter key.
    assert driver.calls == 4
    assert state["tools"] == [
        "browser_observe",
        "browser_fill",
        "browser_press",
        "browser_click",
        "browser_observe",
        "browser_fill",
        "browser_click",
        "browser_observe",
    ]


def test_done_with_exhausted_save_verification_requests_human_confirmation(monkeypatch) -> None:
    driver = _UnknownSaveDriver()
    monkeypatch.setattr(executor_module, "select_driver", lambda **kwargs: driver)

    def no_fast_path(**kwargs):
        return None

    async def no_sites(user_id):
        return []

    async def pending_record(self, *, prepared, after, supplemental_evidence=None):
        del after, supplemental_evidence
        contract = prepared.contract
        receipt = EffectReceipt(
            contract_key=contract.key(),
            status="unknown",
            action_name=contract.action_name,
            operation_family=contract.operation_family,
            side_effect=contract.side_effect,
            completes_goal=True,
            fingerprint=contract.fingerprint,
            reason="no fresh direct save proof",
        )
        self._receipts[receipt.contract_key] = receipt
        self._pending[receipt.contract_key] = prepared
        return receipt

    async def prepare_save(self, *, target, before):
        del target
        return PreparedEffect(
            target_key="save",
            before=before,
            contract=EffectContract(
                action_name="保存为草稿",
                operation_family="save",
                side_effect="write",
                is_commit=True,
                completes_goal=True,
                source="local_rule",
            ),
        )

    async def exhaust_pending(self, *, after, supplemental_evidence=None):
        del after, supplemental_evidence
        refreshed = []
        for key in list(self._pending):
            receipt = self._receipts[key].model_copy(update={
                "fingerprint": {
                    **dict(self._receipts[key].fingerprint or {}),
                    "verification_exhausted": True,
                },
            })
            self._receipts[key] = receipt
            self._pending.pop(key, None)
            refreshed.append(receipt)
        return refreshed

    monkeypatch.setattr(executor_module, "prepare_skill_fast_path", no_fast_path)
    monkeypatch.setattr(executor_module.site_profile_service, "list_for_user", no_sites)
    monkeypatch.setattr(executor_module.EffectTracker, "record", pending_record)
    monkeypatch.setattr(executor_module.EffectTracker, "prepare_click", prepare_save)
    monkeypatch.setattr(executor_module.EffectTracker, "refresh_pending", exhaust_pending)

    page = _payload(
        "https://example.test/editor",
        "Editor",
        "tab:1",
        [{"ref": "save", "role": "button", "name": "保存为草稿"}],
        "文章内容",
    )
    executor = DesktopAgentBrowserExecutor("user-1", "session-1")

    async def dispatch(self, decision):
        if decision.tool in {"browser_observe", "browser_click"}:
            return {"observation": page}, True, None
        raise AssertionError(f"unexpected dispatch: {decision.tool}")

    executor._dispatch = MethodType(dispatch, executor)
    goal = "保存文章草稿"
    node = CapabilityTask(
        node_id="browser",
        goal=goal,
        assigned_agent="agent.browser",
        meta={"capability_id": "browser.submit"},
    )
    inputs = CapabilityInputs(
        messages=[SimpleNamespace(role="user", content=goal)],
        raw_messages=[{"role": "user", "content": goal}],
        intent="browser_automation",
        output_spec={"run_id": "run-1"},
        language="zh",
    )

    async def collect():
        return [item async for item in executor.execute(node=node, inputs=inputs)]

    events = asyncio.run(collect())
    interventions = [
        event["content"] for event, _ in events
        if event.get("type") == "intervention_required"
    ]
    terminal = [
        event for event, _ in events if event.get("type") == "subagent_done"
    ]

    assert interventions[-1]["category"] == "form_effect_verify"
    assert interventions[-1]["handoff"]["contract"]["kind"] == "form_effect_verify"
    assert terminal[-1]["content"]["status"] == "suspended_waiting_approval"


def test_scope_rejection_notifies_driver_and_forces_fresh_observation(monkeypatch) -> None:
    driver = _RejectedFillDriver()
    monkeypatch.setattr(executor_module, "select_driver", lambda **kwargs: driver)

    def no_fast_path(**kwargs):
        return None

    async def no_sites(user_id):
        return []

    def reject_fill(self, decision, observation):
        del self, observation
        if decision.tool != "browser_fill":
            return None
        return ScopeBlocker(
            active_scope="0:#active-form",
            target_scope="unresolved",
            reason="target disappeared before dispatch",
        )

    monkeypatch.setattr(executor_module, "prepare_skill_fast_path", no_fast_path)
    monkeypatch.setattr(executor_module.site_profile_service, "list_for_user", no_sites)
    monkeypatch.setattr(
        executor_module.FormTransactionTracker,
        "interaction_scope_blocker",
        reject_fill,
    )

    executor = DesktopAgentBrowserExecutor("user-1", "session-1")
    page = _payload(
        "https://example.test/form",
        "Form",
        "tab:1",
        [{
            "ref": "note",
            "role": "textbox",
            "name": "备注",
            "editable": True,
            "scopeId": "0:#active-form",
        }],
    )
    tools = []

    async def dispatch(self, decision):
        tools.append(decision.tool)
        assert decision.tool == "browser_observe"
        return page, True, None

    executor._dispatch = MethodType(dispatch, executor)
    goal = "填写并提交表单"
    node = CapabilityTask(
        node_id="browser",
        goal=goal,
        assigned_agent="agent.browser",
        meta={"capability_id": "browser.submit"},
    )
    inputs = CapabilityInputs(
        messages=[SimpleNamespace(role="user", content=goal)],
        raw_messages=[{"role": "user", "content": goal}],
        intent="browser_automation",
        output_spec={"run_id": "run-1"},
        language="zh",
    )

    async def collect():
        return [item async for item in executor.execute(node=node, inputs=inputs)]

    events = asyncio.run(collect())

    assert driver.rejections == [
        ("scope_target_unresolved", "target disappeared before dispatch"),
    ]
    assert tools == ["browser_observe", "browser_observe"]
    terminal = [event for event, _ in events if event.get("type") == "subagent_done"]
    assert terminal[-1]["content"]["status"] == "suspended_waiting_approval"
    intervention = next(
        event for event, _ in events
        if event.get("type") == "intervention_required"
    )
    assert intervention["content"]["category"] == "browser_interaction"


def test_hallucinated_same_site_navigation_never_reaches_browser(monkeypatch) -> None:
    driver = _HallucinatedRouteDriver()
    monkeypatch.setattr(executor_module, "select_driver", lambda **kwargs: driver)

    def no_fast_path(**kwargs):
        return None

    async def no_sites(user_id):
        return []

    monkeypatch.setattr(executor_module, "prepare_skill_fast_path", no_fast_path)
    monkeypatch.setattr(executor_module.site_profile_service, "list_for_user", no_sites)

    executor = DesktopAgentBrowserExecutor("user-1", "session-1")
    page = _payload(
        "https://example.test/home",
        "Home",
        "tab:1",
        [{"ref": "stats", "role": "button", "name": "统计分析"}],
    )
    tools = []

    async def dispatch(self, decision):
        tools.append(decision.tool)
        assert decision.tool == "browser_observe"
        return page, True, None

    executor._dispatch = MethodType(dispatch, executor)
    goal = "进入统计分析"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    inputs = CapabilityInputs(
        messages=[SimpleNamespace(role="user", content=goal)],
        raw_messages=[{"role": "user", "content": goal}],
        intent="browser_automation",
        output_spec={"run_id": "run-1"},
        language="zh",
    )

    async def collect():
        return [item async for item in executor.execute(node=node, inputs=inputs)]

    events = asyncio.run(collect())

    assert tools == ["browser_observe"]
    assert driver.calls == 3
    assert [category for category, _ in driver.rejections] == [
        "navigation_provenance",
        "navigation_provenance",
        "navigation_provenance",
    ]
    warnings = [
        event["content"]["message"]
        for event, _ in events
        if event.get("type") == "activity"
        and event.get("content", {}).get("kind") == "warning"
    ]
    assert any("不要根据按钮文字猜站内路径" in message for message in warnings)


def test_url_only_login_ask_user_suspends_once_instead_of_replanning(monkeypatch) -> None:
    driver = _AskUserDriver()
    monkeypatch.setattr(executor_module, "select_driver", lambda **kwargs: driver)

    def no_fast_path(**kwargs):
        return None

    async def no_sites(user_id):
        return []

    suspensions = []

    async def fake_auth_suspension(*, bridge, save_checkpoint, request):
        suspensions.append(request)
        yield {
            "type": "intervention_required",
            "content": {
                "category": request.category,
                "resumable": True,
                "suspension_id": "susp-1",
            },
        }, {}
        yield {
            "type": "subagent_done",
            "content": {
                "subagent_id": request.subagent_id,
                "node_id": request.node_id,
                "status": "suspended_waiting_approval",
            },
        }, {"gateway": "SUSPEND"}

    monkeypatch.setattr(executor_module, "prepare_skill_fast_path", no_fast_path)
    monkeypatch.setattr(executor_module.site_profile_service, "list_for_user", no_sites)
    monkeypatch.setattr(
        executor_module,
        "suspend_browser_authentication",
        fake_auth_suspension,
    )

    executor = DesktopAgentBrowserExecutor("user-1", "session-1")
    login_page = _payload(
        "https://example.test/login",
        "Login",
        "tab:1",
        [],
        "Please sign in",
    )

    async def dispatch(self, decision):
        assert decision.tool == "browser_observe"
        return login_page, True, None

    executor._dispatch = MethodType(dispatch, executor)
    goal = "登录后继续发布"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    inputs = CapabilityInputs(
        messages=[SimpleNamespace(role="user", content=goal)],
        raw_messages=[{"role": "user", "content": goal}],
        intent="browser_automation",
        output_spec={"run_id": "run-1"},
        language="zh",
    )

    async def collect():
        return [item async for item in executor.execute(node=node, inputs=inputs)]

    events = asyncio.run(collect())

    assert driver.calls == 1
    assert len(suspensions) == 1
    assert suspensions[0].source == "ask_user"
    assert suspensions[0].next_step == 2
    terminal = [event for event, _ in events if event.get("type") == "subagent_done"]
    assert terminal[-1]["content"]["status"] == "suspended_waiting_approval"


def test_non_auth_ask_user_keeps_the_generic_intervention_path(monkeypatch) -> None:
    driver = _AskUserDriver()
    monkeypatch.setattr(executor_module, "select_driver", lambda **kwargs: driver)

    def no_fast_path(**kwargs):
        return None

    async def no_sites(user_id):
        return []

    async def unexpected_auth_suspension(**kwargs):
        raise AssertionError("ordinary user input must not enter browser auth suspension")
        yield  # pragma: no cover

    monkeypatch.setattr(executor_module, "prepare_skill_fast_path", no_fast_path)
    monkeypatch.setattr(executor_module.site_profile_service, "list_for_user", no_sites)
    monkeypatch.setattr(
        executor_module,
        "suspend_browser_authentication",
        unexpected_auth_suspension,
    )

    executor = DesktopAgentBrowserExecutor("user-1", "session-1")
    ownership_commands = []

    async def send_command(command, **kwargs):
        ownership_commands.append((command, kwargs))

    executor.bridge = SimpleNamespace(send_command=send_command)
    form_page = _payload(
        "https://example.test/form",
        "Form",
        "tab:1",
        [{"ref": "e1", "role": "textbox", "name": "审批意见", "editable": True}],
        "请确认审批意见",
    )

    async def dispatch(self, decision):
        assert decision.tool == "browser_observe"
        return form_page, True, None

    executor._dispatch = MethodType(dispatch, executor)
    goal = "填写表单，遇到不明确的信息时询问我"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    inputs = CapabilityInputs(
        messages=[SimpleNamespace(role="user", content=goal)],
        raw_messages=[{"role": "user", "content": goal}],
        intent="browser_automation",
        output_spec={"run_id": "run-1"},
        language="zh",
    )

    async def collect():
        return [item async for item in executor.execute(node=node, inputs=inputs)]

    events = asyncio.run(collect())

    assert driver.calls == 1
    interventions = [
        event["content"]
        for event, _ in events
        if event.get("type") == "intervention_required"
    ]
    assert interventions[-1]["category"] == "browser"
    assert [command for command, _ in ownership_commands] == [
        "recording_start", "set_owner",
    ]
    assert ownership_commands[0][1]["recording_mode"] == "assistance"
    assert ownership_commands[0][1]["run_id"] == "run-1"
    assert ownership_commands[0][1]["node_id"] == "browser"
    assert ownership_commands[1] == ("set_owner", {"owner": "human"})
    terminal = [event for event, _ in events if event.get("type") == "subagent_done"]
    assert terminal[-1]["content"]["status"] == "suspended_waiting_approval"
