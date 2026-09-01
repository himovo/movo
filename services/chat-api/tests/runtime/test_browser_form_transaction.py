from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract
from app.enterprise_capabilities.browser.engine.effect_verification.form_transaction import FormTransactionTracker
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation


def _obs(*, value: str = "", page_text: str = "", placeholder: str = "输入内容") -> Observation:
    return Observation(
        url="https://example.test/edit",
        title="test",
        elements=[{
            "ref": "e1",
            "role": "textbox",
            "name": "正文",
            "placeholder": placeholder,
            "selector": "#search-input",
            "editable": True,
            "value": value,
        }],
        page_text=page_text,
    )


def test_ambiguous_fill_blocks_commit_until_fresh_observation_confirms_value() -> None:
    tracker = FormTransactionTracker()
    before = _obs()
    receipt = tracker.record_fill(
        args={"ref": "e1", "value": "需要发布的正文"},
        result={
            "fill_receipt": {
                "status": "ambiguous",
                "reason": "target replaced",
            },
        },
        ok=True,
        error=None,
        before=before,
        after=_obs(),
    )

    assert receipt.status == "ambiguous"
    assert tracker.commit_blocker(_obs()) is not None
    assert tracker.commit_blocker(_obs(value="需要发布的正文")) is None


def test_rich_text_fill_reconciles_editor_whitespace_and_inline_boundaries() -> None:
    tracker = FormTransactionTracker()
    before = _obs()
    before.elements[0].update({
        "contentEditable": True,
        "contentEditableMode": "true",
        "tag": "div",
    })
    tracker.record_fill(
        args={
            "ref": "e1",
            "value": "重复咨询\n就像办公室里的灰犀牛\nAI员工服务台\n应运而生",
        },
        result=None,
        ok=False,
        error="value_not_applied: rich editor normalized the document",
        before=before,
        after=before,
    )
    current = _obs(
        value="重复咨询就像办公室里的灰犀牛\n\n AI员工服务台应运而生",
    )
    current.elements[0].update({
        "contentEditable": True,
        "contentEditableMode": "true",
        "tag": "div",
    })

    assert tracker.commit_blocker(current) is None


def test_plain_text_fill_does_not_ignore_missing_word_boundaries() -> None:
    tracker = FormTransactionTracker()
    tracker.record_fill(
        args={"ref": "e1", "value": "hello world"},
        result=None,
        ok=False,
        error="value_not_applied",
        before=_obs(),
        after=_obs(),
    )

    assert tracker.commit_blocker(_obs(value="helloworld")) is not None


def test_failed_fill_blocks_commit() -> None:
    tracker = FormTransactionTracker()
    tracker.record_fill(
        args={"ref": "e1", "value": "正文"},
        result=None,
        ok=False,
        error="value_not_applied: expected value was not written",
        before=_obs(),
        after=_obs(),
    )

    blocker = tracker.commit_blocker(_obs())
    assert blocker is not None
    assert blocker.fields == ("正文",)


def test_dynamic_placeholder_does_not_create_duplicate_field_receipts() -> None:
    tracker = FormTransactionTracker()
    tracker.record_fill(
        args={"ref": "e1", "value": "员工服务台"},
        result=None,
        ok=False,
        error="dispatch-error: timeout",
        before=_obs(placeholder="法国vs英格兰"),
        after=_obs(placeholder="法国vs英格兰"),
    )
    tracker.record_fill(
        args={"ref": "e1", "value": "员工服务台"},
        result=None,
        ok=False,
        error="dispatch-error: timeout",
        before=_obs(placeholder="新的动态热词"),
        after=_obs(placeholder="新的动态热词"),
    )

    blocker = tracker.commit_blocker(_obs(placeholder="第三个动态热词"))
    assert blocker is not None
    assert len(blocker.fields) == 1


def test_search_field_semantics_are_carried_into_effect_contract() -> None:
    tracker = FormTransactionTracker()
    search = Observation(
        url="https://example.test/explore",
        title="Explore",
        elements=[{
            "ref": "e1", "role": "searchbox", "name": "Search",
            "selector": "#search-input", "editable": True, "value": "",
            "semanticPurpose": "search",
        }],
    )
    filled = Observation(
        url=search.url,
        title=search.title,
        elements=[{**search.elements[0], "value": "工单系统"}],
    )
    tracker.record_fill(
        args={"ref": "e1", "value": "工单系统"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=search,
        after=filled,
    )

    contract = tracker.enrich_contract(EffectContract(
        action_name="Submit",
        operation_family="submit",
        side_effect="write",
        is_commit=True,
        completes_goal=True,
    ))

    assert contract.fingerprint["interaction_purpose"] == "search"
    assert contract.operation_family == "search"
    assert contract.side_effect == "none"
    assert contract.is_commit is False
    assert contract.completes_goal is False


def test_context_proven_search_enter_downgrades_semantically_incomplete_field():
    tracker = FormTransactionTracker()
    field = {
        "ref": "e1", "role": "textbox", "selector": "#query",
        "editable": True, "visible": True, "value": "",
    }
    before = Observation(url="https://example.test/", title="Search", elements=[field])
    tracker.record_fill(
        args={"ref": "e1", "value": "Askbot"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=before,
        after=Observation(
            url=before.url, title=before.title,
            elements=[{**field, "value": "Askbot"}],
        ),
    )

    contract = tracker.enrich_contract(
        EffectContract(
            action_name="Press Enter", operation_family="submit",
            side_effect="write", is_commit=True, completes_goal=True,
        ),
        target={**field, "value": "Askbot"},
        purpose_override="search",
    )

    assert contract.operation_family == "search"
    assert contract.is_commit is False


def test_context_purpose_cannot_downgrade_explicit_business_operation():
    tracker = FormTransactionTracker()
    before = _obs()
    tracker.record_fill(
        args={"ref": "e1", "value": "draft body"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=before,
        after=_obs(value="draft body"),
    )

    contract = tracker.enrich_contract(
        EffectContract(
            action_name="Publish", operation_family="publish",
            side_effect="write", is_commit=True, completes_goal=True,
        ),
        purpose_override="search",
    )

    assert contract.operation_family == "publish"
    assert contract.is_commit is True


def test_generic_submit_inherits_search_from_explicit_field_association() -> None:
    tracker = FormTransactionTracker()
    search = Observation(
        url="https://example.test/explore",
        title="Explore",
        elements=[{
            "ref": "e1", "role": "searchbox", "name": "Search",
            "selector": "#query", "editable": True, "value": "",
            "semanticPurpose": "search",
            "scopeId": "0:#query-shell", "scopeSelector": "#query-shell",
            "scopeLockable": True, "frameDepth": 0,
        }],
    )
    tracker.record_fill(
        args={"ref": "e1", "value": "工单系统"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=search,
        after=Observation(
            url=search.url,
            title=search.title,
            elements=[{**search.elements[0], "value": "工单系统"}],
        ),
    )
    generic_submit = {
        "ref": "e9", "role": "button", "name": "Submit",
        "selector": "#query-submit",
        # Custom SPA components may give the field and icon button different
        # inferred scopes. The sidecar's direct DOM association is authoritative.
        "scopeId": "0:#page-shell", "scopeSelector": "#page-shell",
        "scopeLockable": False, "frameDepth": 0,
        "associatedFieldSelectors": ["#query"],
    }

    contract = tracker.enrich_contract(
        EffectContract(
            action_name="Submit",
            operation_family="submit",
            side_effect="write",
            is_commit=True,
            completes_goal=True,
        ),
        target=generic_submit,
    )

    assert contract.fingerprint["interaction_purpose"] == "search"
    assert contract.operation_family == "search"
    assert contract.side_effect == "none"
    assert contract.is_commit is False
    assert contract.completes_goal is False


def test_field_association_does_not_downgrade_a_different_form_submit() -> None:
    tracker = FormTransactionTracker()
    search = Observation(
        url="https://example.test/explore",
        title="Explore",
        elements=[{
            "ref": "e1", "role": "searchbox", "name": "Search",
            "selector": "#query", "editable": True, "value": "",
            "semanticPurpose": "search",
            "scopeId": "0:#query-shell", "scopeSelector": "#query-shell",
            "scopeLockable": True, "frameDepth": 0,
        }],
    )
    tracker.record_fill(
        args={"ref": "e1", "value": "工单系统"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=search,
        after=Observation(
            url=search.url,
            title=search.title,
            elements=[{**search.elements[0], "value": "工单系统"}],
        ),
    )
    unrelated_submit = {
        "ref": "e9", "role": "button", "name": "Submit",
        "selector": "#comment-submit",
        "scopeId": "0:#comment-form", "scopeSelector": "#comment-form",
        "scopeLockable": True, "frameDepth": 0,
        "associatedFieldSelectors": ["#comment-body"],
    }

    contract = tracker.enrich_contract(
        EffectContract(
            action_name="Submit",
            operation_family="submit",
            side_effect="write",
            is_commit=True,
            completes_goal=True,
        ),
        target=unrelated_submit,
    )

    assert "interaction_purpose" not in contract.fingerprint
    assert contract.operation_family == "submit"
    assert contract.side_effect == "write"
    assert contract.is_commit is True


def test_search_context_does_not_downgrade_explicit_business_commit() -> None:
    tracker = FormTransactionTracker()
    search = Observation(
        url="https://example.test/explore",
        title="Explore",
        elements=[{
            "ref": "e1", "role": "searchbox", "name": "Search",
            "selector": "#search-input", "editable": True, "value": "",
            "semanticPurpose": "search",
        }],
    )
    tracker.record_fill(
        args={"ref": "e1", "value": "工单系统"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=search,
        after=Observation(
            url=search.url,
            title=search.title,
            elements=[{**search.elements[0], "value": "工单系统"}],
        ),
    )

    contract = tracker.enrich_contract(EffectContract(
        action_name="发布",
        operation_family="publish",
        side_effect="external",
        is_commit=True,
        completes_goal=True,
    ))

    assert "interaction_purpose" not in contract.fingerprint
    assert contract.operation_family == "publish"
    assert contract.side_effect == "external"
    assert contract.is_commit is True


def test_old_search_field_does_not_tag_unrelated_business_action() -> None:
    tracker = FormTransactionTracker()
    search = Observation(
        url="https://example.test/explore",
        title="Explore",
        elements=[{
            "ref": "e1", "role": "searchbox", "name": "Search",
            "selector": "#search-input", "editable": True, "value": "",
            "semanticPurpose": "search", "scopeId": "search-form",
            "scopeSelector": "#search-form", "frameDepth": 0,
        }],
    )
    filled = Observation(
        url=search.url,
        title=search.title,
        elements=[{**search.elements[0], "value": "工单系统"}],
    )
    tracker.record_fill(
        args={"ref": "e1", "value": "工单系统"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=search,
        after=filled,
    )
    unrelated_target = {
        "ref": "e9", "role": "button", "name": "Approve",
        "scopeId": "approval-form", "scopeSelector": "#approval-form",
        "frameDepth": 0,
    }

    contract = tracker.enrich_contract(
        EffectContract(action_name="Approve", is_commit=True),
        target=unrelated_target,
    )

    assert "interaction_purpose" not in contract.fingerprint


def test_reconciliation_checks_the_same_field_not_any_matching_value() -> None:
    tracker = FormTransactionTracker()
    before = _obs()
    tracker.record_fill(
        args={"ref": "e1", "value": "员工服务台"},
        result=None,
        ok=False,
        error="dispatch-error: timeout",
        before=before,
        after=before,
    )
    other_field_has_value = Observation(
        url=before.url,
        title=before.title,
        elements=[
            {**before.elements[0], "value": ""},
            {
                "ref": "e2", "role": "textbox", "selector": "#other-input",
                "editable": True, "value": "员工服务台",
            },
        ],
    )

    blocker = tracker.commit_blocker(other_field_has_value)

    assert blocker is not None


def test_non_editable_stale_receipt_no_longer_blocks_actions() -> None:
    tracker = FormTransactionTracker()
    stale = Observation(
        url="https://example.test/edit",
        title="test",
        elements=[{
            "ref": "e2", "role": "link", "name": "首页",
            "selector": "#home", "editable": False, "value": "",
        }],
    )
    tracker.record_fill(
        args={"ref": "e2", "value": "工单系统"},
        result=None,
        ok=False,
        error="target_not_editable",
        before=stale,
        after=stale,
    )

    assert tracker.commit_blocker(stale) is None


def test_confirmed_replacement_retires_missing_receipt_for_same_value() -> None:
    tracker = FormTransactionTracker()
    old = Observation(
        url="https://example.test/edit",
        title="test",
        elements=[{
            "ref": "e2", "role": "searchbox", "name": "Search",
            "selector": "#old-search", "editable": True, "value": "",
        }],
    )
    tracker.record_fill(
        args={"ref": "e2", "value": "工单系统"},
        result=None,
        ok=False,
        error="value_not_applied",
        before=old,
        after=old,
    )
    replacement = Observation(
        url=old.url,
        title=old.title,
        elements=[{
            "ref": "e19", "role": "searchbox", "name": "Search",
            "selector": "#new-search", "editable": True, "value": "工单系统",
        }],
    )
    tracker.record_fill(
        args={"ref": "e19", "value": "工单系统"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=replacement,
        after=replacement,
    )

    assert tracker.commit_blocker(replacement) is None
    assert len(tracker.summaries()) == 1


def test_failed_fill_blocks_dependent_button_and_enter_but_allows_refocus() -> None:
    tracker = FormTransactionTracker()
    observation = _obs()
    tracker.record_fill(
        args={"ref": "e1", "value": "员工服务台"},
        result=None,
        ok=False,
        error="target_not_focused",
        before=observation,
        after=observation,
    )

    assert tracker.dependent_action_blocker(
        observation,
        tool="browser_click",
        target={"ref": "e2", "role": "button", "name": "搜索"},
    ) is not None
    assert tracker.dependent_action_blocker(
        observation,
        tool="browser_press",
        key="Enter",
    ) is not None
    assert tracker.dependent_action_blocker(
        observation,
        tool="browser_click",
        target={"ref": "e1", "role": "textbox", "editable": True},
    ) is None


def test_unresolved_fill_only_blocks_actions_in_its_own_form_scope() -> None:
    tracker = FormTransactionTracker()
    search = {
        "ref": "search", "role": "searchbox", "editable": True,
        "selector": "#search", "scopeId": "0:header > form",
        "scopeSelector": "header > form", "frameDepth": 0, "value": "",
    }
    search_button = {
        "ref": "search-submit", "role": "button", "editable": False,
        "selector": "#search-submit", "scopeId": "0:header > form",
        "scopeSelector": "header > form", "frameDepth": 0,
    }
    comment_button = {
        "ref": "comment-submit", "role": "button", "editable": False,
        "selector": "#comment-submit", "scopeId": "0:article > footer",
        "scopeSelector": "article > footer", "frameDepth": 0,
    }
    observation = Observation(
        url="https://example.test/post",
        title="test",
        elements=[search, search_button, comment_button],
    )
    tracker.record_fill(
        args={"ref": "search", "value": "工单系统"},
        result={"fill_receipt": {"status": "ambiguous", "reason": "target replaced"}},
        ok=True,
        error=None,
        before=observation,
        after=observation,
    )

    assert tracker.dependent_action_blocker(
        observation,
        tool="browser_click",
        target=search_button,
    ) is not None
    assert tracker.dependent_action_blocker(
        observation,
        tool="browser_click",
        target=comment_button,
    ) is None


def test_missing_unresolved_fill_receipt_expires_after_fresh_observations() -> None:
    tracker = FormTransactionTracker()
    before = _obs()
    tracker.record_fill(
        args={"ref": "e1", "value": "员工服务台"},
        result={"fill_receipt": {"status": "ambiguous", "reason": "target replaced"}},
        ok=True,
        error=None,
        before=before,
        after=before,
    )
    missing = Observation(url=before.url, title=before.title, elements=[])

    tracker.reconcile(missing)
    tracker.reconcile(missing)

    assert tracker.commit_blocker(missing) is None


def test_navigation_retires_unresolved_fill_receipt() -> None:
    tracker = FormTransactionTracker()
    before = _obs()
    tracker.record_fill(
        args={"ref": "e1", "value": "员工服务台"},
        result={"fill_receipt": {"status": "ambiguous", "reason": "target replaced"}},
        ok=True,
        error=None,
        before=before,
        after=before,
    )
    next_page = Observation(
        url="https://example.test/results",
        title="results",
        elements=[],
    )

    assert tracker.commit_blocker(next_page) is None


def test_press_binding_reconciles_an_ambiguous_fill_before_dispatch() -> None:
    tracker = FormTransactionTracker()
    before = _obs()
    tracker.record_fill(
        args={"ref": "e1", "value": "员工服务台"},
        result={"fill_receipt": {"status": "ambiguous", "reason": "target replaced"}},
        ok=True,
        error=None,
        before=before,
        after=before,
    )

    decision = tracker.bind_interaction_target(
        Decision(tool="browser_press", args={"key": "Enter"}),
        _obs(value="员工服务台"),
    )

    assert decision.args["ref"] == "e1"


def test_outcome_evidence_uses_confirmed_non_secret_values_without_exposing_content() -> None:
    tracker = FormTransactionTracker()
    tracker.record_fill(
        args={"ref": "e1", "value": "通用发布内容"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=_obs(),
        after=_obs(value="通用发布内容"),
    )

    evidence = tracker.outcome_evidence(_obs(page_text="列表中展示：通用发布内容"))
    enriched = tracker.enrich_contract(EffectContract(action_name="发布", is_commit=True))

    assert len(evidence) == 1
    assert evidence[0].kind == "submitted_value_added_to_result"
    assert "通用发布内容" not in enriched.model_dump_json()
    assert enriched.fingerprint["confirmed_fill_count"] == 1


def test_outcome_evidence_requires_a_new_result_occurrence() -> None:
    tracker = FormTransactionTracker()
    existing = _obs(page_text="列表中已经存在：通用发布内容")
    tracker.record_fill(
        args={"ref": "e1", "value": "通用发布内容"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=existing,
        after=_obs(value="通用发布内容", page_text=existing.page_text),
    )

    evidence = tracker.outcome_evidence(_obs(page_text=existing.page_text))

    assert all(item.kind != "submitted_value_added_to_result" for item in evidence)


def test_historical_search_fill_cannot_confirm_a_later_commit() -> None:
    tracker = FormTransactionTracker()
    search = _obs()
    tracker.record_fill(
        args={"ref": "e1", "value": "历史搜索词"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=search,
        after=_obs(value="历史搜索词"),
    )
    tracker.record_fill(
        args={"ref": "e1", "value": "本次准备提交的正文"},
        result={"fill_receipt": {"status": "confirmed", "reason": "verified"}},
        ok=True,
        error=None,
        before=_obs(),
        after=_obs(value="本次准备提交的正文"),
    )

    evidence = tracker.outcome_evidence(_obs(page_text="页面仍展示历史搜索词"))

    assert evidence == []


def test_confirmed_form_transaction_survives_checkpoint_restore() -> None:
    before = Observation(
        url="https://example.test/post/1",
        title="Post",
        elements=[{
            "ref": "comment-old",
            "role": "textbox",
            "name": "Comment",
            "editable": True,
            "scopeId": "comment-form",
            "scopeSelector": "#comment-form",
        }],
    )
    after = Observation(
        url=before.url,
        title=before.title,
        elements=[{**before.elements[0], "ref": "comment-new", "value": "hello"}],
    )
    tracker = FormTransactionTracker()
    tracker.record_fill(
        args={"ref": "comment-old", "value": "hello"},
        result={"fill_receipt": {"status": "confirmed"}},
        ok=True,
        error=None,
        before=before,
        after=after,
    )

    restored = FormTransactionTracker()
    restored.restore_state(tracker.export_state())
    state = restored.interaction_scope_state(after)

    assert restored.has_confirmed_fill() is True
    assert state is not None
    assert state["scope_id"] == "comment-form"
