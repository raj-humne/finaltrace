"""Login, session issuance/validation, and logout.

Design notes (B2):
  - Argon2id hashing (api.security.passwords) — never plaintext, never
    reversible.
  - A wrong password and an unknown username both run a real Argon2id verify
    against *some* hash (a fixed dummy for unknown users) so the two cases
    take comparable time and a login endpoint can't be used to enumerate
    valid usernames by timing.
  - Lockout: 5 failed attempts (api.security.lockout) trigger exponential
    backoff, tracked on the account row itself so it survives restarts.
  - Sessions are opaque 256-bit tokens; only a SHA-256 hash is stored
    server-side (api.security.tokens), with sliding expiry.
  - Every login, logout, failure and privileged action is appended to
    audit_log (api.security.audit) — never updated, never deleted.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.time import as_utc
from api.models.identity import Account, SessionToken
from api.security.audit import write_audit
from api.security.exceptions import AccountInactive, AccountLocked, InvalidCredentials, SessionInvalid
from api.security.lockout import is_locked, locked_until_after_failure
from api.security.passwords import hash_password, verify_password
from api.security.tokens import generate_session_token, hash_token
from api.settings import settings

# A real Argon2id hash of a fixed, never-used password. Verifying against
# this for unknown usernames keeps failed-login timing indistinguishable
# from a known-username/wrong-password failure.
_DUMMY_HASH = hash_password("st-dummy-hash-for-timing-parity-only-never-a-real-account-password")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def authenticate(db: Session, *, username: str, password: str) -> Account:
    now = _now()
    account = db.scalar(select(Account).where(Account.username == username))

    if account is None:
        verify_password(_DUMMY_HASH, password)  # constant-time-ish parity; discard result
        write_audit(db, actor=username, action="login_failed", object_type="account", object_id=username)
        db.commit()
        raise InvalidCredentials("unknown username or wrong password")

    locked_until = as_utc(account.locked_until)
    if is_locked(locked_until, now):
        retry_after = (locked_until - now).total_seconds()
        write_audit(
            db, actor=account.username, action="login_blocked_locked",
            object_type="account", object_id=str(account.account_id),
        )
        db.commit()
        raise AccountLocked(retry_after)

    if not account.is_active:
        write_audit(
            db, actor=account.username, action="login_blocked_inactive",
            object_type="account", object_id=str(account.account_id),
        )
        db.commit()
        raise AccountInactive("account disabled")

    if not verify_password(account.password_hash, password):
        account.failed_attempts += 1
        account.locked_until = locked_until_after_failure(account.failed_attempts, now)
        write_audit(
            db, actor=account.username, action="login_failed",
            object_type="account", object_id=str(account.account_id),
            after={"failed_attempts": account.failed_attempts, "locked_until": _iso(account.locked_until)},
        )
        db.commit()
        raise InvalidCredentials("unknown username or wrong password")

    account.failed_attempts = 0
    account.locked_until = None
    write_audit(
        db, actor=account.username, action="login_success",
        object_type="account", object_id=str(account.account_id),
    )
    db.commit()
    db.refresh(account)
    return account


def create_session(db: Session, account: Account) -> str:
    now = _now()
    raw_token = generate_session_token()
    row = SessionToken(
        account_id=account.account_id,
        token_hash=hash_token(raw_token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + dt.timedelta(minutes=settings.session_ttl_minutes),
    )
    db.add(row)
    db.commit()
    return raw_token


def resolve_session(db: Session, raw_token: str) -> Account:
    """Validate a session cookie and slide its idle expiry forward. Raises
    SessionInvalid for a missing, expired, or revoked session."""
    now = _now()
    token_hash = hash_token(raw_token)
    row = db.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash))
    if row is None or row.revoked_at is not None:
        raise SessionInvalid("no such session")
    if as_utc(row.expires_at) <= now:
        raise SessionInvalid("session expired")

    idle_cutoff = as_utc(row.last_seen_at) + dt.timedelta(minutes=settings.session_idle_ttl_minutes)
    if idle_cutoff <= now:
        row.revoked_at = now
        db.commit()
        raise SessionInvalid("session idle timeout")

    account = db.get(Account, row.account_id)
    if account is None or not account.is_active:
        raise SessionInvalid("account no longer active")

    # This runs on EVERY authenticated request - every page load, every
    # background /auth/me poll, every read-only GET - not just real user
    # actions. Writing (and committing) on every single one of those made
    # the session table one of the busiest writers in the whole app,
    # competing for SQLite's single write lock against genuinely long
    # operations like a live-demo injection - a plain page load could 500
    # with "database is locked" for no reason related to what it was doing.
    # The idle timeout only needs minute-level granularity (default 30 min),
    # so skipping the write when the row was already touched recently costs
    # nothing observable while cutting write volume by roughly two orders
    # of magnitude under normal polling.
    if as_utc(row.last_seen_at) + dt.timedelta(seconds=60) <= now:
        row.last_seen_at = now
        db.commit()
    return account


def revoke_session(db: Session, raw_token: str, *, actor: str) -> None:
    token_hash = hash_token(raw_token)
    row = db.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash))
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        write_audit(db, actor=actor, action="logout", object_type="session", object_id=str(row.session_id))
        db.commit()


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None
