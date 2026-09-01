"""DSH adapter over ASKAI's existing configured image generation service."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext
from app.services.image_generation import generate_image_asset

from .progress import ImageGenerationProgress


ImageGenerator = Callable[..., Awaitable[dict[str, Any]]]


def _plain_text(value: Any, *, fallback: str = "") -> str:
    return " ".join(str(value or fallback).split()).strip()


def _markdown_alt(value: Any, *, index: int) -> str:
    return _plain_text(value, fallback=f"Generated image {index}").replace("[", "").replace("]", "")[:240]


class ImageGenerationCapability:
    def __init__(self, generator: ImageGenerator = generate_image_asset) -> None:
        self._generator = generator

    async def run(
        self,
        arguments: dict[str, Any],
        context: CapabilityExecutionContext,
    ) -> dict[str, Any]:
        requests = [dict(item) for item in list(arguments.get("images") or []) if isinstance(item, dict)][:4]
        if not requests:
            return self._result(requested=0, assets=[], failures=[{"index": 0, "error": "image request is required"}])

        language = str(context.turn_context.get("language") or "zh")
        progress = ImageGenerationProgress(
            action_id=context.action_id,
            message_id=context.message_id,
            language=language,
        )
        assets: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        total = len(requests)
        for index, spec in enumerate(requests, start=1):
            prompt = str(spec.get("prompt") or "").strip()
            if not prompt:
                failures.append({"index": index, "error": "image prompt is required"})
                continue
            await context.publish_progress(progress.row(stage="started", index=index, total=total))
            try:
                generated = await self._generator(
                    prompt=prompt,
                    user_id=context.user_id,
                    output_spec={"main_id": context.tenant_id},
                    file_prefix="dsh_generated_image",
                )
                image_url = str(generated.get("image_url") or "").strip()
                object_path = str(generated.get("object_path") or "").strip()
                if not image_url or not object_path:
                    raise RuntimeError(str(generated.get("error") or "image generation returned no persisted asset"))
                alt_text = _markdown_alt(spec.get("alt_text"), index=index)
                assets.append({
                    "index": index,
                    "image_url": image_url,
                    "object_path": object_path,
                    "markdown": f"![{alt_text}]({image_url})",
                    "alt_text": alt_text,
                    "placement_hint": _plain_text(spec.get("placement_hint"))[:500],
                })
                await context.publish_progress(progress.row(stage="completed", index=index, total=total))
            except Exception as exc:
                failures.append({"index": index, "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})
        return self._result(requested=total, assets=assets, failures=failures)

    @staticmethod
    def _result(
        *,
        requested: int,
        assets: list[dict[str, Any]],
        failures: list[dict[str, Any]],
    ) -> dict[str, Any]:
        generated = len(assets)
        status = "completed" if generated == requested and requested > 0 else (
            "partial_success" if generated else "failed"
        )
        return {
            "success": generated > 0,
            "status": status,
            "requested_count": requested,
            "generated_count": generated,
            "assets": assets,
            "failures": failures,
            "continuation_required": status == "partial_success",
            "message": "" if status == "completed" else (
                "some requested images were not generated" if generated else "no requested image was generated"
            ),
        }


_capability = ImageGenerationCapability()


async def generate_images(arguments: dict[str, Any], context: CapabilityExecutionContext) -> dict[str, Any]:
    return await _capability.run(arguments, context)


__all__ = ["ImageGenerationCapability", "generate_images"]
