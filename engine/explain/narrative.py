"""Deterministic three-layer narrative grammar - no LLM (ADR 0004).

Headline, summary, and detail bullets are assembled directly from stored
signal and incident fields. Every phrase comes from a rule's own `phrase`
field, rendered with real feature values at rule-evaluation time
(engine/detect/rules.py) - the narrative is a rendering of the evidence rows,
not an independent generation, so it cannot drift from the data and is
byte-identical across runs (docs section 7.1, FR-5.1/5.2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.core.config import Config
from engine.core.models import STAGE_NAMES, Signal
from engine.correlate.incident import Incident


@dataclass(frozen=True)
class Narrative:
    headline: str
    summary: str
    detail: tuple[str, ...]
    template_ids: tuple[str, ...]


def _top_signal(signals: list[Signal], deltas: dict[str, float] | None = None) -> Signal:
    """"The single most attributable signal" (docs section 7.1) - by
    counterfactual delta when available, matching the Detail layer's own
    ordering, so the headline never names a different signal than the one
    Detail ranks first."""
    if deltas:
        return max(signals, key=lambda s: (deltas.get(s.rule_id, s.contribution), s.rule_id))
    return max(signals, key=lambda s: (s.contribution, s.rule_id))


def _ordered_stage_names(signals: list[Signal]) -> list[str]:
    return [STAGE_NAMES[stage] for stage in sorted({s.stage for s in signals})]


def build_headline(incident: Incident, deltas: dict[str, float] | None = None) -> str:
    top = _top_signal(incident.signals, deltas)
    return (f"{top.phrase} — {incident.signal_count} correlated signals "
            f"across {incident.category_count} categories")


def baseline_clause(incident: Incident, feature_row: dict[str, Any] | None,
                    cfg: Config, deltas: dict[str, float] | None = None) -> str | None:
    """"File activity was N self-baseline / M peer-baseline standard
    deviations above normal" - grounded in the top signal's own underlying
    feature, read directly from the stored feature row (FR-5.2's "vs self
    and vs peers"). None when that data is not available (e.g. a binary-
    scale rule with no baselined feature, or no feature row supplied)."""
    if not feature_row:
        return None
    top = _top_signal(incident.signals, deltas)
    rule = next((r for r in cfg.rules if r["id"] == top.rule_id), None)
    feature = (rule.get("strength") or {}).get("feature") if rule else None
    if not feature:
        return None

    z_self = feature_row.get(f"{feature}__z_self")
    z_peer = feature_row.get(f"{feature}__z_peer")
    bits = []
    if z_self is not None and z_self == z_self:   # not NaN
        bits.append(f"{z_self:.1f} self-baseline standard deviations")
    if z_peer is not None and z_peer == z_peer:
        bits.append(f"{z_peer:.1f} peer-baseline standard deviations")
    if not bits:
        return None
    label = feature.replace("_", " ")
    return f"{label} ran {' and '.join(bits)} above normal."


def departure_context_clause(feature_row: dict[str, Any] | None) -> str | None:
    if not feature_row:
        return None
    days = feature_row.get("days_to_departure")
    if days is None or days != days:   # NaN or absent
        return None
    if days < 0:
        return "This activity occurred after the user's recorded departure."
    return f"The user's departure is recorded {days:.0f} days later."


def build_summary(incident: Incident, who: str, feature_row: dict[str, Any] | None,
                  cfg: Config, deltas: dict[str, float] | None = None) -> str:
    when = (f"acted between {incident.window_start:%H:%M} and "
            f"{incident.window_end:%H:%M} on {incident.window_start:%Y-%m-%d}")
    stage_names = _ordered_stage_names(incident.signals)
    if len(stage_names) >= 2:
        stage_clause = f", progressing from {stage_names[0]} through to {stage_names[-1]}"
    elif stage_names:
        stage_clause = f", showing {stage_names[0]} activity"
    else:
        stage_clause = ""

    sentences = [f"{who} {when}{stage_clause}."]
    peer = baseline_clause(incident, feature_row, cfg, deltas)
    if peer:
        sentences.append(peer)
    context = departure_context_clause(feature_row)
    if context:
        sentences.append(context)
    return " ".join(sentences)


def build_detail(incident: Incident, deltas: dict[str, float]) -> tuple[str, ...]:
    """One bullet per signal, ordered by counterfactual contribution
    (docs section 7.1's "Detail" layer)."""
    ordered = sorted(incident.signals,
                     key=lambda s: (deltas.get(s.rule_id, s.contribution), s.rule_id),
                     reverse=True)
    lines = []
    for s in ordered:
        delta = deltas.get(s.rule_id, s.contribution)
        lines.append(f"[{s.category.upper()} · +{delta:.1f} pts] {s.phrase}")
    return tuple(lines)


def build_narrative(incident: Incident, who: str, deltas: dict[str, float],
                    feature_row: dict[str, Any] | None, cfg: Config) -> Narrative:
    return Narrative(
        headline=build_headline(incident, deltas),
        summary=build_summary(incident, who, feature_row, cfg, deltas),
        detail=build_detail(incident, deltas),
        template_ids=("headline.v1", "summary.v1", "detail.v1"),
    )
