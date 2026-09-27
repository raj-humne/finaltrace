# 01 — Product Requirements Document

**Product:** SentinelTrace — Behavioural Threat Detection & Incident Correlation
**Version:** 1.0 (hackathon scope) · **Status:** Approved for build · **Owner:** Team SentinelTrace

---

## 1. Problem statement

### 1.1 The gap

Perimeter security assumes the attacker is outside. Insider threats and compromised-credential attacks invalidate that assumption: the actor holds valid credentials, passes every authentication check, and touches only systems they are entitled to touch. A firewall has nothing to block. A signature engine has no signature to match.

What makes these attacks detectable is **not any single action** — it is the *shape* of a sequence:

```
21:47  logon        PC-4412  (own machine, but 3h after normal last-activity)
21:51  file  open    3 finance spreadsheets from a share read ~2x/month
21:59  device       USB storage connected  (first time in 8 months)
22:04  file  copy    x14 to removable media
22:31  http  upload  to a personal cloud-storage domain
```

Every line is a legitimate, authorised, policy-compliant action. The sequence is a data theft.

### 1.2 What is broken today

| Pain | Consequence |
|---|---|
| Alerts fire per-event, per-tool, in silos | Analyst sees 5 unrelated low-severity alerts instead of 1 critical incident |
| Low-fidelity rules tuned for recall | Alert fatigue; real signal buried in noise |
| Detection scores with no explanation | Analyst cannot triage or justify escalation to HR/Legal |
| No confidence dimension | Team either escalates on thin evidence or ignores real risk |
| Slow-burn campaigns spread over weeks | Each day looks normal; the correlation window is too short to see the campaign |
| ML models are black boxes | Cannot be used in HR proceedings; cannot be tuned; cannot be trusted |

### 1.3 Why now

Insider incidents are the slowest and most expensive class of breach to contain, and the tooling market is split between (a) SIEM correlation rules that are hand-written and brittle, and (b) UEBA products that are opaque, expensive, and enterprise-only. There is a real gap for an **explainable, lightweight, correlation-first** layer.

---

## 2. Goals and non-goals

### 2.1 Goals (what v1 must do)

| # | Goal | How it is measured |
|---|---|---|
| G1 | Turn multi-source raw logs into per-user-per-day behavioural features | 5 sources ingested; >= 40 features per user-day |
| G2 | Detect anomalous behaviour with a hybrid engine (rules + ML), not a single model | Both subsystems contribute independently to every score |
| G3 | Correlate related signals into a **single** incident instead of N alerts | Alert-to-incident compression ratio >= 4:1 |
| G4 | Every incident carries a plain-English narrative, with no LLM in the loop | 100% of incidents have a generated narrative |
| G5 | Every score is fully attributable — signal, weight, contribution | Counterfactual delta available for every contributing signal |
| G6 | Route by confidence, not just risk | Three triage lanes: auto-flag / review / monitor |
| G7 | Validate against CMU CERT ground truth | See section 7 |
| G8 | Investigation UI an analyst can use unaided | Analyst completes triage of an incident in under 90 s |

### 2.2 Non-goals (explicitly out of scope for v1)

- **Real-time streaming.** v1 is batch over precomputed local data. The scaling path is designed (`02-ARCHITECTURE` section 8) but not built.
- **Real remediation enforcement.** SentinelTrace now supports configurable, simulated automated remediation through a webhook-based mitigation pipeline (see `docs/11-MITIGATION.md`): when a correlated incident's threat weight exceeds a configurable threshold, it automatically dispatches a structured JSON payload to a remediation webhook and simulates isolating the flagged entity, recording every action for analyst auditability. It does not actually disable real accounts, quarantine real hosts, or block real egress — production deployment would require integration with the organization's approved IAM/network/DLP remediation systems.
- **Network packet inspection / DLP content analysis.** We reason over metadata (who, what, when, where), not file contents.
- **Multi-tenancy, SSO, RBAC.** Single-tenant, single analyst role in v1.
- **LLM-generated narratives.** Deliberately excluded — see `adr/0004`.
- **External intrusion / malware detection.** Different problem, different signals.

### 2.3 Anti-goals (things we refuse to do even if asked)

- Ship a score without an explanation.
- Auto-escalate to HR without a human review gate.
- Quote a precision number the base rate makes mathematically impossible (`07-EVALUATION` section 2).

---

## 3. Users and personas

### Persona A — Priya, Tier-1 SOC Analyst (primary)
- Works a queue. 200+ alerts per shift across tools. Judged on mean-time-to-triage.
- **Needs:** to know in 10 seconds whether an item deserves 10 minutes.
- **Pain:** context-switching between five consoles to assemble one story.
- **Success:** opens an incident, reads one paragraph, sees the timeline, decides. No pivoting.

### Persona B — Rohit, Insider Threat Lead (secondary)
- Runs formal investigations. Interfaces with HR, Legal, and management.
- **Needs:** a defensible evidence trail. "Why did the system flag this person?" must have a written answer.
- **Pain:** black-box UEBA scores are inadmissible in an HR proceeding.
- **Success:** exports an incident with full signal / weight / threshold provenance.

### Persona C — Anjali, Detection Engineer (tertiary)
- Owns tuning. Cares about FP rate and coverage.
- **Needs:** to see which rule fired how often, with what precision, and change its weight.
- **Success:** adjusts a weight, re-runs eval, sees the precision/recall delta immediately.

### Non-user: the monitored employee
Ethically significant, has no interface. Their protection is: confidence gating (no action on thin evidence), mandatory human review before escalation, and full auditability of every decision. This is a **product requirement**, not a footnote — see section 9.

---

## 4. User stories

**Triage**
- As Priya, I see a queue of incidents sorted by risk, so the worst is first.
- As Priya, I see risk *and* confidence as separate values, so I know when a high score rests on thin evidence.
- As Priya, I read a one-paragraph narrative before opening any raw log.
- As Priya, I see the correlation graph, so I can visually confirm the signals are actually related in time.

**Investigation**
- As Rohit, I select a user and a date range and see their risk trend over time.
- As Rohit, I replay a day of activity as an animated timeline with the risk score climbing.
- As Rohit, I see, for each contributing signal, exactly how many points it added.
- As Rohit, I see the counterfactual: what the score would be without each signal.
- As Rohit, I compare this user against their peer-group baseline, not only their own history.

**Feedback**
- As Priya, I mark an incident confirmed / benign / inconclusive with a note.
- As Anjali, benign verdicts feed back into threshold calibration and suppression rules.
- As Anjali, I see per-rule precision computed from analyst verdicts.

---

## 5. Functional requirements

### FR-1 — Ingestion
- **FR-1.1** Load five CERT log types: `logon`, `device`, `file`, `http`, `email`.
- **FR-1.2** Join to `LDAP` org data (role, department, supervisor, team) for peer grouping.
- **FR-1.3** Normalise all records into a unified `Event` model: `(event_id, user, pc, timestamp, source, action, attributes{})`.
- **FR-1.4** Ingestion is idempotent — re-running on the same file produces no duplicates (content-hash dedup).
- **FR-1.5** Record ingestion provenance: source file, row count, time range, parse errors.
- **FR-1.6** `POST /ingest` accepts a batch and reports per-source accepted / rejected counts.

### FR-2 — Feature extraction
- **FR-2.1** Produce a `UserDayFeature` row per (user, date) with >= 40 numeric/boolean features across all five sources (catalogue in `03-DATA-MODEL` section 4).
- **FR-2.2** Compute **self-baselines**: trailing 30-day rolling mean and sigma per user per feature, with a 14-day minimum warm-up.
- **FR-2.3** Compute **peer-baselines**: the same statistics over the user's role + department cohort.
- **FR-2.4** Emit both `z_self` and `z_peer` for every baselined feature.
- **FR-2.5** Mark `is_first_ever` for categorical firsts (first USB use, first access to a PC, first visit to a domain category).

### FR-3 — Detection
- **FR-3.1** Rule engine evaluates a declarative rule catalogue (YAML) against each user-day.
- **FR-3.2** Each rule emits a `Signal` with rule id, category, kill-chain stage, strength (0–1), weight, evidence event ids, and a human-readable phrase.
- **FR-3.3** IsolationForest anomaly detector trained per peer-cohort on the feature matrix; outputs a percentile-normalised anomaly score.
- **FR-3.4** Risk score combines rules and ML through a **log-odds additive model with per-category saturation** (`04-DETECTION-ENGINE` section 4), bounded 0–100.
- **FR-3.5** Confidence score computed independently from evidence diversity, data completeness, baseline maturity, and rule/ML agreement.
- **FR-3.6** All weights, thresholds, and windows live in a versioned config file, never in code.

### FR-4 — Correlation
- **FR-4.1** Build an event graph per user-day; connect events within a configurable time window (default 60 min, with per-pair overrides).
- **FR-4.2** Connected components of >= 2 events become an `Incident`.
- **FR-4.3** Cross-user edges where events share a PC or a file, enabling lateral-movement detection.
- **FR-4.4** **Campaign linking:** incidents for the same user within 14 days that advance the kill chain are linked into a `Campaign` — this is the slow-burn detector.
- **FR-4.5** Correlation adds a bonus to risk only when signals span **different categories**; redundant co-occurring signals must not inflate the score.

### FR-5 — Explanation
- **FR-5.1** Generate a deterministic plain-English narrative from a template grammar — no LLM.
- **FR-5.2** The narrative names what happened, when, why it is unusual (vs self and vs peers), and which kill-chain stage it represents.
- **FR-5.3** **Counterfactual attribution:** for each signal, report the delta in risk if that signal were removed.
- **FR-5.4** Report the **minimal sufficient evidence set** — the smallest subset of signals that still clears the alert threshold.

### FR-6 — Triage routing
- **FR-6.1** Route each incident on the (risk, confidence) plane into `AUTO_FLAG`, `ANALYST_REVIEW`, `MONITOR`, or `SUPPRESSED`.
- **FR-6.2** High risk with low confidence must **never** auto-flag — it routes to review.
- **FR-6.3** Analyst verdict (`confirmed_threat` / `benign` / `inconclusive`) plus note recorded with actor and timestamp.
- **FR-6.4** Benign verdicts create candidate suppression rules for engineer approval.

### FR-7 — API and UI
- **FR-7.1** REST API per `05-API-SPEC.md`.
- **FR-7.2** Dashboard screens per `06-FRONTEND-DESIGN.md`: Queue, Incident Detail (graph + timeline + evidence), User Profile, Detection Health.
- **FR-7.3** Timeline replay animates a day of events with a live-climbing risk score.

### FR-8 — Evaluation
- **FR-8.1** Load CERT ground-truth answer files and label user-days, incidents, and insiders.
- **FR-8.2** Compute the metric suite in `07-EVALUATION.md` and write a report artifact.
- **FR-8.3** Produce a per-rule precision / recall / lift table, so weak rules are visible.

---

## 6. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | Full pipeline run over CERT r4.2 | <= 15 min on a laptop CPU, no GPU |
| NFR-2 | API p95 latency, cached queries | < 200 ms |
| NFR-3 | Incident detail endpoint | < 500 ms including graph payload |
| NFR-4 | Memory ceiling | <= 4 GB (chunked ingestion; never load 32M rows at once) |
| NFR-5 | Determinism | Same input + same config + fixed seed produces byte-identical output |
| NFR-6 | Explainability | Zero unexplained scores. An incident without a narrative is a bug, not a degraded state |
| NFR-7 | Offline demo | Runs with no internet; precomputed artifacts committed |
| NFR-8 | Auditability | Every score reproducible from stored signal rows plus config version |
| NFR-9 | Config-over-code | Adding a rule requires no Python change |

---

## 7. Success metrics

> **Read `07-EVALUATION.md` before quoting any number.** Its headline finding: *"85% precision" is not achievable at the user-day level* given the base rate, and claiming it invites a fatal question from a technical judge. The metrics below are the defensible reframing.

### 7.1 Primary (detection quality)

| Metric | Definition | Target | Stretch |
|---|---|---|---|
| **Insider recall** | Fraction of labelled malicious insiders flagged at least once *before their final malicious act* | **>= 0.85** | 0.93 |
| **Incident precision** | Of emitted incidents, the fraction attributable to a labelled insider | **>= 0.50** overall | 0.65 |
| **Auto-flag precision** | Same, restricted to the `AUTO_FLAG` lane | **>= 0.75** | 0.85 |
| **User-day PR-AUC** | Area under the precision-recall curve at user-day granularity | **>= 0.35** (~350x base-rate lift) | 0.50 |
| **Median time-to-detect** | Malicious-active days elapsed before the first flag | **<= 2 days** | 1 day |

### 7.2 Secondary (operational)

| Metric | Target |
|---|---|
| Alert volume | <= 0.5 incidents/day per 1,000 monitored users |
| Alert-to-incident compression | >= 4 correlated signals per incident on average |
| Narrative coverage | 100% |
| Analyst triage time (measured in demo) | < 90 s per incident |
| Confidence calibration error (ECE) | <= 0.10 |

### 7.3 Hackathon judging proxies

- The live demo runs end-to-end without a crash.
- The correlation graph renders legibly in under 2 s.
- Every claim on a slide has a doc section behind it.
- We can answer "what is your false positive rate and why should we believe it" with a number *and* a methodology.

---

## 8. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Extreme class imbalance** (~0.05–0.1% malicious user-days) | Certain | High | Do not optimise accuracy. Evaluate at incident level with an alert budget; use PR-AUC and precision@k, never ROC-AUC |
| **False positives from miscalibrated thresholds** | High | High | Confidence gating; peer-group baselines to catch "always weird" users; analyst feedback loop; per-rule precision tracking |
| **Overfitting to CERT synthetic patterns** | Medium | High | Rules encode *behavioural logic*, not dataset artefacts. Hold out scenario 3 during rule authoring and report on it cold. Document as a known limitation |
| **Unsupervised model unstable across runs** | Medium | Medium | Fixed seed; percentile-normalised output; the model is capped at a bounded contribution to total risk so it cannot dominate |
| **Correlation window too wide, everything connects** | Medium | Medium | Cross-category requirement for the correlation bonus; per-pair-type windows; a graph-density guard that degrades to no-bonus when a component exceeds N events |
| **Cold start / sparse users** | High | Low | 14-day warm-up gate; confidence penalised by baseline maturity; peer baseline substituted when the self-baseline is immature |
| **Demo fails live** | Medium | Fatal | Precomputed artifacts committed; the UI reads from a snapshot; the full pipeline has a recorded fallback |
| **Ethical / privacy objection from judges** | Medium | Medium | Section 9 exists and is on a slide. Human-in-the-loop is a product requirement, not a disclaimer |
| **Scope creep** | High | High | Section 2.2 non-goals are binding. The delivery plan (`09`) is ordered so a demo exists at every checkpoint |

---

## 9. Ethics, privacy and governance

This product monitors people. That requires explicit guardrails, built in rather than bolted on.

1. **Human-in-the-loop is mandatory.** No automated adverse action. `AUTO_FLAG` means "an analyst sees this first", not "the account is disabled".
2. **Confidence gating protects the monitored.** Thin evidence never produces a high-severity outcome, regardless of risk score.
3. **Explainability is a subject right, not a feature.** Anyone flagged can be shown the exact signals, weights, and thresholds behind the score.
4. **Metadata only.** We reason over who / what / when / where. File contents and email bodies are out of scope by design.
5. **No protected-attribute features.** Peer grouping uses role and department — job function, never demographic attributes.
6. **Proportionality.** Rules target exfiltration-shaped behaviour, not productivity or personal browsing. A rule that would flag "spends a lot of time on news sites" is out of scope.
7. **Audit trail.** Every verdict, suppression, and config change is recorded with actor and timestamp.
8. **Data minimisation and retention.** Raw events age out; derived features and incidents persist. The retention window is configurable.

---

## 10. Assumptions

- CERT r4.2 is available locally and its schema matches the published format.
- Ground-truth answer files identify malicious users and the time ranges of their activity.
- Logs are clock-synchronised; time-skew reconciliation is not solved in v1.
- One user equals one identity. Account-to-person resolution is assumed already done.
- The demo environment is a single laptop, CPU-only, offline-capable.

## 11. Open questions (tracked, not blocking)

| # | Question | Owner | Resolution path |
|---|---|---|---|
| OQ-1 | Exact per-scenario insider counts in the local r4.2 copy | Data | Read `answers/` on first ingest; fill into `07-EVALUATION` section 1.2 |
| OQ-2 | Correlation window default — 60 min vs adaptive | Detection | Sweep 15/30/60/120 min on held-out data; pick by incident PR-AUC |
| OQ-3 | Should campaign linking span 14 or 30 days? | Detection | Sweep against scenario-1 slow-burn cases |
| OQ-4 | Postgres vs SQLite for the live demo | Platform | SQLite by default for the demo; the compose file ships both — see `adr/0005` |
