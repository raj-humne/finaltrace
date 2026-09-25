"""Canonical data models.

Everything from every source normalises into `Event`. This is what makes the
adapter layer possible (docs/08-ADAPTER-LAYER.md) and what keeps the engine
independent of any particular vendor's log schema.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any

SOURCES = ("logon", "device", "file", "http", "email")

CATEGORIES = ("context", "access", "staging", "collection", "exfil", "evasion")


class Stage(IntEnum):
    CONTEXT = 0
    RECON = 1
    STAGING = 2
    COLLECTION = 3
    EXFILTRATION = 4
    EVASION = 5


STAGE_NAMES = {
    0: "context",
    1: "reconnaissance",
    2: "staging",
    3: "collection",
    4: "exfiltration",
    5: "evasion",
}


def make_event_id(source: str, raw_id: str, user_id: str, ts: datetime) -> str:
    """Content-addressed id: re-ingesting the same record is a no-op (FR-1.4)."""
    payload = f"{source}|{raw_id}|{user_id}|{ts.isoformat()}"
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    user_id: str
    ts: datetime
    source: str
    action: str
    pc_id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def date(self):
        return self.ts.date()

    @property
    def minute_of_day(self) -> int:
        return self.ts.hour * 60 + self.ts.minute


@dataclass(frozen=True, slots=True)
class Signal:
    """One rule firing on one user-day, with the evidence that justifies it."""

    rule_id: str
    name: str
    category: str
    stage: int
    strength: float          # 0..1, how strongly the rule fired
    weight: float            # log-odds evidence points at strength 1.0
    contribution: float      # post-saturation points actually applied
    phrase: str              # rendered narrative clause
    detail: dict[str, Any] = field(default_factory=dict)
    evidence_event_ids: tuple[str, ...] = ()
    references: tuple[str, ...] = ()

    @property
    def raw_points(self) -> float:
        return self.weight * self.strength


@dataclass
class ScoreBreakdown:
    prior_logit: float
    rule_points: float
    ml_points: float
    correlation_points: float
    total_logit: float
    tau: float

    def as_dict(self) -> dict[str, float]:
        return {
            "prior_logit": round(self.prior_logit, 4),
            "rule_points": round(self.rule_points, 4),
            "ml_points": round(self.ml_points, 4),
            "correlation_points": round(self.correlation_points, 4),
            "total_logit": round(self.total_logit, 4),
            "tau": self.tau,
        }


@dataclass
class ConfidenceTerms:
    agreement: float
    diversity: float
    completeness: float
    maturity: float
    caps_applied: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "agreement": round(self.agreement, 3),
            "diversity": round(self.diversity, 3),
            "completeness": round(self.completeness, 3),
            "maturity": round(self.maturity, 3),
            "caps_applied": list(self.caps_applied),
        }


@dataclass
class UserDayScore:
    user_id: str
    date: Any
    risk: float
    confidence: float
    signals: list[Signal]
    breakdown: ScoreBreakdown
    confidence_terms: ConfidenceTerms
    anomaly_percentile: float | None = None
    config_version: str = ""

    @property
    def categories(self) -> set[str]:
        return {s.category for s in self.signals}

    @property
    def max_stage(self) -> int:
        return max((s.stage for s in self.signals), default=0)
