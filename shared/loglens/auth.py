"""Shared-secret JWT authentication and RBAC.

Suitable for local development and portfolio deployment: a single shared
HMAC secret (JWT_SECRET) signs and verifies tokens (HS256). Tokens carry a
``role`` claim (viewer | analyst | admin). Verification is provided as a
FastAPI dependency so it can be applied per-route without duplicating logic.

No external IdP is used. This is intentionally simple and self-contained.
"""

import os
import time
from typing import List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_ALGO = "HS256"
_bearer = HTTPBearer(auto_error=False)


class AuthError(Exception):
    pass


def create_token(secret: str, subject: str, role: str, expires_sec: int = 86400) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + expires_sec,
    }
    return jwt.encode(payload, secret, algorithm=_ALGO)


def decode_token(secret: str, token: str) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=[_ALGO])
    except jwt.PyJWTError as e:
        raise AuthError(f"Invalid token: {e}")


# Role hierarchy: higher roles include lower privileges.
_ROLE_RANK = {"viewer": 1, "analyst": 2, "admin": 3}


def require_role(required: List[str], secret: str):
    """FastAPI dependency factory enforcing JWT + RBAC.

    Args:
        required: list of acceptable roles (any match grants access).
        secret: shared JWT secret.
    """
    required_ranks = [_ROLE_RANK.get(r, 0) for r in required]

    def dependency(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)):
        return check_authorization(creds, required_ranks, secret)

    return dependency


def check_authorization(
    creds: Optional[HTTPAuthorizationCredentials],
    required_ranks: List[int],
    secret: str,
) -> dict:
    """Core authorization check, separable from the FastAPI dependency."""
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(secret, creds.credentials)
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role = payload.get("role", "viewer")
    rank = _ROLE_RANK.get(role, 0)
    if not any(rank >= r for r in required_ranks):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' cannot access this resource",
        )
    return payload


def get_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        # Fail-fast: auth cannot operate without a secret.
        raise RuntimeError("JWT_SECRET environment variable is required for auth")
    return secret
