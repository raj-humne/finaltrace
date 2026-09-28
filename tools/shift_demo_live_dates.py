"""One-off maintenance: shift every timestamp in data/demo_live's baseline
CSVs (both the live copy and the untouched _original backup) forward so the
live-demo dataset reads as current instead of frozen at its original
generation date (2010-01 through 2010-03).

Run whenever the demo has drifted far enough into the past to look stale:

    python tools/shift_demo_live_dates.py

Safe to re-run: it always shifts relative to _original's own max timestamp,
so running it twice in a row is a no-op (delta collapses to ~0). It also
resets the live copy back to _original before shifting, discarding any
previously-injected demo events - equivalent to POST /live-demo/reset plus
the shift, since a stale injected event wouldn't make sense at a new anchor
anyway.

api.live_demo.DEMO_BASE_ANCHOR reads _original's max timestamp at import
time and adds a fixed gap (see _ANCHOR_GAP there), so it re-derives itself
automatically after this script runs - no code change needed alongside it.
"""
from __future__ import annotations

import csv
import datetime as dt
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_RAW_DIR = REPO_ROOT / "data" / "demo_live"
BACKUP_DIR = DEMO_RAW_DIR / "_original"
DEMO_TS = "%m/%d/%Y %H:%M:%S"
SOURCES = ("logon", "device", "file", "http", "email")


def _max_timestamp(directory: Path) -> dt.datetime | None:
    latest = None
    for name in SOURCES:
        path = directory / f"{name}.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    ts = dt.datetime.strptime(row["date"], DEMO_TS)
                except (KeyError, ValueError):
                    continue
                if latest is None or ts > latest:
                    latest = ts
    return latest


def _shift_file(path: Path, delta: dt.timedelta) -> None:
    if not path.exists():
        return
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)
    for row in rows:
        try:
            ts = dt.datetime.strptime(row["date"], DEMO_TS)
        except (KeyError, ValueError):
            continue
        row["date"] = (ts + delta).strftime(DEMO_TS)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    old_max = _max_timestamp(BACKUP_DIR)
    if old_max is None:
        raise SystemExit(f"no timestamped rows found under {BACKUP_DIR}")

    now = dt.datetime.now().replace(microsecond=0)
    # Preserve the original dataset's own gap between its last baseline event
    # and DEMO_BASE_ANCHOR (2010-03-08 21:47 minus 2010-03-05 19:14) so the
    # shifted anchor lands the same relative distance past the new max.
    target_anchor = now
    old_anchor = dt.datetime(2010, 3, 8, 21, 47, 0)
    gap = old_anchor - old_max
    target_max = target_anchor - gap
    delta = target_max - old_max

    print(f"_original max timestamp: {old_max}")
    print(f"shifting by: {delta}")
    print(f"new max timestamp: {old_max + delta}  (anchor will be ~{target_anchor})")

    for name in SOURCES:
        _shift_file(BACKUP_DIR / f"{name}.csv", delta)
        shutil.copyfile(BACKUP_DIR / f"{name}.csv", DEMO_RAW_DIR / f"{name}.csv")

    print("done - _original and the live copy are both shifted and in sync.")


if __name__ == "__main__":
    main()
