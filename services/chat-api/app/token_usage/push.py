from __future__ import annotations

from typing import Any, Dict

import httpx

from app.core.config import get_settings
from app.token_usage.models import TokenUsagePushResult, TokenUsageRecord


class TokenUsagePushService:
    async def push(self, record: TokenUsageRecord) -> TokenUsagePushResult:
        settings = get_settings()
        if not bool(getattr(settings, "TOKEN_USAGE_PUSH_ENABLED", False)):
            return TokenUsagePushResult(enabled=False, pushed=False)

        url = str(getattr(settings, "TOKEN_USAGE_PUSH_URL", "") or "").strip()
        if not url:
            return TokenUsagePushResult(enabled=True, pushed=False, error="missing_push_url")

        payload = self._to_remote_payload(record)
        timeout = float(getattr(settings, "TOKEN_USAGE_PUSH_TIMEOUT_SECONDS", 2.0) or 2.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            return TokenUsagePushResult(enabled=True, pushed=True)
        except Exception as exc:
            return TokenUsagePushResult(enabled=True, pushed=False, error=str(exc))

    @staticmethod
    def _to_remote_payload(record: TokenUsageRecord) -> Dict[str, Any]:
        user_id: Any = record.user_id
        try:
            if str(user_id).strip():
                user_id = int(str(user_id))
        except Exception:
            user_id = str(record.user_id or "")
        return {
            "mainId": record.main_id,
            "userId": user_id,
            "modelName": record.model_name,
            "modelId": record.model_id,
            "prompt": record.prompt,
            "startTime": record.start_time,
            "endTime": record.end_time,
            "requestTitleZh": record.request_title_zh,
            "requestTitleEn": record.request_title_en,
            "requestPayload": record.request_payload,
            "responsePayload": record.response_payload,
            "totalTokens": record.total_tokens,
            "promptTokens": record.prompt_tokens,
            "completionTokens": record.completion_tokens,
        }
