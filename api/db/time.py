"""SQLite does not persist tzinfo on DateTime(timezone=True) columns — a value
written as UTC-aware comes back naive. Every column in this schema is UTC by
convention, so this normalizes a value read back from the DB to UTC-aware
before it is compared against a fresh `datetime.now(timezone.utc)`. Postgres
round-trips tzinfo correctly already; this is a no-op there.
"""
from __future__ import annotations

import datetime as dt


def as_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value
