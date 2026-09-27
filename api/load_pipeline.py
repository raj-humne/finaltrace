"""Bridge: run engine.run.Pipeline and persist its output into the API's
database, so the dashboard (which reads only from the DB via the API) has
something real to show.

This did not exist before: Track B's own ingest_adapter.py is a separate,
independent CERT parser used only to populate `events` for its own testing -
nothing previously took the actual detection engine's output (features,
signals, incidents, the correlation graph, campaigns) and loaded it here.

This is a demo/reload bridge, not an incremental ETL: each run wipes and
reloads the tables it owns (in FK-safe order) rather than merging, since the
goal is "make the dashboard show the latest pipeline run", not append-only
history. ingest_runs/events from Track B's own /ingest endpoint are untouched.

Usage:
    python -m api.load_pipeline --raw-dir data/raw/r4.2
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

import api.models  # noqa: F401  (register all tables on Base.metadata)
from api.db.base import Base
from api.db.session import SessionLocal, engine
from api.models.correlation import Campaign, Incident, IncidentEdge, IncidentEvent
from api.models.detection import ConfigVersion, Signal as SignalRow
from api.models.explain import Attribution, Narrative
from api.models.feedback import Review, Suppression
from api.models.features import UserDayFeature
from api.models.identity import User, UserOrg
from api.models.ingest import Event, IngestRun

from engine.core.config import load_config
from engine.correlate.incident import Incident as EngineIncident
from engine.explain.counterfactual import counterfactual_deltas, minimal_sufficient_set
from engine.explain.narrative import build_narrative
from engine.detect.scoring import CorrelationInputs, compute_confidence, compute_risk
from engine.run import Pipeline
from api.models.detection import UserDayScore

REPO_ROOT = Path(__file__).resolve().parent.parent
BRIDGE_RUN_ID = "run_pipeline_bridge"


def _wipe(db: Session) -> None:
    """Clear tables this bridge owns, children before parents. Suppression/
    Review/Attribution aren't populated by this bridge, but pre-existing
    seed data in them FKs into incidents/signals, so they must go first."""
    for model in (Suppression, Review, Attribution, Narrative, IncidentEdge,
                  IncidentEvent, SignalRow, Incident, Campaign,
                  UserDayScore, UserDayFeature, Event, UserOrg):
        db.execute(delete(model))
    db.execute(delete(IngestRun).where(IngestRun.run_id == BRIDGE_RUN_ID))
    db.commit()


def _persist_users_and_org(db: Session, org: pd.DataFrame, events: pd.DataFrame) -> None:
    user_ids = set(events["user_id"].unique())
    if not org.empty:
        user_ids |= set(org["user_id"].unique())

    first_seen = events.groupby("user_id")["date"].min()
    last_seen = events.groupby("user_id")["date"].max()
    org_by_user = {r["user_id"]: r for _, r in org.iterrows()} if not org.empty else {}

    for uid in sorted(user_ids):
        o = org_by_user.get(uid)
        fs = first_seen.get(uid)
        ls = last_seen.get(uid)
        db.merge(User(
            user_id=uid,
            employee_name=(o.get("employee_name") if o is not None else None),
            email=(o.get("email") if o is not None else None),
            first_seen=(pd.Timestamp(fs).date() if pd.notna(fs) else dt.date(2010, 1, 1)),
            last_seen=(pd.Timestamp(ls).date() if pd.notna(ls) else dt.date(2010, 1, 1)),
            departure_date=(
                pd.Timestamp(o["departure_date"]).date()
                if o is not None and pd.notna(o.get("departure_date")) else None
            ),
        ))
        if o is not None:
            # valid_to is exclusive (docs/03-DATA-MODEL section 5): it must be
            # strictly after the last day this org record applies, or a lookup
            # for "the org as of this user's last_seen date" (api/routers/users.py
            # _current_org, called with as_of=last_seen) always misses - the
            # interval [valid_from, last_seen) does not contain last_seen itself.
            last_seen_date = pd.Timestamp(ls).date() if pd.notna(ls) else dt.date(2010, 1, 1)
            db.merge(UserOrg(
                user_id=uid,
                valid_from=(pd.Timestamp(fs).date() if pd.notna(fs) else dt.date(2010, 1, 1)),
                valid_to=last_seen_date + dt.timedelta(days=1),
                role=str(o.get("role") or "unknown"),
                department=str(o.get("department") or "unknown"),
                team=None,
                supervisor=None,
                cohort_key=str(o.get("cohort_key") or "unknown|unknown"),
            ))
    db.flush()


def _persist_events(db: Session, events: pd.DataFrame, config_version: str,
                    run_id: str = BRIDGE_RUN_ID) -> None:
    """`run_id` is additive (defaults to the original bridge constant, so the
    full-corpus load path is unaffected) - api/live_demo.py passes a distinct
    id so a demo re-persist never collides with IngestRun's primary key on a
    row the main corpus bridge already inserted."""
    db.merge(IngestRun(
        run_id=run_id,
        started_at=dt.datetime.now(dt.timezone.utc),
        finished_at=dt.datetime.now(dt.timezone.utc),
        status="success",
        source_files={"source": "engine.run.Pipeline"},
        rows_accepted=len(events),
        rows_rejected=0,
        config_version=config_version,
    ))
    db.flush()

    for row in events.itertuples(index=False):
        attrs = {c[2:]: getattr(row, c) for c in events.columns
                 if c.startswith("a_") and pd.notna(getattr(row, c))}
        db.add(Event(
            event_id=row.event_id, user_id=row.user_id,
            pc_id=(row.pc_id or None) if isinstance(row.pc_id, str) else row.pc_id,
            ts=pd.Timestamp(row.ts).to_pydatetime().replace(tzinfo=dt.timezone.utc),
            event_date=pd.Timestamp(row.date).date(),
            source=str(row.source), action=str(row.action),
            attrs=attrs, ingest_run_id=run_id,
        ))
    db.commit()


def _persist_features(db: Session, features: pd.DataFrame, config_version: str,
                      baselined_cols: list[str]) -> None:
    self_cols = [f"{c}__z_self" for c in baselined_cols if f"{c}__z_self" in features.columns]
    peer_cols = [f"{c}__z_peer" for c in baselined_cols if f"{c}__z_peer" in features.columns]
    skip = set(self_cols) | set(peer_cols) | {
        "user_id", "date", "cohort_key", "data_completeness", "baseline_maturity"}

    for row in features.itertuples(index=False):
        d = row._asdict()
        feats = {k: v for k, v in d.items() if k not in skip and pd.notna(v) if not isinstance(v, (list, dict))}
        z_self = {c[:-len("__z_self")]: d[c] for c in self_cols if pd.notna(d[c])}
        z_peer = {c[:-len("__z_peer")]: d[c] for c in peer_cols if pd.notna(d[c])}
        db.add(UserDayFeature(
            user_id=row.user_id, event_date=pd.Timestamp(row.date).date(),
            cohort_key=str(getattr(row, "cohort_key", "unknown")),
            features=_json_safe(feats), z_self=_json_safe(z_self), z_peer=_json_safe(z_peer),
            data_completeness=float(getattr(row, "data_completeness", 1.0)),
            baseline_maturity=float(getattr(row, "baseline_maturity", 0.0)),
            config_version=config_version,
        ))
    db.commit()


def _persist_user_day_scores(db: Session, pipeline: Pipeline, cfg, config_version: str) -> None:
    """One row per scored user-day (docs/03-DATA-MODEL section 5's
    user_day_scores), not only days that grew into a multi-event incident.
    api/routers/users.py's /users/{id} and /users/{id}/risk - and therefore
    the dashboard's whole "risk over time" chart and "days of history" text -
    read every day from this table. Without it, every user shows empty
    history regardless of how much real activity or signal firing they have.

    A day that fired signals but never correlated into an incident (FR-4.2
    requires >= 2 events) still gets a real standalone score here, mirroring
    engine.run.print_day's "standalone day score" branch exactly - same
    compute_risk/compute_confidence calls, just with CorrelationInputs()
    defaults instead of the incident's actual correlation inputs.
    """
    incident_for_user_date: dict[tuple[str, dt.date], EngineIncident] = {}
    for inc in pipeline.incidents:
        d = inc.window_start.date()
        end = inc.window_end.date()
        while d <= end:
            incident_for_user_date[(inc.user_id, d)] = inc
            d += dt.timedelta(days=1)

    half_life_days = cfg.detection.get("risk_decay", {}).get("half_life_days")
    risk_series_by_user: dict[str, list[tuple[dt.date, float]]] = {}

    for row in pipeline.features.itertuples(index=False):
        user_id = row.user_id
        date = pd.Timestamp(row.date).date()
        anomaly_pctl = getattr(row, "anomaly_percentile", None)
        completeness = float(getattr(row, "data_completeness", 1.0))
        maturity = float(getattr(row, "baseline_maturity", 0.0))

        inc = incident_for_user_date.get((user_id, date))
        if inc is not None:
            corr = CorrelationInputs(
                distinct_categories=inc.category_count,
                stage_advances=max(0, len(inc.stages) - 1),
                proximity_factor=0.0 if inc.over_dense else 1.0,
                over_dense=inc.over_dense,
            )
            signals = inc.signals
        else:
            corr = CorrelationInputs()
            signals = pipeline.signals_by_day.get((user_id, date), [])

        risk, breakdown, _ = compute_risk(signals, anomaly_pctl, corr, cfg)
        confidence, _ = compute_confidence(signals, anomaly_pctl, completeness, maturity, cfg)

        db.add(UserDayScore(
            user_id=user_id, event_date=date, risk=risk, confidence=confidence,
            logit=breakdown.total_logit, rule_points=breakdown.rule_points,
            ml_points=breakdown.ml_points, corr_points=breakdown.correlation_points,
            anomaly_pctl=anomaly_pctl, risk_ewma=None, config_version=config_version,
        ))
        risk_series_by_user.setdefault(user_id, []).append((date, risk))

    db.flush()

    if half_life_days:
        _apply_risk_ewma(db, risk_series_by_user, float(half_life_days))

    db.commit()


def _apply_risk_ewma(db: Session, risk_series_by_user: dict[str, list[tuple[dt.date, float]]],
                     half_life_days: float) -> None:
    """Gap-aware exponential decay (docs/02-ARCHITECTURE section 11 /
    config/detection.yaml's risk_decay.half_life_days): a day with no prior
    activity for `half_life_days` carries half the weight of yesterday, so a
    quiet stretch lets the trailing risk actually cool off rather than
    freezing at its last value."""
    for user_id, series in risk_series_by_user.items():
        series.sort(key=lambda t: t[0])
        ewma = None
        prev_date = None
        for date, risk in series:
            if ewma is None:
                ewma = risk
            else:
                gap_days = (date - prev_date).days
                decay = 0.5 ** (gap_days / half_life_days)
                ewma = decay * ewma + (1 - decay) * risk
            db.execute(
                UserDayScore.__table__.update()
                .where(UserDayScore.user_id == user_id, UserDayScore.event_date == date)
                .values(risk_ewma=ewma)
            )
            prev_date = date


def _json_safe(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (bool, int, float, str)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


def _persist_incidents(db: Session, pipeline: Pipeline, config_version: str,
                       cfg) -> dict[str, int]:
    """Incidents, their signals, evidence graph, narratives. Returns
    incident_id -> signal_id map isn't needed since Signal has no stable id
    of its own outside the DB row; signals are inserted per-incident."""
    node_ts = {n: d["ts"] for n, d in pipeline.graph.graph.nodes(data=True)} if pipeline.graph else {}
    node_role_signal = {n: d.get("is_signal", False) for n, d in pipeline.graph.graph.nodes(data=True)} if pipeline.graph else {}

    # Campaigns must exist before any Incident referencing one via campaign_id
    # (a FK) is flushed. They used to be inserted in a loop after this one,
    # which worked only because nothing forced a flush until the final
    # `db.commit()` let SQLAlchemy reorder by dependency; the per-incident
    # `db.flush()` below (needed to get each Signal's id for Attribution)
    # flushes in insertion order instead, so campaigns must go first now.
    for camp in pipeline.campaigns:
        db.add(Campaign(
            campaign_id=camp.campaign_id, user_id=camp.user_id,
            first_seen=camp.first_seen, last_seen=camp.last_seen,
            incident_count=len(camp.incident_ids), max_stage=camp.max_stage,
            peak_risk=camp.peak_risk, stage_progression=list(camp.stage_progression),
        ))
    db.flush()

    for inc in pipeline.incidents:
        db.add(Incident(
            incident_id=inc.incident_id, user_id=inc.user_id,
            window_start=inc.window_start.to_pydatetime().replace(tzinfo=dt.timezone.utc),
            window_end=inc.window_end.to_pydatetime().replace(tzinfo=dt.timezone.utc),
            risk=inc.risk, confidence=inc.confidence,
            triage_lane=inc.triage_lane or "ANALYST_REVIEW",
            status="open", killchain_stages=list(inc.stages),
            signal_count=inc.signal_count, event_count=inc.event_count,
            category_count=inc.category_count, over_dense=inc.over_dense,
            campaign_id=inc.campaign_id, config_version=config_version,
        ))

        for eid in inc.event_ids:
            db.add(IncidentEvent(
                incident_id=inc.incident_id, event_id=eid,
                node_role="signal" if node_role_signal.get(eid) else "context",
            ))

        signal_rows = []
        for s in inc.signals:
            row_obj = SignalRow(
                user_id=inc.user_id, event_date=inc.window_start.date(),
                rule_id=s.rule_id, category=s.category, killchain_stage=s.stage,
                strength=s.strength, weight=s.weight, contribution=s.contribution,
                evidence_event_ids=list(s.evidence_event_ids), phrase=s.phrase,
                detail=_json_safe(s.detail), config_version=config_version,
            )
            db.add(row_obj)
            signal_rows.append(row_obj)
        db.flush()  # assigns signal_id on each row_obj, needed for Attribution's FK below
        signal_id_by_rule = {r.rule_id: r.signal_id for r in signal_rows}

        row = pipeline.feature_row(inc.user_id, inc.window_start.date())
        if row is not None:
            corr = CorrelationInputs(
                distinct_categories=inc.category_count,
                stage_advances=max(0, len(inc.stages) - 1),
                proximity_factor=0.0 if inc.over_dense else 1.0,
                over_dense=inc.over_dense,
            )
            anomaly_pctl = row.get("anomaly_percentile")
            deltas = counterfactual_deltas(inc.signals, anomaly_pctl, corr, cfg)

            # Attribution rows (docs/03-DATA-MODEL section 5 `attributions` table):
            # this is what api/routers/incidents.py's get_incident reads to build
            # the Evidence list, so without these every incident shows 0 signals
            # regardless of how many the engine actually found - the deltas were
            # already being computed for the narrative, just never persisted.
            full_risk, _, _ = compute_risk(inc.signals, anomaly_pctl, corr, cfg)
            threshold = cfg.triage["alert_threshold"]
            minimal = minimal_sufficient_set(inc.signals, anomaly_pctl, corr, cfg, threshold, deltas=deltas)
            minimal_rule_ids = {s.rule_id for s in minimal}
            ranked = sorted(inc.signals, key=lambda s: deltas.get(s.rule_id, s.contribution), reverse=True)
            for rank, s in enumerate(ranked, start=1):
                sig_id = signal_id_by_rule.get(s.rule_id)
                if sig_id is None:
                    continue
                delta = deltas.get(s.rule_id, 0.0)
                db.add(Attribution(
                    incident_id=inc.incident_id, signal_id=sig_id,
                    points=s.contribution, risk_without=full_risk - delta, delta=delta,
                    in_minimal_set=s.rule_id in minimal_rule_ids, rank=rank,
                ))

            who = f"{inc.user_id} ({row.get('role', '?')}, {row.get('department', '?')})"
            narrative = build_narrative(inc, who, deltas, row, cfg)
            db.add(Narrative(
                incident_id=inc.incident_id, headline=narrative.headline,
                summary=narrative.summary, detail="\n".join(narrative.detail),
                template_ids=[],
            ))

    if pipeline.graph is not None:
        seen_incident_events: dict[str, set[str]] = {}
        for inc in pipeline.incidents:
            seen_incident_events[inc.incident_id] = set(inc.event_ids)
        for a, b, d in pipeline.graph.graph.edges(data=True):
            for inc in pipeline.incidents:
                members = seen_incident_events[inc.incident_id]
                if a in members and b in members:
                    db.add(IncidentEdge(
                        incident_id=inc.incident_id, src_event=a, dst_event=b,
                        gap_seconds=int(d.get("gap_seconds", 0)),
                        edge_type=str(d.get("type", "temporal")),
                        weight=float(d.get("weight", 0.0)),
                    ))
                    break
    db.commit()
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load an engine.run.Pipeline result into the API DB")
    parser.add_argument("--raw-dir", type=Path, default=REPO_ROOT / "data" / "raw" / "r4.2")
    parser.add_argument("--config-dir", type=Path, default=REPO_ROOT / "config")
    args = parser.parse_args(argv)

    cfg = load_config(str(args.config_dir))
    print(f"config_version: {cfg.version}")

    pipeline = Pipeline(cfg).run(args.raw_dir)
    print(pipeline.ingest_report.summary())
    print(f"features: {len(pipeline.features):,}  incidents: {len(pipeline.incidents):,}  "
          f"campaigns: {len(pipeline.campaigns):,}")

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        print("wiping previous bridge-loaded data...")
        _wipe(db)

        if not db.get(ConfigVersion, cfg.version):
            db.add(ConfigVersion(config_version=cfg.version, payload={}, note="loaded by api.load_pipeline"))
            db.commit()

        print("persisting users + org...")
        _persist_users_and_org(db, pipeline.org, pipeline.events)
        print("persisting events...")
        _persist_events(db, pipeline.events, cfg.version)
        print("persisting features...")
        _persist_features(db, pipeline.features, cfg.version, cfg.features["baselined_features"])
        print("persisting user-day scores...")
        _persist_user_day_scores(db, pipeline, cfg, cfg.version)
        print("persisting incidents, signals, evidence, narratives, campaigns...")
        _persist_incidents(db, pipeline, cfg.version, cfg)
        print("done.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
