"""Make a fresh deployment usable with no shell access.

Idempotent, safe to run on every build and every start:
  1. `alembic upgrade head` - create/upgrade the schema.
  2. If there are no events yet, load the committed demo dataset
     (data/demo_live) through the real detection pipeline.
  3. If SENTINEL_BOOTSTRAP_USERNAME / SENTINEL_BOOTSTRAP_PASSWORD are set and
     that account doesn't exist, create it. Credentials come only from the
     environment, never from code.

Usage: python -m api.bootstrap
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

import api.models  # noqa: F401  (register all tables)
from api.db.session import SessionLocal
from api.models.identity import Account
from api.models.ingest import Event
from api.security.passwords import hash_password

REPO_ROOT = Path(__file__).resolve().parent.parent


def _migrate() -> None:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def _load_demo_data_if_empty() -> None:
    with SessionLocal() as db:
        events = db.scalar(select(func.count()).select_from(Event)) or 0
    if events:
        print(f"bootstrap: {events:,} events already present, skipping data load")
        return
    print("bootstrap: empty database, loading data/demo_live ...")
    from api import load_pipeline

    load_pipeline.main(["--raw-dir", str(REPO_ROOT / "data" / "demo_live")])


def _ensure_account() -> None:
    username = os.environ.get("SENTINEL_BOOTSTRAP_USERNAME", "").strip()
    password = os.environ.get("SENTINEL_BOOTSTRAP_PASSWORD", "")
    if not username or not password:
        print("bootstrap: SENTINEL_BOOTSTRAP_USERNAME/PASSWORD not set, no account created")
        return
    with SessionLocal() as db:
        if db.scalar(select(Account).where(Account.username == username)) is not None:
            print(f"bootstrap: account '{username}' already exists")
            return
        db.add(Account(
            username=username,
            display_name=os.environ.get("SENTINEL_BOOTSTRAP_DISPLAY_NAME", username.title()),
            role=os.environ.get("SENTINEL_BOOTSTRAP_ROLE", "detection_engineer"),
            password_hash=hash_password(password),
        ))
        db.commit()
        print(f"bootstrap: created account '{username}'")


def main() -> int:
    _migrate()
    _load_demo_data_if_empty()
    _ensure_account()
    return 0


if __name__ == "__main__":
    sys.exit(main())
