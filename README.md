# SentinelTrace

**Behavioural Threat Detection & Incident Correlation**
HACKINDORE 4.0 — Cybersecurity Track (PS2) · Category: Software

> Insider threats don't break in. They log in.
> SentinelTrace connects individually-harmless actions into one prioritized, explainable incident — before the data leaves.

---

## The one-sentence pitch

A hybrid rule + anomaly detection engine that ingests five streams of enterprise activity logs, correlates weak signals across a time window into a single incident, scores it on **two independent axes (risk × confidence)**, and explains itself in plain English with a counterfactual trail — so an analyst knows not just *how bad*, but *how sure*, and *which one signal made the difference*.

## Why this is different from "another anomaly detector"

| Most tools | SentinelTrace |
|---|---|
| One score, black box | Two axes: **risk** (how bad) × **confidence** (how sure) |
| Alert per event | **Incident per correlated cluster** of events |
| "Anomaly score: 0.87" | "Off-hours logon + USB insert within 12 min, on a machine this user has never touched" |
| Score with no attribution | **Counterfactual**: "remove the USB event → risk drops 71 → 34" |
| Self-baseline only | **Self + peer-group** baselines (role/department cohort) |
| Flat alert list | **Kill-chain staging** — recon → collection → exfil, escalating as stages advance |
| Static thresholds | **Analyst feedback loop** recalibrates thresholds and learns suppressions |

## Document map

| Doc | What's in it |
|---|---|
| [`docs/01-PRD.md`](docs/01-PRD.md) | Problem, users, personas, scope, requirements, success metrics, risks |
| [`docs/02-ARCHITECTURE.md`](docs/02-ARCHITECTURE.md) | System architecture, components, data flow, deployment, scaling path |
| [`docs/03-DATA-MODEL.md`](docs/03-DATA-MODEL.md) | CERT log schemas, feature catalogue, full SQL DDL, indexing |
| [`docs/04-DETECTION-ENGINE.md`](docs/04-DETECTION-ENGINE.md) | Rule catalogue, scoring math, ML design, correlation algorithm, narrative grammar |
| [`docs/05-API-SPEC.md`](docs/05-API-SPEC.md) | Full REST contract with request/response examples and error model |
| [`docs/06-FRONTEND-DESIGN.md`](docs/06-FRONTEND-DESIGN.md) | Screens, wireframes, component tree, design tokens, interaction spec |
| [`docs/07-EVALUATION.md`](docs/07-EVALUATION.md) | Ground-truth methodology, the metrics that actually matter, target numbers |
| [`docs/08-ADAPTER-LAYER.md`](docs/08-ADAPTER-LAYER.md) | Schema-mapping layer for real-world (non-CERT) log formats |
| [`docs/09-DELIVERY-PLAN.md`](docs/09-DELIVERY-PLAN.md) | Build order, hackathon timeline, demo script, judge Q&A prep |
| [`docs/10-LIVE-DEMO.md`](docs/10-LIVE-DEMO.md) | Two-laptop live-injection demo mechanism |
| [`docs/11-MITIGATION.md`](docs/11-MITIGATION.md) | Automated threat mitigation pipeline: config, webhook, mock remediation, audit trail |

### Architecture decision records

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-two-axis-scoring.md) | Risk and confidence are separate axes |
| [0002](docs/adr/0002-declarative-rules.md) | Rules are declarative YAML, not Python predicates |
| [0003](docs/adr/0003-log-odds-scoring.md) | Log-odds additive scoring with category saturation |
| [0004](docs/adr/0004-template-narratives.md) | Template grammar for narratives, not an LLM |
| [0005](docs/adr/0005-parquet-plus-relational.md) | Parquet for events, relational for incidents |
| [0006](docs/adr/0006-peer-group-baselines.md) | Peer-group baselines alongside self-baselines |

### Open items from the pitch deck — resolved here

| Was open | Now |
|---|---|
| Exact success-metric numbers (placeholders: >85% precision, >75% recall) | [`07-EVALUATION`](docs/07-EVALUATION.md) — those placeholders are **not achievable at this base rate**; section 2 shows the arithmetic and gives the defensible reframing |
| Adapter layer for non-CERT log formats — "a talking point, not built" | [`08-ADAPTER-LAYER`](docs/08-ADAPTER-LAYER.md) — full declarative spec, coverage reporting, v1 build scope |
| Dashboard wireframes not started | [`06-FRONTEND-DESIGN`](docs/06-FRONTEND-DESIGN.md) — four screens wireframed, component tree, validated palette, chart specs |

## Stack

Python 3.11 · Pandas · scikit-learn · FastAPI · Pydantic v2 · SQLAlchemy · SQLite (demo) · React 18 + TypeScript + Tailwind + shadcn/ui · Recharts · react-force-graph

## Repository layout (target)

```
sentineltrace/
├── docs/                      # this specification set
├── engine/                    # detection core — pure Python, no web deps
│   ├── ingest/                # loaders + adapter layer
│   ├── features/              # feature extraction
│   ├── detect/                # rules, ML, scoring
│   ├── correlate/             # graph building, incident assembly
│   ├── explain/               # narrative + counterfactual
│   └── eval/                  # ground-truth scoring harness
├── api/                       # FastAPI service
├── web/                       # React dashboard
├── data/                      # CERT r4.2 (gitignored) + precomputed artifacts
├── tests/
└── run-local.ps1 / run-local.bat
```

## Quick start

Runs locally, no Docker required. `SENTINEL_DB=sqlite:///./data/demo.db` drops
Postgres entirely — the backend and frontend talk to a local SQLite file.

```powershell
./run-local.ps1
```

(or `run-local.bat`). This launches the FastAPI backend on
`http://localhost:8000` (docs at `/docs`) and the Vite dev server on
`http://localhost:5173`, which proxies `/api` straight to the backend.

There are no default credentials anywhere in this repo — create the first
account yourself:

```bash
python -m api.cli create-user \
  --username you --display-name "Your Name" --role detection_engineer
```

To (re-)run the real detection pipeline and evaluation report against a raw
log corpus (e.g. `./data/raw` or `./data/demo_live`) and load the results
into the demo database:

```bash
python -m api.load_pipeline --raw-dir data/demo_live
```
