"""Analyst Feedback Loop for False-Positive Reduction (Challenge 2).

Two small, deterministic, unit-testable modules that api/feedback.py (the
API-layer orchestrator) and engine/detect/scoring.py (via
`compute_feedback_aware_risk`) both depend on:

- `baseline`: Pandas-based recomputation of a user's behavioral tolerance for
  one numeric feature, given its trusted history plus the just-dismissed
  incident's observation (spec C).
- `edge_weights`: the bounded exponential decay applied to a user-scoped
  correlation-graph edge after repeated false-positive feedback (spec D).
- `scoring_adjust`: wires both into the real scoring model
  (engine/detect/scoring.py::compute_risk) without forking it.
"""
