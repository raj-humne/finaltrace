"""Live-injection demo: a real employee (`DEMO_USER_ID`), a real ~9-week
engine-computed baseline, and a small catalogue of semantic "actions" that
append real rows to the real CSVs the engine reads, then re-run the actual
detection engine end to end.

This is not a second, fake detection path. `inject_and_rescore()` calls the
exact same `engine.run.Pipeline` every other entry point uses - the only
thing special about this dataset is that it is a small, dedicated, clearly-
synthetic corpus (`data/demo_live/`, generated with zero injected scenarios,
so every incident up to the point of live injection is the engine correctly
finding nothing) built specifically so a live demo has a mature baseline to
be anomalous against. Real CERT scoring claims never come from this dataset
(engine.eval.harness's real-data guard has nothing to do with this file, by
design - this is a demo mechanism, not an evaluation source).

Injected events land as real rows in the real CSVs (append-only, in the
exact CERT schema `engine.ingest.loader.CertAdapter` already parses), so a
full engine.run.Pipeline().run() naturally picks them up on the very next
call with zero new ingestion code. Measured at ~5s for a full re-run over
this dataset's size - fast enough to feel live without needing incremental
scoring.

Two laptops: Laptop B runs this API (bound to 0.0.0.0 so it's reachable on
the LAN). Laptop A runs tools/live_demo_inject.py, which authenticates
against Laptop B's API exactly like any other client and calls
POST /live-demo/inject - it has no engine or database code of its own.
"""
from __future__ import annotations

import csv
import datetime as dt
import threading
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.db.base import Base
from api.db.session import engine as db_engine
from api.models.correlation import Campaign, Incident, IncidentEdge, IncidentEvent
from api.models.detection import ConfigVersion, Signal as SignalRow, UserDayScore
from api.models.explain import Attribution, Narrative
from api.models.features import UserDayFeature
from api.models.identity import User
from api.models.ingest import Event, IngestRun
from api.models.mitigation import MitigationAction
from engine.core.config import Config, load_config
from engine.run import Pipeline

DEMO_INGEST_RUN_ID = "live_demo"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_RAW_DIR = REPO_ROOT / "data" / "demo_live"
DEMO_USER_ID = "AA0000"
DEMO_OWN_PC = "PC-1000"
DEMO_FOREIGN_PC = "PC-1009"  # a real peer's PC in the generated dataset, for "on a workstation that isn't theirs"
DEMO_TS = "%m/%d/%Y %H:%M:%S"
# The generated baseline runs through 2010-03-05 (see the module docstring's
# dataset). Injected events must be anchored just after that, not at the
# real wall-clock "now" - the demo employee's 30-day trailing baseline and
# every z_self/z_peer feature are computed relative to event dates, so an
# anchor 16 real-world years away from the baseline leaves those windows
# empty and produces a weak, unrealistic score instead of the dramatic one
# a live-off-hours-logon-plus-first-ever-USB sequence should actually earn.
DEMO_BASE_ANCHOR = dt.datetime(2010, 3, 8, 21, 47, 0)

# The one write lock for this demo's CSVs + the DB rows this endpoint owns.
# A live demo is one operator at a time by nature; this only guards against
# two requests racing on the same append.
_LOCK = threading.Lock()


class UnknownDemoAction(ValueError):
    pass


def _next_ids() -> dict[str, int]:
    """Highest numeric suffix already used per source, so appended ids never
    collide with the generated dataset's own {X-0000001} scheme."""
    counts: dict[str, int] = {}
    for prefix, name in (("L", "logon"), ("D", "device"), ("F", "file"),
                        ("H", "http"), ("E", "email")):
        path = DEMO_RAW_DIR / f"{name}.csv"
        n = 0
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    rid = row.get("id", "")
                    digits = "".join(c for c in rid if c.isdigit())
                    if digits:
                        n = max(n, int(digits))
        counts[prefix] = n
    return counts


def _next_anchor() -> dt.datetime:
    """DEMO_BASE_ANCHOR on a fresh/reset dataset; on a repeat injection
    within the same demo session, the day after whatever was most recently
    injected - so replaying the scenario twice reads as two separate days
    (each fully scored on its own) rather than overlapping the exact same
    timestamps or silently landing back in 2026."""
    latest = None
    for name in ("logon", "device", "file", "http", "email"):
        path = DEMO_RAW_DIR / f"{name}.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    ts = dt.datetime.strptime(row["date"], DEMO_TS)
                except (KeyError, ValueError):
                    continue
                # >= not >: an injected event can legitimately land exactly
                # ON the anchor (e.g. a single "offhours_logon" action with
                # no start_at, whose only event is anchor+0) - a strict `>`
                # here would never recognise that as prior evidence, and a
                # second single-action injection with no explicit start_at
                # would silently reuse the exact same timestamp instead of
                # advancing a day.
                if ts >= DEMO_BASE_ANCHOR and (latest is None or ts > latest):
                    latest = ts
    if latest is None:
        return DEMO_BASE_ANCHOR
    next_day = (latest + dt.timedelta(days=1)).replace(
        hour=DEMO_BASE_ANCHOR.hour, minute=DEMO_BASE_ANCHOR.minute, second=0)
    return next_day


def _append_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        for row in rows:
            w.writerow(row)


def _fmt(ts: dt.datetime) -> str:
    return ts.strftime(DEMO_TS)


# ------------------------------------------------------------- action catalogue
# Each macro is a small, named, pre-built chunk of a real insider sequence -
# Laptop A's script sends the name, not raw CERT columns, so it needs no
# knowledge of the engine's internal schema. `anchor` is when the macro
# starts; each returns the list of (source, row-dict) pairs to append.
def _macro_offhours_logon(anchor: dt.datetime, seq: dict[str, int]) -> list[tuple[str, dict]]:
    seq["L"] += 1
    return [("logon", {"id": f"{{L-{seq['L']:07d}}}", "date": _fmt(anchor),
                       "user": DEMO_USER_ID, "pc": DEMO_OWN_PC, "activity": "Logon"})]


def _macro_usb_connect_foreign(anchor: dt.datetime, seq: dict[str, int]) -> list[tuple[str, dict]]:
    seq["D"] += 1
    return [("device", {"id": f"{{D-{seq['D']:07d}}}", "date": _fmt(anchor),
                        "user": DEMO_USER_ID, "pc": DEMO_FOREIGN_PC, "activity": "Connect"})]


def _macro_file_copy_burst(anchor: dt.datetime, seq: dict[str, int],
                           count: int = 45) -> list[tuple[str, dict]]:
    """count=45 (not a rounder, smaller number) is deliberate: both
    exfil.file_copy_to_usb (log strength scale, lo=10/hi=200) and
    collect.file_burst (gte 25 within any 10-min window, log scale
    lo=25/hi=300) sit right at their threshold floor with a small count and
    contribute strength ~0 despite technically firing - a real trap this
    macro fell into originally. 45 in an 8-second cadence (352s total, safely
    under the 10-minute window) clears both floors with real strength."""
    out = []
    exts = ["xlsx", "pdf", "zip", "csv", "docx"]
    for i in range(count):
        seq["F"] += 1
        ts = anchor + dt.timedelta(seconds=i * 8)
        out.append(("file", {
            "id": f"{{F-{seq['F']:07d}}}", "date": _fmt(ts), "user": DEMO_USER_ID,
            "pc": DEMO_FOREIGN_PC, "filename": f"Q{i:02d}_{uuid.uuid4().hex[:8].upper()}.{exts[i % len(exts)]}",
            "to_removable_media": "True", "content": "",
        }))
    return out


def _macro_usb_disconnect(anchor: dt.datetime, seq: dict[str, int]) -> list[tuple[str, dict]]:
    seq["D"] += 1
    return [("device", {"id": f"{{D-{seq['D']:07d}}}", "date": _fmt(anchor),
                        "user": DEMO_USER_ID, "pc": DEMO_FOREIGN_PC, "activity": "Disconnect"})]


def _macro_leak_upload(anchor: dt.datetime, seq: dict[str, int]) -> list[tuple[str, dict]]:
    """3 visits, not 1: exfil.leak_platform_visit's strength scale is
    log(lo=1, hi=10) - at exactly leak_platform_visits=1 that is
    log(1/1)/log(10/1) = 0, so a single visit "fires" the rule (it clears
    the >=1 threshold) but contributes literally zero risk. This is a real,
    generalizable property of every log-scale rule in the catalogue: firing
    and contributing are different things at the floor value."""
    out = []
    docs = ["quarterly-financials", "client-contracts", "engineering-roadmap"]
    for i, doc in enumerate(docs):
        seq["H"] += 1
        ts = anchor + dt.timedelta(seconds=i * 20)
        out.append(("http", {"id": f"{{H-{seq['H']:07d}}}", "date": _fmt(ts),
                             "user": DEMO_USER_ID, "pc": DEMO_FOREIGN_PC,
                             "url": f"http://pastebin.com/upload?doc={doc}",
                             "content": ""}))
    return out


ACTIONS: dict[str, Any] = {
    "offhours_logon": _macro_offhours_logon,
    "usb_connect_foreign": _macro_usb_connect_foreign,
    "file_copy_burst": _macro_file_copy_burst,
    "usb_disconnect": _macro_usb_disconnect,
    "leak_upload": _macro_leak_upload,
}

# The full staged sequence in one call, each macro offset a realistic number
# of minutes from the last - the PRD's own opening scenario, replayed live.
FULL_SCENARIO: list[tuple[str, int]] = [
    ("offhours_logon", 0),
    ("usb_connect_foreign", 12),
    ("file_copy_burst", 17),   # runs ~6 minutes (45 files, 8s apart) -> ends ~23
    ("usb_disconnect", 24),
    ("leak_upload", 29),
]

_FILE_SPECS = {
    "logon": ["id", "date", "user", "pc", "activity"],
    "device": ["id", "date", "user", "pc", "activity"],
    "file": ["id", "date", "user", "pc", "filename", "to_removable_media", "content"],
    "http": ["id", "date", "user", "pc", "url", "content"],
    "email": ["id", "date", "user", "pc", "to", "cc", "bcc", "from", "size", "attachments", "content"],
}


def append_actions(action_names: list[str], start_at: dt.datetime | None = None) -> dt.datetime:
    """Append rows for each named action, spaced a few minutes apart starting
    at `start_at` (default: now, UTC-naive to match the dataset's own naive
    timestamps). Returns the timestamp of the last appended event."""
    with _LOCK:
        seq = _next_ids()
        anchor = start_at or _next_anchor()
        by_source: dict[str, list[dict]] = {"logon": [], "device": [], "file": [], "http": [], "email": []}

        cursor = anchor
        for name in action_names:
            if name not in ACTIONS:
                raise UnknownDemoAction(f"unknown demo action: {name!r} (known: {sorted(ACTIONS)})")
            for source, row in ACTIONS[name](cursor, seq):
                by_source[source].append(row)
            cursor = cursor + dt.timedelta(minutes=3)

        for source, rows in by_source.items():
            if rows:
                _append_rows(DEMO_RAW_DIR / f"{source}.csv", _FILE_SPECS[source], rows)

        return cursor


def append_full_scenario(start_at: dt.datetime | None = None) -> dt.datetime:
    """The staged 5-step sequence in one shot, with the PRD's own timing
    offsets (12/17/22/27 minutes) rather than the flat 3-minute spacing
    `append_actions` uses for arbitrary action lists."""
    with _LOCK:
        seq = _next_ids()
        anchor = start_at or _next_anchor()
        by_source: dict[str, list[dict]] = {"logon": [], "device": [], "file": [], "http": [], "email": []}
        last_ts = anchor
        for name, offset_min in FULL_SCENARIO:
            ts = anchor + dt.timedelta(minutes=offset_min)
            for source, row in ACTIONS[name](ts, seq):
                by_source[source].append(row)
                last_ts = max(last_ts, dt.datetime.strptime(row["date"], DEMO_TS))
        for source, rows in by_source.items():
            if rows:
                _append_rows(DEMO_RAW_DIR / f"{source}.csv", _FILE_SPECS[source], rows)
        return last_ts


def reset_demo_events(db: Session) -> None:
    """Truncate every source CSV back to just its header row, discarding all
    previously injected rows - the demo employee's original ~9-week baseline
    lives in a separate, untouched copy this restores from - and delete this
    user's persisted rows from the DB too, or a stale live-injected incident
    would keep showing on the dashboard after a reset even though the CSVs
    (and the next rescore) no longer produce it."""
    import shutil
    _wipe_demo_rows(db)
    backup_dir = DEMO_RAW_DIR / "_original"
    with _LOCK:
        for source in _FILE_SPECS:
            src = backup_dir / f"{source}.csv"
            dst = DEMO_RAW_DIR / f"{source}.csv"
            if src.exists():
                shutil.copyfile(src, dst)


def rescore(cfg: Config | None = None) -> Pipeline:
    """Re-run the real engine over the demo dataset as it currently stands
    on disk (original baseline + whatever has been injected so far)."""
    cfg = cfg or load_config()
    return Pipeline(cfg).run(DEMO_RAW_DIR)


def _wipe_demo_rows(db: Session) -> None:
    """Delete only this demo user's previously-persisted rows, in FK-safe
    order - never touches any other user's data, unlike load_pipeline.py's
    full-corpus _wipe(). Every call to persist_demo_result() re-persists
    DEMO_USER_ID's ENTIRE history (all ~9 weeks of baseline plus whatever has
    been injected), not only the newest day - so this must be a full wipe of
    that user's rows, not date-scoped, or the second injection in a demo
    session would hit a primary-key violation re-inserting the same
    Event/UserDayFeature/UserDayScore rows from the first call.

    Note: build_incidents() assigns an incident's `user_id` to whichever
    participant has the most events in that connected component (docs/04
    section 6.3). Every incident this demo can plausibly produce is
    overwhelmingly dominated by DEMO_USER_ID's own injected burst, so this
    filter is correct in practice; it is not a hard guarantee against every
    conceivable component shape.
    """
    incident_ids = [
        r[0] for r in db.query(Incident.incident_id).filter(Incident.user_id == DEMO_USER_ID).all()
    ]
    if incident_ids:
        db.execute(delete(MitigationAction).where(MitigationAction.incident_id.in_(incident_ids)))
        db.execute(delete(Attribution).where(Attribution.incident_id.in_(incident_ids)))
        db.execute(delete(Narrative).where(Narrative.incident_id.in_(incident_ids)))
        db.execute(delete(IncidentEdge).where(IncidentEdge.incident_id.in_(incident_ids)))
        db.execute(delete(IncidentEvent).where(IncidentEvent.incident_id.in_(incident_ids)))
        db.execute(delete(Incident).where(Incident.user_id == DEMO_USER_ID))
    db.execute(delete(SignalRow).where(SignalRow.user_id == DEMO_USER_ID))
    db.execute(delete(Campaign).where(Campaign.user_id == DEMO_USER_ID))
    db.execute(delete(UserDayScore).where(UserDayScore.user_id == DEMO_USER_ID))
    db.execute(delete(UserDayFeature).where(UserDayFeature.user_id == DEMO_USER_ID))
    db.execute(delete(Event).where(Event.user_id == DEMO_USER_ID))
    db.execute(delete(IngestRun).where(IngestRun.run_id == DEMO_INGEST_RUN_ID))
    db.commit()


def persist_demo_result(db: Session, pipeline: Pipeline, cfg: Config) -> list[Incident]:
    """Write only DEMO_USER_ID's incidents (and their signals/attributions/
    narratives/scores) from a fresh pipeline run into the real database,
    reusing api.load_pipeline's exact row-mapping logic so a demo incident is
    stored identically to one loaded from the real corpus."""
    from api.load_pipeline import (
        _persist_events, _persist_features, _persist_incidents,
        _persist_user_day_scores, _persist_users_and_org,
    )

    Base.metadata.create_all(db_engine)
    if not db.get(ConfigVersion, cfg.version):
        db.add(ConfigVersion(config_version=cfg.version, payload={}, note="live_demo"))
        db.commit()

    _wipe_demo_rows(db)

    demo_events = pipeline.events[pipeline.events["user_id"] == DEMO_USER_ID]
    demo_features = pipeline.features[pipeline.features["user_id"] == DEMO_USER_ID]
    demo_incidents_only = [i for i in pipeline.incidents if i.user_id == DEMO_USER_ID]

    # users/org for every user (cheap, and other demo-cohort users need to
    # exist for FK integrity on shared_pc/shared_file cross-user edges).
    _persist_users_and_org(db, pipeline.org, pipeline.events)

    if not db.get(User, DEMO_USER_ID):
        pass  # _persist_users_and_org already covers this via merge()

    _persist_events(db, demo_events, cfg.version, run_id=DEMO_INGEST_RUN_ID)
    _persist_features(db, demo_features, cfg.version, cfg.features["baselined_features"])

    class _DemoPipelineView:
        """A tiny stand-in so _persist_user_day_scores/_persist_incidents -
        which read pipeline.features/.incidents/.campaigns/.graph/.signals_by_day/
        .feature_row() - see only this user's slice, without needing those
        functions to grow a user filter of their own."""
        def __init__(self, features, incidents, campaigns, graph, signals_by_day, feature_row_fn):
            self.features = features
            self.incidents = incidents
            self.campaigns = campaigns
            self.graph = graph
            self.signals_by_day = signals_by_day
            self.feature_row = feature_row_fn

    demo_campaigns = [c for c in pipeline.campaigns if c.user_id == DEMO_USER_ID]
    demo_signals_by_day = {k: v for k, v in pipeline.signals_by_day.items() if k[0] == DEMO_USER_ID}
    view = _DemoPipelineView(demo_features, demo_incidents_only, demo_campaigns,
                             pipeline.graph, demo_signals_by_day, pipeline.feature_row)

    _persist_user_day_scores(db, view, cfg, cfg.version)
    _persist_incidents(db, view, cfg.version, cfg)

    return demo_incidents_only


def inject_and_rescore(action_names: list[str] | None, use_full_scenario: bool,
                       db: Session, cfg: Config | None = None) -> dict:
    """The one call the API endpoint makes: append, rescore, persist, and
    return a summary of what the demo employee's live incident looks like."""
    cfg = cfg or load_config()

    if use_full_scenario:
        last_ts = append_full_scenario()
    else:
        last_ts = append_actions(action_names or [])

    pipeline = rescore(cfg)
    demo_incidents = persist_demo_result(db, pipeline, cfg)

    # Automated mitigation (Challenge 1) already ran as part of incident
    # finalization inside persist_demo_result -> api.load_pipeline._persist_
    # incidents (the one shared integration point for both this live-demo
    # path and the full bulk corpus bridge). Read back whatever it recorded
    # for these incidents, for display in this response - never re-evaluate
    # here, since evaluate_and_mitigate is only meant to run once per
    # incident at finalization time.
    mitigation_by_incident: dict[str, dict] = {}
    incident_ids = [i.incident_id for i in demo_incidents]
    if incident_ids:
        for row in db.scalars(
            select(MitigationAction).where(MitigationAction.incident_id.in_(incident_ids))
        ).all():
            mitigation_by_incident[row.incident_id] = {
                "mitigation_action_id": row.mitigation_action_id,
                "threat_weight": row.threat_weight,
                "threshold": row.threshold,
                "status": row.status,
                "isolation_status": row.isolation_status,
                "target_type": row.target_type,
                "target_value": row.target_value,
            }

    live_day = last_ts.date()
    todays = [i for i in demo_incidents if i.window_start.date() <= live_day <= i.window_end.date()]

    return {
        "user_id": DEMO_USER_ID,
        "injected_through": last_ts.isoformat(),
        "incidents_today": [
            {
                "incident_id": i.incident_id, "risk": round(i.risk, 1),
                "confidence": round(i.confidence, 2), "triage_lane": i.triage_lane,
                "signal_count": i.signal_count, "event_count": i.event_count,
                "categories": list(i.categories), "stages": list(i.stages),
                "mitigation": mitigation_by_incident.get(i.incident_id),
            }
            for i in todays
        ],
        "total_incidents_for_user": len(demo_incidents),
    }
