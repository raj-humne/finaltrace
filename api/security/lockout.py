"""Account lockout policy: 5 failed attempts trigger exponential backoff.

Pure functions over plain values so the policy is testable without a database.
"""
from __future__ import annotations

import datetime as dt

from api.settings import settings


def backoff_seconds(failed_attempts: int) -> float:
    """Seconds to lock the account for, given the failed-attempt count *after*
    this failure. Zero below the lockout threshold — the account only starts
    locking once it has actually failed `lockout_threshold` times."""
    if failed_attempts < settings.lockout_threshold:
        return 0.0
    exponent = failed_attempts - settings.lockout_threshold
    return min(settings.lockout_base_seconds * (2**exponent), settings.lockout_max_seconds)


def locked_until_after_failure(failed_attempts: int, now: dt.datetime) -> dt.datetime | None:
    seconds = backoff_seconds(failed_attempts)
    if seconds <= 0:
        return None
    return now + dt.timedelta(seconds=seconds)


def is_locked(locked_until: dt.datetime | None, now: dt.datetime) -> bool:
    return locked_until is not None and locked_until > now
