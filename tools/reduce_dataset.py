"""Reduce the real CERT r4.2 corpus to ~20% of its users, by disk footprint.

Keeps EVERY real labelled insider (all 70, across all 3 scenarios) so
evaluation/demo integrity survives, plus a random sample of benign users to
reach the target total. Filters all 5 log files + every LDAP monthly
snapshot to just the selected users, via chunked reads (the same pattern
engine/ingest/loader.py uses) so this never needs the full 14.5GB http.csv
in memory at once.

Writes to a NEW directory first and only swaps it in after every file has
been written successfully - the original is never touched until the reduced
version is confirmed complete, so a crash partway through cannot leave a
half-written, unusable dataset in place of the real one.

Usage:
    python -m tools.reduce_dataset --fraction 0.20 --seed 42
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "r4.2"
ANSWERS_DIR = REPO_ROOT / "data" / "raw" / "answers" / "answers"
STAGING_DIR = REPO_ROOT / "data" / "raw" / "r4.2_reduced"

SOURCE_FILES = ["logon.csv", "device.csv", "file.csv", "http.csv", "email.csv"]
USER_COLUMN = "user"


def select_users(fraction: float, seed: int) -> set[str]:
    insiders_df = pd.read_csv(ANSWERS_DIR / "insiders.csv", dtype=str)
    insiders = set(insiders_df[insiders_df["dataset"] == "4.2"]["user"].unique())

    latest_ldap = sorted((RAW_DIR / "LDAP").glob("*.csv"))[-1]
    all_users = set(pd.read_csv(latest_ldap, dtype=str)["user_id"].unique())

    target_total = round(len(all_users) * fraction)
    benign_pool = sorted(all_users - insiders)
    n_benign_needed = max(0, target_total - len(insiders))

    rng = __import__("random").Random(seed)
    benign_sample = set(rng.sample(benign_pool, min(n_benign_needed, len(benign_pool))))

    selected = insiders | benign_sample
    print(f"total users: {len(all_users)}  target: {target_total} ({fraction:.0%})")
    print(f"kept: {len(insiders)} insiders + {len(benign_sample)} benign = {len(selected)} total")
    return selected


def filter_source_file(name: str, selected_users: set[str], out_dir: Path) -> tuple[int, int]:
    """The first chunk always writes mode='w', header=True - even if it
    happens to contain zero matching rows, this still produces a valid,
    correctly-headered CSV, which is what guarantees `dst` exists and is
    readable afterward without a separate empty-file fallback."""
    src = RAW_DIR / name
    dst = out_dir / name
    total_in, total_out = 0, 0
    first_chunk = True
    for chunk in pd.read_csv(src, chunksize=500_000, dtype=str, keep_default_na=False):
        total_in += len(chunk)
        kept = chunk[chunk[USER_COLUMN].isin(selected_users)]
        total_out += len(kept)
        kept.to_csv(dst, mode="w" if first_chunk else "a", header=first_chunk, index=False)
        first_chunk = False
    return total_in, total_out


def filter_ldap(selected_users: set[str], out_dir: Path) -> None:
    out_ldap = out_dir / "LDAP"
    out_ldap.mkdir(parents=True, exist_ok=True)
    for path in sorted((RAW_DIR / "LDAP").glob("*.csv")):
        df = pd.read_csv(path, dtype=str)
        df[df["user_id"].isin(selected_users)].to_csv(out_ldap / path.name, index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fraction", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--keep-staging", action="store_true",
                       help="don't delete data/raw/r4.2_reduced/ after swapping it in")
    args = parser.parse_args(argv)

    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True)

    selected = select_users(args.fraction, args.seed)

    print("\nfiltering LDAP snapshots...")
    filter_ldap(selected, STAGING_DIR)

    for name in SOURCE_FILES:
        print(f"filtering {name}...", flush=True)
        n_in, n_out = filter_source_file(name, selected, STAGING_DIR)
        print(f"  {n_in:,} -> {n_out:,} rows ({n_out / max(1, n_in):.1%})")

    for extra in ("readme.txt", "license.txt", "psychometric.csv"):
        src = RAW_DIR / extra
        if src.exists():
            shutil.copyfile(src, STAGING_DIR / extra)

    print("\nverifying every expected file exists in the reduced dataset...")
    for name in SOURCE_FILES:
        assert (STAGING_DIR / name).exists(), f"missing {name} in staged output"
    assert (STAGING_DIR / "LDAP").is_dir()
    print("OK.")

    old_size = sum(f.stat().st_size for f in RAW_DIR.rglob("*") if f.is_file())
    new_size = sum(f.stat().st_size for f in STAGING_DIR.rglob("*") if f.is_file())
    print(f"\noriginal: {old_size / 1e9:.2f} GB   reduced: {new_size / 1e9:.2f} GB "
         f"({new_size / old_size:.1%})")

    print(f"\nSwapping {RAW_DIR} -> reduced version. The original is NOT recoverable "
         f"after this without re-downloading.")
    shutil.rmtree(RAW_DIR)
    STAGING_DIR.rename(RAW_DIR)
    print(f"done. {RAW_DIR} now holds the reduced dataset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
