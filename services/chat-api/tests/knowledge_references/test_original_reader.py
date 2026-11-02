import asyncio
from types import SimpleNamespace
import pytest
from app.knowledge_references import original_reader


def test_failed_original_can_be_parsed_and_read_in_pages(monkeypatch, tmp_path):
    file = tmp_path / 'report.txt'
    file.write_text('Original report content')
    monkeypatch.setattr(original_reader, 'get_settings', lambda: SimpleNamespace(KNOWLEDGE_STORAGE_TYPE='local'))
    monkeypatch.setattr(original_reader, '_local_path', lambda key: file)
    document = {'_id': 'doc', 'parse_status': 'failed', 'storage_key': 'registered-key', 'original_filename': 'report.txt'}
    first = asyncio.run(original_reader.read_original(document, scope='organization', source_id='doc', offset=0, char_offset=0, max_chars=8))
    assert first['segments'][0]['text'] == 'Original'
    assert first['has_more']
    second = asyncio.run(original_reader.read_original(document, scope='organization', source_id='doc', max_chars=100, **first['next_cursor']))
    assert second['segments'][0]['text'] == ' report content'
    assert not second['has_more']


def test_missing_original_is_not_reported_as_read(monkeypatch):
    with pytest.raises(LookupError, match='knowledge_original_unavailable'):
        asyncio.run(original_reader.read_original({'_id': 'doc'}, scope='personal', source_id='resource', offset=0, char_offset=0, max_chars=1000))
