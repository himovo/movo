from __future__ import annotations

import inspect
from typing import Any, Callable, Dict

RunnableConfig = Dict[str, Any]


async def adispatch_custom_event(event: str, payload: Dict[str, Any], config: RunnableConfig | None = None) -> None:
    # Compatibility no-op. Runtime-native streaming handles progress events.
    _ = (event, payload, config)
    return None


class ToolAdapter:
    def __init__(self, fn: Callable[..., Any]) -> None:
        self._fn = fn
        self._signature = inspect.signature(fn)
        self.name = str(getattr(fn, "__name__", "tool") or "tool")
        self.description = str(inspect.getdoc(fn) or "").strip()
        self.args = self._build_args_schema(fn)
        self.args_schema = None

    @staticmethod
    def _build_args_schema(fn: Callable[..., Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        sig = inspect.signature(fn)
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            required = param.default is inspect._empty
            if name == "config":
                required = False
            out[name] = {
                "required": required,
                "description": "",
            }
        return out

    def _normalize_call_input(self, payload: Any) -> Dict[str, Any]:
        if payload is None:
            kwargs: Dict[str, Any] = {}
        elif isinstance(payload, dict):
            kwargs = dict(payload)
        else:
            kwargs = {"input": payload}
        param = self._signature.parameters.get("config")
        if param is not None and "config" not in kwargs:
            kwargs["config"] = {}
        return kwargs

    def invoke(self, payload: Any = None) -> Any:
        kwargs = self._normalize_call_input(payload)
        return self._fn(**kwargs)

    async def ainvoke(self, payload: Any = None) -> Any:
        kwargs = self._normalize_call_input(payload)
        result = self._fn(**kwargs)
        if inspect.isawaitable(result):
            return await result  # type: ignore[no-any-return]
        return result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._fn(*args, **kwargs)


def tool(fn: Callable[..., Any] | None = None):
    if fn is None:
        def _decorator(inner: Callable[..., Any]) -> ToolAdapter:
            return ToolAdapter(inner)

        return _decorator
    return ToolAdapter(fn)
