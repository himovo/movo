"""Parse an authorized knowledge original without requiring an indexing job."""
import asyncio
from app.core.config import get_settings
from app.services.knowledge_preview_stream import _local_path
from app.services.document_parser import document_parser_service
from app.services.runtime_parse_service import runtime_parse_service


async def read_original(document, *, scope, source_id, offset, char_offset, max_chars):
    if offset != 0:
        raise ValueError('knowledge_cursor_out_of_range')
    key = str(document.get('storage_key') or '')
    if not key:
        raise LookupError('knowledge_original_unavailable')
    filename = str(document.get('original_filename') or document.get('name') or '')
    settings = get_settings()
    if str(document.get('storage_type') or settings.KNOWLEDGE_STORAGE_TYPE or 'local') == 'oss':
        import oss2
        def sign():
            bucket = oss2.Bucket(oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET),
                settings.KNOWLEDGE_OSS_ENDPOINT or settings.OSS_ENDPOINT,
                document.get('storage_bucket') or settings.KNOWLEDGE_OSS_BUCKET or settings.OSS_BUCKET_NAME)
            return bucket.sign_url('GET', key, 300)
        url = await asyncio.to_thread(sign)
        parsed = await document_parser_service.parse_document(document={'filename': filename, 'signed_url': url})
    else:
        path = await asyncio.to_thread(_local_path, key)
        parsed = await runtime_parse_service._parse_local_document(item={'filename': filename, 'local_path': str(path)})
    if not parsed.get('ok'):
        raise LookupError('knowledge_original_parse_failed')
    text = str(parsed.get('markdown') or '')
    if not text:
        raise LookupError('knowledge_document_has_no_text')
    if char_offset >= len(text):
        raise ValueError('knowledge_cursor_out_of_range')
    end = min(len(text), char_offset + max_chars)
    return {'success': True, 'scope': scope, 'source_id': source_id, 'document_id': str(document['_id']),
        'document_name': str(document.get('name') or filename), 'checksum': str(document.get('checksum') or ''),
        'chunk_stage': 'runtime_parse', 'total_chunks': 1,
        'segments': [{'chunk_id': 'original', 'ordinal': 0, 'char_offset': char_offset, 'text': text[char_offset:end]}],
        'has_more': end < len(text), 'next_cursor': {'offset': 0, 'char_offset': end} if end < len(text) else None}
