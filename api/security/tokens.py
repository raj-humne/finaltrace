"""Session token generation and constant-time comparison helpers."""
from __future__ import annotations

import hashlib
import hmac
import secrets

SESSION_TOKEN_BYTES = 32  # 256 bits


def generate_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """The raw token is never persisted — only this hash, so a DB read alone
    cannot be replayed as a session cookie."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
