"""Import-level proof that the session-share router is mounted under /api.

Plan todo 5: the new router must be registered under the same ``/api``
prefix as the other routers. FastAPI 0.141 includes routers lazily:
``include_router`` records an ``_IncludedRouter`` wrapper instead of
flattening APIRoutes into ``app.routes``, so an ``isinstance(route,
APIRoute)`` scan never sees included routes. The test therefore resolves
the session-share router's wrapper and materializes its effective
(prefixed) route contexts.
"""

from __future__ import annotations

from fastapi.routing import APIRoute, _IncludedRouter

from app.api.endpoints import session_shares
from app.main import app


def test_session_share_router_mounted_under_api_prefix() -> None:
    included = [
        route
        for route in app.routes
        if isinstance(route, _IncludedRouter)
        and route.original_router is session_shares.router
    ]
    assert included, "session_shares.router is not registered in app.main"

    mounted = {
        (method, ctx.path)
        for ctx in included[0].effective_candidates()
        if isinstance(ctx.original_route, APIRoute)
        for method in ctx.original_route.methods
    }
    expected = {
        ("POST", "/api/sessions/{session_id}/share"),
        ("POST", "/api/session-shares/{token}/join"),
        ("DELETE", "/api/sessions/{session_id}/share"),
        ("GET", "/api/sessions/{session_id}/participants"),
        ("DELETE", "/api/sessions/{session_id}/participants/me"),
        ("DELETE", "/api/sessions/{session_id}/participants/{user_id}"),
    }
    missing = expected - mounted
    assert not missing, f"session-share routes missing under /api: {sorted(missing)}"
