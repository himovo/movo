from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlsplit

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Decision, Observation

from .contracts import CachedCompletionContract


def build_local_completion(
    contract: CachedCompletionContract,
    observation: Observation,
    *,
    lang: str,
) -> Decision | None:
    # Write completion belongs to the executor's EffectTracker.  A cached
    # click plus ordinary page text is not a business receipt and must never
    # short-circuit the existing verification/fallback chain.
    if _requires_effect_receipt(contract.capability_id):
        return None
    summary = "已通过本地缓存流程完成浏览器任务" if lang.startswith("zh") else (
        "Browser task completed through the local cached workflow"
    )
    data = _completion_data(contract, observation)
    if data is None:
        return None
    return Decision(
        tool="browser_done",
        args={"summary": summary, "data": data},
        rationale="[learned_workflow] locally verified terminal step",
    )


def _requires_effect_receipt(capability_id: str) -> bool:
    return str(capability_id or "").strip().casefold() in {
        "browser.submit", "browser.modify", "browser.delete",
        "browser.publish", "browser.publish_or_submit",
    }


def _completion_data(
    contract: CachedCompletionContract,
    observation: Observation,
) -> Dict[str, Any] | None:
    capability = str(contract.capability_id or "").strip().lower()
    url = str(observation.url or "")
    title = str(observation.title or "")
    text = str(observation.page_text or title or url)[:12000]
    observed = {"url": url, "title": title, "text": text}
    if capability == "browser.navigate":
        return {"final_url": url, "page_title": title, "landed_ok": bool(url and url != "about:blank")}
    if capability in {"browser.read", "browser.navigate_and_extract", "browser.search"}:
        if not str(observation.page_text or observation.title or "").strip():
            return None
        return {"result": observed}
    if capability in {"browser.submit", "browser.modify", "browser.delete"}:
        return {"confirmation": {"text": text[:1200], "redirect_url": url}}
    if capability in {"browser.publish", "browser.publish_or_submit"}:
        host = str(urlsplit(url).hostname or "browser")
        return {"delivery": {"channel": host, "destination": url or host}}
    if capability == "browser.file_transfer":
        return {"file": {"direction": contract.file_direction, "path_or_url": url}}
    return {"result": observed}


__all__ = ["build_local_completion"]
