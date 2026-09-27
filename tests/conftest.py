"""Test-wide fixtures for the api/ test suite.

Sets SENTINEL_DB to a scratch SQLite file *before* any api.* module is
imported, since api/db/session.py builds its engine from settings at import
time. MITIGATION_PAYLOAD_DIR gets the same treatment: api/mitigation.py
writes a real .json file per triggered incident, and without this it would
write real-looking incident files straight into the shared demo folder
(data/mitigation_payloads/) on every test run - a real bug this project hit
once already.
"""
from __future__ import annotations

import os
import pathlib
import shutil

_TEST_DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "_test.db"
if _TEST_DB_PATH.exists():
    _TEST_DB_PATH.unlink()

_TEST_PAYLOAD_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "_test_mitigation_payloads"
shutil.rmtree(_TEST_PAYLOAD_DIR, ignore_errors=True)

os.environ["SENTINEL_DB"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["MITIGATION_PAYLOAD_DIR"] = str(_TEST_PAYLOAD_DIR)
# Fast, deterministic lockout timings so tests don't sleep for real.
os.environ.setdefault("SENTINEL_LOCKOUT_BASE_SECONDS", "2.0")
os.environ.setdefault("SENTINEL_LOCKOUT_MAX_SECONDS", "3.0")
os.environ.setdefault("SENTINEL_SESSION_TTL_MIN", "480")
os.environ.setdefault("SENTINEL_SESSION_IDLE_TTL_MIN", "30")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.models  # noqa: E402,F401
from api.db.base import Base  # noqa: E402
from api.db.session import SessionLocal, engine  # noqa: E402
from api.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    if _TEST_DB_PATH.exists():
        try:
            _TEST_DB_PATH.unlink()
        except PermissionError:
            pass  # Windows keeps a brief handle on the sqlite file; harmless
    shutil.rmtree(_TEST_PAYLOAD_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _wipe_tables():
    yield
    with SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def seeded_db(db_session):
    from api.seed import seed as run_seed

    run_seed(db_session)
    return db_session
