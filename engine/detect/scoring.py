"""Log-odds additive scoring model (docs/04-DETECTION-ENGINE.md section 4,
ADR 0003).

Three mechanisms a naive weighted sum lacks: per-category geometric
saturation (kills redundancy stacking), a hard-capped ML contribution (the
black box can support a case but never carry one), and a correlation bonus
that only rewards cross-category, time-ordered evidence. Confidence is
computed independently of risk (ADR 0001) from evidence quality alone.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Sequence

from engine.core.config import Config
from engine.core.models import ConfidenceTerms, ScoreBreakdown, Signal


@dataclass(frozen=True)
class CorrelationInputs:
    """Pre-computed by engine/correlate (graph.py / incident.py) from the
    actual event graph - scoring.py has no event-level knowledge of its own.
    A lone user-day with no multi-event incident scores with all of these at
    their default zero, which correctly yields no correlation bonus."""
    distinct_categories: int = 0
    stage_advances: int = 0
    proximity_factor: float = 0.0
    over_dense: bool = False


def _is_missing(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _sigmoid(x: float) -> float:
    # Numerically stable for large |x| in either direction.
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


# --------------------------------------------------------------- step 1: rules
def saturate_signals(signals: Sequence[Signal], delta: float) -> tuple[float, list[Signal]]:
    """Within each category, sort by raw contribution descending and apply
    geometric decay (docs/04 section 4.2 step 1). A category is capped at
    under `2 * w_max` structurally - this is what kills redundancy stacking
    rather than hoping rules are independent (ADR 0003).

    Returns the total rule-evidence points and the signals with
    `contribution` set to the points actually applied post-saturation, which
    is what engine/explain reads for attribution and narrative ordering.
    """
    by_category: dict[str, list[Signal]] = {}
    for s in signals:
        by_category.setdefault(s.category, []).append(s)

    total = 0.0
    updated: list[Signal] = []
    for category in sorted(by_category):
        ordered = sorted(by_category[category], key=lambda s: s.raw_points, reverse=True)
        for i, s in enumerate(ordered):
            points = (delta ** i) * s.raw_points
            total += points
            updated.append(replace(s, contribution=points))
    return total, updated


# ----------------------------------------------------------------- step 2: ml
def ml_contribution(anomaly_percentile: float | None, cfg: Config) -> float:
    """Tail function: only genuine outliers contribute, and the contribution
    is hard-capped at `ml_weight` regardless of how extreme the percentile."""
    if _is_missing(anomaly_percentile):
        return 0.0
    p0 = cfg.scoring["ml_percentile_floor"]
    denom = 1.0 - p0
    phi = (anomaly_percentile - p0) / denom if denom > 0 else 0.0
    phi = min(1.0, max(0.0, phi))
    return cfg.scoring["ml_weight"] * phi


# --------------------------------------------------------- step 3: correlation
def correlation_bonus(corr: CorrelationInputs, cfg: Config) -> float:
    """Only cross-category, ordered evidence is rewarded (FR-4.5). Zeroed
    when the component is `over_dense` - a day where everything connects
    carries no correlation information (docs/04 section 6.3)."""
    if corr.over_dense or corr.distinct_categories <= 1:
        return 0.0
    b = cfg.corr_bonus
    c_term = b["diversity_weight"] * (corr.distinct_categories - 1)
    a_term = b["chain_weight"] * corr.stage_advances
    p_term = b["proximity_weight"] * corr.proximity_factor
    return c_term + a_term + p_term


# ------------------------------------------------------- step 4: combine & squash
def compute_risk(signals: Sequence[Signal], anomaly_percentile: float | None,
                 corr: CorrelationInputs, cfg: Config
                 ) -> tuple[float, ScoreBreakdown, list[Signal]]:
    """The full log-odds model: L = L0 + rule_points + ml_points + corr_points,
    risk = 100 * sigmoid(L / tau)."""
    s = cfg.scoring
    rule_points, updated_signals = saturate_signals(signals, s["category_decay"])
    ml_points = ml_contribution(anomaly_percentile, cfg)
    corr_points = correlation_bonus(corr, cfg)

    total_logit = s["prior_logit"] + rule_points + ml_points + corr_points
    risk = 100.0 * _sigmoid(total_logit / s["tau"])

    breakdown = ScoreBreakdown(
        prior_logit=s["prior_logit"], rule_points=rule_points, ml_points=ml_points,
        correlation_points=corr_points, total_logit=total_logit, tau=s["tau"],
    )
    return risk, breakdown, updated_signals


# ------------------------------------------------------------------ confidence
def compute_confidence(signals: Sequence[Signal], anomaly_percentile: float | None,
                       data_completeness: float, baseline_maturity: float,
                       cfg: Config) -> tuple[float, ConfidenceTerms]:
    """Independent of risk (ADR 0001). Two hard caps exist to protect the
    monitored person: thin evidence or an immature baseline can never produce
    a confidently-stated score, whatever the risk magnitude is."""
    c = cfg.confidence
    has_rules = len(signals) > 0
    has_ml = ml_contribution(anomaly_percentile, cfg) > 0

    if has_rules and has_ml:
        agreement = c["agreement_both"]
    elif has_rules:
        agreement = c["agreement_rules_only"]
    elif has_ml:
        agreement = c["agreement_ml_only"]
    else:
        agreement = 0.0

    categories = {s.category for s in signals}
    diversity = min(1.0, len(categories) / c["diversity_target_categories"])

    confidence = (
        c["agreement_weight"] * agreement
        + c["diversity_weight"] * diversity
        + c["completeness_weight"] * data_completeness
        + c["maturity_weight"] * baseline_maturity
    )

    caps_applied: list[str] = []
    if baseline_maturity < 0.5:
        confidence = min(confidence, c["cap_immature_baseline"])
        caps_applied.append("immature_baseline")
    if len(signals) == 1:
        confidence = min(confidence, c["cap_single_signal"])
        caps_applied.append("single_signal")

    terms = ConfidenceTerms(agreement=agreement, diversity=diversity,
                            completeness=data_completeness, maturity=baseline_maturity,
                            caps_applied=caps_applied)
    return confidence, terms
