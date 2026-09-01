from app.enterprise_capabilities.browser.engine.form_human_assistance import FORM_TASK_COMPLETION_CATEGORY
from app.enterprise_capabilities.browser.engine.human_assistance_policy import (
    READ_BUDGET,
    browser_human_assistance,
)
from app.enterprise_capabilities.browser.engine.recovery_router import (
    BROWSER_CONNECTION_LOST,
    INTERNAL_FAILURE,
    LOOP_EXHAUSTED,
    MODEL_FAILURE,
    OUTPUT_CONTRACT_EXHAUSTED,
    RESUME_RECONCILIATION_UNAVAILABLE,
    route_browser_recovery,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _observation(*, fresh: bool = True) -> Observation:
    return Observation(
        url="https://example.test/editor",
        title="Editor",
        elements=[{"ref": "button-1", "role": "button", "name": "Save"}],
        page_text="Draft editor",
        revision="r1",
        fresh=fresh,
    )


def test_form_failure_routes_to_typed_completion_assistance() -> None:
    plan = route_browser_recovery(
        source=MODEL_FAILURE,
        observation=_observation(),
        lang="zh",
        error="无法可靠定位保存按钮",
        has_form_payload=True,
    )

    assert plan.can_assist
    assert plan.decision is not None
    assert plan.decision.args["category"] == FORM_TASK_COMPLETION_CATEGORY
    contract = plan.decision.args["handoff"]["contract"]
    assert contract["action"] == "repair_or_complete_form"
    assert contract["replay_policy"] == "never_replay_after_human_task_completed"


def test_prebuilt_media_assistance_is_not_replaced_or_trimmed() -> None:
    media = Decision(
        tool="browser_ask_user",
        args={
            "category": "media_upload",
            "question": "请手动上传图片",
            "handoff": {
                "contract": {"kind": "form_media"},
                "article": {"title": "标题", "body": "正文"},
                "images": [{"candidate_id": "image-1", "url": "https://assets.test/1.png"}],
            },
        },
    )

    plan = route_browser_recovery(
        source=MODEL_FAILURE,
        observation=_observation(),
        lang="zh",
        prebuilt_assistance=media,
    )

    assert plan.can_assist
    assert plan.decision is media
    assert plan.decision.args["handoff"]["article"] == {"title": "标题", "body": "正文"}
    assert plan.decision.args["handoff"]["images"][0]["candidate_id"] == "image-1"


def test_connection_failure_can_ask_for_help_without_a_fresh_dom() -> None:
    plan = route_browser_recovery(
        source=LOOP_EXHAUSTED,
        observation=_observation(fresh=False),
        lang="zh",
        error="agent-disconnected",
    )

    assert plan.can_assist
    assert plan.source == BROWSER_CONNECTION_LOST
    assert plan.decision is not None
    assert plan.decision.args["category"] == "browser_connection"


def test_output_contract_failure_requests_visible_evidence() -> None:
    plan = route_browser_recovery(
        source=OUTPUT_CONTRACT_EXHAUSTED,
        observation=_observation(),
        lang="zh",
        error="missing requested fields",
    )

    assert plan.can_assist
    assert plan.decision is not None
    assert plan.decision.args["category"] == "browser_evidence"


def test_resume_recovery_preserves_original_contract() -> None:
    contract = {
        "kind": FORM_TASK_COMPLETION_CATEGORY,
        "contract_id": "contract-1",
        "replay_policy": "never_replay_after_human_task_completed",
    }
    plan = route_browser_recovery(
        source=RESUME_RECONCILIATION_UNAVAILABLE,
        observation=_observation(fresh=False),
        lang="zh",
        preserved_handoff={"contract": contract},
    )

    assert plan.can_assist
    assert plan.decision is not None
    assert plan.decision.args["category"] == FORM_TASK_COMPLETION_CATEGORY
    assert plan.decision.args["handoff"]["contract"] == contract


def test_explicit_business_failure_and_internal_failure_remain_terminal() -> None:
    business_failure = route_browser_recovery(
        source=LOOP_EXHAUSTED,
        observation=_observation(),
        lang="zh",
        error="submission rejected",
        effect_statuses=("confirmed_failure",),
    )
    internal_failure = route_browser_recovery(
        source=INTERNAL_FAILURE,
        observation=_observation(),
        lang="zh",
        error="invalid executor state",
    )

    assert business_failure.action == "hard_fail"
    assert not business_failure.can_assist
    assert internal_failure.action == "hard_fail"
    assert not internal_failure.can_assist


def test_generic_failure_without_live_page_does_not_create_fake_assistance() -> None:
    plan = route_browser_recovery(
        source=MODEL_FAILURE,
        observation=Observation(url="", title="", elements=[], fresh=False),
        lang="zh",
        error="no page",
    )

    assert plan.action == "hard_fail"
    assert not plan.can_assist


def test_same_page_state_uses_one_dedupe_key_across_failure_sources() -> None:
    model_failure = route_browser_recovery(
        source=MODEL_FAILURE,
        observation=_observation(),
        lang="zh",
        error="planner cannot continue",
    )
    loop_failure = route_browser_recovery(
        source=LOOP_EXHAUSTED,
        observation=_observation(),
        lang="zh",
        error="loop exhausted",
    )

    assert model_failure.assistance is not None
    assert loop_failure.assistance is not None
    assert model_failure.assistance.dedupe_key == loop_failure.assistance.dedupe_key

    existing_policy = browser_human_assistance(
        source=READ_BUDGET,
        observation=_observation(),
        lang="zh",
    )
    assert existing_policy is not None
    assert existing_policy.dedupe_key == model_failure.assistance.dedupe_key


def test_changed_page_state_can_request_assistance_again() -> None:
    before = _observation()
    before.state_fingerprint = "state-before"
    after = _observation()
    after.state_fingerprint = "state-after"

    first = route_browser_recovery(
        source=MODEL_FAILURE,
        observation=before,
        lang="zh",
        error="blocked",
    )
    second = route_browser_recovery(
        source=MODEL_FAILURE,
        observation=after,
        lang="zh",
        error="blocked later",
    )

    assert first.assistance is not None
    assert second.assistance is not None
    assert first.assistance.dedupe_key != second.assistance.dedupe_key
