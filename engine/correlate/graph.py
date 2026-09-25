"""Event graph construction (docs/04-DETECTION-ENGINE.md section 6.1).

Nodes are events that carry at least one signal, plus their immediate
context neighbours. Edges are drawn per-pair-type: temporal (windowed by
source pair, docs section 6.2), shared PC and shared file (cross-user, for
lateral movement), and stage-advance (the kill-chain progression correlation
exists to reward). NetworkX computes connected components server-side
(docs/02-ARCHITECTURE.md section 11); the client only renders.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date as date_type

import networkx as nx
import numpy as np
import pandas as pd

from engine.core.config import Config
from engine.core.models import Signal

# No configured pair window exceeds this; used to bound the pairwise scan so
# it need not compare every node against every other node in the corpus.
_MAX_SCAN_MINUTES = 24 * 60


@dataclass
class EventGraph:
    graph: nx.Graph
    event_stage: dict[str, int] = field(default_factory=dict)
    event_category: dict[str, str] = field(default_factory=dict)
    event_to_signals: dict[str, list[Signal]] = field(default_factory=dict)


def _event_signal_maps(
    signals_by_day: dict[tuple[str, date_type], list[Signal]]
) -> tuple[dict[str, int], dict[str, str], dict[str, list[Signal]]]:
    """event_id -> the strongest (highest-stage) signal citing it, and the
    full list of signals that cite each event (an event can be evidence for
    more than one rule)."""
    stage_of: dict[str, int] = {}
    category_of: dict[str, str] = {}
    signals_of: dict[str, list[Signal]] = {}
    for signals in signals_by_day.values():
        for s in signals:
            for eid in s.evidence_event_ids:
                signals_of.setdefault(eid, []).append(s)
                if eid not in stage_of or s.stage > stage_of[eid]:
                    stage_of[eid] = s.stage
                    category_of[eid] = s.category
    return stage_of, category_of, signals_of


def _same_file(a: pd.Series, b: pd.Series) -> bool:
    fa, fb = a.get("filename"), b.get("filename")
    return bool(fa) and bool(fb) and fa == fb


def build_graph(events: pd.DataFrame,
                signals_by_day: dict[tuple[str, date_type], list[Signal]],
                cfg: Config) -> EventGraph:
    stage_of, category_of, signals_of = _event_signal_maps(signals_by_day)
    signal_event_ids = set(stage_of)

    g = nx.Graph()
    if not signal_event_ids or events.empty:
        return EventGraph(graph=g, event_stage=stage_of, event_category=category_of,
                          event_to_signals=signals_of)

    ev = events.sort_values("ts", kind="stable").reset_index(drop=True)
    if "filename" not in ev.columns:
        ev["filename"] = None

    neighbour_min = cfg.correlation["context_neighbour_min"]
    delta_ns = np.timedelta64(neighbour_min, "m")
    node_ids: set[str] = set(signal_event_ids)

    # Context neighbours: events within +/- neighbour_min of a signal event,
    # same user - keeps the neighbourhood meaningful and bounded.
    signal_events = ev[ev["event_id"].isin(signal_event_ids)]
    for user, se in signal_events.groupby("user_id", sort=False):
        pool = ev[ev["user_id"] == user]
        ts = pool["ts"].to_numpy()
        for t in se["ts"].to_numpy():
            lo = np.searchsorted(ts, t - delta_ns, side="left")
            hi = np.searchsorted(ts, t + delta_ns, side="right")
            node_ids.update(pool["event_id"].iloc[lo:hi].tolist())

    nodes = (ev[ev["event_id"].isin(node_ids)]
             .sort_values("ts", kind="stable").reset_index(drop=True))

    for row in nodes.itertuples(index=False):
        g.add_node(row.event_id, ts=row.ts, user_id=row.user_id, pc_id=row.pc_id,
                  source=row.source, stage=stage_of.get(row.event_id),
                  category=category_of.get(row.event_id),
                  is_signal=row.event_id in signal_event_ids)

    ts_arr = nodes["ts"].to_numpy()
    scan_limit = np.timedelta64(_MAX_SCAN_MINUTES, "m")
    n = len(nodes)
    for i in range(n):
        a = nodes.iloc[i]
        # Sorted by ts: once the gap exceeds the widest possible window, every
        # later j is farther still - stop scanning this row.
        j_end = np.searchsorted(ts_arr, ts_arr[i] + scan_limit, side="right")
        for j in range(i + 1, min(j_end, n)):
            b = nodes.iloc[j]
            gap_min = (b["ts"] - a["ts"]).total_seconds() / 60.0

            window = cfg.pair_window_min(a["source"], b["source"])
            if gap_min <= window:
                w = math.exp(-gap_min / window) if window > 0 else 1.0
                g.add_edge(a["event_id"], b["event_id"], type="temporal", weight=w,
                          gap_seconds=int(round(gap_min * 60)))

            if a["pc_id"] and a["pc_id"] == b["pc_id"] and a["user_id"] != b["user_id"]:
                g.add_edge(a["event_id"], b["event_id"], type="shared_pc", weight=0.8,
                          gap_seconds=int(round(gap_min * 60)))

            if _same_file(a, b) and a["user_id"] != b["user_id"]:
                g.add_edge(a["event_id"], b["event_id"], type="shared_file", weight=0.9,
                          gap_seconds=int(round(gap_min * 60)))

            stage_a, stage_b = stage_of.get(a["event_id"]), stage_of.get(b["event_id"])
            if stage_a is not None and stage_b is not None and stage_b == stage_a + 1:
                g.add_edge(a["event_id"], b["event_id"], type="stage_advance", weight=1.0,
                          gap_seconds=int(round(gap_min * 60)))

    return EventGraph(graph=g, event_stage=stage_of, event_category=category_of,
                      event_to_signals=signals_of)
