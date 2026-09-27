"""Tests for single-use incident verification tokens (api/verification.py).

Judge-requested: once an incident is flagged (AUTO_FLAG), anyone holding a
token issued for it can independently confirm the report is genuine and
unaltered - without a SentinelTrace login, and without being able to reuse
or forge a token. These tests exercise the real signing/verification path
end to end against a real (scratch) database, via the real FastAPI app.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import api.live_demo as live_demo


@pytest.fixture(autouse=True)
def _restore_demo_csvs():
    import shutil
    backup = live_demo.DEMO_RAW_DIR / "_original"
    files = ["logon.csv", "device.csv", "file.csv", "http.csv", "email.csv"]

    def restore():
        for name in files:
            src, dst = backup / name, live_demo.DEMO_RAW_DIR / name
            if src.exists():
                shutil.copyfile(src, dst)

    restore()
    yield
    restore()


@pytest.fixture
def flagged_incident(demo_client) -> str:
    """A real AUTO_FLAG incident, created via the real live-demo path -
    the same one every other verification test builds on."""
    r = demo_client.post("/api/v1/live-demo/inject", json={"scenario": True})
    assert r.status_code == 200, r.text
    incidents = r.json()["incidents_today"]
    flagged = [i for i in incidents if i["triage_lane"] == "AUTO_FLAG"]
    assert flagged, "expected the full scenario to produce an AUTO_FLAG incident"
    return flagged[0]["incident_id"]


@pytest.fixture
def demo_client(tmp_path, monkeypatch):
    from api.db.base import Base
    from api.db.session import SessionLocal, engine
    from api.main import app
    from api.models.identity import Account
    from api.security.passwords import hash_password

    Base.metadata.create_all(engine)
    db = SessionLocal()
    if not db.query(Account).filter(Account.username == "verify_test").first():
        db.add(Account(username="verify_test", display_name="Verify Test", role="detection_engineer",
                       password_hash=hash_password("VerifyTest!2026")))
        db.commit()
    db.close()

    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"username": "verify_test", "password": "VerifyTest!2026"})
    assert r.status_code == 200, r.text
    return client


# ==================================================================== issuance
def test_issuing_a_token_requires_login():
    from api.main import app
    anon = TestClient(app)
    r = anon.post("/api/v1/incidents/INC-DOES-NOT-EXIST/verification-token")
    assert r.status_code == 401


def test_cannot_issue_a_token_for_a_nonexistent_incident(demo_client):
    r = demo_client.post("/api/v1/incidents/INC-DOES-NOT-EXIST/verification-token")
    assert r.status_code == 404


def test_cannot_issue_a_token_for_an_incident_that_is_not_auto_flagged(demo_client):
    """Only a raised (AUTO_FLAG) incident is eligible - a MONITOR-lane
    incident was never 'raised' in the sense that prompted this feature."""
    r = demo_client.post("/api/v1/live-demo/inject", json={"actions": ["offhours_logon"]})
    assert r.status_code == 200, r.text
    non_flagged = [i for i in r.json()["incidents_today"] if i["triage_lane"] != "AUTO_FLAG"]
    if not non_flagged:
        pytest.skip("this run happened to auto-flag on a single weak signal - not the case under test")
    r2 = demo_client.post(f"/api/v1/incidents/{non_flagged[0]['incident_id']}/verification-token")
    assert r2.status_code == 403


def test_issuing_a_token_returns_a_real_jwt(demo_client, flagged_incident):
    r = demo_client.post(f"/api/v1/incidents/{flagged_incident}/verification-token")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["incident_id"] == flagged_incident
    token = body["token"]
    assert token.count(".") == 2  # header.payload.signature - a real JWT shape

    import base64
    header_b64 = token.split(".")[0]
    header_b64 += "=" * (-len(header_b64) % 4)
    header = json.loads(base64.urlsafe_b64decode(header_b64))
    assert header["alg"] == "HS256"


def test_each_issuance_call_produces_a_distinct_token(demo_client, flagged_incident):
    r1 = demo_client.post(f"/api/v1/incidents/{flagged_incident}/verification-token")
    r2 = demo_client.post(f"/api/v1/incidents/{flagged_incident}/verification-token")
    assert r1.json()["token"] != r2.json()["token"]


# ==================================================================== verification
def test_verify_does_not_require_login():
    """The whole point: HR, a judge, an auditor - anyone holding a token -
    can check it without a SentinelTrace account."""
    from api.main import app
    anon = TestClient(app)
    r = anon.post("/api/v1/verify-token", json={"token": "not-a-real-token"})
    assert r.status_code != 401  # rejected for being malformed, never for lacking a login


def test_a_fresh_token_verifies_successfully_with_the_real_incident_data(demo_client, flagged_incident):
    issued = demo_client.post(f"/api/v1/incidents/{flagged_incident}/verification-token").json()
    r = demo_client.post("/api/v1/verify-token", json={"token": issued["token"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["incident_id"] == flagged_incident
    assert body["triage_lane"] == "AUTO_FLAG"
    assert body["risk"] >= 70
    assert body["issued_by"] == "verify_test"


def test_a_used_token_cannot_verify_a_second_time(demo_client, flagged_incident):
    """The single-use requirement, verified directly: same token, second
    call, must be refused - not silently re-approved."""
    token = demo_client.post(f"/api/v1/incidents/{flagged_incident}/verification-token").json()["token"]

    first = demo_client.post("/api/v1/verify-token", json={"token": token})
    assert first.status_code == 200

    second = demo_client.post("/api/v1/verify-token", json={"token": token})
    assert second.status_code == 409
    assert "already used" in second.json()["detail"]


def test_a_tampered_token_is_rejected_as_a_fake_report(demo_client, flagged_incident):
    """The core 'identify the fake report' requirement: editing the signed
    payload (here, flipping characters in the signature) must fail the
    signature check, not silently pass with altered claims."""
    token = demo_client.post(f"/api/v1/incidents/{flagged_incident}/verification-token").json()["token"]
    tampered = token[:-6] + ("A" if token[-1] != "A" else "B") + token[-5:]

    r = demo_client.post("/api/v1/verify-token", json={"token": tampered})
    assert r.status_code == 401
    assert "forged" in r.json()["detail"] or "tampered" in r.json()["detail"] or "signature" in r.json()["detail"]


def test_forging_a_token_with_a_different_secret_is_rejected(demo_client, flagged_incident):
    """Not just bit-flipping - a fully self-consistent, well-formed JWT
    signed with the WRONG secret (as an attacker without server access
    would have to do) must still fail verification."""
    import jwt as pyjwt

    real_token = demo_client.post(f"/api/v1/incidents/{flagged_incident}/verification-token").json()["token"]
    claims = pyjwt.decode(real_token, options={"verify_signature": False})
    forged = pyjwt.encode(claims, "an-attackers-guessed-secret", algorithm="HS256")

    r = demo_client.post("/api/v1/verify-token", json={"token": forged})
    assert r.status_code == 401


def test_a_malformed_token_is_rejected_cleanly():
    from api.main import app
    anon = TestClient(app)
    r = anon.post("/api/v1/verify-token", json={"token": "definitely-not-a-jwt"})
    assert r.status_code == 400


def test_an_unknown_but_validly_signed_token_is_rejected(demo_client, flagged_incident):
    """A token signed with OUR real secret, for a jti we never actually
    issued (e.g. a fresh database, or a token from a different server
    instance) must not verify - the database row is what proves issuance,
    not the signature alone."""
    import jwt as pyjwt
    from api.settings import settings

    fabricated = pyjwt.encode(
        {"jti": "never-issued-by-this-server", "incident_id": flagged_incident,
         "risk": 99.0, "confidence": 0.99, "triage_lane": "AUTO_FLAG",
         "config_version": "sha256:fake", "iat": 1234567890, "iss": "sentineltrace"},
        settings.jwt_secret, algorithm="HS256",
    )
    r = demo_client.post("/api/v1/verify-token", json={"token": fabricated})
    assert r.status_code == 404
