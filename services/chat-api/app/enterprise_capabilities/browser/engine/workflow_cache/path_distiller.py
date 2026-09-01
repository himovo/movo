from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List
from urllib.parse import urlparse

from .page_state import url_shape
from .trace_compaction import compact_causal_actions


_MUTATION_TOOLS = {
    "browser_fill", "browser_type_at", "browser_select",
    "browser_upload_file", "browser_paste_image",
}
_TERMINAL_ACTION_TOKENS = (
    "save", "submit", "publish", "confirm", "delete", "complete",
    "send", "apply", "create", "update",
    "保存", "提交", "发布", "确认", "确定", "删除", "完成", "发送",
    "应用", "创建", "更新", "存草稿", "草稿",
)


@dataclass(frozen=True)
class DistilledLearningPath:
    entries: List[Any]
    critical_gaps: List[Any]
    dropped_events: int

    @property
    def complete(self) -> bool:
        return bool(self.entries) and not self.critical_gaps


def distill_success_path(
    entries: Iterable[Any],
    gaps: Iterable[Any],
    *,
    site_id: str = "",
) -> DistilledLearningPath:
    """Return the loop-erased causal route to the terminal browser state.

    Gaps participate in the same state route as replayable actions.  A gap
    removed together with a dead-end/return loop is exploration noise; a gap
    that remains on the final route is critical and blocks cache admission.
    """
    all_events = sorted(
        [*list(entries), *list(gaps)],
        key=lambda item: int(getattr(item, "sequence", 0)),
    )
    scoped = _trim_to_site(all_events, site_id)
    routed = _erase_state_loops(scoped)
    compacted = _drop_overwritten_mutations(compact_causal_actions(routed))
    replayable = [event for event in compacted if not _is_gap(event)]
    critical = [event for event in compacted if _is_gap(event)]
    return DistilledLearningPath(
        entries=replayable,
        critical_gaps=critical,
        dropped_events=max(0, len(all_events) - len(compacted)),
    )


def _trim_to_site(events: List[Any], site_id: str) -> List[Any]:
    site = str(site_id or "").lower().removeprefix("www.")
    if not site or site.startswith("profile:"):
        return list(events)
    first = next((
        index for index, event in enumerate(events)
        if _belongs_to_site(_after_url(event), site)
    ), None)
    return list(events[first:]) if first is not None else list(events)


def _erase_state_loops(events: List[Any]) -> List[Any]:
    if not events:
        return []
    route: List[Any] = []
    states: List[tuple[str, str, str]] = []
    for event_index, event in enumerate(events):
        before = (_before_state(event), url_shape(_before_url(event)), _before_tab(event))
        after = (_after_state(event), url_shape(_after_url(event)), _after_tab(event))
        if not states:
            states.append(before)
        target = (
            None
            if event_index == len(events) - 1
            else _previous_state_index(states, after, event)
        )
        if target is not None:
            route = route[:target]
            states = states[: target + 1]
            continue
        route.append(event)
        states.append(after)
    return route


def _previous_state_index(
    states: List[tuple[str, str, str]],
    after: tuple[str, str, str],
    event: Any,
) -> int | None:
    if (
        str(getattr(event, "tool", "")) in _MUTATION_TOOLS
        or _is_terminal_action(event)
    ):
        return None
    after_key, after_shape, after_tab = after
    # Blank documents are transient popup/new-tab placeholders, not business
    # states. Treating them as loop destinations deletes the causal route that
    # opened the new tab. This also protects recordings made before tab IDs
    # were added to the journal.
    if _is_transient_document(_after_url(event)):
        return None
    for index in range(len(states) - 1, -1, -1):
        state_key, state_shape, state_tab = states[index]
        if after_tab and state_tab and after_tab != state_tab:
            continue
        if after_key and state_key and after_key == state_key:
            return index
        # URL-changing returns are reliable even when page fingerprints contain
        # transient counters.  Same-URL UI transitions require semantic-state
        # equality and are not collapsed merely because the URL is unchanged.
        if (
            _before_url(event) != _after_url(event)
            and after_shape
            and after_shape == state_shape
        ):
            return index
    return None


def _drop_overwritten_mutations(events: List[Any]) -> List[Any]:
    last_write: dict[tuple[str, str, str], int] = {}
    for index, event in enumerate(events):
        tool = str(getattr(event, "tool", ""))
        if _is_gap(event) or tool not in _MUTATION_TOOLS:
            continue
        family = "upload" if tool in {"browser_upload_file", "browser_paste_image"} else (
            "select" if tool == "browser_select" else "fill"
        )
        key = (family, _locator_key(event), url_shape(_before_url(event)))
        if key[1]:
            last_write[key] = index
    output: List[Any] = []
    for index, event in enumerate(events):
        tool = str(getattr(event, "tool", ""))
        if _is_gap(event) or tool not in _MUTATION_TOOLS:
            output.append(event)
            continue
        family = "upload" if tool in {"browser_upload_file", "browser_paste_image"} else (
            "select" if tool == "browser_select" else "fill"
        )
        key = (family, _locator_key(event), url_shape(_before_url(event)))
        if not key[1] or last_write.get(key) == index:
            output.append(event)
    return output


def _locator_key(event: Any) -> str:
    locator = dict(getattr(event, "locator", {}) or {})
    return "|".join(str(locator.get(key) or "").strip().casefold() for key in (
        "selector", "role", "name", "placeholder", "semanticPurpose", "scopeName",
    ))


def _is_terminal_action(event: Any) -> bool:
    tool = str(getattr(event, "tool", ""))
    if tool not in {"browser_click", "browser_click_at", "browser_press"}:
        return False
    locator = dict(getattr(event, "locator", {}) or {})
    text = " ".join((
        str(locator.get("name") or ""),
        str(locator.get("text") or ""),
        str(locator.get("description") or ""),
        str(locator.get("semanticPurpose") or ""),
        str(getattr(event, "rationale", "") or ""),
    )).casefold()
    return any(token in text for token in _TERMINAL_ACTION_TOKENS)


def _is_gap(event: Any) -> bool:
    return bool(getattr(event, "reason", "")) and not hasattr(event, "locator")


def _before_state(event: Any) -> str:
    return str(getattr(event, "before_state_key", "") or "")


def _after_state(event: Any) -> str:
    return str(getattr(event, "after_state_key", "") or "")


def _before_url(event: Any) -> str:
    return str(getattr(event, "before_url", "") or "")


def _after_url(event: Any) -> str:
    return str(getattr(event, "after_url", "") or "")


def _before_tab(event: Any) -> str:
    return str(getattr(event, "before_tab_id", "") or "")


def _after_tab(event: Any) -> str:
    return str(getattr(event, "after_tab_id", "") or _before_tab(event))


def _is_transient_document(url: str) -> bool:
    normalized = str(url or "").strip().casefold()
    return normalized in {"", "about:blank", "about:srcdoc"}


def _belongs_to_site(url: str, site: str) -> bool:
    host = str(urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    return host == site or host.endswith(f".{site}")


__all__ = ["DistilledLearningPath", "distill_success_path"]
