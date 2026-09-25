"""CLI-level test for engine/eval/report.py.

Verifies the argparse/file-I/O plumbing end to end against the fast synthetic
fixture, with `engine.eval.report.load_ground_truth` monkeypatched to the same
synthetic-answers adapter test_eval_ablate.py uses - `load_ground_truth`
itself is real-CERT-format-specific and is exercised separately against real
data by Session 0's ground-truth verification, not re-tested here.

This does NOT prove the CLI works against the real corpus - only that its
wiring (argument parsing, the real-data guard, file output, the summary
paragraph, the ablation hand-off) is correct. The real-corpus run is a
separate, explicit, much longer-running action.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

CFG_DIR = None  # use the real config/ directory - report.py loads it itself


def _synthetic_ground_truth(dataset_dir: Path) -> pd.DataFrame:
    payload = json.loads((dataset_dir / "answers.json").read_text())
    rows = [
        {"user_id": ins["user_id"], "date": pd.Timestamp(d),
         "scenario": ins["scenario"], "is_malicious": True}
        for ins in payload["insiders"] for d in ins["malicious_days"]
    ]
    return pd.DataFrame(rows, columns=["user_id", "date", "scenario", "is_malicious"])


@pytest.fixture(scope="module")
def synthetic_dataset(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("report_cli_fixture")
    argv = sys.argv
    sys.argv = ["generate_synthetic", "--users", "12", "--days", "35",
               "--insiders", "2", "--seed", "3", "--out", str(out)]
    try:
        from tools.generate_synthetic import main as generate_main
        generate_main()
    finally:
        sys.argv = argv
    return out


@pytest.fixture
def profile_path(tmp_path, request) -> Path:
    data_source = getattr(request, "param", "synthetic")
    p = tmp_path / "dataset_profile.json"
    p.write_text(json.dumps({"data_source": data_source}))
    return p


def test_refuses_without_allow_synthetic_flag(synthetic_dataset, profile_path, tmp_path, capsys):
    from engine.eval.report import main

    rc = main([
        "--raw-dir", str(synthetic_dataset),
        "--answers-dir", str(synthetic_dataset / "answers"),  # doesn't exist - must not matter
        "--profile", str(profile_path),
        "--out", str(tmp_path / "report.json"),
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert "real_cert_r42" in err
    assert not (tmp_path / "report.json").exists()


def test_refuses_when_profile_missing(tmp_path, capsys):
    from engine.eval.report import main

    rc = main(["--profile", str(tmp_path / "does_not_exist.json"),
              "--raw-dir", str(tmp_path), "--out", str(tmp_path / "out.json")])
    assert rc == 2
    assert "missing dataset profile" in capsys.readouterr().err


def test_allow_synthetic_runs_pipeline_but_the_report_guard_still_refuses(
        synthetic_dataset, profile_path, tmp_path, monkeypatch, capsys):
    """`--allow-synthetic` is a CLI-level convenience only. It must let the
    real pipeline wiring run end to end (proving argparse, Pipeline.run,
    ground-truth loading, and the hand-off to build_report all work) - but
    build_report's own guard (engine.eval.harness.assert_real_data) has no
    bypass and must still refuse to write a report, because that guard is
    the one thing standing between synthetic data and a number someone could
    mistake for a real result. A pass here means defense-in-depth: two
    independent checks, and weakening the outer one does not weaken the
    inner one."""
    import engine.eval.report as report_mod

    monkeypatch.setattr(report_mod, "load_ground_truth",
                        lambda _answers_dir: _synthetic_ground_truth(synthetic_dataset))

    out_path = tmp_path / "eval_report.json"
    rc = report_mod.main([
        "--raw-dir", str(synthetic_dataset),
        "--answers-dir", str(synthetic_dataset / "answers"),  # unused via monkeypatch
        "--profile", str(profile_path),
        "--out", str(out_path),
        "--allow-synthetic",
        "--skip-ablation",
    ])

    assert rc == 2  # the inner guard fired - no bypass exists for it
    assert not out_path.exists()  # nothing that looks like a report was written

    captured = capsys.readouterr()
    # But the pipeline itself genuinely ran to completion first - proving the
    # CLI's own wiring is correct up to the point the guard stops it.
    assert "pipeline:" in captured.out
    assert "ground truth:" in captured.out
    assert "refusing to emit an evaluation report" in captured.err
