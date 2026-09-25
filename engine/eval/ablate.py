"""Ablation study (docs/07-EVALUATION.md section 4).

Isolates what each layer of the hybrid design actually buys. Every row is a
real, independently computed pipeline run and evaluation report - never a
config flag read by engine internals that don't exist, and never scoring
logic duplicated here. Each row is built by calling the *same* real engine
functions `engine.run.Pipeline` calls, just a different subset of them:

  1. rules_only_no_baselines  - build_features, skip add_baselines, skip
     score_anomaly. Rules gated on z_self_gte/z_peer_gte fail closed on their
     own (engine/detect/rules.py's `_feature_value` returns None for a
     missing column, which every comparison operator treats as "does not
     fire") - no engine change was needed to realise this row.
  2. rules_only_with_baselines - add add_baselines back, ML still skipped.
  3. ml_only                   - skip detect_signals entirely (empty
     signals_by_day for every day). No rule signal ever fires, which under
     the current architecture also means no multi-event *incident* can ever
     form (engine/correlate/incident.py requires >=1 signal-carrying node per
     component) - this row can only be evaluated at user-day granularity via
     `build_day_scores`'s anomaly-only fallback path, not at incident level.
     That is a real, reportable architectural property, not a bug in this row.
  4. hybrid_no_correlation     - rules + ML, `build_incidents(...,
     disable_correlation_bonus=True)` (the one small additive engine
     parameter this module needed - see engine/correlate/incident.py).
  5. hybrid_with_correlation   - same, correlation bonus on.
  6. hybrid_with_campaigns     - + `link_campaigns`. Note (read before
     interpreting this row): `link_campaigns` currently only annotates
     `Incident.campaign_id` and computes a separate `Campaign.peak_risk`; it
     does not feed back into any individual incident's risk/confidence/lane.
     Under the current engine, this row is therefore expected to show *no*
     measurable difference from row 5 at the per-incident and per-day metrics
     this harness computes - `ablation_notes()` below reports that plainly as
     a finding rather than hiding it (see its own docstring).
  7. full_system               - identical run to row 6; included so the
     table has an explicit "this is what ships" row for a same-footing read.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from engine.core.config import Config, load_config
from engine.eval.harness import build_day_scores, build_insider_index, build_report


@dataclass
class AblationRow:
    name: str
    description: str
    report: dict | None = None
    error: str | None = None


def _bump_version(cfg: Config, suffix: str) -> Config:
    """A distinct `config_version` per ablation row, so a stored report is
    traceable to exactly which variant produced it (NFR-8) - never mutates
    the real config, which stays identical across every row except for the
    flags each row's runner explicitly applies."""
    return Config(detection=cfg.detection, features=cfg.features,
                 correlation=cfg.correlation, triage=cfg.triage, rules=cfg.rules,
                 domains=cfg.domains, version=f"{cfg.version}:{suffix}",
                 source_dir=cfg.source_dir)


class AblatedPipeline:
    """Same shape as `engine.run.Pipeline` (features, signals_by_day,
    incidents) but assembled by calling a chosen subset of the real stage
    functions - this class contains no scoring or detection logic of its
    own, only which real stages to call and in what combination."""

    def __init__(self, features, signals_by_day, incidents):
        self.features = features
        self.signals_by_day = signals_by_day
        self.incidents = incidents


def _run_row(name: str, cfg: Config, events, org,
            use_baselines: bool, use_ml: bool, use_rules: bool,
            disable_correlation_bonus: bool, use_campaigns: bool) -> AblatedPipeline:
    from engine.correlate.graph import build_graph
    from engine.correlate.incident import link_campaigns, build_incidents
    from engine.detect.anomaly import score_anomaly
    from engine.detect.rules import detect_signals
    from engine.features.baseline import add_baselines
    from engine.features.extract import build_features
    from engine.route.triage import route

    row_cfg = _bump_version(cfg, name)

    feats = build_features(events, org, row_cfg)
    if use_baselines:
        feats = add_baselines(feats, row_cfg)
    if use_ml:
        feats = score_anomaly(feats, row_cfg)

    signals_by_day = detect_signals(feats, events, row_cfg) if use_rules else {}

    graph = build_graph(events, signals_by_day, row_cfg)

    anomaly_by_ud, completeness_by_ud, maturity_by_ud = {}, {}, {}
    for r in feats.itertuples(index=False):
        key = (r.user_id, pd.Timestamp(r.date).date())
        anomaly_by_ud[key] = getattr(r, "anomaly_percentile", None)
        completeness_by_ud[key] = getattr(r, "data_completeness", 1.0)
        maturity_by_ud[key] = getattr(r, "baseline_maturity", 0.0)

    incidents = build_incidents(events, graph, anomaly_by_ud, completeness_by_ud,
                               maturity_by_ud, row_cfg,
                               disable_correlation_bonus=disable_correlation_bonus)
    if use_campaigns:
        link_campaigns(incidents, row_cfg)
    for inc in incidents:
        inc.triage_lane = route(inc.risk, inc.confidence, row_cfg).lane

    return AblatedPipeline(feats, signals_by_day, incidents)


ROW_SPECS: list[tuple[str, str, dict]] = [
    ("rules_only_no_baselines",
     "Rules only, self/peer-baseline-gated rules forced off (fixed thresholds)",
     dict(use_baselines=False, use_ml=False, use_rules=True,
          disable_correlation_bonus=True, use_campaigns=False)),
    ("rules_only_with_baselines",
     "Rules only, self/peer baselines active",
     dict(use_baselines=True, use_ml=False, use_rules=True,
          disable_correlation_bonus=True, use_campaigns=False)),
    ("ml_only",
     "IsolationForest only, rules disabled",
     dict(use_baselines=True, use_ml=True, use_rules=False,
          disable_correlation_bonus=True, use_campaigns=False)),
    ("hybrid_no_correlation",
     "Rules + ML, correlation bonus disabled",
     dict(use_baselines=True, use_ml=True, use_rules=True,
          disable_correlation_bonus=True, use_campaigns=False)),
    ("hybrid_with_correlation",
     "+ correlation bonus",
     dict(use_baselines=True, use_ml=True, use_rules=True,
          disable_correlation_bonus=False, use_campaigns=False)),
    ("hybrid_with_campaigns",
     "+ campaign linking",
     dict(use_baselines=True, use_ml=True, use_rules=True,
          disable_correlation_bonus=False, use_campaigns=True)),
    ("full_system",
     "Deployed configuration (identical run to the row above)",
     dict(use_baselines=True, use_ml=True, use_rules=True,
          disable_correlation_bonus=False, use_campaigns=True)),
]


def run_ablation(events, org, ground_truth, dataset_profile: dict,
                 base_cfg: Config | None = None) -> list[AblationRow]:
    """`events`/`org` are already-loaded frames (from `engine.ingest.loader`),
    `ground_truth` is `engine.ingest.ground_truth.load_ground_truth`'s output -
    all real data, loaded once by the caller and reused across every row so
    an eight-run ablation study does not re-parse the corpus eight times."""
    cfg = base_cfg or load_config()
    insiders = build_insider_index(ground_truth)

    rows: list[AblationRow] = []
    for name, description, kwargs in ROW_SPECS:
        try:
            pipeline = _run_row(name, cfg, events, org, **kwargs)
            day_scores = build_day_scores(pipeline.features, pipeline.signals_by_day,
                                          pipeline.incidents, insiders, cfg)
            report = build_report(day_scores, pipeline.signals_by_day, insiders,
                                  cfg, dataset_profile, f"{cfg.version}:{name}")
            rows.append(AblationRow(name, description, report=report))
        except Exception as exc:  # noqa: BLE001 - a failed row is reported, never fatal
            rows.append(AblationRow(name, description, error=f"{type(exc).__name__}: {exc}"))
    return rows


def format_table(rows: list[AblationRow]) -> str:
    header = (f"{'row':<26}{'recall':>8}{'inc.prec':>10}{'auto.prec':>11}"
             f"{'pr_auc':>9}{'incid/day/1k':>13}")
    lines = [header, "-" * len(header)]
    for row in rows:
        if row.error:
            lines.append(f"{row.name:<26}  ERROR: {row.error}")
            continue
        r = row.report
        recall = r["insider_level"]["recall"]
        prec = r["incident_level"]["precision"]
        auto = r["incident_level"].get("auto_flag_precision")
        auc = r["user_day_level"]["pr_auc"]
        vol = r["incident_level"].get("incidents_per_day_per_1k_users")

        def fmt(v, spec=".2f"):
            return "" if v is None else format(v, spec)

        lines.append(
            f"{row.name:<26}{fmt(recall):>8}{fmt(prec):>10}{fmt(auto):>11}"
            f"{fmt(auc, '.3f'):>9}{fmt(vol):>13}"
        )
    return "\n".join(lines)


def ablation_notes(rows: list[AblationRow]) -> list[str]:
    """Checks the directional claims the product pitch makes against what was
    actually measured, and states plainly when a row contradicts them - see
    the module docstring's note on `hybrid_with_campaigns` in particular."""
    notes: list[str] = []
    by_name = {r.name: r for r in rows if r.report}

    no_corr, with_corr = by_name.get("hybrid_no_correlation"), by_name.get("hybrid_with_correlation")
    if no_corr and with_corr:
        p0 = no_corr.report["incident_level"]["precision"]
        p1 = with_corr.report["incident_level"]["precision"]
        r0 = no_corr.report["insider_level"]["recall"]
        r1 = with_corr.report["insider_level"]["recall"]
        if p0 is not None and p1 is not None:
            if p1 > p0:
                notes.append(f"Correlation bonus raised incident precision "
                            f"{p0:.2f} -> {p1:.2f}.")
            else:
                notes.append(f"CONTRADICTS PITCH: correlation bonus did not raise "
                            f"incident precision ({p0:.2f} -> {p1:.2f}). Reported as measured.")
        if r0 is not None and r1 is not None and abs(r1 - r0) > 0.05:
            notes.append(f"Correlation bonus moved recall by {r1 - r0:+.2f} "
                        f"(the pitch expects roughly constant recall here).")

    with_camp = by_name.get("hybrid_with_campaigns")
    if with_corr and with_camp:
        r1 = with_corr.report["per_scenario"].get("1", {}).get("recall")
        r1c = with_camp.report["per_scenario"].get("1", {}).get("recall")
        if r1 is not None and r1c is not None:
            if r1c > r1:
                notes.append(f"Campaign linking raised scenario-1 (slow-burn) recall "
                            f"{r1:.2f} -> {r1c:.2f}.")
            elif r1c == r1:
                notes.append(
                    "Campaign linking made no measurable difference to scenario-1 "
                    "recall in this run - expected under the current engine: "
                    "link_campaigns() annotates Incident.campaign_id and computes a "
                    "separate Campaign.peak_risk, but does not feed back into any "
                    "individual incident's risk, confidence, or triage lane, so "
                    "per-day flagging (what insider_recall reads) cannot change. "
                    "Campaign-level triage routing is not yet implemented.")
            else:
                notes.append(f"CONTRADICTS PITCH: campaign linking lowered scenario-1 "
                            f"recall ({r1:.2f} -> {r1c:.2f}). Reported as measured.")

    return notes
