"""Tests for the two-laptop live-injection demo (api/live_demo.py).

These exercise the real path end to end: append real rows to the real demo
CSVs, run the real engine.run.Pipeline, persist into a real (scratch) DB,
and read the result back through the real FastAPI app - the same path
tools/live_demo_inject.py drives from a second machine. Slow-ish (each
inject rescoring is a full pipeline run over the demo dataset, a few
seconds) but this is exactly the mechanism being tested, so there is no
faster equivalent that would still mean anything.

Every test restores data/demo_live/'s CSVs from _original/ in a fixture
teardown, so a failed run never leaves the shared demo dataset polluted for
whoever runs the app next.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.live_demo as live_demo


@pytest.fixture(autouse=True)
def _restore_demo_csvs():
    """Every test starts from, and ends on, the clean original baseline -
    live_demo.reset_demo_events() itself is one of the things under test, so
    this fixture cannot rely on calling it; it restores the files directly."""
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
def demo_client(tmp_path, monkeypatch):
    """A real FastAPI TestClient against a scratch SQLite DB, with a demo
    account pre-created and already logged in - api.db.session builds its
    engine from settings at import time, so SENTINEL_DB must be set before
    any api.* module is first imported anywhere in the test session (see
    tests/conftest.py's identical constraint)."""
    from api.db.base import Base
    from api.db.session import SessionLocal, engine
    from api.main import app
    from api.models.identity import Account
    from api.security.passwords import hash_password

    Base.metadata.create_all(engine)
    db = SessionLocal()
    if not db.query(Account).filter(Account.username == "demo_test").first():
        db.add(Account(username="demo_test", display_name="Demo Test", role="detection_engineer",
                       password_hash=hash_password("LiveDemoTest!2026")))
        db.commit()
    db.close()

    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"username": "demo_test", "password": "LiveDemoTest!2026"})
    assert r.status_code == 200, r.text
    return client


# ==================================================================== action catalogue
def test_all_full_scenario_actions_are_registered():
    for name, _offset in live_demo.FULL_SCENARIO:
        assert name in live_demo.ACTIONS


def test_unknown_action_raises():
    with pytest.raises(live_demo.UnknownDemoAction):
        live_demo.append_actions(["not_a_real_action"])


def test_append_actions_writes_real_rows_to_the_real_csvs():
    before = _count_rows(live_demo.DEMO_RAW_DIR / "logon.csv")
    live_demo.append_actions(["offhours_logon"])
    after = _count_rows(live_demo.DEMO_RAW_DIR / "logon.csv")
    assert after == before + 1


def test_file_copy_burst_writes_45_sensitive_files_on_removable_media():
    import csv
    live_demo.append_actions(["file_copy_burst"])
    with (live_demo.DEMO_RAW_DIR / "file.csv").open(encoding="utf-8") as f:
        # Filter by the macro's own filename pattern ("Q{NN}_..."), not just
        # user id - AA0000 already has ~45 days of unrelated benign file
        # activity in the baseline, which a plain user-id filter would also
        # match (the generator's own filenames are 8 hex chars with no "Q"
        # prefix, so this pattern is unique to injected rows).
        rows = [r for r in csv.DictReader(f)
               if r["user"] == live_demo.DEMO_USER_ID and r["filename"].startswith("Q")]
    assert len(rows) == 45
    assert all(r["to_removable_media"] == "True" for r in rows)


def test_leak_upload_writes_three_visits_not_one():
    """docs the exact bug this module's own comments flag: a single leak-
    platform visit clears the rule's >=1 threshold but contributes zero
    strength at the log scale's floor - the macro must send more than one."""
    import csv
    live_demo.append_actions(["leak_upload"])
    with (live_demo.DEMO_RAW_DIR / "http.csv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if "pastebin.com" in r["url"]]
    assert len(rows) == 3


def test_next_anchor_is_after_the_generated_baseline():
    anchor = live_demo._next_anchor()
    assert anchor > live_demo.DEMO_BASE_ANCHOR - __import__("datetime").timedelta(days=1)
    assert anchor.year == 2010  # never drifts to the real wall-clock year


def test_next_anchor_advances_past_prior_injections():
    first = live_demo._next_anchor()
    live_demo.append_actions(["offhours_logon"], start_at=first)
    second = live_demo._next_anchor()
    assert second > first


def _count_rows(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8")) - 1  # minus header


# ==================================================================== end to end via the real API
def test_inject_full_scenario_produces_a_real_auto_flag_incident(demo_client):
    """The actual demo payoff, verified for real: after the full staged
    sequence, the demo employee has a genuine AUTO_FLAG incident spanning
    the collection and exfiltration stages, with a real narrative."""
    r = demo_client.post("/api/v1/live-demo/inject", json={"scenario": True})
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["user_id"] == live_demo.DEMO_USER_ID
    assert len(data["incidents_today"]) == 1
    inc = data["incidents_today"][0]
    assert inc["triage_lane"] == "AUTO_FLAG"
    assert inc["risk"] >= 70
    assert "exfil" in inc["categories"]

    # And it is genuinely readable back through the normal incident-detail
    # path a dashboard would use - not just returned inline by /inject.
    detail = demo_client.get(f"/api/v1/incidents/{inc['incident_id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["narrative"]["headline"]
    assert body["narrative"]["summary"]
    assert len(body["signals"]) == inc["signal_count"]


def test_inject_is_idempotent_across_repeated_calls(demo_client):
    """The second injection in the same demo session must not crash on a
    primary-key conflict re-persisting the demo user's own history - this
    is exactly the bug _wipe_demo_rows exists to prevent."""
    r1 = demo_client.post("/api/v1/live-demo/inject", json={"actions": ["offhours_logon"]})
    assert r1.status_code == 200, r1.text
    r2 = demo_client.post("/api/v1/live-demo/inject", json={"actions": ["offhours_logon"]})
    assert r2.status_code == 200, r2.text


def test_unknown_action_returns_400(demo_client):
    r = demo_client.post("/api/v1/live-demo/inject", json={"actions": ["not_a_real_action"]})
    assert r.status_code == 400


def test_empty_request_returns_400(demo_client):
    r = demo_client.post("/api/v1/live-demo/inject", json={})
    assert r.status_code == 400


def test_inject_requires_authentication():
    from api.main import app
    anon = TestClient(app)
    r = anon.post("/api/v1/live-demo/inject", json={"scenario": True})
    assert r.status_code == 401


def test_reset_clears_injected_incidents(demo_client):
    r = demo_client.post("/api/v1/live-demo/inject", json={"scenario": True})
    assert r.status_code == 200
    incident_id = r.json()["incidents_today"][0]["incident_id"]
    assert demo_client.get(f"/api/v1/incidents/{incident_id}").status_code == 200

    r = demo_client.post("/api/v1/live-demo/reset")
    assert r.status_code == 204

    # The CSVs are back to the clean baseline, so re-running produces no
    # incident for "today" at all - the reset genuinely undid the injection,
    # not merely relabelled it.
    r2 = demo_client.post("/api/v1/live-demo/inject", json={"actions": ["offhours_logon"]})
    assert r2.status_code == 200
    assert incident_id not in [i["incident_id"] for i in r2.json()["incidents_today"]]


def test_list_actions_endpoint(demo_client):
    r = demo_client.get("/api/v1/live-demo/actions")
    assert r.status_code == 200
    assert set(r.json()["actions"]) == set(live_demo.ACTIONS)
