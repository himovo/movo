"""Stable V3 UI projection; DSH-native payloads never cross this boundary."""

from __future__ import annotations

import json
from typing import Any, Mapping

from app.dsh_runtime.contracts import KernelEventEnvelope
class KernelEventProjector:
    """Project native kernel events into ASKAI's stable enterprise UI model.

    Tool results do not repeat the tool name, so the projector retains only
    short-lived call metadata keyed by kernel session and call id. Everything
    persisted in V3 remains deterministic: native cursor is the item revision.
    """

    def __init__(self) -> None:
        self._tool_calls: dict[tuple[str, str], dict[str, Any]] = {}

    def project(
        self,
        event: KernelEventEnvelope,
        *,
        message_id: str,
        tool_presentations: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        event_type = event.type
        item_kind: str | None = None
        item_id: str | None = None
        payload: dict[str, Any]
        projected_type: str

        if event_type == "turn.started":
            projected_type, payload = "run.started", {"kernel": "dsh"}
        elif event_type == "agent.message.delta":
            text = self._delta_text(event.payload)
            if not text:
                return None
            projected_type, item_kind = "item.delta", "final_answer"
            item_id = self._assistant_item_id(message_id, event.payload)
            payload = {"text": text, "provisional": True}
        elif event_type == "agent.message.completed":
            text = self._message_text(event.payload)
            has_tool_call = self._message_has_tool_call(event.payload)
            if has_tool_call:
                if not text:
                    return None
                projected_type, item_kind = "item.completed", "commentary"
                payload = {
                    "text": text,
                    "source": "model",
                    "reason": "tool_call",
                    "retract_provisional": True,
                }
            else:
                projected_type, item_kind = "item.completed", "final_answer"
                payload = {"text": text, "provisional": False}
            item_id = self._assistant_item_id(message_id, event.payload)
        elif event_type == "tool.call.started":
            call_id = str(event.payload.get("callId") or event.event_id)
            name = str(event.payload.get("name") or "tool")
            presentation = dict((tool_presentations or {}).get(name) or {})
            tool_payload = {
                "callId": call_id,
                "name": name,
                "display_name": str(presentation.get("display_name") or name),
                "description": str(presentation.get("description") or ""),
                "risk_level": str(presentation.get("risk_level") or ""),
                "args": self._arguments(event.payload.get("arguments")),
                "status": "running",
            }
            self._tool_calls[(event.session_id, call_id)] = tool_payload
            projected_type, item_kind, item_id = "item.started", "tool", call_id
            payload = dict(tool_payload)
        elif event_type == "tool.call.completed":
            call_id = self._tool_result_call_id(event.payload) or event.event_id
            started = self._tool_calls.pop((event.session_id, call_id), {})
            name = str(started.get("name") or event.payload.get("name") or "tool")
            presentation = dict((tool_presentations or {}).get(name) or {})
            ok, summary, error, result_value = self._tool_result(event.payload)
            projected_type, item_kind, item_id = (
                "item.completed" if ok else "item.failed",
                "tool",
                call_id,
            )
            payload = {
                "callId": call_id,
                "name": name,
                "display_name": str(
                    started.get("display_name") or presentation.get("display_name") or name
                ),
                "description": str(
                    started.get("description") or presentation.get("description") or ""
                ),
                "risk_level": str(
                    started.get("risk_level") or presentation.get("risk_level") or ""
                ),
                "args": started.get("args") if isinstance(started.get("args"), dict) else {},
                "status": "succeeded" if ok else "failed",
                "ok": ok,
            }
            if summary:
                payload["result_summary"] = summary
            if error:
                payload["error"] = error
            evidence = self._tool_evidence(name, result_value, call_id)
            if evidence is not None:
                payload["evidence_bundle"] = evidence
            artifacts = self._result_artifacts(result_value)
            if artifacts:
                payload["artifacts"] = artifacts
            intervention = self._browser_intervention(name, result_value)
            if intervention is not None:
                payload["browser_intervention"] = intervention
        elif event_type in {"tool.approval.requested", "tool.approval.decided"}:
            # ASKAI's persisted EnterpriseApproval is the single UI authority.
            # Native DSH approval events remain in the kernel inbox for audit,
            # but cannot safely drive UI state because `decided` omits callId.
            return None
        elif event_type in {"model.request.failed", "runtime.failed"}:
            projected_type, item_kind, item_id = (
                ("run.failed", None, None)
                if event_type == "runtime.failed"
                else ("item.failed", "error", message_id)
            )
            payload = {
                "code": str(event.payload.get("code") or "dsh_runtime_failed"),
                "message": str(event.payload.get("message") or "DSH execution failed"),
                "retryable": bool(event.payload.get("retryable")),
            }
        elif event_type == "turn.completed":
            reason = event.payload.get("reason")
            reason_kind = str(reason.get("kind") if isinstance(reason, dict) else reason or "stop")
            if reason_kind in {"aborted", "cancelled", "user"}:
                projected_type = "run.cancelled"
            elif reason_kind == "error":
                projected_type = "run.failed"
            else:
                projected_type = "run.completed"
            payload = {"reason": reason_kind}
        else:
            return None

        result: dict[str, Any] = {
            "v": 3,
            "event_id": f"dsh-v3:{event.event_id}",
            "id": f"dsh-v3:{event.event_id}",
            "ts": int(event.occurred_at.timestamp() * 1000),
            "type": projected_type,
            "revision": max(1, event.cursor),
            "stream_seq": event.cursor,
            "stream_seq_end": event.cursor,
            "payload": payload,
        }
        if item_kind:
            result["item_kind"] = item_kind
        if item_id:
            result["item_id"] = item_id
        return result

    @staticmethod
    def _assistant_item_id(message_id: str, payload: dict[str, Any]) -> str:
        turn = int(payload.get("turn") or 0)
        step = int(payload.get("step") or 0)
        return f"{message_id}:assistant:{turn}:{step}"

    @staticmethod
    def _delta_text(payload: dict[str, Any]) -> str:
        chunk = payload.get("chunk")
        if isinstance(chunk, dict) and chunk.get("type") == "text-delta":
            return str(chunk.get("text") or "")
        return ""

    @staticmethod
    def _message_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
        message = payload.get("message")
        if not isinstance(message, dict):
            return []
        content = message.get("content")
        return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []

    @classmethod
    def _message_text(cls, payload: dict[str, Any]) -> str:
        message = payload.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        return "".join(
            str(block.get("text") or "")
            for block in cls._message_blocks(payload)
            if block.get("type") == "text"
        )

    @classmethod
    def _message_has_tool_call(cls, payload: dict[str, Any]) -> bool:
        return any(block.get("type") == "tool-call" for block in cls._message_blocks(payload))

    @staticmethod
    def _arguments(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(str(value or "{}"))
        except (TypeError, ValueError):
            return {"_raw": str(value or "")[:1000]}
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    @staticmethod
    def _tool_result_call_id(payload: dict[str, Any]) -> str:
        message = payload.get("message")
        if not isinstance(message, dict):
            return str(payload.get("callId") or "")
        source = message.get("source")
        if isinstance(source, dict) and source.get("callId"):
            return str(source["callId"])
        for block in list(message.get("content") or []):
            if isinstance(block, dict) and block.get("toolCallId"):
                return str(block["toolCallId"])
        return str(payload.get("callId") or "")

    @staticmethod
    def _tool_result(payload: dict[str, Any]) -> tuple[bool, str, str, Any]:
        if payload.get("codeDispatch"):
            texts = [
                str(part.get("text") or "")
                for part in list(payload.get("content") or [])
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            summary = "\n".join(value for value in texts if value).strip()[:1000]
            decoded: Any = None
            if len(texts) == 1:
                try:
                    decoded = json.loads(texts[0])
                except (TypeError, ValueError):
                    decoded = None
            is_error = bool(payload.get("isError"))
            return (not is_error), ("" if is_error else summary), (summary if is_error else ""), decoded
        message = payload.get("message")
        if not isinstance(message, dict):
            return True, "", "", None
        texts: list[str] = []
        is_error = bool(message.get("error"))
        for block in list(message.get("content") or []):
            if not isinstance(block, dict) or block.get("type") != "tool-result":
                continue
            is_error = is_error or bool(block.get("isError"))
            for part in list(block.get("content") or []):
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(str(part.get("text") or ""))
        summary = "\n".join(value for value in texts if value).strip()[:1000]
        decoded: Any = None
        if len(texts) == 1:
            try:
                decoded = json.loads(texts[0])
            except (TypeError, ValueError):
                decoded = None
        return (not is_error), ("" if is_error else summary), (summary if is_error else ""), decoded

    @staticmethod
    def _tool_evidence(name: str, value: Any, call_id: str) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        projected = value.get("evidence_bundle")
        if isinstance(projected, dict) and (
            projected.get("sources") or projected.get("confirmed_facts")
        ):
            return {"id": f"evidence-{call_id}", **dict(projected)}
        if name != "knowledge_search":
            return None
        sources: list[dict[str, Any]] = []
        for index, item in enumerate(list(value.get("items") or [])[:50]):
            if not isinstance(item, dict):
                continue
            document_id = str(item.get("documentId") or "")
            chunk_id = str(item.get("chunkId") or "")
            text = str(item.get("contextualText") or item.get("text") or "").strip()
            title_path = list(item.get("titlePath") or [])
            sources.append({
                "id": str(item.get("citation_ref") or f"kb-{document_id}-{chunk_id or index}"),
                "citation_id": str(item.get("citation_ref") or ""),
                "title": " / ".join(str(part) for part in title_path if str(part)) or document_id or "内部知识",
                "source_name": "knowledge_search",
                "snippet": text[:1000],
                "content": text,
                "source_type": "kb",
                "document_id": document_id,
                "chunk_id": chunk_id,
                "page_no": item.get("pageNo"),
                "content_type": str(item.get("contentType") or "text"),
                "source_chunk_ids": list(item.get("sourceChunkIds") or []),
            })
        return {
            "id": f"evidence-{call_id}",
            "summary": f"Knowledge retrieval returned {len(sources)} source chunk(s).",
            "sources": sources,
            "confirmed_facts": [],
            "open_questions": [] if sources else ["No authorized knowledge evidence was retrieved."],
        }

    @staticmethod
    def _result_artifacts(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, dict):
            return []
        candidates: list[Any] = []
        if isinstance(value.get("artifact"), dict):
            candidates.append(value["artifact"])
        candidates.extend(item for item in list(value.get("documents") or []) if isinstance(item, dict))
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            lifecycle = str(item.get("lifecycle") or "").strip().lower()
            visibility = str(item.get("visibility") or "").strip().lower()
            if lifecycle == "intermediate" or visibility == "internal":
                continue
            object_path = str(item.get("object_path") or "")
            marker = object_path or str(item.get("url") or item.get("filename") or "")
            if not marker or marker in seen:
                continue
            seen.add(marker)
            result.append(dict(item))
        return result

    @staticmethod
    def _browser_intervention(name: str, value: Any) -> dict[str, Any] | None:
        if name != "browser_task" or not isinstance(value, dict):
            return None
        suspension = value.get("intervention_suspension")
        if not isinstance(suspension, dict) or not suspension.get("suspension_id"):
            return None
        event = next(
            (
                row for row in reversed(list(value.get("domain_events") or []))
                if isinstance(row, dict) and row.get("type") == "intervention_required"
            ),
            {},
        )
        content = dict(event.get("content") or {}) if isinstance(event, dict) else {}
        return {
            **suspension,
            "reason": str(content.get("reason") or "Browser needs human assistance"),
            "category": str(content.get("category") or "browser"),
            "url": str(content.get("url") or ""),
            "status": "pending",
        }
