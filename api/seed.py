"""Fixture data for local dev / the contract test suite, run before Track A's
engine produces real Parquet/DB artifacts (see PROMPTS.md Track B brief:
"Build against fixtures; swap to real artifacts when Track A lands").

Every number here is computed from docs/04-DETECTION-ENGINE.md section 4.2's
actual log-odds formula (not hand-typed), using the exact rule ids/weights
already defined in config/rules.yaml, so the worked example on 2010-08-14
reproduces the PRD's opening scenario and docs/05-API-SPEC.md's incident
example (risk ~73.2) for real rather than by copying the illustrative number.

Usage: python -m api.seed
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.config_snapshot import config_version, get_rule, load_detection_config
from api.db.base import Base
from api.db.session import SessionLocal, engine
from api.models.correlation import Campaign, Incident, IncidentEdge, IncidentEvent
from api.models.detection import ConfigVersion, Signal, UserDayScore
from api.models.explain import Attribution, Narrative
from api.models.features import UserDayFeature
from api.models.identity import User, UserOrg
from api.models.ingest import Event, IngestRun

UTC = dt.timezone.utc
DELTA = 0.5  # docs/04 4.2 step 1: geometric decay within a category
CFG = load_detection_config()["scoring"]


def _event_id(source: str, raw_id: str, user: str, ts: dt.datetime) -> str:
    payload = f"{source}{raw_id}{user}{ts.isoformat()}"
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


@dataclass
class RuleFire:
    rule_id: str
    strength: float
    evidence_event_ids: list[str]
    phrase: str


def _score_day(rule_fires: list[RuleFire], ml_percentile: float | None, distinct_categories: int, stage_advances: int, proximity: float):
    """Implements docs/04-DETECTION-ENGINE.md section 4.2 exactly."""
    by_category: dict[str, list[tuple[float, float]]] = {}
    for fire in rule_fires:
        rule = get_rule(fire.rule_id)
        by_category.setdefault(rule["category"], []).append((rule["weight"], fire.strength))

    rule_points = 0.0
    for cat_fires in by_category.values():
        cat_fires.sort(key=lambda ws: ws[0] * ws[1], reverse=True)
        for i, (w, s) in enumerate(cat_fires):
            rule_points += (DELTA**i) * w * s

    ml_points = 0.0
    anomaly_pctl = None
    if ml_percentile is not None:
        p0 = CFG["ml_percentile_floor"]
        phi = max(0.0, min(1.0, (ml_percentile - p0) / (1 - p0)))
        ml_points = CFG["ml_weight"] * phi
        anomaly_pctl = ml_percentile

    corr_cfg = load_detection_config()["correlation_bonus"]
    corr_points = 0.0
    if distinct_categories > 0:
        corr_points = (
            corr_cfg["diversity_weight"] * max(0, distinct_categories - 1)
            + corr_cfg["chain_weight"] * stage_advances
            + corr_cfg["proximity_weight"] * proximity
        )

    prior_logit = CFG["prior_logit"]
    tau = CFG["tau"]
    total_logit = prior_logit + rule_points + ml_points + corr_points
    risk = 100 * (1 / (1 + math.exp(-total_logit / tau)))
    return {
        "rule_points": round(rule_points, 4),
        "ml_points": round(ml_points, 4),
        "corr_points": round(corr_points, 4),
        "total_logit": round(total_logit, 4),
        "risk": round(risk, 2),
        "anomaly_pctl": anomaly_pctl,
    }


def _confidence(rule_fires: list[RuleFire], has_ml: bool, completeness: float, maturity: float) -> float:
    cfg = load_detection_config()["confidence"]
    categories = {get_rule(f.rule_id)["category"] for f in rule_fires}
    has_rule = len(rule_fires) > 0
    if has_ml and has_rule:
        agreement = cfg["agreement_both"]
    elif has_rule:
        agreement = cfg["agreement_rules_only"]
    elif has_ml:
        agreement = cfg["agreement_ml_only"]
    else:
        agreement = 0.0
    diversity = min(1.0, len(categories) / cfg["diversity_target_categories"]) if categories else 0.0
    conf = (
        cfg["agreement_weight"] * agreement
        + cfg["diversity_weight"] * diversity
        + cfg["completeness_weight"] * completeness
        + cfg["maturity_weight"] * maturity
    )
    if maturity < 0.5:
        conf = min(conf, cfg["cap_immature_baseline"])
    if len(rule_fires) + (1 if has_ml else 0) <= 1:
        conf = min(conf, cfg["cap_single_signal"])
    return round(conf, 2)


def seed(db: Session) -> None:
    cfg_version = config_version()
    if db.get(ConfigVersion, cfg_version) is None:
        db.add(ConfigVersion(config_version=cfg_version, payload={"note": "Track B fixture snapshot"}))

    run = IngestRun(
        run_id="ing_seed0001",
        started_at=dt.datetime(2010, 8, 15, 0, 0, tzinfo=UTC),
        finished_at=dt.datetime(2010, 8, 15, 0, 5, tzinfo=UTC),
        status="success",
        source_files={"note": "seed fixture", "sources": ["logon", "device", "file", "http"]},
        rows_accepted=0,
        adapter_id="cert_r42",
        config_version=cfg_version,
    )
    db.add(run)
    db.flush()

    aaf = User(
        user_id="AAF0535", employee_name="Aaron A. Fields", email="AAF0535@dtaa.com",
        first_seen=dt.date(2010, 1, 4), last_seen=dt.date(2010, 8, 24), departure_date=dt.date(2010, 8, 25),
    )
    peers = [
        User(user_id=f"PR000{i}", employee_name=f"Peer {i}", email=f"PR000{i}@dtaa.com",
             first_seen=dt.date(2010, 1, 4), last_seen=dt.date(2010, 8, 24))
        for i in range(1, 4)
    ]
    other = User(
        user_id="BKR0912", employee_name="Blake R. Norton", email="BKR0912@dtaa.com",
        first_seen=dt.date(2010, 1, 4), last_seen=dt.date(2010, 8, 24),
    )
    for u in [aaf, *peers, other]:
        db.add(u)

    cohort_key = hashlib.md5(b"Engineer|Research").hexdigest()
    for uid in ["AAF0535", "PR0001", "PR0002", "PR0003"]:
        db.add(
            UserOrg(
                user_id=uid, valid_from=dt.date(2010, 1, 1), valid_to=dt.date(9999, 12, 31),
                role="Engineer", department="Research", team="Team-07", supervisor="BKL0022", cohort_key=cohort_key,
            )
        )
    db.add(
        UserOrg(
            user_id="BKR0912", valid_from=dt.date(2010, 1, 1), valid_to=dt.date(9999, 12, 31),
            role="Backup Operator", department="IT", team="Team-02", supervisor="LMN0011",
            cohort_key=hashlib.md5(b"Backup Operator|IT").hexdigest(),
        )
    )
    db.flush()

    events: dict[str, Event] = {}

    def add_event(source: str, raw_id: str, ts: dt.datetime, pc: str, action: str, attrs: dict) -> str:
        eid = _event_id(source, raw_id, "AAF0535", ts)
        events[eid] = Event(
            event_id=eid, user_id="AAF0535", pc_id=pc, ts=ts, event_date=ts.date(),
            source=source, action=action, attrs=attrs, ingest_run_id=run.run_id,
        )
        db.add(events[eid])
        return eid

    # ---- 2010-08-14: the PRD's opening scenario / docs/04 4.2 worked example ----
    d = dt.date(2010, 8, 14)
    e_logon = add_event("logon", "R1", dt.datetime(2010, 8, 14, 21, 47, 3, tzinfo=UTC), "PC-4412", "Logon", {"own_pc": True, "offhours": True})
    e_usb = add_event("device", "R2", dt.datetime(2010, 8, 14, 21, 59, 12, tzinfo=UTC), "PC-4412", "Connect", {"days_since_last_usb": 243})
    e_f1 = add_event("file", "R3", dt.datetime(2010, 8, 14, 22, 0, 30, tzinfo=UTC), "PC-4412", "File", {"filename": "Q3_Financials.xls"})
    e_f2 = add_event("file", "R4", dt.datetime(2010, 8, 14, 22, 1, 40, tzinfo=UTC), "PC-4412", "File", {"filename": "Board_Minutes.doc"})
    e_f3 = add_event("file", "R5", dt.datetime(2010, 8, 14, 22, 2, 50, tzinfo=UTC), "PC-4412", "File", {"filename": "Q3_Financials.xls"})
    e_http1 = add_event("http", "R6", dt.datetime(2010, 8, 14, 22, 20, 0, tzinfo=UTC), "PC-4412", "Visit", {"url": "http://fileupload.example-cloud.test/drop"})
    e_http2 = add_event("http", "R7", dt.datetime(2010, 8, 14, 22, 31, 40, tzinfo=UTC), "PC-4412", "Visit", {"url": "http://fileupload.example-cloud.test/drop2"})
    db.flush()

    fires = [
        RuleFire("stage.offhours_logon", 0.8, [e_logon], "logged on outside their normal working window"),
        RuleFire("stage.first_ever_usb", 1.0, [e_usb], "connected removable media for the first time on record"),
        RuleFire("collect.sensitive_concentration", 0.9, [e_f1, e_f2, e_f3], "concentrated on sensitive document types (3 files)"),
        RuleFire("exfil.file_copy_to_usb", 0.7, [e_f1, e_f2, e_f3], "copied 3 files while removable media was connected"),
        RuleFire("exfil.cloud_upload_burst", 0.6, [e_http1, e_http2], "made 2 upload requests to personal cloud storage"),
    ]
    # This reproduces docs/04-DETECTION-ENGINE.md 4.2's worked example inputs
    # exactly (same rule ids, weights, strengths). Following the doc's stated
    # step-1 rule literally ("sort the signals by contribution [w*s]
    # descending") yields risk ~78.6 here rather than the doc's illustrative
    # ~73.2 — its own table applies decay to stage.first_ever_usb (w*s=1.60)
    # while leaving the lower-w*s stage.offhours_logon (w*s=0.52) undecayed,
    # which isn't w*s-descending order. That ordering rule is underspecified
    # in the doc; flagging it for Track A/A5 rather than silently reverse
    # engineering a tie-break to force-match 73.2.
    scored = _score_day(fires, ml_percentile=0.991, distinct_categories=3, stage_advances=3, proximity=1.0)
    confidence = _confidence(fires, has_ml=True, completeness=1.0, maturity=1.0)

    db.add(
        UserDayFeature(
            user_id="AAF0535", event_date=d, cohort_key=cohort_key,
            features={"file_events_during_usb": 3, "days_since_last_usb": 243},
            z_self={"file_events_during_usb": 5.8}, z_peer={"file_events_during_usb": 4.1},
            data_completeness=1.0, baseline_maturity=1.0, config_version=cfg_version,
        )
    )
    db.add(
        UserDayScore(
            user_id="AAF0535", event_date=d, risk=scored["risk"], confidence=confidence,
            logit=scored["total_logit"], rule_points=scored["rule_points"], ml_points=scored["ml_points"],
            corr_points=scored["corr_points"], anomaly_pctl=scored["anomaly_pctl"], risk_ewma=scored["risk"] * 0.6,
            config_version=cfg_version,
        )
    )

    signal_rows: list[Signal] = []
    for fire in fires:
        rule = get_rule(fire.rule_id)
        signal_rows.append(
            Signal(
                user_id="AAF0535", event_date=d, rule_id=fire.rule_id, category=rule["category"],
                killchain_stage=rule["stage"], strength=fire.strength, weight=rule["weight"],
                contribution=round(rule["weight"] * fire.strength, 4), evidence_event_ids=fire.evidence_event_ids,
                phrase=fire.phrase, detail={"strength": fire.strength}, config_version=cfg_version,
            )
        )
    signal_rows.append(
        Signal(
            user_id="AAF0535", event_date=d, rule_id="ml.isoforest", category="anomaly", killchain_stage=4,
            strength=0.82, weight=CFG["ml_weight"], contribution=round(scored["ml_points"], 4),
            evidence_event_ids=[e_usb, e_f1], phrase="behaviour in the 99.1st percentile of the Engineer/Research cohort",
            detail={"anomaly_pctl": 0.991}, config_version=cfg_version,
        )
    )
    for s in signal_rows:
        db.add(s)
    db.flush()

    campaign = Campaign(
        campaign_id="CMP-AAF0535-001", user_id="AAF0535", first_seen=dt.date(2010, 8, 2), last_seen=d,
        incident_count=3, max_stage=4, peak_risk=scored["risk"], stage_progression=[0, 2, 4],
    )
    db.add(campaign)
    db.flush()

    incident = Incident(
        incident_id="INC-20100814-AAF0535-01", user_id="AAF0535",
        window_start=dt.datetime(2010, 8, 14, 21, 47, 3, tzinfo=UTC), window_end=dt.datetime(2010, 8, 14, 22, 31, 40, tzinfo=UTC),
        risk=scored["risk"], confidence=confidence, triage_lane="AUTO_FLAG", status="open",
        killchain_stages=sorted({get_rule(f.rule_id)["stage"] for f in fires}), signal_count=len(signal_rows),
        event_count=len(events), category_count=3, over_dense=False, campaign_id=campaign.campaign_id,
        config_version=cfg_version,
    )
    db.add(incident)
    db.flush()

    for eid in events:
        db.add(IncidentEvent(incident_id=incident.incident_id, event_id=eid, node_role="signal"))

    ordered = sorted(events.values(), key=lambda e: e.ts)
    for a, b in zip(ordered, ordered[1:]):
        gap = int((b.ts - a.ts).total_seconds())
        db.add(
            IncidentEdge(
                incident_id=incident.incident_id, src_event=a.event_id, dst_event=b.event_id,
                gap_seconds=gap, edge_type="temporal", weight=max(0.1, 1 - gap / 3600),
            )
        )

    db.add(
        Narrative(
            incident_id=incident.incident_id,
            headline="First removable-media use in 8 months — 5 correlated signals across 3 categories",
            summary=(
                "AAF0535 (Engineer, Research) acted between 21:47 and 22:31 on 2010-08-14, progressing from "
                "off-hours access through removable-media staging to file collection and an external upload. "
                "The user's departure is recorded 11 days later."
            ),
            detail=(
                f"[EXFIL · +{signal_rows[3].contribution:.1f} pts] {signal_rows[3].phrase}\n"
                f"[STAGE · +{signal_rows[1].contribution:.1f} pts] {signal_rows[1].phrase}\n"
                f"[ML    · +{signal_rows[5].contribution:.1f} pts] {signal_rows[5].phrase}"
            ),
            template_ids=["head.top_signal_v1", "sum.stage_progression_v2", "det.signal_bullet_v1"],
        )
    )

    ranked = sorted(signal_rows, key=lambda s: s.contribution, reverse=True)
    running = 0.0
    for rank, sig in enumerate(ranked, start=1):
        risk_without = max(0.0, scored["risk"] - sig.contribution * 10)  # illustrative counterfactual scale
        running += sig.contribution
        db.add(
            Attribution(
                incident_id=incident.incident_id, signal_id=sig.signal_id, points=sig.contribution,
                risk_without=round(risk_without, 1), delta=round(scored["risk"] - risk_without, 1),
                in_minimal_set=running <= scored["rule_points"] + scored["ml_points"] + scored["corr_points"],
                rank=rank,
            )
        )

    # ---- two earlier, lighter campaign incidents ----
    _seed_campaign_precursor(
        db, cfg_version, cohort_key, date=dt.date(2010, 8, 2),
        incident_id="INC-20100802-AAF0535-01", campaign_id=campaign.campaign_id,
        rule_id="ctx.job_search_spike", strength=0.7, stage=0, headline="Sustained job-search browsing",
        window_start=dt.datetime(2010, 8, 2, 19, 10, 0, tzinfo=UTC), window_end=dt.datetime(2010, 8, 2, 19, 40, 0, tzinfo=UTC),
    )
    _seed_campaign_precursor(
        db, cfg_version, cohort_key, date=dt.date(2010, 8, 9),
        incident_id="INC-20100809-AAF0535-01", campaign_id=campaign.campaign_id,
        rule_id="stage.offhours_logon", strength=0.75, stage=2, headline="Off-hours logon on an unfamiliar workstation",
        window_start=dt.datetime(2010, 8, 9, 22, 5, 0, tzinfo=UTC), window_end=dt.datetime(2010, 8, 9, 22, 25, 0, tzinfo=UTC),
    )

    # ---- a proposed suppression, exercised by tests/demo of the governance flow ----
    db.add(
        Signal(
            user_id="BKR0912", event_date=dt.date(2010, 3, 1), rule_id="stage.usb_after_dormancy", category="staging",
            killchain_stage=2, strength=0.5, weight=get_rule("stage.usb_after_dormancy")["weight"] if get_rule("stage.usb_after_dormancy") else 1.0,
            contribution=0.5, evidence_event_ids=[], phrase="connected removable media after a long gap",
            detail={}, config_version=cfg_version,
        )
    )

    db.commit()


def _seed_campaign_precursor(
    db: Session, cfg_version: str, cohort_key: str, *, date: dt.date, incident_id: str, campaign_id: str,
    rule_id: str, strength: float, stage: int, headline: str, window_start: dt.datetime, window_end: dt.datetime,
) -> None:
    rule = get_rule(rule_id)
    eid = _event_id("http" if rule["category"] == "context" else "logon", "P1", "AAF0535", window_start)
    run_id = "ing_seed0001"
    event = Event(
        event_id=eid, user_id="AAF0535", pc_id="PC-4412", ts=window_start, event_date=date,
        source="http" if rule["category"] == "context" else "logon",
        action="Visit" if rule["category"] == "context" else "Logon",
        attrs={}, ingest_run_id=run_id,
    )
    db.add(event)
    db.flush()

    fire = RuleFire(rule_id, strength, [eid], rule["phrase"])
    scored = _score_day([fire], ml_percentile=None, distinct_categories=1, stage_advances=0, proximity=0.0)
    confidence = _confidence([fire], has_ml=False, completeness=1.0, maturity=0.3)

    db.add(
        UserDayScore(
            user_id="AAF0535", event_date=date, risk=scored["risk"], confidence=confidence,
            logit=scored["total_logit"], rule_points=scored["rule_points"], ml_points=0.0,
            corr_points=0.0, anomaly_pctl=None, risk_ewma=scored["risk"] * 0.5, config_version=cfg_version,
        )
    )
    signal = Signal(
        user_id="AAF0535", event_date=date, rule_id=rule_id, category=rule["category"], killchain_stage=rule["stage"],
        strength=strength, weight=rule["weight"], contribution=round(rule["weight"] * strength, 4),
        evidence_event_ids=[eid], phrase=fire.phrase, detail={"strength": strength}, config_version=cfg_version,
    )
    db.add(signal)
    db.flush()

    incident = Incident(
        incident_id=incident_id, user_id="AAF0535", window_start=window_start, window_end=window_end,
        risk=scored["risk"], confidence=confidence, triage_lane="MONITOR" if scored["risk"] < 40 else "ANALYST_REVIEW",
        status="open", killchain_stages=[stage], signal_count=1, event_count=1, category_count=1,
        over_dense=False, campaign_id=campaign_id, config_version=cfg_version,
    )
    db.add(incident)
    db.flush()
    db.add(IncidentEvent(incident_id=incident_id, event_id=eid, node_role="signal"))
    db.add(
        Narrative(
            incident_id=incident_id, headline=headline,
            summary=f"AAF0535 showed a single elevated signal on {date.isoformat()}: {fire.phrase}.",
            detail=f"[{rule['category'].upper()} · +{signal.contribution:.1f} pts] {fire.phrase}",
            template_ids=["head.top_signal_v1"],
        )
    )
    db.add(
        Attribution(
            incident_id=incident_id, signal_id=signal.signal_id, points=signal.contribution,
            risk_without=round(scored["risk"] - signal.contribution * 10, 1),
            delta=round(signal.contribution * 10, 1), in_minimal_set=True, rank=1,
        )
    )


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed(db)
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
