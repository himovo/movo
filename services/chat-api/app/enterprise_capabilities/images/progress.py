"""Timeline projection for image generation owned by ASKAI."""

from __future__ import annotations

from time import time


class ImageGenerationProgress:
    def __init__(self, *, action_id: str, message_id: str, language: str) -> None:
        self._action_id = action_id
        self._namespace = f"{message_id or 'no-message'}:{action_id}"
        self._is_zh = str(language or "").lower().startswith("zh")
        self._counter = 0

    def row(self, *, stage: str, index: int, total: int) -> dict:
        self._counter += 1
        if self._is_zh:
            text = (
                f"正在生成第 {index}/{total} 张图片"
                if stage == "started" else f"第 {index}/{total} 张图片已生成"
            )
        else:
            text = (
                f"Generating image {index}/{total}"
                if stage == "started" else f"Generated image {index}/{total}"
            )
        event_id = f"askai-v3:image-generation:{self._namespace}:{self._counter}"
        return {
            "v": 3,
            "event_id": event_id,
            "id": event_id,
            "ts": int(time() * 1000),
            "type": "item.completed",
            "item_kind": "commentary",
            "item_id": f"{self._action_id}:image-progress:{self._counter}",
            "parent_item_id": self._action_id,
            "revision": 1,
            "payload": {
                "text": text,
                "source": "image_generation_pipeline",
                "reason": f"image_{stage}",
            },
        }


__all__ = ["ImageGenerationProgress"]
