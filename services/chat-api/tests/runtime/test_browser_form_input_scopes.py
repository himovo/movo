import asyncio
from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.drivers.base import BrowserDriver
from app.enterprise_capabilities.browser.engine.drivers.form_input import FormInputDriver
from app.enterprise_capabilities.browser.engine.form_input import (
    BrowserInputContext,
    FieldBinding,
    InputCandidate,
)
from app.enterprise_capabilities.browser.engine.form_input.inventory import discover_fields
from app.enterprise_capabilities.browser.engine.form_input.readiness import ready_business_form_scopes
from app.enterprise_capabilities.browser.engine.form_input.scopes import element_scope_id
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision,
    Observation,
    StepRecord,
)


OUTER_FORM_SCOPE = "0:body > main > form"


class _Fallback(BrowserDriver):
    def __init__(self, decision: Optional[Decision] = None) -> None:
        self.decision = decision or Decision(
            tool="browser_observe",
            rationale="fallback",
        )
        self.last_state_ledger: Optional[Dict[str, Any]] = None

    @property
    def kind(self) -> str:
        return "test"

    async def next_step(
        self,
        goal: str,
        history: List[StepRecord],
        observation: Observation,
        state_ledger: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        del goal, history, observation
        self.last_state_ledger = state_ledger
        return self.decision


class _GoalResolver:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.task_goal = ""

    async def resolve(self, **kwargs) -> List[FieldBinding]:
        self.task_goal = str(kwargs.get("task_goal") or "")
        fields = list(kwargs.get("fields") or [])
        if not self.value or not fields:
            return []
        field = next(
            (item for item in fields if item.control_kind == "rich_text"),
            fields[0],
        )
        return [
            FieldBinding(
                field_key=field.field_key,
                action="fill",
                source_kind="transform",
                value=self.value,
                confidence=0.95,
                rationale="current browser node supplied the body",
            )
        ]


class _SkipResolver:
    async def resolve(self, **kwargs) -> List[FieldBinding]:
        return [
            FieldBinding(
                field_key=field.field_key,
                action="skip",
                source_kind="unknown",
                confidence=0.9,
                rationale="model considered the field optional",
            )
            for field in list(kwargs.get("fields") or [])
        ]


def _unlabelled_article_editor(
    *,
    title_value: str = "",
    body_value: str = "",
) -> Observation:
    return Observation(
        url="https://publisher.example.test/edit",
        title="Editor",
        elements=[
            {
                "ref": "title",
                "role": "textbox",
                "name": "",
                "tag": "div",
                "contentEditable": True,
                "editable": True,
                "visible": True,
                "value": title_value,
                "scopeId": OUTER_FORM_SCOPE,
                "scopeRole": "form",
                "scopeLockable": True,
                "frameDepth": 0,
                "width": 640,
                "height": 39,
            },
            {
                "ref": "body",
                "role": "textbox",
                "name": "",
                "tag": "body",
                "contentEditable": True,
                "editable": True,
                "visible": True,
                "value": body_value,
                "scopeId": "1:html > body",
                "scopeLockable": False,
                "frameHostScopeIds": [OUTER_FORM_SCOPE],
                "frameDepth": 1,
                "width": 688,
                "height": 590,
            },
            {
                "ref": "save",
                "role": "button",
                "name": "保存草稿",
                "tag": "button",
                "visible": True,
                "scopeId": OUTER_FORM_SCOPE,
                "scopeRole": "form",
                "scopeLockable": True,
                "frameDepth": 0,
            },
        ],
    )


def _confirmed_paste(observation: Observation) -> Observation:
    observation.diagnostics = {
        "mediaInsert": {
            "status": "confirmed",
            "method": "paste",
            "mediaCountBefore": 0,
            "mediaCountAfter": 1,
        },
    }
    return observation


def test_non_lockable_iframe_editor_inherits_nearest_host_form_scope() -> None:
    editor = {
        "scopeId": "1:html > body",
        "scopeLockable": False,
        "frameDepth": 1,
        "frameHostScopeIds": [
            "0:body > main",
            OUTER_FORM_SCOPE,
        ],
    }

    assert element_scope_id(editor) == OUTER_FORM_SCOPE


def test_lockable_iframe_form_keeps_its_own_explicit_scope() -> None:
    editor = {
        "scopeId": "1:html > body > form",
        "scopeLockable": True,
        "frameDepth": 1,
        "frameHostScopeIds": [OUTER_FORM_SCOPE],
    }

    assert element_scope_id(editor) == "1:html > body > form"


def test_outer_title_and_iframe_body_form_one_ready_publish_scope() -> None:
    observation = Observation(
        url="https://publisher.example.test/edit",
        title="Editor",
        elements=[
            {
                "ref": "title",
                "role": "textbox",
                "name": "标题",
                "tag": "input",
                "editable": True,
                "visible": True,
                "scopeId": OUTER_FORM_SCOPE,
                "scopeRole": "form",
                "scopeLockable": True,
                "frameDepth": 0,
            },
            {
                "ref": "body",
                "role": "textbox",
                "name": "正文",
                "tag": "body",
                "contentEditable": True,
                "editable": True,
                "visible": True,
                "scopeId": "1:html > body",
                "scopeLockable": False,
                "frameHostScopeIds": [OUTER_FORM_SCOPE],
                "frameDepth": 1,
                "width": 700,
                "height": 500,
            },
            {
                "ref": "save",
                "role": "button",
                "name": "保存",
                "tag": "button",
                "visible": True,
                "scopeId": OUTER_FORM_SCOPE,
                "scopeRole": "form",
                "scopeLockable": True,
                "frameDepth": 0,
            },
        ],
    )

    fields = discover_fields(observation)
    ready = ready_business_form_scopes(observation, fields)

    assert set(ready) == {OUTER_FORM_SCOPE}
    assert [field.ref for field in ready[OUTER_FORM_SCOPE]] == ["title", "body"]


def test_unlabelled_short_title_and_large_iframe_editor_get_structural_roles() -> None:
    fields = discover_fields(_unlabelled_article_editor())

    assert [(field.ref, field.semantic_role) for field in fields] == [
        ("title", "title"),
        ("body", "body"),
    ]


def test_compact_unlabelled_comment_editor_is_not_promoted_to_article_fields() -> None:
    fields = discover_fields(Observation(
        url="https://community.example.test/post/1",
        title="Comment",
        elements=[{
            "ref": "comment",
            "role": "textbox",
            "name": "",
            "tag": "div",
            "contentEditable": True,
            "editable": True,
            "visible": True,
            "scopeId": "0:#comment-form",
            "scopeRole": "form",
            "scopeLockable": True,
            "frameDepth": 0,
            "width": 560,
            "height": 48,
        }],
    ))

    assert len(fields) == 1
    assert fields[0].semantic_role == ""


def test_unrelated_iframe_editor_does_not_join_publish_form_scope() -> None:
    editor = {
        "scopeLockable": False,
        "frameDepth": 1,
        "frameHostScopeIds": ["0:body > aside > form"],
    }

    assert element_scope_id(editor) == "0:body > aside > form"


def test_iframe_body_is_filled_before_clipboard_image_is_pasted() -> None:
    def editor(body_value: str) -> Observation:
        return Observation(
            url="https://publisher.example.test/edit",
            title="Editor",
            elements=[
                {
                    "ref": "title",
                    "role": "textbox",
                    "name": "标题",
                    "tag": "input",
                    "editable": True,
                    "visible": True,
                    "value": "测试标题",
                    "scopeId": OUTER_FORM_SCOPE,
                    "scopeRole": "form",
                    "scopeLockable": True,
                    "frameDepth": 0,
                },
                {
                    "ref": "body",
                    "role": "textbox",
                    "name": "",
                    "tag": "body",
                    "contentEditable": True,
                    "editable": True,
                    "visible": True,
                    "value": body_value,
                    "scopeId": "1:html > body",
                    "scopeLockable": False,
                    "frameHostScopeIds": [OUTER_FORM_SCOPE],
                    "frameDepth": 1,
                    "width": 700,
                    "height": 500,
                },
            ],
        )

    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="填写正文，然后把图片复制粘贴到正文",
            candidates=[
                InputCandidate(
                    "body-input",
                    "upstream",
                    "publish_payload.body",
                    "body",
                    "测试正文",
                ),
                InputCandidate(
                    "image-input",
                    "upstream",
                    "resources.images",
                    "images",
                    ["https://assets.example.test/image.png"],
                    value_kind="file",
                ),
            ],
        ),
        capability_id="browser.publish",
    )

    fill = asyncio.run(driver.next_step("发布图文", [], editor("")))
    assert fill.tool == "browser_fill"
    assert fill.args["ref"] == "body"
    assert fill.args["value"] == "测试正文"

    filled = editor("测试正文")
    driver.on_step_completed(fill, True, filled)
    paste = asyncio.run(driver.next_step("发布图文", [], filled))

    assert paste.tool == "browser_paste_image"
    assert paste.args["editor_ref"] == "body"


def test_current_browser_goal_can_bind_body_before_media() -> None:
    observation = Observation(
        url="https://publisher.example.test/edit",
        title="Editor",
        elements=[
            {
                "ref": "title",
                "role": "textbox",
                "name": "标题",
                "tag": "input",
                "editable": True,
                "visible": True,
                "value": "节点目标中的标题",
                "scopeId": OUTER_FORM_SCOPE,
                "scopeRole": "form",
                "scopeLockable": True,
            },
            {
                "ref": "body",
                "role": "textbox",
                "name": "",
                "tag": "body",
                "contentEditable": True,
                "editable": True,
                "visible": True,
                "value": "",
                "scopeId": OUTER_FORM_SCOPE,
                "scopeRole": "form",
                "scopeLockable": True,
                "width": 700,
                "height": 500,
            },
        ],
    )
    resolver = _GoalResolver("节点目标中的正文")
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="把下载图片复制到编辑器并保存",
            candidates=[
                InputCandidate(
                    "image-input",
                    "upstream",
                    "resources.images",
                    "images",
                    ["https://assets.example.test/image.png"],
                    value_kind="file",
                ),
            ],
        ),
        capability_id="browser.publish",
        model_resolver=resolver,
    )

    decision = asyncio.run(driver.next_step(
        "在正文富文本编辑器填写“节点目标中的正文”，然后粘贴图片",
        [],
        observation,
    ))

    assert decision.tool == "browser_fill"
    assert decision.args == {"ref": "body", "value": "节点目标中的正文"}
    assert "节点目标中的正文" in resolver.task_goal


def test_unresolved_body_blocks_media_mutation_from_fallback() -> None:
    fallback = _Fallback(Decision(
        tool="browser_paste_image",
        args={
            "editor_ref": "body",
            "sources": ["https://assets.example.test/image.png"],
        },
        rationale="model attempted media before body",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="先填写正文，再复制图片",
            candidates=[
                InputCandidate(
                    "image-input",
                    "upstream",
                    "resources.images",
                    "images",
                    ["https://assets.example.test/image.png"],
                    value_kind="file",
                ),
            ],
        ),
        capability_id="browser.publish",
        model_resolver=_GoalResolver(),
    )
    observation = Observation(
        url="https://publisher.example.test/edit",
        title="Editor",
        elements=[
            {
                "ref": "title",
                "role": "textbox",
                "name": "标题",
                "tag": "input",
                "editable": True,
                "visible": True,
                "value": "测试标题",
                "scopeId": OUTER_FORM_SCOPE,
                "scopeRole": "form",
                "scopeLockable": True,
            },
            {
                "ref": "body",
                "role": "textbox",
                "name": "正文",
                "tag": "div",
                "contentEditable": True,
                "editable": True,
                "visible": True,
                "value": "",
                "scopeId": OUTER_FORM_SCOPE,
                "scopeRole": "form",
                "scopeLockable": True,
                "width": 700,
                "height": 500,
            },
        ],
    )

    decision = asyncio.run(driver.next_step(
        "填写正文后粘贴图片",
        [],
        observation,
    ))

    assert decision.tool == "browser_observe"
    assert fallback.last_state_ledger["form_input_phase"] == "fields_before_media"
    assert fallback.last_state_ledger["pending_form_field_count"] == 1


def test_model_skip_cannot_release_requested_article_fields_before_media() -> None:
    fallback = _Fallback(Decision(
        tool="browser_paste_image",
        args={
            "editor_ref": "body",
            "sources": ["https://assets.example.test/image.png"],
        },
        rationale="model attempted media before article text",
    ))
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="填写标题和正文，再把图片复制到正文",
            candidates=[
                InputCandidate(
                    "image-input",
                    "upstream",
                    "resources.images",
                    "images",
                    ["https://assets.example.test/image.png"],
                    value_kind="file",
                ),
            ],
        ),
        capability_id="browser.publish",
        model_resolver=_SkipResolver(),
    )

    decision = asyncio.run(driver.next_step(
        "填写标题和正文，再粘贴图片",
        [],
        _unlabelled_article_editor(),
    ))

    assert decision.tool == "browser_observe"
    assert fallback.last_state_ledger["form_input_phase"] == "fields_before_media"
    assert {
        item["label"]
        for item in fallback.last_state_ledger["pending_form_fields"]
    } == {"title", "body"}


def test_generated_article_text_is_filled_before_its_image() -> None:
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=BrowserInputContext(
            original_request="把生成的图文文章和配图复制到当前编辑器",
            candidates=[
                InputCandidate(
                    "article-title",
                    "upstream",
                    "publish_payload.title",
                    "title",
                    "生成文章标题",
                ),
                InputCandidate(
                    "article-body",
                    "upstream",
                    "publish_payload.body",
                    "body",
                    "生成文章正文",
                    value_kind="rich_text",
                    plain_text="生成文章正文",
                    rich_html="<p>生成文章正文</p>",
                ),
                InputCandidate(
                    "article-image",
                    "upstream",
                    "publish_payload.media.0",
                    "media",
                    ["https://assets.example.test/image.png"],
                    value_kind="file",
                ),
            ],
        ),
        capability_id="browser.publish",
    )

    empty = _unlabelled_article_editor()
    title = asyncio.run(driver.next_step("发布生成的图文文章", [], empty))
    assert title.tool == "browser_fill"
    assert title.args == {"ref": "title", "value": "生成文章标题"}

    title_filled = _unlabelled_article_editor(title_value="生成文章标题")
    driver.on_step_completed(title, True, title_filled)
    body = asyncio.run(driver.next_step("发布生成的图文文章", [], title_filled))
    assert body.tool == "browser_fill"
    assert body.args == {
        "ref": "body",
        "value": "生成文章正文",
        "rich_html": "<p>生成文章正文</p>",
    }

    article_filled = _unlabelled_article_editor(
        title_value="生成文章标题",
        body_value="生成文章正文",
    )
    driver.on_step_completed(body, True, article_filled)
    image = asyncio.run(driver.next_step(
        "发布生成的图文文章",
        [],
        article_filled,
    ))
    assert image.tool == "browser_paste_image"
    assert image.args["editor_ref"] == "body"


def test_body_replacement_requeues_media_inserted_in_that_editor() -> None:
    fallback = _Fallback()
    driver = FormInputDriver(
        fallback=fallback,
        input_context=BrowserInputContext(
            original_request="先粘贴图片，然后修改正文，暂时不要提交",
            candidates=[
                InputCandidate(
                    "article-image",
                    "upstream",
                    "publish_payload.media.0",
                    "media",
                    ["https://assets.example.test/image.png"],
                    value_kind="file",
                ),
            ],
        ),
        capability_id="browser.publish",
    )
    before = _unlabelled_article_editor(
        title_value="测试标题",
        body_value="旧正文",
    )

    first_image = asyncio.run(driver.next_step("编辑图文", [], before))
    assert first_image.tool == "browser_paste_image"
    driver.on_step_completed(first_image, True, _confirmed_paste(before))

    fallback.decision = Decision(
        tool="browser_fill",
        args={"ref": "body", "value": "新正文"},
        rationale="replace the article body",
    )
    replacement = asyncio.run(driver.next_step("编辑图文", [], before))
    assert replacement.tool == "browser_fill"

    replaced = _unlabelled_article_editor(
        title_value="测试标题",
        body_value="新正文",
    )
    driver.on_step_completed(replacement, True, replaced)
    second_image = asyncio.run(driver.next_step("编辑图文", [], replaced))

    assert second_image.tool == "browser_paste_image"
    assert second_image.args["sources"] == [
        "https://assets.example.test/image.png",
    ]
