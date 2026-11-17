"""Internal admission API used by trusted Runtime hosts, never browser clients."""
import anyio

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field

from .execution_workers import run_script_work


class PermitRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=128)
    key: str = Field(default='', max_length=256)
    token: str = Field(default='', max_length=128)
    parent: str = Field(default='', max_length=128)


def permit_router(authorize, permits):
    def authorize_header(authorization: str | None = Header(default=None)):
        authorize(authorization)
    router = APIRouter(dependencies=[Depends(authorize_header)])

    @router.post('/v1/execution-permits/{operation}')
    async def execute(operation: str, body: PermitRequest):
        def work():
            try:
                pool = permits()
                if operation == 'acquire':
                    if not body.key:
                        raise ValueError('Execution key is required')
                    return pool.acquire(body.owner, body.key, body.parent)
                if operation == 'cancel':
                    pool.cancel(body.owner, body.key)
                    return {'ok': True}
                if operation == 'heartbeat':
                    return pool.heartbeat(body.token, body.owner)
                if operation == 'release':
                    pool.release(body.token, body.owner)
                    return {'ok': True}
                raise HTTPException(404, 'Unknown execution permit operation')
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(429, str(exc)) from exc
        if operation == 'acquire':
            return await run_script_work(work)
        return await anyio.to_thread.run_sync(work)
    return router
