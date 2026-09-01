import asyncio
import json
from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.action_resolution import resolve_wait_for_action
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _obs():
    return Observation(
        url="https://mail.example/compose",
        title="Mail",
        elements=[
            {"ref": "e5", "role": "textbox", "name": "主题"},
            {"ref": "e7", "role": "button", "name": "发送"},
            {"ref": "e8", "role": "button", "name": "发送并关闭"},
        ],
    )


def test_local_rule_match_returns_direct_click_without_llm():
    resolved = asyncio.run(resolve_wait_for_action(
        goal="发送邮件", query="发送", domain="mail.example", lang="zh", observation=_obs(),
        result={"matched": True, "resolution": "action_rule", "clickable_ref": "e7"},
        llm=SimpleNamespace(ainvoke_structured=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError())),
    ))
    assert resolved.source == "local_rule"
    assert resolved.decision.args["ref"] == "e7"


def test_field_rule_match_is_not_rewritten_into_a_click():
    resolved = asyncio.run(resolve_wait_for_action(
        goal="搜索学知网", query="搜索", domain="example.test", lang="zh", observation=_obs(),
        result={"matched": True, "resolution": "field_rule", "fillable_ref": "e5"},
        llm=SimpleNamespace(ainvoke_structured=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError())),
    ))
    assert resolved.decision is None
    assert resolved.source == "none"


class _Picker:
    def __init__(self, ref="e8", action="click"):
        self.ref = ref
        self.action = action
        self.user_payload = None

    async def ainvoke_structured(self, messages, schema):
        self.user_payload = json.loads(messages[1].content)
        return schema(action=self.action, selected_ref=self.ref, rationale="best candidate")


def test_model_only_sees_candidates_and_schema_limits_ref_values():
    picker = _Picker()
    resolved = asyncio.run(resolve_wait_for_action(
        goal="发送后关闭窗口", query="发送", domain="mail.example", lang="zh", observation=_obs(),
        result={
            "model_required": True,
            "candidates": [
                {"ref": "e7", "role": "button", "name": "发送"},
                {"ref": "e8", "role": "button", "name": "发送并关闭"},
            ],
        },
        llm=picker,
    ))
    assert resolved.source == "model_candidate"
    assert resolved.decision.args["ref"] == "e8"
    assert {item["ref"] for item in picker.user_payload["candidates"]} == {"e7", "e8"}
    assert "e5" not in json.dumps(picker.user_payload)


def test_unique_exact_action_candidate_is_selected_without_llm():
    resolved = asyncio.run(resolve_wait_for_action(
        goal="创建文章", query="文章", domain="mp.weixin.qq.com", lang="zh",
        observation=Observation(
            url="https://mp.weixin.qq.com/",
            title="微信公众平台",
            elements=[
                {"ref": "e10", "role": "menuitem", "name": "文章", "hitTestable": True},
                {"ref": "e11", "role": "menuitem", "name": "视频", "hitTestable": True},
            ],
        ),
        result={
            "model_required": True,
            "candidates": [
                {"ref": "e10", "role": "menuitem", "name": "文章"},
                {"ref": "e11", "role": "menuitem", "name": "视频"},
            ],
        },
        llm=SimpleNamespace(ainvoke_structured=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError())),
    ))
    assert resolved.source == "local_rule"
    assert resolved.decision.args["ref"] == "e10"


def test_duplicate_exact_action_candidates_remain_model_decision():
    picker = _Picker(ref="e12")
    resolved = asyncio.run(resolve_wait_for_action(
        goal="选择正确的文章入口", query="文章", domain="example.test", lang="zh",
        observation=Observation(
            url="https://example.test/",
            title="Example",
            elements=[
                {"ref": "e10", "role": "menuitem", "name": "文章"},
                {"ref": "e12", "role": "button", "name": "文章"},
            ],
        ),
        result={
            "model_required": True,
            "candidates": [
                {"ref": "e10", "role": "menuitem", "name": "文章"},
                {"ref": "e12", "role": "button", "name": "文章"},
            ],
        },
        llm=picker,
    ))
    assert resolved.source == "model_candidate"
    assert resolved.decision.args["ref"] == "e12"


def test_hidden_or_unverified_candidate_is_never_exposed_to_model():
    picker = _Picker(action="none", ref=None)
    resolved = asyncio.run(resolve_wait_for_action(
        goal="创建文章", query="文章", domain="example.test", lang="zh",
        observation=Observation(
            url="https://example.test/",
            title="Example",
            elements=[{"ref": "e10", "role": "menuitem", "name": "文章", "hitTestable": False}],
        ),
        result={
            "model_required": True,
            "candidates": [{"ref": "e10", "role": "menuitem", "name": "文章"}],
        },
        llm=picker,
    ))
    assert resolved.source == "none"
    assert picker.user_payload is None


def test_out_of_candidate_ref_is_rejected_even_if_provider_bypasses_schema():
    class BadPicker:
        async def ainvoke_structured(self, _messages, _schema):
            return SimpleNamespace(model_dump=lambda **_kwargs: {
                "action": "click", "selected_ref": "e5", "rationale": "invented",
            })

    resolved = asyncio.run(resolve_wait_for_action(
        goal="发送邮件", query="发送", domain="mail.example", lang="zh", observation=_obs(),
        result={"model_required": True, "candidates": [{"ref": "e7", "role": "button", "name": "发送"}]},
        llm=BadPicker(),
    ))
    assert resolved.decision is None


def test_dynamic_schema_rejects_ref_not_present_in_candidates():
    class SchemaPicker:
        async def ainvoke_structured(self, _messages, schema):
            return schema(action="click", selected_ref="e5", rationale="not offered")

    resolved = asyncio.run(resolve_wait_for_action(
        goal="发送邮件", query="发送", domain="mail.example", lang="zh", observation=_obs(),
        result={"model_required": True, "candidates": [{"ref": "e7", "role": "button", "name": "发送"}]},
        llm=SchemaPicker(),
    ))
    assert resolved.decision is None
    assert resolved.allowed_refs == ["e7"]
