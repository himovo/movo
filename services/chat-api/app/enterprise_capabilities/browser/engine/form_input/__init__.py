"""Runtime form-input planning for the native-CDP browser agent."""

from .contracts import FieldBinding, FieldDescriptor, FormInputPlan
from .binding_authority import normalize_authoritative_fill
from .commit_binding import CommitBindingLedger, commit_control_key
from .commit_resolver import (
    CommitResolution,
    is_commit_control_for_fields,
    is_semantic_commit_control,
    resolve_form_commit,
)
from .commit_dispatch_guard import CommitDispatchGuard, guard_dirty_form_commit
from .commit_replanning import replan_rejected_commit
from .input_context import BrowserInputContext, InputCandidate
from .inventory import discover_fields, is_business_form, page_signature
from .model_fallback import FormInputModelResolver
from .media_handoff import augment_media_handoff_ledger, pending_media_candidates
from .media_activation import (
    MediaActivationResolution,
    promote_media_control_decision,
    resolve_media_activation,
)
from .media_upload_normalization import normalize_media_upload_decision
from .media_paste import (
    normalize_media_paste_decision,
    resolve_requested_media_paste,
)
from .media_delivery import prefers_media_paste
from .media_dispatch_guard import guard_media_dispatch
from .mutation_handoff import FormMutationHandoff, resolve_fallback_form_mutation
from .readiness import is_ready_business_form, ready_business_form_scopes
from .resolver import resolve_deterministic

__all__ = [
    "BrowserInputContext",
    "CommitResolution",
    "CommitDispatchGuard",
    "CommitBindingLedger",
    "commit_control_key",
    "guard_dirty_form_commit",
    "replan_rejected_commit",
    "is_commit_control_for_fields",
    "is_semantic_commit_control",
    "FieldBinding",
    "FieldDescriptor",
    "FormInputModelResolver",
    "FormInputPlan",
    "FormMutationHandoff",
    "InputCandidate",
    "MediaActivationResolution",
    "augment_media_handoff_ledger",
    "discover_fields",
    "is_business_form",
    "is_ready_business_form",
    "ready_business_form_scopes",
    "page_signature",
    "pending_media_candidates",
    "normalize_media_upload_decision",
    "normalize_media_paste_decision",
    "normalize_authoritative_fill",
    "prefers_media_paste",
    "resolve_requested_media_paste",
    "guard_media_dispatch",
    "promote_media_control_decision",
    "resolve_deterministic",
    "resolve_form_commit",
    "resolve_fallback_form_mutation",
    "resolve_media_activation",
]
