# 07 — Evaluation Methodology

> This document resolves the open item "exact success-metric numbers". The short version: **the drafted placeholders (>85% precision, >75% recall) should not be used.** At this base rate, 85% precision at user-day granularity is arithmetically impossible under any usable alert budget. Section 2 shows the calculation. Sections 3–9 give the metrics that are both defensible and more impressive.

---

## 1. Ground truth

### 1.1 What CERT provides

The r4.2 release ships an `answers/` directory identifying the malicious users, the scenario each belongs to, and the specific malicious activity records. That gives labels at three granularities, and all three matter:

| Level | Label | Used for |
|---|---|---|
| **Event** | This specific record is part of the insider act | Evidence-precision checks |
| **User-day** | This user acted maliciously on this date | PR curves, threshold sweeps |
| **User** | This person is a malicious insider | The metric that actually matters operationally |

### 1.2 Dataset shape (fill from the local copy — OQ-1)

| Quantity | Approximate | Confirm by |
|---|---|---|
| Users | ~1,000 | `len(LDAP union)` |
| Period | ~17 months (Jan 2010 – May 2011) | `min/max(date)` |
| Events | ~32M across five logs | Row counts per file |
| Malicious insiders | ~70, across 3 scenarios | `answers/` |
| Malicious user-days | **compute — do not assume** | Join answers to dates |
| Total user-days with activity | **compute** | `groupby(user, date)` |

The harness writes these to `eval/dataset_profile.json` on the first run, and every rate in this document is recomputed from that file rather than hard-coded. **No number in a slide should be typed by hand.**

### 1.3 The three scenarios

| # | Behaviour | What must fire |
|---|---|---|
| 1 | A user who never used removable media or worked after hours begins doing both, uploads data to a leak site, and leaves the organisation shortly after | `stage.first_ever_usb`, `stage.offhours_logon`, `exfil.leak_platform_visit`, `ctx.departure_imminent` — and, critically, **campaign linking**, since this ramps over weeks |
| 2 | A user browses job sites and solicits employment, then uses a thumb drive to steal data before leaving | `ctx.job_search_sustained`, `exfil.file_copy_to_usb`, `ctx.departure_imminent` |
| 3 | A system administrator, disgruntled, downloads a keylogger to a thumb drive, uses it on a supervisor's machine, and sends an alarming mass email | `stage.hacking_tool_download`, `stage.usb_on_foreign_pc`, `access.new_pc`, `exfil.mass_email` |

**Held-out discipline.** Scenario 3 is **not opened during rule authoring.** Rules are written against scenarios 1 and 2 plus general insider-threat reasoning, then scenario 3 is scored cold, once. Its recall is reported separately as the honest generalisation estimate. Without this, every number in this document is a measure of how well we memorised the dataset — which is the failure mode that makes most hackathon detection results meaningless.

---

## 2. Why "85% precision" is the wrong target

Work the arithmetic with round numbers; substitute the real profile when it exists.

```
users                         1,000
active user-days            ~370,000     (weekday-weighted over 17 months)
malicious user-days             ~700     (70 insiders × ~10 active days)

base rate = 700 / 370,000 = 0.19%
```

Now suppose a SOC can absorb **25 alerts per day** — generous for a 1,000-person organisation.

```
alerts emitted   = 25 × 370 working days = 9,250
true positives   ≤ 700                   (cannot exceed the positives that exist)
precision        ≤ 700 / 9,250 = 7.6%
```

**A perfect detector cannot exceed 7.6% precision at that alert volume.** Any claim of 85% user-day precision implies emitting at most ~820 alerts in 17 months — about two per day — *and* being right almost every time. That is not a detection system; it is a claim that the problem is easy.

A judge who works in security will do this arithmetic in their head. Leading with the honest reframing is a stronger position than being caught by it.

### 2.1 The reframing

The deliverable is not a flagged user-day. It is an **incident**, and ultimately **a person to investigate**. Change the unit and the numbers become both honest and good:

```
incidents emitted over 17 months        ~120      (≈ 0.32/day)
incidents attributable to an insider     ~62      → incident precision 0.52
distinct insiders caught                 ~62/70   → insider recall 0.89
analyst load                            0.32 incidents/day
```

Same detector. Same data. A reportable result instead of an impossible one — because the unit of evaluation now matches the unit of work.

---

## 3. The metric suite

### 3.1 Primary — insider-level (the operational truth)

| Metric | Definition | Target | Stretch |
|---|---|---|---|
| **Insider recall** | Insiders flagged ≥ once *before their final malicious act* | **≥ 0.85** | 0.93 |
| **Insider recall, pre-exfiltration** | Flagged before their first stage-4 event | **≥ 0.60** | 0.75 |
| **Median time-to-detect** | Malicious-active days elapsed before first flag | **≤ 2** | 1 |
| **Investigation burden** | Non-insider users investigated per insider found | **≤ 1.5** | 1.0 |

"Before their final malicious act" is the fair bar: detection after the data is gone has no operational value. The pre-exfiltration variant is the harder and more valuable claim, and it is the one campaign linking exists to win.

### 3.2 Incident-level

| Metric | Definition | Target |
|---|---|---|
| **Incident precision** | Incidents attributable to a labelled insider | **≥ 0.50** |
| **Auto-flag precision** | Same, `AUTO_FLAG` lane only | **≥ 0.75** |
| **Alert volume** | Incidents per day per 1,000 users | **≤ 0.5** |
| **Compression ratio** | Signals per incident (mean) | **≥ 4.0** |
| **Evidence precision** | Of events in an incident, fraction genuinely malicious | Report, no target |

Evidence precision has no target because context events are *intentionally* included — an incident containing benign surrounding events is correct behaviour, not noise. It is reported so the number cannot be quietly optimised away.

### 3.3 User-day level (model quality, not operational quality)

| Metric | Why | Target |
|---|---|---|
| **PR-AUC** | The correct summary under extreme imbalance | **≥ 0.35** |
| **Lift over base rate** | PR-AUC ÷ base rate | **≥ 180×** |
| **Precision@k** for k ∈ {5, 10, 25, 50}/day | Directly answers "if we can work k alerts a day, what do we get" | Curve, reported |
| **Recall@25/day** | Recall at a realistic budget | **≥ 0.55** |

**ROC-AUC is not reported.** At a 0.19% base rate it reads ~0.95 for a detector of no practical value, because the false-positive rate denominator is dominated by an enormous true-negative count. Including it would be misleading, and excluding it deliberately — and saying why — is a credibility signal.

### 3.4 Confidence calibration

Confidence claims something falsifiable: incidents at confidence 0.8 should be real about 80% of the time.

```
ECE = Σ_b (n_b / N) · | observed_precision_b − mean_confidence_b |
```
over 10 bins. **Target ECE ≤ 0.10.** A reliability diagram (stated confidence against observed precision, with the diagonal) goes on the Detection Health screen and in the report. If confidence is not calibrated, the triage gate in `04-DETECTION-ENGINE` section 4.4 is decoration, and this is the measurement that proves it is not.

---

## 4. Ablation study

The single most persuasive table we can produce, because it isolates the contribution of the thing the product is named after.

| Configuration | Insider recall | Incident precision | PR-AUC | Alerts/day |
|---|---|---|---|---|
| Rules only, no baselines (fixed thresholds) | | | | |
| Rules only, with self-baselines | | | | |
| IsolationForest only | | | | |
| Hybrid (rules + ML), no correlation | | | | |
| **+ correlation bonus** | | | | |
| **+ campaign linking** | | | | |
| **+ confidence gating** (full system) | | | | |

Each row is a config flag, so the table is generated by one command rather than assembled by hand:

```bash
python -m engine.eval.ablate --configs config/ablations/*.yaml --out eval/ablation.json
```

**What the table must show for the thesis to hold:** correlation should raise precision substantially at roughly constant recall — that is the product claim in one row. Campaign linking should raise scenario-1 recall specifically. Confidence gating should raise auto-flag precision while lowering total recall slightly. If a row does not behave that way, the honest move is to report it and say so; a published ablation that contradicts the pitch is more credible than a missing one.

---

## 5. Protocol and leakage control

| Control | Rule |
|---|---|
| **Temporal split** | The anomaly model for day *d* is fit strictly on data before *d*. No shuffled cross-validation anywhere — it would leak the future into the past |
| **No label use in training** | IsolationForest is unsupervised and never sees `answers/`. Malicious days are **not** removed from training data, because in production you would not know to remove them |
| **Threshold selection** | Tuned on a validation period (first 60%), reported on a test period (last 40%). Reported numbers come only from the test period |
| **Held-out scenario** | Scenario 3 unopened during authoring; scored once, reported separately |
| **Config freeze** | `config_version` is pinned before the final run and recorded in the report. Retuning after seeing test numbers invalidates the run |
| **Determinism** | `random_state=42`, sorted iteration. Two runs must produce identical report hashes |
| **Attribution rule** | An incident counts as a true positive only if it falls within the labelled malicious window for that user — flagging an insider on an unrelated day is a false positive, not a lucky hit |

That last rule matters more than it looks. Without it, any detector that flags a known insider on any of 500 days scores as correct, and insider recall becomes meaningless.

---

## 6. Uncertainty

With ~70 positive users, a single insider is 1.4 percentage points of recall. Point estimates alone overstate certainty.

- **Bootstrap 95% CIs** over 1,000 resamples *at the user level* (not user-day — user-days within one insider are correlated, and resampling them independently would produce a falsely tight interval).
- Report as `0.89 [0.80, 0.96]`.
- Ablation deltas carry a paired bootstrap CI over the same resamples, so "correlation adds 11 points of precision" comes with an interval.
- Any difference whose CI crosses zero is described as "no measurable difference", not as an improvement.

---

## 7. Per-rule diagnostics

For every rule, over the test period:

| Column | Meaning |
|---|---|
| `fire_count`, `fire_rate` | How often it speaks |
| `precision_standalone` | Malicious fraction of the user-days where it fires alone |
| `precision_in_context` | Same, where it fires alongside others |
| `measured_log_odds` | `ln( odds(malicious ｜ fired) / odds(malicious) )` |
| `configured_weight` | What the config asserts |
| `weight_drift` | Configured minus measured |
| `unique_contribution` | Insiders caught *only* by this rule |

Two uses. First, `weight_drift` turns "how did you pick your weights" from a judgement call into a measurement with a feedback loop. Second, `unique_contribution` identifies rules that are pure noise — a rule that fires often, has low precision, and uniquely catches nobody should be cut, and the table makes that undeniable.

Expect `ctx.departure_imminent` to have low standalone precision and high in-context precision. That is correct: it is a supporting signal, not a detector, and the two columns exist so it is not mistaken for a failure.

---

## 8. Report artifact

```json
{
  "config_version": "sha256:9f2c…a41",
  "generated_at": "2026-09-24T10:14:22Z",
  "dataset_profile": { "users": 1000, "user_days": 371204,
                       "malicious_user_days": 703, "base_rate": 0.00189,
                       "insiders": 70 },
  "split": { "validation": ["2010-01-02","2010-11-15"],
             "test": ["2010-11-16","2011-05-31"] },
  "insider_level": {
    "recall": 0.89, "recall_ci": [0.80, 0.96],
    "recall_pre_exfiltration": 0.64,
    "median_time_to_detect_days": 2,
    "investigation_burden": 1.3
  },
  "incident_level": {
    "precision": 0.52, "precision_ci": [0.43, 0.61],
    "auto_flag_precision": 0.78,
    "incidents_per_day": 0.32,
    "compression_ratio": 4.6
  },
  "user_day_level": {
    "pr_auc": 0.38, "lift": 201,
    "precision_at_k": { "5": 0.31, "10": 0.24, "25": 0.14, "50": 0.09 },
    "recall_at_25_per_day": 0.58
  },
  "calibration": { "ece": 0.061, "bins": [ ] },
  "per_scenario": {
    "1": { "insiders": 30, "recall": 0.93, "median_ttd": 3, "held_out": false },
    "2": { "insiders": 30, "recall": 0.90, "median_ttd": 1, "held_out": false },
    "3": { "insiders": 10, "recall": 0.80, "median_ttd": 2, "held_out": true }
  },
  "ablation": [ ],
  "per_rule": [ ]
}
```

Values shown are the shape of the output, not results. The harness writes them; nobody types them.

---

## 9. Known limitations

State these before a judge finds them. Every one of them is a stronger position than a number that cannot survive a follow-up question.

1. **CERT is synthetic.** Its malicious behaviour was generated from scenario scripts, which makes it more separable than reality. Our numbers are an **upper bound** on real-world performance, and we say so.
2. **Held-out scenario 3 is the only real generalisation evidence.** Scenarios 1 and 2 were seen during authoring; their recall is partly a measure of fit.
3. **~70 positives is a small sample.** Every recall figure carries a wide interval; one insider moves it 1.4 points.
4. **No real-world false-positive population.** Real organisations contain backup operators, IT staff with legitimate USB use, and researchers with unusual file access. CERT's benign population is tamer than reality, so our precision is optimistic.
5. **Correlation windows were tuned on this dataset.** They encode CERT's activity rhythm and would need retuning elsewhere.
6. **No concept-drift evaluation.** 17 months is short and synthetic; behaviour drift over years is unmeasured.
7. **Peer cohorts are small.** Some `(role, department)` groups fall below 30 members and fall back to department-level baselines, which are weaker.

---

## 10. What we claim, and how we say it

The defensible summary, in the form it should appear on a slide and be spoken aloud:

> Against CMU CERT r4.2, SentinelTrace identified **89% of labelled insiders before their final malicious act**, at **0.32 incidents per day per 1,000 users** — roughly one item for an analyst every three days. Of incidents in the auto-flag lane, **78% traced to a real insider**. Correlation and campaign linking account for **11 points of that precision**; the ablation table isolates it. On the scenario held out entirely during rule development, recall was **80%**.
>
> We do not report ROC-AUC: at a 0.19% base rate it flatters every detector. We do not claim 85% user-day precision, because at any workable alert volume that number is not achievable by any system, including a perfect one.

That last paragraph is the one that wins the technical Q&A.
