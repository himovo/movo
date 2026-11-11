from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import get_current_admin_user
from app.core.db import get_db
from app.repositories.directory_repository import AUDIT_LOG_COLLECTION, DEPARTMENT_COLLECTION
from app.services.department_import import MAX_BYTES, parse_workbook, plan_import, template_bytes

router = APIRouter()


async def _root_and_departments(main_id: str):
    db = get_db()
    rows = await db[DEPARTMENT_COLLECTION].find({"main_id": main_id}).to_list(length=5000)
    root = next((row for row in rows if row.get("code") == "root"), None)
    if root is None:
        raise HTTPException(status_code=409, detail="root_missing")
    return root, rows


async def _uploaded_bytes(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="xlsx_required")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file_too_large")
    return content


@router.get("/departments/import-template")
async def department_import_template(current_user: dict = Depends(get_current_admin_user), accept_language: str = Header(default="en")):
    root, _ = await _root_and_departments(str(current_user.get("main_id") or "default"))
    return Response(template_bytes(str(root.get("name") or "root"), accept_language), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="department-import-template.xlsx"', "Cache-Control": "no-store"})


@router.post("/departments/import-preview")
async def department_import_preview(file: UploadFile = File(...), current_user: dict = Depends(get_current_admin_user)):
    main_id = str(current_user.get("main_id") or "default")
    content = await _uploaded_bytes(file)
    root, existing = await _root_and_departments(main_id)
    try:
        rows = parse_workbook(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**plan_import(rows, existing, str(root.get("name") or "root")), "digest": hashlib.sha256(content).hexdigest()}


@router.post("/departments/import-commit")
async def department_import_commit(file: UploadFile = File(...), digest: str = File(...), current_user: dict = Depends(get_current_admin_user)):
    main_id = str(current_user.get("main_id") or "default")
    content = await _uploaded_bytes(file)
    if hashlib.sha256(content).hexdigest() != digest:
        raise HTTPException(status_code=409, detail="file_changed")
    root, existing = await _root_and_departments(main_id)
    try:
        rows = parse_workbook(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    plan = plan_import(rows, existing, str(root.get("name") or "root"))
    if plan["errors"]:
        raise HTTPException(status_code=409, detail="preview_outdated")
    db = get_db()
    by_path = {"/".join([*row.get("path_names", []), row.get("name", "")]): row for row in existing}
    inserted: list[ObjectId] = []
    try:
        for item in plan["items"]:
            if item["action"] != "create":
                continue
            path = item["path"]
            parent_path, name = path.rsplit("/", 1)
            parent = by_path[parent_path]
            parent_id = str(parent["_id"])
            if await db[DEPARTMENT_COLLECTION].find_one({"main_id": main_id, "parent_id": parent_id, "name": name}):
                raise HTTPException(status_code=409, detail="preview_outdated")
            new_id = ObjectId()
            now = datetime.now(timezone.utc)
            document = {"_id": new_id, "main_id": main_id, "name": name, "code": f"import_{new_id}", "parent_id": parent_id, "path_ids": [*parent.get("path_ids", []), parent_id], "path_names": [*parent.get("path_names", []), parent.get("name", "")], "status": "active", "source": "local", "source_dept_id": "", "created_at": now, "updated_at": now}
            await db[DEPARTMENT_COLLECTION].insert_one(document)
            inserted.append(new_id)
            by_path[path] = document
    except Exception:
        if inserted:
            await db[DEPARTMENT_COLLECTION].delete_many({"main_id": main_id, "_id": {"$in": inserted}})
        raise
    await db[AUDIT_LOG_COLLECTION].insert_one({"main_id": main_id, "operator": str(current_user.get("username") or ""), "action": "import", "target_type": "department", "target_id": "", "payload": {"created": len(inserted), "skipped": plan["skipCount"]}, "created_at": datetime.now(timezone.utc)})
    return {"created": len(inserted), "skipped": plan["skipCount"]}
