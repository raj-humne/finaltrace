"""Wires analyst-feedback learning into the real scoring model (Challenge 2,
spec E) — a thin wrapper around engine.detect.scoring.compute_risk, never a
parallel scorer. Every risk number this module returns is still exactly
`compute_risk`'s log-odds model; this module only decides what
`CorrelationInputs` and signal strengths to feed it, given this user's own
learned edge-weight and baseline-adjustment history.

Two independent adjustments, both scoped to a single user and both bounded:

1. Edge-weight multiplier (engine/feedback/edge_weights.py): this incident's
   correlation graph carries `stage_advances` and `proximity_factor` terms
   that are derived directly from graph edges (engine/correlate/graph.py and
   engine/correlate/incident.py's `_stage_advance_count`/`_proximity_factor`).
   `distinct_categories` is a property of the *signal set*, not of graph
   edges, so it is deliberately left unscaled - a learned edge dismissal
   narrows correlation strength, it does not silently make unrelated
   evidence categories disappear.

2. Baseline discount: a signal whose firing clause references a feature this
   user has a trusted, feedback-widened baseline for (`feedback_adjustment`
   on `BehavioralBaseline`) has its `strength` (and therefore
   `raw_points`/`contribution`) shrunk by that same fraction before
   saturation - "the same raw value is less anomalous now" is applied at the
   rule-strength level, the earliest point in the pipeline where a numeric
   feature value turns into evidence points.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from engine.core.config import Config
from engine.core.models import Signal
from engine.detect.scoring import CorrelationInputs, ScoreBreakdown, compute_risk


@dataclass(frozen=True)
class FeedbackAdjustment:
    """One explainability record (spec E.5's `feedback_adjustments` list)."""

    type: str          # "baseline" | "edge_weight"
    scope: str          # e.g. "user:u_014"
    effect: str
    feature: str | None = None
    edge: str | None = None
    multiplier: float | None = None


def _discount_signal(signal: Signal, discount: float) -> Signal:
    new_strength = max(0.0, signal.strength * (1 - discount))
    return replace(signal, strength=new_strength, contribution=signal.weight * new_strength)


def compute_feedback_aware_risk(
    signals: Sequence[Signal],
    anomaly_percentile: float | None,
    corr: CorrelationInputs,
    cfg: Config,
    *,
    user_id: str,
    edge_multiplier: float = 1.0,
    baseline_discount_by_feature: dict[str, float] | None = None,
) -> tuple[float, ScoreBreakdown, list[Signal], list[FeedbackAdjustment]]:
    """Real `compute_risk`, fed a user-scoped, feedback-adjusted signal set
    and correlation input. `edge_multiplier=1.0` and an empty
    `baseline_discount_by_feature` (the defaults) reproduce the exact
    unmodified score - a user or incident with no feedback history is
    provably unaffected by this module existing."""
    discounts = baseline_discount_by_feature or {}
    adjustments: list[FeedbackAdjustment] = []
    scope = f"user:{user_id}"

    adjusted_signals: list[Signal] = []
    for s in signals:
        clause_features = {c.get("feature") for c in (s.detail or {}).get("clauses", []) if c.get("feature")}
        matched = [f for f in clause_features if discounts.get(f, 0.0) > 0]
        discount = max((discounts[f] for f in matched), default=0.0)
        if discount > 0:
            adjusted_signals.append(_discount_signal(s, discount))
            adjustments.append(FeedbackAdjustment(
                type="baseline", scope=scope, feature=matched[0],
                effect="trusted false-positive feedback adjusted behavioral tolerance",
            ))
        else:
            adjusted_signals.append(s)

    scaled_corr = corr
    if edge_multiplier != 1.0 and not corr.over_dense:
        scaled_corr = CorrelationInputs(
            distinct_categories=corr.distinct_categories,
            stage_advances=corr.stage_advances * edge_multiplier,
            proximity_factor=corr.proximity_factor * edge_multiplier,
            over_dense=corr.over_dense,
        )
        adjustments.append(FeedbackAdjustment(
            type="edge_weight", scope=scope, multiplier=round(edge_multiplier, 4),
            effect="previously dismissed relationship",
        ))

    risk, breakdown, updated_signals = compute_risk(adjusted_signals, anomaly_percentile, scaled_corr, cfg)
    return risk, breakdown, updated_signals, adjustments
