from __future__ import annotations

import csv
import datetime as dt
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config_snapshot import config_version
from api.deps import get_current_account, get_db
from api.ingest_adapter import RejectedRecord, parse_record
from api.models.identity import User
from api.models.ingest import Event, IngestRun
from api.schemas.ingest import IngestRequest, IngestRunOut, IngestRunSummary, RejectSample

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(get_current_account)])

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _iter_source_records(payload: IngestRequest):
    if payload.mode == "inline":
        for rec in payload.records or []:
            yield rec
    elif payload.mode == "file":
        if not payload.path:
            raise HTTPException(status_code=400, detail="mode=file requires 'path'")
        csv_path = (REPO_ROOT / payload.path).resolve()
        if not str(csv_path).startswith(str(REPO_ROOT)):
            raise HTTPException(status_code=400, detail="path must be inside the repository")
        if not csv_path.exists():
            raise HTTPException(status_code=404, detail=f"no such file: {payload.path}")
        with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
            yield from csv.DictReader(f)
    else:
        raise HTTPException(status_code=400, detail="mode must be 'file' or 'inline'")


def _run_response(run: IngestRun) -> IngestRunOut:
    return IngestRunOut(
        run_id=run.run_id,
        status=run.status,
        source=run.source_files.get("source", ""),
        accepted=run.rows_accepted,
        rejected=run.rows_rejected,
        duplicates_skipped=run.source_files.get("duplicates_skipped", 0),
        ts_range=[run.ts_min, run.ts_max],
        rejects_sample=[RejectSample(**s) for s in (run.reject_samples or [])],
        links={"self": f"/api/v1/ingest/runs/{run.run_id}"},
    )


@router.post("", response_model=IngestRunOut, status_code=202)
def ingest(
    payload: IngestRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestRunOut:
    if idempotency_key:
        existing = db.scalars(select(IngestRun)).all()
        for run in existing:
            if run.source_files.get("idempotency_key") == idempotency_key:
                return _run_response(run)

    accepted = 0
    rejected = 0
    duplicates_skipped = 0
    reject_samples: list[dict] = []
    ts_min: dt.datetime | None = None
    ts_max: dt.datetime | None = None
    row = 0

    run_id = f"ing_{uuid.uuid4().hex[:12]}"
    run = IngestRun(
        run_id=run_id,
        started_at=dt.datetime.now(dt.timezone.utc),
        status="running",
        source_files={
            "source": payload.source, "adapter": payload.adapter, "mode": payload.mode,
            "path": payload.path, "idempotency_key": idempotency_key,
        },
        adapter_id=payload.adapter,
        config_version=config_version(),
    )
    db.add(run)
    db.flush()

    known_user_ids = {u for u in db.scalars(select(User.user_id))}
    seen_this_run: set[str] = set()

    for rec in _iter_source_records(payload):
        row += 1
        try:
            parsed = parse_record(payload.source, rec)
        except RejectedRecord as exc:
            rejected += 1
            if len(reject_samples) < 20:
                reject_samples.append({"row": row, "reason": exc.reason, "raw": str(exc.raw)[:200]})
            continue

        if parsed.event_id in seen_this_run or db.get(Event, parsed.event_id) is not None:
            duplicates_skipped += 1
            continue
        seen_this_run.add(parsed.event_id)

        if not payload.options.dry_run:
            if parsed.user_id not in known_user_ids:
                db.add(User(user_id=parsed.user_id, first_seen=parsed.ts.date(), last_seen=parsed.ts.date()))
                known_user_ids.add(parsed.user_id)
                db.flush()
            db.add(
                Event(
                    event_id=parsed.event_id, user_id=parsed.user_id, pc_id=parsed.pc_id, ts=parsed.ts,
                    event_date=parsed.ts.date(), source=parsed.source, action=parsed.action,
                    attrs=parsed.attrs, ingest_run_id=run_id,
                )
            )

        accepted += 1
        ts_min = parsed.ts if ts_min is None else min(ts_min, parsed.ts)
        ts_max = parsed.ts if ts_max is None else max(ts_max, parsed.ts)

    # ingest_runs.status is DB-constrained to running/success/failed/partial
    # (docs/03 section 5's DDL); "validated" is an API-response-only label
    # for a dry run (docs/05 section 3), not a value the CHECK constraint
    # accepts, so it's applied to the response after persisting the real
    # outcome.
    run.finished_at = dt.datetime.now(dt.timezone.utc)
    run.status = "success" if rejected == 0 else "partial"
    run.rows_accepted = accepted
    run.rows_rejected = rejected
    run.reject_samples = reject_samples
    run.ts_min = ts_min
    run.ts_max = ts_max
    run.source_files = {**run.source_files, "duplicates_skipped": duplicates_skipped}

    # dry_run already skipped every Event/User write above (see the `if not
    # payload.options.dry_run` guard); the run record itself is kept either
    # way so GET /ingest/runs shows the validation attempt in history.
    db.commit()
    db.refresh(run)
    out = _run_response(run)
    if payload.options.dry_run:
        out.status = "validated"
    return out


@router.get("/runs", response_model=list[IngestRunSummary])
def list_runs(status: str | None = None, limit: int = 50, db: Session = Depends(get_db)) -> list[IngestRunSummary]:
    stmt = select(IngestRun)
    if status:
        stmt = stmt.where(IngestRun.status == status)
    runs = db.scalars(stmt.order_by(IngestRun.started_at.desc()).limit(limit)).all()
    return [
        IngestRunSummary(
            run_id=r.run_id, status=r.status, started_at=r.started_at, finished_at=r.finished_at,
            rows_accepted=r.rows_accepted, rows_rejected=r.rows_rejected, adapter_id=r.adapter_id,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=IngestRunOut)
def get_run(run_id: str, db: Session = Depends(get_db)) -> IngestRunOut:
    run = db.get(IngestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No ingest run with id {run_id}")
    return _run_response(run)
