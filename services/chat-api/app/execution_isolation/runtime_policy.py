"""Resolve server Runtime placement from the sandbox control plane."""

import os
from time import monotonic

import httpx

_confirmed: dict[str, tuple[float, bool]] = {}


async def uses_on_demand_runtime() -> bool:
    base = os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip().rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if not base or not token:
        return False
    started = monotonic()
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(f"{base}/v1/settings", headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            mode = response.json().get("runtime_mode")
            if mode in ("on_demand", "forced") and started >= _confirmed.get(base, (0, False))[0]:
                _confirmed[base] = (started, mode == "on_demand")
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return _confirmed.get(base, (0, False))[1]
