from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .contracts import EffectContract, EffectEvidence, EffectReceipt
from .discovery import discover_effect_contract, read_only_navigation_contract
from .interaction_transition import detect_interaction_transition, has_editable_surface
from .local_interaction_policy import local_read_only_interaction_contract
from .pending_boundary import breaks_pending_verification
from .semantic_alignment import SemanticAlignment, assess_target_alignment
from .verifier import verify_effect


logger = logging.getLogger(__name__)


@dataclass
class PreparedEffect:
    target_key: str
    contract: EffectContract
    before: Observation


class SemanticActionRejected(RuntimeError):
    def __init__(self, alignment: SemanticAlignment) -> None:
        self.alignment = alignment
        super().__init__(alignment.reason or "浏览器目标元素与任务业务对象不一致")


class EffectTracker:
    def __init__(self, *, goal: str, capability_id: str, lang: str, original_request: str = "", llm: Any = None) -> None:
        self.goal = goal
        self.capability_id = capability_id
        self.lang = lang
        self.original_request = original_request
        self.llm = llm
        self._discovered: Dict[str, EffectContract] = {}
        self._receipts: Dict[str, EffectReceipt] = {}
        self._pending: Dict[str, PreparedEffect] = {}
        self._alignments: Dict[str, SemanticAlignment] = {}
        self._editor_intended: tuple[str, str] | None = None
        self._refresh_attempts: Dict[str, int] = {}
        self.max_refresh_attempts = 3

    async def prepare_click(self, *, target: Dict[str, Any], before: Observation) -> Optional[PreparedEffect]:
        target_key = self._target_key(target, before)
        contract = self._discovered.get(target_key)
        if contract is None:
            contract = local_read_only_interaction_contract(target, before)
        if contract is None:
            contract = read_only_navigation_contract(target)
        if contract is None:
            contract = await discover_effect_contract(
                goal=self.goal,
                capability_id=self.capability_id,
                target=target,
                lang=self.lang,
                original_request=self.original_request,
                llm=self.llm,
            )
        self._discovered[target_key] = contract
        if not contract.is_commit:
            return None

        alignment = self._alignments.get(target_key)
        if alignment is None:
            alignment = await assess_target_alignment(
                goal=self.goal,
                original_request=self.original_request,
                target=target,
                lang=self.lang,
                llm=self.llm,
            )
            self._alignments[target_key] = alignment
        if (
            has_editable_surface(before)
            and not alignment.intended.entity.strip()
            and self._editor_intended is not None
        ):
            operation, entity = self._editor_intended
            alignment = alignment.model_copy(update={
                "intended": alignment.intended.model_copy(update={
                    "operation": operation,
                    "entity": entity,
                    "confidence": max(alignment.intended.confidence, 0.8),
                    "evidence": "business object inherited from the action that opened this editor",
                }),
            })
        if alignment.blocks_action:
            raise SemanticActionRejected(alignment)
        contract = contract.model_copy(update={
            "intended_operation": alignment.intended.operation,
            "intended_entity": alignment.intended.entity,
            "target_operation": alignment.observed.operation,
            "target_entity": alignment.observed.entity,
            "semantic_confidence": alignment.confidence,
            "fingerprint": {
                **dict(contract.fingerprint),
                "interaction_target_id": _interaction_target_id(target),
            },
        })
        self._discovered[target_key] = contract
        return PreparedEffect(target_key=target_key, contract=contract, before=before)

    def prepare_submit_press(
        self,
        *,
        key: str,
        target: Dict[str, Any],
        before: Observation,
    ) -> Optional[PreparedEffect]:
        """Track a form submission dispatched by Enter/Return.

        The form transaction later refines search/query fields to a read-only
        interaction, so only an active business form reaches effect checking.
        """
        if str(key or "").strip().lower() not in {"enter", "return"}:
            return None
        target_key = f"press:{self._target_key(target, before)}"
        contract = EffectContract(
            action_name=f"Press {key}",
            operation_family="submit",
            side_effect="write",
            is_commit=True,
            completes_goal=True,
            source="local_rule",
            fingerprint={"interaction_target_id": _interaction_target_id(target)},
        )
        self._discovered[target_key] = contract
        return PreparedEffect(target_key=target_key, contract=contract, before=before)

    def replay_blocker(self, prepared: PreparedEffect) -> Optional[EffectReceipt]:
        receipt = self._receipts.get(prepared.contract.key())
        return receipt if receipt and receipt.blocks_replay else None

    def update_contract(
        self,
        prepared: PreparedEffect,
        contract: EffectContract,
    ) -> Optional[PreparedEffect]:
        prepared.contract = contract
        self._discovered[prepared.target_key] = contract
        if (
            not contract.is_commit
            and dict(contract.fingerprint or {}).get("commit_precondition")
            == "entry_transition"
        ):
            self._remember_editor_intent(contract)
        return prepared if contract.is_commit else None

    async def record(
        self,
        *,
        prepared: PreparedEffect,
        after: Observation,
        supplemental_evidence: List[EffectEvidence] | None = None,
    ) -> Optional[EffectReceipt]:
        transition = detect_interaction_transition(before=prepared.before, after=after)
        confirmed_fill_count = int(
            dict(prepared.contract.fingerprint or {}).get("confirmed_fill_count") or 0
        )
        if transition is not None and (
            prepared.contract.source == "model"
            or confirmed_fill_count == 0
        ):
            self._remember_editor_intent(prepared.contract)
            self._discovered[prepared.target_key] = prepared.contract.model_copy(
                update={"is_commit": False, "side_effect": "none", "completes_goal": False},
            )
            logger.info(
                "browser click reclassified as interaction transition",
                extra={
                    "event": "browser.effect_reclassified_interaction",
                    "action": prepared.contract.action_name,
                    "transition": transition.kind,
                    "reason": transition.reason,
                },
            )
            return None
        receipt = await verify_effect(
            contract=prepared.contract,
            before=prepared.before,
            after=after,
            lang=self.lang,
            llm=self.llm,
            supplemental_evidence=supplemental_evidence,
        )
        self._receipts[receipt.contract_key] = receipt
        if receipt.status in {"pending", "unknown"}:
            self._pending[receipt.contract_key] = prepared
        else:
            self._pending.pop(receipt.contract_key, None)
            self._editor_intended = None
        return receipt

    def _remember_editor_intent(self, contract: EffectContract) -> None:
        if contract.intended_entity.strip():
            self._editor_intended = (
                contract.intended_operation,
                contract.intended_entity,
            )

    def defer_until_fresh_observation(
        self,
        *,
        prepared: PreparedEffect,
        reason: str,
    ) -> EffectReceipt:
        contract = prepared.contract
        receipt = EffectReceipt(
            contract_key=contract.key(),
            status="unknown",
            confidence=0.0,
            action_name=contract.action_name,
            operation_family=contract.operation_family,
            entity=contract.entity,
            side_effect=contract.side_effect,
            completes_goal=contract.completes_goal,
            fingerprint=contract.fingerprint,
            verification_hints=contract.verification_hints,
            intended_operation=contract.intended_operation,
            intended_entity=contract.intended_entity,
            target_operation=contract.target_operation,
            target_entity=contract.target_entity,
            reason=reason,
            business_action_id=contract.business_action_id,
            action_attempt_id=contract.action_attempt_id,
            business_target_id=contract.business_target_id,
            observation_revision=contract.observation_revision,
        )
        self._receipts[receipt.contract_key] = receipt
        self._pending[receipt.contract_key] = prepared
        return receipt

    async def refresh_pending(
        self,
        *,
        after: Observation,
        supplemental_evidence: List[EffectEvidence] | None = None,
    ) -> List[EffectReceipt]:
        changed: List[EffectReceipt] = []
        for contract_key, prepared in list(self._pending.items()):
            attempts = self._refresh_attempts.get(contract_key, 0) + 1
            self._refresh_attempts[contract_key] = attempts
            previous = self._receipts.get(contract_key)
            receipt = await verify_effect(
                contract=prepared.contract,
                before=prepared.before,
                after=after,
                lang=self.lang,
                llm=self.llm,
                supplemental_evidence=supplemental_evidence,
            )
            self._receipts[contract_key] = receipt
            if receipt.status not in {"pending", "unknown"}:
                self._pending.pop(contract_key, None)
                self._refresh_attempts.pop(contract_key, None)
            elif attempts >= self.max_refresh_attempts:
                receipt = receipt.model_copy(update={
                    "fingerprint": {
                        **dict(receipt.fingerprint or {}),
                        "verification_exhausted": True,
                    },
                    "reason": (
                        f"{receipt.reason}; verification budget exhausted"
                        if receipt.reason else "verification budget exhausted"
                    ),
                })
                self._receipts[contract_key] = receipt
                self._pending.pop(contract_key, None)
            if previous is None or (receipt.status, receipt.reason) != (previous.status, previous.reason):
                changed.append(receipt)
        return changed

    def receipts(self) -> list[Dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self._receipts.values()]

    def receipt(self, contract_key: str) -> Optional[EffectReceipt]:
        return self._receipts.get(str(contract_key or ""))

    def adopt_manual_receipt(self, receipt: EffectReceipt) -> None:
        """Replace an exhausted receipt with the human's explicit outcome."""
        self._receipts[receipt.contract_key] = receipt
        self._pending.pop(receipt.contract_key, None)
        self._refresh_attempts.pop(receipt.contract_key, None)

    def pending_receipts(self) -> List[EffectReceipt]:
        return [
            self._receipts[key]
            for key in self._pending
            if key in self._receipts
        ]

    def supersede_pending_for_action(
        self,
        decision: Decision,
        *,
        preserve_contract_key: str = "",
    ) -> List[EffectReceipt]:
        """Stop older receipts from absorbing changes caused by a new action."""
        if not breaks_pending_verification(decision):
            return []
        changed: List[EffectReceipt] = []
        for contract_key in list(self._pending):
            if preserve_contract_key and contract_key == preserve_contract_key:
                continue
            previous = self._receipts.get(contract_key)
            if previous is None:
                self._pending.pop(contract_key, None)
                self._refresh_attempts.pop(contract_key, None)
                continue
            receipt = previous.model_copy(update={
                "fingerprint": {
                    **dict(previous.fingerprint or {}),
                    "verification_superseded": True,
                },
                "reason": (
                    f"{previous.reason}; verification window superseded by a later interaction"
                    if previous.reason else
                    "verification window superseded by a later interaction"
                ),
            })
            self._receipts[contract_key] = receipt
            self._pending.pop(contract_key, None)
            self._refresh_attempts.pop(contract_key, None)
            changed.append(receipt)
        return changed

    def export_state(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "discovered": {
                key: value.model_dump(mode="json")
                for key, value in self._discovered.items()
            },
            "receipts": {
                key: value.model_dump(mode="json")
                for key, value in self._receipts.items()
            },
            "pending": {
                key: {
                    "target_key": prepared.target_key,
                    "contract": prepared.contract.model_dump(mode="json"),
                    "before": _observation_state(prepared.before),
                }
                for key, prepared in self._pending.items()
            },
            "editor_intended": list(self._editor_intended) if self._editor_intended else None,
            "refresh_attempts": dict(self._refresh_attempts),
            "max_refresh_attempts": self.max_refresh_attempts,
        }

    def restore_state(self, payload: Dict[str, Any]) -> None:
        self._discovered = {
            str(key): EffectContract.model_validate(value)
            for key, value in dict((payload or {}).get("discovered") or {}).items()
            if isinstance(value, dict)
        }
        self._receipts = {
            str(key): EffectReceipt.model_validate(value)
            for key, value in dict((payload or {}).get("receipts") or {}).items()
            if isinstance(value, dict)
        }
        self._pending = {}
        for key, value in dict((payload or {}).get("pending") or {}).items():
            if not isinstance(value, dict) or not isinstance(value.get("contract"), dict):
                continue
            self._pending[str(key)] = PreparedEffect(
                target_key=str(value.get("target_key") or ""),
                contract=EffectContract.model_validate(value["contract"]),
                before=_observation_from_state(value.get("before") or {}),
            )
        editor_intended = (payload or {}).get("editor_intended")
        self._editor_intended = (
            (str(editor_intended[0]), str(editor_intended[1]))
            if isinstance(editor_intended, list) and len(editor_intended) == 2
            else None
        )
        self._refresh_attempts = {
            str(key): max(0, int(value))
            for key, value in dict((payload or {}).get("refresh_attempts") or {}).items()
        }
        self.max_refresh_attempts = max(
            1,
            int((payload or {}).get("max_refresh_attempts") or self.max_refresh_attempts),
        )

    @staticmethod
    def _target_key(target: Dict[str, Any], observation: Observation) -> str:
        phase = "editing" if has_editable_surface(observation) else "viewing"
        return "\x00".join([
            phase,
            _interaction_target_id(target),
            *(str(target.get(key) or "").strip().lower() for key in ("role", "name", "text", "type")),
        ])


def _interaction_target_id(target: Dict[str, Any]) -> str:
    frame = str(target.get("frameDepth") or 0)
    backend = str(target.get("backendNodeId") or "").strip()
    selector = str(target.get("selector") or "").strip()
    href = str(target.get("href") or "").strip()
    scope = str(target.get("scopeId") or target.get("scopeSelector") or "").strip()
    ref = str(target.get("ref") or "").strip()
    locator = (
        f"backend:{backend}" if backend else
        f"selector:{selector}" if selector else
        f"href:{href}" if href else
        f"scope:{scope}:ref:{ref}" if scope else
        f"ref:{ref}"
    )
    semantic = "\x00".join(
        str(target.get(key) or "").strip().casefold()
        for key in ("role", "name", "text", "type")
    )
    raw = f"{frame}\x00{locator}\x00{semantic}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _observation_state(observation: Observation) -> Dict[str, Any]:
    return {
        "url": observation.url,
        "title": observation.title,
        "revision": observation.revision,
        "state_fingerprint": observation.state_fingerprint,
        "page_text": str(observation.page_text or "")[:16000],
        "elements": list(observation.elements or [])[:240],
        "effects": list(observation.effects or [])[-40:],
        "frame_count": observation.frame_count,
    }


def _observation_from_state(payload: Dict[str, Any]) -> Observation:
    return Observation(
        url=str(payload.get("url") or ""),
        title=str(payload.get("title") or ""),
        revision=str(payload.get("revision") or ""),
        state_fingerprint=str(payload.get("state_fingerprint") or ""),
        elements=list(payload.get("elements") or []),
        page_text=str(payload.get("page_text") or ""),
        effects=list(payload.get("effects") or []),
        frame_count=max(1, int(payload.get("frame_count") or 1)),
    )
