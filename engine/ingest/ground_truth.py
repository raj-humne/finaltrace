"""Ground truth: real CERT r4.2 answers/ -> (user_id, date, scenario, is_malicious).

CERT's answer format is release-specific and is *not* proper CSV (readme.txt in the
answers archive says so explicitly). For r4.2 it is:

  - answers/insiders.csv: the master index. One row per insider:
    dataset, scenario, details (detail filename), user, start, end.
  - answers/r4.2-{1,2,3}/<details>: one file per insider (r4.2 is CERT's "dense
    needles" release, so each scenario has many instances, collected in a
    subdirectory per scenario). Rows are variable-length and interleaved in
    chronological order, tagged by a leading data-type column
    (logon/device/file/http/email/...). The timestamp is always the third field
    regardless of row type.

Malicious user-days are the dates on which an insider's detail file actually
records a row — not the [start, end] window from insiders.csv, which can span
many more calendar days than the insider was active on (07-EVALUATION section 1.1
requires user-day counts to be computed from the record dates, not assumed).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

CERT_TS = "%m/%d/%Y %H:%M:%S"
RELEASE = "4.2"


def _detail_dates(path: Path) -> list[datetime]:
    dates: list[datetime] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 3:
                continue
            try:
                dates.append(datetime.strptime(row[2].strip(), CERT_TS))
            except ValueError:
                continue
    return dates


def _detail_path(answers_dir: Path, rec: pd.Series) -> Path:
    return answers_dir / f"r{rec['dataset']}-{rec['scenario']}" / rec["details"]


def load_ground_truth(answers_dir: Path, release: str = RELEASE) -> pd.DataFrame:
    """Return one row per (user_id, malicious date) for every insider in `release`.

    Only malicious rows are emitted. Callers left-join against the full
    (user, date)-with-activity frame and treat non-matches as benign, since
    enumerating every benign pair here would be wasteful and is the caller's job.
    """
    master = pd.read_csv(answers_dir / "insiders.csv", dtype=str)
    master = master[master["dataset"] == release]
    if master.empty:
        raise ValueError(f"no insiders.csv rows for dataset={release!r}")

    rows: list[dict] = []
    for _, rec in master.iterrows():
        path = _detail_path(answers_dir, rec)
        if not path.exists():
            raise FileNotFoundError(f"ground truth detail file missing: {path}")
        dates = _detail_dates(path)
        if not dates:
            raise ValueError(f"no dated rows parsed from {path}")
        for day in sorted({d.date() for d in dates}):
            rows.append({
                "user_id": rec["user"],
                "date": pd.Timestamp(day),
                "scenario": int(rec["scenario"]),
                "is_malicious": True,
            })

    out = pd.DataFrame(rows, columns=["user_id", "date", "scenario", "is_malicious"])
    return out.sort_values(["user_id", "date"], kind="stable").reset_index(drop=True)


def _main() -> int:
    import json
    import sys
    import time

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.core.config import load_config
    from engine.ingest.loader import load_events

    root = Path(__file__).resolve().parents[2]
    raw_dir = root / "data" / "raw" / "r4.2"
    answers_dir = root / "data" / "raw" / "answers" / "answers"
    out_path = root / "data" / "artifacts" / "dataset_profile.json"

    cfg = load_config(str(root / "config"))

    t0 = time.time()
    events, report = load_events(raw_dir, cfg)
    ingest_seconds = time.time() - t0
    print(report.summary())
    print(f"ingest: {ingest_seconds:.1f}s")

    gt = load_ground_truth(answers_dir)

    activity_days = (
        events[["user_id", "date"]]
        .drop_duplicates()
        .rename(columns={"date": "ts_date"})
    )
    activity_days["ts_date"] = activity_days["ts_date"].dt.normalize()
    gt_norm = gt.assign(ts_date=gt["date"].dt.normalize())

    joined = activity_days.merge(
        gt_norm[["user_id", "ts_date", "is_malicious"]],
        on=["user_id", "ts_date"], how="left",
    )
    joined["is_malicious"] = joined["is_malicious"].fillna(False)

    total_users = events["user_id"].nunique()
    total_user_days = len(activity_days)
    malicious_user_days = int(joined["is_malicious"].sum())
    n_insiders = gt["user_id"].nunique()
    base_rate = malicious_user_days / total_user_days if total_user_days else 0.0

    # Sanity: every insider's malicious days should actually appear in the
    # activity frame (an insider absent from events entirely would mean the
    # ingest and the answers disagree about who exists).
    insiders_with_activity = gt["user_id"].isin(activity_days["user_id"]).all()

    profile = {
        "data_source": "real_cert_r42",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "config_version": cfg.version,
        "total_users": int(total_users),
        "total_user_days_with_activity": int(total_user_days),
        "insiders": int(n_insiders),
        "malicious_user_days": malicious_user_days,
        "base_rate": base_rate,
        "date_range": [str(report.ts_min.date()), str(report.ts_max.date())],
        "events_ingested": int(report.rows_accepted),
        "ingest_seconds": round(ingest_seconds, 1),
        "insiders_all_have_activity_rows": bool(insiders_with_activity),
        "per_scenario_insiders": {
            str(k): int(v) for k, v in gt.groupby("scenario")["user_id"].nunique().items()
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(json.dumps(profile, indent=2))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
