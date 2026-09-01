from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


def _normalize_token(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _unique(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        token = str(item or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


@dataclass(frozen=True)
class PublishChannelPolicy:
    channel: str
    aliases: tuple[str, ...] = ()
    draft_post_action: str = "publish"
    default_required_elements: tuple[str, ...] = ()
    default_forbidden_elements: tuple[str, ...] = ()
    default_style_hints: tuple[str, ...] = ()
    default_applicable_scenarios: str = ""
    delivery_forbidden: tuple[str, ...] = ()
    template_tags: tuple[str, ...] = ()
    publish_url: str = ""


class PublishChannelRegistry:
    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or (Path(__file__).resolve().parent / "publish_channels.yaml")
        self._policies: Dict[str, PublishChannelPolicy] = {}
        self._alias_to_channel: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}
        items = raw.get("channels") if isinstance(raw.get("channels"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            channel = _normalize_token(item.get("channel"))
            if not channel:
                continue
            aliases = _unique(
                [channel]
                + [_normalize_token(alias) for alias in list(item.get("aliases") or []) if _normalize_token(alias)]
            )
            policy = PublishChannelPolicy(
                channel=channel,
                aliases=tuple(aliases),
                draft_post_action=str(item.get("draft_post_action") or "publish").strip() or "publish",
                default_required_elements=tuple(_unique([str(x).strip() for x in list(item.get("default_required_elements") or [])])),
                default_forbidden_elements=tuple(_unique([str(x).strip() for x in list(item.get("default_forbidden_elements") or [])])),
                default_style_hints=tuple(_unique([str(x).strip() for x in list(item.get("default_style_hints") or [])])),
                default_applicable_scenarios=str(item.get("default_applicable_scenarios") or "").strip(),
                delivery_forbidden=tuple(_unique([str(x).strip() for x in list(item.get("delivery_forbidden") or [])])),
                template_tags=tuple(_unique([str(x).strip().lower() for x in list(item.get("template_tags") or [])])),
                publish_url=str(item.get("publish_url") or "").strip(),
            )
            self._policies[channel] = policy
            for alias in policy.aliases:
                self._alias_to_channel[alias] = channel
        if "generic" not in self._policies:
            self._policies["generic"] = PublishChannelPolicy(channel="generic", aliases=("generic",))
            self._alias_to_channel["generic"] = "generic"

    @staticmethod
    def _contains_alias(text: str, alias: str) -> bool:
        if not alias or not text:
            return False
        if re.fullmatch(r"[a-z0-9_ ]+", alias):
            pattern = r"(^|[^a-z0-9_])%s([^a-z0-9_]|$)" % re.escape(alias)
            return re.search(pattern, text) is not None
        return alias in text

    def known_channels(self) -> List[str]:
        return list(self._policies.keys())

    def canonicalize(self, value: Any, *, default: str = "generic", preserve_unknown: bool = True) -> str:
        token = _normalize_token(value)
        if not token:
            return default
        matched = self._alias_to_channel.get(token)
        if matched:
            return matched
        return token if preserve_unknown else default

    def canonicalize_many(self, values: Any, *, default: str = "generic") -> List[str]:
        if isinstance(values, list):
            raw_items = values
        elif isinstance(values, str):
            raw_items = [values]
        else:
            raw_items = []
        normalized = [self.canonicalize(item, default="", preserve_unknown=True) for item in raw_items]
        normalized = [item for item in normalized if item]
        return _unique(normalized) or ([default] if default else [])

    def detect_from_text(self, text: Any, *, default: str = "") -> str:
        haystack = _normalize_token(text)
        if not haystack:
            return default
        best_channel = ""
        best_alias_len = -1
        for alias, channel in self._alias_to_channel.items():
            if not alias or alias == "generic":
                continue
            if self._contains_alias(haystack, alias) and len(alias) > best_alias_len:
                best_channel = channel
                best_alias_len = len(alias)
        return best_channel or default

    def resolve(self, *, explicit: Any = "", context: Any = "", default: str = "generic") -> str:
        explicit_channel = self.canonicalize(explicit, default="", preserve_unknown=True)
        if explicit_channel:
            return explicit_channel
        detected = self.detect_from_text(context, default="")
        if detected:
            return detected
        return default

    def policy_for(self, channel: Any) -> PublishChannelPolicy:
        canonical = self.canonicalize(channel, default="generic", preserve_unknown=True)
        return self._policies.get(canonical) or self._policies["generic"]

    def draft_post_action_for(self, channel: Any) -> str:
        return str(self.policy_for(channel).draft_post_action or "publish")

    def required_elements_for(self, channel: Any) -> List[str]:
        return list(self.policy_for(channel).default_required_elements)

    def forbidden_elements_for(self, channel: Any) -> List[str]:
        return list(self.policy_for(channel).default_forbidden_elements)

    def style_hints_for(self, channel: Any) -> List[str]:
        return list(self.policy_for(channel).default_style_hints)

    def applicable_scenarios_for(self, channel: Any) -> str:
        return str(self.policy_for(channel).default_applicable_scenarios or "")

    def delivery_forbidden_for(self, channel: Any) -> List[str]:
        return list(self.policy_for(channel).delivery_forbidden)

    def template_tags_for(self, channel: Any) -> List[str]:
        policy = self.policy_for(channel)
        return list(policy.template_tags or ([policy.channel] if policy.channel else []))

    def publish_url_for(self, channel: Any) -> str:
        """Return the configured publish-page URL for a channel.

        Empty string if the channel either doesn't exist or doesn't declare
        one (e.g., generic / email / knowledge_base). Callers should treat
        that as "no default — don't rewrite".
        """
        return str(self.policy_for(channel).publish_url or "")


publish_channel_registry = PublishChannelRegistry()
