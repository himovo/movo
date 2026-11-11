from io import BytesIO

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.api.routes import directory_import
from app.repositories.directory_repository import AUDIT_LOG_COLLECTION, DEPARTMENT_COLLECTION


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, length):
        return self.rows[:length]


class Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, query):
        return Cursor([row for row in self.rows if row.get("main_id") == query.get("main_id")])

    async def find_one(self, query):
        return next((row for row in self.rows if all(row.get(key) == value for key, value in query.items())), None)

    async def insert_one(self, row):
        self.rows.append(row)

    async def delete_many(self, query):
        self.rows = [row for row in self.rows if row.get("_id") not in query["_id"]["$in"]]


def upload_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("department_name", "parent_path"))
    sheet.append(("Child", "Headquarters/Parent"))
    sheet.append(("Parent", "Headquarters"))
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_preview_and_commit_preserve_hierarchy(monkeypatch):
    departments = Collection([{"_id": ObjectId(), "main_id": "tenant-a", "name": "Headquarters", "code": "root", "path_ids": [], "path_names": []}])
    audits = Collection()
    monkeypatch.setattr(directory_import, "get_db", lambda: {DEPARTMENT_COLLECTION: departments, AUDIT_LOG_COLLECTION: audits})
    app = FastAPI()
    app.include_router(directory_import.router, prefix="/api/directory")
    app.dependency_overrides[directory_import.get_current_admin_user] = lambda: {"main_id": "tenant-a", "username": "admin"}
    content = upload_bytes()
    with TestClient(app) as client:
        preview = client.post("/api/directory/departments/import-preview", files={"file": ("departments.xlsx", content)})
        assert preview.status_code == 200
        assert preview.json()["createCount"] == 2
        result = client.post("/api/directory/departments/import-commit", files={"file": ("departments.xlsx", content)}, data={"digest": preview.json()["digest"]})
        assert result.status_code == 200
        assert result.json()["created"] == 2
        parent = next(row for row in departments.rows if row["name"] == "Parent")
        child = next(row for row in departments.rows if row["name"] == "Child")
        assert child["parent_id"] == str(parent["_id"])
        assert child["path_ids"] == [str(departments.rows[0]["_id"]), str(parent["_id"])]
        assert child["path_names"] == ["Headquarters", "Parent"]
        assert len(audits.rows) == 1
