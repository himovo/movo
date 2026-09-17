from __future__ import annotations

import datetime
import string

import pytest

from app.services.session_sharing.service import (
    SessionShareError,
    build_link,
    create_token,
    hash_token,
    is_active,
    issue_share,
    revoke_share,
)


NOW = datetime.datetime(2026, 9, 17, 12, 0, tzinfo=datetime.timezone.utc)
SESSION = {"_id": "sess-1", "main_id": "tenant-1", "user_id": "owner-1"}
URLSAFE_ALPHABET = set(string.ascii_letters + string.digits + "-_")


def _issued_doc(session: dict, issued: dict) -> dict:
    return {**session, **issued["fields"]}


def test_create_token_returns_urlsafe_32_byte_token():
    token = create_token()
    assert isinstance(token, str)
    assert len(token) == 43
    assert set(token) <= URLSAFE_ALPHABET
    assert token != create_token()


def test_issue_share_returns_token_and_persistable_fields():
    issued = issue_share(SESSION, now=NOW)

    assert set(issued["fields"]) == {"share_token_hash", "share_expires_at", "share_revoked_at"}
    assert issued["fields"]["share_token_hash"] == hash_token(issued["token"])
    assert issued["fields"]["share_expires_at"] == NOW + datetime.timedelta(days=30)
    assert issued["fields"]["share_revoked_at"] is None
    assert "token" not in issued["fields"]
    assert issued["fields"]["share_token_hash"] != issued["token"]


def test_issued_share_is_active_when_fields_persisted():
    issued = issue_share(SESSION, now=NOW)

    assert is_active(_issued_doc(SESSION, issued), issued["token"], NOW)


def test_regenerated_share_deactivates_previous_token():
    first = issue_share(SESSION, now=NOW)
    shared_doc = _issued_doc(SESSION, first)
    second = issue_share(shared_doc, now=NOW)
    rotated_doc = _issued_doc(shared_doc, second)

    assert is_active(rotated_doc, second["token"], NOW)
    assert not is_active(rotated_doc, first["token"], NOW)


def test_regenerate_clears_revocation():
    issued = issue_share(SESSION, now=NOW)
    revoked_doc = {**_issued_doc(SESSION, issued), **revoke_share(now=NOW)}

    regenerated = issue_share(revoked_doc, now=NOW)

    assert regenerated["fields"]["share_revoked_at"] is None
    assert is_active(_issued_doc(revoked_doc, regenerated), regenerated["token"], NOW)


def test_revoke_share_returns_revocation_fields():
    assert revoke_share(now=NOW) == {"share_token_hash": None, "share_revoked_at": NOW}


def test_is_active_when_share_revoked():
    issued = issue_share(SESSION, now=NOW)
    revoked_doc = {**_issued_doc(SESSION, issued), **revoke_share(now=NOW)}

    assert not is_active(revoked_doc, issued["token"], NOW)


def test_is_active_when_token_expired():
    issued = issue_share(SESSION, now=NOW - datetime.timedelta(days=31))
    expired_doc = _issued_doc(SESSION, issued)

    assert not is_active(expired_doc, issued["token"], NOW)


def test_is_active_when_expiry_equals_now():
    issued = issue_share(SESSION, now=NOW - datetime.timedelta(days=30))
    doc = _issued_doc(SESSION, issued)

    assert doc["share_expires_at"] == NOW
    assert not is_active(doc, issued["token"], NOW)


def test_is_active_when_token_hash_mismatch():
    issued = issue_share(SESSION, now=NOW)
    other_doc = {**_issued_doc(SESSION, issued), "share_token_hash": hash_token("some-other-token")}

    assert not is_active(other_doc, issued["token"], NOW)


def test_is_active_when_session_never_shared():
    never_shared = {
        **SESSION,
        "share_token_hash": None,
        "share_expires_at": None,
        "share_revoked_at": None,
    }

    assert not is_active(never_shared, create_token(), NOW)


def test_is_active_with_naive_expires_at_treated_as_utc():
    issued = issue_share(SESSION, now=NOW)
    naive_doc = _issued_doc(SESSION, issued)
    naive_doc["share_expires_at"] = issued["fields"]["share_expires_at"].replace(tzinfo=None)

    assert is_active(naive_doc, issued["token"], NOW)


def test_build_link_format():
    assert build_link("https://chat.example.com", "tok-123") == "https://chat.example.com/?session-share=tok-123"


def test_hash_token_matches_sha256_known_vector():
    assert hash_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.parametrize("token", ["", "   "])
def test_hash_token_rejects_blank_tokens(token):
    with pytest.raises(SessionShareError) as excinfo:
        hash_token(token)

    assert excinfo.value.code == "session_share_token_required"
