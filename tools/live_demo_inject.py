"""Laptop A's script for the two-laptop live demo.

Laptop B runs the real API + dashboard (what's shown to judges). This script
runs on Laptop A ("the insider's machine") and does nothing but make real,
authenticated HTTP calls to Laptop B's API over the LAN - no engine code, no
database, no local state. Every action it sends becomes a real event, really
scored by the real engine, and the resulting incident really appears on
Laptop B's screen within seconds.

Usage:
    python -m tools.live_demo_inject --host 192.168.1.42 --username demo \\
        --scenario

    python -m tools.live_demo_inject --host 192.168.1.42 --username demo \\
        --actions offhours_logon usb_connect_foreign file_copy_burst \\
                  usb_disconnect leak_upload

    python -m tools.live_demo_inject --host 192.168.1.42 --username demo --reset

Password is always prompted interactively (getpass) - never a CLI argument,
same reasoning as api/cli.py: it must not land in shell history or a process
list a second screen could see mid-demo.
"""
from __future__ import annotations

import argparse
import getpass
import sys
import time

try:
    import requests
except ImportError as exc:
    print("This script needs 'requests' (pip install requests) - it has no "
         "other dependency on this repo's engine or API code.", file=sys.stderr)
    raise SystemExit(1) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True, help="Laptop B's LAN IP, e.g. 192.168.1.42")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--username", required=True)
    parser.add_argument("--scenario", action="store_true",
                       help="run the full staged 5-step scenario in one call")
    parser.add_argument("--actions", nargs="+", default=None,
                       help="named steps to inject, one at a time or as a list "
                            "(see --list-actions)")
    parser.add_argument("--list-actions", action="store_true",
                       help="print the available action names and exit")
    parser.add_argument("--reset", action="store_true",
                       help="wipe all injected events back to the clean baseline")
    parser.add_argument("--step-delay", type=float, default=0.0,
                       help="seconds to sleep between each action in --actions "
                            "(dramatic pacing for a live audience; 0 = as fast as possible)")
    args = parser.parse_args(argv)

    base = f"http://{args.host}:{args.port}/api/v1"
    session = requests.Session()

    password = getpass.getpass(f"Password for {args.username}@{args.host}: ")
    print(f"connecting to {base} ...")
    r = session.post(f"{base}/auth/login", json={"username": args.username, "password": password},
                     timeout=10)
    if r.status_code != 200:
        print(f"login failed ({r.status_code}): {r.text}", file=sys.stderr)
        return 1
    print(f"logged in as {args.username} ({r.json().get('account', {}).get('role', '?')})")

    if args.list_actions:
        r = session.get(f"{base}/live-demo/actions", timeout=10)
        r.raise_for_status()
        print("available actions:", ", ".join(r.json()["actions"]))
        return 0

    if args.reset:
        r = session.post(f"{base}/live-demo/reset", timeout=30)
        if r.status_code not in (200, 204):
            print(f"reset failed ({r.status_code}): {r.text}", file=sys.stderr)
            return 1
        print("demo reset to clean baseline.")
        return 0

    if not args.scenario and not args.actions:
        print("nothing to do - pass --scenario, --actions, or --reset", file=sys.stderr)
        return 2

    if args.scenario:
        print("injecting the full staged scenario (off-hours logon -> USB on a "
             "foreign workstation -> 45-file copy burst -> disconnect -> leak-site "
             "upload) and rescoring with the real engine...")
        t0 = time.time()
        r = session.post(f"{base}/live-demo/inject", json={"scenario": True}, timeout=120)
        _report(r, time.time() - t0)
        return 0 if r.status_code == 200 else 1

    for action in args.actions:
        print(f"injecting: {action} ...")
        t0 = time.time()
        r = session.post(f"{base}/live-demo/inject", json={"actions": [action]}, timeout=120)
        _report(r, time.time() - t0)
        if r.status_code != 200:
            return 1
        if args.step_delay:
            time.sleep(args.step_delay)

    return 0


def _report(r, elapsed: float) -> None:
    if r.status_code != 200:
        print(f"  failed ({r.status_code}): {r.text}", file=sys.stderr)
        return
    data = r.json()
    print(f"  rescored in {elapsed:.1f}s. incidents today for {data['user_id']}:")
    if not data["incidents_today"]:
        print("    (none yet - not enough correlated signal to form an incident)")
    for inc in data["incidents_today"]:
        lane = inc["triage_lane"]
        # Plain ASCII only: a Windows console's default codepage (cp1252 or
        # similar) cannot encode most emoji or symbol characters, and this
        # script must never crash mid-demo over a print() call - it already
        # did exactly that once during testing (UnicodeEncodeError on
        # U+1F6A8), which is precisely the failure mode to avoid live.
        marker = "[AUTO-FLAG]" if lane == "AUTO_FLAG" else (
            "[REVIEW]" if lane == "ANALYST_REVIEW" else "-")
        print(f"    {marker} {inc['incident_id']}  risk={inc['risk']}  "
             f"confidence={inc['confidence']}  lane={lane}  "
             f"({inc['signal_count']} signals, stages {inc['stages']})")


if __name__ == "__main__":
    raise SystemExit(main())
