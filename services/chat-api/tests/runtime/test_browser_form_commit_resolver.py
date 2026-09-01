from app.enterprise_capabilities.browser.engine.form_input import (
    discover_fields,
    is_semantic_commit_control,
    resolve_form_commit,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


SCOPE = "0:body > dialog > article > footer"
SELECTOR = "body > dialog > article > footer"


def _element(ref, *, role="button", name="", value="", editable=False, disabled=False, required=False):
    return {
        "ref": ref,
        "role": role,
        "name": name,
        "value": value,
        "editable": editable,
        "visible": True,
        "hitTestable": True,
        "disabled": disabled,
        "required": required,
        "selector": f"#{ref}",
        "scopeId": SCOPE,
        "scopeSelector": SELECTOR,
        "scopeLockable": True,
        "frameDepth": 0,
        "tag": "textarea" if editable else "button",
    }


def _observation(*elements):
    return Observation(url="https://example.test/post", title="Post", elements=list(elements))


def _resolve(observation, *, observation_is_fresh=True):
    fields = discover_fields(observation)
    return resolve_form_commit(
        observation,
        fields=fields,
        mutated_field_keys={fields[0].field_key},
        observation_is_fresh=observation_is_fresh,
    )


def test_unique_send_wins_over_cancel_and_carousel_controls() -> None:
    observation = _observation(
        _element("comment", role="textbox", name="评论", value="有价值的评论", editable=True),
        _element("send", name="发送"),
        _element("cancel", name="取消"),
        _element("next", name="Next"),
    )

    resolution = _resolve(observation)

    assert resolution.kind == "click"
    assert resolution.decision.args == {"ref": "send"}


def test_disabled_commit_requests_one_fresh_observation() -> None:
    disabled = _observation(
        _element("comment", role="textbox", name="评论", value="内容", editable=True),
        {
            **_element("send-old", name="发送", disabled=True),
            "hitTestable": False,
        },
    )
    refreshed = _observation(
        _element("comment-new", role="textbox", name="评论", value="内容", editable=True),
        _element("send-new", name="发送"),
    )

    first = _resolve(disabled, observation_is_fresh=False)
    second = _resolve(refreshed, observation_is_fresh=True)

    assert first.kind == "refresh"
    assert first.decision.tool == "browser_observe"
    assert second.kind == "click"
    assert second.decision.args == {"ref": "send-new"}


def test_disabled_send_remains_structural_commit_evidence() -> None:
    send = {
        **_element("send", name="发送", disabled=True),
        "hitTestable": False,
    }
    cancel = _element("cancel", name="取消")

    assert is_semantic_commit_control(send) is False
    assert is_semantic_commit_control(send, require_hit_testable=False) is True
    assert is_semantic_commit_control(cancel) is False


def test_completed_status_is_not_treated_as_a_commit_control() -> None:
    observation = _observation(
        _element("comment", role="textbox", name="评论", value="内容", editable=True),
        _element("sent-folder", name="已发送"),
    )

    resolution = _resolve(observation)

    assert resolution.kind == "none"


def test_multiple_enabled_commit_controls_fall_back_to_planner() -> None:
    observation = _observation(
        _element("comment", role="textbox", name="评论", value="内容", editable=True),
        _element("send", name="发送"),
        _element("publish", name="发布"),
    )

    resolution = _resolve(observation)

    assert resolution.kind == "ambiguous"
    assert resolution.decision is None


def test_required_empty_field_prevents_atomic_commit() -> None:
    observation = _observation(
        _element("body", role="textbox", name="正文", value="内容", editable=True),
        _element("title", role="textbox", name="标题", value="", editable=True, required=True),
        _element("publish", name="发布"),
    )
    fields = discover_fields(observation)

    resolution = resolve_form_commit(
        observation,
        fields=fields,
        mutated_field_keys={fields[0].field_key},
        observation_is_fresh=True,
    )

    assert resolution.kind == "none"


def test_unique_commit_in_sibling_toolbar_is_resolved_from_shared_component() -> None:
    component = "body > main > article > div:nth-of-type(2)"
    field = {
        **_element(
            "answer",
            role="textbox",
            name="回答",
            value="正文",
            editable=True,
        ),
        "selector": f"{component} > form > div[contenteditable=true]",
        "scopeId": f"0:{component} > form",
        "scopeSelector": f"{component} > form",
        "formOwnerSelector": f"{component} > form",
        "componentOwnerSelector": component,
        "componentOwnerLockable": True,
    }
    submit = {
        **_element("publish-answer", name="发布回答"),
        "selector": f"{component} > footer > button",
        "scopeId": f"0:{component} > footer",
        "scopeSelector": f"{component} > footer",
        "componentOwnerSelector": component,
        "componentOwnerLockable": True,
        "fieldAssociationKind": "component",
    }
    observation = _observation(field, submit)
    fields = discover_fields(observation)

    resolution = resolve_form_commit(
        observation,
        fields=fields,
        mutated_field_keys={fields[0].field_key},
        observation_is_fresh=True,
    )

    assert resolution.kind == "click"
    assert resolution.decision is not None
    assert resolution.decision.args == {"ref": "publish-answer"}


def test_unique_commit_in_large_editor_toolbar_ignores_scope_action_limit() -> None:
    component = (
        "body > div:nth-of-type(1) > div > main > div > div "
        "> div:nth-of-type(2) > div > div > div > div:nth-of-type(2)"
    )
    form = f"{component} > form"
    field = {
        **_element(
            "answer",
            role="textbox",
            name="回答",
            value="正文",
            editable=True,
        ),
        "selector": f"{form} > div > div[contenteditable=true]",
        "scopeId": f"0:{form}",
        "scopeSelector": form,
        "formOwnerSelector": form,
        "componentOwnerSelector": component,
        "componentOwnerLockable": False,
        "componentOwnerAssociable": True,
        "componentOwnerFormCount": 1,
        "scopeActionCount": 27,
    }
    submit = {
        **_element("publish-answer", name="发布回答"),
        "selector": f"{component} > div > footer > button:nth-of-type(2)",
        "scopeId": f"0:{component}",
        "scopeSelector": component,
        "scopeLockable": False,
        "componentOwnerSelector": component,
        "componentOwnerLockable": False,
        "componentOwnerAssociable": True,
        "componentOwnerFormCount": 1,
        "scopeActionCount": 32,
        "fieldAssociationKind": "component",
    }
    observation = _observation(field, submit)
    fields = discover_fields(observation)

    resolution = resolve_form_commit(
        observation,
        fields=fields,
        mutated_field_keys={fields[0].field_key},
        observation_is_fresh=True,
    )

    assert resolution.kind == "click"
    assert resolution.decision is not None
    assert resolution.decision.args == {"ref": "publish-answer"}
