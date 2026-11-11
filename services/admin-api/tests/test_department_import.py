from io import BytesIO
from unittest import TestCase

from openpyxl import Workbook

from app.services.department_import import parse_workbook, plan_import, template_bytes


def workbook(rows):
    book = Workbook()
    sheet = book.active
    sheet.append(("department_name", "parent_path"))
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


ROOT = {"_id": "root-id", "name": "Headquarters", "code": "root", "path_names": []}


class DepartmentImportTests(TestCase):
    def test_template_and_out_of_order_hierarchy(self):
        self.assertEqual(len(parse_workbook(template_bytes("Headquarters"))), 2)
        self.assertEqual(len(parse_workbook(template_bytes("Headquarters", "zh-CN"))), 2)
        rows = parse_workbook(workbook([
            ("UX", "Headquarters/Product/Design"),
            ("Design", "Headquarters/Product"),
            ("Product", "Headquarters"),
        ]))
        plan = plan_import(rows, [ROOT], "Headquarters")
        self.assertEqual(plan["errors"], [])
        self.assertEqual([item["path"] for item in plan["items"]], [
            "Headquarters/Product", "Headquarters/Product/Design", "Headquarters/Product/Design/UX",
        ])

    def test_duplicate_and_missing_parent(self):
        rows = parse_workbook(workbook([
            ("Product", "Headquarters"),
            ("Product", "Headquarters"),
            ("Other", "Headquarters/Missing"),
        ]))
        plan = plan_import(rows, [ROOT], "Headquarters")
        self.assertEqual([error["code"] for error in plan["errors"]], ["duplicate_row", "parent_not_found"])

    def test_same_name_in_different_parents(self):
        rows = parse_workbook(workbook([
            ("Team", "Headquarters/One"),
            ("Team", "Headquarters/Two"),
        ]))
        existing = [ROOT,
            {"_id": "one", "name": "One", "path_names": ["Headquarters"]},
            {"_id": "two", "name": "Two", "path_names": ["Headquarters"]},
        ]
        plan = plan_import(rows, existing, "Headquarters")
        self.assertEqual(plan["createCount"], 2)
        self.assertEqual(plan["errors"], [])
