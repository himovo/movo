import asyncio
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.api.deps import get_current_admin_user
from app.api.routes import system_audit
from app.system_audit import export


def test_workbook_preserves_literal_text_and_unicode():
    data = export.workbook_bytes([{"actor": "=HYPERLINK(1)", "target": "中文 & <test>\x00", "statusCode": 0}], 'en-US')
    with ZipFile(BytesIO(data)) as archive:
        root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        ns = {'m': export.NS}
        cells = root.findall('.//m:row', ns)[1].findall('m:c', ns)
        assert cells[4].attrib['t'] == 'inlineStr'
        assert cells[4].find('m:is/m:t', ns).text == '=HYPERLINK(1)'
        assert cells[5].find('m:is/m:t', ns).text == '中文 & <test>'
        assert len(cells) == 7
        assert not root.findall('.//m:f', ns)
        for name in archive.namelist():
            ET.fromstring(archive.read(name))


def test_export_uses_authenticated_tenant_and_filters(monkeypatch):
    seen = []
    class Query:
        async def list_logs(self, **kwargs):
            seen.append(kwargs)
            return {'total': 21, 'items': [{'id': str(i)} for i in range(21)]}
    monkeypatch.setattr(export, 'SystemAuditQuery', Query)
    app = FastAPI()
    app.include_router(system_audit.router)
    app.dependency_overrides[get_current_admin_user] = lambda: {'main_id': 'tenant-a'}
    with TestClient(app) as client:
        response = client.get('/export?category=management&module=settings&keyword=admin&result=failed&mainId=other')
    assert response.status_code == 200
    assert response.headers['content-type'] == export.MIME_TYPE
    assert '.xlsx' in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    assert seen == [dict(main_id='tenant-a', category='management', page=1, page_size=10001, module='settings', keyword='admin', result='failed')]
    with ZipFile(BytesIO(response.content)) as archive:
        assert len(ET.fromstring(archive.read('xl/worksheets/sheet1.xml')).findall(f'.//{{{export.NS}}}row')) == 22


def test_export_rejects_excess_instead_of_truncating(monkeypatch):
    class Query:
        async def list_logs(self, **kwargs): return {'total': 10001, 'items': []}
    monkeypatch.setattr(export, 'SystemAuditQuery', Query)
    with pytest.raises(HTTPException) as error:
        asyncio.run(export.export_audit(main_id='a', category='agent', keyword='', result='', module='', language='en'))
    assert error.value.status_code == 413


def test_export_requires_authentication():
    app = FastAPI()
    app.include_router(system_audit.router)
    with TestClient(app) as client:
        assert client.get('/export').status_code in (401, 403)
