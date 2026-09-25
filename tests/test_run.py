"""End-to-end pipeline tests for engine/run.py.

NFR-5 (determinism) is the one property that matters most here: fixed seeds,
sorted iteration, no wall-clock reads inside the engine, so the same input
and config must produce byte-identical output. This runs the whole pipeline
twice over a small generated fixture and diffs the results, rather than
trusting the design by inspection.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from engine.core.config import load_config
from engine.run import Pipeline

CFG = load_config()


@pytest.fixture(scope="module")
def tiny_fixture(tmp_path_factory) -> Path:
    """A small CERT-schema dataset via the same generator used for dev
    fixtures - fast enough to run twice per test session."""
    out = tmp_path_factory.mktemp("tiny_cert")
    argv = sys.argv
    sys.argv = ["generate_synthetic", "--users", "10", "--days", "40",
               "--insiders", "2", "--seed", "7", "--out", str(out)]
    try:
        from tools.generate_synthetic import main as generate_main
        generate_main()
    finally:
        sys.argv = argv
    return out


def test_pipeline_runs_end_to_end(tiny_fixture):
    pipeline = Pipeline(CFG).run(tiny_fixture)
    assert not pipeline.events.empty
    assert not pipeline.features.empty
    # Every incident must carry a triage lane once routed.
    for inc in pipeline.incidents:
        from engine.route.triage import route
        inc.triage_lane = route(inc.risk, inc.confidence, CFG).lane
        assert inc.triage_lane in ("AUTO_FLAG", "ANALYST_REVIEW", "MONITOR", "SUPPRESSED")


def test_pipeline_is_deterministic(tiny_fixture):
    p1 = Pipeline(CFG).run(tiny_fixture)
    p2 = Pipeline(CFG).run(tiny_fixture)

    assert len(p1.features) == len(p2.features)
    assert len(p1.incidents) == len(p2.incidents)
    assert len(p1.campaigns) == len(p2.campaigns)

    risks_1 = sorted((inc.incident_id, round(inc.risk, 6), round(inc.confidence, 6))
                     for inc in p1.incidents)
    risks_2 = sorted((inc.incident_id, round(inc.risk, 6), round(inc.confidence, 6))
                     for inc in p2.incidents)
    assert risks_1 == risks_2

    feats_1 = p1.features.sort_values(["user_id", "date"]).reset_index(drop=True)
    feats_2 = p2.features.sort_values(["user_id", "date"]).reset_index(drop=True)
    numeric_cols = feats_1.select_dtypes("number").columns
    assert (feats_1[numeric_cols].fillna(-999) == feats_2[numeric_cols].fillna(-999)).all().all()


def test_config_version_is_stable_across_runs(tiny_fixture):
    p1 = Pipeline(CFG).run(tiny_fixture)
    p2 = Pipeline(load_config()).run(tiny_fixture)
    assert p1.cfg.version == p2.cfg.version == CFG.version
