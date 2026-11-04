"""Token-protected read-only deployment status service."""

from __future__ import annotations

import hmac
import os

from fastapi import FastAPI, Header, HTTPException

from .deployment_status import inventory
from .docker_engine import DockerEngine


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _authorize(authorization: str | None) -> None:
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    supplied = (authorization or "").removeprefix("Bearer ")
    if not token or not hmac.compare_digest(token, supplied):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    engine = DockerEngine()
    try:
        engine.request("GET", "/_ping")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Docker Engine unavailable") from exc
    finally:
        engine.client.close()
    return {"ok": True}


@app.get("/status")
def status(authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    engine = DockerEngine()
    try:
        return inventory(engine)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Deployment status unavailable") from exc
    finally:
        engine.client.close()
