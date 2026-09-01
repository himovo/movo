from app.enterprise_capabilities.browser.engine.effect_verification.interaction_relation import (
    resolve_action_fields_relation,
    resolve_field_action_relation,
)


def test_direct_dom_association_is_related_without_lockable_scope() -> None:
    field = {
        "selector": "#query",
        "frameDepth": 0,
        "scopeLockable": False,
    }
    action = {
        "associatedFieldSelectors": ["#query"],
        "frameDepth": 0,
        "scopeLockable": False,
    }

    relation = resolve_field_action_relation(field, action)

    assert relation.status == "related"
    assert relation.source == "direct_dom_association"


def test_different_native_form_owners_are_unrelated() -> None:
    relation = resolve_field_action_relation(
        {"formOwnerSelector": "#editor", "frameDepth": 0},
        {"formOwnerSelector": "#navigation", "frameDepth": 0},
    )

    assert relation.status == "unrelated"
    assert relation.source == "form_owner"


def test_cross_frame_field_is_related_only_through_explicit_host_scope() -> None:
    outer_scope = "0:body > main > form"
    relation = resolve_field_action_relation(
        {
            "selector": "body",
            "frameDepth": 1,
            "frameHostScopeIds": [outer_scope],
        },
        {
            "scopeId": outer_scope,
            "scopeSelector": "body > main > form",
            "frameDepth": 0,
        },
    )

    assert relation.status == "related"
    assert relation.source == "frame_host_scope"


def test_cross_frame_field_without_shared_host_scope_is_unrelated() -> None:
    relation = resolve_field_action_relation(
        {
            "selector": "body",
            "frameDepth": 1,
            "frameHostScopeIds": ["0:body > main > form"],
        },
        {
            "scopeId": "0:body > aside > form",
            "scopeSelector": "body > aside > form",
            "frameDepth": 0,
        },
    )

    assert relation.status == "unrelated"
    assert relation.source == "different_frame"


def test_iframe_field_is_related_to_outer_action_through_host_component() -> None:
    editor_component = "body > main > div.editor-shell"
    editor_form = f"{editor_component} > section > form"
    relation = resolve_field_action_relation(
        {
            "selector": "html > body",
            "frameDepth": 1,
            "frameHostScopeIds": [f"0:{editor_form}"],
        },
        {
            "selector": f"{editor_component} > footer > button",
            "frameDepth": 0,
            "scopeLockable": False,
            "componentOwnerSelector": editor_component,
            "componentOwnerAssociable": False,
            "componentOwnerFormCount": 2,
        },
    )

    assert relation.status == "related"
    assert relation.source == "frame_host_component_owner"


def test_iframe_field_does_not_bind_action_owned_by_another_outer_form() -> None:
    relation = resolve_field_action_relation(
        {
            "selector": "html > body",
            "frameDepth": 1,
            "frameHostScopeIds": ["0:body > main > form.editor"],
        },
        {
            "selector": "body > aside > form.assistant > button",
            "frameDepth": 0,
            "formOwnerSelector": "body > aside > form.assistant",
            "componentOwnerSelector": "body",
        },
    )

    assert relation.status == "unrelated"
    assert relation.source == "frame_host_form_owner"


def test_explicit_association_is_not_overridden_by_broad_scope_ancestry() -> None:
    main = "body > main"
    relation = resolve_field_action_relation(
        {
            "selector": "#other-field",
            "scopeSelector": f"{main} > section",
            "scopeRole": "div",
            "scopeLockable": False,
            "frameDepth": 0,
        },
        {
            "associatedFieldSelectors": ["#owned-field"],
            "scopeSelector": main,
            "scopeRole": "main",
            "scopeLockable": False,
            "frameDepth": 0,
        },
    )

    assert relation.status == "unrelated"
    assert relation.source == "direct_dom_association"


def test_unlockable_nested_editor_does_not_trust_broad_main_boundary() -> None:
    main = "body > div > main"
    relation = resolve_field_action_relation(
        {
            "scopeSelector": f"{main} > section:nth-of-type(2)",
            "scopeRole": "div",
            "scopeLockable": False,
            "frameDepth": 0,
        },
        {
            "scopeSelector": main,
            "scopeRole": "main",
            "scopeLockable": False,
            "frameDepth": 0,
        },
    )

    assert relation.status == "unknown"
    assert relation.source == ""


def test_disjoint_unlockable_scopes_remain_unknown() -> None:
    relation = resolve_field_action_relation(
        {
            "scopeSelector": "body > main > section",
            "scopeRole": "div",
            "scopeLockable": False,
            "frameDepth": 0,
        },
        {
            "scopeSelector": "body > nav",
            "scopeRole": "nav",
            "scopeLockable": False,
            "frameDepth": 0,
        },
    )

    assert relation.status == "unknown"


def test_aggregate_requires_all_negative_evidence_before_unrelated() -> None:
    relation = resolve_action_fields_relation(
        action={
            "scopeSelector": "body > nav",
            "scopeRole": "nav",
            "scopeLockable": False,
            "frameDepth": 0,
        },
        fields=[
            {
                "formOwnerSelector": "#editor",
                "frameDepth": 0,
            },
            {
                "scopeSelector": "body > main",
                "scopeRole": "main",
                "scopeLockable": False,
                "frameDepth": 0,
            },
        ],
    )

    assert relation.status == "unknown"


def test_submit_outside_form_is_related_through_shared_interaction_component() -> None:
    component = "body > main > article > div:nth-of-type(2)"
    relation = resolve_field_action_relation(
        {
            "selector": f"{component} > form > div[contenteditable=true]",
            "formOwnerSelector": f"{component} > form",
            "componentOwnerSelector": component,
            "componentOwnerLockable": True,
            "frameDepth": 0,
        },
        {
            "selector": f"{component} > footer > button",
            "componentOwnerSelector": component,
            "componentOwnerLockable": True,
            "fieldAssociationKind": "component",
            "frameDepth": 0,
        },
    )

    assert relation.status == "related"
    assert relation.source == "interaction_component_owner"


def test_component_association_list_is_not_treated_as_exhaustive() -> None:
    component = "body > main > article"
    relation = resolve_field_action_relation(
        {
            "selector": f"{component} > form > textarea:nth-of-type(13)",
            "componentOwnerSelector": component,
            "componentOwnerLockable": True,
            "frameDepth": 0,
        },
        {
            "selector": f"{component} > footer > button",
            "associatedFieldSelectors": [
                f"{component} > form > textarea:nth-of-type(1)",
            ],
            "fieldAssociationKind": "component",
            "componentOwnerSelector": component,
            "componentOwnerLockable": True,
            "frameDepth": 0,
        },
    )

    assert relation.status == "related"
    assert relation.source == "interaction_component_owner"


def test_broad_or_different_component_does_not_bind_commit_control() -> None:
    relation = resolve_field_action_relation(
        {
            "selector": "#editor",
            "componentOwnerSelector": "body > main > article",
            "componentOwnerLockable": True,
            "frameDepth": 0,
        },
        {
            "selector": "#publish-navigation",
            "componentOwnerSelector": "body > main",
            "componentOwnerLockable": False,
            "fieldAssociationKind": "component",
            "frameDepth": 0,
        },
    )

    assert relation.status == "unknown"


def test_large_editor_toolbar_uses_association_quality_not_action_count() -> None:
    component = (
        "body > div:nth-of-type(1) > div > main > div > div "
        "> div:nth-of-type(2) > div > div > div > div:nth-of-type(2)"
    )
    form = f"{component} > form"
    relation = resolve_field_action_relation(
        {
            "selector": f"{form} > div > div[contenteditable=true]",
            "formOwnerSelector": form,
            "componentOwnerSelector": component,
            "componentOwnerLockable": False,
            "componentOwnerAssociable": True,
            "componentOwnerFormCount": 1,
            "scopeActionCount": 27,
            "frameDepth": 0,
        },
        {
            "selector": f"{component} > div > footer > button:nth-of-type(2)",
            "componentOwnerSelector": component,
            "componentOwnerLockable": False,
            "componentOwnerAssociable": True,
            "componentOwnerFormCount": 1,
            "scopeActionCount": 32,
            "fieldAssociationKind": "component",
            "frameDepth": 0,
        },
    )

    assert relation.status == "related"
    assert relation.source == "interaction_component_owner"


def test_page_level_shared_owner_is_not_enough_to_bind_submit() -> None:
    page = "body > div > main"
    relation = resolve_field_action_relation(
        {
            "selector": f"{page} > article > form > textarea",
            "formOwnerSelector": f"{page} > article > form",
            "componentOwnerSelector": page,
            "componentOwnerAssociable": False,
            "componentOwnerFormCount": 1,
            "frameDepth": 0,
        },
        {
            "selector": f"{page} > aside > button",
            "componentOwnerSelector": page,
            "componentOwnerAssociable": False,
            "componentOwnerFormCount": 1,
            "fieldAssociationKind": "",
            "frameDepth": 0,
        },
    )

    assert relation.status == "unknown"


def test_multi_form_shared_owner_is_not_enough_to_bind_submit() -> None:
    component = "body > main > section"
    relation = resolve_field_action_relation(
        {
            "selector": f"{component} > form:nth-of-type(1) > textarea",
            "formOwnerSelector": f"{component} > form:nth-of-type(1)",
            "componentOwnerSelector": component,
            "componentOwnerAssociable": False,
            "componentOwnerFormCount": 2,
            "frameDepth": 0,
        },
        {
            "selector": f"{component} > footer > button",
            "componentOwnerSelector": component,
            "componentOwnerAssociable": False,
            "componentOwnerFormCount": 2,
            "fieldAssociationKind": "",
            "frameDepth": 0,
        },
    )

    assert relation.status == "unknown"


def test_shared_component_metadata_cannot_override_selector_mismatch() -> None:
    component = "body > main > article"
    relation = resolve_field_action_relation(
        {
            "selector": f"{component} > form > textarea",
            "formOwnerSelector": f"{component} > form",
            "componentOwnerSelector": component,
            "componentOwnerAssociable": True,
            "componentOwnerFormCount": 1,
            "frameDepth": 0,
        },
        {
            "selector": "body > aside > button",
            "componentOwnerSelector": component,
            "componentOwnerAssociable": True,
            "componentOwnerFormCount": 1,
            "fieldAssociationKind": "component",
            "frameDepth": 0,
        },
    )

    assert relation.status == "unknown"


def test_shared_component_accepts_compact_id_selectors_without_ancestry() -> None:
    component = "body > main > section"
    relation = resolve_field_action_relation(
        {
            "selector": "#answer-editor",
            "formOwnerSelector": "#answer-form",
            "componentOwnerSelector": component,
            "componentOwnerAssociable": True,
            "componentOwnerFormCount": 1,
            "frameDepth": 0,
        },
        {
            "selector": "#publish-answer",
            "componentOwnerSelector": component,
            "componentOwnerAssociable": True,
            "componentOwnerFormCount": 1,
            "fieldAssociationKind": "component",
            "frameDepth": 0,
        },
    )

    assert relation.status == "related"
    assert relation.source == "interaction_component_owner"
