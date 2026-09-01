from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from app.services.setup_quota import configure_setup_quotas


class SetupQuotaValidationTests(IsolatedAsyncioTestCase):
    async def test_rejects_default_employee_quota_above_org_total(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能超过企业总 Token"):
            await configure_setup_quotas(
                main_id="test-main-id",
                total_tokens=100,
                default_user_tokens=101,
                period="monthly",
                timezone_name="Asia/Shanghai",
                operator="admin",
            )

    async def test_rejects_non_positive_quota_before_database_access(self) -> None:
        with self.assertRaisesRegex(ValueError, "必须大于 0"):
            await configure_setup_quotas(
                main_id="test-main-id",
                total_tokens=0,
                default_user_tokens=1,
                period="monthly",
                timezone_name="Asia/Shanghai",
                operator="admin",
            )
