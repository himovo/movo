import asyncio
import json
import httpx
import pytest
from app.services.mcp_session_pool import McpSessionPool


def test_reuse_user_credential_isolation_and_no_replay():
    async def run():
        methods=[]
        broken=False
        def serve(request):
            body=json.loads(request.content); methods.append(body['method'])
            if body['method']=='notifications/initialized':return httpx.Response(202)
            if body['method']=='initialize':
                return httpx.Response(200,headers={'Mcp-Session-Id':str(len(methods))},json={
                    'jsonrpc':'2.0','id':body['id'],'result':{'protocolVersion':'2025-06-18'}})
            if broken:raise httpx.ReadError('connection lost after execution')
            return httpx.Response(200,json={'jsonrpc':'2.0','id':body['id'],'result':{'content':[]}})
        pool=McpSessionPool(transport=httpx.MockTransport(serve))
        async def call(actor='a',token='one'):
            return await pool.call(endpoint='http://mcp.test',headers={'Authorization':token},timeout=1,
                                   actor=['tenant',actor],method='tools/call',params={'name':'test'})
        try:
            await call(); await call()
            assert methods==['initialize','notifications/initialized','tools/call','tools/call']
            await call('b'); await call(token='rotated')
            assert methods.count('initialize')==3
            broken=True; before=len(methods)
            with pytest.raises(httpx.ReadError):await call()
            assert methods[before:]==['tools/call']
            broken=False; await call()
            assert methods[-3:]==['initialize','notifications/initialized','tools/call']
        finally:await pool.close()
        assert not pool._sessions
    asyncio.run(run())


def test_bounded_pool_preserves_active_session():
    async def run():
        started=asyncio.Event(); release=asyncio.Event()
        async def serve(request):
            body=json.loads(request.content)
            if body['method']=='notifications/initialized':return httpx.Response(202)
            if body['method']=='tools/call' and body.get('params',{}).get('name')=='block':
                started.set(); await release.wait()
            return httpx.Response(200,json={'jsonrpc':'2.0','id':body['id'],'result':{}})
        pool=McpSessionPool(limit=1,transport=httpx.MockTransport(serve))
        args=dict(endpoint='http://mcp.test',headers={},timeout=1,method='tools/call')
        try:
            first=asyncio.create_task(pool.call(**args,actor='a',params={'name':'block'}))
            await started.wait()
            await pool.call(**args,actor='b',params={'name':'other'})
            assert len(pool._sessions)==1
            release.set(); await first
        finally:release.set(); await pool.close()
    asyncio.run(run())
