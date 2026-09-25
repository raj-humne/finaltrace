"""Counterfactual attribution (docs/04-DETECTION-ENGINE.md sections 7.2-7.3).

For each signal, re-run the scoring function with that signal removed and
record the delta. This is not a linear share-out: because of category
saturation and the correlation bonus, removing a signal can change the decay
position of its siblings and drop the category count, so deltas are
genuinely non-additive and typically sum to more than the total (ADR 0003).
That is correct behaviour, not a bug.
"""
from __future__ import annotations

from engine.core.config import Config
from engine.core.models import Signal
from engine.detect.scoring import CorrelationInputs, compute_risk


def _corr_for_subset(signals: list[Signal], base_corr: CorrelationInputs) -> CorrelationInputs:
    """Recomputes the category-diversity term exactly - cheap, and it is the
    specific effect ADR 0003 calls out ("removing a signal can... drop the
    category count"). The chain/proximity terms are held at the full
    incident's values: recomputing them exactly would require re-deriving
    stage-advance edges and event timestamps from the graph, which Signal
    objects alone do not carry. Documented approximation, not silent error.
    """
    return CorrelationInputs(
        distinct_categories=len({s.category for s in signals}),
        stage_advances=base_corr.stage_advances,
        proximity_factor=base_corr.proximity_factor,
        over_dense=base_corr.over_dense,
    )


def counterfactual_deltas(signals: list[Signal], anomaly_percentile: float | None,
                          corr: CorrelationInputs, cfg: Config) -> dict[str, float]:
    """`delta(s) = risk(S) - risk(S \\ {s})` for every signal in S."""
    full_risk, _, _ = compute_risk(signals, anomaly_percentile, corr, cfg)
    deltas: dict[str, float] = {}
    for i, s in enumerate(signals):
        without = signals[:i] + signals[i + 1:]
        risk_without, _, _ = compute_risk(
            without, anomaly_percentile, _corr_for_subset(without, corr), cfg)
        deltas[s.rule_id] = full_risk - risk_without
    return deltas


def minimal_sufficient_set(signals: list[Signal], anomaly_percentile: float | None,
                           corr: CorrelationInputs, cfg: Config, threshold: float,
                           deltas: dict[str, float] | None = None) -> list[Signal]:
    """Greedily drop the lowest-contribution signals while the score stays at
    or above `threshold` (docs section 7.3): the smallest evidence subset
    that still clears the alert bar on its own."""
    if deltas is None:
        deltas = counterfactual_deltas(signals, anomaly_percentile, corr, cfg)

    kept = sorted(signals, key=lambda s: deltas.get(s.rule_id, s.contribution))
    for s in list(kept):   # weakest first
        candidate = [x for x in kept if x.rule_id != s.rule_id]
        if not candidate:
            break
        risk_candidate, _, _ = compute_risk(
            candidate, anomaly_percentile, _corr_for_subset(candidate, corr), cfg)
        if risk_candidate >= threshold:
            kept = candidate
    return kept
