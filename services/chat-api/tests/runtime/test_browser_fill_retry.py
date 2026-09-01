from app.enterprise_capabilities.browser.engine.form_input.fill_retry import FillRetryPolicy
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _obs(value: str, *, ref: str = "e11", placeholder: str = "动态热点") -> Observation:
    return Observation(
        url="https://example.test",
        title="test",
        elements=[{
            "ref": ref, "role": "combobox", "tag": "input", "type": "text",
            "selector": "#search", "placeholder": placeholder, "editable": True,
            "value": value,
        }],
    )


def test_transient_fill_failure_retries_same_field_with_a_bound() -> None:
    policy = FillRetryPolicy(max_retries=2)
    decision = Decision(
        tool="browser_fill",
        args={"ref": "e11", "value": "员工服务台", "domain": "example.test"},
        rationale="fill search",
    )

    first = policy.after_result(decision, ok=False, error="target_not_focused", before=_obs(""))
    retry_one = policy.after_observation(_obs("", ref="e7", placeholder="另一个热点"))
    second = policy.after_result(retry_one, ok=False, error="Browser is under human control", before=_obs("", ref="e7"))
    retry_two = policy.after_observation(_obs("", ref="e8"))
    third = policy.after_result(retry_two, ok=False, error="target_not_focused", before=_obs("", ref="e8"))

    assert first is not None and first.tool == "browser_observe"
    assert retry_one is not None and retry_one.args["ref"] == "e7"
    assert second is not None and second.tool == "browser_observe"
    assert retry_two is not None and retry_two.args["ref"] == "e8"
    assert third is None
    assert policy.assistance_required(
        retry_two,
        error="target_not_focused",
        before=_obs("", ref="e8"),
    )


def test_non_retryable_fill_failure_does_not_request_human_assistance() -> None:
    policy = FillRetryPolicy(max_retries=1)
    fill = Decision(tool="browser_fill", args={"ref": "e11", "value": "x"})

    assert policy.after_result(
        fill,
        ok=False,
        error="agent disconnected",
        before=_obs(""),
    ) is None
    assert not policy.assistance_required(
        fill,
        error="agent disconnected",
        before=_obs(""),
    )


def test_success_clears_retry_budget_and_non_fill_is_ignored() -> None:
    policy = FillRetryPolicy(max_retries=1)
    fill = Decision(tool="browser_fill", args={"ref": "e1", "value": "x"}, rationale="")
    click = Decision(tool="browser_click", args={"ref": "e2"}, rationale="")

    assert policy.after_result(fill, ok=False, error="dispatch-error: timeout", before=_obs("", ref="e1")) is not None
    assert policy.after_observation(_obs("x", ref="e2")) is None
    assert policy.after_result(fill, ok=True, error=None) is None
    assert policy.after_result(fill, ok=False, error="dispatch-error: timeout", before=_obs("", ref="e1")) is not None
    assert policy.after_result(click, ok=False, error="dispatch-error: timeout") is None


def test_timeout_reconciliation_does_not_repeat_an_applied_fill() -> None:
    policy = FillRetryPolicy(max_retries=2)
    fill = Decision(tool="browser_fill", args={"ref": "e11", "value": "员工服务台"})

    observe = policy.after_result(
        fill,
        ok=False,
        error="dispatch-error: timeout",
        before=_obs("", placeholder="热点一"),
    )
    retry = policy.after_observation(_obs("员工服务台", ref="e3", placeholder="热点二"))

    assert observe is not None and observe.tool == "browser_observe"
    assert retry is None


def test_mismatched_non_empty_value_is_not_appended_again() -> None:
    policy = FillRetryPolicy(max_retries=2)
    fill = Decision(tool="browser_fill", args={"ref": "e11", "value": "AI助手"})

    observe = policy.after_result(
        fill,
        ok=False,
        error='value_not_applied: expected "AI助手", received "员工服务台AI助手"',
        before=_obs("员工服务台"),
    )
    retry = policy.after_observation(_obs("员工服务台AI助手", ref="e7"))

    assert observe is not None and observe.tool == "browser_observe"
    assert retry is None


def test_rich_text_reconciliation_does_not_retry_editor_normalization() -> None:
    policy = FillRetryPolicy(max_retries=2)
    before = _obs("")
    before.elements[0].update({
        "contentEditable": True,
        "contentEditableMode": "true",
        "tag": "div",
    })
    fill = Decision(
        tool="browser_fill",
        args={
            "ref": "e11",
            "value": "重复咨询\n就像灰犀牛\nAI员工服务台\n应运而生",
        },
    )
    observe = policy.after_result(
        fill,
        ok=False,
        error="value_not_applied: rich editor normalized the document",
        before=before,
    )
    current = _obs("重复咨询就像灰犀牛\n\nAI员工服务台应运而生", ref="e7")
    current.elements[0].update({
        "contentEditable": True,
        "contentEditableMode": "true",
        "tag": "div",
    })

    retry = policy.after_observation(current)

    assert observe is not None and observe.tool == "browser_observe"
    assert retry is None
