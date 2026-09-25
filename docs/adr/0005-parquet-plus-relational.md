# ADR 0005 — Parquet for events, relational for incidents

**Status:** Accepted · **Date:** 2026-09-24

## Context

Two workloads with opposite shapes share this system.

**Bulk analytical:** scan ~32M events, group by user and day, compute 56 features over columns. Touches few columns, all rows, once per pipeline run.

**Transactional serving:** fetch one incident with its signals, attributions, narrative, and review. Touches many columns, few rows, repeatedly, with joins and foreign keys, and needs transactional writes when an analyst records a verdict.

Forcing both into one store makes one of them bad. All-Postgres means a 32M-row table the feature stage scans through a row-store; all-Parquet means hand-rolling joins and losing transactional verdict writes.

## Decision

Split by workload.

| Data | Store | Why |
|---|---|---|
| Raw events | **Parquet**, partitioned by month, ZSTD | Columnar scan; the feature stage reads 6 of 12 columns |
| Features, baselines | **Parquet** + a Postgres table for queried slices | Dense numeric matrix |
| Signals, incidents, campaigns, narratives, attributions, reviews | **PostgreSQL** (SQLite in demo) | Joins, foreign keys, transactional writes |
| Models | Pickle + manifest, versioned with the config hash | Reproducibility |
| Eval reports | JSON artifacts | Diffable in CI |

**The engine reads Parquet. The API reads the database. The batch runner is the only writer to the database.**

## Alternatives considered

**All PostgreSQL.** Simplest operationally, one connection string. Rejected on the feature-stage scan: a row-store reading 32M rows to compute column aggregates is the wrong access pattern, and a partitioned events table plus GIN indexes on `attrs` would carry real write cost during ingest for no read benefit in the bulk path.

**All Parquet / DuckDB.** Attractive — DuckDB would handle the analytical side beautifully and can join. Rejected because analyst verdicts need real transactional writes with concurrent readers, and because the API layer is far more ordinary against SQLAlchemy and Postgres. Reconsider if the serving side stays as small as it is now.

**ClickHouse for events.** The right answer at streaming scale, and named as such in the v2 scaling path. Overkill for a local, offline, laptop-bound demo.

## Consequences

**Good.** Each workload gets the store that fits. The database stays small — hundreds of incidents, not tens of millions of events — so SQLite is genuinely viable for the demo and the whole thing runs with no external dependency. **No read/write contention during a demo:** the UI reads the database while a pipeline run writes Parquet, so a pipeline run cannot slow the interface down.

**Costs.** Two storage systems to keep consistent. The pipeline must be re-run to move new events into incidents — there is no live path from a raw event to a served incident, which is acceptable for a batch product and is exactly what the streaming work in v2 changes. `event_id` is the only join key between the two worlds, so it must be stable; it is content-addressed, and the adapter conformance suite tests that it is identical across runs.

**Follow-on.** The SQLite/Postgres difference is confined to the SQLAlchemy dialect layer. No engine or API code branches on which is in use.
