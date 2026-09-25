"""Declarative rule evaluation over config/rules.yaml (ADR 0002).

A small interpreter over a closed operator set - no `eval`, no expression
language. An operator that does not exist is a feature request against this
module, never an escape hatch. `engine.core.config._validate` already rejects
a rule using anything outside this set at load time, so this module only
needs to implement exactly what that validator allows.
"""
from __future__ import annotations

import math
from datetime import date as date_type
from typing import Any

import pandas as pd

from engine.core.config import Config
from engine.core.models import Signal

# ------------------------------------------------------------------ clauses
def _feature_value(row: Any, feature: str, op: str) -> float | bool | None:
    if op == "z_self_gte":
        key = f"{feature}__z_self"
    elif op == "z_peer_gte":
        key = f"{feature}__z_peer"
    else:
        key = feature
    value = row.get(key) if isinstance(row, dict) else row[key] if key in row.index else None
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def _eval_clause(row: Any, clause: dict[str, Any]) -> bool:
    op = clause["op"]
    feature = clause.get("feature")

    if op in ("is_true", "is_false"):
        value = _feature_value(row, feature, op)
        if value is None:
            return False
        return bool(value) if op == "is_true" else not bool(value)

    value = _feature_value(row, feature, op)
    if value is None:
        return False

    target = clause.get("value")
    if op == "gte":
        return value >= target
    if op == "gt":
        return value > target
    if op == "lte":
        return value <= target
    if op == "lt":
        return value < target
    if op == "eq":
        return value == target
    if op == "neq":
        return value != target
    if op == "in":
        return value in target
    if op in ("z_self_gte", "z_peer_gte"):
        return value >= target
    raise ValueError(f"unsupported operator: {op}")   # unreachable if config validated


def rule_fires(row: Any, rule: dict[str, Any]) -> bool:
    """All clauses in `when` must hold (implicit AND), honouring warm-up."""
    if rule.get("requires_baseline", False):
        mature = row.get("baseline_mature") if isinstance(row, dict) else (
            row["baseline_mature"] if "baseline_mature" in row.index else True)
        if not bool(mature):
            return False
    return all(_eval_clause(row, clause) for clause in rule["when"])


# ------------------------------------------------------------------ strength
def _strength_value(row: Any, spec: dict[str, Any]) -> float:
    scale = spec.get("scale", "binary")
    if scale == "binary":
        return 1.0

    feature = spec["feature"]
    lo, hi = float(spec["lo"]), float(spec["hi"])
    raw = row.get(feature) if isinstance(row, dict) else (
        row[feature] if feature in row.index else None)
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return 0.0
    v = float(raw)

    if scale == "linear":
        frac = (v - lo) / (hi - lo) if hi > lo else 1.0
        return min(1.0, max(0.0, frac))

    if scale == "inverse_linear":
        frac = (v - lo) / (hi - lo) if hi > lo else 1.0
        return min(1.0, max(0.0, 1.0 - frac))

    if scale == "log":
        v = max(v, lo)
        if lo <= 0:
            lo = max(lo, 1e-9)
            v = max(v, lo)
        frac = (math.log(v) - math.log(lo)) / (math.log(hi) - math.log(lo))
        return min(1.0, max(0.0, frac))

    if scale == "step":
        steps = int(spec.get("steps", 4))
        frac = (v - lo) / (hi - lo) if hi > lo else 1.0
        frac = min(1.0, max(0.0, frac))
        return math.floor(frac * steps) / steps if steps > 0 else frac

    raise ValueError(f"unsupported strength scale: {scale}")   # unreachable if config validated


# ------------------------------------------------------------------ signal
def _evidence_event_ids(events_for_day: pd.DataFrame | None,
                        rule: dict[str, Any]) -> tuple[str, ...]:
    sources = (rule.get("evidence") or {}).get("sources") or []
    if not sources or events_for_day is None or events_for_day.empty:
        return ()
    matched = events_for_day[events_for_day["source"].isin(sources)]
    return tuple(sorted(matched["event_id"].tolist()))


def _render_phrase(row: Any, rule: dict[str, Any]) -> str:
    values = dict(row) if isinstance(row, dict) else row.to_dict()
    try:
        return rule["phrase"].format(**values)
    except (KeyError, ValueError):
        return rule["phrase"]


def build_signal(row: Any, rule: dict[str, Any],
                 events_for_day: pd.DataFrame | None = None) -> Signal:
    strength = _strength_value(row, rule.get("strength") or {"scale": "binary"})
    weight = float(rule["weight"])
    return Signal(
        rule_id=rule["id"],
        name=rule.get("name", rule["id"]),
        category=rule["category"],
        stage=int(rule["stage"]),
        strength=strength,
        weight=weight,
        contribution=weight * strength,   # placeholder; scoring applies saturation
        phrase=_render_phrase(row, rule),
        detail={"clauses": rule["when"]},
        evidence_event_ids=_evidence_event_ids(events_for_day, rule),
        references=tuple(rule.get("references", [])),
    )


def evaluate_user_day(row: Any, cfg: Config,
                      events_for_day: pd.DataFrame | None = None) -> list[Signal]:
    """Every rule that fires for one (user, date) feature row, in catalogue order."""
    return [build_signal(row, rule, events_for_day)
            for rule in cfg.rules if rule_fires(row, rule)]


def detect_signals(features: pd.DataFrame, events: pd.DataFrame,
                   cfg: Config) -> dict[tuple[str, date_type], list[Signal]]:
    """Evaluate every rule against every (user, date) row in `features`.

    Sorted iteration over sorted keys (NFR-5): the same input and config
    always visits user-days in the same order.
    """
    out: dict[tuple[str, date_type], list[Signal]] = {}
    if features.empty:
        return out

    events_by_day: dict[tuple[str, date_type], pd.DataFrame] = {}
    if events is not None and not events.empty:
        for key, grp in events.groupby(["user_id", "date"], sort=False, observed=True):
            user_id, ts = key
            events_by_day[(user_id, pd.Timestamp(ts).date())] = grp

    ordered = features.sort_values(["user_id", "date"], kind="stable")
    for _, row in ordered.iterrows():
        user_id = row["user_id"]
        day = pd.Timestamp(row["date"]).date()
        day_events = events_by_day.get((user_id, day))
        out[(user_id, day)] = evaluate_user_day(row, cfg, day_events)
    return out


def signals_to_frame(signals_by_day: dict[tuple[str, date_type], list[Signal]]
                     ) -> pd.DataFrame:
    """Flatten to the `signals` table shape (docs/03-DATA-MODEL section 5)."""
    rows = []
    for (user_id, day), signals in sorted(signals_by_day.items()):
        for s in signals:
            rows.append({
                "user_id": user_id, "event_date": day, "rule_id": s.rule_id,
                "category": s.category, "killchain_stage": s.stage,
                "strength": s.strength, "weight": s.weight,
                "contribution": s.contribution, "phrase": s.phrase,
                "evidence_event_ids": list(s.evidence_event_ids),
            })
    return pd.DataFrame(rows)
