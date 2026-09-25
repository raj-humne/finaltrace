"""Event graph construction (docs/04-DETECTION-ENGINE.md section 6.1).

Nodes are events that carry at least one signal, plus their immediate
context neighbours. Edges are drawn per-pair-type: temporal (windowed by
source pair, docs section 6.2), shared PC and shared file (cross-user, for
lateral movement), and stage-advance (the kill-chain progression correlation
exists to reward). NetworkX computes connected components server-side
(docs/02-ARCHITECTURE.md section 11); the client only renders.

Deviation from the docs section 6.1 pseudocode, flagged rather than silently
"corrected": the pseudocode's `temporal` and `stage_advance` edges carry no
same-user guard, but FR-4.3 scopes cross-user correlation to exactly
`shared_pc`/`shared_file` ("lateral movement"), and every reasoning example
in docs section 6.2 and the PRD 1.1 walkthrough is a single person's session.
Taken literally, an unguarded temporal edge connects any two employees who
happen to act within a few hours of each other - on real data this collapses
almost the entire signal-bearing population into one connected component
per day (empirically ~70K nodes, components up to 3,850, on the synthetic
fixture), which starves every genuine incident of a correlation bonus via
`over_dense`. This implementation restricts `temporal` and `stage_advance`
to same-user pairs; cross-user connectivity still exists, but only through
the two edge types the spec explicitly designed for it.
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

    # Plain numpy arrays, not per-row pandas indexing: with tens of thousands
    # of candidate nodes the .iloc-per-pair version is dominated by pandas
    # call overhead rather than the arithmetic itself.
    ts_arr = nodes["ts"].to_numpy()
    event_id_arr = nodes["event_id"].to_numpy()
    user_arr = nodes["user_id"].to_numpy()
    pc_arr = nodes["pc_id"].to_numpy()
    source_arr = nodes["source"].to_numpy()
    filename_arr = nodes["filename"].to_numpy()
    stage_arr = np.array([stage_of.get(e) for e in event_id_arr], dtype=object)

    scan_limit = np.timedelta64(_MAX_SCAN_MINUTES, "m")
    n = len(nodes)
    edges: list[tuple[str, str, str, float, int]] = []
    for i in range(n):
        # Sorted by ts: once the gap exceeds the widest possible window, every
        # later j is farther still - stop scanning this row.
        j_end = int(np.searchsorted(ts_arr, ts_arr[i] + scan_limit, side="right"))
        if j_end <= i + 1:
            continue

        gap_min = (ts_arr[i + 1:j_end] - ts_arr[i]) / np.timedelta64(1, "m")
        window_min = np.array(
            [cfg.pair_window_min(source_arr[i], s) for s in source_arr[i + 1:j_end]])
        same_pc = (pc_arr[i + 1:j_end] == pc_arr[i]) & (pc_arr[i] not in (None, ""))
        diff_user = user_arr[i + 1:j_end] != user_arr[i]
        same_user = ~diff_user
        same_file = (filename_arr[i + 1:j_end] == filename_arr[i]) & (
            filename_arr[i] not in (None, ""))
        stage_i = stage_arr[i]
        stage_advance = np.array([
            stage_i is not None and s is not None and s == stage_i + 1
            for s in stage_arr[i + 1:j_end]])

        for offset in range(j_end - i - 1):
            j = i + 1 + offset
            gm = float(gap_min[offset])
            gap_seconds = int(round(gm * 60))
            eid_a, eid_b = event_id_arr[i], event_id_arr[j]

            if same_user[offset] and gm <= window_min[offset]:
                w = math.exp(-gm / window_min[offset]) if window_min[offset] > 0 else 1.0
                edges.append((eid_a, eid_b, "temporal", w, gap_seconds))
            if same_pc[offset] and diff_user[offset]:
                edges.append((eid_a, eid_b, "shared_pc", 0.8, gap_seconds))
            if same_file[offset] and diff_user[offset]:
                edges.append((eid_a, eid_b, "shared_file", 0.9, gap_seconds))
            if same_user[offset] and stage_advance[offset]:
                edges.append((eid_a, eid_b, "stage_advance", 1.0, gap_seconds))

    for eid_a, eid_b, edge_type, weight, gap_seconds in edges:
        g.add_edge(eid_a, eid_b, type=edge_type, weight=weight, gap_seconds=gap_seconds)

    return EventGraph(graph=g, event_stage=stage_of, event_category=category_of,
                      event_to_signals=signals_of)
