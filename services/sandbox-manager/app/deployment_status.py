"""Read-only Docker deployment inventory for the administrator status page."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .docker_engine import DockerEngine


SERVICES = (
    "gateway", "admin-web", "user-web", "admin-api", "chat-api",
    "dsh-runtime-host", "document-api", "document-worker", "mongo",
    "redis", "weaviate", "sandbox-manager", "sandbox-egress", "deployment-observer",
)
SANDBOX_SERVICES = frozenset({"sandbox-manager", "sandbox-egress"})


def deployment_record() -> dict:
    path = Path(os.environ.get("MOVO_DEPLOYMENT_RECORD", "/deployment/deployment.json"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {key: data.get(key) for key in ("upgradedAt", "version", "commit") if isinstance(data.get(key), str)}


def recorded_images() -> dict[str, str]:
    path = Path(os.environ.get("MOVO_DEPLOYMENT_IMAGES", "/deployment/image-ids.txt"))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    pairs = (line.split(" ", 1) for line in lines if " " in line)
    return {name: image_id for name, image_id in pairs if name in SERVICES and image_id.startswith("sha256:")}


def inventory(engine: DockerEngine) -> dict:
    project = os.environ.get("MOVO_SANDBOX_COMPOSE_PROJECT", "movo")
    response = engine.request("GET", "/containers/json", params={
        "all": 1, "filters": json.dumps({"label": [f"com.docker.compose.project={project}"]}),
    })
    rows = {item.get("Labels", {}).get("com.docker.compose.service"): item for item in response.json()}
    expected_images = recorded_images()
    record = deployment_record()
    sandbox_enabled = "sandbox-manager" in rows or "sandbox-egress" in rows
    services = []
    image_revisions: dict[str, str] = {}
    for name in SERVICES:
        row = rows.get(name)
        if row is None:
            services.append({"name": name, "status": "disabled" if name in SANDBOX_SERVICES and not sandbox_enabled else "missing"})
            continue
        try:
            details = engine.inspect(row["Id"])
        except Exception:
            details = {"Id": row["Id"], "Image": row.get("ImageID"), "State": {"Status": row.get("State") or "unknown"}}
        state = details.get("State") or {}
        health = (state.get("Health") or {}).get("Status") or "unknown"
        image_id = str(details.get("Image") or row.get("ImageID") or "")
        image_name = str((details.get("Config") or {}).get("Image") or row.get("Image") or "")
        if image_id and image_id not in image_revisions:
            try:
                image_details = engine.request("GET", f"/images/{image_id}/json").json()
                image_revisions[image_id] = str((image_details.get("Config") or {}).get("Labels", {}).get("org.opencontainers.image.revision") or "")
            except Exception:
                image_revisions[image_id] = ""
        version_mismatch = bool(expected_images.get(name) and expected_images[name] != image_id)
        services.append({
            "name": name,
            "status": str(state.get("Status") or "unknown"),
            "health": health,
            "image": image_name,
            "imageId": image_id,
            "revision": image_revisions.get(image_id, ""),
            "versionMismatch": version_mismatch,
            "containerId": str(details.get("Id") or row["Id"]),
            "createdAt": details.get("Created"),
            "startedAt": state.get("StartedAt"),
            "restarts": int(details.get("RestartCount") or 0),
        })
    revisions = sorted({service["revision"] for service in services if service.get("revision") and service["name"] not in {"mongo", "redis", "weaviate"}})
    record["revisions"] = revisions
    record["commit"] = revisions[0] if len(revisions) == 1 else ""
    image_name = os.environ.get("MOVO_SANDBOX_SCRIPT_IMAGE", "").strip()
    script_image = {"image": image_name, "imageId": "", "available": False}
    if image_name:
        try:
            image = engine.request("GET", f"/images/{image_name}/json").json()
            script_image = {"image": image_name, "imageId": str(image.get("Id") or ""), "available": True}
        except Exception:
            pass
    return {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "deployment": record,
        "services": services,
        "scriptImage": script_image,
    }
