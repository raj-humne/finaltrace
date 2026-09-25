"""Risk x confidence triage routing (docs/04-DETECTION-ENGINE.md section 4.4).

FR-6.2 is the safety property of the whole product: high risk with low
confidence must never auto-flag. `engine.core.config._validate` already
refuses to start the whole engine if the configured matrix violates this -
this module just reads the matrix, plus the one allowed override: an active
suppression demotes a lane by exactly one step, never silences it outright.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.core.config import Config

# Most severe first - demotion moves one step toward the end, and never past it.
LANES = ("AUTO_FLAG", "ANALYST_REVIEW", "MONITOR", "SUPPRESSED")


@dataclass(frozen=True)
class TriageDecision:
    lane: str
    risk_band: str
    confidence_band: str
    suppression_id: str | None = None
    demoted: bool = False


def risk_band(risk: float, cfg: Config) -> str:
    bands = cfg.triage["risk_bands"]
    if risk < bands["low"]:
        return "low"
    if risk < bands["high"]:
        return "mid"
    return "high"


def confidence_band(confidence: float, cfg: Config) -> str:
    bands = cfg.triage["confidence_bands"]
    if confidence < bands["low"]:
        return "low"
    if confidence < bands["high"]:
        return "mid"
    return "high"


def _demote(lane: str) -> str:
    idx = LANES.index(lane)
    return LANES[min(idx + 1, len(LANES) - 1)]


def route(risk: float, confidence: float, cfg: Config,
         active_suppression_id: str | None = None) -> TriageDecision:
    """FR-6.1: route onto the (risk, confidence) plane. FR-6.4's suppression
    demotion is applied here, never as a silent override - `demoted` and
    `suppression_id` are always reported alongside the resulting lane."""
    rb = risk_band(risk, cfg)
    cb = confidence_band(confidence, cfg)
    lane = cfg.triage["matrix"][rb][cb]

    demoted = False
    if active_suppression_id:
        lane = _demote(lane)
        demoted = True

    return TriageDecision(lane=lane, risk_band=rb, confidence_band=cb,
                          suppression_id=active_suppression_id, demoted=demoted)
