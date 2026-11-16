from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

import pytest
from pydantic import ValidationError

from app.api.routes.setup import SetupInitRequest
from app.services.setup_quota import configure_setup_quotas


@pytest.fixture
def setup_payload():
    return {
        "orgName": "Test Organization",
        "adminUsername": "admin",
        "adminPassword": "test-password-only",
        "employeeUsername": "employee",
        "employeePassword": "test-password-only",
        "employeeName": "Test User",
        "orgTotalTokens": 1000,
        "defaultUserTokens": 100,
        "model": {
            "providerId": "test",
            "displayName": "Test Model",
            "modelName": "test-model",
            "baseUrl": "https://example.com/v1",
            "apiKey": "test-secret",
        },
    }


def test_setup_accepts_largest_safe_integer_quotas(setup_payload):
    limit = 2**53 - 1
    request = SetupInitRequest(**{
        **setup_payload, "orgTotalTokens": limit, "defaultUserTokens": limit,
    })

    assert request.orgTotalTokens == request.defaultUserTokens == limit


@pytest.mark.parametrize("field", ["orgTotalTokens", "defaultUserTokens"])
def test_setup_rejects_quota_above_largest_safe_integer(setup_payload, field):
    with pytest.raises(ValidationError) as error:
        SetupInitRequest(**{**setup_payload, field: 2**53})

    assert [(item["loc"], item["type"]) for item in error.value.errors()] == [
        ((field,), "less_than_equal"),
    ]


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
