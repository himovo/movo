from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation
from app.enterprise_capabilities.browser.engine.form_input.identity import field_label, find_field, stable_field_key
from app.enterprise_capabilities.browser.engine.form_input.value_equivalence import field_values_equivalent

from .contracts import EffectContract, EffectEvidence, EffectReceipt
from .form_scope import FormScopeLock, ScopeBlocker
from .interaction_contract import refine_contract_for_interaction
from .interaction_purpose import resolve_interaction_purpose
from .scope_identity import ScopeIdentity, scope_identity, scope_present, scopes_related


FillStatus = Literal["confirmed", "ambiguous", "failed"]


@dataclass
class FieldReceipt:
    field_key: str
    label: str
    expected_value: str
    value_hash: str
    status: FillStatus
    reason: str
    baseline_result_count: int = 0
    origin_url: str = ""
    scope_id: str = ""
    scope_selector: str = ""
    frame_depth: int = 0
    missing_observations: int = 0
    secret: bool = False
    target: Dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class CommitBlocker:
    fields: tuple[str, ...]
    reason: str


class FormTransactionTracker:
    """Tracks fill postconditions and gates commits within one browser node."""

    def __init__(self) -> None:
        self._fields: Dict[str, FieldReceipt] = {}
        self._scope_lock = FormScopeLock()

    def record_fill(
        self,
        *,
        args: Dict[str, Any],
        result: Any,
        ok: bool,
        error: Optional[str],
        before: Observation,
        after: Observation,
    ) -> FieldReceipt:
        ref = str(args.get("ref") or "").strip()
        target = next(
            (
                item for item in before.elements
                if isinstance(item, dict) and str(item.get("ref") or "").strip() == ref
            ),
            {},
        )
        value = str(args.get("value") or "")
        key = stable_field_key(target) if target else f"ref:{ref}"
        label = field_label(target, ref)
        local = result.get("fill_receipt") if isinstance(result, dict) else None
        local_status = str(local.get("status") or "") if isinstance(local, dict) else ""
        if ok and local_status == "ambiguous":
            status: FillStatus = "ambiguous"
            reason = str(local.get("reason") or "filled value could not be verified")
        elif ok:
            # Older sidecars only returned success after their own value check.
            status = "confirmed"
            reason = str(local.get("reason") or "fill completed and was verified by the browser agent") if isinstance(local, dict) else "fill completed"
        else:
            status = "ambiguous" if _is_post_input_identity_error(error) else "failed"
            reason = str(error or "fill failed")
        receipt = FieldReceipt(
            field_key=key,
            label=label,
            expected_value=value,
            value_hash=_value_hash(value),
            status=status,
            reason=reason,
            baseline_result_count=_result_occurrences(before, value),
            origin_url=str(before.url or ""),
            scope_id=str(target.get("scopeId") or ""),
            scope_selector=str(target.get("scopeSelector") or ""),
            frame_depth=int(target.get("frameDepth") or 0),
            secret=_is_secret_field(target),
            target=dict(target),
        )
        if receipt.status == "confirmed":
            self._retire_superseded_receipts(receipt, after)
        self._fields[key] = receipt
        self.reconcile(after)
        recorded = self._fields.get(key, receipt)
        if recorded.status == "confirmed" and target:
            self._scope_lock.record_confirmed_fill(target, after)
        return recorded

    def reconcile(self, observation: Observation) -> None:
        if not observation.fresh:
            return
        self._scope_lock.reconcile(observation)
        for key, receipt in list(self._fields.items()):
            if receipt.status == "confirmed":
                continue
            current = _find_receipt_field(observation, receipt)
            page_changed = bool(
                receipt.origin_url
                and observation.url
                and receipt.origin_url != str(observation.url)
            )
            if page_changed:
                self._fields.pop(key, None)
                continue
            if current is not None and not current.get("editable"):
                self._fields.pop(key, None)
                continue
            if current is None:
                missing = receipt.missing_observations + 1
                receipt_scope = _receipt_scope(receipt)
                scope_gone = bool(
                    receipt_scope is not None
                    and not scope_present(
                        receipt_scope,
                        (item for item in observation.elements if isinstance(item, dict)),
                    )
                )
                if scope_gone or missing >= 2:
                    self._fields.pop(key, None)
                else:
                    self._fields[key] = FieldReceipt(
                        **{**receipt.__dict__, "missing_observations": missing},
                    )
                continue
            if field_values_equivalent(
                current.get("value"),
                receipt.expected_value,
                target=receipt.target,
            ):
                confirmed = FieldReceipt(
                    **{**receipt.__dict__, "status": "confirmed", "reason": "value confirmed in a fresh observation"},
                )
                self._fields[key] = confirmed
                self._scope_lock.record_confirmed_fill(current, observation)

    def bind_interaction_target(
        self,
        decision: Decision,
        observation: Observation,
    ) -> Decision:
        self.reconcile(observation)
        bound = self._scope_lock.bind_press_target(decision, observation)
        if (
            bound.tool != "browser_press"
            or str((bound.args or {}).get("ref") or "").strip()
        ):
            return bound
        target = self._latest_confirmed_field(observation)
        if target is None:
            return bound
        args = dict(bound.args or {})
        args["ref"] = str(target.get("ref") or "")
        return Decision(tool=bound.tool, args=args, rationale=bound.rationale)

    def resolve_interaction_target(
        self,
        decision: Decision,
        observation: Observation,
    ) -> Optional[Dict[str, Any]]:
        return self._scope_lock.resolve_target(decision, observation)

    def _latest_confirmed_field(
        self,
        observation: Observation,
    ) -> Optional[Dict[str, Any]]:
        for receipt in reversed(list(self._fields.values())):
            if receipt.status != "confirmed":
                continue
            current = _find_receipt_field(observation, receipt)
            if current is not None and current.get("editable"):
                return current
        return None

    def interaction_scope_blocker(
        self,
        decision: Decision,
        observation: Observation,
    ) -> Optional[ScopeBlocker]:
        return self._scope_lock.blocker(
            decision,
            observation,
            related_fields=self._confirmed_targets(observation),
        )

    def interaction_scope_state(
        self,
        observation: Observation,
    ) -> Optional[Dict[str, Any]]:
        return self._scope_lock.planner_state(
            observation,
            related_fields=self._confirmed_targets(observation),
        )

    def _confirmed_targets(
        self,
        observation: Observation,
    ) -> List[Dict[str, Any]]:
        targets: List[Dict[str, Any]] = []
        for receipt in self._fields.values():
            if receipt.status != "confirmed":
                continue
            current = _find_receipt_field(observation, receipt)
            if current is not None:
                targets.append(current)
        return targets

    def after_action(
        self,
        decision: Decision,
        *,
        before: Observation,
        after: Observation,
        ok: bool,
    ) -> None:
        self._scope_lock.after_action(decision, before=before, after=after, ok=ok)
        self.reconcile(after)

    def after_effect(self, receipt: EffectReceipt, observation: Observation) -> None:
        self._scope_lock.after_effect(receipt, observation)

    def _retire_superseded_receipts(
        self,
        replacement: FieldReceipt,
        observation: Observation,
    ) -> None:
        expected = _normalize(replacement.expected_value)
        if not expected:
            return
        for key, receipt in list(self._fields.items()):
            if key == replacement.field_key or receipt.status == "confirmed":
                continue
            if _normalize(receipt.expected_value) != expected:
                continue
            current = _find_receipt_field(observation, receipt)
            if current is None or not current.get("editable"):
                self._fields.pop(key, None)

    def commit_blocker(
        self,
        observation: Observation,
        *,
        target: Optional[Dict[str, Any]] = None,
    ) -> Optional[CommitBlocker]:
        self.reconcile(observation)
        unresolved = [
            item.label
            for item in self._fields.values()
            if item.status != "confirmed" and _receipt_blocks_target(item, target)
        ]
        if not unresolved:
            return None
        return CommitBlocker(
            fields=tuple(unresolved),
            reason="存在已尝试填写但尚未确认写入的字段",
        )

    def dependent_action_blocker(
        self,
        observation: Observation,
        *,
        tool: str,
        target: Optional[Dict[str, Any]] = None,
        key: str = "",
    ) -> Optional[CommitBlocker]:
        """Block actions that consume an unverified field value.

        This is broader than a business commit: a search button or Enter key
        can consume the current input and navigate before any external write
        occurs. Plain field focusing and cancellation controls stay allowed.
        """
        blocker = self.commit_blocker(observation, target=target)
        if blocker is None:
            return None
        if tool == "browser_press":
            return blocker if str(key or "").strip().lower() in {"enter", "return"} else None
        if tool != "browser_click" or not isinstance(target, dict):
            return None
        if target.get("editable"):
            return None
        role = str(target.get("role") or "").strip().lower()
        element_type = str(target.get("type") or "").strip().lower()
        if role not in {"button", "menuitem"} and element_type not in {"submit", "button"}:
            return None
        label = _normalize(" ".join(str(target.get(name) or "") for name in ("name", "text", "value")))
        if re.fullmatch(r"(取消|关闭|返回|放弃|cancel|close|back|dismiss)", label, re.I):
            return None
        return blocker

    def enrich_contract(
        self,
        contract: EffectContract,
        *,
        target: Optional[Dict[str, Any]] = None,
        purpose_override: str = "",
    ) -> EffectContract:
        confirmed = [item for item in self._fields.values() if item.status == "confirmed"]
        if not confirmed:
            return contract
        resolution = resolve_interaction_purpose(
            action_target=target,
            filled_targets=[item.target for item in confirmed],
        )
        resolved_purpose = str(purpose_override or resolution.purpose or "").strip()
        if target is None:
            scoped = confirmed
        elif resolution.matched_indexes:
            scoped = [confirmed[index] for index in resolution.matched_indexes]
        else:
            scoped = [
                item for item in confirmed
                if _receipt_matches_target_scope(item, target)
            ]
        if target is not None and not scoped and not resolved_purpose:
            return contract
        fingerprint = dict(contract.fingerprint)
        fingerprint["confirmed_fill_count"] = len(scoped)
        fingerprint["confirmed_fill_hashes"] = [item.value_hash for item in scoped if not item.secret]
        enriched = contract.model_copy(update={"fingerprint": fingerprint})
        return refine_contract_for_interaction(
            enriched,
            purpose=resolved_purpose,
        )

    def outcome_evidence(self, observation: Observation) -> List[EffectEvidence]:
        corpus = _observation_corpus(observation)
        editable_values = {
            _normalize(str(item.get("value") or item.get("text") or ""))
            for item in observation.elements
            if isinstance(item, dict) and item.get("editable")
        }
        evidence: List[EffectEvidence] = []
        confirmed_candidates = [
            item for item in self._fields.values()
            if item.status == "confirmed" and not item.secret and len(_normalize(item.expected_value)) >= 4
        ]
        # A browser node may have filled search boxes long before opening the
        # final editor. Only the most recently confirmed payload is eligible
        # for deterministic result-placement proof; older fields must not turn
        # unrelated page content into a successful commit.
        primary_candidates = confirmed_candidates[-1:]
        for index, receipt in enumerate(primary_candidates):
            expected = _normalize(receipt.expected_value)
            # Seeing the value still inside the editor only proves the fill,
            # not the committed business result.
            if expected in editable_values:
                continue
            if expected not in corpus:
                continue
            result_count = _result_occurrences(observation, receipt.expected_value)
            if result_count > receipt.baseline_result_count:
                evidence.append(EffectEvidence(
                    evidence_id=f"field_added:{index}:{receipt.value_hash[:10]}:{result_count}",
                    kind="submitted_value_added_to_result",
                    detail=(
                        f"已确认字段“{receipt.label}”的值从编辑区进入结果区，"
                        f"结果区匹配数 {receipt.baseline_result_count} -> {result_count}"
                    ),
                    polarity="positive",
                    weight=0.95,
                ))
                continue
            evidence.append(EffectEvidence(
                evidence_id=f"field:{index}:{receipt.value_hash[:10]}",
                kind="submitted_value_present",
                detail=f"提交后的页面包含已确认字段“{receipt.label}”的值",
                polarity="positive",
                weight=0.85,
            ))
        return evidence[:8]

    def summaries(self) -> List[Dict[str, Any]]:
        return [
            {
                "field": item.label,
                "status": item.status,
                "value_hash": item.value_hash,
                "reason": item.reason,
            }
            for item in self._fields.values()
        ]

    def has_confirmed_fill(self) -> bool:
        return any(item.status == "confirmed" for item in self._fields.values())

    def has_confirmed_value(self, values: List[str]) -> bool:
        """Return whether a confirmed fill came from the supplied payload."""
        expected_hashes = {
            _value_hash(str(value or ""))
            for value in values
            if str(value or "").strip()
        }
        if not expected_hashes:
            return False
        return any(
            item.status == "confirmed" and item.value_hash in expected_hashes
            for item in self._fields.values()
        )

    def export_state(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "fields": [
                {
                    **{
                        key: value
                        for key, value in receipt.__dict__.items()
                        if key != "target"
                    },
                    "target": dict(receipt.target),
                }
                for receipt in self._fields.values()
            ],
            "scope_lock": self._scope_lock.export_state(),
        }

    def restore_state(self, payload: Dict[str, Any]) -> None:
        self._fields = {}
        for item in list((payload or {}).get("fields") or []):
            if not isinstance(item, dict):
                continue
            try:
                receipt = FieldReceipt(**item)
            except (TypeError, ValueError):
                continue
            self._fields[receipt.field_key] = receipt
        self._scope_lock.restore_state(dict((payload or {}).get("scope_lock") or {}))


def _find_receipt_field(
    observation: Observation,
    receipt: FieldReceipt,
) -> Optional[Dict[str, Any]]:
    target = receipt.target
    has_stable_locator = bool(
        str(target.get("selector") or "").strip()
        or target.get("backendNodeId") not in (None, "")
    )
    return find_field(
        observation.elements,
        target,
        "" if has_stable_locator else str(target.get("ref") or ""),
    )


def _receipt_scope(receipt: FieldReceipt) -> Optional[ScopeIdentity]:
    target_scope = scope_identity(receipt.target)
    if target_scope is not None:
        return target_scope
    if not receipt.scope_id and not receipt.scope_selector:
        return None
    return ScopeIdentity(
        scope_id=receipt.scope_id or f"{receipt.frame_depth}:{receipt.scope_selector}",
        selector=receipt.scope_selector,
        frame_depth=receipt.frame_depth,
    )


def _receipt_blocks_target(
    receipt: FieldReceipt,
    target: Optional[Dict[str, Any]],
) -> bool:
    if target is None:
        return True
    target_scope = scope_identity(target)
    receipt_scope = _receipt_scope(receipt)
    if target_scope is None or receipt_scope is None:
        return True
    return scopes_related(receipt_scope, target_scope)


def _receipt_matches_target_scope(
    receipt: FieldReceipt,
    target: Optional[Dict[str, Any]],
) -> bool:
    if target is None:
        return True
    target_scope = scope_identity(target)
    receipt_scope = _receipt_scope(receipt)
    return bool(
        target_scope is not None
        and receipt_scope is not None
        and scopes_related(receipt_scope, target_scope)
    )


def _is_secret_field(target: Dict[str, Any]) -> bool:
    field_type = str(target.get("type") or "").strip().lower()
    label = " ".join(str(target.get(key) or "") for key in ("name", "placeholder", "text")).lower()
    return field_type == "password" or bool(re.search(r"(密码|口令|验证码|password|passcode|otp|secret|token)", label))


def _interaction_purpose(target: Dict[str, Any]) -> str:
    semantic = str(target.get("semanticPurpose") or "").strip().lower()
    if semantic:
        return semantic
    if target.get("searchContext") or str(target.get("role") or "").strip().lower() == "searchbox":
        return "search"
    return ""


def _is_post_input_identity_error(error: Optional[str]) -> bool:
    text = str(error or "").lower()
    return "target_not_found" in text and "after input" in text


def _observation_corpus(observation: Observation) -> str:
    values: List[str] = [str(observation.page_text or "")]
    for item in observation.elements:
        if not isinstance(item, dict):
            continue
        values.extend(str(item.get(key) or "") for key in ("name", "text", "value"))
    return _normalize("\n".join(values))


def _result_occurrences(observation: Observation, value: str) -> int:
    expected = _normalize(value)
    if not expected:
        return 0
    # page_text is the canonical rendered-text surface and avoids counting the
    # same DOM node repeatedly through name/text/value accessibility aliases.
    page_text = _normalize(observation.page_text or "")
    if page_text:
        return page_text.count(expected)
    result_values: List[str] = []
    for item in observation.elements:
        if not isinstance(item, dict) or item.get("editable"):
            continue
        result_values.extend(str(item.get(key) or "") for key in ("name", "text"))
    return _normalize("\n".join(result_values)).count(expected)


def _value_hash(value: str) -> str:
    return hashlib.sha256(_normalize(value).encode("utf-8")).hexdigest()[:20]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()
