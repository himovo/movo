from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.api.routes.skills import _serialize
from app.core.db import get_db
from app.services.organization_skill_feedback import organization_skill_feedback_service
from app.services.skill_lifecycle import OrganizationSkillLifecycle
from app.services.workflow_validation import validate_workflow_config


router = APIRouter()


class PublishSkillPayload(BaseModel):
    version: str = Field(default="", max_length=32)
    releaseNotes: str = Field(default="", max_length=2000)


@router.post("/{skill_id}/publish")
async def publish_skill(skill_id: str, payload: PublishSkillPayload, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    try:
        row = await get_db().skills.find_one({"_id": str(skill_id), "main_id": main_id})
        if row is None:
            raise LookupError("技能不存在")
        draft = row.get("draft") or row
        if draft.get("type") == "workflow":
            validate_workflow_config(draft.get("config") or {})
        doc, release = await OrganizationSkillLifecycle().publish(
            main_id=main_id, skill_id=str(skill_id), version=payload.version, notes=payload.releaseNotes,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="技能不存在")
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"skill": _serialize(doc), "release": {"id": release["_id"], "version": release["version"]}}


@router.get("/{skill_id}/releases")
async def list_releases(skill_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    try:
        return {"items": await OrganizationSkillLifecycle().releases(main_id=main_id, skill_id=str(skill_id))}
    except LookupError:
        raise HTTPException(status_code=404, detail="技能不存在")


@router.get("/{skill_id}/feedback")
async def list_skill_feedback(skill_id: str, current_user: dict = Depends(get_current_admin_user)) -> dict[str, Any]:
    main_id = str(current_user.get("main_id") or "default")
    try:
        return await organization_skill_feedback_service.list(main_id=main_id, skill_id=str(skill_id))
    except LookupError:
        raise HTTPException(status_code=404, detail="技能不存在")


async def ensure_indexes() -> None:
    await get_db().organization_skill_releases.create_index(
        [("main_id", 1), ("skill_id", 1), ("version", 1)], unique=True,
        name="organization_skill_release_version",
    )
