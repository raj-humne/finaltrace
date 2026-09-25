"""SentinelTrace engine CLI (docs/09-DELIVERY-PLAN.md milestones M3-M4).

Wires ingest -> features -> baselines -> anomaly -> rules -> correlate ->
explain -> route into the one pipeline the rest of the system consumes.
`engine/` reads raw CSVs and writes Parquet; it never touches a database
(docs/02-ARCHITECTURE.md section 6 - the API is the only DB reader/writer,
and the batch runner here is the only writer to the Parquet artifacts).

Usage:
    python -m engine.run
    python -m engine.run --user AB0026 --date 2010-07-23
    python -m engine.run --raw-dir data/synthetic --no-write
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from engine.core.config import Config, load_config
from engine.correlate.graph import build_graph
from engine.correlate.incident import Campaign, Incident, build_incidents, link_campaigns
from engine.detect.anomaly import score_anomaly
from engine.detect.rules import detect_signals
from engine.detect.scoring import CorrelationInputs, compute_confidence, compute_risk
from engine.explain.counterfactual import counterfactual_deltas
from engine.explain.narrative import build_narrative
from engine.features.baseline import add_baselines
from engine.features.extract import build_features
from engine.ingest.loader import IngestReport, load_events, load_org
from engine.route.triage import route

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_ARTIFACTS_DIR = REPO_ROOT / "data" / "artifacts"


def _peak_rss_mb() -> float | None:
    """Peak resident set size in MB so far, for the diagnostic checkpoints
    below - Unix only (Kaggle/Linux), silently unavailable on Windows."""
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return ru / 1024  # ru_maxrss is KB on Linux
    except ImportError:
        return None


class Pipeline:
    """Holds every stage's output. One object per run, for the CLI and for
    tests that want to inspect an intermediate stage directly."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.events: pd.DataFrame = pd.DataFrame()
        self.org: pd.DataFrame = pd.DataFrame()
        self.features: pd.DataFrame = pd.DataFrame()
        self.signals_by_day: dict = {}
        self.graph = None
        self.incidents: list[Incident] = []
        self.campaigns: list[Campaign] = []
        self.ingest_report: IngestReport | None = None

    def run(self, raw_dir: Path) -> "Pipeline":
        def _checkpoint(stage: str) -> None:
            rss = _peak_rss_mb()
            if rss is not None:
                print(f"[checkpoint] after {stage}: peak RSS {rss:,.0f} MB", flush=True)

        self.events, self.ingest_report = load_events(raw_dir, self.cfg)
        self.org = load_org(raw_dir)
        _checkpoint("load_events + load_org")

        feats = build_features(self.events, self.org, self.cfg)
        _checkpoint("build_features")
        feats = add_baselines(feats, self.cfg)
        _checkpoint("add_baselines")
        feats = score_anomaly(feats, self.cfg)
        _checkpoint("score_anomaly")
        self.features = feats

        self.signals_by_day = detect_signals(self.features, self.events, self.cfg)
        _checkpoint("detect_signals")
        self.graph = build_graph(self.events, self.signals_by_day, self.cfg)
        _checkpoint("build_graph")

        anomaly_by_ud: dict = {}
        completeness_by_ud: dict = {}
        maturity_by_ud: dict = {}
        for row in self.features.itertuples(index=False):
            key = (row.user_id, pd.Timestamp(row.date).date())
            anomaly_by_ud[key] = getattr(row, "anomaly_percentile", None)
            completeness_by_ud[key] = row.data_completeness
            maturity_by_ud[key] = row.baseline_maturity

        self.incidents = build_incidents(self.events, self.graph, anomaly_by_ud,
                                         completeness_by_ud, maturity_by_ud, self.cfg)
        _checkpoint("build_incidents")
        self.campaigns = link_campaigns(self.incidents, self.cfg)
        _checkpoint("link_campaigns")

        for inc in self.incidents:
            inc.triage_lane = route(inc.risk, inc.confidence, self.cfg).lane
        _checkpoint("route")
        return self

    def feature_row(self, user_id: str, date) -> dict | None:
        date = pd.Timestamp(date)
        match = self.features[(self.features["user_id"] == user_id)
                              & (pd.to_datetime(self.features["date"]) == date)]
        return match.iloc[0].to_dict() if not match.empty else None

    def incidents_for(self, user_id: str, date) -> list[Incident]:
        date = pd.Timestamp(date).date()
        return [inc for inc in self.incidents
               if inc.user_id == user_id and inc.window_start.date() <= date <= inc.window_end.date()]

    def write_artifacts(self, out_dir: Path) -> None:
        """Events and features to Parquet, partitioned by month (docs/03-
        DATA-MODEL.md section 6). Incidents/signals are not written here -
        those are relational (ADR 0005) and land in the DB via the API's
        repository layer, not this engine-only batch step."""
        if self.events.empty:
            return
        events_dir = out_dir / "events"
        tagged = self.events.assign(_month=pd.to_datetime(self.events["date"]).dt.to_period("M"))
        for period, grp in tagged.groupby("_month"):
            month_dir = events_dir / f"year={period.year}" / f"month={period.month:02d}"
            month_dir.mkdir(parents=True, exist_ok=True)
            grp.drop(columns=["_month"]).to_parquet(month_dir / "part-000.parquet", index=False)

        feat_dir = out_dir / "features"
        feat_dir.mkdir(parents=True, exist_ok=True)
        tagged = self.features.assign(
            _month=pd.to_datetime(self.features["date"]).dt.to_period("M"))
        for period, grp in tagged.groupby("_month"):
            grp.drop(columns=["_month"]).to_parquet(
                feat_dir / f"month={period.year}-{period.month:02d}.parquet", index=False)


def print_day(pipeline: Pipeline, user_id: str, date_str: str, cfg: Config) -> None:
    date = pd.Timestamp(date_str)
    print(f"\n{'=' * 70}\n{user_id}  {date.date()}\n{'=' * 70}")

    row = pipeline.feature_row(user_id, date)
    if row is None:
        print("no feature row for this user/date (no activity, or outside the ingested range)")
        return

    day_signals = pipeline.signals_by_day.get((user_id, date.date()), [])
    incidents = pipeline.incidents_for(user_id, date.date())

    if incidents:
        for inc in incidents:
            print(f"\n--- {inc.incident_id}  (triage: {inc.triage_lane}) ---")
            print(f"risk={inc.risk:.1f}  confidence={inc.confidence:.2f}  "
                 f"campaign={inc.campaign_id or '-'}  over_dense={inc.over_dense}")
            print(f"logit breakdown: {inc.breakdown.as_dict()}")
            print(f"confidence terms: {inc.confidence_terms.as_dict()}")

            corr = CorrelationInputs(
                distinct_categories=inc.category_count,
                stage_advances=max(0, len(inc.stages) - 1),
                proximity_factor=0.0 if inc.over_dense else 1.0,
                over_dense=inc.over_dense,
            )
            deltas = counterfactual_deltas(inc.signals, row.get("anomaly_percentile"), corr, cfg)
            who = f"{user_id} ({row.get('role', '?')}, {row.get('department', '?')})"
            narrative = build_narrative(inc, who, deltas, row, cfg)

            print(f"\nHEADLINE: {narrative.headline}")
            print(f"SUMMARY:  {narrative.summary}")
            print("DETAIL:")
            for line in narrative.detail:
                print(f"  {line}")

    elif day_signals:
        min_events = cfg.correlation["min_events_per_incident"]
        print(f"\n{len(day_signals)} signal(s) fired but did not form a multi-event "
             f"incident (< {min_events} correlated events). Standalone day score:")
        corr = CorrelationInputs()
        risk, breakdown, updated = compute_risk(
            day_signals, row.get("anomaly_percentile"), corr, cfg)
        confidence, terms = compute_confidence(
            day_signals, row.get("anomaly_percentile"),
            row.get("data_completeness", 1.0), row.get("baseline_maturity", 0.0), cfg)
        decision = route(risk, confidence, cfg)
        print(f"risk={risk:.1f}  confidence={confidence:.2f}  lane={decision.lane}")
        print(f"logit breakdown: {breakdown.as_dict()}")
        print(f"confidence terms: {terms.as_dict()}")
        for s in sorted(updated, key=lambda s: -s.contribution):
            print(f"  [{s.category.upper()} · +{s.contribution:.2f} pts] {s.phrase}")
    else:
        print("\nno signals fired on this day.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentinelTrace detection engine")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR,
                       help="directory with logon/device/file/http/email.csv + LDAP/ "
                            f"(default: {DEFAULT_RAW_DIR})")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--no-write", action="store_true",
                       help="skip writing Parquet artifacts")
    parser.add_argument("--user", type=str, default=None)
    parser.add_argument("--date", type=str, default=None,
                       help="YYYY-MM-DD, used with --user")
    args = parser.parse_args(argv)

    cfg = load_config()
    print(f"config_version: {cfg.version}")

    pipeline = Pipeline(cfg).run(args.raw_dir)
    print(pipeline.ingest_report.summary())
    print(f"\nuser-days: {len(pipeline.features):,}  incidents: {len(pipeline.incidents):,}  "
         f"campaigns: {len(pipeline.campaigns):,}")

    if not args.no_write:
        pipeline.write_artifacts(args.out_dir)
        print(f"artifacts written to {args.out_dir}")

    if args.user and args.date:
        print_day(pipeline, args.user, args.date, cfg)
    elif args.user or args.date:
        print("--user and --date must be given together", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
