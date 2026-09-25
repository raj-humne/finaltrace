# 08 — Schema Adapter Layer

> This resolves the open item "a schema-mapping/adapter layer story for real-world log formats — currently just a talking point, not built". It is specified here as a buildable component with a concrete v1 scope, because a talking point collapses under one question: *"so what happens when I point it at my Okta logs?"*

---

## 1. The problem

The engine is built against CERT's five log types. Real organisations have none of them. They have Windows Security Event 4624, Okta system logs, CrowdStrike device-control events, Zscaler web proxy logs, Microsoft 365 message traces — different field names, different time formats, different identity keys, different semantics.

Hard-coding CERT's schema into feature extraction would mean rewriting the engine per customer. That is the failure mode this layer exists to prevent.

**The claim this layer lets us make honestly:** *the detection logic never changes. A new log source is a mapping file, not a code change.* Without it, that claim is marketing. With it, it is a file.

---

## 2. Where it sits

```
   raw log (any format)
          │
          ▼
  ┌───────────────────┐
  │  SourceAdapter    │   declarative YAML mapping
  │  ┌─────────────┐  │   1. reader     — csv | jsonl | evtx | api
  │  │ reader      │  │   2. field map  — source path -> canonical field
  │  │ field map   │  │   3. transforms — parse, normalise, derive
  │  │ transforms  │  │   4. semantics  — which canonical action this is
  │  │ semantics   │  │   5. identity   — resolve to a SentinelTrace user
  │  │ identity    │  │   6. validation — required fields, enums, ranges
  │  └─────────────┘  │
  └─────────┬─────────┘
            ▼
     canonical Event      ← everything downstream sees only this
            │
            ▼
   features → detect → correlate → explain
```

Everything above the line is per-source and declarative. Everything below is the engine, unchanged. CERT itself is implemented as an adapter (`cert_r42.yaml`) rather than as a privileged path — which is the only way to know the abstraction actually holds.

---

## 3. The canonical contract

An adapter's sole job is to emit valid `Event` records.

| Canonical field | Required | Notes |
|---|---|---|
| `user_id` | yes | After identity resolution (section 6) |
| `ts` | yes | tz-aware UTC |
| `source` | yes | One of the canonical source classes (section 4) |
| `action` | yes | From that source's controlled vocabulary |
| `pc_id` | no | Asset identifier where applicable |
| `attrs` | no | Source-specific; only keys the feature registry reads have meaning |

### 3.1 Canonical action vocabulary

Adapters map into this fixed set. A vendor action with no mapping is either dropped with a counted reason or mapped to `other` — never silently reinterpreted.

| Source class | Actions |
|---|---|
| `logon` | `logon`, `logoff`, `failed_logon`, `lock`, `unlock`, `session_start`, `session_end` |
| `device` | `connect`, `disconnect`, `mount`, `write_blocked` |
| `file` | `open`, `write`, `copy`, `delete`, `rename`, `move_to_removable`, `print` |
| `http` | `visit`, `upload`, `download` |
| `email` | `send`, `receive`, `forward` |

New source classes (`vpn`, `cloud_audit`, `badge`) are added by declaring a class and its vocabulary in `config/source_classes.yaml` plus the features that consume it. That is a v2 activity, but the extension point exists in v1 so the design does not have to change to accommodate it.

### 3.2 The attribute contract

The feature registry declares which `attrs` keys it reads, and each carries a type and an optional unit:

```yaml
# config/attribute_contract.yaml
device.removable:     { type: bool,   required_for: [stage.first_ever_usb] }
file.extension:       { type: string }
file.on_removable:    { type: bool,   required_for: [exfil.file_copy_to_usb] }
http.domain:          { type: string }
http.category:        { type: enum,   values: [job_search, cloud_storage, leak_platform,
                                               hacking_tools, webmail, neutral] }
http.bytes_out:       { type: int,    unit: bytes }
email.external:       { type: bool }
email.attachment_bytes: { type: int,  unit: bytes }
```

This is the load-bearing piece. An adapter is **validated against the contract at load time**, so a mapping that fails to supply `file.on_removable` produces an explicit startup report — *"rule `exfil.file_copy_to_usb` will not fire: no adapter supplies `file.on_removable`"* — rather than a silently absent detection. Detection coverage degrading invisibly is the worst possible failure in this product, and this is the mechanism that makes it impossible.

---

## 4. Adapter definition format

A complete, real example — Windows Security 4624 logon events:

```yaml
# adapters/windows_security.yaml
id: windows_security_4624
version: 1
source_class: logon
description: Windows Security Event Log, successful and failed interactive logons

reader:
  format: jsonl
  path_glob: "data/raw/winsec/*.jsonl"
  chunk_size: 100000

filter:                          # rows that do not match are skipped, not rejected
  - field: EventID
    op: in
    value: [4624, 4625, 4634]

map:
  raw_id:    "$.RecordNumber"
  ts:        "$.TimeCreated"
  user_id:   "$.TargetUserName"
  pc_id:     "$.Computer"
  _logon_type: "$.LogonType"
  _event_id:   "$.EventID"

transforms:
  - field: ts
    op: parse_datetime
    format: iso8601
    timezone: source            # or an IANA name when the log carries local time
  - field: user_id
    op: strip_domain_prefix     # DOMAIN\jdoe -> jdoe
  - field: user_id
    op: lowercase
  - field: pc_id
    op: strip_fqdn              # PC-4412.corp.example -> pc-4412

semantics:                       # first match wins
  action:
    - when: { _event_id: 4624, _logon_type: { in: [2, 10, 11] } }
      value: logon
    - when: { _event_id: 4625 }
      value: failed_logon
    - when: { _event_id: 4634 }
      value: logoff
    - default: other

attrs:
  logon.interactive: { from: _logon_type, op: in_set, value: [2, 10, 11] }
  logon.remote:      { from: _logon_type, op: eq, value: 10 }

identity:
  strategy: directory_lookup
  key: sam_account_name
  on_miss: quarantine

validate:
  required: [user_id, ts, action]
  reject_if:
    - field: user_id
      op: in
      value: ["SYSTEM", "ANONYMOUS LOGON", "LOCAL SERVICE", "NETWORK SERVICE"]
  ts_range: { min: "2000-01-01", max: "+1d" }

provenance:
  vendor: Microsoft
  doc: "Security event 4624 — an account was successfully logged on"
  mapped_by: team-sentineltrace
  mapped_at: 2026-09-24
```

### 4.1 Transform library

Small, closed, and pure — so an adapter cannot contain arbitrary code and cannot become a security hole of its own.

| Transform | Purpose |
|---|---|
| `parse_datetime` | Formats, epoch seconds/millis, timezone attachment |
| `strip_domain_prefix`, `strip_fqdn`, `lowercase`, `trim` | Identity and asset normalisation |
| `regex_extract`, `split_take` | Pull a field out of a composite string |
| `url_domain` | Host from a URL |
| `lookup` | Table lookup against a config file (domain → category) |
| `map_values` | Enum remap |
| `coalesce` | First non-null of several source paths |
| `to_bool`, `to_int`, `to_bytes` | Typing, with unit conversion |
| `hash` | Pseudonymise a field at ingest |
| `constant` | Fixed value for a source that lacks the field |

No expression language, no `eval`. A transform that does not exist is a feature request, not an escape hatch. This keeps adapters reviewable by someone who is not a Python developer — which is the point of having them.

---

## 5. Semantic mapping: the hard part

Field renaming is trivial. Meaning is not, and this is where an honest design differs from a hand-wave.

### 5.1 Semantic gaps are declared, not papered over

Each adapter declares what it **cannot** supply:

```yaml
coverage:
  supplies:  [logon.interactive, logon.remote]
  missing:
    - attr: device.removable
      reason: "Windows Security does not carry device-class information"
      impact: "stage.first_ever_usb, exfil.file_copy_to_usb will not fire from this source"
      remedy: "Pair with a device-control source (CrowdStrike, Ivanti) or Windows 6416"
```

At startup the engine merges `supplies` across all loaded adapters and computes **rule coverage**:

```
Adapter coverage report
─────────────────────────────────────────────────────────────
  27 rules defined
  19 fully supported
   5 partially supported   (degraded strength, flagged on each signal)
   3 unsupported           — will never fire:
       exfil.leak_platform_visit   needs http.category
       evade.activity_after_logoff needs paired session events
       exfil.bcc_external          needs email.bcc

  Estimated insider recall impact: scenario 1 detection degraded
  (leak-platform terminal signal unavailable)
─────────────────────────────────────────────────────────────
```

This report is the deployment artifact. It is also the honest answer to "will this work on our logs": *here is exactly which detections you get and which you do not, before you buy anything.*

### 5.2 Semantic equivalence, not field equivalence

Three examples where the mapping is a judgement and must be recorded as one:

| CERT concept | Real-world source | The judgement |
|---|---|---|
| `device Connect` | CrowdStrike `DcUsbDeviceConnected` | CrowdStrike fires per *device*; CERT fires per *session*. The adapter coalesces events within 60s into one `connect`, and records the coalescing rule in provenance |
| `file open` | Windows 4663 object access | 4663 is enormously noisier and needs SACL configuration. The adapter filters to configured sensitive paths and **declares** that `file_event_count` is therefore not comparable to CERT's — so baselines must be rebuilt, never transferred |
| `http upload` | Zscaler proxy log | Zscaler carries real `bytes_out`; CERT infers upload shape from URL form. The adapter supplies `http.bytes_out`, which *improves* the signal — and the rule catalogue's `upload_shaped_count` uses the better field when present, via the fallback chain in section 5.3 |

Recording these as judgements in `provenance` is what lets a future engineer understand why a number differs between deployments.

### 5.3 Graceful degradation with fallback chains

Rules declare a preference order over attributes rather than a single hard dependency:

```yaml
- id: exfil.cloud_upload_burst
  requires:
    - prefer: http.bytes_out          # best: real byte counts
      fallback: http.upload_shaped    # acceptable: URL-form inference
      degrade_strength: 0.7           # the weaker evidence is weighted lower
```

A signal produced from a fallback carries `evidence_quality: "degraded"` through to the API and is rendered in the UI as *"inferred from request shape; byte counts unavailable"*. The analyst sees the provenance of the inference, and confidence is reduced accordingly — degradation flows into the confidence score rather than being hidden inside it.

---

## 6. Identity resolution

Every source names people differently: `AAF0535`, `aaron.fields@corp.com`, `CORP\afields`, `S-1-5-21-...`, `00u1a2b3c4d5`.

```yaml
identity:
  strategy: directory_lookup
  key: email | sam_account_name | upn | sid | employee_id | okta_id
  on_miss: quarantine        # quarantine | passthrough | reject
```

A resolution table is built from the directory source, mapping every known alias to a canonical `user_id`. Unresolved principals go to a `quarantine` table with a count and samples, surfaced in the ingest report.

**`on_miss: quarantine` is the default and is deliberate.** `passthrough` would create phantom users whose baselines are meaningless and whose anomaly scores are noise; `reject` would silently lose events. Quarantine keeps the data, refuses to score it, and tells someone. Service accounts and shared mailboxes are handled by an explicit exclusion list rather than by hoping they fail to resolve.

---

## 7. Validation and testing

### 7.1 `POST /ingest` with `dry_run: true`

The safe path for a new adapter. Parses, maps, validates, and reports — writing nothing.

```json
{
  "status": "validated",
  "adapter": "windows_security_4624",
  "rows_read": 100000,
  "rows_mapped": 94112,
  "rows_filtered": 5888,
  "rows_rejected": 0,
  "identity": { "resolved": 93980, "quarantined": 132,
                "quarantine_sample": ["svc_backup", "S-1-5-21-…-1004"] },
  "action_distribution": { "logon": 71204, "logoff": 20918, "failed_logon": 1990 },
  "ts_range": ["2026-08-01T00:00:12Z", "2026-08-31T23:59:41Z"],
  "attrs_supplied": ["logon.interactive", "logon.remote"],
  "warnings": [
    "ts had no timezone; 'source' applied — confirm the log is UTC",
    "2 rules depend on device.removable, which no loaded adapter supplies"
  ]
}
```

### 7.2 Golden-file tests

Each adapter ships `adapters/tests/<id>/input.jsonl` and `expected_events.json`. CI asserts exact output. An adapter without tests fails the build, generated from the adapter registry the same way rule tests are.

### 7.3 The conformance suite

A fixed set of behavioural assertions every adapter must satisfy: timestamps are tz-aware, actions are in the declared vocabulary, `user_id` is non-empty post-resolution, `event_id` is stable across two runs, and re-ingesting the same file produces zero new rows. This is what makes "adapters are interchangeable" a tested property rather than an intention.

---

## 8. v1 scope

Honest about what gets built for the hackathon versus what is designed.

| Adapter | Status | Effort |
|---|---|---|
| `cert_r42` | **Built** — the reference implementation, and proof the engine has no privileged path | — |
| `generic_csv` | **Built** — column mapping for arbitrary CSV; covers "point it at any spreadsheet export" | 3h |
| `windows_security` | **Specified**, mapping file written, tested against synthetic fixtures | 4h |
| `zscaler_web` | Specified, not built | — |
| `okta_system_log` | Specified, not built | — |
| `crowdstrike_device` | Specified, not built | — |
| `o365_message_trace` | Specified, not built | — |

**The demo claim is precisely this:** CERT runs through the same adapter mechanism as everything else, `generic_csv` ingests an arbitrary file live, and the coverage report shows exactly which rules a partial source supports. That is a demonstrated abstraction, not a promised one — and it is a far stronger statement than a slide listing seven vendor logos.

---

## 9. Why not a universal schema standard

OCSF, ECS, and the Sigma taxonomy all exist and all solve part of this. We do not adopt one wholesale because:

- **They are incomplete for this problem.** None carries the behavioural attributes insider detection needs — removable-media session pairing, upload shape, peer-group identity.
- **Adoption is partial in practice.** A customer with ECS-normalised logs still has three sources that are not.

The pragmatic position, and the one to state if asked: **the canonical model is deliberately small and ECS-compatible in naming where the concepts align**, and `adapters/ecs_generic.yaml` maps the ECS common fields as a fast path for organisations that already normalise. We interoperate with the standard without depending on it — which is the right posture for a layer whose whole purpose is to absorb heterogeneity.
