"""Firebase Authentication for the FastAPI services.

The browser signs in with Firebase and sends its ID token as ``Authorization: Bearer <token>``. The token is
verified here against Google's public keys for the project (RS256, audience = project id, issuer =
securetoken.google.com/<project id>), so no service-account credentials are needed.

Config:
  FIREBASE_PROJECT_ID    required unless DOPPEL_AUTH_DISABLED=1
  DOPPEL_ADMIN_EMAILS    comma-separated emails allowed to use break-it-live (verified emails only)
  DOPPEL_AUTH_DISABLED=1 local tests and the CLI only; never in a shared deployment
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request

JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
_jwks: jwt.PyJWKClient | None = None


@dataclass(frozen=True)
class User:
    uid: str
    email: str
    email_verified: bool
    is_admin: bool


def auth_disabled() -> bool:
    return os.environ.get("DOPPEL_AUTH_DISABLED") == "1"


def project_id() -> str:
    return os.environ.get("FIREBASE_PROJECT_ID", "")


def admin_emails() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("DOPPEL_ADMIN_EMAILS", "").split(",") if e.strip()}


def check_config() -> None:
    """Call at startup: refuse to run unprotected by accident."""
    if not auth_disabled() and not project_id():
        raise RuntimeError("Set FIREBASE_PROJECT_ID (or DOPPEL_AUTH_DISABLED=1 for local tests).")


def _signing_key(token: str) -> Any:
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks.get_signing_key_from_jwt(token).key


def verify_token(token: str, key: Any | None = None) -> dict[str, Any]:
    pid = project_id()
    try:
        claims = jwt.decode(
            token,
            key if key is not None else _signing_key(token),
            algorithms=["RS256"],
            audience=pid,
            issuer=f"https://securetoken.google.com/{pid}",
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            leeway=10,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, f"invalid sign-in token: {exc}") from exc
    if not claims.get("sub") or claims.get("auth_time", 0) > time.time() + 10:
        raise HTTPException(401, "invalid sign-in token")
    return claims


def user_from_claims(claims: dict[str, Any]) -> User:
    email = (claims.get("email") or "").lower()
    verified = bool(claims.get("email_verified"))
    return User(uid=claims["sub"], email=email, email_verified=verified,
                is_admin=verified and email in admin_emails())


LOCAL_USER = User(uid="local", email="local@localhost", email_verified=True, is_admin=True)


def bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def require_user(request: Request) -> User:
    if auth_disabled():
        return LOCAL_USER
    token = bearer(request)
    if not token:
        raise HTTPException(401, "sign in required")
    return user_from_claims(verify_token(token))


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "break-it-live is limited to demo operators (DOPPEL_ADMIN_EMAILS)")
    return user


def allowed_origins() -> list[str]:
    raw = os.environ.get("DOPPEL_ALLOWED_ORIGINS", "http://localhost:5180")
    return [o.strip() for o in raw.split(",") if o.strip()]
