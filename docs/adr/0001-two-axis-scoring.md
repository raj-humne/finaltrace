# ADR 0001 — Separate risk from confidence

**Status:** Accepted · **Date:** 2026-09-24

## Context

Detection systems in this category almost universally emit a single number: a risk score, a severity, a percentage. That number silently fuses two different questions:

- **How serious would this be if it is real?**
- **How sure are we that it is real?**

They come apart constantly. A single decisive rule firing on a user with nine days of history is serious-if-real but poorly evidenced. Six cross-source signals with three months of baseline is both. A single score cannot distinguish them, so the analyst either treats every 80 the same way — and learns that 80 means nothing — or develops private heuristics the system does not share.

There is also a fairness dimension. The monitored employee has no interface and no voice. A system that acts decisively on thin evidence harms people, and a single score gives it no way to know it is doing so.

## Decision

Every user-day and every incident carries **two independent values**:

- `risk` ∈ [0, 100] — magnitude of the evidence, from the log-odds model.
- `confidence` ∈ [0, 1] — quality of the evidence: rule/ML agreement, category diversity, source completeness, baseline maturity.

Triage routes on the **plane**, not on either axis alone. The binding rule: high risk with confidence below 0.65 routes to `ANALYST_REVIEW`, never `AUTO_FLAG`.

Confidence is **calibrated and measured** — expected calibration error is a reported metric with a target of ≤ 0.10. Without that, it is decoration.

## Alternatives considered

**Single score with a confidence interval.** Closer to correct, but an interval on a bounded 0–100 score is hard to read at a glance and harder to route on. Rejected for legibility in a queue.

**Confidence as a multiplier on risk.** `risk × confidence` collapses back to one number and re-creates the exact problem: 90 × 0.4 and 45 × 0.8 both give 36, and they demand completely different responses.

**Confidence as a filter only** (suppress below a threshold, then show risk). Loses information the analyst needs; a low-confidence high-risk item should be *seen and marked as such*, not hidden.

## Consequences

**Good.** Analysts can triage on evidence quality. The system has a principled reason to decline to act. Missing data lowers certainty rather than silently lowering risk. Calibration becomes measurable, so the gate is testable.

**Costs.** Two numbers is more UI surface and more to explain in a demo. Confidence must be calibrated or it is worse than useless — a miscalibrated confidence is an unearned claim. Analysts need training on the difference; the interface carries that load by always showing both at equal weight and drawing thresholds on the meters.

**Follow-on.** `04-DETECTION-ENGINE` section 4.3 specifies the terms; `07-EVALUATION` section 3.4 specifies the calibration measurement.
