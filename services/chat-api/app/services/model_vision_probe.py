"""Small, deterministic image challenge for a saved chat model."""

from __future__ import annotations

import base64
import struct
import zlib

from app.llm.configured_models import get_llm_client_by_model_id
from app.llm.types import Message, Role


def _blue_square_data_url() -> str:
    width = height = 32
    pixels = b"".join(b"\0" + b"\x17\x58\xdb" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


async def probe_model_vision(model_id: str, main_id: str) -> tuple[bool, str]:
    """Require a correct visual answer, not merely an accepted HTTP request."""
    client = await get_llm_client_by_model_id(
        model_id, main_id=main_id, streaming=False, intent="vision",
        stage="model_vision_probe", output_spec={"main_id": main_id, "model_id": model_id},
    )
    response = await client.ainvoke([
        Message(role=Role.SYSTEM, content="Answer the image question using the image only. Reply with one English color word."),
        Message(role=Role.USER, content=[
            {"type": "text", "text": "What color is the solid square in this image?"},
            {"type": "image_url", "image_url": {"url": _blue_square_data_url()}},
        ]),
    ])
    answer = str(response.content or "").strip().lower()
    normalized = answer.strip(" \t\r\n.!。！`'\"")
    return normalized in {"blue", "蓝色", "蓝"}, answer[:120]
