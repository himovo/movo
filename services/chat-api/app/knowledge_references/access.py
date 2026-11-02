from app.core.db import get_db
from app.product.extensions import get_product_extension
from app.enterprise_capabilities.knowledge.document_reader import _resolve_document


async def visible_documents(documents, *, main_id, user_id):
    policy = get_product_extension().knowledge_access_policy
    if policy is None:
        return documents
    bulk = getattr(policy, "filter_visible_documents", None)
    if bulk:
        ids = await bulk(main_id=main_id, user_id=user_id, documents=documents)
        return [row for row in documents if str(row['_id']) in ids]
    rows = []
    for row in documents:
        try:
            await policy.require_view(main_id=main_id, user_id=user_id, document_id=str(row['_id']))
            rows.append(row)
        except (PermissionError, LookupError):
            continue
    return rows


async def directory_tree(*, main_id, user_id, scope):
    query = {"main_id": main_id, "deleted_at": None}
    collection = 'knowledge_directories'
    if scope == 'personal':
        collection = 'personal_knowledge_directories'
        query['owner_user_id'] = user_id
    return await get_db()[collection].find(query).to_list(length=None)


def descendants(rows, directory_id):
    ids = {directory_id}
    while True:
        expanded = ids | {str(row['_id']) for row in rows if str(row.get('parent_id') or '') in ids}
        if expanded == ids:
            return ids
        ids = expanded


def directory_path(rows, directory_id):
    by_id = {str(row['_id']): row for row in rows}
    parts, seen = [], set()
    while directory_id in by_id and directory_id not in seen:
        seen.add(directory_id)
        row = by_id[directory_id]
        parts.append(str(row.get('name') or ''))
        directory_id = str(row.get('parent_id') or '')
    return ' / '.join(reversed(parts))


async def document_reference(*, main_id, user_id, scope, source_id):
    document = await _resolve_document(tenant_id=main_id, user_id=user_id, scope=scope, source_id=source_id, require_parsed=False)
    return {"scope": scope, "kind": "document", "source_id": source_id,
            "document_id": str(document['_id']), "checksum": str(document.get('checksum') or ''),
            "name": str(document.get('name') or document.get('original_filename') or source_id)}
