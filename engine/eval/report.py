"""CLI: run the full pipeline once and write the evaluation report + ablation
table against real CMU CERT r4.2 (docs/07-EVALUATION.md).

Usage:
    python -m engine.eval.report
    python -m engine.eval.report --raw-dir data/raw/r4.2 --skip-ablation
    python -m engine.eval.report --raw-dir data/synthetic --allow-synthetic

`--allow-synthetic` exists ONLY to smoke-test this CLI's own wiring (argument
parsing, running Pipeline, handing off to the harness) against the fast
synthetic fixture during development. It bypasses only THIS CLI's early
pre-check - `engine.eval.harness.assert_real_data`, called inside
`build_report`, has no bypass and always refuses non-real data regardless of
this flag (PROJECT_CONTEXT.md section 6.2). That is deliberate: a "real data"
guard with an escape hatch is not a guard. So with `--allow-synthetic` on
synthetic data, expect the pipeline to run to completion and then the run to
still correctly fail with no report written - that failure is the guard
working, not a bug.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from engine.core.config import load_config
from engine.eval.ablate import ablation_notes, format_table, run_ablation
from engine.eval.harness import (
    SyntheticDataRejected,
    build_day_scores,
    build_insider_index,
    build_report,
    summary_paragraph,
)
from engine.ingest.ground_truth import load_ground_truth
from engine.run import Pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=REPO_ROOT / "data" / "raw" / "r4.2")
    parser.add_argument("--answers-dir", type=Path,
                       default=REPO_ROOT / "data" / "raw" / "answers" / "answers")
    parser.add_argument("--profile", type=Path,
                       default=REPO_ROOT / "data" / "artifacts" / "dataset_profile.json")
    parser.add_argument("--out", type=Path,
                       default=REPO_ROOT / "data" / "artifacts" / "eval_report.json")
    parser.add_argument("--skip-ablation", action="store_true",
                       help="report only, skip the 7-row ablation study "
                            "(the ablation is ~7x the cost of one pipeline run)")
    parser.add_argument("--allow-synthetic", action="store_true",
                       help="dev-only: bypass the real-CERT guard for smoke-testing "
                            "this CLI. Never use for a reported number.")
    args = parser.parse_args(argv)

    if not args.profile.exists():
        print(f"missing dataset profile: {args.profile}\n"
             f"run Session 0 (engine/ingest/ground_truth.py) first.", file=sys.stderr)
        return 2
    dataset_profile = json.loads(args.profile.read_text())

    if not args.allow_synthetic and dataset_profile.get("data_source") != "real_cert_r42":
        print(f"refusing to run: {args.profile} has data_source="
             f"{dataset_profile.get('data_source')!r}, not real_cert_r42. "
             f"Pass --allow-synthetic only for dev smoke-testing this CLI itself.",
             file=sys.stderr)
        return 2

    cfg = load_config()
    print(f"config_version: {cfg.version}")

    t0 = time.time()
    pipeline = Pipeline(cfg).run(args.raw_dir)
    print(pipeline.ingest_report.summary())
    print(f"pipeline: {len(pipeline.features):,} user-days, "
         f"{len(pipeline.incidents):,} incidents, {len(pipeline.campaigns):,} "
         f"campaigns  ({time.time() - t0:.1f}s)")

    ground_truth = load_ground_truth(args.answers_dir)
    insiders = build_insider_index(ground_truth)
    print(f"ground truth: {len(insiders)} insiders")

    day_scores = build_day_scores(pipeline.features, pipeline.signals_by_day,
                                  pipeline.incidents, insiders, cfg)

    try:
        report = build_report(day_scores, pipeline.signals_by_day, insiders, cfg,
                             dataset_profile, cfg.version)
    except SyntheticDataRejected as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nreport written to {args.out}")
    print(f"\n{summary_paragraph(report)}")

    if not args.skip_ablation:
        print("\nrunning ablation study (7 pipeline runs)...")
        t0 = time.time()
        rows = run_ablation(pipeline.events, pipeline.org, ground_truth,
                           dataset_profile, base_cfg=cfg)
        print(f"ablation complete ({time.time() - t0:.1f}s)\n")
        print(format_table(rows))
        print()
        for note in ablation_notes(rows):
            print(f"- {note}")

        ablation_out = args.out.parent / "ablation_report.json"
        ablation_out.write_text(json.dumps(
            {"rows": [{"name": r.name, "description": r.description,
                     "report": r.report, "error": r.error} for r in rows],
             "notes": ablation_notes(rows)},
            indent=2, default=str))
        print(f"\nablation written to {ablation_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
