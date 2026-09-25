# 04 — Detection Engine

> This is the core of the product. Everything else is plumbing around what is specified here.

---

## 1. Design stance

Three commitments shape the whole engine.

**1. Hybrid means two independent opinions, not one blended model.**
Rules encode what a security analyst knows. The anomaly model finds what nobody thought to write down. If they are merged into a single trained classifier, the explanation dies and the label scarcity kills the training. Kept separate, each is independently auditable, each can be disabled, and their *agreement* becomes a confidence signal in its own right.

**2. Risk and confidence are orthogonal.**
A score of 88 built on one rule and a sparse baseline is a different object from a score of 88 built on six cross-source signals with 40 days of history. Collapsing them into one number is the mistake nearly every UEBA product makes, and it is what produces both analyst distrust and unfair outcomes for the monitored.

**3. Correlation must be earned.**
Ten rules firing on the same underlying fact is one piece of evidence, not ten. The scoring model has explicit saturation to enforce this, and the correlation bonus requires signals from *different categories*.

---

## 2. The insider kill chain

Every rule is tagged with a stage. Staging turns a flat list of alerts into a progression, and progression is what distinguishes a campaign from a bad day.

| Stage | Name | Meaning | Typical signals |
|---|---|---|---|
| 0 | `CONTEXT` | Disposition / motive indicator | job-search browsing, imminent departure, post-departure activity |
| 1 | `RECON` | Looking around | access to new shares, unusual breadth of file access, new PCs touched |
| 2 | `STAGING` | Preparing the means | first-ever USB, hacking-tool downloads, off-hours logon on a foreign PC |
| 3 | `COLLECTION` | Gathering the data | file bursts, sensitive-extension concentration, mass reads |
| 4 | `EXFILTRATION` | Moving it out | file-to-USB copies, uploads to cloud storage, self-send with attachments |
| 5 | `EVASION` | Covering up | activity gaps, logoff-then-activity, deletions, off-hours-only patterns |

**Stage-advance bonus.** When an incident (or a campaign) contains signals at stages that advance monotonically in time, correlation adds points. `RECON at 14:00 → STAGING at 21:47 → COLLECTION at 22:04 → EXFILTRATION at 22:31` is an ordered chain. The same four signals in scrambled order is not, and scores lower. This is a cheap, deterministic, and genuinely discriminative feature that most scoring systems omit.

---

## 3. Rule catalogue

Rules are declarative YAML. Adding one requires no Python (`adr/0002`).

### 3.1 Rule schema

```yaml
- id: exfil.file_copy_to_usb
  name: "Bulk file activity during removable-media session"
  category: exfil                 # access|staging|collection|exfil|evasion|context
  stage: 4                        # kill-chain stage
  weight: 1.30                    # log-odds evidence points at strength 1.0
  when:                           # ALL must hold
    - feature: file_events_during_usb
      op: gte
      value: 10
  strength:                       # maps magnitude -> 0..1
    feature: file_events_during_usb
    scale: log
    lo: 10
    hi: 200
  requires_baseline: false        # fires even during warm-up
  evidence:
    sources: [file, device]
    window_min: 60
  phrase: "copied {file_events_during_usb} files while removable media was connected"
  references: ["MITRE T1052.001"]
```

Supported operators: `gte`, `gt`, `lte`, `lt`, `eq`, `neq`, `in`, `is_true`, `z_self_gte`, `z_peer_gte`, `and`, `or`, `not`.
Strength scales: `linear`, `log`, `step`, `binary`.

### 3.2 The catalogue (v1 — 27 rules)

#### Context (stage 0)
| id | Fires when | Weight |
|---|---|---|
| `ctx.departure_imminent` | `days_to_departure <= 30` | 0.55 |
| `ctx.post_departure_activity` | Any activity after `departure_date` | 2.20 |
| `ctx.job_search_spike` | `job_search_visits` z_peer >= 3 and count >= 5 | 0.70 |
| `ctx.job_search_sustained` | job-search visits on >= 5 of the trailing 14 days | 0.85 |

#### Access / recon (stage 1)
| id | Fires when | Weight |
|---|---|---|
| `access.new_pc` | `new_pc_count >= 1` and not in warm-up | 0.60 |
| `access.pc_breadth` | `distinct_pc_count` z_self >= 3 | 0.75 |
| `access.file_breadth` | `distinct_file_count` z_self >= 3.5 and z_peer >= 2 | 0.80 |
| `access.new_extension` | `new_extension_count >= 3` | 0.45 |

#### Staging (stage 2)
| id | Fires when | Weight |
|---|---|---|
| `stage.first_ever_usb` | `is_first_ever_usb` is true | **1.60** |
| `stage.usb_after_dormancy` | `days_since_last_usb >= 90` | 1.10 |
| `stage.usb_on_foreign_pc` | `usb_on_foreign_pc` is true | 1.35 |
| `stage.hacking_tool_download` | `hacking_tool_visits >= 1` | **1.75** |
| `stage.offhours_logon` | `after_hours_logon_count >= 1` (learned window) | 0.65 |
| `stage.offhours_logon_foreign_pc` | off-hours logon and `own_pc_ratio < 1` | 1.20 |

#### Collection (stage 3)
| id | Fires when | Weight |
|---|---|---|
| `collect.file_burst` | `file_burst_max_per_10min >= 25` | 0.95 |
| `collect.sensitive_concentration` | `sensitive_ext_count` z_self >= 3 and ratio >= 0.6 | 0.85 |
| `collect.volume_anomaly` | `file_event_count` z_self >= 4 | 0.80 |
| `collect.offhours_file_access` | `offhours_event_ratio >= 0.5` and `file_event_count >= 20` | 0.90 |

#### Exfiltration (stage 4)
| id | Fires when | Weight |
|---|---|---|
| `exfil.file_copy_to_usb` | `file_events_during_usb >= 10` | **1.30** |
| `exfil.leak_platform_visit` | `leak_platform_visits >= 1` | **2.40** |
| `exfil.cloud_upload_burst` | `cloud_storage_visits >= 3` and `upload_shaped_count >= 3` | 1.25 |
| `exfil.self_send_attachments` | `self_send_count >= 1` and `attachment_count >= 1` | 1.15 |
| `exfil.external_attachment_volume` | `attachment_bytes_external` z_self >= 3.5 | 1.05 |
| `exfil.mass_email` | `max_recipients_single_email` above cohort p99 | 1.40 |
| `exfil.bcc_external` | `bcc_external_count >= 1` | 0.70 |

#### Evasion (stage 5)
| id | Fires when | Weight |
|---|---|---|
| `evade.activity_after_logoff` | Events with no open session | 1.30 |
| `evade.offhours_only_day` | `offhours_event_ratio == 1.0` and `>= 15` events | 0.95 |

### 3.3 Weight calibration

Weights are **log-odds evidence points**, and they have a defined meaning rather than being arbitrary tuning knobs:

> A weight of `w` means: observing this signal multiplies the odds that this user-day is malicious by `e^w`.

So `w = 0.69` doubles the odds; `w = 1.60` multiplies them by roughly 5; `w = 2.40` by roughly 11. This makes weights comparable, reviewable, and empirically checkable — the evaluation harness computes the *observed* log-odds ratio per rule against ground truth and reports the drift from the configured weight. A rule whose configured weight is 1.6 but whose measured evidence is 0.3 is a bad rule, and the report says so in a single column.

Initial weights come from analyst judgement; the harness corrects them. That loop is the honest answer to "how did you pick these numbers".

---

## 4. Scoring model

### 4.1 Why not a weighted sum

The naive approach — `risk = sum(weight * strength)`, clipped to 100 — has three failure modes that matter here:

1. **Score inflation.** Twelve weak signals outscore one decisive one.
2. **Redundancy stacking.** `offhours_logon`, `offhours_file_access`, and `offhours_only_day` all fire on the same underlying fact and triple-count it.
3. **No probabilistic meaning.** 70 has no interpretation, so thresholds cannot be reasoned about.

### 4.2 The model

**Step 1 — per-category saturated evidence.**
Within each category `c`, sort the signals by contribution descending and apply geometric decay:

```
E_c = Σ_{i=1..n_c}  δ^(i-1) · w_i · s_i          with δ = 0.5
```

The top signal in a category counts fully, the second at half, the third at a quarter. A category can therefore contribute at most `2 × w_max`, which structurally kills redundancy stacking.

**Step 2 — machine-learning contribution.**
The IsolationForest percentile `p` (within cohort) is mapped through a tail function so that only genuine outliers contribute:

```
φ(p) = clamp((p − p₀) / (1 − p₀), 0, 1)        p₀ = 0.95
E_ml = w_ml · φ(p)                              w_ml = 1.20  (hard cap)
```

The cap is deliberate: the model can strongly support a case but can never carry one alone. Its maximum contribution is less than a single decisive rule.

**Step 3 — correlation bonus.**
Only cross-category, ordered evidence is rewarded:

```
E_corr = w_div · (C − 1)  +  w_chain · A  +  w_prox · P
```

| Term | Meaning | Value |
|---|---|---|
| `C` | Number of *distinct categories* with at least one signal | `w_div = 0.35` per extra category |
| `A` | Number of monotonic stage advances in the incident | `w_chain = 0.30` per advance |
| `P` | Proximity factor: `1` if the median inter-signal gap is under 30 min, decaying to `0` at 12 h | `w_prox = 0.45` |

`E_corr` is set to `0` when the component is flagged `over_dense`.

**Step 4 — combine and squash.**

```
L  = L₀ + Σ_c E_c + E_ml + E_corr           L₀ = −4.6   (prior odds ≈ 0.01)
risk = 100 · σ(L / τ)                        σ = logistic,  τ = 1.8
```

The prior `L₀` encodes the base rate honestly: with no evidence at all, risk is near zero, not 50. `τ` controls how sharply evidence converts to score and is the single knob for global sensitivity.

**Worked example** — the scenario in `01-PRD` section 1.1:

| Signal | Category | w | s | Applied |
|---|---|---|---|---|
| `stage.offhours_logon` | staging | 0.65 | 0.8 | 0.52 |
| `stage.first_ever_usb` | staging | 1.60 | 1.0 | 0.80 (×δ, second in category) |
| `collect.sensitive_concentration` | collection | 0.85 | 0.9 | 0.77 |
| `exfil.file_copy_to_usb` | exfil | 1.30 | 0.7 | 0.91 |
| `exfil.cloud_upload_burst` | exfil | 1.25 | 0.6 | 0.38 (×δ) |
| ML anomaly, p = 0.991 | — | 1.20 | φ=0.82 | 0.98 |
| Correlation: C=3, A=3, P=1.0 | — | — | — | 0.70 + 0.90 + 0.45 = 2.05 |

```
L = −4.6 + (0.52+0.80) + 0.77 + (0.91+0.38) + 0.98 + 2.05 = 1.81
risk = 100 · σ(1.81 / 1.8) = 100 · σ(1.006) ≈ 73.2
```

Note the correlation term contributes more than any single rule. That is the thesis of the product, expressed in arithmetic.

### 4.3 Confidence

Computed independently of risk, from four terms in `[0, 1]`:

| Term | Definition | Weight |
|---|---|---|
| **Agreement** `A` | `1.0` if both rules and ML fire; `0.65` rules only; `0.45` ML only | 0.30 |
| **Diversity** `D` | `min(1, distinct_categories / 3)` | 0.30 |
| **Completeness** `K` | Fraction of the 5 sources present for this user-day | 0.20 |
| **Maturity** `M` | `min(1, baseline_days / 30)` | 0.20 |

```
confidence = 0.30·A + 0.30·D + 0.20·K + 0.20·M
```

Then two hard caps, which exist to protect the monitored person:

- If `M < 0.5` (baseline under 15 days), `confidence = min(confidence, 0.60)`.
- If the incident rests on a single signal, `confidence = min(confidence, 0.45)`.

Confidence is **calibrated**, not decorative: `07-EVALUATION` section 5 measures expected calibration error against ground truth, so "0.8 confidence" empirically means roughly 80% of such incidents are real.

### 4.4 Triage routing

```
confidence
   1.0 ┤  MONITOR   │  REVIEW   │   AUTO_FLAG
       │            │           │
  0.65 ┼────────────┼───────────┼──────────────
       │  MONITOR   │  REVIEW   │   REVIEW
  0.40 ┼────────────┼───────────┼──────────────
       │ SUPPRESSED │  MONITOR  │   REVIEW
   0.0 └────────────┴───────────┴──────────────
       0           40          70            100   risk
```

The load-bearing cell is **top-right-adjacent**: high risk with confidence below 0.65 routes to `REVIEW`, never `AUTO_FLAG`. That is FR-6.2, and it is the mechanism by which the system refuses to act decisively on thin evidence.

Active suppressions demote a lane by one step and record the suppression id on the incident.

### 4.5 Risk decay

A user-level rolling risk with a 7-day half-life:

```
risk_ewma(t) = α · risk(t) + (1 − α) · risk_ewma(t−1),   α = 1 − 2^(−1/7) ≈ 0.094
```

Used for the user profile trend line and for campaign detection. A `benign` verdict applies a negative adjustment, so a cleared user does not carry a permanent stain.

---

## 5. Anomaly detection design

| Decision | Choice | Reason |
|---|---|---|
| Algorithm | IsolationForest | No labels needed, CPU-cheap, handles mixed-scale features, robust in high dimensions |
| Training scope | **Per peer cohort** `(role, department)` with >= 30 members; otherwise fall back to the department, then global | A sysadmin's normal is not a salesperson's normal |
| Training window | Trailing 90 days, refit monthly | Captures seasonality without drifting into the incident under investigation |
| Features | The 56-feature matrix, `z_self` variants, rank-transformed | Rank transform removes the heavy right tail that would otherwise dominate splits |
| Contamination | `0.01` | Deliberately near the true base rate rather than sklearn's `auto` |
| `n_estimators` | 200, `max_samples=256`, `random_state=42` | Determinism (NFR-5) |
| Output | `score_samples` converted to a within-cohort percentile | Raw scores are not comparable across cohorts; percentiles are |
| Guard | Contribution capped at `w_ml = 1.20` | The black box can support but never carry a case |

**Training hygiene.** The model is fit on data *strictly before* the scored day — no target leakage, and the same code path works for streaming. Known-malicious days from ground truth are never excluded from training, because in production you would not know them; excluding them would inflate results.

**Why not an autoencoder / LSTM.** Both would add a GPU dependency, destroy interpretability, and require a training regime that 70 positive users across 17 months cannot support. IsolationForest is the right tool at this data scale, and saying so plainly is stronger than adding a deep model for its own sake.

---

## 6. Correlation algorithm

### 6.1 Graph construction

```python
def build_graph(events, signals, cfg) -> EventGraph:
    # Nodes: every event carrying a signal, plus context events within ±15 min
    nodes = signal_events | context_neighbours(signal_events, minutes=15)

    for a, b in ordered_pairs(nodes):            # sorted by ts -> deterministic
        gap = (b.ts - a.ts).total_seconds() / 60
        w   = cfg.window_for(a.source, b.source)   # per-pair window
        if gap <= w:
            add_edge(a, b, type="temporal",
                     weight=exp(-gap / w))          # closer = stronger
        if a.pc_id and a.pc_id == b.pc_id and a.user_id != b.user_id:
            add_edge(a, b, type="shared_pc", weight=0.8)
        if same_file(a, b) and a.user_id != b.user_id:
            add_edge(a, b, type="shared_file", weight=0.9)
        if stage(b) == stage(a) + 1 and b.ts > a.ts:
            add_edge(a, b, type="stage_advance", weight=1.0)
```

### 6.2 Per-pair windows

A single global window is wrong, because the meaningful latency between two actions depends entirely on which two actions they are.

| Pair | Window | Reasoning |
|---|---|---|
| `logon → device` | 90 min | Arrive, settle, then plug in |
| `device → file` | 60 min | Copy follows connection closely |
| `file → http` | 120 min | Stage locally, upload later |
| `file → email` | 120 min | Same |
| `http → http` | 30 min | Browsing sessions are tight |
| `logon → file` | 180 min | Broad working-session link |
| default | 60 min | |

### 6.3 Incident assembly

1. Connected components over the graph.
2. Discard components with fewer than 2 events or 0 signals.
3. If `component.event_count > max_component_events` (default 400), set `over_dense = true` and zero the correlation bonus — a day where everything connects carries no correlation information.
4. Assign `incident_id = INC-{date}-{user}-{nn}`.
5. Recompute risk and confidence over the component's signal set (not the whole user-day) so the incident score reflects only its own evidence.

### 6.4 Campaign linking (the slow-burn detector)

```
for each user:
    for each pair of incidents (i, j) with 0 < (j.start − i.end) <= 14 days:
        if max_stage(j) > max_stage(i):        # the chain advances
            link(i, j)
    campaign = connected components of links
    campaign.peak_risk = max(incident risks) + 0.25·(len(campaign) − 1)   # in logit space
```

This is what catches CERT scenario 1, where an insider ramps over weeks and no individual day is alarming. Without campaign linking, each day scores in the 40s and nothing surfaces; with it, the campaign clears the threshold even though no single day does.

---

## 7. Explanation

### 7.1 Narrative grammar (no LLM — see `adr/0004`)

A three-layer deterministic grammar.

**Headline** — the single most attributable signal plus the incident shape:
```
{top_signal.headline_phrase} — {n_signals} correlated signals across {n_categories} categories
```
> "First removable-media use in 8 months — 5 correlated signals across 3 categories"

**Summary** — one paragraph, assembled from ordered clause slots:
```
{who} {when_clause} {stage_sequence_clause}. {peer_clause} {context_clause}
```
> "AAF0535 (Engineer, Research) acted between 21:47 and 22:31 on 2010-08-14, progressing from off-hours access through removable-media staging to file collection and an external upload. File activity was 6.2× this user's 30-day norm and 4.1× the norm for their role. The user's departure is recorded 11 days later."

**Detail** — one bullet per signal, ordered by counterfactual contribution:
```
• [EXFIL  ·  +18.4 pts] copied 47 files while removable media was connected
                        (threshold 10; observed 47; z_self 5.8)
• [STAGE  ·  +14.1 pts] connected removable media for the first time in 243 days
• [ML     ·   +9.6 pts] behaviour in the 99.1st percentile of the Engineer/Research cohort
```

Every phrase comes from the `phrase` field of the rule that fired, with feature values interpolated. This means **the narrative is a rendering of the evidence rows**, not an independent generation — it cannot drift from the data, cannot hallucinate, runs offline, costs nothing, and is identical on every re-render. When a judge asks "how do you know the explanation is faithful?", the answer is structural: there is no path by which it could not be.

### 7.2 Counterfactual attribution

For each signal `s` in the incident, recompute the full scoring pipeline with `s` removed:

```
delta(s) = risk(S) − risk(S \ {s})
```

This is not a linear share-out. Because of category saturation and the correlation bonus, removing a signal can change the *decay position* of its siblings and can drop the category count — so the deltas are genuinely non-additive and typically sum to more than the total. That is correct behaviour and is labelled as such in the UI ("contributions overlap; they do not sum to the total"). Cost is N evaluations of a closed-form arithmetic expression: microseconds.

### 7.3 Minimal sufficient evidence set

```python
def minimal_set(signals, threshold):
    kept = sorted(signals, key=contribution, reverse=True)
    for s in reversed(kept):                  # try dropping weakest first
        if risk(kept − {s}) >= threshold:
            kept.remove(s)
    return kept
```

The analyst-facing value: *"these 2 of 7 signals are sufficient on their own to clear the threshold"* — it tells them exactly where to start the investigation and what would have to be disproved for the case to collapse.

---

## 8. Configuration

```
config/
├── detection.yaml         # weights, thresholds, L0, tau, delta, w_ml
├── rules.yaml             # the 27-rule catalogue
├── correlation.yaml       # per-pair windows, max_component_events, campaign span
├── domain_categories.yaml # domain -> category
├── triage.yaml            # the risk x confidence lane matrix
└── features.yaml          # baseline windows, warm-up, off-hours percentiles
```

At startup the engine merges these, computes `config_version = sha256(canonical_json)`, and writes it to `config_versions`. Every signal, score, and incident carries that hash. Any historical score is therefore reproducible from its stored configuration — which is what makes NFR-8 (auditability) true rather than aspirational.

---

## 9. Test strategy for the engine

| Layer | What is tested | Method |
|---|---|---|
| Features | Each feature function against a hand-built fixture day | Table-driven unit tests |
| Baselines | MAD robustness — injecting one extreme day must not move the baseline more than X | Property test |
| Rules | Every rule has a positive fixture and a negative fixture | Generated from the YAML catalogue, so a new rule without tests fails CI |
| Scoring | Monotonicity (more evidence never lowers risk); saturation (the 4th signal in a category adds under 1/8 of the first); the `L0` floor | Property tests via Hypothesis |
| Correlation | Known chains form one component; scrambled order scores lower than ordered | Synthetic event sequences |
| Counterfactual | `sum(deltas) >= total` under saturation; removing everything yields the prior | Property test |
| End-to-end | The three CERT scenarios are each detected on a seeded slice | Golden-file test with a pinned config hash |
| Determinism | Two full runs produce identical output hashes | CI check |
