from __future__ import annotations

import json
import urllib.request
from typing import Any


def post_callback(callback_url: str, callback_token: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        callback_url,
        data=data,
        headers={
            "Authorization": f"Bearer {callback_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()
