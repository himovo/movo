from __future__ import annotations

from app.enterprise_capabilities.browser.engine.effect_verification.commit_preconditions import (
    enforce_commit_preconditions,
)
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract
from app.enterprise_capabilities.browser.engine.effect_verification.form_transaction import (
    FormTransactionTracker,
)
from app.enterprise_capabilities.browser.engine.form_input.input_context import (
    BrowserInputContext,
    InputCandidate,
)
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


def _commit(
    *,
    operation: str = "publish",
    intended_operation: str = "",
) -> EffectContract:
    return EffectContract(
        action_name="Publish",
        operation_family=operation,
        side_effect="external",
        is_commit=True,
        completes_goal=True,
        intended_operation=intended_operation,
        source="model",
    )


def test_semantic_entry_action_is_not_registered_as_business_commit() -> None:
    decision = enforce_commit_preconditions(
        _commit(intended_operation="open"),
        requires_form_input=False,
        has_confirmed_form_input=False,
    )

    assert decision.downgraded is True
    assert decision.contract.is_commit is False
    assert decision.contract.operation_family == "navigate"


def test_semantic_entry_phrase_is_normalized_without_site_rules() -> None:
    decision = enforce_commit_preconditions(
        _commit(intended_operation="open_editor"),
        requires_form_input=False,
        has_confirmed_form_input=False,
    )

    assert decision.downgraded is True
    assert decision.contract.is_commit is False


def test_structured_publish_requires_a_confirmed_payload_field() -> None:
    decision = enforce_commit_preconditions(
        _commit(),
        requires_form_input=True,
        has_confirmed_form_input=False,
    )

    assert decision.downgraded is True
    assert decision.contract.is_commit is False


def test_confirmed_structured_publish_remains_a_commit() -> None:
    decision = enforce_commit_preconditions(
        _commit(),
        requires_form_input=True,
        has_confirmed_form_input=True,
    )

    assert decision.downgraded is False
    assert decision.contract.is_commit is True


def test_one_click_business_action_is_not_affected() -> None:
    decision = enforce_commit_preconditions(
        _commit(operation="approve", intended_operation="approve"),
        requires_form_input=False,
        has_confirmed_form_input=False,
    )

    assert decision.downgraded is False
    assert decision.contract.is_commit is True


def test_publish_context_and_form_transaction_share_authoritative_values() -> None:
    context = BrowserInputContext(
        original_request="publish the generated article",
        candidates=[
            InputCandidate(
                candidate_id="title",
                source_kind="upstream",
                source_path="artifact.publish_payload.title",
                semantic_name="title",
                value="A generated title",
                metadata={
                    "binding_authority": "publish_payload",
                    "field_role": "title",
                },
            ),
            InputCandidate(
                candidate_id="media",
                source_kind="upstream",
                source_path="artifact.publish_payload.media.0",
                semantic_name="media",
                value=["/tmp/image.png"],
                value_kind="file",
            ),
        ],
    )
    transaction = FormTransactionTracker()

    assert context.requires_authoritative_form_input() is True
    assert context.authoritative_form_values() == ["A generated title"]
    assert transaction.has_confirmed_value(
        context.authoritative_form_values(),
    ) is False

    before = Observation(
        url="https://example.test/editor",
        title="Editor",
        elements=[{
            "ref": "title",
            "role": "textbox",
            "name": "Title",
            "editable": True,
            "value": "",
        }],
    )
    after = Observation(
        url=before.url,
        title=before.title,
        elements=[{
            **before.elements[0],
            "value": "A generated title",
        }],
    )
    transaction.record_fill(
        args={"ref": "title", "value": "A generated title"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=before,
        after=after,
    )

    assert transaction.has_confirmed_value(
        context.authoritative_form_values(),
    ) is True
