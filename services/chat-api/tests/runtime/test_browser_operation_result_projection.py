from types import SimpleNamespace

from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectReceipt
from app.enterprise_capabilities.browser.engine.operation_result_projection import (
    project_verified_operation_result,
)


class _Context:
    def result_evidence(self, _observation):
        return {
            "search_query": "智能体",
            "target_title": "豆包智能体！有希望！大家一起加油！",
            "target_url": (
                "https://example.test/post/42"
                "?xsec_token=secret&source=search&utm_source=test"
            ),
        }


def _receipt(*hashes: str) -> EffectReceipt:
    return EffectReceipt(
        contract_key="publish-comment",
        status="confirmed_success",
        confidence=0.95,
        action_name="发送",
        operation_family="send",
        completes_goal=True,
        fingerprint={"confirmed_fill_hashes": list(hashes)},
    )


def test_projection_preserves_verified_business_details_without_raw_dom():
    result = project_verified_operation_result(
        receipt=_receipt("comment-hash"),
        context=_Context(),
        form_state={
            "fields": [
                {
                    "label": "评论",
                    "expected_value": "这是一条已确认提交的评论。",
                    "value_hash": "comment-hash",
                    "status": "confirmed",
                    "secret": False,
                    "target": {
                        "role": "textbox",
                        "semanticPurpose": "comment",
                    },
                },
                {
                    "label": "搜索",
                    "expected_value": "不应混入提交字段",
                    "value_hash": "search-hash",
                    "status": "confirmed",
                    "secret": False,
                    "target": {
                        "role": "searchbox",
                        "semanticPurpose": "search",
                    },
                },
            ],
        },
        observation=SimpleNamespace(
            url="https://example.test/post/42?token=secret",
            title="Example",
        ),
    )

    details = result["operation_details"]
    assert details["search_query"] == "智能体"
    assert details["target_title"] == "豆包智能体！有希望！大家一起加油！"
    assert details["target_url"] == "https://example.test/post/42?source=search"
    assert details["submitted_fields"] == [{
        "label": "评论",
        "value": "这是一条已确认提交的评论。",
        "purpose": "comment",
    }]
    assert "page_text" not in str(result)


def test_projection_excludes_secret_fields_even_when_hash_is_present():
    result = project_verified_operation_result(
        receipt=_receipt("password-hash", "otp-hash"),
        context=SimpleNamespace(result_evidence=lambda _obs: {}),
        form_state={
            "fields": [
                {
                    "label": "密码",
                    "expected_value": "plain-password",
                    "value_hash": "password-hash",
                    "status": "confirmed",
                    "secret": True,
                    "target": {"type": "password"},
                },
                {
                    "label": "验证码",
                    "expected_value": "123456",
                    "value_hash": "otp-hash",
                    "status": "confirmed",
                    "secret": True,
                    "target": {"type": "text"},
                },
            ],
        },
        observation=SimpleNamespace(
            url="https://example.test/login?sid=secret",
            title="Login",
        ),
    )

    details = result["operation_details"]
    assert "submitted_fields" not in details
    assert details["target_url"] == "https://example.test/login"
    assert "plain-password" not in str(result)
    assert "123456" not in str(result)


def test_projection_is_empty_for_unconfirmed_operation():
    receipt = _receipt("comment-hash").model_copy(
        update={"status": "unknown"},
    )

    result = project_verified_operation_result(
        receipt=receipt,
        context=_Context(),
        form_state={},
        observation=SimpleNamespace(url="https://example.test", title="Example"),
    )

    assert result == {}
