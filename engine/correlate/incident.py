"""Connected components -> incidents, plus campaign linking (docs/04-
DETECTION-ENGINE.md sections 6.3-6.4).

An incident's risk and confidence are recomputed over *its own* signal set,
not the whole user-day (docs section 6.3 point 5) - a component is the unit
of evidence, and two unrelated signals on the same day that never connect
must not share a score.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date as date_type

import networkx as nx
import pandas as pd

from engine.core.config import Config
from engine.core.models import ConfidenceTerms, ScoreBreakdown, Signal
from engine.correlate.graph import EventGraph
from engine.detect.scoring import CorrelationInputs, compute_confidence, compute_risk


@dataclass
class Incident:
    incident_id: str
    user_id: str
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    event_ids: tuple[str, ...]
    signals: list[Signal]
    categories: tuple[str, ...]
    stages: tuple[int, ...]
    event_count: int
    signal_count: int
    category_count: int
    over_dense: bool
    risk: float
    confidence: float
    breakdown: ScoreBreakdown
    confidence_terms: ConfidenceTerms
    campaign_id: str | None = None


@dataclass
class Campaign:
    campaign_id: str
    user_id: str
    first_seen: date_type
    last_seen: date_type
    incident_ids: tuple[str, ...]
    max_stage: int
    peak_risk: float
    stage_progression: tuple[int, ...]


def _proximity_factor(timestamps: list[pd.Timestamp], cfg: Config) -> float:
    """1.0 when signal events cluster tightly, decaying to 0 by
    `proximity_zero_min` (docs section 4.2 step 3)."""
    if len(timestamps) < 2:
        return 0.0
    ts = sorted(timestamps)
    gaps_min = sorted((ts[i + 1] - ts[i]).total_seconds() / 60.0
                      for i in range(len(ts) - 1))
    median_gap = gaps_min[len(gaps_min) // 2]
    full = cfg.corr_bonus["proximity_full_min"]
    zero = cfg.corr_bonus["proximity_zero_min"]
    if median_gap <= full:
        return 1.0
    if median_gap >= zero:
        return 0.0
    return 1.0 - (median_gap - full) / (zero - full)


def _stage_advance_count(g: nx.Graph, component: set[str]) -> int:
    return sum(1 for a, b, d in g.edges(component, data=True)
              if d.get("type") == "stage_advance" and a in component and b in component)


def build_incidents(
    events: pd.DataFrame, event_graph: EventGraph,
    anomaly_by_user_date: dict[tuple[str, date_type], float],
    completeness_by_user_date: dict[tuple[str, date_type], float],
    maturity_by_user_date: dict[tuple[str, date_type], float],
    cfg: Config,
) -> list[Incident]:
    g = event_graph.graph
    min_events = cfg.correlation["min_events_per_incident"]
    max_component = cfg.correlation["max_component_events"]

    node_ts = nx.get_node_attributes(g, "ts")
    node_user = nx.get_node_attributes(g, "user_id")
    node_is_signal = nx.get_node_attributes(g, "is_signal")

    raw_incidents = []
    for component in nx.connected_components(g):
        if len(component) < min_events:
            continue
        signal_nodes = [eid for eid in component if node_is_signal.get(eid)]
        if not signal_nodes:
            continue

        signals: dict[str, Signal] = {}
        for eid in signal_nodes:
            for s in event_graph.event_to_signals.get(eid, []):
                signals.setdefault(s.rule_id, s)
        signal_list = list(signals.values())
        if not signal_list:
            continue

        over_dense = len(component) > max_component
        ordered_nodes = sorted(component, key=lambda e: node_ts[e])
        window_start = node_ts[ordered_nodes[0]]
        window_end = node_ts[ordered_nodes[-1]]

        user_counts: dict[str, int] = {}
        for eid in component:
            user_counts[node_user[eid]] = user_counts.get(node_user[eid], 0) + 1
        primary_user = max(sorted(user_counts), key=lambda u: user_counts[u])

        categories = sorted({s.category for s in signal_list})
        stages = sorted({s.stage for s in signal_list})

        corr = CorrelationInputs(
            distinct_categories=len(categories),
            stage_advances=0 if over_dense else _stage_advance_count(g, component),
            proximity_factor=0.0 if over_dense else _proximity_factor(
                [node_ts[e] for e in signal_nodes], cfg),
            over_dense=over_dense,
        )

        primary_date = window_start.date()
        anomaly_pctl = anomaly_by_user_date.get((primary_user, primary_date))
        completeness = completeness_by_user_date.get((primary_user, primary_date), 1.0)
        maturity = maturity_by_user_date.get((primary_user, primary_date), 0.0)

        risk, breakdown, updated_signals = compute_risk(signal_list, anomaly_pctl, corr, cfg)
        confidence, confidence_terms = compute_confidence(
            signal_list, anomaly_pctl, completeness, maturity, cfg)

        raw_incidents.append(Incident(
            incident_id="",   # assigned below, once sorted (NFR-5 determinism)
            user_id=primary_user, window_start=window_start, window_end=window_end,
            event_ids=tuple(sorted(component)), signals=updated_signals,
            categories=tuple(categories), stages=tuple(stages),
            event_count=len(component), signal_count=len(signal_list),
            category_count=len(categories), over_dense=over_dense,
            risk=risk, confidence=confidence, breakdown=breakdown,
            confidence_terms=confidence_terms,
        ))

    raw_incidents.sort(key=lambda inc: (inc.user_id, inc.window_start))
    seq: dict[tuple[str, date_type], int] = {}
    finished = []
    for inc in raw_incidents:
        key = (inc.user_id, inc.window_start.date())
        seq[key] = seq.get(key, 0) + 1
        incident_id = f"INC-{inc.window_start:%Y%m%d}-{inc.user_id}-{seq[key]:02d}"
        finished.append(_replace_id(inc, incident_id))
    return finished


def _replace_id(inc: Incident, incident_id: str) -> Incident:
    inc.incident_id = incident_id
    return inc


# ------------------------------------------------------------------ campaigns
def link_campaigns(incidents: list[Incident], cfg: Config) -> list[Campaign]:
    """Slow-burn detector (docs section 6.4): incidents for the same user
    within `span_days` are linked when the kill chain advances. This is what
    catches an insider who ramps over weeks with no single alarming day."""
    span = pd.Timedelta(days=cfg.correlation["campaign"]["span_days"])
    bonus = cfg.correlation["campaign"]["per_incident_logit_bonus"]
    tau = cfg.scoring["tau"]

    campaigns: list[Campaign] = []
    by_user: dict[str, list[Incident]] = {}
    for inc in incidents:
        by_user.setdefault(inc.user_id, []).append(inc)

    for user in sorted(by_user):
        user_incidents = sorted(by_user[user], key=lambda i: i.window_start)
        n = len(user_incidents)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(n):
            for j in range(i + 1, n):
                gap = user_incidents[j].window_start - user_incidents[i].window_end
                if gap.total_seconds() <= 0 or gap > span:
                    continue
                if max(user_incidents[j].stages, default=-1) > max(
                        user_incidents[i].stages, default=-1):
                    union(i, j)

        groups: dict[int, list[int]] = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)

        seq = 0
        for root in sorted(groups):
            members = groups[root]
            if len(members) < 2:
                continue
            seq += 1
            member_incidents = [user_incidents[i] for i in sorted(
                members, key=lambda i: user_incidents[i].window_start)]

            peak_logit = max(inc.breakdown.total_logit for inc in member_incidents)
            peak_logit += bonus * (len(member_incidents) - 1)
            peak_risk = 100.0 * _sigmoid(peak_logit / tau)

            campaign_id = f"CMP-{member_incidents[0].window_start:%Y%m%d}-{user}-{seq:02d}"
            for inc in member_incidents:
                inc.campaign_id = campaign_id

            campaigns.append(Campaign(
                campaign_id=campaign_id, user_id=user,
                first_seen=member_incidents[0].window_start.date(),
                last_seen=member_incidents[-1].window_end.date(),
                incident_ids=tuple(inc.incident_id for inc in member_incidents),
                max_stage=max(max(inc.stages, default=0) for inc in member_incidents),
                peak_risk=peak_risk,
                stage_progression=tuple(max(inc.stages, default=0)
                                        for inc in member_incidents),
            ))
    return campaigns


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)
