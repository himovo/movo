import asyncio

from app.services.end_user_tenant_access import load_tenant_candidates, project_tenant_candidate, resolve_space_type


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length):
        return self.rows[:length]


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query):
        main_ids = set(query.get("main_id", {}).get("$in", []))
        status = query.get("status")
        return _Cursor([
            row for row in self.rows
            if row.get("main_id") in main_ids and (status is None or row.get("status") == status)
        ])


class _Db:
    def __init__(self, organizations, admin_accounts):
        self.organizations = _Collection(organizations)
        self.admin_accounts = _Collection(admin_accounts)


def test_authoritative_organization_name_replaces_technical_tenant_id() -> None:
    candidate = project_tenant_candidate(
        {"_id": "u1", "main_id": "org_deadbeef", "login_name": "employee", "name": "普通员工"},
        {"main_id": "org_deadbeef", "org_name": "示例科技"},
        None,
    )
    assert candidate["orgName"] == "示例科技"
    assert candidate["spaceType"] == "enterprise"
    assert candidate["canAccessAdmin"] is False


def test_explicit_enterprise_identity_wins_over_stale_personal_organization() -> None:
    candidate = project_tenant_candidate(
        {
            "_id": "u1",
            "main_id": "org_1",
            "login_name": "employee",
            "name": "普通员工",
            "org_name": "示例科技",
            "space_type": "enterprise",
        },
        {"main_id": "org_1", "org_name": "个人空间"},
        None,
    )
    assert candidate["orgName"] == "示例科技"
    assert candidate["spaceType"] == "enterprise"


def test_admin_access_requires_active_non_member_admin_account() -> None:
    user = {"_id": "u1", "main_id": "org_1", "login_name": "employee"}
    organization = {"main_id": "org_1", "org_name": "示例科技"}
    assert project_tenant_candidate(user, organization, {"status": "active", "group_code": "member"})["canAccessAdmin"] is False
    assert project_tenant_candidate(user, organization, {"status": "disabled", "group_code": "admin"})["canAccessAdmin"] is False
    assert project_tenant_candidate(user, organization, {"status": "active", "group_code": "admin"})["canAccessAdmin"] is True


def test_explicit_personal_space_remains_personal() -> None:
    assert resolve_space_type({"space_type": "personal", "org_name": "个人空间"}) == "personal"


def test_personal_space_never_projects_admin_access() -> None:
    candidate = project_tenant_candidate(
        {"_id": "u1", "main_id": "personal_1", "login_name": "owner", "space_type": "personal"},
        {"main_id": "personal_1", "org_name": "个人空间"},
        {"status": "active", "group_code": "admin"},
    )
    assert candidate["spaceType"] == "personal"
    assert candidate["canAccessAdmin"] is False


def test_admin_org_name_is_tenant_fallback_without_granting_employee_admin_access() -> None:
    db = _Db([], [{
        "main_id": "org_1", "username": "owner", "org_name": "示例科技", "status": "active", "group_code": "admin",
    }])
    candidates = asyncio.run(load_tenant_candidates(db, [{
        "_id": "u1", "main_id": "org_1", "login_name": "employee", "org_name": "org_1",
    }]))
    assert candidates[0]["orgName"] == "示例科技"
    assert candidates[0]["canAccessAdmin"] is False
