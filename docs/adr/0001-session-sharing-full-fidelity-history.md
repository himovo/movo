# ADR 0001: Full-fidelity history for shared sessions and the known limitations

## Status

Accepted. This records a deliberate product decision (plan decision Q5=a, dual-review APPROVE). No code change is intended in this scope.

## Context

Session sharing lets a second user in the same tenant join an owner's conversation. Membership means the viewer is the session owner or holds an active `session_participants` row. Once joined, a participant reads the thread through the same endpoint the owner uses, `GET /sessions/{session_id}`, which authorizes owner or active participant and serializes each message's full artifact set (`app/api/endpoints/sessions.py:1020-1077`).

That artifact set is produced under the owner's grants. The `execution_events` replayed from the execution stores (`sessions.py:1012-1016`), the `evidence_bundles`, the `images` and the `documents` on each message all exist because the owner's capability profile and permissions produced them. The serialization applies no viewer-based filter to any of these fields, so a participant receives exactly what the owner receives.

File references inside these artifacts are signed URLs. `sign_local_file_url` (`app/services/local_file_signing.py:9-21`) computes an HMAC over the object path and the expiry timestamp using SHA256 (`_signature`, `:38-40`). The signed message carries no user identity. The serving route `GET /files/{object_path:path}` (`app/api/endpoints/documents.py:282-311`) has no authentication dependency; it verifies only the signature and the expiry, then serves the file. Access therefore depends on possessing the URL, not on who possesses it.

## Decision

We share history at full fidelity. A participant can read the owner's `execution_events`, `evidence_bundles`, `images` and `documents` as produced under the owner's grants. This is intentional. A shared conversation is one thread, and a thread with redacted or missing artifacts would mislead the participant about what actually happened.

We accept the signed URL property that comes with it. A file URL is an HMAC over the path with no identity check, so access to a file survives share revocation until the TTL elapses. The TTL is a caller-passed `ttl_seconds` parameter (`local_file_signing.py:14`, a required keyword-only argument with no default in the signature); the expiry is computed as `int(time.time()) + max(1, int(ttl_seconds))` at `:18`. Its effective value is resolved at the call sites, and nowhere else. Every call site falls back to the `OSS_SIGN_EXPIRE_SECONDS` setting when the caller passes no explicit expiry:

| Call site | Effective value |
| --- | --- |
| `app/utils/oss_uploader.py:184-192` (`sign_url`, local backend) | the caller's `expires`, else `OSS_SIGN_EXPIRE_SECONDS` |
| `app/utils/oss_uploader.py:193-195` (`sign_url`, OSS backend) | the caller's `expires`, else `OSS_SIGN_EXPIRE_SECONDS` |
| `app/utils/oss_uploader.py:197-205` (`internal_url`, local backend) | always `OSS_SIGN_EXPIRE_SECONDS` |
| `app/utils/oss_uploader.py:300-309` (markdown URL refresh) | the caller's `expires`, else `OSS_SIGN_EXPIRE_SECONDS` |
| `app/api/endpoints/documents.py:64-70` (`POST /documents/sign`) | the request's optional `expires` field (`documents.py:28-31`), else `OSS_SIGN_EXPIRE_SECONDS` |

`OSS_SIGN_EXPIRE_SECONDS` is defined at `app/core/config.py:152` with the value `3600`, mirrored in `services/chat-api/.env.example:117`. The effective TTL for a file URL is therefore one hour unless a caller passes an explicit expiry. Revoking the share link stops further joins; it does not invalidate file URLs that were already minted.

## Known limitations

The following limitations are known and accepted. Each is recorded with the code that produces it. Regression tests freeze these boundaries (plan todo 31); this ADR records them, it does not change them.

(a) The owner's search, RAG and compaction do not return participant-authored rows.

- Search: the message query at `app/api/endpoints/sessions.py:832-843` filters `user_id` to the caller, and the session fallback lookup at `:850-855` does the same. A participant's messages never surface in the owner's search results.
- History RAG: the candidate set at `app/services/rag_service/local_knowledge_rag_service.py:112-126` filters `user_id`.
- Compaction and prior-turn evidence: `_load_rows` at `app/services/conversation_evidence_service.py:126-142` filters `user_id`; the compaction summary writer is scoped to the user too (`_next_seq` at `app/services/session_persistence_service.py:58-62` mints `seq` per user, and the summary row at `:327-347` carries the writer's `user_id`).

(b) A participant's own token-usage rows become invisible to them. The usage view resolves the sessions it reports on from the sessions the caller owns only (`_load_visible_session_ids` at `app/services/token_usage_service.py:149-153` matches `user_id` on `chat_sessions`; participant membership is not consulted). The match then requires both `user_id` and a visible `session_id` (`:120-122`), and with no visible sessions the view returns an empty page (`:28-36`). A participant's usage rows on a shared session carry that session's id, which their owned-session set never contains, so those rows are invisible to them.

(c) A scheduled job run as a non-owner against an owner's shared session silently fails to find the session. The scheduler runs each job as its configured execution user (`run_as_user_id` or `owner_user_id` at `app/scheduled_tasks/runner.py:26`) and resolves a fixed-session target with `{"_id": ..., "user_id": user_id}` (`runner.py:64-76`). When the execution user is a participant rather than the owner, the lookup misses and the run fails into the scheduler's own run and job rows plus the service log (`_fail_before_start`, `runner.py:93-114`); nothing appears in the shared session and the participant receives no signal. Separately, the scheduled-path message write at `app/scheduled_tasks/dsh_execution.py:174-180` is metadata-only: it is an `update_one` that stamps `trigger_source`, `scheduled_job_id` and `scheduled_run_id` onto an existing message row and mints no `seq` (there is no `$inc` and no insert), so it cannot affect the unique `(main_id, session_id, seq)` index. The title update at `dsh_execution.py:163-168` and the unread update at `:213-224` are also scoped to the execution user and no-op for a non-owner.

(d) Participant-side pending-approval badges stay viewer-scoped. The pending list filters by the caller's `user_id` (`app/enterprise_capabilities/tools/service.py:219-230`) and the badge aggregate `_attach_pending_approval_counts` (`app/api/endpoints/sessions.py:194-201`) is viewer-scoped, so a participant sees a badge for their own pending approvals only, never for the owner's or another participant's. The durable `approval_requested` event already carries a pending approval into the thread (published at `tools/service.py:216, 232-239`); no new badge is built in this scope.

(e) No redaction. The serialization path applies no viewer-based filtering, masking or redaction to `execution_events`, `evidence_bundles`, `images` or `documents`. The owner's historical tool traces are shared in full, including tool names, arguments and results recorded while the owner ran under their own grants.

(f) A leaked link's blast radius is bounded only by tenant scoping, expiry and revoke. Anyone in the same tenant who obtains the token can join while the share is active (`share_expires_at > now` and `share_revoked_at is None`); there is no other bound. After expiry or revocation, no new joins succeed, and file URLs minted earlier remain accessible until their TTL elapses (the signed URL property above).

## Consequences

A shared conversation presents one faithful history to every member, and participants can audit what happened without asking the owner for screenshots or exports. The existing serialization and signing code is untouched; this decision changes no code in this scope.

The costs are the limitations above. Operators should treat share links like bearer credentials: possession grants the entitlements described here, and revocation bounds the future, not the past. File access after revocation is delayed only by the TTL, so deployments that need tighter control should shorten `OSS_SIGN_EXPIRE_SECONDS`. Tenant membership is the outer bound on who a leaked link can reach.
