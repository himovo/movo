from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.principal import ApiPrincipal, require_end_user_principal
from app.knowledge_references.search import search_references

router = APIRouter(prefix='/knowledge/references', tags=['knowledge-references'])


@router.get('')
async def list_references(
    principal: ApiPrincipal = Depends(require_end_user_principal),
    scope: Literal['personal', 'organization'] = 'personal',
    keyword: str = Query('', max_length=120),
    directory_id: str = Query('', max_length=128),
    cursor: int = Query(0, ge=0, le=1_000_000),
):
    try:
        return await search_references(main_id=principal.main_id, user_id=principal.user_id,
            scope=scope, keyword=keyword, directory_id=directory_id, cursor=cursor)
    except (PermissionError, LookupError) as exc:
        raise HTTPException(status_code=403, detail='knowledge_reference_unavailable') from exc
