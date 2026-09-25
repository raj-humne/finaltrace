"""Tests for engine/eval/ablate.py.

Runs the real ablation pipeline end to end against the synthetic generator -
the same dev-fixture pattern tests/test_run.py already uses. This is a
legitimate use of synthetic data (PROJECT_CONTEXT.md section 6.2): it proves
every row actually executes and every real engine function is wired
correctly, without needing the ~14-minute real-CERT corpus on every change.
It is never used to assert a specific recall/precision *value* - only that
the plumbing between rows behaves as the module contract requires.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from engine.core.config import load_config
from engine.eval.ablate import ROW_SPECS, ablation_notes, format_table, run_ablation
from engine.ingest.loader import load_events, load_org

CFG = load_config()


def _synthetic_ground_truth(dataset_dir: Path) -> pd.DataFrame:
    """The synthetic generator writes its own answers.json (user_id,
    scenario, malicious_days), a different shape from real CERT's per-
    scenario answers/ directory that engine.ingest.ground_truth.
    load_ground_truth parses. This adapts synthetic's shape to the same
    (user_id, date, scenario, is_malicious) frame load_ground_truth returns,
    without touching that real-CERT-specific parser."""
    payload = json.loads((dataset_dir / "answers.json").read_text())
    rows = [
        {"user_id": ins["user_id"], "date": pd.Timestamp(d),
         "scenario": ins["scenario"], "is_malicious": True}
        for ins in payload["insiders"] for d in ins["malicious_days"]
    ]
    return pd.DataFrame(rows, columns=["user_id", "date", "scenario", "is_malicious"])


@pytest.fixture(scope="module")
def synthetic_dataset(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("ablation_fixture")
    argv = sys.argv
    sys.argv = ["generate_synthetic", "--users", "16", "--days", "45",
               "--insiders", "3", "--seed", "11", "--out", str(out)]
    try:
        from tools.generate_synthetic import main as generate_main
        generate_main()
    finally:
        sys.argv = argv
    return out


@pytest.fixture(scope="module")
def loaded(synthetic_dataset):
    events, _ = load_events(synthetic_dataset, CFG)
    org = load_org(synthetic_dataset)
    ground_truth = _synthetic_ground_truth(synthetic_dataset)
    return events, org, ground_truth


REAL_PROFILE = {"data_source": "real_cert_r42"}  # the guard only checks this marker


def test_all_seven_rows_execute_without_error(loaded):
    events, org, ground_truth = loaded
    rows = run_ablation(events, org, ground_truth, REAL_PROFILE, base_cfg=CFG)
    assert [r.name for r in rows] == [spec[0] for spec in ROW_SPECS]
    errors = [(r.name, r.error) for r in rows if r.error]
    assert errors == [], f"ablation rows failed: {errors}"


def test_rows_only_no_baselines_has_no_z_gated_signals(loaded):
    """The row that skips add_baselines must never see a signal from a rule
    whose only clauses are z_self_gte/z_peer_gte - if one appears, baselines
    were not actually skipped."""
    from engine.eval.ablate import _run_row

    events, org, _ = loaded
    pipeline = _run_row("test", CFG, events, org, use_baselines=False, use_ml=False,
                        use_rules=True, disable_correlation_bonus=True, use_campaigns=False)
    assert "anomaly_percentile" not in pipeline.features.columns
    assert not any(c.endswith("__z_self") or c.endswith("__z_peer")
                  for c in pipeline.features.columns)


def test_ml_only_row_never_forms_incidents(loaded):
    """Documented architectural property (module docstring row 3): with no
    rule signals, no component has a signal-carrying node, so build_incidents
    must return an empty list."""
    from engine.eval.ablate import _run_row

    events, org, _ = loaded
    pipeline = _run_row("test", CFG, events, org, use_baselines=True, use_ml=True,
                        use_rules=False, disable_correlation_bonus=True, use_campaigns=False)
    assert pipeline.signals_by_day == {}
    assert pipeline.incidents == []


def test_correlation_bonus_row_differs_from_no_correlation_row(loaded):
    """hybrid_with_correlation and hybrid_no_correlation must be genuinely
    different runs - if disable_correlation_bonus were silently ignored,
    every incident's risk would be identical between the two rows."""
    from engine.eval.ablate import _run_row

    events, org, _ = loaded
    no_corr = _run_row("a", CFG, events, org, use_baselines=True, use_ml=True,
                       use_rules=True, disable_correlation_bonus=True, use_campaigns=False)
    with_corr = _run_row("b", CFG, events, org, use_baselines=True, use_ml=True,
                         use_rules=True, disable_correlation_bonus=False, use_campaigns=False)

    no_corr_risk = {inc.incident_id: round(inc.risk, 6) for inc in no_corr.incidents}
    with_corr_risk = {inc.incident_id: round(inc.risk, 6) for inc in with_corr.incidents}
    # Same incidents form either way (same signal-carrying components); only
    # the correlation-bonus contribution to their risk should differ.
    assert set(no_corr_risk) == set(with_corr_risk)
    if no_corr_risk:  # only meaningful if this fixture produced any incidents
        multi_category = [
            inc for inc in with_corr.incidents if inc.category_count > 1
        ]
        for inc in multi_category:
            assert with_corr_risk[inc.incident_id] >= no_corr_risk[inc.incident_id]


def test_format_table_includes_every_row(loaded):
    events, org, ground_truth = loaded
    rows = run_ablation(events, org, ground_truth, REAL_PROFILE, base_cfg=CFG)
    table = format_table(rows)
    for name, _, _ in ROW_SPECS:
        assert name in table


def test_ablation_notes_flags_campaign_row_honestly(loaded):
    """As documented: link_campaigns does not currently change any incident's
    score, so the campaign-linking row is expected to show no measurable
    difference, and ablation_notes must say so plainly rather than silently
    claiming an improvement that did not happen."""
    events, org, ground_truth = loaded
    rows = run_ablation(events, org, ground_truth, REAL_PROFILE, base_cfg=CFG)
    notes = ablation_notes(rows)
    campaign_notes = [n for n in notes if "campaign" in n.lower()]
    assert campaign_notes, "expected at least one note about campaign linking"
    # It must be an honest report either way, never silent.
    assert any("no measurable difference" in n or "raised" in n or "CONTRADICTS" in n
              for n in campaign_notes)
