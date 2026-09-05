from __future__ import annotations

from app.enterprise_capabilities.browser.engine.checkpoint import BrowserExecutionCheckpoint
from app.enterprise_capabilities.browser.engine.contexts.action_transition import BrowserActionTransition
from app.enterprise_capabilities.browser.engine.contexts.factory import maybe_init
from app.enterprise_capabilities.browser.engine.contexts.general import GeneralBrowserContext
from app.enterprise_capabilities.browser.engine.contexts.detail_progress import capture_detail_baseline
from app.enterprise_capabilities.browser.engine.contexts.search_progress import SearchBaseline
from app.enterprise_capabilities.browser.engine.form_input.input_context import (
    BrowserInputContext,
    InputCandidate,
)
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _obs(url: str, title: str, text: str = "") -> Observation:
    return Observation(url=url, title=title, elements=[], page_text=text)


def _step(ctx: GeneralBrowserContext, tool: str, obs: Observation, args=None, result=None) -> None:
    ctx.after_step(
        Decision(tool=tool, args=args or {}),
        result or {},
        True,
        obs,
    )


def _prepare(ctx: GeneralBrowserContext, tool: str, obs: Observation, args=None) -> Decision:
    decision = Decision(tool=tool, args=args or {})
    verdict, prepared, hint = ctx.validate_action(decision, obs)
    assert verdict == "allow", hint
    return prepared


def _transition(
    ctx: GeneralBrowserContext,
    decision: Decision,
    before: Observation,
    after: Observation,
    result=None,
) -> None:
    ctx.after_transition(
        BrowserActionTransition.capture(
            decision,
            before=before,
            after=after,
        ),
        result or {},
        True,
    )


def test_factory_uses_stateful_general_context_for_uncategorized_browser_task():
    node = CapabilityTask(node_id="browser", goal="open a site", assigned_agent="agent.browser")

    context = maybe_init(
        node=node,
        output_spec={},
        original_user_request="open a site",
        goal="open a site",
        lang="en",
    )

    assert isinstance(context, GeneralBrowserContext)
    assert context.stateful is True
    assert context.active is False


def test_focused_read_does_not_repeat_search_from_original_chat_request():
    original = "搜索 DeepSeek Harness，打开一篇笔记并发表评论"
    goal = "快速检查当前页面：报告 URL、标题以及是否出现登录或风控提示，只读取，不操作"
    node = CapabilityTask(
        node_id="browser",
        goal=goal,
        assigned_agent="agent.browser",
        meta={"capability_id": "browser.read"},
    )

    context = GeneralBrowserContext(
        lang="zh",
        node=node,
        goal=goal,
        original_user_request=original,
    )
    detail = _obs(
        "https://example.test/detail/1",
        "Detail title",
        "正文内容，没有登录或风控提示",
    )
    _step(context, "browser_observe", detail)

    assert context.requirements == {"navigate", "read"}
    assert context.ready_to_done() is True
    assert "search_submitted" not in context.build_state_ledger(detail)["remaining_signals"]


def test_factory_marks_media_search_satisfied_when_upstream_files_exist():
    goal = "打开创作编辑器，搜索2张相关配图并下载上传，停留在发布预览"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    input_context = BrowserInputContext(
        original_request="生成图文并放入创作编辑器",
        candidates=[
            InputCandidate(
                candidate_id="media-1",
                source_kind="upstream",
                source_path="artifacts.writer.publish_payload.media.0",
                semantic_name="media",
                value=["/tmp/generated-image.png"],
                value_kind="file",
            ),
        ],
    )

    context = maybe_init(
        node=node,
        output_spec={},
        original_user_request=input_context.original_request,
        goal=goal,
        lang="zh",
        input_context=input_context,
    )

    assert isinstance(context, GeneralBrowserContext)
    assert "search" in context.requirements
    assert "search" in context.completed
    assert context.mission.search_enabled is False
    assert "search_submitted" not in context.build_state_ledger()["remaining_signals"]
    assert any(
        signal == "upstream_satisfied: search_submitted"
        for signal in context.build_state_ledger()["completed_signals"]
    )


def test_upstream_media_does_not_satisfy_a_platform_content_search():
    goal = "搜索高赞帖子，进入详情阅读内容，然后上传已有配图"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    input_context = BrowserInputContext(
        original_request=goal,
        candidates=[
            InputCandidate(
                candidate_id="media-1",
                source_kind="upstream",
                source_path="artifacts.writer.publish_payload.media.0",
                semantic_name="media",
                value=["/tmp/generated-image.png"],
                value_kind="file",
            ),
        ],
    )

    context = maybe_init(
        node=node,
        output_spec={},
        original_user_request=goal,
        goal=goal,
        lang="zh",
        input_context=input_context,
    )

    assert isinstance(context, GeneralBrowserContext)
    assert "search" in context.requirements
    assert "search" not in context.completed
    assert context.mission.search_enabled is True


def test_prepare_only_publish_request_does_not_require_or_allow_final_commit():
    goal = "打开创作入口，填写标题正文和配图，停留在发布预览页面"
    original = f"{goal}，暂时不要点击最终发布按钮"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=original,
    )
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        elements=[
            {"ref": "entry", "role": "button", "name": "发布图文笔记"},
            {"ref": "publish", "role": "button", "name": "发布"},
        ],
    )

    assert context.stop_before_final_commit is True
    assert "commit" not in context.requirements
    assert context.validate_action(
        Decision(tool="browser_click", args={"ref": "entry"}),
        observation,
    )[0] == "allow"
    verdict, _decision, hint = context.validate_action(
        Decision(tool="browser_click", args={"ref": "publish"}),
        observation,
    )
    assert verdict == "reject"
    assert "预览或草稿" in hint


def test_general_context_keeps_page_evidence_after_returning_from_detail():
    goal = (
        "Search for employee service desk, open the first question, read its title and URL, "
        "then go back to the search results."
    )
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="en", node=node, goal=goal, original_user_request=goal,
    )
    home = Observation(
        url="https://example.test/", title="Home",
        elements=[{"ref": "e1", "role": "searchbox", "name": "Search", "editable": True, "semanticPurpose": "search"}],
    )
    results = Observation(
        url="https://example.test/search?q=desk", title="Search", page_text="First question",
        elements=[{
            "ref": "e8", "role": "link", "name": "How should a service desk work?",
            "href": "https://example.test/question/42",
        }],
    )
    detail = _obs("https://example.test/question/42", "How should a service desk work?")

    _step(context, "browser_navigate", home)
    _step(context, "browser_fill", home, {"ref": "e1", "value": "employee service desk"})
    _step(context, "browser_press", results, {"key": "Enter"})
    assert "search" in context.completed
    assert "open_result" not in context.completed
    decision = _prepare(context, "browser_click", results, {"ref": "e8"})
    _step(context, decision.tool, detail, decision.args)
    _step(context, "browser_read_text", detail, result={"text": "A useful answer."})
    _step(context, "browser_back", results)

    ledger = context.build_state_ledger(results)

    assert ledger["remaining_signals"] == []
    assert context.ready_to_done() is True
    assert any("question/42" in signal for signal in ledger["completed_signals"])
    assert any("How should a service desk work?" in signal for signal in ledger["completed_signals"])


def test_action_target_identity_survives_dynamic_dom_ref_renumbering():
    goal = "搜索相关帖子，进入一个帖子详情，阅读正文并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    search = Observation(
        url="https://example.test/explore",
        title="Explore",
        elements=[{
            "ref": "search-before",
            "role": "textbox",
            "name": "搜索",
            "placeholder": "搜索内容",
            "editable": True,
        }],
    )
    search_filled = Observation(
        url=search.url,
        title=search.title,
        elements=[{
            "ref": "search-after",
            "role": "textbox",
            "name": "搜索",
            "placeholder": "搜索内容",
            "editable": True,
            "value": "AI助手",
        }],
    )
    stale_after_fill = Observation(
        url=search.url,
        title=search.title,
        elements=[],
        fresh=False,
    )
    results = Observation(
        url="https://example.test/search?q=AI助手",
        title="Search results",
        page_text="AI助手 帖子一 帖子二",
        elements=[
            {
                "ref": "result-after-submit",
                "role": "link",
                "name": "帖子一",
                "href": "https://example.test/post/1",
            },
            {
                "ref": "result-two",
                "role": "link",
                "name": "帖子二",
                "href": "https://example.test/post/2",
            },
        ],
    )
    detail = Observation(
        url="https://example.test/post/1",
        title="帖子一",
        page_text="这是帖子正文，已经足以生成一条有价值的评论。",
        elements=[{
            "ref": "comment-after-open",
            "role": "textbox",
            "name": "写评论",
            "editable": True,
        }],
    )

    fill = Decision(
        tool="browser_fill",
        args={"ref": "search-before", "value": "AI助手"},
    )
    _transition(context, fill, search, stale_after_fill)

    assert context.search_input_pending is True
    assert context.search_baseline is not None
    assert context.search_baseline.query == "AI助手"

    _transition(
        context,
        Decision(tool="browser_observe", args={}),
        stale_after_fill,
        search_filled,
    )

    assert context.search_input_pending is True
    assert "search" not in context.completed

    press = Decision(
        tool="browser_press",
        args={"ref": "search-after", "key": "Enter"},
    )
    _transition(context, press, search_filled, results)

    assert "search" in context.completed

    click = _prepare(
        context,
        "browser_click",
        results,
        {"ref": "result-after-submit"},
    )
    _transition(context, click, results, detail)

    assert "open_result" in context.completed
    assert "read" in context.completed
    assert context.evidence[0]["url"] == detail.url


def test_unfinished_detail_candidate_is_excluded_after_returning_to_results():
    goal = "从候选列表中进入一个问题并发布回答"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    results = Observation(
        url="https://example.test/invited",
        title="Candidates",
        page_text="First question Second question",
        elements=[
            {
                "ref": "first-title",
                "role": "link",
                "name": "First question",
                "href": "https://example.test/question/1",
                "selector": "#list > article:nth-child(1) > header > a",
            },
            {
                "ref": "first",
                "role": "button",
                "name": "写回答",
                "selector": "#list > article:nth-child(1) > footer > button",
            },
            {
                "ref": "second-title",
                "role": "link",
                "name": "Second question",
                "href": "https://example.test/question/2",
                "selector": "#list > article:nth-child(2) > header > a",
            },
            {
                "ref": "second",
                "role": "button",
                "name": "写回答",
                "selector": "#list > article:nth-child(2) > footer > button",
            },
        ],
    )
    unavailable_detail = Observation(
        url="https://example.test/question/1",
        title="First question",
        page_text="Existing result",
        elements=[],
    )

    first = _prepare(context, "browser_click", results, {"ref": "first"})
    _transition(context, first, results, unavailable_detail)
    assert "open_result" in context.completed
    assert context.detail_target_lock.detail_confirmed is True

    _transition(
        context,
        Decision(
            tool="browser_navigate",
            args={"url": "https://example.test/invited"},
        ),
        unavailable_detail,
        results,
    )

    assert "open_result" not in context.completed
    assert context.detail_target_lock.target is None
    verdict, _decision, hint = context.validate_action(first, results)
    assert verdict == "reject"
    assert "当前详情目标" in hint

    verdict, _decision, hint = context.validate_action(
        Decision(tool="browser_click", args={"ref": "second"}),
        results,
    )
    assert verdict == "allow", hint
    constraints = context.build_state_ledger(results)["action_constraints"]
    assert any("已淘汰" in item for item in constraints)


def test_entry_navigation_does_not_complete_open_result_before_candidate_selection():
    goal = "打开问题推荐列表，选择一个问题并发布回答"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    blank = Observation(url="about:blank", title="", elements=[])
    results = Observation(
        url="https://example.test/invited",
        title="Candidates",
        page_text="First question",
        elements=[{
            "ref": "question-1",
            "role": "link",
            "name": "First question",
            "href": "https://example.test/question/1",
        }],
    )
    detail = Observation(
        url="https://example.test/question/1",
        title="First question",
        page_text="Question details",
        elements=[],
    )

    entry = _prepare(
        context,
        "browser_navigate",
        blank,
        {"url": results.url},
    )
    assert context.detail_target_lock.target is None
    _transition(context, entry, blank, results)

    assert "navigate" in context.completed
    assert "open_result" not in context.completed
    assert context.detail_target_lock.target is None

    candidate = _prepare(
        context,
        "browser_navigate",
        results,
        {"url": detail.url},
    )
    assert context.detail_target_lock.target is not None
    assert context.detail_target_lock.target.target_url == detail.url
    _transition(context, candidate, results, detail)

    assert "open_result" in context.completed
    assert context.detail_url == detail.url


def test_confirmed_deferred_effect_blocks_another_business_write():
    goal = "搜索相关帖子，进入一个帖子，阅读后发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    context.completed.add("navigate")
    receipt = EffectReceipt(
        contract_key="comment:post-1",
        status="confirmed_success",
        confidence=0.98,
        action_name="发布",
        operation_family="publish",
        side_effect="external",
        business_action_id="comment:post-1",
    )

    context.after_effect(
        receipt,
        _obs("https://example.test/post/1", "Post one"),
    )

    assert context.mission.confirmed_effects == 0
    assert context.build_state_ledger()["pending_confirmed_effects"] == 1
    assert context.business_effect_blocker(object()) != ""

    search = Observation(
        url="https://example.test/search",
        title="Search",
        elements=[{
            "ref": "new-search",
            "role": "searchbox",
            "editable": True,
            "semanticPurpose": "search",
        }],
    )
    verdict, rewritten, _ = context.validate_action(
        Decision(
            tool="browser_fill",
            args={"ref": "new-search", "value": "第二个关键词"},
        ),
        search,
    )
    assert verdict == "rewrite"
    assert rewritten.tool == "browser_observe"

    context.completed.update({"search", "open_result", "read"})
    context._reconcile_deferred_effects()

    assert context.mission.confirmed_effects == 1
    assert context.ready_to_done() is True
    assert context.business_effect_blocker(object()) == ""


def test_confirmed_effect_with_missing_milestones_converges_to_partial_success():
    goal = "搜索相关帖子，进入一个帖子，阅读后发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    context.completed.add("navigate")
    receipt = EffectReceipt(
        contract_key="comment:post-2",
        status="confirmed_success",
        confidence=0.98,
        action_name="发布评论",
        operation_family="publish",
        side_effect="external",
        business_action_id="comment:post-2",
    )
    current = _obs("https://example.test/post/2", "Post two")

    context.after_effect(receipt, current)
    assert context.effect_task_outcome(receipt).status == "continue"

    _transition(
        context,
        Decision(tool="browser_observe", args={}),
        current,
        current,
    )
    outcome = context.effect_task_outcome(receipt)

    assert outcome.status == "partial_success"
    assert "navigate" in outcome.verified_requirements
    assert set(outcome.missing_requirements) >= {"search", "open_result", "commit"}


def test_general_context_checkpoint_restores_milestones_not_raw_dom():
    goal = "Open the first result and read its content"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="en", node=node, goal=goal, original_user_request=goal,
    )
    detail = _obs("https://example.test/item/7", "Item seven")
    _step(context, "browser_navigate", detail)
    _step(context, "browser_read_text", detail, result={"text": "Evidence text"})

    checkpoint = BrowserExecutionCheckpoint.capture(
        phase="running",
        next_step=3,
        visible_tool_step=2,
        observation=detail,
        history=[],
        authenticated_domains=set(),
        last_safe_url_by_domain={},
        login_recovery_failures={},
        wait_for_text_calls={},
        context_state=context.export_checkpoint_state(),
    )
    restored = GeneralBrowserContext(
        lang="en", node=node, goal=goal, original_user_request=goal,
    )
    restored.restore_checkpoint_state(checkpoint.context_state)

    assert restored.page_milestones == context.page_milestones
    assert restored.evidence == context.evidence
    assert restored.completed == context.completed


def test_returning_a_title_is_not_misread_as_browser_back_requirement():
    goal = "打开 https://example.test，读取页面内容，返回页面标题和网址"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    page = _obs("https://example.test/", "Example")

    _step(context, "browser_navigate", page)
    _step(context, "browser_read_text", page, result={"text": "Example body"})

    assert "return" not in context.requirements
    assert context.ready_to_done() is True


def test_open_result_can_complete_from_click_transition_without_search_step():
    goal = "打开列表中的第一条结果并读取正文"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=goal, original_user_request=goal,
    )
    listing = Observation(
        url="https://example.test/items", title="Items", page_text="First item",
        elements=[{
            "ref": "e2", "role": "link", "name": "First item",
            "href": "https://example.test/items/1",
        }],
    )
    detail = _obs("https://example.test/items/1", "First item")

    _step(context, "browser_navigate", listing)
    decision = _prepare(context, "browser_click", listing, {"ref": "e2"})
    _step(context, decision.tool, detail, decision.args)
    _step(context, "browser_read_text", detail, result={"text": "Item body"})

    assert context.ready_to_done() is True


def test_delayed_detail_navigation_is_recorded_by_later_observation():
    goal = "搜索相关帖子，进入一个帖子详情并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    search = Observation(
        url="https://example.test/search", title="Search", page_text="",
        elements=[{"ref": "e1", "role": "searchbox", "name": "Search", "editable": True, "semanticPurpose": "search"}],
    )
    results = Observation(
        url="https://example.test/search?q=AI", title="Search results", page_text="结果一 结果二",
        elements=[{
            "ref": "e7", "role": "link", "name": "帖子七", "text": "帖子七",
            "href": "https://example.test/post/7", "x": 100, "y": 200,
            "width": 160, "height": 100,
        }],
    )
    detail = _obs("https://example.test/post/7", "Post seven", "帖子正文")

    _step(context, "browser_fill", search, {"ref": "e1", "value": "AI助手"})
    _step(context, "browser_press", results, {"key": "Enter"})
    decision = _prepare(context, "browser_click_at", results, {"x": 120, "y": 240})
    _step(context, decision.tool, results, decision.args)
    assert "open_result" not in context.completed

    _step(context, "browser_observe", detail)

    assert "open_result" in context.completed
    assert context.detail_url == detail.url


def test_failed_detail_click_reobserves_and_retries_the_same_result():
    goal = "搜索相关帖子，进入一个帖子详情并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    search = Observation(
        url="https://example.test/search", title="Search", page_text="",
        elements=[{"ref": "e1", "role": "searchbox", "name": "Search", "editable": True, "semanticPurpose": "search"}],
    )
    results = Observation(
        url="https://example.test/search?q=AI", title="Results", page_text="帖子七 帖子八",
        elements=[
            {"ref": "e7", "role": "link", "name": "帖子七", "href": "https://example.test/post/7"},
            {"ref": "e8", "role": "link", "name": "帖子八", "href": "https://example.test/post/8"},
        ],
    )
    _step(context, "browser_fill", search, {"ref": "e1", "value": "AI助手"})
    _step(context, "browser_press", results, {"key": "Enter"})
    first = _prepare(context, "browser_click", results, {"ref": "e7"})
    _step(context, first.tool, results, first.args)

    observe = context.suggest_next_action(results)
    assert observe is not None and observe.tool == "browser_observe"
    _step(context, observe.tool, results, observe.args)

    retry = context.suggest_next_action(Observation(
        url=results.url, title=results.title, page_text=results.page_text,
        elements=[
            {"ref": "e19", "role": "link", "name": "帖子七", "href": "https://example.test/post/7"},
            {"ref": "e20", "role": "link", "name": "帖子八", "href": "https://example.test/post/8"},
        ],
    ))
    assert retry is not None
    assert retry.tool == "browser_click"
    assert retry.args["ref"] == "e19"


def test_same_url_detail_overlay_is_recorded_from_changed_page_state():
    goal = "搜索相关帖子，进入一个帖子详情并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    search = Observation(
        url="https://example.test/search", title="Search", page_text="",
        elements=[{"ref": "e1", "role": "searchbox", "name": "Search", "editable": True, "semanticPurpose": "search"}],
    )
    results = Observation(
        url="https://example.test/search?q=AI", title="Search results", page_text="结果一 结果二",
        elements=[{
            "ref": "e7", "role": "button", "name": "帖子七", "text": "帖子七",
            "scopeLockable": True,
        }],
    )
    overlay = _obs("https://example.test/search?q=AI", "Post detail", "帖子七 完整帖子正文与评论区域")

    _step(context, "browser_fill", search, {"ref": "e1", "value": "AI助手"})
    _step(context, "browser_press", results, {"key": "Enter"})
    decision = _prepare(context, "browser_click", results, {"ref": "e7"})
    _step(context, decision.tool, results, decision.args)
    _step(context, "browser_observe", overlay)

    assert "open_result" in context.completed


def test_wrong_detail_resource_blocks_comment_and_returns_to_source_list():
    goal = "搜索相关帖子，进入帖子详情阅读后发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    results = Observation(
        url="https://example.test/search?q=AI",
        title="Search results",
        page_text="目标帖子 其他帖子",
        elements=[{
            "ref": "e81",
            "role": "link",
            "name": "目标帖子",
            "href": "https://example.test/post/expected",
            "contentContextId": "attribute:data-note-id:expected-record",
        }],
    )
    wrong_detail = Observation(
        url="https://example.test/post/other",
        title="无关招聘信息",
        page_text="这是另一篇完全无关的帖子",
        elements=[
            {"ref": "comment", "role": "textbox", "editable": True},
            {"ref": "send", "role": "button", "name": "发送"},
        ],
    )
    context.completed.update({"navigate", "search"})
    context.search_results_url = results.url
    context.detail_baseline = capture_detail_baseline(results)

    click = _prepare(context, "browser_click", results, {"ref": "e81"})
    _transition(context, click, results, wrong_detail)

    verdict, _, hint = context.validate_action(
        Decision(tool="browser_fill", args={"ref": "comment", "value": "评论"}),
        wrong_detail,
    )
    assert verdict == "reject"
    assert "详情页尚未确认" in hint

    verdict, _, hint = context.validate_action(
        Decision(tool="browser_click", args={"ref": "send"}),
        wrong_detail,
    )
    assert verdict == "reject"
    assert "禁止填写" in hint

    recovery = context.suggest_next_action(wrong_detail)
    assert recovery is not None
    assert recovery.tool == "browser_navigate"
    assert recovery.args["url"] == results.url


def test_verified_detail_resource_allows_comment_input():
    goal = "搜索相关帖子，进入帖子详情阅读后发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    results = Observation(
        url="https://example.test/search?q=AI",
        title="Search results",
        page_text="目标帖子",
        elements=[{
            "ref": "e81",
            "role": "link",
            "name": "目标帖子",
            "href": "https://example.test/post/expected",
            "contentContextId": "attribute:data-note-id:expected-record",
        }],
    )
    detail = Observation(
        url="https://example.test/post/expected",
        title="目标帖子",
        page_text="目标帖子正文",
        elements=[
            {"ref": "comment", "role": "textbox", "editable": True},
            {"ref": "send", "role": "button", "name": "发送"},
        ],
    )
    context.completed.update({"navigate", "search"})
    context.search_results_url = results.url
    context.detail_baseline = capture_detail_baseline(results)

    click = _prepare(context, "browser_click", results, {"ref": "e81"})
    _transition(context, click, results, detail)

    verdict, _, hint = context.validate_action(
        Decision(tool="browser_fill", args={"ref": "comment", "value": "评论"}),
        detail,
    )
    assert verdict == "allow", hint

    _step(
        context,
        "browser_fill",
        detail,
        {"ref": "comment", "value": "评论"},
    )
    verdict, _, hint = context.validate_action(
        Decision(tool="browser_click", args={"ref": "send"}),
        detail,
    )
    assert verdict == "allow", hint


def test_detail_observation_counts_visible_post_text_as_read_evidence():
    goal = "搜索相关帖子，打开一个结果，阅读帖子内容并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    context.completed.update({"navigate", "search", "open_result"})
    detail = _obs(
        "https://example.test/post/1",
        "Post one",
        "这是帖子正文，浏览器观察已经取得了撰写评论所需的内容。",
    )

    _step(context, "browser_observe", detail)

    assert "read" in context.completed
    assert context.evidence[0]["text"].startswith("这是帖子正文")


def test_search_results_observation_does_not_satisfy_detail_read_requirement():
    goal = "搜索相关帖子，打开一个结果并阅读帖子内容"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    context.completed.update({"navigate", "search"})
    results = _obs(
        "https://example.test/search?q=service",
        "Search results",
        "结果一 结果二 结果三",
    )

    _step(context, "browser_observe", results)

    assert "read" not in context.completed
    assert context.evidence == []


def test_opening_an_english_post_does_not_imply_a_publish_operation():
    goal = "Open the first post and read its content"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="en", node=node, goal=goal, original_user_request=goal)

    assert "commit" not in context.requirements


def test_search_publish_mission_does_not_switch_query_before_consuming_results():
    goal = "搜索多个行业关键词，打开相关帖子并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    search = Observation(
        url="https://example.test/search", title="Search", page_text="",
        elements=[{"ref": "e1", "role": "textbox", "name": "Search", "editable": True, "semanticPurpose": "search"}],
    )
    _step(context, "browser_fill", search, {"ref": "e1", "value": "AI助手"})
    results = Observation(
        url="https://example.test/search?q=AI", title="Search results", page_text="AI助手",
        elements=search.elements,
    )
    _step(context, "browser_press", results, {"key": "Enter"})
    _step(context, "browser_observe", results)

    verdict, _, hint = context.validate_action(
        Decision(tool="browser_fill", args={"ref": "e1", "value": "工单系统"}), search,
    )
    assert verdict == "reject"
    assert "AI助手" in hint


def test_direct_search_result_navigation_creates_a_search_cycle():
    goal = "搜索相关帖子，进入一个帖子详情并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    results = Observation(
        url="https://example.test/search_result?keyword=AI助手",
        title="AI助手 - 搜索结果",
        page_text="AI助手 结果一 结果二",
        elements=[
            {"ref": "e7", "role": "link", "name": "结果一", "href": "https://example.test/post/1"},
            {"ref": "e8", "role": "link", "name": "结果二", "href": "https://example.test/post/2"},
            {"ref": "e9", "role": "link", "name": "结果三", "href": "https://example.test/post/3"},
        ],
    )

    _step(
        context,
        "browser_navigate",
        results,
        {"url": "https://example.test/search_result?keyword=AI助手"},
    )

    assert "search" in context.completed
    assert context.mission.current_cycle is not None
    assert context.mission.current_cycle.query == "AI助手"
    assert context.mission.current_cycle.state == "submitted"

    verdict, _, hint = context.validate_action(
        Decision(tool="browser_fill", args={"ref": "search", "value": "工单系统"}),
        Observation(
            url=results.url,
            title=results.title,
            page_text=results.page_text,
            elements=[{
                "ref": "search", "role": "searchbox", "editable": True,
                "semanticPurpose": "search",
            }],
        ),
    )
    assert verdict == "reject"
    assert "AI助手" in hint


def test_direct_result_navigation_detail_read_and_one_effect_complete_vague_mission():
    goal = "搜索一些相关帖子，进入高赞帖子阅读后发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    results = Observation(
        url="https://example.test/search?keyword=AI助手",
        title="AI助手 - 搜索结果",
        page_text="AI助手 帖子一 帖子二",
        elements=[
            {"ref": "e7", "role": "link", "name": "帖子一", "href": "https://example.test/post/1"},
            {"ref": "e8", "role": "link", "name": "帖子二", "href": "https://example.test/post/2"},
        ],
    )
    detail = _obs(
        "https://example.test/post/1",
        "帖子一",
        "这是帖子正文，提供了撰写评论所需的业务信息。",
    )

    _step(context, "browser_navigate", results, {"url": results.url})
    click = _prepare(context, "browser_click", results, {"ref": "e7"})
    _step(context, click.tool, detail, click.args)
    _step(context, "browser_observe", detail)
    context.after_effect(EffectReceipt(
        contract_key="comment:post-1",
        status="confirmed_success",
        confidence=0.96,
        action_name="发布",
        operation_family="publish",
        completes_goal=False,
    ), detail)

    assert {"navigate", "search", "open_result", "read", "commit"}.issubset(context.completed)
    assert context.mission.minimum_effects == 1
    assert context.ready_to_done() is True
    result_evidence = context.result_evidence(detail)
    assert result_evidence["search_query"] == "AI助手"
    assert result_evidence["target_url"] == "https://example.test/post/1"
    assert result_evidence["target_title"] == "帖子一"
    assert "这是帖子正文" in result_evidence["observed_content"]["text"]


def test_each_item_language_compiles_as_multi_operation_mission():
    goal = "依次搜索几个关键词，进入帖子详情，每帖发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)

    assert context.mission.minimum_effects == 2


def test_vague_some_language_defaults_to_one_external_write():
    goal = "浏览一些相关帖子，从中选择一篇并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)

    assert context.mission.minimum_effects == 1


def test_some_business_targets_with_comment_scope_compiles_as_multi_operation():
    original_request = "进入到一些高评论、高赞的帖子笔记下面进行评论"
    # The graph goal can lose the quantifier; the original request must remain
    # authoritative for browser operation cardinality.
    goal = "搜索相关笔记并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh",
        node=node,
        goal=goal,
        original_user_request=original_request,
    )

    assert context.mission.minimum_effects == 2


def test_enter_does_not_complete_search_without_result_page_evidence():
    goal = "搜索员工服务台并打开一个结果"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    search = Observation(
        url="https://example.test/explore", title="Explore", page_text="员工服务台",
        elements=[{"ref": "e1", "role": "searchbox", "name": "Search", "editable": True, "semanticPurpose": "search", "value": "员工服务台"}],
    )

    _step(context, "browser_fill", search, {"ref": "e1", "value": "员工服务台"})
    _step(context, "browser_press", search, {"key": "Enter"})

    assert "search" not in context.completed
    assert context.search_input_pending is True
    assert context.mission.cycles == []


def test_search_mission_accepts_one_unambiguous_editor_without_accessibility_semantics():
    goal = "搜索 Askbot 并总结"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    landing = Observation(
        url="https://example.test/", title="Search", page_text="",
        elements=[{
            "ref": "e15", "role": "textbox", "selector": "#chat-textarea",
            "editable": True, "visible": True, "value": "",
        }],
    )

    _step(context, "browser_fill", landing, {"ref": "e15", "value": "Askbot"})

    assert context.search_submission.active is True
    decision = context.suggest_next_action(Observation(
        url=landing.url, title=landing.title,
        elements=[{**landing.elements[0], "value": "Askbot"}],
    ))
    assert decision is not None
    assert context.interaction_purpose(decision, landing) == "search"


def test_fresh_result_observation_reconciles_search_after_action_history_is_lost():
    goal = "搜索 Askbot 并总结"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    context.search_baseline = SearchBaseline(query="Askbot", url="https://example.test/", title="Search")
    results = Observation(
        url="https://example.test/s?wd=Askbot",
        title="Askbot search results",
        page_text="Askbot official site and product overview",
        elements=[
            {"ref": "r1", "role": "link", "href": "https://askbot.example/", "name": "Askbot"},
            {"ref": "r2", "role": "link", "href": "https://docs.example/askbot", "name": "Docs"},
        ],
    )

    ledger = context.build_state_ledger(results)

    assert "search" in context.completed
    assert "search_submitted" in ledger["completed_signals"]
    assert context.phase != "awaiting_search"


def test_non_search_editor_does_not_create_a_search_baseline():
    goal = "搜索相关帖子并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    editor = Observation(
        url="https://example.test/post/1", title="Post", page_text="",
        elements=[{"ref": "e9", "role": "textbox", "name": "写评论", "editable": True}],
    )

    _step(context, "browser_fill", editor, {"ref": "e9", "value": "有价值的评论"})

    assert context.search_baseline is None
    assert context.search_input_pending is False


def test_multi_result_publish_requires_confirmed_effects_before_done():
    goal = "搜索多个相关话题，打开帖子并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    context.completed.update({"navigate", "search", "open_result"})
    receipt = EffectReceipt(
        contract_key="one", status="confirmed_success", confidence=0.95,
        action_name="发布", operation_family="publish", completes_goal=False,
    )
    context.after_effect(receipt, _obs("https://example.test/post/1", "Post"))
    assert context.ready_to_done() is False
    assert "open_result" not in context.completed
    context.completed.add("open_result")
    context.after_effect(receipt.model_copy(update={"contract_key": "two"}), _obs("https://example.test/post/2", "Post"))
    assert context.ready_to_done() is True


def test_observed_content_and_required_confirmed_effects_finish_multi_post_mission():
    goal = "搜索多个相关帖子，阅读帖子内容后分别发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    context.completed.update({"navigate", "search", "open_result"})
    detail = _obs("https://example.test/post/1", "Post", "帖子正文已经由页面观察取得。")
    _step(context, "browser_observe", detail)
    receipt = EffectReceipt(
        contract_key="one", status="confirmed_success", confidence=0.95,
        action_name="发布", operation_family="publish", completes_goal=False,
    )

    context.after_effect(receipt, detail)
    assert context.ready_to_done() is False
    assert "read" not in context.completed
    _step(
        context,
        "browser_observe",
        _obs("https://example.test/post/2", "Post", "第二篇帖子正文。"),
    )
    context.after_effect(
        receipt.model_copy(update={"contract_key": "two"}),
        _obs("https://example.test/post/2", "Post", "第二篇帖子正文。"),
    )

    assert context.ready_to_done() is True
    assert context.build_state_ledger()["remaining_signals"] == []


def test_first_comment_starts_a_fresh_verified_target_cycle_before_second_comment():
    request = "搜索AI助手相关信息，进入一些高赞帖子笔记下面进行评论"
    node = CapabilityTask(node_id="browser", goal=request, assigned_agent="agent.browser")
    context = GeneralBrowserContext(
        lang="zh", node=node, goal=request, original_user_request=request,
    )
    context.completed.update({"navigate", "search", "open_result"})
    context.search_results_url = "https://example.test/search?q=assistant"
    context.detail_url = "https://example.test/post/1"
    context.detail_business_target = "content:post-1"
    first = EffectReceipt(
        contract_key="comment:post-1",
        business_action_id="comment:post-1",
        status="confirmed_success",
        confidence=0.96,
        action_name="发布评论",
        operation_family="publish",
        side_effect="external",
    )

    context.after_effect(first, _obs("https://example.test/post/1", "Post one"))

    assert context.mission.confirmed_effects == 1
    assert context.ready_to_done() is False
    assert "search" in context.completed
    assert "open_result" not in context.completed
    assert "commit" not in context.completed
    assert context.detail_business_target == ""
    assert context.business_effect_blocker(object()) == ""
    suggested = context.suggest_next_action(
        _obs("https://example.test/post/1", "Post one"),
    )
    assert suggested is not None
    assert suggested.tool == "browser_navigate"
    assert suggested.args["url"] == "https://example.test/search?q=assistant"

    results = Observation(
        url="https://example.test/search?q=assistant",
        title="Results",
        page_text="Post two",
        elements=[{
            "ref": "post-2",
            "role": "link",
            "name": "Post two",
            "href": "https://example.test/post/detail",
            "contentContextId": "attribute:data-note-id:post-2",
        }],
    )
    second_detail = _obs(
        "https://example.test/post/detail",
        "Post two",
        "第二篇帖子的正文内容。",
    )
    click_second = _prepare(context, "browser_click", results, {"ref": "post-2"})
    _transition(context, click_second, results, second_detail)

    assert {"open_result", "read"}.issubset(context.completed)
    assert context.business_target_hint(second_detail) == "attribute:data-note-id:post-2"

    second = first.model_copy(update={
        "contract_key": "comment:post-2",
        "business_action_id": "comment:post-2",
    })
    context.after_effect(second, second_detail)

    assert context.mission.confirmed_effects == 2
    assert context.ready_to_done() is True


def test_intermediate_submit_receipt_cannot_complete_comment_goal():
    goal = "搜索相关帖子，进入帖子详情并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    context.completed.add("navigate")
    search_submit = EffectReceipt(
        contract_key="search-submit", status="confirmed_success", confidence=0.94,
        action_name="Submit", operation_family="submit", side_effect="write",
        fingerprint={"interaction_purpose": "search"},
    )

    context.after_effect(search_submit, _obs("https://example.test/search?q=desk", "Results"))

    assert context.mission.confirmed_effects == 0
    assert "commit" not in context.completed
    assert context.effect_completes_task(search_submit) is False
    assert "search" in context.rejected_effects[0]["reason"]

    context.completed.update({"search", "open_result"})
    context._reconcile_deferred_effects()

    assert context.mission.confirmed_effects == 0
    assert "commit" not in context.completed


def test_verified_business_effect_completes_commit_after_required_phases():
    goal = "搜索相关帖子，进入帖子详情并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    context.completed.update({"navigate", "search", "open_result"})
    publish = EffectReceipt(
        contract_key="comment-publish", status="confirmed_success", confidence=0.95,
        action_name="发布", operation_family="publish", side_effect="external",
    )

    context.after_effect(publish, _obs("https://example.test/post/1", "Post one"))

    assert context.mission.confirmed_effects == 1
    assert "commit" in context.completed
    assert context.effect_completes_task(publish) is True


def test_return_to_known_page_does_not_count_as_opening_result_detail():
    goal = "搜索相关帖子，进入帖子详情并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    home = Observation(
        url="https://example.test/explore", title="Explore", page_text="",
        elements=[{
            "ref": "search", "role": "searchbox", "name": "Search",
            "editable": True, "semanticPurpose": "search",
        }],
    )
    results = Observation(
        url="https://example.test/search?q=desk", title="Results", page_text="Result one",
        elements=[{
            "ref": "home", "role": "link", "name": "Home",
            "href": "https://example.test/explore",
        }],
    )
    _step(context, "browser_navigate", home)
    _step(context, "browser_fill", home, {"ref": "search", "value": "desk"})
    _step(context, "browser_press", results, {"key": "Enter"})
    decision = _prepare(context, "browser_click", results, {"ref": "home"})

    _step(context, decision.tool, home, decision.args)

    assert "search" in context.completed
    assert "open_result" not in context.completed
    assert context.mission.current_cycle is not None
    assert context.mission.current_cycle.state != "detail_opened"


def test_search_success_then_return_cannot_finish_publish_mission():
    goal = "搜索相关帖子，进入帖子详情并发表评论"
    node = CapabilityTask(node_id="browser", goal=goal, assigned_agent="agent.browser")
    context = GeneralBrowserContext(lang="zh", node=node, goal=goal, original_user_request=goal)
    home = Observation(
        url="https://example.test/explore", title="Explore", page_text="",
        elements=[{
            "ref": "search", "role": "searchbox", "name": "Search",
            "editable": True, "semanticPurpose": "search",
        }],
    )
    results = Observation(
        url="https://example.test/assistant?q=desk", title="Assistant results",
        page_text="工单系统的搜索结果",
        elements=[{
            "ref": "home", "role": "link", "name": "Home",
            "href": "https://example.test/explore",
        }],
    )
    search_receipt = EffectReceipt(
        contract_key="search-submit", status="confirmed_success", confidence=0.94,
        action_name="Submit", operation_family="submit", side_effect="write",
        fingerprint={"interaction_purpose": "search"},
    )

    _step(context, "browser_navigate", home)
    _step(context, "browser_fill", home, {"ref": "search", "value": "工单系统"})
    context.after_effect(search_receipt, results)
    _step(context, "browser_click", results, {"ref": "submit"})
    decision = _prepare(context, "browser_click", results, {"ref": "home"})
    _step(context, decision.tool, home, decision.args)

    assert "search" in context.completed
    assert "open_result" not in context.completed
    assert "commit" not in context.completed
    assert context.effect_completes_task(search_receipt) is False
    assert context.ready_to_done() is False
