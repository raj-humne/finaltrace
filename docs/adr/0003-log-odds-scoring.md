# ADR 0003 — Log-odds additive scoring with category saturation

**Status:** Accepted · **Date:** 2026-09-24

## Context

The obvious scoring model is `risk = min(100, Σ weight × strength)`. It is easy to build and easy to explain, and it has three failures that matter in this domain.

1. **Score inflation.** Twelve weak signals outrank one decisive one, so the top of the queue fills with users who tripped many small things.
2. **Redundancy stacking.** `stage.offhours_logon`, `collect.offhours_file_access`, and `evade.offhours_only_day` all fire on one underlying fact — the person worked at night — and the sum counts it three times.
3. **No probabilistic meaning.** If 70 means nothing in particular, a threshold at 70 cannot be reasoned about, defended, or transferred to another deployment.

## Decision

Score in **log-odds space**, with three mechanisms:

```
E_c  = Σ_i δ^(i-1) · w_i · s_i          per category, δ = 0.5   (saturation)
E_ml = w_ml · φ(anomaly_percentile)      w_ml = 1.20 hard cap
E_corr = w_div·(C−1) + w_chain·A + w_prox·P                      (cross-category only)

L    = L₀ + Σ_c E_c + E_ml + E_corr      L₀ = −4.6
risk = 100 · σ(L / τ)                    τ = 1.8
```

- **Weights are log-odds evidence points.** `w` means "observing this multiplies the odds of malicious by `e^w`" — a falsifiable claim, measurable against ground truth.
- **Geometric decay within a category** caps any single category at `2 × w_max`, killing redundancy stacking structurally rather than by hoping rules are independent.
- **`L₀ = −4.6`** encodes a ~1% prior, so a user-day with no evidence scores near zero rather than at the midpoint.
- **The ML term is capped below a single decisive rule**, so the black box can support a case but never carry one.

## Alternatives considered

**Weighted sum with clipping.** The three failures above.

**Train a supervised classifier on ground truth.** With ~70 positives and a 0.19% base rate, it would overfit CERT's scenario scripts, and it would need labels a real deployment does not have. It also destroys the explanation: coefficients are not clauses.

**Bayesian network over signals.** Principled, and it would model dependence properly rather than approximating it with a decay constant. Rejected for v1 on build cost and on explainability — a network's conditional structure is harder for an analyst to read than "this added 18.4 points".

**Noisy-OR.** Close to what we built and arguably more principled; log-odds addition is the same family with a clearer per-rule interpretation and a cheaper counterfactual. Would revisit alongside the Bayesian option.

## Consequences

**Good.** Weights mean something and can be checked (`07-EVALUATION` section 7 measures drift). Thresholds are interpretable as odds. Redundancy cannot inflate a score. Counterfactuals are closed-form arithmetic — microseconds, not model refits. Monotonicity and saturation are property-testable.

**Costs.** Less intuitive than a sum; requires explanation in the demo, which is why the worked example in `04-DETECTION-ENGINE` section 4.2 exists. `δ`, `τ`, and `L₀` are three global knobs that need calibration. **Contributions are non-additive** — because removing a signal changes its siblings' decay positions and can drop the category count, per-signal deltas sum to more than the total. That is correct but surprising, so the UI states it where the numbers are rather than hiding it.
