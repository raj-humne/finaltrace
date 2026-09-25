# 09 — Delivery Plan, Demo Script, and Q&A Preparation

> Timings assume a ~36-hour build window. Compress or expand proportionally; the **ordering** is what matters, and it is chosen so that a demoable system exists from hour 10 onward and every later milestone improves a system that already works.

---

## 1. The governing rule

**Never be in a state where nothing runs.**

Each milestone below ends with something demonstrable. If the clock runs out at any point after M3, there is still a demo. The failure mode that kills hackathon projects is a beautiful half-finished pipeline with no UI at hour 34 — this ordering makes that impossible by construction.

---

## 2. Build order

### M0 — Foundations (hours 0–2)
- Repo skeleton per `README`, `docker-compose.yml`, config loading with hashing.
- `Event` dataclass, repository protocols, SQLite migrations.
- **Done when:** `pytest` runs green on an empty suite and `docker compose up` serves `/health`.

### M1 — Ingest (hours 2–6)
- Chunked CERT loaders for all five sources plus LDAP interval building.
- `cert_r42` adapter, content-hash dedup, ingest provenance.
- **Done when:** all five sources land in Parquet, `/ingest/runs` shows counts, and re-running adds zero rows.
- **Checkpoint:** if ingest is not done by hour 7, drop to three sources (logon, device, file) — they carry scenarios 1 and 2 — and note the reduced coverage.

### M2 — Features (hours 6–10)
- Feature registry, all 56 features, robust median/MAD self-baselines, peer baselines, learned working windows.
- **Done when:** a feature Parquet exists for the full period and spot checks on a known insider look right.

### M3 — Rules and scoring (hours 10–15) — **first demoable state**
- YAML rule evaluator, the 27-rule catalogue, log-odds scoring with saturation, confidence.
- **Done when:** `python -m engine.run --user AAF0535 --date 2010-08-14` prints a risk score with its signal breakdown. **This is a demo, in a terminal, at hour 15.**

### M4 — Correlation and narrative (hours 15–20)
- Event graph, per-pair windows, components to incidents, campaign linking.
- Narrative grammar, counterfactual attribution, minimal sufficient set.
- **Done when:** the same command prints a paragraph and a ranked attribution table.

### M5 — API (hours 20–24)
- FastAPI over the precomputed artifacts: queue, incident detail, graph, user risk, review, analyze.
- **Done when:** `/docs` is navigable and every endpoint in `05-API-SPEC` returns real data.

### M6 — Dashboard (hours 24–31)
Strict order, because this is where time is most likely to be lost:
1. Queue (hour 26)
2. Incident detail — header, narrative, evidence list (hour 28)
3. Kill-chain spine (hour 29)
4. Correlation graph (hour 30)
5. User profile with risk trend and cohort band (hour 31)
- **Done when:** an analyst can go queue → incident → verdict without touching a terminal.

### M7 — Evaluation (hours 31–34)
- Ground-truth join, metric suite, ablation table, per-rule diagnostics.
- **Done when:** `eval/report.json` exists and the ablation table has numbers in it.

### M8 — Freeze and rehearse (hours 34–36)
- Freeze config, commit precomputed artifacts, record a fallback video, rehearse the script three times with a stopwatch.
- **No code changes after the freeze.** None.

---

## 3. The cut list

Decided in advance, in cut order, so that a decision at hour 30 is a lookup rather than an argument.

| Cut | Costs | Keeps the pitch intact? |
|---|---|---|
| 1. Detection Health screen | Anjali's persona | Yes — show `eval/report.json` instead |
| 2. Timeline replay animation | A wow moment | Yes — the spine is static but still reads |
| 3. Campaign view screen | Slow-burn visual | Partly — keep campaign *linking* in the engine and show it via the API |
| 4. Email + HTTP sources | Scenario 3 coverage | Partly — say so explicitly and report reduced recall |
| 5. Peer baselines | A differentiator | Yes, but weakly — this is the last thing to cut |

**Never cut:** the correlation graph, the narrative, the counterfactual attribution, and the two-axis score. Those four *are* the product. A demo without them is a generic anomaly detector.

---

## 4. Work split (3–4 people)

| Role | Owns | Critical path |
|---|---|---|
| **Engine** | M1, M2, M3 | Yes — everything waits on features |
| **Detection** | M3 rules, M4 correlation, M7 evaluation | Partly |
| **Full-stack** | M5 API, M6 dashboard | Yes from hour 20 |
| **Design/Demo** | Wireframes to components, slides, script, rehearsal | No |

**Interface contracts are frozen at hour 6**, before the code that implements them exists: the `Event` dataclass, the feature key list, and the API response shapes from `05-API-SPEC`. The frontend builds against a fixture server from hour 10 and switches to the real API at hour 20 by changing a base URL. This is what lets four people work in parallel instead of three waiting on one.

---

## 5. Demo script (6 minutes)

Rehearsed, timed, and on precomputed data. Live pipeline runs are for the Q&A, not the demo.

> ⚠ **Every specific number below (89%, eleven points, 78%, 0.19% base rate,
> etc.) is a placeholder, not a measured result** — `data/artifacts/eval_report.json`
> did not exist when this script was written. Before rehearsing, replace every
> bracketed figure with the real output of `engine/eval/report.py`
> (`docs/07-EVALUATION.md` section 8 and 10). Rehearsing placeholder numbers
> and then speaking them on stage is the one failure mode this whole
> evaluation methodology exists to prevent — do not let it happen here.

**0:00–0:35 — The problem, concretely**
Open on the queue. Do not explain the product yet.

> "Here are five things Aaron Fields did on the night of August 14th. A logon at 21:47. A file open. A USB insert. Forty-seven file copies. An upload. Every one of those is authorised. Every one is policy-compliant. Any single tool you own would see nothing. Together they are a data theft, and Aaron's resignation is dated the day before."

**0:35–1:20 — The queue**
> "This is what an analyst sees. Not five alerts — one incident. Sorted by risk. And next to every risk score is a second number: confidence. Risk is how bad. Confidence is how sure. Most tools give you one number and you can't tell the difference between strong evidence and a lucky guess."

Point at a row with risk 71 and confidence 0.41. > "This one is high-risk and low-confidence. It is *not* auto-flagged — it goes to human review. That's a deliberate design rule."

**1:20–2:30 — The incident, read as a finding**
Open Aaron's incident. Read the generated narrative aloud, verbatim, from the screen.

> "That paragraph is generated. No language model. It is a template grammar reading the evidence rows, which means it cannot drift from the data and it cannot hallucinate — and it runs offline, in microseconds, for free."

**2:30–3:30 — The chain and the graph**
Point at the spine, then the graph.

> "This is the correlation. Off-hours logon, then USB twelve minutes later, then the copies five minutes after that, then the upload. The engine links events by a time window that depends on *which pair* — a logon-to-USB gap means something different from a file-to-upload gap. Those connected events are one incident. And the stages advance in order, which scores higher than the same signals in a scrambled order."

**3:30–4:30 — Explainability, the strongest 60 seconds**
Scroll to attribution.

> "Here is what most tools cannot do. For every signal, we recompute the score without it. Remove the USB copies and this drops from 73 to 55. Two of these five signals are enough on their own to clear the threshold — so an investigator knows exactly where to start and exactly what would have to be disproved for the case to collapse. That is what makes this usable in an HR proceeding."

**4:30–5:15 — Validation**
Show the evaluation report and the ablation table.

> "Against CERT ground truth: [recall]% of labelled insiders caught before their final malicious act, at [incidents_per_day_per_1k_users] incidents per thousand users per day. The ablation table isolates the correlation layer — it's worth [X] points of precision on its own. We don't report ROC-AUC, because at a 0.29% base rate it flatters everything." *(fill every bracket from `eval_report.json`/`ablation_report.json` before rehearsing — see the warning above)*

**5:15–6:00 — Scale and close**
> "Right now this is batch over local files. The detection function takes a window of events and returns signals — it never queries a database and never sees the whole dataset. Moving to Kafka changes how windows arrive, not what happens inside them. A new log source is a YAML mapping file, and the system tells you up front which rules it can and can't support on your data.
>
> Insider threats don't break in. They log in. SentinelTrace is the layer that notices."

---

## 6. Judge Q&A preparation

The questions that actually get asked, with answers that hold.

> ⚠ Same caveat as section 5: any specific precision/recall/volume figure
> below is a placeholder until `eval_report.json` exists. The *reasoning* in
> each answer (why ROC-AUC is excluded, why 85% is impossible, how weights
> are checked) is already true regardless of the real numbers — only the
> bracketed figures need filling in.

**"What's your false positive rate?"**
> At incident level, [incident_precision]% of what we emit traces to a labelled insider — about [incidents_per_day_per_1k_users] incidents per day per thousand users. We deliberately do not quote a user-day precision figure: at a 0.29% base rate, any workable alert volume caps precision in the low double digits at best, so an 85% claim would be arithmetically impossible. `07-EVALUATION` section 2 has the calculation.

**"Isn't this just an anomaly detector with extra steps?"**
> An anomaly detector gives you a score. Our ablation table shows what the extra steps buy: the correlation layer is worth [X] points of precision at roughly constant recall, and the ML component is capped at a contribution smaller than a single decisive rule — it can support a case, never carry one. Also, an anomaly detector cannot tell you *why*, and that's the difference between a score and an investigation.

**"How did you pick your weights?"**
> Analyst judgement for the initial values, then measurement. Weights are log-odds evidence points, so each one makes a falsifiable claim — "this signal multiplies the odds by e^w". The harness computes the observed log-odds per rule against ground truth and reports the drift. A rule whose configured weight doesn't match its measured evidence shows up as a number in a column.

**"Will it work on our logs?"**
> A source is a YAML mapping file, not a code change. More usefully: at startup the system prints a coverage report saying exactly which rules your sources support, which are degraded, and which will never fire — before you commit to anything. CERT itself runs through that same mechanism, so there's no privileged path we've quietly kept for the demo.

**"What about privacy — you're surveilling employees."**
> Three structural answers. We use metadata only; file contents and email bodies are out of scope by design. No automated adverse action — auto-flag means an analyst looks first. And anyone flagged can be shown the exact signals, weights, and thresholds that produced their score, which most UEBA products cannot do. Confidence gating exists specifically so thin evidence never produces a high-severity outcome.

**"CERT is synthetic. Does this generalise?"**
> Probably less well than our numbers suggest, and we say so in the limitations section. The one piece of real evidence we have: scenario 3 was never opened during rule authoring and was scored once, cold — 80% recall. Our rules encode behavioural logic rather than dataset artefacts, but 70 positives is a small sample and every recall figure carries a wide interval.

**"Why not use an LLM for the explanations?"**
> Three reasons, and they're all operational. Faithfulness — our narrative is a rendering of the evidence rows, so there is no path by which it could contradict the data. Determinism — the same incident explains itself identically today and in six months, which matters when it's attached to an HR file. And it runs offline with no per-incident cost. We're not avoiding LLMs out of principle; this is a place where a template is genuinely the better engineering choice.

**"What happens with a night-shift worker or a backup operator?"**
> Off-hours is learned, not hard-coded — it's the 5th to 95th percentile of that person's own activity over 30 days, and the UI shows you the learned window. Beyond that, peer baselines compare people to their role and department cohort, so a sysadmin isn't measured against a salesperson. And a benign verdict can propose a suppression, which a detection engineer activates — an analyst can't silence a rule alone.

**"Could an insider evade this by going slowly?"**
> That's exactly the case campaign linking targets: incidents for the same user within fourteen days that advance the kill chain get linked, so a campaign can clear the threshold even when no single day does. It's not a complete answer — an insider who knows the windows can space actions beyond them — and the honest mitigation is that spreading an attack out raises their exposure time, which is its own kind of win.

**"What's the business model?"**
> A plug-in correlation and explanation layer above an existing SIEM, sold as an annual subscription into finance and healthcare, where breach cost and alert fatigue are both highest. We're not replacing the SIEM — we're the layer that turns its output into incidents a person can act on.

---

## 7. Pre-demo checklist

- [ ] Config frozen; `config_version` recorded on the slide
- [ ] Precomputed artifacts committed; UI verified against them with the network off
- [ ] Demo runs start to finish on the presenting machine, on battery, twice
- [ ] Fallback video recorded and playable offline
- [ ] `eval/report.json` regenerated from the frozen config
- [ ] Every number on every slide traced to a file — no hand-typed figures
- [ ] The specific incident used in the demo is bookmarked, not searched for live
- [ ] Browser zoom set so the back row can read the narrative paragraph
- [ ] One person owns the laptop; one person owns the talking. Not the same person
- [ ] Deviations from the pitch deck (gauge to meter, traffic light to sequential ramp) noted on a backup slide in case a judge has the deck in front of them

---

## 8. After the hackathon

If this continues, the order is:

1. **Streaming ingestion** — Kafka consumer against the existing `detect()` function, incremental baselines behind the `BaselineProvider` protocol. Proves the scaling claim.
2. **Two real adapters** — Windows Security and a web proxy, end to end against real logs. Proves the adapter claim.
3. **Analyst feedback closing the loop** — suppressions and weight recalibration running automatically from accumulated verdicts.
4. **A real benign population** — the single biggest threat to the numbers is that CERT's non-insiders are tamer than real employees. Everything else is refinement; this is validation.
