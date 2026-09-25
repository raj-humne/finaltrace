"""Tests for engine/route/triage.py.

FR-6.2 is the safety property of the whole product: high risk with low
confidence must never route to AUTO_FLAG. That is tested here explicitly,
both as a fixed example and as a Hypothesis property over the entire
high-risk/low-confidence region - not just the one cell the config's own
load-time validator already checks.
"""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from engine.core.config import load_config
from engine.route.triage import LANES, confidence_band, risk_band, route

CFG = load_config()


def test_high_risk_low_confidence_routes_to_review_never_auto_flag():
    decision = route(risk=95.0, confidence=0.10, cfg=CFG)
    assert decision.lane != "AUTO_FLAG"
    assert decision.lane == "ANALYST_REVIEW"


@given(risk=st.floats(min_value=CFG.triage["risk_bands"]["high"], max_value=100.0),
      confidence=st.floats(min_value=0.0,
                           max_value=CFG.triage["confidence_bands"]["low"] - 1e-9))
def test_high_risk_low_confidence_never_auto_flags_property(risk, confidence):
    decision = route(risk=risk, confidence=confidence, cfg=CFG)
    assert decision.lane != "AUTO_FLAG"


def test_high_risk_high_confidence_can_auto_flag():
    decision = route(risk=95.0, confidence=0.90, cfg=CFG)
    assert decision.lane == "AUTO_FLAG"


def test_low_risk_low_confidence_is_suppressed():
    decision = route(risk=5.0, confidence=0.05, cfg=CFG)
    assert decision.lane == "SUPPRESSED"


# ---------------------------------------------------------------- band edges
def test_risk_band_boundaries_match_config():
    bands = CFG.triage["risk_bands"]
    assert risk_band(bands["low"] - 0.01, CFG) == "low"
    assert risk_band(bands["low"], CFG) == "mid"
    assert risk_band(bands["high"] - 0.01, CFG) == "mid"
    assert risk_band(bands["high"], CFG) == "high"


def test_confidence_band_boundaries_match_config():
    bands = CFG.triage["confidence_bands"]
    assert confidence_band(bands["low"] - 0.001, CFG) == "low"
    assert confidence_band(bands["low"], CFG) == "mid"
    assert confidence_band(bands["high"] - 0.001, CFG) == "mid"
    assert confidence_band(bands["high"], CFG) == "high"


# -------------------------------------------------------------- suppression
def test_active_suppression_demotes_one_lane_step():
    baseline = route(risk=95.0, confidence=0.90, cfg=CFG)
    assert baseline.lane == "AUTO_FLAG"

    suppressed = route(risk=95.0, confidence=0.90, cfg=CFG, active_suppression_id="sup-1")
    assert suppressed.lane == "ANALYST_REVIEW"
    assert suppressed.demoted is True
    assert suppressed.suppression_id == "sup-1"


def test_suppression_never_pushes_past_suppressed_floor():
    decision = route(risk=5.0, confidence=0.05, cfg=CFG, active_suppression_id="sup-2")
    assert decision.lane == "SUPPRESSED"


def test_lanes_ordering_matches_severity():
    assert LANES == ("AUTO_FLAG", "ANALYST_REVIEW", "MONITOR", "SUPPRESSED")


def test_no_active_suppression_never_demotes():
    decision = route(risk=95.0, confidence=0.90, cfg=CFG)
    assert decision.demoted is False
    assert decision.suppression_id is None
