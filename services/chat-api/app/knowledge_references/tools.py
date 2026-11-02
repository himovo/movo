from .search import search_documents


async def knowledge_browse(arguments, context):
    page = await search_documents(main_id=context.tenant_id, user_id=context.user_id,
        scope=str(arguments.get('scope') or ''), directory_id=str(arguments.get('directory_id') or ''),
        keyword=str(arguments.get('query') or '')[:120], cursor=max(0, int(arguments.get('cursor') or 0)))
    return {"success": True, **page}
