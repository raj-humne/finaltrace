# 03 — Data Model

---

## 1. Source schemas (CMU CERT r4.2)

Five activity logs plus an organisational directory, all keyed on `user`, `pc`, and `date`.

### 1.1 `logon.csv`
| Column | Type | Notes |
|---|---|---|
| `id` | string | `{XNNN-YNNNNNNNN-NNNNNNNN}` record id |
| `date` | datetime | `MM/DD/YYYY HH:MM:SS` |
| `user` | string | e.g. `AAF0535` |
| `pc` | string | e.g. `PC-0843` |
| `activity` | enum | `Logon` \| `Logoff` |

**Derived:** session pairing (logon to next logoff on the same pc), session duration, off-hours flag, own-vs-other PC.

### 1.2 `device.csv`
| Column | Type | Notes |
|---|---|---|
| `id` | string | |
| `date` | datetime | |
| `user`, `pc` | string | |
| `activity` | enum | `Connect` \| `Disconnect` |

**Derived:** removable-media session duration, connect count, first-ever-use flag, off-hours connect.

### 1.3 `file.csv`
| Column | Type | Notes |
|---|---|---|
| `id`, `date`, `user`, `pc` | | |
| `filename` | string | e.g. `XKQ4RPHE.doc` |
| `content` | text | **Not used.** Metadata-only policy (`01-PRD` section 9.4) |

**Derived:** file event count, distinct extensions, sensitive-extension ratio, count during an active USB session (the strongest single exfiltration primitive).

### 1.4 `http.csv`
| Column | Type | Notes |
|---|---|---|
| `id`, `date`, `user`, `pc` | | |
| `url` | string | |
| `content` | text | **Not used** |

**Derived:** domain, **domain category** (see 1.7), upload-shaped request count, visits to job-search / cloud-storage / hacking-tool categories, first-ever-domain flag.

### 1.5 `email.csv`
| Column | Type | Notes |
|---|---|---|
| `id`, `date`, `user`, `pc` | | |
| `to`, `cc`, `bcc` | string | semicolon-delimited |
| `from` | string | |
| `size` | int | bytes |
| `attachments` | int | count |
| `content` | text | **Not used** |

**Derived:** external-recipient count, self-send flag (personal domain in `to`), attachment bytes to external recipients, bcc-to-external count, recipient-count outlier.

### 1.6 `LDAP/*.csv` (monthly snapshots)
| Column | Notes |
|---|---|
| `employee_name`, `user_id`, `email` | identity |
| `role`, `business_unit`, `functional_unit`, `department`, `team` | **peer-group keys** |
| `supervisor` | org graph |

Snapshots are monthly. We build a `user_org` interval table (`valid_from`, `valid_to`) and forward-fill, so a user who changes department mid-window is compared against the right cohort on each date. A user who disappears between two snapshots gets a `departure_date` — the single most predictive contextual feature in the whole dataset, because CERT scenario 1 exfiltration clusters immediately before departure.

### 1.7 Domain categorisation (our addition, not in CERT)

`config/domain_categories.yaml` maps domains to categories by exact match and suffix rules:

| Category | Examples | Why it matters |
|---|---|---|
| `job_search` | job sites, recruiter portals | Precursor signal in CERT scenario 2 |
| `cloud_storage` | personal file-sharing hosts | Exfiltration channel |
| `leak_platform` | whistleblowing / paste sites | Scenario 1 terminal action |
| `hacking_tools` | keylogger / exploit distribution | Scenario 3 staging |
| `webmail` | personal mail | Exfiltration channel |
| `neutral` | everything else | Baseline volume |

Categories are data, not code, and the file is versioned with the config hash.

---

## 2. Canonical internal model

Everything from every source normalises into one shape. This is what makes the adapter layer (`08-ADAPTER-LAYER.md`) possible.

```python
@dataclass(frozen=True, slots=True)
class Event:
    event_id: str          # blake2b(source|raw_id|user|ts)[:16] — content-addressed
    user_id: str
    pc_id: str | None
    ts: datetime           # UTC, tz-aware
    source: Source         # LOGON | DEVICE | FILE | HTTP | EMAIL
    action: str            # logon, logoff, connect, disconnect, open, visit, send
    attrs: dict[str, Any]  # source-specific: filename, domain, category, size...
    ingest_run_id: str
```

**Design notes.** `attrs` is deliberately schemaless (JSONB in Postgres) so a new source adds no migration. Anything a *rule* needs to read is promoted into a typed feature column during extraction — so the schemaless part never reaches the hot path.

---

## 3. Entity relationship model

```
 user_org ──┐
            │  (role, department per date interval)
            ▼
          users ───┬──────────────▶ events ──────┐
                   │                  │          │ evidence
                   │                  ▼          ▼
                   ├──────▶ user_day_features   signals
                   │                  │          │
                   │                  └────┬─────┘
                   │                       ▼
                   ├──────────────▶    incidents ──▶ incident_events (join)
                   │                       │      ──▶ incident_edges  (graph)
                   │                       │      ──▶ attributions    (counterfactual)
                   │                       │      ──▶ narratives
                   │                       ▼
                   └──────────────▶   campaigns
                                           │
                                           ▼
                                        reviews ──▶ suppressions
                                           │
                                           ▼
                                       audit_log

 ingest_runs ──▶ events          config_versions ──▶ signals, incidents
 ground_truth ──▶ (eval only)    rule_stats  ◀── computed from signals + reviews
```

---

## 4. Feature catalogue

One row per `(user_id, date)`. Every baselined feature carries three columns: the raw value, `z_self`, and `z_peer`.

### 4.1 Temporal (7)
| Feature | Definition |
|---|---|
| `first_activity_min` | Minutes past midnight of first event |
| `last_activity_min` | Minutes past midnight of last event |
| `active_span_min` | Last minus first |
| `offhours_event_count` | Events outside the user's own learned working window |
| `offhours_event_ratio` | The above divided by total events |
| `is_weekend` | Boolean |
| `weekend_activity_count` | Events on a weekend day |

> **Off-hours is learned, not hard-coded.** The working window is the 5th–95th percentile of the user's event times over the trailing 30 days. A night-shift admin is not off-hours at 02:00; a 9-to-5 analyst is. Hard-coding 18:00–06:00 is the single most common source of false positives in this problem class.

### 4.2 Logon (6)
`logon_count`, `distinct_pc_count`, `own_pc_ratio`, `new_pc_count`, `after_hours_logon_count`, `max_session_duration_min`

### 4.3 Device / removable media (7)
`device_connect_count`, `usb_session_total_min`, `usb_offhours_connect_count`, `is_first_ever_usb` *(boolean, extremely high weight)*, `days_since_last_usb`, `usb_on_foreign_pc`, `usb_connect_after_hours_ratio`

### 4.4 File (8)
`file_event_count`, `distinct_file_count`, `distinct_extension_count`, `sensitive_ext_count` (doc/xls/pdf/zip/csv), `file_events_during_usb` *(the exfiltration primitive)*, `file_to_usb_ratio`, `new_extension_count`, `file_burst_max_per_10min`

### 4.5 HTTP (9)
`http_event_count`, `distinct_domain_count`, `new_domain_count`, `job_search_visits`, `cloud_storage_visits`, `leak_platform_visits`, `hacking_tool_visits`, `upload_shaped_count`, `offhours_http_ratio`

### 4.6 Email (8)
`email_sent_count`, `external_recipient_count`, `self_send_count`, `attachment_count`, `attachment_bytes_external`, `bcc_external_count`, `max_recipients_single_email`, `mass_email_flag` (recipients above the peer p99)

### 4.7 Contextual / organisational (6)
`days_to_departure` (null if not departing), `is_departing_within_30d`, `role_id`, `department_id`, `tenure_days`, `peer_cohort_size`

### 4.8 Cross-source interaction (5) — the correlation-aware features
| Feature | Definition | Why |
|---|---|---|
| `min_gap_logon_to_usb_min` | Minutes from off-hours logon to first USB connect | Intent proximity |
| `min_gap_usb_to_file_min` | USB connect to first file event | Copy behaviour |
| `min_gap_file_to_upload_min` | File access to next upload-shaped HTTP request | Exfiltration chain |
| `chain_completeness` | How many of logon → file → device → http stages occurred | 0–4 |
| `killchain_max_stage` | Furthest stage reached that day | Ordinal |

These five are where the product name earns itself. A single-source model cannot compute them.

**Total: 56 features**, comfortably above the FR-2.1 floor of 40.

### 4.9 Baseline columns
For each baselined feature `f`: `f`, `f__z_self`, `f__z_peer`.

Robust z-score, using median and MAD rather than mean and standard deviation:

```
z_self(f) = (f - median_30d(f)) / (1.4826 * MAD_30d(f) + eps)
z_peer(f) = (f - median_cohort(f)) / (1.4826 * MAD_cohort(f) + eps)
```

MAD is used because a single large insider day inside the trailing window inflates a standard deviation enough to hide the next one. Median/MAD resists that. `eps = 0.5` prevents a division blow-up on features that are zero for most users.

---

## 5. Relational schema (PostgreSQL DDL)

```sql
-- ============================================================
-- Reference / identity
-- ============================================================
CREATE TABLE users (
    user_id        TEXT PRIMARY KEY,
    employee_name  TEXT,
    email          TEXT,
    first_seen     DATE NOT NULL,
    last_seen      DATE NOT NULL,
    departure_date DATE
);

CREATE TABLE user_org (
    user_id     TEXT NOT NULL REFERENCES users(user_id),
    valid_from  DATE NOT NULL,
    valid_to    DATE NOT NULL,          -- exclusive; 9999-12-31 if current
    role        TEXT NOT NULL,
    department  TEXT NOT NULL,
    team        TEXT,
    supervisor  TEXT,
    cohort_key  TEXT NOT NULL,          -- md5(role || '|' || department)
    PRIMARY KEY (user_id, valid_from)
);
CREATE INDEX idx_user_org_cohort ON user_org (cohort_key, valid_from, valid_to);

-- ============================================================
-- Ingestion
-- ============================================================
CREATE TABLE ingest_runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('running','success','failed','partial')),
    source_files    JSONB NOT NULL,
    rows_accepted   BIGINT DEFAULT 0,
    rows_rejected   BIGINT DEFAULT 0,
    reject_samples  JSONB,
    ts_min          TIMESTAMPTZ,
    ts_max          TIMESTAMPTZ,
    adapter_id      TEXT,
    config_version  TEXT
);

CREATE TABLE events (
    event_id      TEXT PRIMARY KEY,                 -- content hash => idempotent
    user_id       TEXT NOT NULL REFERENCES users(user_id),
    pc_id         TEXT,
    ts            TIMESTAMPTZ NOT NULL,
    event_date    DATE NOT NULL,                    -- generated, partition key
    source        TEXT NOT NULL CHECK (source IN ('logon','device','file','http','email')),
    action        TEXT NOT NULL,
    attrs         JSONB NOT NULL DEFAULT '{}',
    ingest_run_id TEXT NOT NULL REFERENCES ingest_runs(run_id)
) PARTITION BY RANGE (event_date);

CREATE INDEX idx_events_user_date ON events (user_id, event_date);
CREATE INDEX idx_events_pc_ts     ON events (pc_id, ts);          -- lateral movement
CREATE INDEX idx_events_attrs     ON events USING GIN (attrs);    -- filename/domain lookups

-- ============================================================
-- Features
-- ============================================================
CREATE TABLE user_day_features (
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    event_date     DATE NOT NULL,
    cohort_key     TEXT NOT NULL,
    features       JSONB NOT NULL,     -- raw values, 56 keys
    z_self         JSONB NOT NULL,
    z_peer         JSONB NOT NULL,
    data_completeness  REAL NOT NULL CHECK (data_completeness BETWEEN 0 AND 1),
    baseline_maturity  REAL NOT NULL CHECK (baseline_maturity BETWEEN 0 AND 1),
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    config_version TEXT NOT NULL,
    PRIMARY KEY (user_id, event_date)
);
CREATE INDEX idx_udf_cohort_date ON user_day_features (cohort_key, event_date);

-- ============================================================
-- Detection output
-- ============================================================
CREATE TABLE config_versions (
    config_version TEXT PRIMARY KEY,     -- sha256 of merged YAML config
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload        JSONB NOT NULL,
    note           TEXT
);

CREATE TABLE signals (
    signal_id     BIGSERIAL PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(user_id),
    event_date    DATE NOT NULL,
    rule_id       TEXT NOT NULL,          -- 'ml.isoforest' for the anomaly signal
    category      TEXT NOT NULL,          -- access | staging | collection | exfil | evasion | context
    killchain_stage SMALLINT NOT NULL,    -- 0..5
    strength      REAL NOT NULL CHECK (strength BETWEEN 0 AND 1),
    weight        REAL NOT NULL,          -- log-odds evidence points, from config
    contribution  REAL NOT NULL,          -- post-saturation points actually applied
    evidence_event_ids TEXT[] NOT NULL,
    phrase        TEXT NOT NULL,          -- narrative clause fragment
    detail        JSONB NOT NULL,         -- feature values, thresholds, z-scores
    config_version TEXT NOT NULL REFERENCES config_versions(config_version)
);
CREATE INDEX idx_signals_user_date ON signals (user_id, event_date);
CREATE INDEX idx_signals_rule      ON signals (rule_id);

CREATE TABLE user_day_scores (
    user_id       TEXT NOT NULL REFERENCES users(user_id),
    event_date    DATE NOT NULL,
    risk          REAL NOT NULL CHECK (risk BETWEEN 0 AND 100),
    confidence    REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    logit         REAL NOT NULL,          -- pre-squash, for debugging
    rule_points   REAL NOT NULL,
    ml_points     REAL NOT NULL,
    corr_points   REAL NOT NULL,
    anomaly_pctl  REAL,
    risk_ewma     REAL,                   -- 7-day half-life trailing risk
    config_version TEXT NOT NULL,
    PRIMARY KEY (user_id, event_date)
);

-- ============================================================
-- Correlation
-- (campaigns is declared first: incidents carries an FK to it)
-- ============================================================
CREATE TABLE campaigns (
    campaign_id   TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(user_id),
    first_seen    DATE NOT NULL,
    last_seen     DATE NOT NULL,
    incident_count INT NOT NULL,
    max_stage     SMALLINT NOT NULL,
    peak_risk     REAL NOT NULL,
    stage_progression SMALLINT[] NOT NULL
);

CREATE TABLE incidents (
    incident_id     TEXT PRIMARY KEY,     -- INC-YYYYMMDD-USER-NN
    user_id         TEXT NOT NULL REFERENCES users(user_id),
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    risk            REAL NOT NULL,
    confidence      REAL NOT NULL,
    triage_lane     TEXT NOT NULL CHECK (triage_lane IN
                      ('AUTO_FLAG','ANALYST_REVIEW','MONITOR','SUPPRESSED')),
    status          TEXT NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','in_review','closed')),
    killchain_stages SMALLINT[] NOT NULL,
    signal_count    INT NOT NULL,
    event_count     INT NOT NULL,
    category_count  INT NOT NULL,
    over_dense      BOOLEAN NOT NULL DEFAULT FALSE,
    campaign_id     TEXT REFERENCES campaigns(campaign_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    config_version  TEXT NOT NULL
);
CREATE INDEX idx_incidents_triage ON incidents (triage_lane, risk DESC);
CREATE INDEX idx_incidents_user   ON incidents (user_id, window_start);

CREATE TABLE incident_events (
    incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    event_id    TEXT NOT NULL REFERENCES events(event_id),
    node_role   TEXT NOT NULL CHECK (node_role IN ('signal','context')),
    PRIMARY KEY (incident_id, event_id)
);

CREATE TABLE incident_edges (
    incident_id TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    src_event   TEXT NOT NULL,
    dst_event   TEXT NOT NULL,
    gap_seconds INT NOT NULL,
    edge_type   TEXT NOT NULL,   -- temporal | shared_pc | shared_file | stage_advance
    weight      REAL NOT NULL,
    PRIMARY KEY (incident_id, src_event, dst_event)
);

-- ============================================================
-- Explanation
-- ============================================================
CREATE TABLE narratives (
    incident_id  TEXT PRIMARY KEY REFERENCES incidents(incident_id) ON DELETE CASCADE,
    headline     TEXT NOT NULL,
    summary      TEXT NOT NULL,
    detail       TEXT NOT NULL,
    template_ids TEXT[] NOT NULL,        -- which grammar rules produced it
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE attributions (
    incident_id   TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    signal_id     BIGINT NOT NULL REFERENCES signals(signal_id),
    points        REAL NOT NULL,          -- contribution as scored
    risk_without  REAL NOT NULL,          -- counterfactual score
    delta         REAL NOT NULL,          -- risk - risk_without
    in_minimal_set BOOLEAN NOT NULL,
    rank          INT NOT NULL,
    PRIMARY KEY (incident_id, signal_id)
);

-- ============================================================
-- Feedback loop
-- ============================================================
CREATE TABLE reviews (
    review_id    BIGSERIAL PRIMARY KEY,
    incident_id  TEXT NOT NULL REFERENCES incidents(incident_id),
    verdict      TEXT NOT NULL CHECK (verdict IN
                   ('confirmed_threat','benign','inconclusive')),
    note         TEXT,
    analyst_id   TEXT NOT NULL,
    reviewed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    time_to_triage_sec INT
);
CREATE INDEX idx_reviews_incident ON reviews (incident_id);

CREATE TABLE suppressions (
    suppression_id BIGSERIAL PRIMARY KEY,
    scope          TEXT NOT NULL CHECK (scope IN ('user','cohort','rule','user_rule')),
    user_id        TEXT,
    cohort_key     TEXT,
    rule_id        TEXT,
    reason         TEXT NOT NULL,
    source_review  BIGINT REFERENCES reviews(review_id),
    status         TEXT NOT NULL DEFAULT 'proposed'
                     CHECK (status IN ('proposed','active','revoked')),
    created_by     TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ
);

CREATE TABLE audit_log (
    audit_id   BIGSERIAL PRIMARY KEY,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id  TEXT NOT NULL,
    before     JSONB,
    after      JSONB,
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- Evaluation (never joined in the serving path)
-- ============================================================
CREATE TABLE ground_truth (
    user_id      TEXT NOT NULL,
    event_date   DATE NOT NULL,
    scenario     SMALLINT NOT NULL,
    is_malicious BOOLEAN NOT NULL,
    PRIMARY KEY (user_id, event_date)
);
```

### 5.1 SQLite demo mode
Differences applied by the migration layer: `JSONB` becomes `TEXT` with JSON accessors, `TEXT[]` becomes a JSON array, `BIGSERIAL` becomes `INTEGER PRIMARY KEY AUTOINCREMENT`, partitioning is dropped, and GIN indexes are omitted. No engine or API code branches on this — it lives entirely in the SQLAlchemy dialect layer.

---

## 6. Parquet layout (bulk path)

```
data/artifacts/
├── events/          year=2010/month=01/part-000.parquet   # partitioned, ZSTD
├── features/        month=2010-01.parquet
├── baselines/       self/month=2010-01.parquet
│                    peer/month=2010-01.parquet
├── models/          cohort=<key>/isoforest.pkl + manifest.json
└── eval/            report-<config_version>.json
```

Events are written once at ingest and read column-wise by the feature stage. The engine never issues a SQL query for bulk work; the database holds only what the API serves.

---

## 7. Data quality rules

Enforced at ingest, surfaced in the ingest report, never silently applied.

| Check | Action on failure |
|---|---|
| Timestamp parses and falls inside the declared range | Reject row, sample it |
| `user_id` resolves in the LDAP directory | Accept, mark `orphan_user`, exclude from peer stats |
| `pc_id` format matches the expected pattern | Accept with a warning |
| Duplicate `event_id` | Skip silently (idempotency, by design) |
| Logon without a matching logoff | Accept; session duration is null, not zero |
| Device connect without a disconnect | Session assumed to run to end-of-day, flagged `inferred_end` |
| Event date beyond a user's `departure_date` | Accept and flag `post_departure` — a high-signal anomaly, not an error |

---

## 8. Retention and lifecycle

| Data | Retention | Rationale |
|---|---|---|
| Raw events | 90 days hot, then archived Parquet | Data minimisation (`01-PRD` section 9.8) |
| Features, baselines | 13 months | Needed for year-over-year baselines |
| Signals, incidents, narratives, attributions | 24 months | Investigation and audit horizon |
| Reviews, suppressions, audit log | 7 years | Governance |
| Models | Last 5 config versions | Reproducibility of historical scores |
