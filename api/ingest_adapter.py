"""A minimal, working per-source CERT record -> canonical Event mapper.

This is intentionally independent of engine/ingest/loader.py (Track A's
vectorised, chunked, 32M-row adapter) per the Track B brief: don't depend on
engine/ internals that may still be moving, define the interface needed and
work against it directly. Column layouts are taken from
docs/03-DATA-MODEL.md section 1, and the event_id scheme mirrors
docs/02-ARCHITECTURE.md's `blake2b(source + raw_id + user + ts)[:16]` so ids
are stable if this is later swapped for the canonical loader.
"""
from __future__ import annotations

import hashlib
import datetime as dt
from dataclasses import dataclass
from typing import Any

CERT_TS_FORMAT = "%m/%d/%Y %H:%M:%S"
VALID_SOURCES = ("logon", "device", "file", "http", "email")
_LOGON_ACTIVITIES = {"Logon", "Logoff"}
_DEVICE_ACTIVITIES = {"Connect", "Disconnect"}


@dataclass
class ParsedEvent:
    event_id: str
    user_id: str
    pc_id: str | None
    ts: dt.datetime
    source: str
    action: str
    attrs: dict[str, Any]


class RejectedRecord(Exception):
    def __init__(self, reason: str, raw: Any) -> None:
        self.reason = reason
        self.raw = raw
        super().__init__(reason)


def _parse_ts(raw: str) -> dt.datetime:
    try:
        naive = dt.datetime.strptime(raw, CERT_TS_FORMAT)
    except (ValueError, TypeError) as exc:
        raise RejectedRecord("unparseable_date", raw) from exc
    return naive.replace(tzinfo=dt.timezone.utc)


def _event_id(source: str, raw_id: str, user: str, ts: dt.datetime) -> str:
    payload = f"{source}{raw_id}{user}{ts.isoformat()}"
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


def parse_record(source: str, rec: dict[str, Any]) -> ParsedEvent:
    if source not in VALID_SOURCES:
        raise RejectedRecord("unknown_source", source)

    raw_id = rec.get("id")
    user = rec.get("user")
    date_raw = rec.get("date")
    if not raw_id or not user or not date_raw:
        raise RejectedRecord("missing_required_field", rec)

    ts = _parse_ts(date_raw)
    pc = rec.get("pc")

    if source == "logon":
        activity = rec.get("activity")
        if activity not in _LOGON_ACTIVITIES:
            raise RejectedRecord("invalid_activity", rec)
        attrs: dict[str, Any] = {}
        action = activity
    elif source == "device":
        activity = rec.get("activity")
        if activity not in _DEVICE_ACTIVITIES:
            raise RejectedRecord("invalid_activity", rec)
        attrs = {}
        action = activity
    elif source == "file":
        filename = rec.get("filename")
        if not filename:
            raise RejectedRecord("missing_required_field", rec)
        attrs = {"filename": filename}
        action = "File"
    elif source == "http":
        url = rec.get("url")
        if not url:
            raise RejectedRecord("missing_required_field", rec)
        attrs = {"url": url}
        action = "Visit"
    else:  # email
        attrs = {
            "to": rec.get("to"),
            "cc": rec.get("cc"),
            "bcc": rec.get("bcc"),
            "from": rec.get("from"),
            "size": int(rec["size"]) if rec.get("size") not in (None, "") else None,
            "attachments": int(rec["attachments"]) if rec.get("attachments") not in (None, "") else None,
        }
        action = "Send"

    return ParsedEvent(
        event_id=_event_id(source, str(raw_id), str(user), ts),
        user_id=str(user),
        pc_id=pc,
        ts=ts,
        source=source,
        action=action,
        attrs=attrs,
    )
