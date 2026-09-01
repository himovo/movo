from datetime import datetime, timezone

from app.system_audit.middleware import _module_key
from app.system_audit.query import SystemAuditQuery


def test_module_key_uses_admin_route_namespace() -> None:
    assert _module_key("/api/models/model-1") == "models"
    assert _module_key("/api/position-roles/role-1") == "position-roles"
    assert _module_key("/api/settings/external-search") == "settings"


def test_management_item_exposes_safe_operation_metadata() -> None:
    item = SystemAuditQuery._management_item({
        "_id": "audit-1",
        "module_label": "模型中心",
        "action": "update",
        "actor": "admin@example.com",
        "target": "/api/models/model-1",
        "result": "success",
        "status_code": 200,
        "method": "PUT",
        "route": "/api/models/{model_id}",
        "duration_ms": 12,
        "client_ip": "127.0.0.1",
        "occurred_at": datetime(2026, 8, 23, 1, 2, tzinfo=timezone.utc),
        "body": {"apiKey": "must-not-leak"},
    })

    assert item["module"] == "模型中心"
    assert item["details"] == {
        "method": "PUT",
        "route": "/api/models/{model_id}",
        "durationMs": 12,
        "clientIp": "127.0.0.1",
    }
    assert "body" not in item["details"]


def test_permission_denial_is_a_failed_agent_activity() -> None:
    item = SystemAuditQuery._position_item({
        "_id": "audit-2",
        "action": "capability.denied",
        "actor": "employee-1",
        "target_id": "code_generation",
        "details": {"target": "code_generation"},
        "created_at": datetime(2026, 8, 23, 1, 2, tzinfo=timezone.utc),
    })
    assert item["category"] == "agent"
    assert item["result"] == "failed"
    assert item["target"] == "code_generation"
