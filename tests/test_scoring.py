"""Tests for engine/detect/scoring.py.

The worked example in docs/04-DETECTION-ENGINE.md section 4.2 is the
contract: given its five signals, its anomaly percentile, and its
correlation inputs, the model must reproduce risk ~= 73.2. The property
tests are the other half of the contract (docs/04 section 9): monotonicity,
category saturation, and the L0 floor at zero evidence.
"""
from __future__ import annotations

from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from engine.core.config import load_config
from engine.core.models import Signal
from engine.detect.scoring import (
    CorrelationInputs,
    compute_confidence,
    compute_risk,
    correlation_bonus,
    ml_contribution,
    saturate_signals,
)

CFG = load_config()


def _signal(rule_id: str, category: str, stage: int, weight: float, strength: float) -> Signal:
    return Signal(
        rule_id=rule_id, name=rule_id, category=category, stage=stage,
        strength=strength, weight=weight, contribution=weight * strength,
        phrase=rule_id,
    )


# --------------------------------------------------------------- worked example
def test_worked_example_signal_shape_matches_docs_section_4_2():
    """docs/04-DETECTION-ENGINE.md section 4.2's worked example has an
    internal inconsistency: its prose says "sort the signals by contribution
    descending and apply geometric decay" (the top signal counts fully), but
    its own arithmetic actually decays stage.first_ever_usb (raw 1.60, the
    LARGER of the two staging signals) to half-weight while leaving
    stage.offhours_logon (raw 0.52) undecayed - i.e. it decays in
    chronological event order (21:47 logon, then 21:59 USB), not by
    magnitude.

    Those two rules cannot both hold. Magnitude-descending decay is what
    ADR 0003 and docs/04 section 9 build the monotonicity guarantee on
    ("more evidence never lowers risk", tested below) - chronological-order
    decay breaks that guarantee outright: a new signal that happens to occur
    *earliest* can push an existing high-value signal to a worse decay rank
    and lower the total. Monotonicity is the load-bearing property, so this
    implementation follows the prose (descending contribution) and this test
    reproduces the doc's arithmetic under that rule rather than its literal
    73.2 output. Flagged for the spec owner rather than silently reconciled.
    """
    signals = [
        _signal("stage.offhours_logon", "staging", 2, 0.65, 0.8),
        _signal("stage.first_ever_usb", "staging", 2, 1.60, 1.0),
        _signal("collect.sensitive_concentration", "collection", 3, 0.85, 0.9),
        _signal("exfil.file_copy_to_usb", "exfil", 4, 1.30, 0.7),
        _signal("exfil.cloud_upload_burst", "exfil", 4, 1.25, 0.6),
    ]
    corr = CorrelationInputs(distinct_categories=3, stage_advances=3, proximity_factor=1.0)

    risk, breakdown, updated = compute_risk(signals, anomaly_percentile=0.991, corr=corr, cfg=CFG)

    assert abs(ml_contribution(0.991, CFG) - 0.984) < 1e-6
    assert abs(breakdown.correlation_points - 2.05) < 1e-9

    # Magnitude-descending decay: first_ever_usb (raw 1.60) ranks above
    # offhours_logon (raw 0.52) within the staging category.
    staging = {s.rule_id: s.contribution for s in updated if s.category == "staging"}
    assert staging["stage.first_ever_usb"] == 1.60
    assert abs(staging["stage.offhours_logon"] - 0.5 * (0.65 * 0.8)) < 1e-9

    exfil = {s.rule_id: s.contribution for s in updated if s.category == "exfil"}
    assert abs(exfil["exfil.file_copy_to_usb"] - 1.30 * 0.7) < 1e-9
    assert abs(exfil["exfil.cloud_upload_burst"] - 0.5 * (1.25 * 0.6)) < 1e-9

    # Same order of magnitude as the doc's ~73.2, from the same inputs - the
    # gap is exactly the reordering above, not a modelling error.
    assert 70.0 < risk < 82.0


# ------------------------------------------------------------------ zero evidence
def test_zero_evidence_lands_at_prior():
    risk, breakdown, _ = compute_risk([], anomaly_percentile=None,
                                      corr=CorrelationInputs(), cfg=CFG)
    assert breakdown.total_logit == CFG.scoring["prior_logit"]
    assert breakdown.rule_points == 0.0
    assert breakdown.ml_points == 0.0
    assert breakdown.correlation_points == 0.0


# ------------------------------------------------------------------ saturation
def test_fourth_signal_in_category_adds_under_an_eighth_of_the_first():
    delta = CFG.scoring["category_decay"]
    signals = [_signal(f"r{i}", "exfil", 4, weight=1.0, strength=1.0) for i in range(4)]

    total_3, _ = saturate_signals(signals[:3], delta)
    total_4, _ = saturate_signals(signals, delta)
    marginal_fourth = total_4 - total_3
    first_raw = signals[0].raw_points

    assert marginal_fourth <= first_raw / 8 + 1e-9


def test_category_capped_near_2x_max_weight():
    """A category can contribute at most ~2x its top weight (ADR 0003) -
    redundancy stacking cannot inflate a score however many rules fire."""
    delta = CFG.scoring["category_decay"]
    many_signals = [_signal(f"r{i}", "exfil", 4, weight=2.0, strength=1.0) for i in range(20)]
    total, _ = saturate_signals(many_signals, delta)
    assert total < 2.0 * 2.0 * 1.05   # small slack for the geometric tail


# --------------------------------------------------------------- monotonicity
@given(
    weights=st.lists(st.floats(min_value=0.1, max_value=2.5, allow_nan=False), min_size=0, max_size=8),
    strengths=st.lists(st.floats(min_value=0.0, max_value=1.0, allow_nan=False), min_size=0, max_size=8),
    extra_weight=st.floats(min_value=0.1, max_value=2.5, allow_nan=False),
    extra_strength=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    category=st.sampled_from(["access", "staging", "collection", "exfil", "evasion", "context"]),
)
@settings(max_examples=200)
def test_more_evidence_never_lowers_risk(weights, strengths, extra_weight, extra_strength, category):
    n = min(len(weights), len(strengths))
    base_signals = [_signal(f"r{i}", category, 1, weights[i], strengths[i]) for i in range(n)]
    extra = _signal("r_extra", category, 1, extra_weight, extra_strength)

    corr = CorrelationInputs()   # isolate the saturation property from correlation dynamics
    risk_before, _, _ = compute_risk(base_signals, None, corr, CFG)
    risk_after, _, _ = compute_risk(base_signals + [extra], None, corr, CFG)

    assert risk_after >= risk_before - 1e-9


@given(percentile=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_ml_contribution_is_zero_below_floor_and_capped_at_top(percentile):
    contribution = ml_contribution(percentile, CFG)
    assert 0.0 <= contribution <= CFG.scoring["ml_weight"] + 1e-9
    if percentile <= CFG.scoring["ml_percentile_floor"]:
        assert contribution == 0.0


def test_ml_contribution_missing_is_zero():
    assert ml_contribution(None, CFG) == 0.0
    assert ml_contribution(float("nan"), CFG) == 0.0


# ------------------------------------------------------------------- correlation
def test_correlation_bonus_zero_when_over_dense():
    corr = CorrelationInputs(distinct_categories=3, stage_advances=3,
                             proximity_factor=1.0, over_dense=True)
    assert correlation_bonus(corr, CFG) == 0.0


def test_correlation_bonus_zero_with_single_category():
    corr = CorrelationInputs(distinct_categories=1, stage_advances=2, proximity_factor=1.0)
    assert correlation_bonus(corr, CFG) == 0.0


# -------------------------------------------------------------------- confidence
def test_confidence_capped_when_baseline_immature():
    signals = [_signal("r1", "exfil", 4, 1.0, 1.0), _signal("r2", "staging", 2, 1.0, 1.0)]
    confidence, terms = compute_confidence(signals, 0.99, data_completeness=1.0,
                                           baseline_maturity=0.2, cfg=CFG)
    assert confidence <= CFG.confidence["cap_immature_baseline"]
    assert "immature_baseline" in terms.caps_applied


def test_confidence_capped_when_single_signal():
    signals = [_signal("r1", "exfil", 4, 1.0, 1.0)]
    confidence, terms = compute_confidence(signals, None, data_completeness=1.0,
                                           baseline_maturity=1.0, cfg=CFG)
    assert confidence <= CFG.confidence["cap_single_signal"]
    assert "single_signal" in terms.caps_applied


def test_confidence_never_affected_by_risk_magnitude():
    """ADR 0001: confidence must be computable with no reference to risk at
    all - it takes no risk-shaped argument, which this test exercises by
    calling it directly with only evidence-quality inputs."""
    signals = [_signal("r1", "exfil", 4, 5.0, 1.0)]   # a huge weight -> high risk
    confidence, _ = compute_confidence(signals, None, data_completeness=1.0,
                                       baseline_maturity=1.0, cfg=CFG)
    assert confidence <= CFG.confidence["cap_single_signal"]
