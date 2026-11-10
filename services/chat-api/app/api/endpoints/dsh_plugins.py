"""Authenticated enterprise and personal DSH plugin control plane."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.api.principal import ApiPrincipal, require_api_principal
from app.dsh_runtime.plugin_management.installer import DshPluginInstaller, PluginInstallError
from app.dsh_runtime.plugin_management.preflight import inspect_plugin_spec
from app.dsh_runtime.plugin_management.current_assessment import assess_existing_installation, running_dsh_version
from app.dsh_runtime.plugin_management.repository import PluginInstallationRepository
from app.dsh_runtime.plugin_management.source_policy import is_safe_personal_source, is_supported_plugin_source
from app.dsh_runtime.plugin_management.archive_store import delete_archive, save_archive, MAX_ARCHIVE_BYTES
from app.core.db import get_db
from app.utils.uploads import read_upload_with_limit
from app.product.extensions import get_product_extension
from app.product.resource_access import filter_allowed_resource_ids
from app.dsh_runtime.profile.plugins import MongoPluginCatalog
from app.dsh_runtime.profile.plugin_skill_selection import selection_id
from app.dsh_runtime.profile.plugin_command_selection import selection_id as command_selection_id
from app.product.execution_access import execution_is_allowed
from app.dsh_runtime.application import dsh_runtime_application
from app.dsh_runtime.plugin_ui.public_origin import plugin_ui_public_origin
from app.dsh_runtime.plugin_ui.session_navigation import resolve_conversation


router = APIRouter(prefix="/dsh-plugins", tags=["dsh-plugins"])
repository = PluginInstallationRepository()


class InstallRequest(BaseModel):
    spec: str = Field(min_length=1, max_length=500)


class EnabledRequest(BaseModel):
    enabled: bool


def _owner(principal: ApiPrincipal, scope: str) -> str:
    if scope == "organization":
        if principal.kind != "admin_service":
            raise HTTPException(status_code=403, detail="organization_plugin_admin_required")
        return ""
    if scope == "personal" and principal.kind == "end_user":
        return principal.user_id
    raise HTTPException(status_code=403, detail="personal_plugin_user_required")


def _result(data):
    return {"code": 0, "message": "success", "data": data}


async def _running_version() -> str:
    try:
        return await running_dsh_version()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="dsh_runtime_unavailable") from exc


async def _require_personal_execution(principal: ApiPrincipal, owner: str) -> None:
    if owner and not await execution_is_allowed(
        main_id=principal.main_id, user_id=owner, capability="plugin.runtime",
    ):
        raise HTTPException(status_code=403, detail="plugin_runtime_access_denied")


@router.get("/personal/selectable-skills")
async def selectable_plugin_skills(
    scope: str = "all", keyword: str = "", cursor: int = 0, limit: int = 20,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    if principal.kind != "end_user":
        raise HTTPException(status_code=403, detail="personal_plugin_user_required")
    if scope not in {"all", "user", "organization"} or cursor < 0 or not 1 <= limit <= 50:
        raise HTTPException(status_code=400, detail="invalid_plugin_skill_query")
    query = keyword.strip().casefold()
    items = []
    for plugin in await MongoPluginCatalog().list_enabled(principal.main_id, principal.user_id):
        source_scope = "user" if plugin["source_scope"] == "personal" else "organization"
        if scope != "all" and scope != source_scope:
            continue
        for skill in plugin.get("skills") or []:
            if skill.get("userInvocable") is not True:
                continue
            name = skill["name"]
            description = skill.get("description") or ""
            if query and query not in f"{name} {description} {plugin['name']}".casefold():
                continue
            items.append({
                "id": selection_id(plugin["installation_id"], name),
                "mainId": principal.main_id,
                "name": name,
                "description": description,
                "scenario": "",
                "type": "ordinary",
                "sourceScope": source_scope,
                "pluginName": plugin["name"],
                "enabled": True,
                "available": True,
            })
    page = items[cursor:cursor + limit]
    next_cursor = cursor + len(page)
    return _result({"items": page, "nextCursor": str(next_cursor) if next_cursor < len(items) else "",
                    "hasMore": next_cursor < len(items)})


@router.get("/personal/selectable-commands")
async def selectable_plugin_commands(
    scope: str = "all", keyword: str = "", cursor: int = 0, limit: int = 20,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    if principal.kind != "end_user":
        raise HTTPException(status_code=403, detail="personal_plugin_user_required")
    if scope not in {"all", "user", "organization"} or cursor < 0 or not 1 <= limit <= 50:
        raise HTTPException(status_code=400, detail="invalid_plugin_command_query")
    query = keyword.strip().casefold()
    items = []
    for plugin in await MongoPluginCatalog().list_enabled(principal.main_id, principal.user_id):
        source_scope = "user" if plugin["source_scope"] == "personal" else "organization"
        if scope != "all" and scope != source_scope:
            continue
        for command in plugin.get("commands") or []:
            if not command.get("definitionId"):
                continue
            name = str(command["name"])
            description = str(command.get("description") or "")
            if query and query not in f"{name} {description} {plugin['name']}".casefold():
                continue
            items.append({
                "id": command_selection_id(plugin["installation_id"], name),
                "mainId": principal.main_id,
                "name": name, "description": description,
                "scenario": "", "type": "ordinary", "entryKind": "command",
                "sourceScope": source_scope, "pluginName": plugin["name"],
                "enabled": True, "available": True,
            })
    page = items[cursor:cursor + limit]
    next_cursor = cursor + len(page)
    return _result({"items": page, "nextCursor": str(next_cursor) if next_cursor < len(items) else "",
                    "hasMore": next_cursor < len(items)})


@router.get("/personal/execution-access")
async def personal_plugin_execution_access(
    principal: ApiPrincipal = Depends(require_api_principal),
):
    if principal.kind != "end_user":
        raise HTTPException(status_code=403, detail="personal_plugin_user_required")
    allowed = await execution_is_allowed(
        main_id=principal.main_id, user_id=principal.user_id, capability="plugin.runtime",
    )
    return _result({"allowed": allowed})


@router.post("/personal/{plugin_id}/ui-launch")
async def launch_plugin_ui(
    plugin_id: str, request: Request,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    if principal.kind != "end_user":
        raise HTTPException(status_code=403, detail="personal_plugin_user_required")
    payload = await request.json()
    conversation_id = payload.get("conversationId") if isinstance(payload, dict) else None
    if conversation_id is not None and (not isinstance(conversation_id, str) or len(conversation_id) > 128):
        raise HTTPException(status_code=400, detail="plugin_ui_session_invalid")
    ticket, kernel_session_id = await dsh_runtime_application.require_plugin_ui().launch(
        tenant_id=principal.main_id, user_id=principal.user_id, plugin_id=plugin_id,
        conversation_id=conversation_id,
    )
    return _result({"url": f"{plugin_ui_public_origin(request)}/launch?ticket={ticket}",
                    "kernelSessionId": kernel_session_id})


@router.get("/personal/ui-sessions/{kernel_session_id}")
async def resolve_plugin_ui_session(
    kernel_session_id: str,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    if principal.kind != "end_user":
        raise HTTPException(status_code=403, detail="personal_plugin_user_required")
    conversation_id = await resolve_conversation(
        get_db(), tenant_id=principal.main_id, user_id=principal.user_id,
        kernel_session_id=kernel_session_id,
    )
    return _result({"conversationId": conversation_id})


@router.get("/{scope}")
async def list_plugins(scope: str, principal: ApiPrincipal = Depends(require_api_principal)):
    owner = _owner(principal, scope)
    plugins = await repository.list(principal.main_id, owner)
    if owner:
        organization = [plugin for plugin in plugins if plugin["scope"] == "organization"]
        allowed = await filter_allowed_resource_ids(
            "plugin", main_id=principal.main_id, user_id=owner,
            resource_ids=(plugin["id"] for plugin in organization),
        )
        denied_names = {plugin["name"] for plugin in organization if plugin["id"] not in allowed}
        plugins = [plugin for plugin in plugins if plugin["name"] not in denied_names and (
            plugin["scope"] == "personal" or plugin["id"] in allowed
        )]
    if owner:
        execution_allowed = await execution_is_allowed(
            main_id=principal.main_id, user_id=owner, capability="plugin.runtime",
        )
        plugins = [{**plugin, "execution_allowed": execution_allowed} for plugin in plugins]
    return _result(plugins)


async def _initialize_organization_access(main_id: str, plugin: dict) -> None:
    policy = get_product_extension().resource_access_policy
    initialize = getattr(policy, "initialize_plugin", None)
    if callable(initialize):
        await initialize(main_id=main_id, plugin_id=plugin["id"])


async def _existing_organization_plugin(main_id: str, name: str) -> bool:
    return bool(await get_db().dsh_plugin_installations.find_one({
        "main_id": main_id, "owner_user_id": "", "engine": "dsh", "name": name,
    }, {"_id": 1}))


async def _check_personal_name(principal: ApiPrincipal, owner: str, name: str) -> None:
    if not owner:
        return
    row = await get_db().dsh_plugin_installations.find_one({
        "main_id": principal.main_id, "owner_user_id": "", "engine": "dsh", "name": name,
    }, {"_id": 1})
    if row:
        allowed = await filter_allowed_resource_ids(
            "plugin", main_id=principal.main_id, user_id=owner,
            resource_ids=(str(row["_id"]),),
        )
        if str(row["_id"]) not in allowed:
            raise HTTPException(status_code=403, detail="personal_plugin_conflicts_with_restricted_enterprise_plugin")


async def _save_inspected_plugin(principal: ApiPrincipal, owner: str, package: dict) -> dict:
    await _check_personal_name(principal, owner, package["name"])
    existed = await _existing_organization_plugin(principal.main_id, package["name"]) if not owner else True
    plugin = await repository.save(main_id=principal.main_id, user_id=owner, **package)
    if not owner and not existed:
        try:
            await _initialize_organization_access(principal.main_id, plugin)
        except Exception:
            # An installation without its initial audience would inherit legacy
            # all-employee access, so remove the incomplete record.
            await repository.remove(main_id=principal.main_id, user_id="", plugin_id=plugin["id"])
            raise
    return plugin


@router.post("/{scope}/preflight")
async def preflight_plugin(
    scope: str, body: InstallRequest,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    owner = _owner(principal, scope)
    await _require_personal_execution(principal, owner)
    if not is_supported_plugin_source(body.spec):
        raise HTTPException(status_code=400, detail="plugin_source_must_be_prebuilt")
    if owner and not is_safe_personal_source(body.spec):
        raise HTTPException(status_code=400, detail="personal_plugin_source_must_be_public")
    try:
        return _result(await inspect_plugin_spec(body.spec))
    except PluginInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{scope}/install")
async def install_plugin(
    scope: str, body: InstallRequest,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    owner = _owner(principal, scope)
    await _require_personal_execution(principal, owner)
    if not is_supported_plugin_source(body.spec):
        raise HTTPException(status_code=400, detail="plugin_source_must_be_prebuilt")
    if owner and not is_safe_personal_source(body.spec):
        raise HTTPException(status_code=400, detail="personal_plugin_source_must_be_public")
    try:
        package = await DshPluginInstaller().inspect_and_install(body.spec)
    except PluginInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _result(await _save_inspected_plugin(principal, owner, package))


@router.post("/{scope}/upload")
async def upload_plugin(
    scope: str, file: UploadFile = File(...),
    principal: ApiPrincipal = Depends(require_api_principal),
):
    owner = _owner(principal, scope)
    await _require_personal_execution(principal, owner)
    filename = (file.filename or "").lower()
    if not filename.endswith((".tgz", ".tar.gz")):
        raise HTTPException(status_code=400, detail="plugin_archive_must_be_tgz")
    content = await read_upload_with_limit(file, max_bytes=MAX_ARCHIVE_BYTES, label="Plugin archive")
    if not content.startswith(b"\x1f\x8b"):
        raise HTTPException(status_code=400, detail="plugin_archive_must_be_gzip")
    archive_id, digest = await save_archive(get_db(), content, main_id=principal.main_id)
    try:
        package = await DshPluginInstaller().inspect_and_install(
            "uploaded-plugin", archive_id=archive_id, archive_digest=digest,
        )
        return _result(await _save_inspected_plugin(principal, owner, package))
    except PluginInstallError as exc:
        await delete_archive(get_db(), archive_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await delete_archive(get_db(), archive_id)
        raise


@router.post("/{scope}/{plugin_id}/verify")
async def verify_plugin(
    scope: str, plugin_id: str, principal: ApiPrincipal = Depends(require_api_principal),
):
    owner = _owner(principal, scope)
    await _require_personal_execution(principal, owner)
    row = await repository.get(main_id=principal.main_id, user_id=owner, plugin_id=plugin_id)
    if row is None:
        raise HTTPException(status_code=404, detail="plugin_not_found")
    updated = await assess_existing_installation(
        row, repository=repository, dsh_version=await _running_version(),
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="plugin_changed_during_verification")
    return _result(updated)


@router.patch("/{scope}/{plugin_id}/enabled")
async def set_plugin_enabled(
    scope: str, plugin_id: str, body: EnabledRequest,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    owner = _owner(principal, scope)
    if body.enabled:
        await _require_personal_execution(principal, owner)
    existing = await repository.get(main_id=principal.main_id, user_id=owner, plugin_id=plugin_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="plugin_not_found")
    if body.enabled:
        dsh_version = await _running_version()
        availability = existing.get("availability") or {}
        if (str(availability.get("dsh_version") or "") != dsh_version
                or not availability.get("release_compatibility_checked")):
            current = await assess_existing_installation(
                existing, repository=repository, dsh_version=dsh_version,
            )
            if current is None:
                raise HTTPException(status_code=409, detail="plugin_changed_during_verification")
            existing = current
    if body.enabled and (existing.get("availability") or {}).get("status") not in {"session_exposed", "runtime_active", "verified"}:
        raise HTTPException(status_code=409, detail="plugin_failed_movo_availability_check")
    row = await repository.set_enabled(
        main_id=principal.main_id, user_id=owner,
        plugin_id=plugin_id, enabled=body.enabled,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="plugin_not_found")
    return _result(row)


@router.delete("/{scope}/{plugin_id}")
async def remove_plugin(
    scope: str, plugin_id: str,
    principal: ApiPrincipal = Depends(require_api_principal),
):
    owner = _owner(principal, scope)
    if not await repository.remove(
        main_id=principal.main_id, user_id=owner, plugin_id=plugin_id,
    ):
        raise HTTPException(status_code=404, detail="plugin_not_found")
    policy = get_product_extension().resource_access_policy
    delete = getattr(policy, "delete_plugin", None)
    if not owner and callable(delete):
        await delete(main_id=principal.main_id, plugin_id=plugin_id)
    return _result({"removed": True})
