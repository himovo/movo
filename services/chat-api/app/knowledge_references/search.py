"""Bounded name lookup; no unfiltered enterprise names or totals leave the server."""
import re
from app.core.db import get_db
from .access import directory_tree, directory_path, descendants, visible_documents

SCAN_SIZE = 60


async def prepare_lookup(*, main_id, user_id, scope):
    tree = await directory_tree(main_id=main_id, user_id=user_id, scope=scope)
    grants = await get_db().resource_grants.distinct('resource_id', {"main_id": main_id, "recipient_user_id": user_id, "resource_type": "personal_knowledge", "status": "active"}) if scope == 'personal' else []
    return {"tree": tree, "grants": grants}


async def search_documents(*, main_id, user_id, scope, keyword='', directory_id='', cursor=0, lookup=None, include_descendants=False):
    if scope not in {"personal", "organization"}:
        raise ValueError("knowledge_scope_invalid")
    db = get_db()
    lookup = lookup or await prepare_lookup(main_id=main_id, user_id=user_id, scope=scope)
    tree = lookup["tree"]
    query = {"main_id": main_id, "deleted_at": None}
    collection = 'knowledge_documents'
    directory_field = 'knowledge_base_id'
    if scope == 'personal':
        collection, directory_field = 'knowledge_resources', 'directory_id'
        grants = lookup["grants"]
        query.update({"$or": [{"owner_user_id": user_id}, {"_id": {"$in": grants}}]})
    else:
        query.update({"$or": [{"scope": "organization"}, {"scope": {"$exists": False}}]})
    browsing = not keyword.strip()
    if directory_id:
        if directory_id not in {str(row['_id']) for row in tree}:
            raise PermissionError('knowledge_reference_unavailable')
        if browsing:
            query[directory_field] = {"$in": list(descendants(tree, directory_id))} if include_descendants else directory_id
    elif browsing:
        root_locations = [{directory_field: ''}, {directory_field: None}, {directory_field: {"$exists": False}}]
        if scope == 'personal':
            query['$and'] = [{"$or": root_locations + [{"_id": {"$in": lookup['grants']}}]}]
        else:
            query['$and'] = [{"$or": root_locations}]
    if keyword.strip():
        query.setdefault('$and', []).append({"$or": [{field: {"$regex": re.escape(keyword.strip()), "$options": 'i'}} for field in ['name', 'original_filename']]})
    candidates = await db[collection].find(query).sort([('name', 1), ('_id', 1)]).skip(cursor).limit(SCAN_SIZE + 1).to_list(length=SCAN_SIZE + 1)
    more = len(candidates) > SCAN_SIZE
    candidates = candidates[:SCAN_SIZE]
    allowed = await visible_documents(candidates, main_id=main_id, user_id=user_id) if scope == 'organization' else candidates
    items = [{"kind": 'document', "scope": scope, "source_id": str(row['_id']), "name": str(row.get('name') or row.get('original_filename') or ''), "path": directory_path(tree, str(row.get(directory_field) or ''))} for row in allowed]
    return {"items": items, "next_cursor": cursor + SCAN_SIZE if more else None}


async def search_references(*, main_id, user_id, scope, keyword='', directory_id='', cursor=0):
    lookup = await prepare_lookup(main_id=main_id, user_id=user_id, scope=scope)
    page = await search_documents(main_id=main_id, user_id=user_id, scope=scope, keyword=keyword, directory_id=directory_id, cursor=cursor, lookup=lookup)
    tree = lookup["tree"]
    browsing = not keyword.strip()
    matches = [row for row in tree if (not browsing or str(row.get('parent_id') or '') == directory_id) and keyword.casefold() in str(row.get('name') or '').casefold()]
    folders = []
    for row in matches[cursor:cursor + SCAN_SIZE]:
        source_id = str(row['_id'])
        # A directory is disclosed only when an authorized document can be found in it.
        position = 0
        while True:
            contents = await search_documents(main_id=main_id, user_id=user_id, scope=scope, directory_id=source_id, cursor=position, lookup=lookup, include_descendants=True)
            if contents['items']:
                folders.append({"kind": 'directory', "scope": scope, "source_id": source_id, "name": str(row.get('name') or ''), "path": directory_path(tree, source_id)})
                break
            if contents['next_cursor'] is None:
                break
            position = contents['next_cursor']
    directory_more = len(matches) > cursor + SCAN_SIZE
    return {**page, "items": folders + page['items'], "next_cursor": cursor + SCAN_SIZE if directory_more else page["next_cursor"]}
