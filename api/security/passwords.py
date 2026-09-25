"""Argon2id password hashing. Never plaintext, never a reversible encoding."""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Argon2id is the argon2-cffi default `type`. Parameters follow OWASP's
# current minimum recommendation for Argon2id (m=19 MiB, t=2, p=1) raised to
# a slightly stronger memory cost since this runs server-side, not on a
# resource-constrained client.
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    """Constant-time verification. Returns False on any mismatch or malformed hash."""
    try:
        _hasher.verify(stored_hash, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)
