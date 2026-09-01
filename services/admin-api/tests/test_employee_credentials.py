import pytest

from app.services.employee_credentials import normalize_employee_credentials, redact_credential_payload


def test_local_employee_requires_login_and_initial_password() -> None:
    with pytest.raises(ValueError, match="登录名"):
        normalize_employee_credentials(source="local", login_name="", password="secret1", creating=True)
    with pytest.raises(ValueError, match="至少 10 位"):
        normalize_employee_credentials(source="local", login_name="user01", password="", creating=True)


def test_existing_local_employee_can_keep_password() -> None:
    assert normalize_employee_credentials(
        source="local",
        login_name=" user01 ",
        password="",
        creating=False,
        has_existing_password=True,
    ) == ("user01", "")


def test_local_password_length_is_enforced() -> None:
    with pytest.raises(ValueError, match="密码至少 10 位"):
        normalize_employee_credentials(source="local", login_name="user01", password="12345", creating=False, has_existing_password=True)


def test_external_identity_removes_local_login_and_rejects_password() -> None:
    assert normalize_employee_credentials(source="wecom", login_name="legacy", password="", creating=False) == ("", "")
    with pytest.raises(ValueError, match="外部身份"):
        normalize_employee_credentials(source="wecom", login_name="legacy", password="secret1", creating=False)


def test_passwords_are_redacted_from_audit_payload() -> None:
    assert redact_credential_payload({"loginName": "user01", "initialPassword": "secret1"}) == {
        "loginName": "user01",
        "initialPassword": "***",
    }
