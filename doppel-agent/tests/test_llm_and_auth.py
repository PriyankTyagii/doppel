"""Grok request schema and Firebase ID-token verification (no network)."""

import sys
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _paths  # noqa: E402,F401
import firebase_auth as fa  # noqa: E402
from adhoc import Plan  # noqa: E402
from explain import Explanation  # noqa: E402
from llm import strict_schema  # noqa: E402

PROJECT = "doppel-test"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(**over):
    now = int(time.time())
    claims = {"iss": f"https://securetoken.google.com/{PROJECT}", "aud": PROJECT, "sub": "uid-1",
              "iat": now, "exp": now + 3600, "auth_time": now, "email": "Ops@Example.com", "email_verified": True}
    claims.update(over)
    return jwt.encode(claims, KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", PROJECT)
    monkeypatch.setenv("DOPPEL_ADMIN_EMAILS", "ops@example.com, lead@example.com")
    monkeypatch.delenv("DOPPEL_AUTH_DISABLED", raising=False)


def verify(t):
    return fa.verify_token(t, key=KEY.public_key())


def test_valid_token_gives_a_user_and_admin_by_verified_email():
    user = fa.user_from_claims(verify(token()))
    assert (user.uid, user.email, user.is_admin) == ("uid-1", "ops@example.com", True)


def test_unverified_email_is_never_admin():
    assert not fa.user_from_claims(verify(token(email_verified=False))).is_admin


def test_non_admin_email():
    assert not fa.user_from_claims(verify(token(email="someone@else.com"))).is_admin


@pytest.mark.parametrize("bad", [
    {"aud": "other-project"},
    {"iss": "https://securetoken.google.com/other-project"},
    {"exp": int(time.time()) - 60},
    {"sub": ""},
    {"auth_time": int(time.time()) + 3600},
])
def test_rejects_bad_tokens(bad):
    with pytest.raises(HTTPException) as e:
        verify(token(**bad))
    assert e.value.status_code == 401


def test_rejects_token_signed_by_another_key():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(jwt.decode(token(), options={"verify_signature": False}), other, algorithm="RS256")
    with pytest.raises(HTTPException):
        verify(forged)


def test_startup_refuses_to_run_without_a_project(monkeypatch):
    monkeypatch.delenv("FIREBASE_PROJECT_ID")
    with pytest.raises(RuntimeError):
        fa.check_config()
    monkeypatch.setenv("DOPPEL_AUTH_DISABLED", "1")
    fa.check_config()


def _no_refs(node):
    if isinstance(node, dict):
        assert "$ref" not in node
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
        for v in node.values():
            _no_refs(v)
    elif isinstance(node, list):
        for v in node:
            _no_refs(v)


@pytest.mark.parametrize("model", [Explanation, Plan])
def test_strict_schema_is_self_contained_and_closed(model):
    schema = strict_schema(model)
    assert "$defs" not in schema
    _no_refs(schema)
