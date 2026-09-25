"""B4: contract tests hitting every endpoint and validating against the
generated OpenAPI schema (docs/05-API-SPEC.md section 1's endpoint index).
"""
from __future__ import annotations

import jsonschema
import pytest

from api.security.passwords import hash_password
from api.models.identity import Account

PASSWORD = "correct-horse-battery-staple-9"


@pytest.fixture()
def openapi_schema(client):
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    return r.json()


@pytest.fixture()
def analyst_client(client, db_session):
    account = Account(username="priya.s", display_name="Priya S", role="analyst", password_hash=hash_password(PASSWORD))
    db_session.add(account)
    db_session.commit()
    login = client.post("/api/v1/auth/login", json={"username": "priya.s", "password": PASSWORD})
    assert login.status_code == 200
    return client


def _resolve_ref(schema: dict, ref: str) -> dict:
    node = schema
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def assert_response_matches_schema(openapi_schema: dict, method: str, path_template: str, status_code: int, body) -> None:
    """Validate `body` against the response schema OpenAPI declares for this
    operation, resolving local $refs against the full document (this is the
    "validate against the generated OpenAPI schema" contract test, not just a
    smoke check that the call returns 200)."""
    operation = openapi_schema["paths"][path_template][method.lower()]
    response_spec = operation["responses"][str(status_code)]
    if "content" not in response_spec:
        assert body in (None, "") or body == {}
        return
    schema = response_spec["content"]["application/json"]["schema"]

    resolver = jsonschema.RefResolver(base_uri="", referrer=openapi_schema)

    class _LocalResolver(jsonschema.RefResolver):
        def resolve_remote(self, uri):  # pragma: no cover - not expected to trigger
            raise AssertionError(f"unexpected remote $ref: {uri}")

    local_resolver = _LocalResolver(base_uri="", referrer=openapi_schema, store={"": openapi_schema})
    validator = jsonschema.Draft202012Validator(schema, resolver=local_resolver)
    errors = sorted(validator.iter_errors(body), key=str)
    assert not errors, "\n".join(f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors)


def test_openapi_schema_is_complete(openapi_schema):
    expected = {
        "/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/me",
        "/api/v1/users", "/api/v1/users/{user_id}", "/api/v1/users/{user_id}/risk", "/api/v1/users/{user_id}/timeline",
        "/api/v1/incidents", "/api/v1/incidents/{incident_id}", "/api/v1/incidents/{incident_id}/graph",
        "/api/v1/incidents/{incident_id}/export", "/api/v1/incidents/{incident_id}/review",
        "/api/v1/campaigns", "/api/v1/campaigns/{campaign_id}",
        "/api/v1/rules", "/api/v1/rules/{rule_id}/stats",
        "/api/v1/detection/health", "/api/v1/eval/report", "/api/v1/analyze",
        "/api/v1/ingest", "/api/v1/ingest/runs", "/api/v1/ingest/runs/{run_id}",
    }
    assert expected <= set(openapi_schema["paths"])


def test_unauthenticated_requests_are_rejected(client):
    for path in ["/api/v1/users", "/api/v1/incidents", "/api/v1/campaigns", "/api/v1/rules", "/api/v1/detection/health"]:
        r = client.get(path)
        assert r.status_code == 401, path


def test_health_is_public_and_matches_schema(client, openapi_schema):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/health", 200, r.json())


def test_users_list_and_detail_match_schema(analyst_client, openapi_schema, seeded_db):
    r = analyst_client.get("/api/v1/users")
    assert r.status_code == 200
    body = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/users", 200, body)
    assert any(u["user_id"] == "AAF0535" for u in body["items"])

    r = analyst_client.get("/api/v1/users/AAF0535")
    assert r.status_code == 200
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/users/{user_id}", 200, r.json())
    assert r.json()["org"]["department"] == "Research"

    r = analyst_client.get("/api/v1/users/DOES-NOT-EXIST")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


def test_user_risk_and_timeline_match_schema(analyst_client, openapi_schema, seeded_db):
    r = analyst_client.get("/api/v1/users/AAF0535/risk")
    assert r.status_code == 200
    body = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/users/{user_id}/risk", 200, body)
    assert body["summary"]["peak_date"] == "2010-08-14"

    r = analyst_client.get("/api/v1/users/AAF0535/timeline", params={"date": "2010-08-14"})
    assert r.status_code == 200
    body = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/users/{user_id}/timeline", 200, body)
    assert len(body["events"]) == 7


def test_incident_list_detail_graph_export_match_schema(analyst_client, openapi_schema, seeded_db):
    r = analyst_client.get("/api/v1/incidents")
    assert r.status_code == 200
    body = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/incidents", 200, body)
    assert body["total"] == 3
    assert "AUTO_FLAG" in body["facets"]["lane"]

    incident_id = "INC-20100814-AAF0535-01"
    r = analyst_client.get(f"/api/v1/incidents/{incident_id}")
    assert r.status_code == 200
    detail = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/incidents/{incident_id}", 200, detail)
    assert detail["score"]["breakdown"]["prior_logit"] == -4.6
    assert len(detail["signals"]) == 6
    assert detail["campaign"]["campaign_id"] == "CMP-AAF0535-001"

    r = analyst_client.get(f"/api/v1/incidents/{incident_id}/graph")
    assert r.status_code == 200
    graph = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/incidents/{incident_id}/graph", 200, graph)
    assert graph["stats"]["node_count"] == 7

    r = analyst_client.get(f"/api/v1/incidents/{incident_id}/export")
    assert r.status_code == 200
    assert r.json()["incident"]["incident_id"] == incident_id

    r = analyst_client.get("/api/v1/incidents/NOPE")
    assert r.status_code == 404


def test_incident_review_flow_and_suppression_proposal(analyst_client, openapi_schema, seeded_db):
    incident_id = "INC-20100809-AAF0535-01"
    r = analyst_client.post(
        f"/api/v1/incidents/{incident_id}/review",
        json={
            "verdict": "benign",
            "note": "Backup operator; documented change window.",
            "analyst_id": "priya.s",
            "propose_suppression": {"scope": "user_rule", "user_id": "BKR0912", "rule_id": "stage.usb_after_dormancy"},
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert_response_matches_schema(openapi_schema, "post", "/api/v1/incidents/{incident_id}/review", 201, body)
    assert body["incident_status"] == "closed"
    assert body["suppression"]["status"] == "proposed"

    r = analyst_client.get(f"/api/v1/incidents/{incident_id}")
    assert r.json()["status"] == "closed"
    assert r.json()["review"]["verdict"] == "benign"

    # A closed incident refuses a second review without ?force=true (409).
    r = analyst_client.post(
        f"/api/v1/incidents/{incident_id}/review",
        json={"verdict": "confirmed_threat", "analyst_id": "priya.s"},
    )
    assert r.status_code == 409


def test_campaigns_match_schema(analyst_client, openapi_schema, seeded_db):
    r = analyst_client.get("/api/v1/campaigns")
    assert r.status_code == 200
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/campaigns", 200, r.json())
    assert r.json()["total"] == 1

    r = analyst_client.get("/api/v1/campaigns/CMP-AAF0535-001")
    assert r.status_code == 200
    body = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/campaigns/{campaign_id}", 200, body)
    assert len(body["stage_progression"]) == 3
    assert body["stage_progression"][-1]["stage"] == 4


def test_rules_and_rule_stats_match_schema(analyst_client, openapi_schema, seeded_db):
    r = analyst_client.get("/api/v1/rules")
    assert r.status_code == 200
    body = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/rules", 200, body)
    assert len(body) == 27

    r = analyst_client.get("/api/v1/rules/exfil.file_copy_to_usb/stats")
    assert r.status_code == 200
    stats = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/rules/{rule_id}/stats", 200, stats)
    assert stats["fire_count"] >= 1
    assert stats["configured_weight"] == 1.30

    r = analyst_client.get("/api/v1/rules/not.a.real.rule/stats")
    assert r.status_code == 404


def test_detection_health_matches_schema(analyst_client, openapi_schema, seeded_db):
    r = analyst_client.get("/api/v1/detection/health")
    assert r.status_code == 200
    body = r.json()
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/detection/health", 200, body)
    assert body["lane_mix"]


def test_eval_report_404_until_harness_runs(analyst_client):
    r = analyst_client.get("/api/v1/eval/report")
    assert r.status_code == 404


def test_analyze_matches_schema_and_force_recompute_is_503(analyst_client, openapi_schema, seeded_db):
    r = analyst_client.post(
        "/api/v1/analyze",
        json={"user_id": "AAF0535", "date_from": "2010-08-01", "date_to": "2010-08-24"},
    )
    assert r.status_code == 200
    body = r.json()
    assert_response_matches_schema(openapi_schema, "post", "/api/v1/analyze", 200, body)
    assert body["peak_risk"] > 0
    assert "INC-20100814-AAF0535-01" in body["incidents"]

    r = analyst_client.post(
        "/api/v1/analyze",
        json={"user_id": "AAF0535", "date_from": "2010-08-01", "date_to": "2010-08-24", "options": {"force_recompute": True}},
    )
    assert r.status_code == 503


def test_ingest_inline_and_runs_match_schema(analyst_client, openapi_schema):
    r = analyst_client.post(
        "/api/v1/ingest",
        json={
            "source": "device", "adapter": "cert_r42", "mode": "inline",
            "records": [
                {"id": "{R4A1-X}", "date": "08/14/2010 21:59:12", "user": "ZZZ9999", "pc": "PC-9001", "activity": "Connect"},
                {"id": "{R4A2-X}", "date": "not-a-date", "user": "ZZZ9999", "pc": "PC-9001", "activity": "Connect"},
            ],
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert_response_matches_schema(openapi_schema, "post", "/api/v1/ingest", 202, body)
    assert body["accepted"] == 1
    assert body["rejected"] == 1
    assert body["rejects_sample"][0]["reason"] == "unparseable_date"

    # Re-ingesting the same accepted record is a duplicate, not an error.
    r2 = analyst_client.post(
        "/api/v1/ingest",
        json={
            "source": "device", "adapter": "cert_r42", "mode": "inline",
            "records": [{"id": "{R4A1-X}", "date": "08/14/2010 21:59:12", "user": "ZZZ9999", "pc": "PC-9001", "activity": "Connect"}],
        },
    )
    assert r2.json()["duplicates_skipped"] == 1
    assert r2.json()["accepted"] == 0

    r = analyst_client.get("/api/v1/ingest/runs")
    assert r.status_code == 200
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/ingest/runs", 200, r.json())
    assert len(r.json()) >= 2

    run_id = body["run_id"]
    r = analyst_client.get(f"/api/v1/ingest/runs/{run_id}")
    assert r.status_code == 200
    assert_response_matches_schema(openapi_schema, "get", "/api/v1/ingest/runs/{run_id}", 200, r.json())


def test_ingest_dry_run_writes_no_events(analyst_client, db_session):
    from sqlalchemy import select

    from api.models.ingest import Event

    before = len(db_session.scalars(select(Event)).all())
    r = analyst_client.post(
        "/api/v1/ingest",
        json={
            "source": "device", "adapter": "cert_r42", "mode": "inline",
            "options": {"dry_run": True},
            "records": [{"id": "{R4A9-X}", "date": "08/14/2010 21:59:12", "user": "ZZZ8888", "pc": "PC-9002", "activity": "Connect"}],
        },
    )
    assert r.status_code == 202
    assert r.json()["status"] == "validated"
    after = len(db_session.scalars(select(Event)).all())
    assert after == before
