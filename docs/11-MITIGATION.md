# 11. Automated Threat Mitigation Pipeline

Adds a configurable, automatic mitigation pipeline on top of the existing detection/correlation/scoring system: when a correlated incident's existing risk score ("threat weight") exceeds a configurable threshold, the API automatically dispatches a structured JSON payload to a remediation webhook, simulates isolating the flagged entity, and persists the action to SQLite for analyst auditability. No manual "isolate" button exists or is needed — the whole chain runs as a side effect of incident finalization.

This reuses the existing detection engine end to end. It does not compute a new score, a new graph, or a new incident model — "threat weight" **is** `Incident.risk`, the same log-odds risk score `engine/detect/scoring.py::compute_risk()` already produces (see `04-DETECTION-ENGINE.md`).

## Architecture

```
RAW EVENTS → FEATURES → BASELINES → RULES + ML → CORRELATION → INCIDENT → RISK/CONFIDENCE   (unchanged)
                                                                     │
                                                                     ▼
                                                       MITIGATION SERVICE (api/mitigation.py)
                                                                     │
                                                    threat_weight > configured threshold?
                                                          │                    │
                                                        yes                    no
                                                          │                    │
                                            build RemediationPayload      no automatic action
                                            POST → mock remediation           (no row written)
                                            simulate isolation
                                            persist MitigationAction
                                                          │
                                                          ▼
                                            /api/v1/mitigation/* + incident detail page
```

The comparison is strictly `threat_weight > threshold` — **equality does not trigger** ("exceeds", not "reaches").

Integration point: `api/load_pipeline.py::_persist_incidents()`, evaluated once per incident right after its graph (events/edges) is persisted. This one function is shared by both the full corpus bridge (`python -m api.load_pipeline`) and the live-demo path (`api/live_demo.py`), so mitigation is evaluated at incident finalization everywhere incidents are created — not bolted onto the demo as a special case. It is idempotent (see below), so replaying the same data never re-fires it.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `MITIGATION_ENABLED` | `true` | Global kill-switch. When `false`, `evaluate_and_mitigate()` short-circuits immediately — no evaluation, no row, regardless of threat weight. |
| `MITIGATION_THREAT_WEIGHT_THRESHOLD` | `70` | The threshold `Incident.risk` must strictly exceed. |
| `MITIGATION_WEBHOOK_URL` | `http://localhost:8000/api/v1/mock-remediation/isolate` | Where the remediation payload is POSTed. Point this at a real SOAR/firewall webhook in a real deployment. |
| `MITIGATION_WEBHOOK_TIMEOUT_SECONDS` | `5` | Outbound HTTP timeout. |

All four are read in `api/settings.py`, following this repo's existing settings pattern (a frozen dataclass populated from `os.environ` once at import time) — no threshold or URL is ever hardcoded in `api/mitigation.py`.

## Database

New table `mitigation_actions` (Alembic revision `a86e95be8a23`, on top of `2844566c110f`, on top of the original `1b81a2393e53`):

| Column | Notes |
|---|---|
| `mitigation_action_id` | PK |
| `incident_id` | FK → `incidents.incident_id` (CASCADE), **UNIQUE** — at most one mitigation action per incident, ever (idempotency) |
| `user_id`, `flagged_ip` | copied from the incident at trigger time |
| `threat_weight`, `threshold` | the exact values compared at trigger time |
| `action_type`, `target_type`, `target_value` | e.g. `ISOLATE` / `ip` / `10.4.201.3` |
| `status` | `SUCCESS` \| `FAILED` (webhook outcome) |
| `webhook_url`, `webhook_status_code`, `webhook_response` | no secrets — the URL has no embedded auth token |
| `isolation_status` | `SIMULATED_ISOLATED` \| `NOT_ISOLATED` — never a real action |
| `reason`, `error_message` | human-readable, safe (no secrets) |
| `payload` | the exact JSON sent, verbatim |
| `created_at`, `completed_at` | |

Also added: `events.ip_address` and `incidents.pc_id` / `incidents.flagged_ip`. The CERT dataset this engine scores has no real IP field (events carry a workstation hostname, `pc_id`, never an IP) — `engine/core/ip_mapping.py::pc_to_ip()` deterministically derives a stable-looking private IP from the hostname (same hostname → same IP, always), clearly documented as synthetic. This is a real column in the data model, not a value fabricated ad hoc inside the mitigation payload builder.

Run migrations: `alembic upgrade head` (SQLite for the hackathon demo, same as the rest of this repo).

## Mitigation service — `api/mitigation.py`

Kept as a flat module under `api/`, matching this repo's existing convention (`api/assistant.py`, `api/live_demo.py`, `api/load_pipeline.py` — no `api/services/` package exists elsewhere in this codebase).

- `build_remediation_payload(db, incident)` — the real incident graph summary (node/edge counts from `incident_events`/`incident_edges`, a capped sample of real event nodes, real evidence rule ids via the same Attribution/Signal join the incident detail page uses). Nothing here is fabricated.
- `simulate_isolation(incident)` / the isolation fields on the persisted row — never a real action. No OS account is disabled, no firewall rule is touched, no process is killed.
- `_dispatch_webhook(...)` — POSTs the payload, with a request timeout, and turns *any* failure (connection refused, timeout, 4xx/5xx, malformed response) into a `FAILED` result rather than raising. A flaky or unreachable remediation service can never crash incident processing.
- `evaluate_and_mitigate(db, incident)` — the one entry point. Checks `MITIGATION_ENABLED`, checks idempotency (a `MitigationAction` row already exists for this incident → return it unchanged, no re-dispatch), checks `risk > threshold`, then dispatches + persists. The `MitigationAction` row is written **regardless of webhook outcome** — auditability cannot depend on the remote service being up.

## Mock remediation endpoint

`POST /api/v1/mock-remediation/isolate` (`api/routers/mock_remediation.py`) — unauthenticated (a real remediation vendor's inbound webhook wouldn't hold our analysts' session cookies), validates the payload against the same `RemediationPayload` schema the service builds, logs the request, and returns a simulated result. It never performs a real action.

## API endpoints (authenticated, read-only)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/mitigation/status` | Current enabled/threshold/webhook config (no secrets) |
| `GET /api/v1/mitigation/actions` | List all mitigation actions (optional `?incident_id=`) |
| `GET /api/v1/mitigation/actions/{id}` | One action by id |
| `GET /api/v1/mitigation/incidents/{incident_id}` | The action for one incident (404 if none) |

There is deliberately no write/trigger endpoint — the challenge requires *automatic* mitigation, not a manual destructive control. The incident detail page (`GET /api/v1/incidents/{id}`) also embeds `mitigations: MitigationActionOut[]` (0 or 1 entries) so an analyst sees it inline.

## Frontend

`web/src/components/shared/MitigationPanel.tsx`, added to the existing incident detail page (`web/src/pages/IncidentPage.tsx`) as another section in the same hairline-divided frame — no new design system. Shows threat weight vs. threshold (reusing the existing `ScoreMeter`), a status chip (glyph + word + color, matching `LaneChip`'s accessibility pattern, not color alone), action/target, webhook outcome, isolation status, and the reason. Types are generated from the live OpenAPI schema (`npm run generate:types:fixture`), never hand-written.

## Tests — `tests/test_mitigation.py`

15 tests, including the three critical threshold-boundary cases from the spec (`85 > 70` triggers, `60 < 70` does not, `70 == 70` does not), configurability, payload shape, the mock endpoint's real contract, webhook-failure handling (connection refused *and* HTTP error, both recorded as `FAILED`/`NOT_ISOLATED`, never crashing), idempotency (a second evaluation of the same incident never re-dispatches), auth on every mitigation endpoint, and one full end-to-end test that does **not** call the mitigation service directly: it drives the real `/api/v1/live-demo/inject` endpoint (real injected events → real `engine.run.Pipeline` → real correlation → real incident → real risk score) and only then asserts mitigation fired automatically, is queryable via `/api/v1/mitigation/incidents/{id}`, and appears on the incident detail page.

Webhook dispatch in tests is routed through FastAPI's own `TestClient` (an in-process ASGI transport, not a real socket) so the *actual* `/mock-remediation/isolate` route code runs for real in every test — this is not a stand-in for the service, it is the real route without a physical port.

```bash
pytest tests/test_mitigation.py -v   # this feature only
pytest tests/ -q                     # full suite (193 tests)
```

## Running the live demo

```bash
# Terminal 1
MITIGATION_ENABLED=true MITIGATION_THREAT_WEIGHT_THRESHOLD=70 \
  SENTINEL_DB=sqlite:///./data/demo.db uvicorn api.main:app --reload

# Terminal 2 (web/)
npm run dev
```

Log in, then trigger the existing staged insider-threat scenario:

```bash
curl -s -b cookies.txt -X POST http://localhost:8000/api/v1/live-demo/inject \
  -H "Content-Type: application/json" -d '{"scenario": true}'
```

The real engine scores the real injected sequence (off-hours logon → foreign-workstation USB connect → file-copy burst → USB disconnect → upload to a leak platform) well past the default threshold. The response's `incidents_today[].mitigation` block, `GET /api/v1/mitigation/incidents/{incident_id}`, and the incident detail page all show the result — no isolate button was clicked anywhere in this flow.

## Example JSON webhook payload

```json
{
  "incident_id": "INC-20100309-AA0000-01",
  "threat_weight": 92.4,
  "threshold": 70.0,
  "user_id": "AA0000",
  "flagged_ip": "10.214.88.6",
  "action": "ISOLATE",
  "target_type": "ip",
  "target": "10.214.88.6",
  "graph_summary": {"node_count": 51, "edge_count": 63, "categories": 3, "stages": [2, 3, 4]},
  "nodes": [
    {"event_id": "{D-0000412}", "ts": "2010-03-09T21:59:00", "source": "device", "action": "Connect", "pc_id": "PC-1009"},
    {"event_id": "{F-0000501}", "ts": "2010-03-09T22:04:08", "source": "file", "action": "Copy", "pc_id": "PC-1009"}
  ],
  "reason": "threat_weight 92.4 exceeds configured threshold 70.0",
  "evidence": ["collect.file_burst", "exfil.file_copy_to_usb", "exfil.leak_platform_visit"],
  "timestamp": "2026-09-27T15:02:11.483210+00:00"
}
```

## Example SQLite audit record

```json
{
  "mitigation_action_id": 1,
  "incident_id": "INC-20100309-AA0000-01",
  "user_id": "AA0000",
  "flagged_ip": "10.214.88.6",
  "threat_weight": 92.4,
  "threshold": 70.0,
  "action_type": "ISOLATE",
  "target_type": "ip",
  "target_value": "10.214.88.6",
  "status": "SUCCESS",
  "webhook_url": "http://localhost:8000/api/v1/mock-remediation/isolate",
  "webhook_status_code": 200,
  "webhook_response": "{\"success\":true,\"simulated\":true,\"action\":\"ISOLATE\",\"target_type\":\"ip\",\"target\":\"10.214.88.6\",\"status\":\"ISOLATED\"}",
  "isolation_status": "SIMULATED_ISOLATED",
  "reason": "threat_weight 92.4 exceeds configured threshold 70.0",
  "error_message": null,
  "created_at": "2026-09-27T15:02:11.512900+00:00",
  "completed_at": "2026-09-27T15:02:11.601442+00:00"
}
```

## Limitations

- **Simulation only.** No real account is suspended, no real firewall rule is written, no real process is touched. `isolation_status` and the mock endpoint's response are both explicitly labeled simulated. A real deployment would replace `MITIGATION_WEBHOOK_URL` with the organization's approved IAM/network/DLP remediation system and would need real authentication/authorization on that call (out of scope here — webhook URLs in this repo carry no embedded credentials by design).
- **Synthetic IP.** `flagged_ip` is deterministically derived from a workstation hostname (`engine/core/ip_mapping.py`), not sourced from real network telemetry — the CERT dataset has none.
- **One mitigation per incident, forever.** By design (idempotency): if an incident's stored risk were ever revised after the fact, this pipeline would not re-evaluate it. There is no retry-on-failure path; a `FAILED` row stays `FAILED` unless the incident is deleted and rescored (e.g. via `live-demo/reset`).
- **Single mock target.** The bundled mock remediation endpoint always returns success for any well-formed payload; it does not model a real vendor's rate limits, auth, or partial failures beyond what the tests exercise (connection failure, HTTP error).
