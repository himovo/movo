import asyncio
import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.knowledge_references import access, search, admission
from app.enterprise_capabilities.knowledge import document_reader
from app.api.endpoints import knowledge_references as endpoint
from app.api.principal import ApiPrincipal, require_end_user_principal


def matches(row, query):
    for key, value in query.items():
        if key == '$or':
            if not any(matches(row, branch) for branch in value): return False
        elif key == '$and':
            if not all(matches(row, branch) for branch in value): return False
        elif isinstance(value, dict):
            if '$in' in value and row.get(key) not in value['$in']: return False
            if '$nin' in value and row.get(key) in value['$nin']: return False
            if '$exists' in value and (key in row) != value['$exists']: return False
            if '$regex' in value and not re.search(value['$regex'], str(row.get(key) or ''), re.I): return False
        elif row.get(key) != value: return False
    return True


class Cursor:
    def __init__(self, rows): self.rows = rows
    def sort(self, fields): return self
    def skip(self, count): self.rows = self.rows[count:]; return self
    def limit(self, count): self.rows = self.rows[:count]; return self
    async def to_list(self, length): return self.rows[:length]


class Collection:
    def __init__(self, rows): self.rows = rows
    def find(self, query): return Cursor([row for row in self.rows if matches(row, query)])
    async def distinct(self, field, query): return list({row[field] for row in self.rows if matches(row, query)})


class Database:
    def __init__(self, rows): self.rows = rows
    def __getitem__(self, key): return Collection(self.rows.get(key, []))
    def __getattr__(self, key): return self[key]


def install_database(monkeypatch):
    rows = {'knowledge_directories': [{'_id': 'folder', 'main_id': 'tenant', 'name': 'Reports', 'deleted_at': None}],
            'knowledge_documents': [{'_id': name, 'main_id': tenant, 'name': name, 'parse_status': 'succeeded', 'knowledge_base_id': 'folder', 'scope': 'organization', 'deleted_at': None} for name, tenant in [('allowed', 'tenant'), ('secret', 'tenant'), ('foreign', 'other')]]}
    db = Database(rows)
    monkeypatch.setattr(search, 'get_db', lambda: db)
    monkeypatch.setattr(access, 'get_db', lambda: db)
    permitted = {'allowed'}
    class Policy:
        async def require_view(self, *, main_id, user_id, document_id):
            assert (main_id, user_id) == ('tenant', 'user')
            if document_id not in permitted: raise PermissionError('denied')
    monkeypatch.setattr(access, 'get_product_extension', lambda: SimpleNamespace(knowledge_access_policy=Policy()))
    return rows, permitted


def test_search_and_directory_browse_never_disclose_denied_documents(monkeypatch):
    _, permitted = install_database(monkeypatch)
    async def run():
        result = await search.search_references(main_id='tenant', user_id='user', scope='organization')
        assert {item['source_id'] for item in result['items']} == {'folder'}
        folder = await search.search_documents(main_id='tenant', user_id='user', scope='organization', directory_id='folder')
        assert [item['source_id'] for item in folder['items']] == ['allowed']
        permitted.clear()
        result = await search.search_references(main_id='tenant', user_id='user', scope='organization')
        assert result['items'] == []
        with pytest.raises(PermissionError):
            await admission.admit_references([{'scope':'organization','kind':'directory','source_id':'folder'}],main_id='tenant',user_id='user')
    asyncio.run(run())


def test_personal_search_includes_only_own_and_active_shared_documents(monkeypatch):
    db = Database({'knowledge_resources': [{'_id': key, 'main_id': 'tenant', 'owner_user_id': owner, 'status': 'indexed', 'active_document_id': key+'-doc', 'deleted_at': None, 'name': key} for key, owner in [('own','user'),('shared','someone'),('revoked','someone')]],
        'resource_grants': [{'resource_id':'shared','main_id':'tenant','recipient_user_id':'user','resource_type':'personal_knowledge','status':'active'}, {'resource_id':'revoked','main_id':'tenant','recipient_user_id':'user','resource_type':'personal_knowledge','status':'revoked'}]})
    monkeypatch.setattr(search,'get_db',lambda:db); monkeypatch.setattr(access,'get_db',lambda:db)
    result=asyncio.run(search.search_documents(main_id='tenant',user_id='user',scope='personal'))
    assert {row['source_id'] for row in result['items']} == {'own','shared'}


def test_directory_browsing_shows_one_level_and_search_finds_descendants(monkeypatch):
    rows, permitted = install_database(monkeypatch)
    rows['knowledge_directories'].append({'_id': 'child', 'main_id': 'tenant', 'name': 'Manuals', 'parent_id': 'folder', 'deleted_at': None})
    rows['knowledge_documents'].append({'_id': 'manual', 'main_id': 'tenant', 'name': 'Handbook', 'knowledge_base_id': 'child', 'scope': 'organization', 'deleted_at': None})
    rows['knowledge_documents'].append({'_id': 'welcome', 'main_id': 'tenant', 'name': 'Welcome', 'knowledge_base_id': '', 'scope': 'organization', 'deleted_at': None})
    permitted.update({'manual', 'welcome'})

    async def run():
        root = await search.search_references(main_id='tenant', user_id='user', scope='organization')
        assert {item['source_id'] for item in root['items']} == {'folder', 'welcome'}
        folder = await search.search_references(main_id='tenant', user_id='user', scope='organization', directory_id='folder')
        assert {item['source_id'] for item in folder['items']} == {'child', 'allowed'}
        child = await search.search_references(main_id='tenant', user_id='user', scope='organization', directory_id='child')
        assert [item['source_id'] for item in child['items']] == ['manual']
        found = await search.search_references(main_id='tenant', user_id='user', scope='organization', keyword='Handbook')
        assert [item['source_id'] for item in found['items']] == ['manual']

    asyncio.run(run())


def test_admission_ignores_forged_names_and_versions(monkeypatch):
    async def resolve(**kwargs): return {'_id':'real-document','name':'Canonical name','checksum':'real-checksum'}
    monkeypatch.setattr(access,'_resolve_document',resolve)
    refs=[{'scope':'personal','kind':'document','source_id':'resource','name':'Forged','document_id':'foreign'}]
    result=asyncio.run(admission.admit_references(refs,main_id='tenant',user_id='user'))
    assert result[0]['name']=='Canonical name' and result[0]['document_id']=='real-document'


def test_changed_document_is_rejected_before_reading_chunks(monkeypatch):
    async def resolve(**kwargs): return {'_id':'new-version','checksum':'new-checksum'}
    monkeypatch.setattr(document_reader,'_resolve_document',resolve)
    with pytest.raises(LookupError,match='knowledge_reference_changed'):
        asyncio.run(document_reader.read_knowledge_document(tenant_id='tenant',user_id='user',scope='personal',source_id='resource',expected_document_id='old-version'))


def test_reference_api_uses_authenticated_identity(monkeypatch):
    seen=[]
    async def lookup(**kwargs): seen.append(kwargs); return {'items':[],'next_cursor':None}
    monkeypatch.setattr(endpoint,'search_references',lookup)
    app=FastAPI();app.include_router(endpoint.router)
    with TestClient(app) as client: assert client.get('/knowledge/references').status_code==401
    app.dependency_overrides[require_end_user_principal]=lambda:ApiPrincipal('end_user','tenant','user')
    with TestClient(app) as client: assert client.get('/knowledge/references?scope=organization&main_id=foreign&user_id=someone').status_code==200
    assert seen[0]['main_id']=='tenant' and seen[0]['user_id']=='user'


def test_directory_discovery_continues_past_a_fully_denied_page(monkeypatch):
    rows, _ = install_database(monkeypatch)
    template = rows['knowledge_documents'][0]
    rows['knowledge_documents'] = [dict(template, _id=f'denied-{index}') for index in range(65)] + [template]
    async def run():
        first = await search.search_documents(main_id='tenant', user_id='user', scope='organization', directory_id='folder')
        assert first['items'] == [] and first['next_cursor'] == 60
        result = await search.search_references(main_id='tenant', user_id='user', scope='organization', keyword='Reports')
        assert [item['source_id'] for item in result['items']] == ['folder']
    asyncio.run(run())


def test_document_admission_rechecks_access_after_selection(monkeypatch):
    async def revoked(**kwargs):
        raise PermissionError('revoked')
    monkeypatch.setattr(access, '_resolve_document', revoked)
    with pytest.raises(PermissionError, match='revoked'):
        asyncio.run(admission.admit_references([{'scope': 'organization', 'kind': 'document', 'source_id': 'allowed'}], main_id='tenant', user_id='user'))


def test_failed_learning_and_unparsed_documents_remain_selectable(monkeypatch):
    rows, _ = install_database(monkeypatch)
    rows['knowledge_documents'][0]['parse_status'] = 'failed'
    rows['knowledge_resources'] = [{'_id': 'resource', 'main_id': 'tenant', 'owner_user_id': 'user', 'status': 'failed', 'processing_document_id': 'pending', 'name': 'Failed report', 'deleted_at': None}]
    async def run():
        organization = await search.search_documents(main_id='tenant', user_id='user', scope='organization')
        personal = await search.search_documents(main_id='tenant', user_id='user', scope='personal')
        assert organization['items'] == []
        assert [row['source_id'] for row in personal['items']] == ['resource']
    asyncio.run(run())
