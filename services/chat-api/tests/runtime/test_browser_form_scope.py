from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.effect_verification.form_transaction import FormTransactionTracker
from app.enterprise_capabilities.browser.engine.agent_loop import planner as browser_planner
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


COMMENT_SCOPE = "body > main > dialog > article > footer"


def _element(
    ref: str,
    *,
    scope: str,
    editable: bool = False,
    role: str = "button",
    value: str = "",
):
    return {
        "ref": ref,
        "role": role,
        "editable": editable,
        "visible": True,
        "selector": f"#{ref}",
        "scopeId": f"0:{scope}",
        "scopeSelector": scope,
        "frameDepth": 0,
        "value": value,
    }


def _obs(*elements, url: str = "https://example.test/post") -> Observation:
    return Observation(url=url, title="test", elements=list(elements))


def _lock_comment_scope() -> tuple[FormTransactionTracker, Observation]:
    tracker = FormTransactionTracker()
    comment = _element(
        "comment",
        scope=COMMENT_SCOPE,
        editable=True,
        role="textbox",
    )
    send = _element("send", scope=COMMENT_SCOPE)
    search = _element(
        "search",
        scope="body > header > form",
        editable=True,
        role="searchbox",
    )
    before = _obs(comment, send, search)
    after = _obs({**comment, "value": "准备提交的内容"}, send, search)
    tracker.record_fill(
        args={"ref": "comment", "value": "准备提交的内容"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=before,
        after=after,
    )
    return tracker, after


def test_confirmed_fill_blocks_another_form_scope() -> None:
    tracker, observation = _lock_comment_scope()

    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_fill", args={"ref": "search", "value": "next query"}),
        observation,
    )

    assert blocker is not None
    assert blocker.target_scope.endswith("body > header > form")


def test_active_scope_allows_its_submit_control() -> None:
    tracker, observation = _lock_comment_scope()

    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_click", args={"ref": "send"}),
        observation,
    )

    assert blocker is None


def test_outer_form_scope_allows_its_same_origin_iframe_editor() -> None:
    tracker = FormTransactionTracker()
    outer_scope = "0:body > main > form"
    title = _element(
        "title",
        scope="body > main > form",
        editable=True,
        role="textbox",
    )
    body = {
        "ref": "body",
        "role": "textbox",
        "editable": True,
        "visible": True,
        "selector": "body",
        "frameDepth": 1,
        "frameHostScopeIds": [outer_scope],
        "scopeId": "1:body > main",
        "scopeSelector": "body > main",
        "scopeLockable": False,
        "value": "",
    }
    before = _obs(title, body)
    after = _obs({**title, "value": "文章标题"}, body)
    tracker.record_fill(
        args={"ref": "title", "value": "文章标题"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=before,
        after=after,
    )

    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_fill", args={"ref": "body", "value": "文章正文"}),
        after,
    )

    assert blocker is None


def test_unrelated_iframe_editor_remains_blocked() -> None:
    tracker, observation = _lock_comment_scope()
    iframe_editor = {
        "ref": "iframe-editor",
        "role": "textbox",
        "editable": True,
        "visible": True,
        "selector": "body",
        "frameDepth": 1,
        "frameHostScopeIds": ["0:body > aside"],
    }
    observation.elements.append(iframe_editor)

    blocker = tracker.interaction_scope_blocker(
        Decision(
            tool="browser_fill",
            args={"ref": "iframe-editor", "value": "other"},
        ),
        observation,
    )

    assert blocker is not None


def test_iframe_editor_scope_allows_outer_form_submit_after_restore() -> None:
    outer_scope = "0:body > main > form"
    body = {
        "ref": "body",
        "role": "textbox",
        "editable": True,
        "visible": True,
        "selector": "body",
        "frameDepth": 1,
        "frameHostScopeIds": [outer_scope],
        "scopeId": "1:body > main",
        "scopeSelector": "body > main",
        "scopeLockable": False,
        "value": "",
    }
    publish = _element("publish", scope="body > main > form")
    before = _obs(body, publish)
    after = _obs({**body, "value": "文章正文"}, publish)
    tracker = FormTransactionTracker()
    tracker.record_fill(
        args={"ref": "body", "value": "文章正文"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=before,
        after=after,
    )
    restored = FormTransactionTracker()
    restored.restore_state(tracker.export_state())

    blocker = restored.interaction_scope_blocker(
        Decision(tool="browser_click", args={"ref": "publish"}),
        after,
    )

    assert blocker is None


def test_iframe_editor_allows_outer_transaction_action_in_shared_component() -> None:
    editor_component = "body > main > div.editor-shell"
    editor_form = f"{editor_component} > section > form"
    body = {
        "ref": "body",
        "role": "textbox",
        "editable": True,
        "visible": True,
        "selector": "html > body",
        "frameDepth": 1,
        "frameHostScopeIds": [f"0:{editor_form}"],
        "scopeLockable": False,
        "value": "",
    }
    save = {
        "ref": "save",
        "role": "button",
        "editable": False,
        "visible": True,
        "selector": f"{editor_component} > footer > button",
        "frameDepth": 0,
        "scopeSelector": editor_component,
        "scopeLockable": False,
        "componentOwnerSelector": editor_component,
        "componentOwnerAssociable": False,
        "componentOwnerFormCount": 2,
    }
    assistant = {
        "ref": "assistant",
        "role": "button",
        "editable": False,
        "visible": True,
        "selector": "body > aside > form.assistant > button",
        "frameDepth": 0,
        "scopeId": "0:body > aside > form.assistant",
        "scopeSelector": "body > aside > form.assistant",
        "scopeLockable": True,
        "formOwnerSelector": "body > aside > form.assistant",
    }
    before = _obs(body, save, assistant)
    after = _obs({**body, "value": "文章正文"}, save, assistant)
    tracker = FormTransactionTracker()
    tracker.record_fill(
        args={"ref": "body", "value": "文章正文"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=before,
        after=after,
    )

    assert tracker.interaction_scope_blocker(
        Decision(tool="browser_click", args={"ref": "save"}),
        after,
    ) is None
    assert tracker.interaction_scope_blocker(
        Decision(tool="browser_click", args={"ref": "assistant"}),
        after,
    ) is not None
    state = tracker.interaction_scope_state(after)
    assert state is not None
    assert "save" in state["allowed_refs"]
    assert "assistant" not in state["allowed_refs"]


def test_active_scope_allows_aria_owned_portal_option() -> None:
    tracker, observation = _lock_comment_scope()
    option = {
        **_element("suggestion", scope="#search-popup", role="option"),
        "associatedFieldSelectors": ["#comment"],
    }
    observation.elements.append(option)

    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_click", args={"ref": "suggestion"}),
        observation,
    )
    state = tracker.interaction_scope_state(observation)

    assert blocker is None
    assert state is not None
    assert "suggestion" in state["allowed_refs"]


def test_key_press_requires_focus_inside_active_scope() -> None:
    tracker, observation = _lock_comment_scope()
    observation.elements[0]["focused"] = True

    allowed = tracker.interaction_scope_blocker(
        Decision(tool="browser_press", args={"key": "Enter"}),
        observation,
    )
    observation.elements[0]["focused"] = False
    observation.elements[2]["focused"] = True
    blocked = tracker.interaction_scope_blocker(
        Decision(tool="browser_press", args={"key": "Enter"}),
        observation,
    )

    assert allowed is None
    assert blocked is not None


def test_hidden_browser_press_is_bound_to_the_current_form_field() -> None:
    tracker, observation = _lock_comment_scope()

    decision = tracker.bind_interaction_target(
        Decision(tool="browser_press", args={"key": "Enter"}),
        observation,
    )

    assert decision.args["ref"] == "comment"
    assert tracker.interaction_scope_blocker(decision, observation) is None


def test_active_scope_exposes_only_related_refs_to_planner() -> None:
    tracker, observation = _lock_comment_scope()

    state = tracker.interaction_scope_state(observation)

    assert state is not None
    assert state["allowed_refs"] == ["comment", "send"]
    assert "search" not in state["constraint"]


def test_active_scope_allows_a_control_on_an_ancestor_container() -> None:
    tracker, observation = _lock_comment_scope()
    close = _element("close", scope="body > main > dialog")
    observation.elements.append(close)

    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_click", args={"ref": "close"}),
        observation,
    )

    assert blocker is None


def test_navigation_releases_scope_for_the_next_form() -> None:
    tracker, before = _lock_comment_scope()
    search = _element(
        "search",
        scope="body > header > form",
        editable=True,
        role="searchbox",
    )
    after = _obs(search, url="https://example.test/search")
    tracker.after_action(
        Decision(tool="browser_navigate", args={"url": after.url}),
        before=before,
        after=after,
        ok=True,
    )

    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_fill", args={"ref": "search", "value": "next query"}),
        after,
    )

    assert blocker is None


def test_vanished_child_scope_is_not_kept_alive_by_ancestor_control() -> None:
    tracker, observation = _lock_comment_scope()
    close = _element("close", scope="body > main > dialog")
    current = _obs(close)

    tracker.reconcile(current)
    state = tracker.interaction_scope_state(current)

    assert state is None


def test_confirmed_effect_releases_scope() -> None:
    tracker, observation = _lock_comment_scope()
    tracker.after_effect(
        EffectReceipt(
            contract_key="effect-1",
            status="confirmed_success",
            action_name="commit",
        ),
        observation,
    )

    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_fill", args={"ref": "search", "value": "next query"}),
        observation,
    )

    assert blocker is None


def test_field_without_scope_metadata_does_not_create_a_lock() -> None:
    tracker = FormTransactionTracker()
    field = {
        "ref": "field",
        "role": "textbox",
        "editable": True,
        "visible": True,
        "selector": "#field",
        "value": "",
    }
    observation = _obs(field)
    tracker.record_fill(
        args={"ref": "field", "value": "content"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=observation,
        after=_obs({**field, "value": "content"}),
    )

    other = _element("other", scope="body > aside", editable=True, role="textbox")
    current = _obs(field, other)
    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_fill", args={"ref": "other", "value": "other"}),
        current,
    )

    assert blocker is None


def test_page_level_scope_marked_unlockable_does_not_create_a_lock() -> None:
    tracker = FormTransactionTracker()
    page_search = {
        **_element("search", scope="#app", editable=True, role="searchbox"),
        "scopeKind": "inferred",
        "scopeLockable": False,
        "scopeViewportCoverage": 1.0,
    }
    before = _obs(page_search)
    after = _obs({**page_search, "value": "员工服务台"})
    tracker.record_fill(
        args={"ref": "search", "value": "员工服务台"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=before,
        after=after,
    )
    detail_action = _element("open-detail", scope="body > main > article")

    blocker = tracker.interaction_scope_blocker(
        Decision(tool="browser_click", args={"ref": "open-detail"}),
        _obs(page_search, detail_action),
    )

    assert blocker is None


def test_planner_ledger_pins_active_form_refs(monkeypatch) -> None:
    captured = {}

    def fake_compact(observation, *, goal, target, pinned_refs):
        captured["pinned_refs"] = set(pinned_refs or set())
        return {"url": observation.url, "elements": []}

    monkeypatch.setattr(browser_planner, "compact_observation", fake_compact)
    observation = _obs(
        _element("comment", scope=COMMENT_SCOPE, editable=True, role="textbox"),
        _element("send", scope=COMMENT_SCOPE),
    )

    browser_planner._build_user_turn(
        "发表评论",
        [],
        observation,
        state_ledger={"pinned_refs": ["comment", "send"]},
    )

    assert captured["pinned_refs"] == {"comment", "send"}
