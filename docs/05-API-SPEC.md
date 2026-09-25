# 05 — API Specification

**Base URL:** `/api/v1` · **Format:** JSON · **Auth:** `Authorization: Bearer <token>` (static analyst token in v1; OIDC in v2)

---

## 0. Conventions

| Concern | Rule |
|---|---|
| Timestamps | ISO-8601 with offset, always UTC: `2010-08-14T21:47:00Z` |
| Dates | `YYYY-MM-DD` |
| Pagination | `?limit=` (default 50, max 500) and `?cursor=` (opaque); responses carry `next_cursor` |
| Sorting | `?sort=field` / `?sort=-field` for descending |
| Partial responses | `?include=` comma list, to keep the queue endpoint light |
| Idempotency | `POST /ingest` accepts `Idempotency-Key`; a repeat returns the original run |
| Errors | RFC 7807 `application/problem+json` |
| Versioning | Path-versioned. Additive changes only within `v1` |
| Rate limit | 120 req/min/token; `429` with `Retry-After` |

### Error envelope

```json
{
  "type": "https://sentineltrace.dev/errors/incident-not-found",
  "title": "Incident not found",
  "status": 404,
  "detail": "No incident with id INC-20100814-AAF0535-01",
  "instance": "/api/v1/incidents/INC-20100814-AAF0535-01",
  "trace_id": "01J8X2M4Q7"
}
```

| Code | Meaning |
|---|---|
| 400 | Malformed request |
| 401 / 403 | Missing or insufficient token |
| 404 | Unknown resource |
| 409 | Conflicting state (e.g. reviewing a closed incident) |
| 422 | Semantically invalid (e.g. `date_to` before `date_from`) |
| 429 | Rate limited |
| 503 | Pipeline run in progress and the resource is mid-write |

---

## 1. Endpoint index

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness, config version, data freshness |
| `POST` | `/ingest` | Submit a batch of raw records |
| `GET` | `/ingest/runs` · `/ingest/runs/{run_id}` | Ingest history and detail |
| `GET` | `/users` | Directory with current risk |
| `GET` | `/users/{user_id}` | Profile, org context, peer cohort |
| `GET` | `/users/{user_id}/risk` | Risk time series for a window |
| `GET` | `/users/{user_id}/timeline` | Event timeline for replay |
| `GET` | `/incidents` | Triage queue |
| `GET` | `/incidents/{id}` | Full incident with narrative and attribution |
| `GET` | `/incidents/{id}/graph` | Correlation graph payload |
| `GET` | `/incidents/{id}/export` | Evidence pack |
| `POST` | `/incidents/{id}/review` | Record an analyst verdict |
| `GET` | `/campaigns` · `/campaigns/{id}` | Multi-day linked incidents |
| `GET` | `/rules` · `/rules/{rule_id}/stats` | Catalogue and measured per-rule performance |
| `GET` | `/detection/health` | Alert volume, lane mix, calibration |
| `GET` | `/eval/report` | Latest evaluation report |
| `POST` | `/analyze` | Ad-hoc: score a user + window on demand |

---

## 2. Health

### `GET /health`
```json
{
  "status": "ok",
  "config_version": "sha256:9f2c…a41",
  "data": { "ts_min": "2010-01-02T00:00:00Z", "ts_max": "2011-05-31T23:59:00Z",
            "users": 1000, "events": 32770227, "last_pipeline_run": "2026-09-24T08:12:00Z" },
  "engine": { "rules_loaded": 27, "cohort_models": 41, "mode": "batch" }
}
```

---

## 3. Ingestion

### `POST /ingest`

Accepts either a file reference or an inline batch. Idempotent by content hash.

**Request**
```json
{
  "source": "device",
  "adapter": "cert_r42",
  "mode": "file",
  "path": "data/raw/device.csv",
  "options": { "chunk_size": 250000, "dry_run": false }
}
```

Inline form:
```json
{
  "source": "device",
  "adapter": "cert_r42",
  "mode": "inline",
  "records": [
    { "id": "{R4A1-...}", "date": "08/14/2010 21:59:12",
      "user": "AAF0535", "pc": "PC-4412", "activity": "Connect" }
  ]
}
```

**Response `202 Accepted`**
```json
{
  "run_id": "ing_01J8X2M4Q7",
  "status": "running",
  "source": "device",
  "accepted": 405380,
  "rejected": 12,
  "duplicates_skipped": 0,
  "ts_range": ["2010-01-02T07:12:00Z", "2011-05-31T18:44:00Z"],
  "rejects_sample": [
    { "row": 88211, "reason": "unparseable_date", "raw": "13/45/2010 99:99:99" }
  ],
  "links": { "self": "/api/v1/ingest/runs/ing_01J8X2M4Q7" }
}
```

`dry_run: true` validates and returns the same shape with `status: "validated"` and no writes — the safe way to test a new adapter against a real file.

### `GET /ingest/runs?status=&limit=`
Paginated list of `IngestRun` summaries.

---

## 4. Users

### `GET /users`
`?q=` name/id search · `?department=` · `?role=` · `?min_risk=` · `?departing_within=30` · `?sort=-current_risk`

```json
{
  "items": [
    {
      "user_id": "AAF0535",
      "name": "Aaron A. Fields",
      "role": "Engineer",
      "department": "Research",
      "cohort_key": "eng|research",
      "current_risk": 73.2,
      "risk_ewma": 41.8,
      "trend": "rising",
      "open_incidents": 2,
      "departing_in_days": 11
    }
  ],
  "next_cursor": "eyJvIjo1MH0",
  "total": 1000
}
```

### `GET /users/{user_id}`
```json
{
  "user_id": "AAF0535",
  "name": "Aaron A. Fields",
  "email": "AAF0535@dtaa.com",
  "org": { "role": "Engineer", "department": "Research", "team": "Team-07",
           "supervisor": "BKL0022", "cohort_size": 46 },
  "tenure_days": 812,
  "departure_date": "2010-08-25",
  "first_seen": "2010-01-04",
  "last_seen": "2010-08-24",
  "baseline": { "days_available": 217, "maturity": 1.0,
                "working_window": { "start_min": 498, "end_min": 1086 } },
  "current_risk": 73.2,
  "risk_ewma": 41.8,
  "incident_counts": { "AUTO_FLAG": 1, "ANALYST_REVIEW": 1, "MONITOR": 4 }
}
```

`working_window` is the *learned* off-hours boundary in minutes past midnight (here 08:18–18:06) — worth surfacing, because it is how the analyst sees that "off-hours" is personalised rather than hard-coded.

### `GET /users/{user_id}/risk?date_from=&date_to=&include=features`

```json
{
  "user_id": "AAF0535",
  "window": { "from": "2010-07-15", "to": "2010-08-24" },
  "series": [
    { "date": "2010-08-13", "risk": 22.4, "confidence": 0.71, "risk_ewma": 19.8,
      "signal_count": 1, "incident_ids": [] },
    { "date": "2010-08-14", "risk": 73.2, "confidence": 0.88, "risk_ewma": 24.9,
      "signal_count": 5, "incident_ids": ["INC-20100814-AAF0535-01"] }
  ],
  "peer_band": [
    { "date": "2010-08-14", "p50": 8.1, "p90": 19.4, "p99": 38.7 }
  ],
  "summary": { "peak_risk": 73.2, "peak_date": "2010-08-14",
               "days_above_threshold": 2, "trend": "rising" }
}
```

`peer_band` is what makes the chart honest: the user's line is drawn against their cohort's distribution, not against an absolute scale.

### `GET /users/{user_id}/timeline?date=2010-08-14`
Ordered events for the replay animation, each annotated with the running risk at that point.

```json
{
  "date": "2010-08-14",
  "events": [
    { "event_id": "a1f2…", "ts": "2010-08-14T21:47:03Z", "source": "logon",
      "action": "Logon", "pc_id": "PC-4412",
      "attrs": { "own_pc": true, "offhours": true },
      "signal_ids": [88231], "risk_after": 14.2, "stage": 2 },
    { "event_id": "b7c3…", "ts": "2010-08-14T21:59:12Z", "source": "device",
      "action": "Connect", "pc_id": "PC-4412",
      "attrs": { "days_since_last_usb": 243 },
      "signal_ids": [88232], "risk_after": 38.9, "stage": 2 }
  ],
  "working_window": { "start_min": 498, "end_min": 1086 },
  "final_risk": 73.2
}
```

---

## 5. Incidents

### `GET /incidents`

The triage queue. Filters: `?lane=` `?status=` `?min_risk=` `?min_confidence=` `?user_id=` `?date_from=` `?date_to=` `?stage_max=` `?campaign_id=` · default sort `-risk`.

```json
{
  "items": [
    {
      "incident_id": "INC-20100814-AAF0535-01",
      "user_id": "AAF0535",
      "user_name": "Aaron A. Fields",
      "department": "Research",
      "window": { "start": "2010-08-14T21:47:03Z", "end": "2010-08-14T22:31:40Z" },
      "risk": 73.2,
      "confidence": 0.88,
      "triage_lane": "AUTO_FLAG",
      "status": "open",
      "headline": "First removable-media use in 8 months — 5 correlated signals across 3 categories",
      "killchain_stages": [2, 3, 4],
      "max_stage": 4,
      "signal_count": 5,
      "event_count": 61,
      "campaign_id": "CMP-AAF0535-001",
      "top_signal": { "rule_id": "exfil.file_copy_to_usb", "delta": 18.4 }
    }
  ],
  "next_cursor": null,
  "total": 1,
  "facets": {
    "lane": { "AUTO_FLAG": 34, "ANALYST_REVIEW": 118, "MONITOR": 902, "SUPPRESSED": 47 },
    "max_stage": { "2": 210, "3": 480, "4": 371, "5": 40 }
  }
}
```

`facets` lets the queue header render lane counts without a second round trip.

### `GET /incidents/{incident_id}`

The endpoint the Incident Detail screen is built on.

```json
{
  "incident_id": "INC-20100814-AAF0535-01",
  "user": { "user_id": "AAF0535", "name": "Aaron A. Fields",
            "role": "Engineer", "department": "Research", "cohort_size": 46 },
  "window": { "start": "2010-08-14T21:47:03Z", "end": "2010-08-14T22:31:40Z",
              "duration_min": 44.6 },

  "score": {
    "risk": 73.2,
    "confidence": 0.88,
    "triage_lane": "AUTO_FLAG",
    "breakdown": {
      "prior_logit": -4.6,
      "rule_points": 3.38,
      "ml_points": 0.98,
      "correlation_points": 2.05,
      "total_logit": 1.81,
      "tau": 1.8
    },
    "confidence_terms": {
      "agreement": 1.0, "diversity": 1.0, "completeness": 0.8, "maturity": 1.0,
      "caps_applied": []
    }
  },

  "narrative": {
    "headline": "First removable-media use in 8 months — 5 correlated signals across 3 categories",
    "summary": "AAF0535 (Engineer, Research) acted between 21:47 and 22:31 on 2010-08-14, progressing from off-hours access through removable-media staging to file collection and an external upload. File activity was 6.2x this user's 30-day norm and 4.1x the norm for their role. The user's departure is recorded 11 days later.",
    "detail_bullets": [
      "[EXFIL · +18.4 pts] copied 47 files while removable media was connected (threshold 10; observed 47; z_self 5.8)",
      "[STAGE · +14.1 pts] connected removable media for the first time in 243 days",
      "[ML    ·  +9.6 pts] behaviour in the 99.1st percentile of the Engineer/Research cohort"
    ],
    "template_ids": ["head.top_signal_v1", "sum.stage_progression_v2", "det.signal_bullet_v1"]
  },

  "signals": [
    {
      "signal_id": 88234,
      "rule_id": "exfil.file_copy_to_usb",
      "name": "Bulk file activity during removable-media session",
      "category": "exfil",
      "stage": 4,
      "strength": 0.70,
      "weight": 1.30,
      "contribution": 0.91,
      "phrase": "copied 47 files while removable media was connected",
      "detail": { "feature": "file_events_during_usb", "observed": 47,
                  "threshold": 10, "z_self": 5.8, "z_peer": 4.1 },
      "evidence_event_ids": ["c9d1…", "c9d2…", "c9d3…"],
      "references": ["MITRE T1052.001"]
    }
  ],

  "attribution": {
    "note": "Contributions overlap due to category saturation and the correlation bonus; they do not sum to the total.",
    "items": [
      { "signal_id": 88234, "rule_id": "exfil.file_copy_to_usb",
        "risk_without": 54.8, "delta": 18.4, "rank": 1, "in_minimal_set": true },
      { "signal_id": 88232, "rule_id": "stage.first_ever_usb",
        "risk_without": 59.1, "delta": 14.1, "rank": 2, "in_minimal_set": true },
      { "signal_id": 88236, "rule_id": "ml.isoforest",
        "risk_without": 63.6, "delta": 9.6, "rank": 3, "in_minimal_set": false }
    ],
    "minimal_sufficient_set": ["exfil.file_copy_to_usb", "stage.first_ever_usb"],
    "alert_threshold": 40.0
  },

  "campaign": { "campaign_id": "CMP-AAF0535-001", "incident_count": 3,
                "first_seen": "2010-08-02", "last_seen": "2010-08-14",
                "stage_progression": [0, 1, 2, 3, 4] },

  "status": "open",
  "review": null,
  "config_version": "sha256:9f2c…a41",
  "links": { "graph": "/api/v1/incidents/INC-20100814-AAF0535-01/graph",
             "export": "/api/v1/incidents/INC-20100814-AAF0535-01/export" }
}
```

### `GET /incidents/{id}/graph`

Kept separate from the detail payload so the queue and the detail header render fast and the graph streams in after.

```json
{
  "incident_id": "INC-20100814-AAF0535-01",
  "over_dense": false,
  "nodes": [
    { "id": "a1f2…", "ts": "2010-08-14T21:47:03Z", "source": "logon",
      "action": "Logon", "label": "Logon PC-4412", "stage": 2,
      "risk_contribution": 6.2, "has_signal": true, "pc_id": "PC-4412",
      "user_id": "AAF0535" },
    { "id": "b7c3…", "ts": "2010-08-14T21:59:12Z", "source": "device",
      "action": "Connect", "label": "USB Connect", "stage": 2,
      "risk_contribution": 14.1, "has_signal": true, "pc_id": "PC-4412",
      "user_id": "AAF0535" }
  ],
  "edges": [
    { "source": "a1f2…", "target": "b7c3…", "gap_seconds": 729,
      "gap_label": "12 min", "type": "temporal", "weight": 0.87 },
    { "source": "b7c3…", "target": "c9d1…", "gap_seconds": 288,
      "gap_label": "5 min", "type": "stage_advance", "weight": 1.0 }
  ],
  "layout_hint": "temporal_left_to_right",
  "stats": { "node_count": 61, "edge_count": 143, "component_diameter": 7 }
}
```

### `POST /incidents/{id}/review`

**Request**
```json
{
  "verdict": "confirmed_threat",
  "note": "Confirmed with HR — resignation submitted 2010-08-13. Escalated to legal.",
  "analyst_id": "priya.s",
  "time_to_triage_sec": 74,
  "propose_suppression": null
}
```

A benign verdict may propose a suppression:
```json
{
  "verdict": "benign",
  "note": "Backup operator; nightly USB rotation is documented in CHG-4471.",
  "analyst_id": "priya.s",
  "propose_suppression": {
    "scope": "user_rule",
    "user_id": "BKR0912",
    "rule_id": "stage.usb_after_dormancy",
    "expires_at": "2011-02-01T00:00:00Z"
  }
}
```

**Response `201 Created`**
```json
{
  "review_id": 4412,
  "incident_id": "INC-20100814-AAF0535-01",
  "verdict": "confirmed_threat",
  "reviewed_at": "2026-09-24T09:31:02Z",
  "incident_status": "closed",
  "suppression": null,
  "effects": {
    "rule_stats_updated": ["exfil.file_copy_to_usb", "stage.first_ever_usb"],
    "user_risk_ewma_adjusted": false
  }
}
```

A proposed suppression is created with `status: "proposed"` — it does **not** take effect until a detection engineer activates it. An analyst cannot silence a rule on their own; that is a governance control, not an oversight.

`409` if the incident is already closed, unless `?force=true` with an elevated token.

### `GET /incidents/{id}/export?format=json|pdf`
Returns the full evidence pack: incident, signals, attribution, narrative, all referenced raw events, the config snapshot, and a watermark naming the exporting analyst and time. This is the artifact Persona B hands to HR or Legal.

---

## 6. Campaigns

### `GET /campaigns?user_id=&min_stage=&limit=`
### `GET /campaigns/{campaign_id}`
```json
{
  "campaign_id": "CMP-AAF0535-001",
  "user_id": "AAF0535",
  "first_seen": "2010-08-02",
  "last_seen": "2010-08-14",
  "incident_count": 3,
  "peak_risk": 73.2,
  "campaign_risk": 81.4,
  "max_stage": 4,
  "stage_progression": [
    { "date": "2010-08-02", "stage": 0, "incident_id": "INC-20100802-AAF0535-01",
      "risk": 28.1, "headline": "Sustained job-search browsing" },
    { "date": "2010-08-09", "stage": 2, "incident_id": "INC-20100809-AAF0535-01",
      "risk": 44.6, "headline": "Off-hours logon on an unfamiliar workstation" },
    { "date": "2010-08-14", "stage": 4, "incident_id": "INC-20100814-AAF0535-01",
      "risk": 73.2, "headline": "First removable-media use in 8 months" }
  ],
  "narrative": "Over 13 days this user progressed from job-search activity, through off-hours access on an unfamiliar workstation, to removable-media collection and an external upload. No single day exceeded the alert threshold before 2010-08-14; the progression did."
}
```

That last sentence is the slow-burn story in one line, generated from the same template grammar.

---

## 7. Rules and detection health

### `GET /rules`
The catalogue as loaded, including weights — so the UI can show exactly what is in force.

### `GET /rules/{rule_id}/stats?date_from=&date_to=`
```json
{
  "rule_id": "stage.first_ever_usb",
  "configured_weight": 1.60,
  "fire_count": 412,
  "fire_rate_per_user_day": 0.0008,
  "reviewed": 96,
  "confirmed": 71,
  "benign": 22,
  "inconclusive": 3,
  "observed_precision": 0.76,
  "measured_log_odds": 1.44,
  "weight_drift": -0.16,
  "recommendation": "within_tolerance"
}
```

`weight_drift` is the configured weight minus the empirically measured log-odds. It is the mechanism described in `04-DETECTION-ENGINE` section 3.3 and the direct answer to "how did you choose your weights".

### `GET /detection/health`
```json
{
  "window": { "from": "2010-01-01", "to": "2011-05-31" },
  "alert_volume": { "incidents_per_day": 0.41, "per_1k_users_per_day": 0.41 },
  "lane_mix": { "AUTO_FLAG": 34, "ANALYST_REVIEW": 118, "MONITOR": 902, "SUPPRESSED": 47 },
  "compression": { "signals_per_incident_mean": 4.6, "events_per_incident_mean": 38.2 },
  "calibration": {
    "bins": [
      { "confidence_range": [0.4, 0.5], "n": 61,  "observed_precision": 0.44 },
      { "confidence_range": [0.8, 0.9], "n": 88,  "observed_precision": 0.83 }
    ],
    "ece": 0.061
  },
  "top_firing_rules": [
    { "rule_id": "ctx.departure_imminent", "count": 3104, "observed_precision": 0.11 }
  ],
  "warnings": [
    "ctx.departure_imminent has low standalone precision — intended as a supporting signal only"
  ]
}
```

---

## 8. Evaluation

### `GET /eval/report?config_version=`
Returns the latest `EvalReport` — the full metric suite from `07-EVALUATION.md`, including the PR curve points, per-scenario recall, and the time-to-detect distribution.

---

## 9. Ad-hoc analysis

### `POST /analyze`

The runtime query described in the problem statement: an analyst picks a user and a window.

**Request**
```json
{
  "user_id": "AAF0535",
  "date_from": "2010-08-01",
  "date_to": "2010-08-24",
  "options": { "include_graph": true, "force_recompute": false }
}
```

**Response `200 OK`**
```json
{
  "user_id": "AAF0535",
  "window": { "from": "2010-08-01", "to": "2010-08-24" },
  "computed_in_ms": 312,
  "from_cache": true,
  "peak_risk": 73.2,
  "incidents": ["INC-20100802-AAF0535-01", "INC-20100809-AAF0535-01",
                "INC-20100814-AAF0535-01"],
  "campaigns": ["CMP-AAF0535-001"],
  "daily": [ { "date": "2010-08-14", "risk": 73.2, "confidence": 0.88,
               "signal_count": 5 } ],
  "narrative": "Over 13 days this user progressed from job-search activity, through off-hours access on an unfamiliar workstation, to removable-media collection and an external upload."
}
```

With `force_recompute: true` the engine re-runs detection for that window against the current config — this is how a detection engineer sees the effect of a weight change immediately, and it returns `503` if a pipeline run holds the write lock.

---

## 10. OpenAPI and client generation

FastAPI emits OpenAPI 3.1 at `/api/v1/openapi.json`. The frontend build runs `openapi-typescript` against it, so every response type in `06-FRONTEND-DESIGN.md` is generated rather than hand-written, and a backend contract change becomes a frontend type error rather than a runtime surprise.

---

## 11. Endpoint-to-requirement traceability

| Endpoint | Satisfies |
|---|---|
| `POST /ingest`, `GET /ingest/runs` | FR-1.6, FR-1.5 |
| `GET /users`, `/users/{id}` | FR-2.3, persona B peer context |
| `GET /users/{id}/risk` | User story: risk trend |
| `GET /users/{id}/timeline` | FR-7.3 timeline replay |
| `GET /incidents` | FR-4.2, FR-6.1 |
| `GET /incidents/{id}` | FR-3.2, FR-5.1, FR-5.3, FR-5.4 |
| `GET /incidents/{id}/graph` | FR-4.1, FR-4.3 |
| `POST /incidents/{id}/review` | FR-6.3, FR-6.4 |
| `GET /campaigns/{id}` | FR-4.4 |
| `GET /rules/{id}/stats` | FR-8.3 |
| `GET /detection/health` | NFR-6, metric 7.2 |
| `GET /eval/report` | FR-8.1, FR-8.2 |
| `POST /analyze` | Problem-statement runtime query |
