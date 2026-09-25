# Claude Code working prompts

Paste-ready prompts for building SentinelTrace. Section 1 is the master prompt —
**prepend it to every track prompt**, because each Claude Code session starts
cold and knows nothing about this project.

Sections 3–6 are four tracks that can run in **separate sessions in parallel**.
File ownership is disjoint, so they will not fight each other over the same
files.

---

## 1. Master prompt (prepend to every session)

```
You are working on SentinelTrace, a behavioural insider-threat detection and
incident correlation engine. Repo root: C:\Users\Janhavi Pandey\Desktop\SentinelTrace

READ THESE FIRST, IN THIS ORDER:
  docs/01-PRD.md              (sections 2, 5, 6 - scope and requirements)
  docs/02-ARCHITECTURE.md     (sections 1, 3, 4 - module boundaries)
  the doc named in your track below

The specification in docs/ is the contract. It is complete and already reviewed.
Implement it. Do not redesign it. If you believe a spec decision is wrong, say so
in one or two sentences and then implement it as written unless I say otherwise.
The six ADRs in docs/adr/ record decisions that are settled - do not re-litigate
them.

NON-NEGOTIABLES:
1. No mocks, no stubs, no placeholder data, no "TODO: implement". Every function
   either works or is not written yet. If something cannot be finished, say which
   part and why, and leave the rest working.
2. Real CMU CERT r4.2 is the only source for any reported number or the demo. The
   synthetic generator in tools/generate_synthetic.py is for the dev loop and
   pytest fixtures ONLY.
3. Config over code. Rules, weights, thresholds and windows live in config/*.yaml.
   Adding a rule must never require a Python change.
4. Determinism. Fixed seeds, sorted iteration, no wall-clock reads inside the
   engine. Two runs on the same input must produce identical output (NFR-5).
5. Explainability is a data structure, not a rendering step. Signals, weights and
   counterfactuals are stored rows. An incident without a narrative is a bug.
6. engine/ imports nothing from api/. The engine is a library, not a service.
7. Never claim something works without running it. Run it, paste the real output.
   If it fails, fix it before moving on. "Should work" is not acceptable.

CURRENT STATE:
  Working and verified:
    engine/core/config.py      - merges 6 YAML files, hashes to config_version,
                                 validates rules at load time
    engine/core/models.py      - Event, Signal, ScoreBreakdown, ConfidenceTerms,
                                 UserDayScore
    engine/ingest/loader.py    - vectorised CERT adapter, 5 sources + LDAP with
                                 departure detection. 13.8s / 792K rows.
    config/rules.yaml          - all 27 rules, declarative
    tools/generate_synthetic.py - CERT-schema fixture generator, 3 scenarios
  Written but NEVER EXECUTED (assume it has bugs):
    engine/features/extract.py
  Empty: engine/detect, correlate, explain, route, eval; all of api/ and web/

Environment: Windows, Python 3.11, pandas 2.3.1, numpy 1.26.4, scikit-learn 1.3.2.
Use the Bash tool (Git Bash), not PowerShell, for multi-step shell work.

Work in small verified steps. After each module: run it, show the output, then
continue. Tell me when a track step is done and what the real measured result was.
```

---

## 2. Session 0 — CERT data (run this first, alone)

This blocks Track A's real-data verification and all of Track D. Do it before
anything else.

```
[MASTER PROMPT ABOVE]

TRACK: Data onboarding. Read docs/03-DATA-MODEL.md section 1 and
docs/07-EVALUATION.md section 1.

The real CERT r4.2 download has landed in data/raw/ as r4.2.tar.bz2 (4.49 GB)
and answers.tar.bz2 (1.2 MB).

1. Extract both. r4.2 expands to roughly 40 GB - check free disk space FIRST and
   stop and tell me if there is not enough. Extract answers.tar.bz2 first since
   it is small.

2. Before writing any parser, READ the actual files:
   - list what r4.2 contains and the header row of each of the five CSVs
   - list what answers/ contains and show me a sample of each distinct format
   CERT's answer format varies per scenario. Do not guess it. Show me what is
   actually there, then write the parser against that.

3. Confirm our loader handles the real schema. Run engine/ingest/loader.py
   against the real files on a single month first, not the whole corpus. Report:
   rows read, rows accepted, rows rejected with reasons, and the time taken.
   Fix any schema mismatch in the adapter. Do not change the canonical Event
   model to accommodate CERT - that is what the adapter is for.

4. Write engine/ingest/ground_truth.py producing a dataframe of
   (user_id, date, scenario, is_malicious). Then report the REAL dataset profile
   and write it to data/artifacts/dataset_profile.json:
     total users, total user-days with activity, number of insiders,
     malicious user-days, and the resulting base rate.
   docs/07-EVALUATION.md section 1.2 lists these as OQ-1 - this resolves it.
   Every later metric is computed from this file. Nothing is hand-typed.

5. Run the full ingest over the whole corpus once and report wall-clock time and
   peak memory. NFR-1 caps it at 15 minutes, NFR-4 at 4 GB.
```

---

## 3. Track A — Engine (critical path, one session, sequential)

**Do not parallelize this track.** Each step feeds the next; splitting it creates
merge conflicts and inconsistent interfaces.

```
[MASTER PROMPT ABOVE]

TRACK A: Detection engine. Read docs/04-DETECTION-ENGINE.md IN FULL - it is the
core specification and everything below implements it. Also read
docs/03-DATA-MODEL.md section 4 (the feature catalogue).

You own these paths. Do not edit anything outside them:
  engine/features/  engine/detect/  engine/correlate/  engine/explain/
  engine/route/  engine/run.py  tests/test_features* tests/test_detect*
  tests/test_correlate*

Work in this order, verifying each before starting the next.

A1. engine/features/extract.py has NEVER been run. Run it against the synthetic
    fixture and fix it. Known suspects: it references a column a_filename that
    the ingest layer never emits (only a_extension); the http category pivot
    drops columns when a category never appears in the data; webmail_visits may
    be missing. Then prove it works on signal, not just on shape: take the
    insiders listed in data/raw/answers.json and show that their malicious days
    have elevated file_events_during_usb, is_first_ever_usb, leak_platform_visits
    and offhours_event_ratio versus their own normal days. Paste the comparison.

A2. engine/features/baseline.py - robust self-baseline (median/MAD, trailing 30d,
    14d warm-up) and peer baseline over cohort_key. Emit z_self and z_peer for
    every feature in the baselined_features list in config/features.yaml.
    MAD not std: write a test proving one injected extreme day moves a MAD
    baseline less than it moves a std baseline. That is the whole reason for the
    choice and it should be provable.

A3. engine/detect/rules.py - evaluate config/rules.yaml against a feature row.
    Closed operator set only, no eval, no expression language. Emit Signal with
    strength from the declared scale and the phrase rendered with real values.
    Honour requires_baseline by suppressing self-baseline rules during warm-up.
    Generate a positive and negative fixture test per rule FROM the catalogue, so
    a new rule without tests fails CI.

A4. engine/detect/anomaly.py - IsolationForest per cohort (min 30 members, else
    department, else global). Fit strictly on data BEFORE the scored day - no
    leakage. Convert score_samples to a within-cohort percentile, then the tail
    function. Contribution hard-capped at ml_weight. Do NOT exclude known
    malicious days from training: in production you would not know them, and
    excluding them inflates results.

A5. engine/detect/scoring.py - the log-odds model, docs/04 section 4. Per-category
    geometric saturation, capped ML term, correlation bonus, L0 and tau from
    config. Confidence from the four terms plus both hard caps.
    Property-test with hypothesis: more evidence never lowers risk; the 4th signal
    in a category adds under an eighth of the first; zero signals lands at the
    prior. Reproduce the worked example in docs/04 section 4.2 and confirm it
    scores ~73.2.

A6. engine/correlate/graph.py + incident.py - per-pair time windows from
    config/correlation.yaml, connected components to incidents, over_dense guard,
    cross-user edges on shared PC and shared file, campaign linking over 14 days
    on stage advance. Test that an ordered kill-chain scores higher than the same
    signals scrambled in time.

A7. engine/explain/narrative.py + counterfactual.py - deterministic template
    grammar, NO LLM. Counterfactual by re-running the scoring function with each
    signal removed. Minimal sufficient set by greedy drop. Assert the narrative
    is byte-identical across two runs.

A8. engine/route/triage.py - the risk x confidence lane matrix from
    config/triage.yaml. Test explicitly that high risk + low confidence routes to
    ANALYST_REVIEW and never AUTO_FLAG. That is FR-6.2 and it is the safety
    property of the whole product.

A9. engine/run.py - CLI. Full pipeline to Parquet, plus
    --user X --date Y printing one scored day with its full breakdown.
    Show me that command running against a real insider and its real output.
```

---

## 4. Track B — API and real auth (parallel, independent)

Depends only on the frozen contract in `docs/05-API-SPEC.md`, not on Track A's
code. Build against fixtures; swap to real artifacts when Track A lands.

```
[MASTER PROMPT ABOVE]

TRACK B: API and authentication. Read docs/05-API-SPEC.md IN FULL and
docs/03-DATA-MODEL.md section 5 (the DDL).

You own: api/  alembic/  tests/test_api* tests/test_auth*
Do not edit anything under engine/ - if you need something from the engine that
does not exist yet, define the interface you need and work against a fixture.

B1. SQLAlchemy models for every table in docs/03 section 5, plus Alembic
    migrations. SQLite for local, Postgres via compose. The SQLite/Postgres
    difference lives ONLY in the dialect layer - no engine or API code branches
    on which database is in use.

B2. REAL authentication. The spec's "static bearer token" is a placeholder and is
    explicitly replaced:
      - users table with Argon2id hashes via argon2-cffi. Never plaintext,
        never a reversible encoding, never a default password in any file.
      - session tokens: 256-bit from secrets.token_urlsafe, stored server-side
        in a sessions table with sliding expiry, delivered as an httpOnly
        SameSite=Strict cookie
      - RBAC: role 'analyst' (read, record verdicts) and 'detection_engineer'
        (additionally activate suppressions). Enforced by a FastAPI dependency
        on the route. Never by hiding a button in the frontend.
      - account lockout after 5 failed attempts with exponential backoff
      - constant-time comparison on every secret
      - every login, logout, failure, and privileged action appends to audit_log
      - a CLI command to create the first user that PROMPTS for a password
    Tests that must pass: wrong password rejected; lockout actually triggers;
    an analyst calling the suppression-activation endpoint gets 403; an expired
    session is rejected; audit rows are written for each of those.

B3. Routers for every endpoint in docs/05 section 1. Match the documented
    response shapes exactly - the frontend generates its types from this schema,
    so a shape mismatch becomes a frontend build error.
    Note POST /incidents/{id}/review: a benign verdict may PROPOSE a suppression,
    but it is created with status 'proposed' and does NOT take effect until a
    detection_engineer activates it. An analyst cannot silence a rule alone.

B4. Contract tests hitting every endpoint and validating against the generated
    OpenAPI schema. Confirm /api/v1/openapi.json is complete, since Track C
    depends on it.
```

---

## 5. Track C — Dashboard (parallel, independent)

```
[MASTER PROMPT ABOVE]

TRACK C: React dashboard. Read docs/06-FRONTEND-DESIGN.md IN FULL. It contains
the wireframes, component tree, type scale, and an ALREADY-VALIDATED colour
palette.

You own: web/   Do not edit engine/ or api/.

Critical constraints from the design doc - these are not preferences:
  - The palette in docs/06 section 4 was validated with a colourblind-safety
    checker in both light and dark mode. Do not re-pick colours. Do not add a
    green/amber/red traffic light; risk uses the single-hue ember ramp.
  - Light mode has a contrast WARN on three series colours. Every chart using
    them MUST ship visible direct labels or a table view. Not optional.
  - In the correlation graph, source is encoded by SHAPE and risk by FILL. Five
    source hues cannot clear all-pairs colourblind separation, which is why.
  - Type: Archivo for interface, Source Serif 4 for the narrative paragraph only,
    JetBrains Mono for tabular values only.
  - No fade-and-slide-up section entrances, no hover lift on rows. The single
    piece of orchestrated motion is the user-started timeline replay, and it must
    honour prefers-reduced-motion.

C1. Vite + React 18 + TS + Tailwind + shadcn/ui. Generate API types from
    /api/v1/openapi.json with openapi-typescript. Never hand-write a response
    type. Until Track B is up, run against a fixture server using the exact
    example payloads in docs/05 - they are complete and real-shaped.
C2. Login screen and session handling.
C3. Queue: virtualised rows, lane chip as glyph + word + colour, risk and
    confidence side by side at equal weight.
C4. Incident detail: header with thresholds drawn on the meters, then the
    narrative, then the evidence list with counterfactuals written as sentences.
C5. The ChainSpine component at three scales (sm / lg / campaign). This is the
    product's visual signature - roughly 120 lines of hand-written SVG, not a
    chart library.
C6. Correlation graph with react-force-graph. Selection state is SHARED across
    spine, graph, and evidence list - three views of one object.
C7. User profile: risk trend line with the cohort p50-p90 band behind it, and the
    learned working window shown explicitly.
C8. Detection health: calibration plot with the diagonal drawn, and the rule
    table sorted by weight drift.

Keyboard traversal and visible focus rings throughout. Every chart needs a
"view as table" affordance.
```

---

## 6. Track D — Evaluation (starts after A5, can overlap A6–A9)

```
[MASTER PROMPT ABOVE]

TRACK D: Evaluation harness. Read docs/07-EVALUATION.md IN FULL. It is the most
important doc for defending this project to a technical judge.

You own: engine/eval/  tests/test_eval*

The single most important thing in this track: we do NOT report user-day
precision targets like "85%", because at CERT's base rate that is arithmetically
impossible at any workable alert volume. Section 2 has the calculation. Report
insider-level and incident-level metrics instead. Do not report ROC-AUC, and make
the report state why it is absent.

D1. engine/eval/harness.py. Every metric in docs/07 section 3: insider recall
    before the final malicious act, incident precision, auto-flag precision,
    PR-AUC, precision@k, recall at a 25/day budget, median time-to-detect,
    investigation burden, and ECE calibration over 10 bins.
    Attribution rule: an incident is a true positive ONLY if it falls inside that
    user's labelled malicious window. Flagging a known insider on an unrelated day
    is a false positive, not a lucky hit. Without this the metric is meaningless.

D2. Bootstrap 95% CIs over 1000 resamples at the USER level, not user-day.
    User-days within one insider are correlated; resampling them independently
    produces a falsely tight interval. Report as "0.89 [0.80, 0.96]".

D3. Per-rule diagnostics: fire count, standalone precision, in-context precision,
    measured log-odds, configured weight, weight drift, and unique contribution
    (insiders caught ONLY by that rule). This is how we answer "how did you pick
    your weights" with a measurement instead of an opinion.

D4. engine/eval/ablate.py - the 7-row ablation table from docs/07 section 4, each
    row driven by a config flag so the table is generated by one command. This is
    the most persuasive artifact in the project because it isolates what
    correlation actually buys. If a row contradicts our pitch, report it honestly.

D5. Guard: the harness must REFUSE to emit a report unless the input carries a
    real-CERT provenance marker, and must stamp data_source into every report.
    Synthetic numbers must never be able to masquerade as results.

D6. Temporal split only - validation on the first 60%, test on the last 40%.
    Never shuffled cross-validation; it leaks the future into the past.
```

---

## 7. How to run the tracks

**Sequencing**

```
Session 0 (data)  ───┐
                     ├──> Track A (engine) ──> Track D (eval)
Track B (API+auth) ──┘         │
Track C (frontend) ────────────┴──> integration
```

- **Session 0 first, alone.** Everything real depends on it.
- **A, B, C then run in parallel** in three separate Claude Code sessions.
- **D starts once A5 (scoring) exists.**
- Integration last: point C at B, point B at A's Parquet artifacts.

**Why the file ownership matters.** Each track edits disjoint paths, so parallel
sessions never touch the same file. The shared surface is `config/*.yaml` (Track A
only) and `docs/05-API-SPEC.md` (read-only for B and C — it is the frozen
contract between them).

**Do not split Track A.** Steps A1–A9 are a dependency chain. Two sessions on the
engine will produce two incompatible interfaces.

**Before each session ends**, ask it to state: what runs, what was measured (real
numbers), and what is not finished. Paste that into the next session's prompt so
context carries forward.
