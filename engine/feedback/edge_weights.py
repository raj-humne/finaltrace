"""Graph correlation-edge feedback (Challenge 2, spec D).

Each confirmed false-positive dismissal for an incident whose evidence chain
crossed a given (source_event_type -> target_event_type) transition, for a
given user, decays that specific transition's weight for that specific user
only (api/feedback.py::_update_edges writes one EdgeFeedbackWeight row per
context_key="user:{user_id}" pair - never a global row). This module is the
pure math: given how many times this exact (edge, user) pair has already been
dismissed, what multiplier should now apply.
"""
from __future__ import annotations

MIN_MULTIPLIER = 0.40
DECAY_BASE = 0.85


def edge_weight_multiplier(false_positive_count: int) -> float:
    """multiplier = max(0.40, 0.85 ** false_positive_count).

    false_positive_count=0 -> 1.0 (no history, no adjustment).
    false_positive_count=1 -> 0.85 (first dismissal).
    false_positive_count=2 -> 0.7225, and so on, floored at 0.40 so a
    repeatedly-dismissed pattern is heavily deprioritized but never made
    fully invisible - the raw evidence is still there for a human to see.
    """
    if false_positive_count <= 0:
        return 1.0
    return max(MIN_MULTIPLIER, DECAY_BASE ** false_positive_count)


def next_edge_weight(original_weight: float, false_positive_count: int) -> float:
    """current_weight = original_weight * multiplier(false_positive_count)."""
    return original_weight * edge_weight_multiplier(false_positive_count)
