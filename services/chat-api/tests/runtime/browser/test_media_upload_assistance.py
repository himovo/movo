from app.enterprise_capabilities.browser.engine.drivers.form_input import FormInputDriver
from app.enterprise_capabilities.browser.engine.form_input import BrowserInputContext, InputCandidate
from app.enterprise_capabilities.browser.engine.media_upload_assistance import (
    augment_form_assistance_handoff,
    build_media_upload_handoff,
    completed_media_candidate_ids,
    is_media_delivery_handoff_error,
    is_media_upload_receiver_error,
    media_upload_assistance_decision,
)
from app.enterprise_capabilities.browser.engine.form_human_assistance import (
    build_form_repair_assistance_decision,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision


class _Fallback:
    kind = "test"

    async def next_step(self, *args, **kwargs):
        return Decision(tool="browser_observe", args={})

    def on_step_completed(self, *args, **kwargs):
        return None

    def export_checkpoint_state(self):
        return {}

    def restore_checkpoint_state(self, state):
        return None


def _context() -> BrowserInputContext:
    return BrowserInputContext(
        original_request="发布文章",
        candidates=[
            InputCandidate(
                "title", "upstream", "publish.title", "title", "测试标题",
                metadata={"binding_authority": "publish_payload", "field_role": "title"},
            ),
            InputCandidate(
                "body", "upstream", "publish.body", "body", "测试正文",
                plain_text="测试正文",
                metadata={"binding_authority": "publish_payload", "field_role": "body"},
            ),
            InputCandidate(
                "image-1", "upstream", "publish.media.0", "media", ["/tmp/one.png"],
                value_kind="file",
                metadata={
                    "handoff_resource": {
                        "filename": "one.png",
                        "signed_url": "https://assets.example/one.png",
                    },
                    "media_anchor": {"order": 0},
                },
            ),
            InputCandidate(
                "image-2", "upstream", "publish.media.1", "media", ["https://assets.example/two.png"],
                value_kind="file",
                metadata={"media_anchor": {"order": 1}},
            ),
        ],
    )


def test_media_handoff_exposes_article_and_all_pending_images() -> None:
    handoff = build_media_upload_handoff(
        context=_context(), completed_candidate_ids=[], user_id="user-1",
    )

    assert handoff is not None
    assert handoff["article"] == {"title": "测试标题", "body": "测试正文"}
    assert [item["url"] for item in handoff["images"]] == [
        "https://assets.example/one.png",
        "https://assets.example/two.png",
    ]
    assert handoff["pending_candidate_ids"] == ["image-1", "image-2"]
    assert handoff["contract"]["kind"] == "form_media"


def test_media_handoff_omits_candidates_already_completed() -> None:
    handoff = build_media_upload_handoff(
        context=_context(), completed_candidate_ids=["image-1"], user_id="user-1",
    )

    assert handoff is not None
    assert handoff["pending_candidate_ids"] == ["image-2"]


def test_manual_resume_marks_only_known_file_candidates_complete() -> None:
    driver = FormInputDriver(
        fallback=_Fallback(),
        input_context=_context(),
        capability_id="browser.publish",
    )

    driver.apply_resume_signal({
        "type": "human_intervention_completed",
        "media_completed_candidate_ids": ["image-1", "unknown", "title"],
    })

    assert driver.export_checkpoint_state()["completed_candidate_ids"] == ["image-1"]


def test_upload_receiver_error_and_nested_checkpoint_detection() -> None:
    assert is_media_upload_receiver_error("Node is not a file input element")
    assert is_media_upload_receiver_error("File upload receiver is unavailable")
    assert not is_media_upload_receiver_error("network unavailable")
    assert completed_media_candidate_ids({
        "fallback_state": {"completed_candidate_ids": ["image-1"]},
    }) == {"image-1"}
    decision = media_upload_assistance_decision(
        {"images": [{"candidate_id": "image-1"}]},
        lang="zh",
    )
    assert decision is not None
    assert decision.tool == "browser_ask_user"
    assert decision.args["category"] == "media_upload"


def test_unverified_paste_is_handed_off_without_replaying_it() -> None:
    assert is_media_delivery_handoff_error(
        tool="browser_paste_image",
        error="File input accepted the upload, but no new media appeared in the target editor",
    )
    assert is_media_delivery_handoff_error(
        tool="browser_paste_image",
        error="Unable to focus rich editor in frame context: e12",
    )
    assert not is_media_delivery_handoff_error(
        tool="browser_click",
        error="Unable to focus rich editor",
    )


def test_effect_assistance_exposes_full_article_and_all_images() -> None:
    handoff = augment_form_assistance_handoff(
        {
            "contract": {
                "kind": "form_effect_verify",
                "contract_id": "verify-1",
            },
        },
        context=_context(),
        completed_candidate_ids=["image-1"],
        user_id="user-1",
    )

    assert handoff is not None
    assert handoff["article"] == {"title": "测试标题", "body": "测试正文"}
    assert [item["candidate_id"] for item in handoff["images"]] == [
        "image-1", "image-2",
    ]
    assert handoff["images"][0]["completed_by_agent"] is True
    assert handoff["pending_candidate_ids"] == ["image-2"]


def test_generic_form_recovery_is_augmented_with_article_and_images() -> None:
    decision = build_form_repair_assistance_decision(
        reason="cannot locate a reliable submit control",
        lang="zh",
    )
    handoff = augment_form_assistance_handoff(
        decision.args["handoff"],
        context=_context(),
        completed_candidate_ids=["image-1"],
        user_id="user-1",
    )

    assert handoff is not None
    assert handoff["article"] == {"title": "测试标题", "body": "测试正文"}
    assert [item["candidate_id"] for item in handoff["images"]] == [
        "image-1", "image-2",
    ]
    assert handoff["pending_candidate_ids"] == ["image-2"]
