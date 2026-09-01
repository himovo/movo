from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin_user
from app.core.db import get_db

router = APIRouter()

KNOWLEDGE_DIR_COLLECTION = "knowledge_directories"
KNOWLEDGE_DOC_COLLECTION = "knowledge_documents"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _main_id(current_user: dict) -> str:
    return str(current_user.get("main_id", "default"))


def _build_path(parent: dict | None) -> tuple[list[str], list[str]]:
    if parent is None:
        return [], []
    return (
        [*parent.get("path_ids", []), str(parent["_id"])],
        [*parent.get("path_names", []), parent.get("name", "")],
    )


async def _update_descendant_paths(
    main_id: str,
    moved_id: str,
    moved_name: str,
    new_path_ids: list[str],
    new_path_names: list[str],
) -> None:
    db = get_db()
    cursor = db[KNOWLEDGE_DIR_COLLECTION].find({
        "main_id": main_id,
        "path_ids": moved_id,
        "deleted_at": None
    })
    descendants = await cursor.to_list(length=5000)
    for doc in descendants:
        path_ids = doc.get("path_ids", [])
        path_names = doc.get("path_names", [])
        if moved_id not in path_ids:
            continue
        idx = path_ids.index(moved_id)
        suffix_ids = path_ids[idx + 1 :]
        suffix_names = path_names[idx + 1 :]
        next_ids = [*new_path_ids, moved_id, *suffix_ids]
        next_names = [*new_path_names, moved_name, *suffix_names]
        await db[KNOWLEDGE_DIR_COLLECTION].update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "path_ids": next_ids,
                "path_names": next_names,
                "updated_at": _now()
            }},
        )


class DirectoryCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parentId: str | None = None


class DirectoryUpdatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DirectoryMovePayload(BaseModel):
    parentId: str | None = None


@router.get("/tree")
async def get_directory_tree(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, Any]]:
    main_id = _main_id(current_user)
    db = get_db()
    
    # 查找所有未删除的目录
    cursor = db[KNOWLEDGE_DIR_COLLECTION].find({
        "main_id": main_id,
        "deleted_at": None
    }).sort("created_at", 1)
    dirs = await cursor.to_list(length=5000)
    
    # 聚合统计每个目录直接关联的文档数量 (未删除的)
    doc_counts: dict[str, int] = {}
    doc_cursor = db[KNOWLEDGE_DOC_COLLECTION].aggregate([
        {
            "$match": {
                "main_id": main_id,
                "deleted_at": None
            }
        },
        {
            "$group": {
                "_id": "$knowledge_base_id",
                "count": {"$sum": 1}
            }
        }
    ])
    async for item in doc_cursor:
        kb_id = str(item["_id"] or "").strip()
        if kb_id:
            doc_counts[kb_id] = item["count"]

    # 构造嵌套的树结构
    node_map: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    
    for row in dirs:
        node_id = str(row["_id"])
        node_map[node_id] = {
            "id": node_id,
            "name": row.get("name", ""),
            "parentId": row.get("parent_id"),
            "documentCount": doc_counts.get(node_id, 0),
            "totalDocumentCount": doc_counts.get(node_id, 0),
            "children": []
        }
        
    for node in node_map.values():
        p_id = node["parentId"]
        if p_id and p_id in node_map:
            node_map[p_id]["children"].append(node)
        else:
            roots.append(node)
            
    # 递归计算总文档数 (包含子孙目录)
    def calc_totals(curr: dict[str, Any]) -> int:
        total = curr["documentCount"]
        for child in curr["children"]:
            total += calc_totals(child)
        curr["totalDocumentCount"] = total
        return total

    for root in roots:
        calc_totals(root)
        
    return roots


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_directory(
    payload: DirectoryCreatePayload,
    current_user: dict = Depends(get_current_admin_user)
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    
    name = payload.name.strip()
    parent_id = payload.parentId or None
    
    # 同级线下同名目录唯一性校验 (deleted_at: None)
    duplicate = await db[KNOWLEDGE_DIR_COLLECTION].find_one({
        "main_id": main_id,
        "parent_id": parent_id,
        "name": name,
        "deleted_at": None
    })
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同级线下已存在同名目录"
        )
        
    parent = None
    if parent_id:
        parent = await db[KNOWLEDGE_DIR_COLLECTION].find_one({
            "_id": parent_id,
            "main_id": main_id,
            "deleted_at": None
        })
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="父目录不存在"
            )
            
    path_ids, path_names = _build_path(parent)
    now = _now()
    directory_id = uuid.uuid4().hex
    
    await db[KNOWLEDGE_DIR_COLLECTION].insert_one({
        "_id": directory_id,
        "main_id": main_id,
        "name": name,
        "parent_id": parent_id,
        "path_ids": path_ids,
        "path_names": path_names,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None
    })
    
    return {
        "id": directory_id,
        "name": name,
        "parentId": parent_id
    }


@router.put("/{directory_id}")
async def update_directory(
    directory_id: str,
    payload: DirectoryUpdatePayload,
    current_user: dict = Depends(get_current_admin_user)
) -> dict[str, Any]:
    main_id = _main_id(current_user)
    db = get_db()
    
    name = payload.name.strip()
    
    existing = await db[KNOWLEDGE_DIR_COLLECTION].find_one({
        "_id": directory_id,
        "main_id": main_id,
        "deleted_at": None
    })
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目录不存在"
        )
        
    parent_id = existing.get("parent_id")
    
    # 唯一性校验 (如果名字变了)
    old_name = existing.get("name", "")
    if name != old_name:
        duplicate = await db[KNOWLEDGE_DIR_COLLECTION].find_one({
            "main_id": main_id,
            "parent_id": parent_id,
            "name": name,
            "deleted_at": None
        })
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="同级线下已存在同名目录"
            )
            
        await db[KNOWLEDGE_DIR_COLLECTION].update_one(
            {"_id": directory_id},
            {"$set": {
                "name": name,
                "updated_at": _now()
            }}
        )
        
        # 级联更新子孙目录的 path_names
        cursor = db[KNOWLEDGE_DIR_COLLECTION].find({
            "main_id": main_id,
            "path_ids": directory_id,
            "deleted_at": None
        })
        descendants = await cursor.to_list(length=5000)
        for doc in descendants:
            path_ids = doc.get("path_ids", [])
            path_names = doc.get("path_names", [])
            if directory_id in path_ids:
                idx = path_ids.index(directory_id)
                new_names = list(path_names)
                if idx < len(new_names):
                    new_names[idx] = name
                await db[KNOWLEDGE_DIR_COLLECTION].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "path_names": new_names,
                        "updated_at": _now()
                    }}
                )
                
    return {
        "id": directory_id,
        "name": name,
        "parentId": parent_id
    }


@router.post("/{directory_id}/move")
async def move_directory(
    directory_id: str,
    payload: DirectoryMovePayload,
    current_user: dict = Depends(get_current_admin_user)
) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    
    directory = await db[KNOWLEDGE_DIR_COLLECTION].find_one({
        "_id": directory_id,
        "main_id": main_id,
        "deleted_at": None
    })
    if directory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目录不存在"
        )
        
    parent_id = payload.parentId or None
    
    # 规则校验
    if parent_id == directory_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移动到自身目录"
        )
        
    parent = None
    if parent_id:
        # 防循环移动校验
        if directory_id in directory.get("path_ids", []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="循环移动错误"
            )
            
        parent = await db[KNOWLEDGE_DIR_COLLECTION].find_one({
            "_id": parent_id,
            "main_id": main_id,
            "deleted_at": None
        })
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="目标父目录不存在"
            )
            
        if directory_id in parent.get("path_ids", []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能移动到自身的子目录下"
            )
            
    # 校验移动后目标父级下是否重名
    duplicate = await db[KNOWLEDGE_DIR_COLLECTION].find_one({
        "main_id": main_id,
        "parent_id": parent_id,
        "name": directory.get("name"),
        "deleted_at": None
    })
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="目标目录下已存在同名目录"
        )
        
    new_path_ids, new_path_names = _build_path(parent)
    
    await db[KNOWLEDGE_DIR_COLLECTION].update_one(
        {"_id": directory_id},
        {"$set": {
            "parent_id": parent_id,
            "path_ids": new_path_ids,
            "path_names": new_path_names,
            "updated_at": _now()
        }}
    )
    
    # 级联更新子孙目录
    await _update_descendant_paths(
        main_id=main_id,
        moved_id=directory_id,
        moved_name=directory.get("name", ""),
        new_path_ids=new_path_ids,
        new_path_names=new_path_names
    )
    
    return {"success": True}


@router.delete("/{directory_id}")
async def delete_directory(
    directory_id: str,
    current_user: dict = Depends(get_current_admin_user)
) -> dict[str, bool]:
    main_id = _main_id(current_user)
    db = get_db()
    
    existing = await db[KNOWLEDGE_DIR_COLLECTION].find_one({
        "_id": directory_id,
        "main_id": main_id,
        "deleted_at": None
    })
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目录不存在"
        )

    descendant_cursor = db[KNOWLEDGE_DIR_COLLECTION].find(
        {
            "main_id": main_id,
            "path_ids": directory_id,
            "deleted_at": None
        },
        {"_id": 1}
    )
    directory_ids = [directory_id]
    async for row in descendant_cursor:
        row_id = row.get("_id")
        if row_id:
            directory_ids.append(str(row_id))

    # 校验该目录及子目录下是否存在未删除文档
    doc_count = await db[KNOWLEDGE_DOC_COLLECTION].count_documents({
        "main_id": main_id,
        "knowledge_base_id": {"$in": directory_ids},
        "deleted_at": None
    })
    if doc_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该目录或其子目录下存在知识文档，无法删除"
        )

    # 保守删除策略：校验是否存在子目录
    child_count = await db[KNOWLEDGE_DIR_COLLECTION].count_documents({
        "main_id": main_id,
        "parent_id": directory_id,
        "deleted_at": None
    })
    if child_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该目录存在子目录，无法删除"
        )
        
    # 软删除目录
    await db[KNOWLEDGE_DIR_COLLECTION].update_one(
        {"_id": directory_id},
        {"$set": {
            "deleted_at": _now(),
            "updated_at": _now()
        }}
    )
    
    return {"success": True}


async def ensure_indexes() -> None:
    db = get_db()
    # 1. 基础父级层级查询索引
    await db[KNOWLEDGE_DIR_COLLECTION].create_index(
        [("main_id", 1), ("parent_id", 1), ("deleted_at", 1)],
        name="idx_knowledge_dirs_parent"
    )
    # 2. 路径树查询索引
    await db[KNOWLEDGE_DIR_COLLECTION].create_index(
        [("main_id", 1), ("path_ids", 1)],
        name="idx_knowledge_dirs_path"
    )
    # 3. 局部唯一重名校验索引 (deleted_at: null)
    await db[KNOWLEDGE_DIR_COLLECTION].create_index(
        [("main_id", 1), ("parent_id", 1), ("name", 1)],
        unique=True,
        partialFilterExpression={"deleted_at": None},
        name="uniq_knowledge_dirs_parent_name"
    )
