from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

from app.api.skill_package_messages import skill_package_message
from app.api.principal import ApiPrincipal, require_api_principal, require_end_user_principal
from app.services.skill_packages import SkillPackageError, SkillPackageInstaller, validate_skill_package
from app.services.skill_packages.validator import MAX_ARCHIVE_BYTES
from app.services.skill_packages.upgrade import SkillPackageUpgradeInspector
from app.services.skill_sharing.distribution import SkillDistributionService
from app.utils.uploads import read_upload_with_limit
from app.core.db import get_db
from app.services.skill_packages.readiness import environment_status, retry_environment


router = APIRouter()
installer = SkillPackageInstaller()
upgrade_inspector = SkillPackageUpgradeInspector()


def _response(data: dict[str, Any]) -> dict[str, Any]:
    return {"code": 0, "message": "success", "data": data}


async def _validated_upload(file: UploadFile, accept_language: str | None = None):
    filename = str(file.filename or "").strip()
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail={
            "code": "zip_required", "message": skill_package_message("zip_required", accept_language), "file": filename,
        })
    content = await read_upload_with_limit(file, max_bytes=MAX_ARCHIVE_BYTES, label="Skill ZIP")
    try:
        return validate_skill_package(content)
    except SkillPackageError as exc:
        raise HTTPException(status_code=400, detail=exc.detail()) from exc


@router.post("/skills/install-zip")
async def install_personal_skill_zip(
    file: UploadFile = File(...),
    confirm_replace: bool = Form(default=False, alias="confirmReplace"),
    principal: ApiPrincipal = Depends(require_end_user_principal),
    accept_language: str | None = Header(default=None),
) -> dict[str, Any]:
    package = await _validated_upload(file, accept_language)
    upgrade = await upgrade_inspector.inspect(
        package, scope="personal", main_id=principal.main_id, user_id=principal.user_id,
    )
    if upgrade_inspector.requires_confirmation(upgrade) and not confirm_replace:
        raise HTTPException(status_code=409, detail={
            "code": "skill_upgrade_confirmation_required",
            "message": "Confirm before replacing the installed Skill",
            "upgrade": upgrade,
        })
    result = await installer.install(
        package,
        scope="personal",
        main_id=principal.main_id,
        user_id=principal.user_id,
        package_source={"kind": "local_zip", "fileName": str(file.filename or "")},
    )
    if upgrade_inspector.requires_confirmation(upgrade) and not result.get("staged"):
        await SkillDistributionService().publish_from_skill(
            main_id=principal.main_id,
            owner_user_id=principal.user_id,
            source_skill_id=str(result.get("id") or ""),
            version=str(result.get("version") or ""),
        )
    return _response({**result, "upgrade": upgrade})


@router.get("/skills/{skill_id}/dependency-status")
async def personal_skill_dependency_status(
    skill_id: str,
    principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict[str, Any]:
    row = await get_db().user_skills.find_one({
        "_id": skill_id, "main_id": principal.main_id, "user_id": principal.user_id,
    }, {"package_digest": 1, "package_files": 1, "pending_package": 1, "user_id": 1, "main_id": 1})
    if not row or not row.get("package_digest"):
        raise HTTPException(status_code=404, detail="Skill package not found")
    return _response({"status": await environment_status(row) or "not_required"})


@router.post("/skills/{skill_id}/dependency-retry")
async def retry_personal_skill_dependency(
    skill_id: str, principal: ApiPrincipal = Depends(require_end_user_principal),
) -> dict[str, Any]:
    row = await get_db().user_skills.find_one({
        "_id": skill_id, "main_id": principal.main_id, "user_id": principal.user_id,
    }, {"package_digest": 1, "package_files": 1, "pending_package": 1, "user_id": 1, "main_id": 1})
    if not row:
        raise HTTPException(status_code=404, detail="Skill package not found")
    return _response({"status": await retry_environment(row) or "not_required"})


@router.post("/organization-skills/install-zip")
async def install_organization_skill_zip(
    file: UploadFile = File(...),
    confirm_replace: bool = Form(default=False, alias="confirmReplace"),
    principal: ApiPrincipal = Depends(require_api_principal),
    accept_language: str | None = Header(default=None),
) -> dict[str, Any]:
    if principal.kind != "admin_service":
        raise HTTPException(status_code=403, detail={
            "code": "organization_install_forbidden",
            "message": skill_package_message("organization_install_forbidden", accept_language),
        })
    package = await _validated_upload(file, accept_language)
    upgrade = await upgrade_inspector.inspect(package, scope="organization", main_id=principal.main_id)
    if upgrade_inspector.requires_confirmation(upgrade) and not confirm_replace:
        raise HTTPException(status_code=409, detail={
            "code": "skill_upgrade_confirmation_required",
            "message": "Confirm before replacing the installed Skill",
            "upgrade": upgrade,
        })
    result = await installer.install(
        package,
        scope="organization",
        main_id=principal.main_id,
        package_source={"kind": "local_zip", "fileName": str(file.filename or "")},
    )
    return _response({**result, "upgrade": upgrade})


@router.get("/organization-skills/{skill_id}/dependency-status")
async def organization_skill_dependency_status(
    skill_id: str,
    principal: ApiPrincipal = Depends(require_api_principal),
) -> dict[str, Any]:
    if principal.kind != "admin_service":
        raise HTTPException(status_code=403, detail="organization_install_forbidden")
    row = await get_db().skills.find_one({
        "_id": skill_id, "main_id": principal.main_id,
    }, {"package_digest": 1, "package_files": 1, "pending_package": 1})
    if not row or not row.get("package_digest"):
        raise HTTPException(status_code=404, detail="Skill package not found")
    return _response({"status": await environment_status(row) or "not_required"})


@router.post("/organization-skills/{skill_id}/dependency-retry")
async def retry_organization_skill_dependency(
    skill_id: str, principal: ApiPrincipal = Depends(require_api_principal),
) -> dict[str, Any]:
    if principal.kind != "admin_service":
        raise HTTPException(status_code=403, detail="organization_install_forbidden")
    row = await get_db().skills.find_one({
        "_id": skill_id, "main_id": principal.main_id,
    }, {"package_id": 1, "package_digest": 1, "package_files": 1, "pending_package": 1})
    if not row:
        raise HTTPException(status_code=404, detail="Skill package not found")
    return _response({"status": await retry_environment(row) or "not_required"})
