# 02 — System Architecture

---

## 1. Architectural principles

These five constraints drove every decision below.

| # | Principle | Consequence |
|---|---|---|
| P1 | **The engine is a library, not a service.** | `engine/` imports nothing from `api/`. It can be run from a notebook, a CLI, a test, or a Kafka consumer. This is what makes the scaling story real rather than aspirational. |
| P2 | **Explainability is a data structure, not a rendering step.** | Signals, weights, and counterfactuals are *persisted rows*, not strings generated at display time. An incident from six months ago explains itself identically today. |
| P3 | **Config over code.** | Rules, weights, thresholds, and windows live in versioned YAML. The config hash is stored on every score, so any historical score is reproducible. |
| P4 | **Batch now, streaming later — same logic.** | Detection operates on a *window of events*, never on "the whole dataset". Swapping the ingestion layer for Kafka changes how windows arrive, not what happens inside them. |
| P5 | **Determinism.** | Fixed seeds, sorted iteration, no wall-clock reads inside the engine. Same input plus same config equals byte-identical output. |

---

## 2. System context (C4 level 1)

```
                     ┌──────────────────────────────┐
   CERT CSV files ──▶│                              │
   (logon, device,   │                              │
    file, http,      │        SentinelTrace         │──▶ Analyst (web dashboard)
    email, LDAP)     │                              │
                     │   detect · correlate ·       │──▶ Evaluation report (CI artifact)
   Future: SIEM,     │   explain · route            │
   Kafka, cloud  ────▶│                              │──▶ Export (JSON evidence pack)
   audit logs        └──────────────────────────────┘
                                   │
                                   ▼
                        PostgreSQL / SQLite
```

---

## 3. Container view (C4 level 2)

```
┌───────────────────────────────────────────────────────────────────────────┐
│  web/  React 18 + TS + Tailwind + shadcn/ui                               │
│  Queue · Incident Detail · User Profile · Detection Health                │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │ REST/JSON
┌───────────────────────────────▼───────────────────────────────────────────┐
│  api/  FastAPI + Pydantic v2                                              │
│  routers · schemas · dependency-injected repositories · OpenAPI           │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │ repository interfaces
┌───────────────────────────────▼───────────────────────────────────────────┐
│  engine/   pure Python — no HTTP, no ORM at the boundary                  │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌───────────┐ ┌─────────┐ ┌───────┐│
│  │ ingest  │▶│ features │▶│ detect  │▶│ correlate │▶│ explain │▶│ route ││
│  └─────────┘ └──────────┘ └─────────┘ └───────────┘ └─────────┘ └───────┘│
│       ▲            ▲            ▲            ▲            ▲               │
│       └────────────┴──────config/ (YAML, versioned, hashed)──┴───────────│
└───────────────────────────────┬───────────────────────────────────────────┘
                                │ SQLAlchemy Core
┌───────────────────────────────▼───────────────────────────────────────────┐
│  storage/   PostgreSQL (prod) · SQLite (demo)  + artifacts/ (parquet)     │
└───────────────────────────────────────────────────────────────────────────┘
```

### Why the engine has no web or ORM dependency

The engine consumes and produces plain dataclasses / DataFrames. Persistence is injected via repository protocols (`EventRepo`, `FeatureRepo`, `IncidentRepo`). This gives three concrete wins:

1. The engine is unit-testable with in-memory fixtures — no database in the test loop.
2. The batch runner and a future Kafka consumer share identical code.
3. Storage can be swapped (SQLite, Postgres, Parquet-only) without touching detection logic.

---

## 4. The pipeline, stage by stage

```
 CSV / adapter          Event[]            UserDayFeature[]        Signal[]
     │                     │                      │                   │
     ▼                     ▼                      ▼                   ▼
┌─────────┐  normalise ┌────────┐  aggregate ┌─────────┐  evaluate ┌────────┐
│ ingest  │───────────▶│ events │───────────▶│features │──────────▶│ detect │
└─────────┘            └────────┘            └─────────┘           └────────┘
                                                  │                     │
                                     baselines ◀──┘                     │
                                (self 30d + peer cohort)                │
                                                                        ▼
        Incident[]             Graph                        ┌──────────────────┐
            ▲                    ▲                          │ rules  +  ML     │
            │                    │                          │ (IsolationForest)│
        ┌───┴──────┐       ┌─────┴─────┐                    └────────┬─────────┘
        │  route   │◀──────│  explain  │◀───────────────────│ correlate │
        └──────────┘       └───────────┘                    └───────────┘
             │                   │
             │                   └─▶ narrative + counterfactual + minimal set
             └─▶ AUTO_FLAG / ANALYST_REVIEW / MONITOR / SUPPRESSED
```

### Stage 1 — `engine/ingest`
**In:** CSV files or an adapter-mapped record stream. **Out:** normalised `Event` rows.

- Chunked CSV reads (`chunksize=250_000`) to satisfy the 4 GB ceiling.
- Per-source parser turns native columns into the unified `Event` shape.
- `event_id = blake2b(source + raw_id + user + ts)[:16]` gives content-addressed idempotency.
- LDAP snapshots are loaded per month and forward-filled to build `user_org` history (role and department change over time; peer groups must follow).
- Parse failures are counted and sampled into an `ingest_run` record, never silently dropped.

### Stage 2 — `engine/features`
**In:** events for a window. **Out:** `UserDayFeature` rows plus baselines.

- Group by `(user, date)`, apply a feature registry (each feature is a named pure function over that group).
- Rolling self-baseline: trailing 30 days, 14-day minimum warm-up, `median` and `MAD`-derived sigma rather than mean/std — insider spikes would otherwise poison the very baseline meant to catch them. This is a small change with a large robustness effect.
- Peer baseline: the same statistics over the user's `(role, department)` cohort for the same date, so organisation-wide changes (a holiday, a deadline) do not read as individual anomalies.
- Output both `z_self` and `z_peer`. A user who is always odd has a high `z_peer` but a low `z_self`; a user who suddenly changes has the reverse. Rules can require either or both.

### Stage 3 — `engine/detect`
**In:** features. **Out:** `Signal` rows and a per-user-day risk plus confidence.

Two independent subsystems, deliberately not blended into one model:

- **Rule engine** — a declarative catalogue evaluated against the feature row. Each match is a `Signal` with a category, a kill-chain stage, a strength in 0–1, a weight, and the event ids that justify it.
- **Anomaly detector** — IsolationForest trained per peer cohort on the standardised feature matrix, output converted to a within-cohort percentile and mapped through a tail function so only the top few percent contribute anything.

Combined by the log-odds additive model in `04-DETECTION-ENGINE` section 4.

### Stage 4 — `engine/correlate`
**In:** events and signals for a user-window. **Out:** `Incident` and `Campaign` records, plus a graph payload.

- Nodes are events that carry at least one signal (plus their immediate context events).
- Edges are drawn when two events fall within the window for their pair type; the window is per-pair, because `logon → device` at 12 minutes means something quite different from `file → http` at 12 minutes.
- Cross-user edges via shared PC or shared filename catch lateral movement.
- Connected components of size >= 2 become incidents.
- Campaign linking joins a user's incidents within 14 days when the kill-chain stage advances.

### Stage 5 — `engine/explain`
**In:** an incident. **Out:** narrative, counterfactual table, minimal sufficient set.

- Template grammar assembles clauses from signal metadata. Deterministic, auditable, and offline.
- Counterfactual: for each signal, re-run the scoring function with that signal removed and record the delta. With N signals this is N cheap arithmetic evaluations, not N model refits.
- Minimal sufficient set: greedily drop the lowest-contribution signals while the score stays above the alert threshold.

### Stage 6 — `engine/route`
**In:** risk, confidence, suppression rules. **Out:** a triage lane and a persisted incident.

---

## 5. Component responsibilities

| Module | Responsibility | Key types |
|---|---|---|
| `engine/ingest/adapters/` | Map foreign log formats to the canonical schema | `SourceAdapter`, `FieldMapping` |
| `engine/ingest/loader.py` | Chunked read, normalise, dedup, provenance | `Event`, `IngestRun` |
| `engine/features/registry.py` | Named pure feature functions | `FeatureSpec` |
| `engine/features/baseline.py` | Robust rolling self and peer baselines | `Baseline`, `ZScores` |
| `engine/detect/rules.py` | YAML rule evaluation | `Rule`, `Signal` |
| `engine/detect/anomaly.py` | Per-cohort IsolationForest, percentile mapping | `AnomalyModel` |
| `engine/detect/scoring.py` | Log-odds combination, saturation, confidence | `RiskScore`, `Confidence` |
| `engine/correlate/graph.py` | Event graph construction | `EventGraph`, `Edge` |
| `engine/correlate/incident.py` | Components, campaigns, kill-chain staging | `Incident`, `Campaign` |
| `engine/explain/narrative.py` | Template grammar | `Narrative` |
| `engine/explain/counterfactual.py` | Per-signal delta, minimal sufficient set | `Attribution` |
| `engine/route/triage.py` | Risk x confidence lane assignment, suppressions | `TriageDecision` |
| `engine/eval/harness.py` | Ground truth join, metric computation | `EvalReport` |
| `api/routers/` | HTTP surface per `05-API-SPEC.md` | — |
| `api/repositories/` | SQLAlchemy implementations of engine protocols | — |
| `web/src/` | Dashboard | — |

---

## 6. Data flow and storage boundaries

| Layer | Store | Why |
|---|---|---|
| Raw events | Parquet on disk, partitioned by month | 32M rows; columnar scan beats row storage; keeps the DB small |
| Features | Parquet + a Postgres table for queried slices | Feature matrix is dense and numeric |
| Signals, incidents, campaigns, verdicts | Relational (Postgres / SQLite) | Needs joins, foreign keys, and transactional verdict writes |
| Models | Pickled per-cohort IsolationForest plus a manifest | Versioned alongside the config hash |
| Eval reports | JSON artifacts | Diffable in CI |

**Engine reads Parquet directly; the API reads the database.** The batch runner is the only writer to the database. This removes any read/write contention during the demo and means the UI cannot be slowed down by a pipeline run.

---

## 7. Deployment

### Local demo
```yaml
# docker-compose.yml (shape)
services:
  db:      postgres:16          # or omitted entirely for SQLite mode
  api:     build ./api          # uvicorn, mounts ./data as read-only
  web:     build ./web          # vite dev or nginx-served build
  runner:  build ./engine       # one-shot pipeline job, profile: pipeline
```

- `docker compose up` brings up `db`, `api`, `web` and serves committed precomputed artifacts — the demo path, with no pipeline run required.
- `docker compose --profile pipeline up runner` re-runs detection end to end.
- `SENTINEL_DB=sqlite:///./data/demo.db` drops Postgres entirely for a laptop with no Docker.

### Hosted
Render or Railway: the API as a web service, the web build as a static site, Postgres as a managed add-on, and the pipeline as a one-off job that seeds the database. Artifacts are baked into the image so a cold start needs no dataset download.

---

## 8. Scaling path (designed, not built)

The point worth making to judges: **the detection logic is unchanged when this scales. Only ingestion changes.**

| Concern | v1 (now) | v2 (streaming) |
|---|---|---|
| Arrival | CSV batch | Kafka topics per source |
| Windowing | group-by on (user, date) | tumbling or sliding windows keyed by user |
| Baselines | recomputed per run | incremental EWMA in a state store (Redis / RocksDB) |
| Detection | called once per user-day | called per closed window — *same function* |
| Correlation | in-memory graph per user-day | same graph over a sliding window buffer |
| Storage | Parquet + Postgres | object store + OLAP (ClickHouse) for events; Postgres stays for incidents |
| Sources | 5 CERT types | plus VPN, cloud audit (CloudTrail, Entra), EDR, badge / physical access |

Two structural choices make this a port rather than a rewrite:

1. `detect(features, config) -> Signals` is pure and window-scoped. It never queries a database and never sees the full dataset.
2. Baselines already flow through a `BaselineProvider` protocol. The batch implementation recomputes; the streaming implementation reads incremental state. Nothing else changes.

**Throughput estimate.** CERT r4.2 is roughly 32M events over 17 months across 1,000 users — about 25 events/sec average. A single Kafka partition set with per-user keying handles four orders of magnitude more than that before the design needs revisiting; the first real bottleneck is baseline state, which is why it is behind a protocol from day one.

---

## 9. Failure modes and degradation

| Failure | Behaviour | Rationale |
|---|---|---|
| One source missing for a user-day | Detection proceeds; `data_completeness` drops; **confidence is penalised** | Missing data must lower certainty, never silently lower risk |
| Baseline immature (< 14 days) | Self-baseline rules are suppressed; peer-baseline rules still fire; confidence capped at 0.6 | Prevents cold-start false positives |
| Anomaly model unavailable | Rules run alone; confidence agreement term set to the rules-only value | The hybrid degrades to rules; it never fails closed |
| Graph component exceeds `max_component_events` | Correlation bonus set to zero for that component and flagged `over_dense` | A day where everything connects is an artefact, not an incident |
| Malformed rows | Counted, sampled, surfaced in the ingest report | Silent drops destroy trust in recall numbers |
| Config hash mismatch on a stored score | Score served with a `stale_config` flag | Never present an old score as if produced by current logic |

---

## 10. Security of the tool itself

A monitoring system is a high-value target: it holds a map of who has access to what.

- API is read-mostly; only `POST /ingest` and review endpoints write.
- Analyst actions are authenticated (token header in v1, OIDC in v2) and written to an append-only `audit_log`.
- No raw file contents or email bodies are stored — only metadata. This limits blast radius by design.
- Database credentials via environment only; nothing committed.
- The exported evidence pack is explicitly marked as containing personal data and is watermarked with the exporting analyst and timestamp.

---

## 11. Technology choices, with reasons

| Layer | Choice | Why this and not the alternative |
|---|---|---|
| Features | Pandas | The dataset fits in memory when chunked; Spark's overhead is unjustified at 32M rows |
| Anomaly | scikit-learn IsolationForest | CPU-only, fast, no training labels needed, well understood. An autoencoder would add GPU dependency and remove interpretability for no measured gain at this scale |
| Rules | YAML + a small evaluator | Detection engineers must change rules without a Python review. See `adr/0002` |
| API | FastAPI | Pydantic v2 validation and free OpenAPI, which the frontend types are generated from |
| DB | Postgres, SQLite for demo | Postgres for JSONB signal payloads and real indexes; SQLite so the demo has no external dependency |
| Graph | NetworkX server-side, react-force-graph client-side | Components are computed once server-side; the client only renders |
| Frontend | React + Tailwind + shadcn/ui | Fast to build, accessible primitives, consistent design without a designer |
| Charts | Recharts | Declarative, composable, fits the React model |

---

## 12. Architecture decision records

| ADR | Decision |
|---|---|
| `adr/0001` | Two-axis scoring: risk separated from confidence |
| `adr/0002` | Declarative YAML rules instead of Python predicates |
| `adr/0003` | Log-odds additive scoring instead of weighted-sum |
| `adr/0004` | Template narratives instead of an LLM |
| `adr/0005` | Parquet for events, relational for incidents |
| `adr/0006` | Peer-group baselines in addition to self-baselines |
