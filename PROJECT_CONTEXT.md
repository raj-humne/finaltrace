# SentinelTrace — Full Project Context

**Paste this whole file into a fresh LLM session to bring it up to speed with zero
prior context.** It explains what the project is, why every major decision was
made, exactly how it works end to end, the full tech stack, and the exact shape
of the input data. Where something is unbuilt, it says so — nothing below claims
more than what actually exists.

---

## 1. What this is, in one paragraph

SentinelTrace is a behavioural insider-threat detection system, built for
HACKINDORE 4.0 (a cybersecurity hackathon), problem statement PS2:
"Behavioural Threat Detection & Incident Correlation." It ingests five kinds of
enterprise activity logs (who logged into what machine, who plugged in a USB
drive, who opened which file, who visited which website, who emailed whom), and
instead of alerting on any single action, it links related actions across a time
window into one **incident**, scores that incident on two separate axes — **risk**
(how bad) and **confidence** (how sure) — and generates a plain-English
explanation of exactly why, with the evidence and its weight shown for every
signal that contributed.

## 2. The problem it solves, in full

### 2.1 Why this is hard

An insider threat — an employee stealing data, or an attacker who has stolen
valid credentials — does not "break in." They log in normally, with real
credentials, and touch only systems they are entitled to touch. A firewall has
nothing to block. A signature-based antivirus has no malware signature to match.
What makes the behaviour detectable is not any single action but the *sequence*:

```
21:47  logon        own machine, but 3 hours after this person's normal quitting time
21:51  file open    3 finance spreadsheets from a share they read maybe twice a month
21:59  device       USB storage connected — first time in 8 months
22:04  file copy    14 files copied to that removable media
22:31  http upload  to a personal cloud-storage site
```

Every single line above is a normal, policy-compliant, individually-innocent
action. Together, over 44 minutes, they describe a data theft. No single log line
says that. The sequence does.

### 2.2 What existing tools get wrong

- They alert per event, per tool, in silos — a login alert here, a USB alert
  there, in different consoles, never connected.
- Rules tuned for high recall generate so much noise that analysts stop trusting
  the queue (alert fatigue).
- Most anomaly-detection tools output a single score with no explanation — you
  cannot defend "the model said 87" to HR or Legal.
- There is no confidence dimension, so a team either over-reacts to thin evidence
  or under-reacts to strong evidence, because every alert looks the same.
- Slow-burn campaigns spread across weeks look normal on any single day, and
  most correlation windows are too short (hours, not weeks) to see the pattern.

### 2.3 What SentinelTrace does differently

| Typical tool | SentinelTrace |
|---|---|
| One black-box score | Two numbers: **risk** and **confidence**, independently computed |
| Alert per event | **Incident** — a correlated cluster of related events |
| "Anomaly score: 0.87" | "Off-hours logon + USB insert within 12 minutes, then 47 files copied to that same USB session" |
| No attribution | **Counterfactual**: "remove the USB-copy signal and risk drops from 73 to 55" |
| Compares you only to your own history | Compares you to your own history **and** your peer group (same role, same department) |
| Flat severity | **Kill-chain staging**: context → recon → staging → collection → exfiltration → evasion, and the score rewards the stages advancing *in order* |
| Fixed thresholds forever | Confidence-gated triage: thin evidence can never auto-escalate, no matter how high the risk number is |
| Single-day detection only | **Campaign linking**: incidents for the same person within 14 days that advance the kill chain get linked, so a slow-burn attack surfaces even though no single day looks alarming |

---

## 3. Why the design choices were made (the reasoning, not just the result)

These are recorded formally as Architecture Decision Records in `docs/adr/`, but
here is the plain-language version of each, because "why" matters as much as
"what" when explaining this to someone new.

**Why risk and confidence are two separate numbers, not one.**
A single decisive signal on a brand-new employee (9 days of history) is
seriously different from six cross-source signals on someone with 90 days of
established baseline — even if a naive model would score them both "80."
Collapsing that into one number means the system cannot tell you when it's
guessing versus when it's sure, so a human either over-trusts a lucky guess or
ignores a well-evidenced alert. Two axes let the routing rule be explicit: **high
risk with low confidence can never auto-flag** — it always goes to human review.
That's a fairness property for the person being monitored, not just a UX choice.

**Why rules are declarative YAML instead of Python functions.**
The people who need to tune detection thresholds week to week (detection
engineers, and eventually analysts proposing new rules from real incidents) are
not necessarily the people who can safely modify and redeploy the codebase. If a
rule is a Python function, every threshold tweak is a code review and a deploy.
If a rule is a YAML entry with a closed set of operators (`gte`, `lt`, `in`,
`is_true`, `z_self_gte`, `z_peer_gte` — nothing that can execute arbitrary code),
tuning it needs no deploy, and every rule is directly showable to a flagged
person or a judge: "here is exactly the threshold that fired." There's a real
security dimension too — this system reasons over untrusted log content, so an
`eval()`-based rule language would be a code-injection surface. Twenty-seven
rules exist today; none of them needed an escape hatch.

**Why the score is log-odds addition with saturation, not a simple weighted sum.**
A plain `sum(weight × strength)` has three failure modes: (1) twelve weak
signals outrank one decisive one, (2) redundant signals — "worked off-hours,"
"file access was off-hours," "the whole day was off-hours" — all fire off the
same underlying fact and triple-count it, and (3) the number itself means
nothing, so a threshold at 70 can't be defended. The fix: score in **log-odds
space**, where each rule's weight is a literal claim — "observing this multiplies
the odds of malicious behaviour by e^weight" — which is falsifiable and gets
checked against ground truth. Within a category (e.g. "exfiltration" signals),
each additional signal counts at half the weight of the one before it
(geometric decay), which structurally caps how much redundant evidence in one
category can inflate the score. The correlation bonus only applies across
*different* categories, which is the arithmetic expression of "correlation, not
just co-occurrence."

**Why explanations are generated from a template grammar, not an LLM.**
An LLM writing "why this was flagged" can assert something the underlying
evidence doesn't actually support — there's no structural guarantee it won't.
When the explanation might end up in an HR file, that's not an acceptable risk.
A deterministic template that interpolates real stored values into a sentence
*cannot* contradict the data, because it *is* a rendering of the data. It's also
free, instant, fully offline, and produces byte-identical output for the same
incident every time — which matters if someone re-opens the case six months
later.

**Why self-baselines aren't enough on their own (peer-group baselines).**
Comparing someone only to their own history has two failure modes: a person
whose job is always a little unusual (a sysadmin touching many machines at odd
hours) trains a wide personal baseline and becomes hard to flag even when doing
something genuinely new; meanwhile a company-wide event (quarter close, a
migration) makes *everyone's* baseline spike at once and floods the queue with
false positives. Comparing to a peer cohort (same role + department) fixes both:
an org-wide spike is absorbed because everyone's peer average also moved, and a
"quietly always weird" person is caught because a rule can require *both*
`z_self` and `z_peer` to be high at once.

**Why events use Parquet but incidents use a relational database.**
Feature computation is a bulk analytical workload — scan ~32 million rows,
group by user and day, compute columns. That's what columnar Parquet is for. The
API's serving path is the opposite: fetch one incident by id, with joins across
signals, attributions, and a review record, and sometimes write a verdict
transactionally. That's what a relational database is for. Splitting them means
a pipeline run (writing Parquet) can never slow down or lock the live API
(reading Postgres/SQLite) — no contention during a demo.

---

## 4. How it works end to end (the pipeline)

```
raw CSV logs (5 sources) + LDAP org snapshots
        │
        ▼
┌───────────────┐   normalise every source into one Event shape
│    INGEST     │   (blake2b content-hash id → re-running the same file
└───────┬───────┘    adds zero duplicate rows)
        ▼
┌───────────────┐   one row per (user, date): ~56 behavioural features —
│   FEATURES    │   logon timing, USB session length, file burst size,
└───────┬───────┘   domain category visits, email fan-out, cross-source
        │           gaps like "minutes from USB-connect to first file copy"
        ▼
┌───────────────┐   robust self-baseline (30-day trailing median/MAD,
│   BASELINES   │   not mean/std — one extreme day shouldn't distort the
└───────┬───────┘   baseline that's supposed to catch it) + peer-cohort
        │           baseline (same role+department). Emits z_self, z_peer.
        ▼
┌───────────────┐   TWO independent opinions, never merged into one model:
│    DETECT     │   (a) 27 declarative rules evaluate the feature row
└───────┬───────┘   (b) IsolationForest, trained per peer cohort, flags
        │               statistical outliers the rules didn't anticipate
        ▼
┌───────────────┐   log-odds combination: per-category saturation, ML
│    SCORE      │   capped below any single decisive rule, correlation
└───────┬───────┘   bonus only for cross-category + ordered-stage evidence.
        │           Confidence computed independently (agreement, signal
        │           diversity, data completeness, baseline maturity).
        ▼
┌───────────────┐   build a graph of events connected by time-window edges
│   CORRELATE   │   (different pairs get different windows — a logon→USB
└───────┬───────┘   gap means something different from a file→upload gap).
        │           Connected clusters become incidents. Incidents for the
        │           same person within 14 days that advance the kill chain
        │           link into a campaign (the slow-burn catcher).
        ▼
┌───────────────┐   template-grammar narrative (no LLM) + counterfactual:
│   EXPLAIN     │   "remove this signal → score would be X" for every
└───────┬───────┘   contributing signal, plus the minimal set of signals
        │           that alone would still clear the alert threshold.
        ▼
┌───────────────┐   risk × confidence → one of AUTO_FLAG / ANALYST_REVIEW /
│    ROUTE      │   MONITOR / SUPPRESSED. High risk + low confidence can
└───────┬───────┘   NEVER auto-flag — that's enforced in code, not just docs.
        ▼
   API (FastAPI, real auth) → React dashboard for an analyst to triage
```

### Worked example (from the spec, illustrating the scoring math)

A user logs on off-hours (weight 0.65), connects USB for the first time in 8
months (weight 1.60, but decayed to ~half since it's the 2nd signal in its
category), files get copied during that USB session (weight 1.30), and an
upload follows to cloud storage. Correlation bonus applies because the signals
span 3 different categories and advance through 3 kill-chain stages in order.
Combined in log-odds space with a −4.6 prior (encoding "malicious is rare") and
squashed through a logistic function, this scores **≈73/100 risk**. The worked
arithmetic is in `docs/04-DETECTION-ENGINE.md` §4.2, and it's asserted as a test
(`tests/test_scoring.py`) so the number can't silently drift.

---

## 5. Full tech stack

| Layer | Technology | Why |
|---|---|---|
| Feature engineering | Python 3.11, pandas, numpy | Vectorised, not row-by-row — a Python loop over 32M rows would blow the 15-minute budget; column operations don't |
| Detection | scikit-learn `IsolationForest` + a hand-written YAML rule evaluator | No labels needed for the anomaly side; the rule side needs to be auditable and edited without a deploy |
| Correlation graph | NetworkX | Standard, well-tested connected-components and graph traversal |
| Config | PyYAML, hashed with `hashlib.sha256` into a `config_version` on every score | Every historical score must be reproducible from its exact configuration |
| Backend API | FastAPI + Pydantic v2 | Free OpenAPI schema generation, which the frontend's types are generated from — a backend contract change becomes a frontend type error, not a silent mismatch |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | Postgres in production, SQLite for a dependency-free local demo — the difference lives only in the dialect layer |
| Auth | `argon2-cffi` (Argon2id password hashing), server-side session tokens (`secrets.token_urlsafe`), RBAC via FastAPI dependencies | Real credential auth, not a placeholder bearer token — passwords are never stored plaintext or reversibly encoded |
| Testing | pytest, `hypothesis` (property-based testing) | Hypothesis specifically proves properties like "more evidence never lowers the risk score" across generated inputs, not just fixed examples |
| Frontend | React 18 + TypeScript, Vite, Tailwind CSS 4 | Fast build, utility-first styling that matches a hand-picked design system rather than a generic component-library look |
| Frontend components | Radix UI primitives + `class-variance-authority` (shadcn/ui pattern) | Accessible unstyled primitives, styled to the project's own design tokens |
| Data fetching | TanStack Query, `openapi-fetch` | Typed API calls generated directly from the backend's OpenAPI schema (`openapi-typescript`) — no hand-written response interfaces anywhere |
| Charts | Recharts (risk trend, calibration plot) | Declarative, composable |
| Correlation graph (UI) | `react-force-graph-2d` | Force-directed layout for the node/edge evidence graph |
| Virtualised lists | `@tanstack/react-virtual` | The triage queue scrolls 1,000+ rows without pagination |
| Fonts | Archivo (interface), Source Serif 4 (the narrative paragraph only), JetBrains Mono (tabular values only) | Three typefaces, three non-overlapping jobs — see the design rationale in `docs/06-FRONTEND-DESIGN.md` |
| Local dev server for the frontend's own auth cookie handling | Express (`server/`) | Small Node proxy so cookie-based sessions work correctly against Vite's dev server |
| Deployment (designed) | Docker Compose — `db`, `api`, `web`, one-shot `runner` under a `pipeline` profile | Local, offline-capable demo; Postgres or SQLite interchangeably |

---

## 6. The input data, exactly

### 6.1 The real dataset: CMU CERT r4.2 Insider Threat Test Dataset

A synthetic-but-realistic corpus published by Carnegie Mellon's CERT division
specifically for insider-threat detection research. **This project uses the real
r4.2 release** — already downloaded and extracted into `data/raw/r4.2/`:

| File | Size | What it records |
|---|---|---|
| `logon.csv` | 58.5 MB | Every logon/logoff event: id, timestamp, user, PC, activity |
| `device.csv` | 29.0 MB | Every removable-media connect/disconnect: id, timestamp, user, PC, activity |
| `file.csv` | 193.1 MB | Every file access: id, timestamp, user, PC, filename, whether it went to removable media |
| `http.csv` | **14.5 GB** | Every web request: id, timestamp, user, PC, URL |
| `email.csv` | 1.36 GB | Every email: id, timestamp, user, PC, to/cc/bcc, from, size, attachment count |
| `LDAP/*.csv` | small | Monthly org-directory snapshots: name, user id, email, role, business unit, department, team, supervisor |

Rows are keyed by `(user, date, pc)`. Each of ~1,000 simulated employees has
continuous activity over roughly 17 months (Jan 2010–May 2011). A small number
of users (labelled in `data/raw/answers/`) are scripted malicious insiders
following one of three behavioural scenarios:

1. **Slow burn**: a user who never touched removable media or worked after
   hours begins doing both over several weeks, eventually uploads data to a
   leak site, and leaves the company shortly after.
2. **Job-hunt + theft**: browses job-search sites, then copies data to a thumb
   drive shortly before departing.
3. **Disgruntled admin**: downloads a keylogger to a USB drive, uses it on a
   supervisor's machine, then sends an alarming mass email.

The `answers/` directory is the ground truth used by the (not-yet-built)
evaluation harness to measure real detection performance — which users were
malicious, on which dates, in which scenario.

**Important honesty note baked into the evaluation design:** at this dataset's
real base rate (malicious user-days are roughly 0.1–0.5% of all user-days), a
*perfect* detector working a realistic daily alert budget is mathematically
capped at single-digit precision if measured at the day level. The original
placeholder success metrics in the pitch deck ("85% precision, 75% recall") are
not achievable at that granularity by any system, including a perfect one — the
evaluation doc (`docs/07-EVALUATION.md`) works the exact arithmetic and
reframes the real target as **incident-level and insider-level** metrics
instead (e.g. "89% of insiders caught before their final malicious act, at 0.3
incidents/day/1000 users"). This reframing is a deliberate, documented choice,
not an oversight.

### 6.2 The synthetic generator (`tools/generate_synthetic.py`)

Produces data in the *exact same CSV schema* as real CERT, with configurable
user counts, day counts, and injected instances of the same three scenarios. It
exists only because building and testing the pipeline against a 14.5 GB file
during development is slow (minutes per run instead of seconds). **It is not a
source of any reported number or demo claim** — that boundary is enforced by the
evaluation harness itself, which will refuse to emit a report unless the input
data carries a real-CERT provenance marker. It's a pytest fixture generator, not
a mock of the product.

### 6.3 The canonical internal event shape

Whatever the source, everything is normalised into one shape before anything
else touches it — this is also what makes it possible to later plug in a
different company's real logs (Windows Security Events, Okta, a web proxy) via
a mapping file instead of a code change:

```python
Event(
    event_id: str,       # content-addressed hash — re-ingest is a no-op
    user_id: str,
    ts: datetime,         # UTC
    source: str,          # logon | device | file | http | email
    action: str,          # logon, connect, open, visit, send, ...
    pc_id: str | None,
    attrs: dict,          # source-specific: filename, domain, category, size...
)
```

---

## 7. What's actually built right now (verified, not aspirational)

**Engine (`engine/`) — complete, all modules present, 119/119 tests passing:**
- `ingest/loader.py` — vectorised (not row-by-row) parsing of all 5 CERT sources
  plus LDAP org snapshots with departure-date inference. Measured at ~57,000
  rows/second on the synthetic set, projecting to roughly 9 minutes for the real
  32-million-row corpus — inside the 15-minute budget.
- `ingest/ground_truth.py` — parses CERT's `answers/` files into a ground-truth
  table (just added, not yet committed).
- `features/extract.py` — ~56 features per (user, date): timing, session
  pairing, USB-session file-copy counts, burst detection, domain categorisation,
  email fan-out, and the cross-source gap features (logon→USB, USB→file,
  file→upload) that a single-log-source tool structurally cannot compute.
- `features/baseline.py` — robust median/MAD self-baseline and peer-cohort
  baseline.
- `detect/rules.py` — evaluates the 27-rule YAML catalogue.
- `detect/anomaly.py` — per-cohort IsolationForest.
- `detect/scoring.py` — the log-odds combination model.
- `correlate/graph.py`, `correlate/incident.py` — event graph, connected
  components, campaign linking.
- `explain/narrative.py`, `explain/counterfactual.py` — template narrative
  generation and per-signal counterfactual attribution.
- `route/triage.py` — the risk×confidence lane matrix, with the "high risk +
  low confidence never auto-flags" rule enforced as a config-load-time
  validation check, not just a convention.
- `run.py` — CLI entry point; runs the full pipeline to Parquet, or prints one
  user-day's full score breakdown.

**API (`api/`) — complete:**
- FastAPI app with routers for `/health`, `/auth`, `/ingest`, `/users`,
  `/incidents`, `/campaigns`, `/rules`, `/detection/health`, `/eval`,
  `/suppressions`, `/analyze`.
- Real authentication: Argon2id password hashing, server-side sessions, account
  lockout, an append-only audit log, and role-based access control
  distinguishing an `analyst` (can view, can record a verdict) from a
  `detection_engineer` (can additionally activate a suppression rule) —
  enforced server-side via FastAPI dependency injection, not hidden by the
  frontend.
- SQLAlchemy models for every entity (users, sessions, events, features,
  signals, incidents, campaigns, narratives, attributions, reviews,
  suppressions, audit log) with Alembic migrations.

**Frontend (`web/`) — substantial, built against the documented API contract:**
- Login page with real session-cookie auth.
- Queue page (the triage list), Incident detail page, Users page, User detail
  page, Detection Health page.
- Shared components: `ChainSpine` (the visual signature — a six-stage kill-chain
  rail shown at three sizes), `CorrelationGraph` (force-directed, source encoded
  by shape not colour, risk encoded by a single-hue "ember" fill — chosen
  because 5 source colours cannot pass a colour-blind-safety check when *every*
  pair of nodes can be adjacent in a force graph), `ScoreMeter`,
  `ConfidenceMeter`, `LaneChip`, `SignalCard` (shows the counterfactual
  sentence), `RiskTrendChart` (with a shaded peer-cohort band), `CalibrationPlot`,
  `WorkingWindowBar`, `CommandPalette`.
- API types are generated, never hand-written, from the live OpenAPI schema.

**Data — real CERT r4.2 downloaded and extracted** (`data/raw/r4.2/`, full 5
files + LDAP), plus `answers/` (ground truth) extracted. A partial pipeline run
exists covering a 7-month slice (Jan–Jul 2010) in `data/artifacts/` — this looks
like a smoke test on a data slice, not yet the full 17-month corpus.

## 8. What's NOT built yet

- **`engine/eval/`** — the evaluation harness is still an empty directory. This
  is the component that runs the metric suite from `docs/07-EVALUATION.md`
  against real ground truth (insider recall, incident precision, PR-AUC,
  calibration error, the per-rule weight-drift table, and the 7-row ablation
  study showing what correlation and campaign-linking each actually buy). This
  is the single most important remaining piece for defending the project's
  claims with real numbers instead of a hand-typed slide.
- A **full-corpus pipeline run** — the 7-month partial run needs to be re-run
  (or extended) across the complete 17-month dataset before any headline number
  is trustworthy.
- Two files are locally modified/untracked and not yet committed:
  `engine/ingest/loader.py` (a real bug fix — sparse per-source boolean/numeric
  columns were upcasting to Python `object` dtype on concatenation across the
  full corpus, which is what would have exhausted the 4 GB memory budget) and
  `engine/ingest/ground_truth.py` (new).
- Docker Compose packaging, and a recorded demo fallback video, per the delivery
  plan — not started.

## 9. The specification documents (all complete, in `docs/`)

These are the actual contract this build implements — 16 files, ~28,000 words,
covering: PRD (problem, personas, functional/non-functional requirements,
success metrics, ethics section), system architecture (C4 diagrams, module
boundaries, failure modes, the streaming-scale-up story), the full data model
(CERT schema, the 56-feature catalogue, complete PostgreSQL DDL), the detection
engine spec (all 27 rules with their exact trigger conditions, the kill-chain
staging model, the scoring math derived step by step), the REST API contract
(every endpoint with full example request/response JSON), the frontend design
spec (wireframes, a colour-blind-validated palette, the full component tree),
the evaluation methodology (why naive precision targets are impossible here,
the real metric suite, the bootstrap confidence-interval approach), a schema-
adapter-layer design for plugging in non-CERT log formats from a real company,
a delivery/demo plan with a full judge Q&A script, and six ADRs recording the
reasoning behind the biggest design decisions.

---

## 10. If you're an LLM picking this up cold, the fastest orientation is

1. Read `docs/01-PRD.md` §2 and §5 for scope.
2. Read `docs/04-DETECTION-ENGINE.md` in full — it's the actual core logic.
3. Read this file's §4 (the pipeline) and §7/§8 (what exists / what doesn't).
4. Run `python -m pytest -q` to confirm the current state is still green before
   changing anything.
5. The one thing to build next that matters most: `engine/eval/harness.py`,
   against the real ground truth in `data/raw/answers/`.
