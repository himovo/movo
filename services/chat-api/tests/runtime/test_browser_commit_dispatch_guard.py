from app.enterprise_capabilities.browser.engine.form_input.commit_dispatch_guard import guard_dirty_form_commit
from app.enterprise_capabilities.browser.engine.form_input.commit_binding import commit_control_key
from app.enterprise_capabilities.browser.engine.form_input.contracts import FieldDescriptor
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _field(
    scope: str,
    *,
    selector: str = "",
    role: str = "",
    lockable: bool | None = None,
) -> FieldDescriptor:
    raw = {
        "scopeId": scope,
        "scopeSelector": scope,
        "selector": selector,
        "scopeRole": role,
    }
    if lockable is not None:
        raw["scopeLockable"] = lockable
    return FieldDescriptor(
        field_key="body",
        ref="body",
        control_kind="rich_text",
        current_value="draft",
        raw=raw,
    )


def test_out_of_scope_publish_navigation_is_not_a_dirty_form_commit() -> None:
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[{
            "ref": "publish-nav",
            "role": "button",
            "name": "发布",
            "text": "发布",
            "visible": True,
            "hitTestable": True,
            "scopeId": "#navigation",
            "scopeSelector": "#navigation",
        }],
    )

    guarded = guard_dirty_form_commit(
        decision=Decision(tool="browser_click", args={"ref": "publish-nav"}),
        observation=observation,
        fields=[_field("#editor")],
        mutated_field_keys={"body"},
    )

    assert guarded.decision is not None
    assert guarded.decision.tool == "browser_observe"


def test_form_owned_submit_remains_dispatchable() -> None:
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[{
            "ref": "submit",
            "role": "button",
            "name": "发布",
            "text": "发布",
            "visible": True,
            "hitTestable": True,
            "scopeId": "#editor",
            "scopeSelector": "#editor",
        }],
    )

    guarded = guard_dirty_form_commit(
        decision=Decision(tool="browser_click", args={"ref": "submit"}),
        observation=observation,
        fields=[_field("#editor")],
        mutated_field_keys={"body"},
    )

    assert guarded.decision is None


def test_unlockable_editor_does_not_bind_main_publish_navigation() -> None:
    main = "body > div > main"
    editor = f"{main} > section:nth-of-type(2)"
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[{
            "ref": "submit",
            "role": "button",
            "name": "发布笔记",
            "text": "发布笔记",
            "visible": True,
            "hitTestable": True,
            "scopeId": f"0:{main}",
            "scopeSelector": main,
            "scopeRole": "main",
            "scopeLockable": False,
            "selector": f"{main} > nav > div:nth-of-type(1)",
        }],
    )

    guarded = guard_dirty_form_commit(
        decision=Decision(tool="browser_click", args={"ref": "submit"}),
        observation=observation,
        fields=[_field(
            f"0:{editor}",
            selector=f"{editor} > div[contenteditable=true]",
            role="div",
            lockable=False,
        )],
        mutated_field_keys={"body"},
    )

    assert guarded.decision is not None
    assert guarded.decision.tool == "browser_observe"


def test_unknown_unbound_commit_relationship_is_guarded() -> None:
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[{
            "ref": "submit",
            "role": "button",
            "name": "提交",
            "text": "提交",
            "visible": True,
            "hitTestable": True,
        }],
    )

    guarded = guard_dirty_form_commit(
        decision=Decision(tool="browser_click", args={"ref": "submit"}),
        observation=observation,
        fields=[_field("")],
        mutated_field_keys={"body"},
    )

    assert guarded.decision is not None
    assert guarded.decision.tool == "browser_observe"


def test_unknown_commit_relationship_is_allowed_after_causal_binding() -> None:
    target = {
        "ref": "submit",
        "selector": "#submit",
        "role": "button",
        "name": "提交",
        "text": "提交",
        "visible": True,
        "hitTestable": True,
    }
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[target],
    )

    guarded = guard_dirty_form_commit(
        decision=Decision(tool="browser_click", args={"ref": "submit"}),
        observation=observation,
        fields=[_field("")],
        mutated_field_keys={"body"},
        bound_action_keys={commit_control_key(target)},
    )

    assert guarded.decision is None


def test_commit_in_sibling_toolbar_is_allowed_for_shared_editor_component() -> None:
    component = "body > main > article > div:nth-of-type(2)"
    field = _field(
        f"0:{component} > form",
        selector=f"{component} > form > div[contenteditable=true]",
        role="form",
        lockable=True,
    )
    field.raw.update({
        "formOwnerSelector": f"{component} > form",
        "componentOwnerSelector": component,
        "componentOwnerLockable": True,
    })
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[{
            "ref": "submit",
            "selector": f"{component} > footer > button",
            "role": "button",
            "name": "发布回答",
            "text": "发布回答",
            "visible": True,
            "hitTestable": True,
            "componentOwnerSelector": component,
            "componentOwnerLockable": True,
            "fieldAssociationKind": "component",
            "frameDepth": 0,
        }],
    )

    guarded = guard_dirty_form_commit(
        decision=Decision(tool="browser_click", args={"ref": "submit"}),
        observation=observation,
        fields=[field],
        mutated_field_keys={"body"},
    )

    assert guarded.decision is None


def test_complex_editor_commit_is_not_blocked_by_toolbar_action_count() -> None:
    component = (
        "body > div:nth-of-type(1) > div > main > div > div "
        "> div:nth-of-type(2) > div > div > div > div:nth-of-type(2)"
    )
    form = f"{component} > form"
    field = _field(
        f"0:{form}",
        selector=f"{form} > div > div[contenteditable=true]",
        role="form",
        lockable=True,
    )
    field.raw.update({
        "formOwnerSelector": form,
        "componentOwnerSelector": component,
        "componentOwnerLockable": False,
        "componentOwnerAssociable": True,
        "componentOwnerFormCount": 1,
        "scopeActionCount": 27,
    })
    observation = Observation(
        url="https://example.test/question/1#write",
        title="Editor",
        page_text="",
        elements=[{
            "ref": "publish-answer",
            "selector": f"{component} > div > footer > button:nth-of-type(2)",
            "role": "button",
            "name": "发布回答",
            "text": "发布回答",
            "visible": True,
            "hitTestable": True,
            "componentOwnerSelector": component,
            "componentOwnerLockable": False,
            "componentOwnerAssociable": True,
            "componentOwnerFormCount": 1,
            "scopeActionCount": 32,
            "fieldAssociationKind": "component",
            "frameDepth": 0,
        }],
    )

    guarded = guard_dirty_form_commit(
        decision=Decision(
            tool="browser_click",
            args={"ref": "publish-answer"},
        ),
        observation=observation,
        fields=[field],
        mutated_field_keys={"body"},
    )

    assert guarded.decision is None
