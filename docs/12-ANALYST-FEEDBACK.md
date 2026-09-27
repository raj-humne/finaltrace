# 12. Analyst Feedback Loop for False-Positive Reduction

Lets a SOC analyst mark a correlated incident as a false positive from the React UI, and — unless they opt out — has the system learn from that decision: a Pandas-recomputed behavioral baseline for the affected user, and decayed correlation-edge weights for the incident's evidence chain, so the same or a highly similar event sequence scores measurably lower next time. This is a different, complementary feature to `11-MITIGATION.md`'s automated response pipeline: mitigation decides what to *do* about a high-risk incident; this feature decides how the *scorer itself* should adapt after a human says a pattern was benign.

Nothing here rewrites the detection/scoring engine or deletes evidence. `engine/detect/scoring.py::compute_risk()` is still the sole scoring function; this feature only changes what gets fed into it for a given user, going forward.

## Architecture

```
Analyst clicks "Mark as false positive" on the incident page (React dialog)
                              │
                              ▼
      POST /api/v1/incidents/{incident_id}/feedback   (api/routers/incidents.py)
                              │
                              ▼
              api/feedback.py::submit_feedback()   — one DB transaction
                              │
        ┌─────────────────────┼──────────────────────────┐
        ▼                     ▼                           ▼
  AnalystFeedback row   Pandas baseline recompute    Edge-weight decay
  (audit trail)         (engine/feedback/baseline.py) (engine/feedback/edge_weights.py)
        │                     │                           │
        ▼                     ▼                           ▼
  incident.status/disposition   BehavioralBaseline rows    EdgeFeedbackWeight rows
  = closed / false_positive     (per user, per feature)    (per user, per edge-type pair)
                              │
                              ▼
        Next time this user's chain is scored:
        engine/feedback/scoring_adjust.py::compute_feedback_aware_risk()
        wraps the real compute_risk() with the learned, user-scoped adjustments.
```

Raw `events`, `signals`, and `attributions` rows are never modified — "keep raw evidence immutable" is enforced by never writing to those tables from this feature. Only the new, additive tables below plus `incidents.status`/`disposition`/`dismissed_at`/`dismissed_by` change.

## New database tables

All four are additive (a hand-written Alembic migration, `alembic/versions/f3c8a1d92b70_*.py`, following the same style as `2844566c110f`'s incident-column additions):

- **`analyst_feedback`** — one row per submitted false-positive verdict: `incident_id`, `analyst_id`, `verdict` (`'false_positive'` only in this feature), `reason_code` (`approved_business_activity`, `expected_off_hours_work`, `known_usb_workflow`, `known_host_access`, `expected_bulk_access`, `test_or_training`, `other`), `comment`, `apply_to_similar`, `created_at`. Append-only, like `Review` and `MitigationAction`.
- **`behavioral_baselines`** — one row per `(entity_type, entity_id, feature_name)` (unique constraint), holding `mean_value`, `std_value`, `p95_value`, `sample_count`, `feedback_adjustment` (cumulative learned tolerance widening), `updated_at`. `entity_type` is always `'user'` in this feature's write path today, even though the column allows for a future cohort-scoped row.
- **`edge_feedback_weights`** — one row per `(source_event_type, target_event_type, context_key)` (unique constraint), where `context_key` is `"user:{user_id}"`. Holds `original_weight`, `current_weight`, `false_positive_count`, `last_feedback_at`.
- **`feature_observations`** — an immutable, append-only ledger of every numeric feature value ever extracted from a dismissed incident (`is_trusted` records whether the analyst opted in to learning from it). `behavioral_baselines` is recomputed *from* this table, never edited in place from a single event.
- **`incidents`** gains four nullable columns: `disposition`, `disposition_reason`, `dismissed_at`, `dismissed_by` — `status` alone already existed (`open`/`in_review`/`closed`); `disposition` records *why* a closed incident is closed, distinguishing a false-positive dismissal from the pre-existing Review-based `confirmed_threat`/`benign` flow.

## API

`POST /api/v1/incidents/{incident_id}/feedback`

Request:
```json
{
  "verdict": "false_positive",
  "reason_code": "known_usb_workflow",
  "comment": "Scheduled backup workflow for this user - confirmed with IT.",
  "apply_to_similar": true
}
```

Response (201):
```json
{
  "incident_id": "INC-20100105-u_014-01",
  "incident_status": "closed",
  "disposition": "false_positive",
  "feedback_id": 1,
  "updated_baselines": [
    {"feature_name": "file_access_count", "mean_value": 15.0, "std_value": 1.0, "p95_value": 15.0, "sample_count": 1}
  ],
  "updated_edges": [
    {"source_event_type": "logon.logon", "target_event_type": "device.connect",
     "false_positive_count": 1, "original_weight": 1.0, "current_weight": 0.85}
  ],
  "score_impact": {"original_risk": 73.4, "predicted_similar_risk": 44.1, "expected_reduction": 29.3},
  "processed_at": "2026-09-27T16:00:00Z"
}
```

Validation: 404 if the incident does not exist; 409 if it was already dismissed as a false positive (this feature does not support re-opening); 422 if `verdict`/`reason_code` is not one of the allowed values (enforced by Pydantic `Literal` types). The authenticated account from the existing session-cookie mechanism (`api/deps.py::get_current_account`, already required at the incidents router level) supplies the analyst identity — no separate demo identity was needed since this repo already has real analyst auth. Everything happens inside a single DB transaction in `api/feedback.py::submit_feedback()`.

## Why learning is scoped to the specific user

`context_key = "user:{user_id}"` on `edge_feedback_weights`, and `entity_id = user_id` on `behavioral_baselines`, mean a lookup for a different user's identical event-type pair or feature simply finds no row and falls back to the unmodified default. `engine/feedback/scoring_adjust.py::compute_feedback_aware_risk()` only ever receives the multiplier/discounts for the specific `user_id` being scored — there is no code path in this feature that writes or reads a global or cohort-wide row. This is deliberate: one analyst's read of one user's benign pattern must not quietly suppress a genuinely different user exhibiting the same superficial event sequence.

## Bounded-learning controls

- **25% baseline growth cap per feedback event** (`engine/feedback/baseline.py::MAX_ADAPTATION_FRACTION`) — widening an *existing* stored mean or std is capped at 25% over its previous value per event, so repeated false positives compound gradually rather than blowing out a baseline in one shot. A feature's very first trusted observation (no prior baseline to cap against) gets a bounded initial trust bump instead (0.5, well under the 1.0 ceiling) — documented in `api/feedback.py::_update_baselines`.
- **Minimum std floor of 1.0** (`engine/feedback/baseline.py::MIN_STD`) — a baseline can never become so tight that an ordinary day looks anomalous by construction.
- **15% edge-weight decay per false positive, floored at 0.40** (`engine/feedback/edge_weights.py`): `multiplier = max(0.40, 0.85 ** false_positive_count)`. A repeatedly-dismissed transition is heavily deprioritized in scoring but never made fully invisible — the raw evidence is still shown on the incident page regardless of its learned weight.

## Running the tests and demo

```
pytest tests/test_analyst_feedback.py -v      # unit tests (baseline math, edge decay) + the full API/scoring integration test
python -m tools.feedback_loop_demo            # first injection -> feedback -> second injection, printed end to end
```

`tools/feedback_loop_demo.py` uses its own scratch SQLite file (`data/_feedback_loop_demo.db`, recreated on every run) and prints the exact reduction achieved for a real, hand-seeded off-hours-login → USB-insert → high-volume-file-access chain, plus proof that an unrelated user's identical chain is unaffected.

## Safety note

**Feedback reduces prioritization of a narrowly defined, previously reviewed pattern. It does not delete evidence or declare a user safe.**
