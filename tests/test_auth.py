"""B2 required tests: wrong password rejected; lockout actually triggers; an
analyst calling the suppression-activation endpoint gets 403; an expired
session is rejected; audit rows are written for each of those.
"""
from __future__ import annotations

import datetime as dt
import time

from sqlalchemy import select

from api.models.feedback import Suppression
from api.models.identity import Account, AuditLog, SessionToken
from api.security.passwords import hash_password

PASSWORD = "correct-horse-battery-staple-9"


def _make_account(db_session, *, username: str, role: str, password: str = PASSWORD) -> Account:
    account = Account(
        username=username,
        display_name=username,
        role=role,
        password_hash=hash_password(password),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


def test_wrong_password_rejected(client, db_session):
    _make_account(db_session, username="priya.s", role="analyst")

    r = client.post("/api/v1/auth/login", json={"username": "priya.s", "password": "not-the-password"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "st_session" not in r.cookies


def test_unknown_username_rejected(client, db_session):
    r = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "whatever-12345"})
    assert r.status_code == 401


def test_correct_password_accepted_and_sets_httponly_cookie(client, db_session):
    _make_account(db_session, username="priya.s", role="analyst")

    r = client.post("/api/v1/auth/login", json={"username": "priya.s", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["account"]["username"] == "priya.s"
    assert "st_session" in client.cookies

    set_cookie = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()


def test_lockout_actually_triggers(client, db_session):
    _make_account(db_session, username="anjali.k", role="detection_engineer")

    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"username": "anjali.k", "password": "wrong"})
        assert r.status_code == 401

    # 6th attempt, even with the CORRECT password, must be locked out.
    r = client.post("/api/v1/auth/login", json={"username": "anjali.k", "password": PASSWORD})
    assert r.status_code == 423

    account = db_session.scalar(select(Account).where(Account.username == "anjali.k"))
    assert account.failed_attempts == 5
    assert account.locked_until is not None

    # Lock expires quickly under test settings; login then succeeds and resets.
    time.sleep(2.5)
    r = client.post("/api/v1/auth/login", json={"username": "anjali.k", "password": PASSWORD})
    assert r.status_code == 200

    db_session.refresh(account)
    assert account.failed_attempts == 0
    assert account.locked_until is None


def test_analyst_forbidden_from_activating_suppression(client, db_session):
    analyst = _make_account(db_session, username="priya.s", role="analyst")
    suppression = Suppression(
        scope="rule", rule_id="stage.usb_after_dormancy", reason="test fixture", created_by="anjali.k"
    )
    db_session.add(suppression)
    db_session.commit()
    db_session.refresh(suppression)

    login = client.post("/api/v1/auth/login", json={"username": "priya.s", "password": PASSWORD})
    assert login.status_code == 200

    r = client.post(f"/api/v1/suppressions/{suppression.suppression_id}/activate")
    assert r.status_code == 403

    db_session.refresh(suppression)
    assert suppression.status == "proposed"


def test_detection_engineer_can_activate_suppression(client, db_session):
    _make_account(db_session, username="anjali.k", role="detection_engineer")
    suppression = Suppression(
        scope="rule", rule_id="stage.usb_after_dormancy", reason="test fixture", created_by="anjali.k"
    )
    db_session.add(suppression)
    db_session.commit()
    db_session.refresh(suppression)

    login = client.post("/api/v1/auth/login", json={"username": "anjali.k", "password": PASSWORD})
    assert login.status_code == 200

    r = client.post(f"/api/v1/suppressions/{suppression.suppression_id}/activate")
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    audit_row = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "suppression_activated").order_by(AuditLog.audit_id.desc())
    )
    assert audit_row is not None
    assert audit_row.actor == "anjali.k"


def test_expired_session_rejected(client, db_session):
    _make_account(db_session, username="priya.s", role="analyst")
    login = client.post("/api/v1/auth/login", json={"username": "priya.s", "password": PASSWORD})
    assert login.status_code == 200

    # Force the freshly issued session into the past.
    session_row = db_session.scalar(select(SessionToken).order_by(SessionToken.session_id.desc()))
    session_row.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    db_session.commit()

    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_audit_rows_written_for_login_success_failure_and_logout(client, db_session):
    _make_account(db_session, username="priya.s", role="analyst")

    client.post("/api/v1/auth/login", json={"username": "priya.s", "password": "wrong"})
    ok = client.post("/api/v1/auth/login", json={"username": "priya.s", "password": PASSWORD})
    assert ok.status_code == 200
    client.post("/api/v1/auth/logout")

    actions = {
        row.action
        for row in db_session.scalars(select(AuditLog).where(AuditLog.actor == "priya.s")).all()
    }
    assert {"login_failed", "login_success", "logout"} <= actions
