from app.enterprise_capabilities.browser.engine.form_input.commit_binding import (
    CommitBindingLedger,
    commit_control_key,
)
from app.enterprise_capabilities.browser.engine.form_input.commit_resolver import resolve_form_commit
from app.enterprise_capabilities.browser.engine.form_input.contracts import FieldDescriptor
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _field(*, value: str = "") -> FieldDescriptor:
    selector = "#editor"
    return FieldDescriptor(
        field_key="body",
        ref="body",
        control_kind="rich_text",
        current_value=value,
        raw={
            "ref": "body",
            "selector": selector,
            "scopeSelector": "#composer",
            "scopeLockable": False,
            "frameDepth": 0,
            "value": value,
        },
    )


def _action(
    selector: str,
    *,
    disabled: bool = False,
    visible: bool = True,
    hit_testable: bool = True,
    form_owner: str = "",
) -> dict:
    return {
        "ref": selector,
        "selector": selector,
        "role": "button",
        "name": "发布",
        "text": "发布",
        "disabled": disabled,
        "visible": visible,
        "hitTestable": hit_testable,
        "formOwnerSelector": form_owner,
        "scopeLockable": False,
        "frameDepth": 0,
    }


def test_unchanged_page_navigation_is_not_bound_to_mutated_form() -> None:
    ledger = CommitBindingLedger()
    navigation = _action("#publish-navigation")

    ledger.observe(
        candidates=[navigation],
        fields=[_field()],
        mutated_field_keys=set(),
    )
    ledger.observe(
        candidates=[navigation],
        fields=[_field(value="draft")],
        mutated_field_keys={"body"},
    )

    assert commit_control_key(navigation) not in ledger.bound_action_keys


def test_disabled_control_becoming_enabled_is_bound_across_ref_changes() -> None:
    ledger = CommitBindingLedger()
    disabled = _action("#submit", disabled=True, hit_testable=False)
    disabled["ref"] = "e1"
    enabled = _action("#submit")
    enabled["ref"] = "e9"

    ledger.observe(
        candidates=[disabled],
        fields=[_field()],
        mutated_field_keys=set(),
    )
    ledger.observe(
        candidates=[enabled],
        fields=[_field(value="draft")],
        mutated_field_keys={"body"},
    )

    assert commit_control_key(enabled) in ledger.bound_action_keys


def test_new_commit_control_is_bound_after_form_mutation() -> None:
    ledger = CommitBindingLedger()
    submit = _action("#composer > button")

    ledger.observe(
        candidates=[],
        fields=[_field()],
        mutated_field_keys=set(),
    )
    ledger.observe(
        candidates=[submit],
        fields=[_field(value="draft")],
        mutated_field_keys={"body"},
    )

    assert commit_control_key(submit) in ledger.bound_action_keys


def test_new_page_level_commit_control_is_not_bound_by_appearance_alone() -> None:
    ledger = CommitBindingLedger()
    navigation = _action("#navigation > button")

    ledger.observe(
        candidates=[],
        fields=[_field()],
        mutated_field_keys=set(),
    )
    ledger.observe(
        candidates=[navigation],
        fields=[_field(value="draft")],
        mutated_field_keys={"body"},
    )

    assert commit_control_key(navigation) not in ledger.bound_action_keys


def test_explicitly_different_form_control_is_never_causally_bound() -> None:
    ledger = CommitBindingLedger()
    field = _field()
    field.raw["formOwnerSelector"] = "#editor-form"
    other = _action("#submit", form_owner="#other-form")

    ledger.observe(
        candidates=[],
        fields=[field],
        mutated_field_keys=set(),
    )
    filled = field.model_copy(update={"current_value": "draft"})
    filled.raw["value"] = "draft"
    ledger.observe(
        candidates=[other],
        fields=[filled],
        mutated_field_keys={"body"},
    )

    assert commit_control_key(other) not in ledger.bound_action_keys


def test_causally_bound_unknown_control_can_be_resolved_after_fresh_observation() -> None:
    field = _field(value="draft")
    submit = _action("#submit")
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[submit],
    )

    resolution = resolve_form_commit(
        observation,
        fields=[field],
        mutated_field_keys={"body"},
        observation_is_fresh=True,
        bound_action_keys={commit_control_key(submit)},
    )

    assert resolution.kind == "click"
    assert resolution.decision is not None
    assert resolution.decision.args == {"ref": "#submit"}


def test_rejected_outer_commit_is_returned_to_planner_with_local_alternatives() -> None:
    ledger = CommitBindingLedger()
    field = _field(value="draft")
    wrong = _action("#page-navigation")
    wrong["ref"] = "e16"
    wrong["scopeId"] = "0:#page"
    local = {
        "ref": "e15",
        "selector": "#composer > .toolbar > button",
        "role": "button",
        "name": "继续",
        "visible": True,
        "hitTestable": True,
        "scopeId": "0:#composer",
        "scopeSelector": "#composer",
        "frameDepth": 0,
    }
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[wrong, local],
    )

    ledger.reject(
        target=wrong,
        fields=[field],
        reason="not bound to the active form",
        page_url=observation.url,
    )
    state = ledger.augment_planner_state(
        observation=observation,
        fields=[field],
        state_ledger=None,
    )

    assert state is not None
    assert state["pinned_refs"] == ["e15"]
    assert "e16" in " ".join(state["forbidden_actions"])
    assert "e15" in " ".join(state["action_constraints"])
    assert ledger.is_rejected_decision(
        Decision(tool="browser_click", args={"ref": "e16"}),
        observation,
        fields=[field],
    )


def test_rejected_commit_identity_survives_ephemeral_ref_change() -> None:
    ledger = CommitBindingLedger()
    field = _field(value="draft")
    before = _action("#page-navigation")
    before["ref"] = "e16"
    after = _action("#page-navigation")
    after["ref"] = "e42"
    first = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[before],
    )
    refreshed = Observation(
        url=first.url,
        title=first.title,
        page_text="",
        elements=[after],
    )

    ledger.reject(
        target=before,
        fields=[field],
        reason="not bound",
        page_url=first.url,
    )

    assert ledger.is_rejected_decision(
        Decision(tool="browser_click", args={"ref": "e42"}),
        refreshed,
        fields=[field],
    )


def test_rejected_commit_is_cleared_when_form_stage_changes() -> None:
    ledger = CommitBindingLedger()
    field = _field(value="draft")
    wrong = _action("#page-navigation")
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[wrong],
    )
    ledger.reject(
        target=wrong,
        fields=[field],
        reason="not bound",
        page_url=observation.url,
    )
    next_field = field.model_copy(update={
        "field_key": "summary",
        "scope_id": "0:#review",
    })
    next_field.raw["scopeId"] = "0:#review"
    next_field.raw["scopeSelector"] = "#review"

    assert ledger.augment_planner_state(
        observation=observation,
        fields=[next_field],
        state_ledger=None,
    ) is None


def test_rejected_commit_is_rehabilitated_when_it_becomes_causally_bound() -> None:
    ledger = CommitBindingLedger()
    empty = _field()
    disabled = _action(
        "#composer > button",
        disabled=True,
        hit_testable=False,
    )
    disabled["ref"] = "e1"
    enabled = _action("#composer > button")
    enabled["ref"] = "e9"
    observation = Observation(
        url="https://example.test/editor",
        title="Editor",
        page_text="",
        elements=[enabled],
    )

    ledger.observe(
        candidates=[disabled],
        fields=[empty],
        mutated_field_keys=set(),
        page_url=observation.url,
    )
    ledger.reject(
        target=disabled,
        fields=[empty],
        reason="not bound yet",
        page_url=observation.url,
    )
    ledger.observe(
        candidates=[enabled],
        fields=[_field(value="draft")],
        mutated_field_keys={"body"},
        page_url=observation.url,
    )

    assert commit_control_key(enabled) in ledger.bound_action_keys
    assert ledger.augment_planner_state(
        observation=observation,
        fields=[_field(value="draft")],
        state_ledger=None,
    ) is None
