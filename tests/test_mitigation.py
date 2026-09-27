"""Tests for the automated threat mitigation pipeline (Challenge 1):
api/mitigation.py (the service), api/routers/mock_remediation.py (the mock
remediation webhook target), api/routers/mitigation.py (the read-only
auditability API), and the automatic trigger wired into incident
finalization (api/load_pipeline.py::_persist_incidents, shared by the bulk
bridge and api/live_demo.py).

Unit-level tests build hand-crafted Incident/User rows so the threshold
comparison, idempotency, and audit-record behavior are verified precisely
against the spec's own example numbers (85 > 70 triggers, 60 < 70 does not,
70 == 70 does not - "exceeds" is strict), independent of the real engine's
exact risk numbers. The webhook dispatch in these tests is routed through
httpx's ASGI transport straight into the *real* FastAPI app - the actual
`/api/v1/mock-remediation/isolate` route really runs and really validates
the payload, just without a physical TCP socket. This is not a fake: it is
the standard way to test an app calling itself, and it means these tests
exercise the real mock-remediation contract, not a canned stand-in.

The end-to-end test (test_full_pipeline_...) does not call the mitigation
service directly at all: it drives the real live-demo injection endpoint,
which runs the actual detection -> correlation -> incident pipeline, and
only then asserts that mitigation fired automatically as a side effect of
incident finalization - proving the actual integrated pipeline, not just
the service in isolation.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import api.mitigation as mitigation
from api.main import app
from api.models.correlation import Incident
from api.models.identity import User
from api.models.mitigation import MitigationAction
from tests.test_live_demo import _restore_demo_csvs, demo_client  # noqa: F401  (reused fixtures)


def _asgi_client() -> TestClient:
    """A client that routes every request into the real FastAPI `app`
    in-process (no socket, no real network) - used so webhook dispatch in
    tests exercises the actual /mock-remediation/isolate route. FastAPI's
    own TestClient (Starlette's, built on httpx) is used rather than a raw
    httpx.Client(transport=httpx.ASGITransport(...)): the installed httpx
    (0.27) only implements ASGITransport's *async* handler, which a sync
    httpx.Client cannot drive - TestClient already wraps the sync-compatible
    bridge, and its .post() takes the same absolute-URL call our production
    _dispatch_webhook makes."""
    return TestClient(app)


class _CountingClient:
    """Wraps a real client and counts POSTs, so idempotency tests can prove
    a second evaluation never re-dispatches the webhook."""

    def __init__(self, inner: httpx.Client):
        self._inner = inner
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return self._inner.post(*args, **kwargs)


def _set_config(monkeypatch, **overrides) -> None:
    monkeypatch.setattr(mitigation, "settings", dataclasses.replace(mitigation.settings, **overrides))


def _make_incident(db_session, incident_id: str, risk: float, user_id: str = "U-MIT-TEST") -> Incident:
    db_session.merge(User(user_id=user_id, first_seen=dt.date(2010, 1, 1), last_seen=dt.date(2010, 1, 2)))
    db_session.flush()
    incident = Incident(
        incident_id=incident_id, user_id=user_id,
        window_start=dt.datetime(2010, 1, 1, tzinfo=dt.timezone.utc),
        window_end=dt.datetime(2010, 1, 1, 1, 0, tzinfo=dt.timezone.utc),
        risk=risk, confidence=0.8, triage_lane="AUTO_FLAG", status="open",
        killchain_stages=[3], signal_count=2, event_count=5, category_count=1,
        over_dense=False, config_version="test", pc_id="PC-TEST", flagged_ip="10.9.9.9",
    )
    db_session.add(incident)
    db_session.flush()
    return incident


# ============================================================== 1/2/3: threshold comparison
def test_high_threat_triggers_mitigation(db_session, monkeypatch):
    """85 > 70 -> mitigation triggers."""
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    incident = _make_incident(db_session, "INC-MIT-01", risk=85.0)

    result = mitigation.evaluate_and_mitigate(db_session, incident, client=_asgi_client())

    assert result.triggered is True
    assert result.action is not None
    assert result.action.status == "SUCCESS"


def test_low_threat_does_not_trigger(db_session, monkeypatch):
    """60 < 70 -> no webhook, no isolation, no mitigation action."""
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    incident = _make_incident(db_session, "INC-MIT-02", risk=60.0)

    result = mitigation.evaluate_and_mitigate(db_session, incident, client=_asgi_client())

    assert result.triggered is False
    assert result.action is None
    assert db_session.query(MitigationAction).filter(MitigationAction.incident_id == "INC-MIT-02").count() == 0


def test_exact_threshold_does_not_trigger(db_session, monkeypatch):
    """70 == 70 -> NO mitigation. The brief says "exceeds", so equality must
    not fire - this is the single most important boundary in the spec."""
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    incident = _make_incident(db_session, "INC-MIT-03", risk=70.0)

    result = mitigation.evaluate_and_mitigate(db_session, incident, client=_asgi_client())

    assert result.triggered is False
    assert result.action is None


# ============================================================== 4: configurable threshold
def test_threshold_is_configurable_without_code_changes(db_session, monkeypatch):
    """The same risk (85) is evaluated under two different configured
    thresholds - behavior changes purely from settings, no source edit."""
    incident_a = _make_incident(db_session, "INC-MIT-04A", risk=85.0)
    _set_config(monkeypatch, mitigation_threat_weight_threshold=90.0)
    result_a = mitigation.evaluate_and_mitigate(db_session, incident_a, client=_asgi_client())
    assert result_a.triggered is False

    incident_b = _make_incident(db_session, "INC-MIT-04B", risk=85.0)
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    result_b = mitigation.evaluate_and_mitigate(db_session, incident_b, client=_asgi_client())
    assert result_b.triggered is True


# ============================================================== 5: JSON payload shape
def test_payload_contains_all_required_fields(db_session, monkeypatch):
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    incident = _make_incident(db_session, "INC-MIT-05", risk=92.0)

    payload = mitigation.build_remediation_payload(db_session, incident)

    assert payload.incident_id == "INC-MIT-05"
    assert payload.threat_weight == 92.0
    assert payload.threshold == 70.0
    assert payload.user_id == "U-MIT-TEST"
    assert payload.flagged_ip == "10.9.9.9"
    assert payload.action == "ISOLATE"
    assert payload.target_type == "ip"
    assert payload.target == "10.9.9.9"
    assert payload.graph_summary.node_count == 5
    assert isinstance(payload.nodes, list)
    assert payload.reason
    assert isinstance(payload.evidence, list)
    assert isinstance(payload.timestamp, dt.datetime)


# ============================================================== 6/7: mock webhook + simulated isolation
def test_mock_remediation_endpoint_returns_simulated_isolation(demo_client):
    """The real mock-remediation route, called directly: validates the
    payload and returns the exact simulated-isolation contract."""
    body = {
        "incident_id": "INC-X", "threat_weight": 92.0, "threshold": 70.0,
        "user_id": "U1", "flagged_ip": "192.168.1.50", "action": "ISOLATE",
        "target_type": "ip", "target": "192.168.1.50",
        "graph_summary": {"node_count": 1, "edge_count": 0, "categories": 1, "stages": [1]},
        "nodes": [], "reason": "test", "evidence": [],
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    r = demo_client.post("/api/v1/mock-remediation/isolate", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data == {
        "success": True, "simulated": True, "action": "ISOLATE",
        "target_type": "ip", "target": "192.168.1.50", "status": "ISOLATED",
    }


def test_above_threshold_dispatches_webhook_and_simulates_isolation(db_session, monkeypatch):
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    incident = _make_incident(db_session, "INC-MIT-06", risk=92.0)

    result = mitigation.evaluate_and_mitigate(db_session, incident, client=_asgi_client())

    action = result.action
    assert action is not None
    assert action.status == "SUCCESS"
    assert action.webhook_status_code == 200
    assert action.isolation_status == "SIMULATED_ISOLATED"
    assert action.target_type == "ip"
    assert action.target_value == "10.9.9.9"


def test_payload_is_written_to_a_local_json_file(db_session, monkeypatch):
    """The remediation payload must exist as a plain file an analyst can
    open without a database client, not only inside the DB's payload column."""
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    incident = _make_incident(db_session, "INC-MIT-FILE-01", risk=88.0)

    mitigation.evaluate_and_mitigate(db_session, incident, client=_asgi_client())

    path = mitigation.settings.mitigation_payload_dir / "INC-MIT-FILE-01.json"
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["incident_id"] == "INC-MIT-FILE-01"
    assert on_disk["threat_weight"] == 88.0
    path.unlink()  # this test owns its file; don't leave it for other tests/demo runs


# ============================================================== 8: SQLite audit record
def test_mitigation_action_is_persisted_for_auditability(db_session, monkeypatch):
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    incident = _make_incident(db_session, "INC-MIT-07", risk=92.0)

    result = mitigation.evaluate_and_mitigate(db_session, incident, client=_asgi_client())

    stored = db_session.get(MitigationAction, result.action.mitigation_action_id)
    assert stored is not None
    assert stored.incident_id == "INC-MIT-07"
    assert stored.payload["incident_id"] == "INC-MIT-07"
    assert stored.created_at is not None
    assert stored.completed_at is not None


# ============================================================== 9: webhook failure handling
def test_webhook_connection_failure_does_not_crash_and_is_recorded_as_failed(db_session, monkeypatch):
    """Point the webhook at a closed local port - a real, fast, deterministic
    connection failure. The pipeline must not raise, and the audit record
    must say FAILED / NOT_ISOLATED, never a false success."""
    _set_config(
        monkeypatch, mitigation_threat_weight_threshold=70.0,
        mitigation_webhook_url="http://127.0.0.1:1/unreachable",
    )
    incident = _make_incident(db_session, "INC-MIT-08", risk=92.0)

    result = mitigation.evaluate_and_mitigate(db_session, incident)  # real client, no ASGI stub

    assert result.triggered is True
    action = result.action
    assert action.status == "FAILED"
    assert action.isolation_status == "NOT_ISOLATED"
    assert action.webhook_status_code is None
    assert action.error_message is not None
    assert "token" not in action.error_message.lower()  # no secrets ever logged


def test_webhook_http_error_response_is_recorded_as_failed(db_session, monkeypatch):
    """A real 404 from our own app (unknown path) via the ASGI transport -
    exercises the HTTP-status-error branch specifically."""
    _set_config(
        monkeypatch, mitigation_threat_weight_threshold=70.0,
        mitigation_webhook_url="http://testserver/api/v1/mock-remediation/not-a-real-path",
    )
    incident = _make_incident(db_session, "INC-MIT-09", risk=92.0)

    result = mitigation.evaluate_and_mitigate(db_session, incident, client=_asgi_client())

    assert result.action.status == "FAILED"
    assert result.action.isolation_status == "NOT_ISOLATED"
    assert result.action.webhook_status_code == 404


# ============================================================== 10: idempotency / duplicate processing
def test_duplicate_processing_does_not_redispatch_or_duplicate(db_session, monkeypatch):
    _set_config(monkeypatch, mitigation_threat_weight_threshold=70.0)
    incident = _make_incident(db_session, "INC-MIT-10", risk=92.0)
    client = _CountingClient(_asgi_client())

    first = mitigation.evaluate_and_mitigate(db_session, incident, client=client)
    second = mitigation.evaluate_and_mitigate(db_session, incident, client=client)

    assert first.triggered is True
    assert second.triggered is False
    assert second.already_processed is True
    assert second.action.mitigation_action_id == first.action.mitigation_action_id
    assert client.calls == 1  # the webhook was never called a second time
    assert db_session.query(MitigationAction).filter(MitigationAction.incident_id == "INC-MIT-10").count() == 1


def test_mitigation_disabled_short_circuits_entirely(db_session, monkeypatch):
    _set_config(monkeypatch, mitigation_enabled=False, mitigation_threat_weight_threshold=0.0)
    incident = _make_incident(db_session, "INC-MIT-11", risk=99.0)

    result = mitigation.evaluate_and_mitigate(db_session, incident, client=_asgi_client())

    assert result.triggered is False
    assert result.action is None


# ============================================================== 11: authentication on protected endpoints
def test_mitigation_endpoints_require_authentication():
    anon = TestClient(app)
    assert anon.get("/api/v1/mitigation/status").status_code == 401
    assert anon.get("/api/v1/mitigation/actions").status_code == 401
    assert anon.get("/api/v1/mitigation/actions/1").status_code == 401
    assert anon.get("/api/v1/mitigation/incidents/INC-X").status_code == 401


def test_mitigation_status_endpoint(demo_client, monkeypatch):
    _set_config(monkeypatch, mitigation_enabled=True, mitigation_threat_weight_threshold=70.0)
    r = demo_client.get("/api/v1/mitigation/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["threshold"] == 70.0


# ============================================================== 12: full end-to-end integrated pipeline
def test_full_pipeline_real_incident_to_automatic_mitigation(demo_client, monkeypatch):
    """The most important test: does NOT call api.mitigation directly.
    Drives the real live-demo scenario - real injected events, the real
    engine.run.Pipeline (detection + correlation), a real persisted
    incident with its real risk score - and only then checks that
    mitigation fired automatically as a side effect of incident
    finalization, with no manual isolation step anywhere in this test.
    """
    _set_config(monkeypatch, mitigation_enabled=True, mitigation_threat_weight_threshold=0.0)
    # The automatic hook inside incident finalization calls evaluate_and_
    # mitigate() with no explicit client (real production behavior); route
    # that real dispatch through the app in-process rather than a real
    # socket to localhost:8000, which nothing is bound to during tests -
    # the actual mock-remediation route still runs for real either way.
    monkeypatch.setattr(mitigation, "_client_factory", _asgi_client)

    r = demo_client.post("/api/v1/live-demo/inject", json={"scenario": True})
    assert r.status_code == 200, r.text
    inc = r.json()["incidents_today"][0]
    assert inc["risk"] > 0.0  # the real engine's real score, not a stub

    mit = inc["mitigation"]
    assert mit is not None, "mitigation did not fire automatically for a real high-risk incident"
    assert mit["status"] == "SUCCESS"
    assert mit["isolation_status"] == "SIMULATED_ISOLATED"
    assert mit["threat_weight"] == pytest.approx(inc["risk"], abs=0.05)

    # Independently queryable for analyst auditability, not just inline.
    listed = demo_client.get("/api/v1/mitigation/incidents/" + inc["incident_id"])
    assert listed.status_code == 200
    row = listed.json()
    assert row["incident_id"] == inc["incident_id"]
    assert row["status"] == "SUCCESS"
    assert row["payload"]["incident_id"] == inc["incident_id"]
    # This incident has a real, richly-connected correlation graph - the
    # payload's edge_count must reflect that, not an autoflush-timing
    # artifact that silently reads back 0 edges.
    assert row["payload"]["graph_summary"]["edge_count"] > 0

    # And visible on the incident detail page an analyst would actually open.
    detail = demo_client.get(f"/api/v1/incidents/{inc['incident_id']}")
    assert detail.status_code == 200
    mitigations = detail.json()["mitigations"]
    assert len(mitigations) == 1
    assert mitigations[0]["status"] == "SUCCESS"
