from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

import yaml

from app.core.config import get_settings


@dataclass(frozen=True)
class ModelSelection:
    model: str
    source: str


class ModelRouter:
    """Resolve model name by task/stage/node with config-driven priority."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        base = Path(__file__).resolve().parents[1]
        self._config_path = Path(config_path) if config_path else (base / "config" / "model_routing.yaml")
        self._lock = Lock()
        self._loaded_mtime: float = -1.0
        self._cfg: Dict[str, Any] = {}

    def resolve(
        self,
        *,
        explicit_model: str | None = None,
        intent: str | None = None,
        stage: str | None = None,
        node_id: str | None = None,
        output_spec: Dict[str, Any] | None = None,
    ) -> ModelSelection:
        settings = get_settings()
        default_model = str(settings.OPENAI_MODEL or "gpt-5.2")
        env_general = str(settings.OPENAI_MODEL_GENERAL or "").strip()
        env_chat = str(settings.OPENAI_MODEL_CHAT or "").strip()
        env_coding = str(settings.OPENAI_MODEL_CODING or "").strip()

        # Qwen provider currently uses a single configured runtime model.
        if settings.USE_QWEN:
            return ModelSelection(model=str(settings.QWEN_MODEL or default_model), source="provider_default:qwen")

        if explicit_model:
            return ModelSelection(model=str(explicit_model), source="explicit")

        cfg = self._load_config()
        if not bool(cfg.get("enabled", True)):
            return ModelSelection(model=default_model, source="disabled_fallback")

        task_override = self._extract_task_override(output_spec or {})
        if task_override:
            return ModelSelection(model=task_override, source="task_override")

        by_node = cfg.get("by_node") if isinstance(cfg.get("by_node"), dict) else {}
        if node_id and str(node_id) in by_node:
            return ModelSelection(model=str(by_node[str(node_id)]), source="by_node")

        by_stage = cfg.get("by_stage") if isinstance(cfg.get("by_stage"), dict) else {}
        if stage and str(stage) in by_stage:
            return ModelSelection(model=str(by_stage[str(stage)]), source="by_stage")

        by_intent = cfg.get("by_intent") if isinstance(cfg.get("by_intent"), dict) else {}
        if intent and str(intent) in by_intent:
            return ModelSelection(model=str(by_intent[str(intent)]), source="by_intent")

        models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
        model_overrides = {
            "general": env_general,
            "chat": env_chat,
            "coding": env_coding,
        }
        inferred = self._infer_model_key(intent=intent, stage=stage)
        if inferred:
            override_model = model_overrides.get(inferred) or ""
            if override_model:
                return ModelSelection(model=override_model, source=f"env:{inferred}")
            if str(models.get(inferred) or ""):
                return ModelSelection(model=str(models[inferred]), source=f"models.{inferred}")

        fallback = str(cfg.get("fallback_model") or default_model)
        return ModelSelection(model=fallback, source="config_fallback")

    def _extract_task_override(self, output_spec: Dict[str, Any]) -> str:
        direct = str(output_spec.get("model_override") or "").strip()
        if direct:
            return direct

        task_cfg = output_spec.get("task_config") if isinstance(output_spec.get("task_config"), dict) else {}
        override = str(task_cfg.get("model_override") or "").strip()
        if override:
            return override

        agent_cfg = output_spec.get("agent_config") if isinstance(output_spec.get("agent_config"), dict) else {}
        override = str(agent_cfg.get("model_override") or "").strip()
        if override:
            return override

        return ""

    def _infer_model_key(self, *, intent: str | None, stage: str | None) -> str:
        stage_s = str(stage or "").lower()
        intent_s = str(intent or "").lower()
        if "coding" in stage_s or intent_s == "coding":
            return "coding"
        if stage_s in {"browser_planning", "research_query_refine"}:
            return "chat"
        if intent_s in {"chat", "browser_automation"}:
            return "chat"
        return "general"

    def _load_config(self) -> Dict[str, Any]:
        try:
            mtime = self._config_path.stat().st_mtime
        except FileNotFoundError:
            return {}

        with self._lock:
            if self._cfg and mtime == self._loaded_mtime:
                return self._cfg
            try:
                data = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
            self._cfg = data
            self._loaded_mtime = mtime
            return self._cfg


_global_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    global _global_model_router
    if _global_model_router is None:
        _global_model_router = ModelRouter()
    return _global_model_router
