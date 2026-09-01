from __future__ import annotations

from app.enterprise_capabilities.browser.engine.business_site_scope import (
    resolve_business_site_scope,
    resolve_site_from_history,
    scope_node,
)
from app.enterprise_capabilities.browser.engine.form_input.input_context import BrowserInputContext
from app.enterprise_capabilities.browser.engine.workflow_cache.identity import build_workflow_identity
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation, StepRecord


def _node(goal: str, *, scope: str = "") -> CapabilityTask:
    meta = {"capability_id": "browser.publish_or_submit"}
    if scope:
        meta["browser_site_scope"] = scope
    return CapabilityTask(
        node_id="publish",
        goal=goal,
        assigned_agent="agent.browser",
        meta=meta,
    )


def test_resolves_business_destination_in_multi_url_request() -> None:
    request = (
        "https://static.example.com/assets/cover.png请下载这个图片，然后浏览器打开"
        "https://writer.example.com，填写文章并保存草稿"
    )

    resolved = resolve_business_site_scope(
        _node("在内容后台新建并保存草稿"),
        original_request=request,
    )

    assert resolved.site_id == "writer.example.com"
    assert resolved.source == "original_request"


def test_resolves_bare_business_domain_after_resource_url() -> None:
    request = (
        "https://static.example.com/assets/cover.png请下载这个图片，然后浏览器打开"
        "writer.example.com，填写文章并保存草稿"
    )

    resolved = resolve_business_site_scope(
        _node("在内容后台新建并保存草稿"),
        original_request=request,
    )

    assert resolved.site_id == "writer.example.com"


def test_explicit_planner_scope_wins_over_resource_urls() -> None:
    resolved = resolve_business_site_scope(
        _node("保存草稿", scope="https://portal.example.com/editor"),
        original_request="下载 https://cdn.example.net/a.png",
    )

    assert resolved.site_id == "portal.example.com"
    assert resolved.source == "planner"


def test_named_site_profile_resolves_request_without_url() -> None:
    resolved = resolve_business_site_scope(
        _node("发布文章"),
        original_request="请到内容运营系统发布文章",
        visible_sites=[{
            "name": "内容运营系统",
            "entry_url": "https://cms.example.internal/login",
        }],
    )

    assert resolved.site_id == "cms.example.internal"
    assert resolved.source == "site_profile"


def test_ambiguous_operation_sites_fail_open() -> None:
    resolved = resolve_business_site_scope(
        _node("处理浏览器任务"),
        original_request="访问 https://one.example.com 然后访问 https://two.example.com",
    )

    assert resolved.site_id == ""


def test_identity_uses_resolved_business_site_when_node_scope_is_missing() -> None:
    request = (
        "下载 https://cdn.example.com/a.png，然后浏览器打开 "
        "https://publisher.example.com 保存文章草稿"
    )
    identity = build_workflow_identity(
        user_id="u1",
        main_id="m1",
        node=_node("新建并保存文章草稿"),
        input_context=BrowserInputContext(original_request=request, candidates=[]),
    )

    assert identity is not None
    assert identity.site_id == "publisher.example.com"
    assert identity.operation_id == "article.save_draft"


def test_successful_trace_supplies_last_resort_site_for_capture() -> None:
    history = [
        StepRecord(
            observation=Observation(url="https://cdn.example.com/a.png", title="resource", elements=[]),
            decision=Decision(tool="browser_navigate", args={"url": "https://cdn.example.com/a.png"}),
            ok=True,
        ),
        StepRecord(
            observation=Observation(url="https://publisher.example.com/editor", title="editor", elements=[]),
            decision=Decision(tool="browser_fill", args={"ref": "title", "value": "test"}),
            ok=True,
        ),
        StepRecord(
            observation=Observation(url="https://publisher.example.com/drafts", title="drafts", elements=[]),
            decision=Decision(tool="browser_click", args={"ref": "save"}),
            ok=True,
        ),
    ]

    resolution = resolve_site_from_history(history)
    enriched = scope_node(_node("保存草稿"), resolution)

    assert resolution.site_id == "publisher.example.com"
    assert enriched.meta["browser_site_scope"] == "publisher.example.com"
    assert enriched.meta["browser_site_scope_source"] == "successful_trace"
