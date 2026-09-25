"""Generate a synthetic dataset in the CMU CERT r4.2 schema.

Why this exists: the real CERT corpus is a multi-gigabyte download. This emits
the *same column layout*, so the engine can be built and tested today and real
CERT files drop straight in with no code change (they share the `cert_r42`
adapter). It also gives us ground-truth labels for the evaluation harness.

It is a stand-in for the real corpus, not a replacement. Numbers measured
against it are a smoke test of the pipeline, never a published result.

Usage:
    python -m tools.generate_synthetic --users 120 --days 150 --out data/raw
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

ROLES = [
    ("Engineer", "Research", 0.30),
    ("Salesman", "Sales", 0.22),
    ("Analyst", "Finance", 0.16),
    ("Manager", "Operations", 0.12),
    ("ITAdmin", "IT", 0.10),
    ("Technician", "Operations", 0.10),
]

NEUTRAL_DOMAINS = [
    "news.example.com", "wiki.example.org", "intranet.dtaa.com", "weather.example.com",
    "docs.example.net", "forum.example.org", "sports.example.com", "recipes.example.net",
]
JOB_DOMAINS = ["indeed.com", "monster.com", "careerbuilder.com", "dice.com", "glassdoor.com"]
CLOUD_DOMAINS = ["dropbox.com", "mega.nz", "wetransfer.com", "sendspace.com"]
LEAK_DOMAINS = ["wikileaks.org", "pastebin.com", "cryptome.org"]
HACK_DOMAINS = ["keylogger.org", "actualkeylogger.com", "refog.com", "hackforums.net"]

EXTS_COMMON = ["doc", "pdf", "txt", "jpg"]
EXTS_SENSITIVE = ["xls", "xlsx", "doc", "docx", "pdf", "zip", "csv"]


def fmt_ts(dt: datetime) -> str:
    """CERT uses MM/DD/YYYY HH:MM:SS."""
    return dt.strftime("%m/%d/%Y %H:%M:%S")


class Recorder:
    """Collects rows per source and writes CERT-shaped CSVs."""

    def __init__(self) -> None:
        self.logon: list[dict] = []
        self.device: list[dict] = []
        self.file: list[dict] = []
        self.http: list[dict] = []
        self.email: list[dict] = []
        self._n = 0

    def _rid(self, prefix: str) -> str:
        self._n += 1
        return "{%s-%07d}" % (prefix, self._n)

    def add_logon(self, dt, user, pc, activity):
        self.logon.append({"id": self._rid("L"), "date": fmt_ts(dt), "user": user,
                           "pc": pc, "activity": activity})

    def add_device(self, dt, user, pc, activity):
        self.device.append({"id": self._rid("D"), "date": fmt_ts(dt), "user": user,
                            "pc": pc, "activity": activity})

    def add_file(self, dt, user, pc, filename, to_removable=False):
        self.file.append({"id": self._rid("F"), "date": fmt_ts(dt), "user": user,
                          "pc": pc, "filename": filename,
                          "to_removable_media": str(bool(to_removable)),
                          "content": ""})

    def add_http(self, dt, user, pc, url):
        self.http.append({"id": self._rid("H"), "date": fmt_ts(dt), "user": user,
                          "pc": pc, "url": url, "content": ""})

    def add_email(self, dt, user, pc, to, cc, bcc, frm, size, attachments):
        self.email.append({"id": self._rid("E"), "date": fmt_ts(dt), "user": user,
                           "pc": pc, "to": to, "cc": cc, "bcc": bcc, "from": frm,
                           "size": size, "attachments": attachments, "content": ""})

    def write(self, out: Path) -> dict[str, int]:
        specs = {
            "logon.csv": (self.logon, ["id", "date", "user", "pc", "activity"]),
            "device.csv": (self.device, ["id", "date", "user", "pc", "activity"]),
            "file.csv": (self.file, ["id", "date", "user", "pc", "filename",
                                     "to_removable_media", "content"]),
            "http.csv": (self.http, ["id", "date", "user", "pc", "url", "content"]),
            "email.csv": (self.email, ["id", "date", "user", "pc", "to", "cc", "bcc",
                                       "from", "size", "attachments", "content"]),
        }
        counts = {}
        for name, (rows, cols) in specs.items():
            rows.sort(key=lambda r: datetime.strptime(r["date"], "%m/%d/%Y %H:%M:%S"))
            with (out / name).open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)
            counts[name] = len(rows)
        return counts


class User:
    def __init__(self, idx: int, rng: random.Random):
        self.user_id = "%s%s%04d" % (
            chr(65 + idx % 26), chr(65 + (idx // 26) % 26), idx)
        self.name = f"User {self.user_id}"
        self.email = f"{self.user_id}@dtaa.com"
        role, dept, _ = rng.choices(ROLES, weights=[r[2] for r in ROLES])[0]
        self.role, self.department = role, dept
        self.pc = f"PC-{1000 + idx}"
        # Each user has their own working rhythm. This is what makes a learned
        # off-hours window meaningful rather than decorative.
        if role == "ITAdmin" and rng.random() < 0.35:
            self.start_min = rng.randint(13 * 60, 15 * 60)   # a genuine late shift
        else:
            self.start_min = rng.randint(7 * 60 + 30, 9 * 60 + 30)
        self.day_len = rng.randint(8 * 60, 10 * 60)
        self.file_rate = rng.uniform(4, 26)
        self.http_rate = rng.uniform(8, 45)
        self.email_rate = rng.uniform(1, 7)
        self.usb_user = rng.random() < 0.18          # a minority legitimately use USB
        self.usb_rate = rng.uniform(0.05, 0.4) if self.usb_user else 0.0
        self.departure: date | None = None
        self.scenario = 0
        self.malicious_days: set[date] = set()


def business_days(start: date, days: int) -> list[date]:
    out, d = [], start
    while len(out) < days:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def jitter(base: datetime, minutes: int, rng: random.Random) -> datetime:
    return base + timedelta(minutes=rng.randint(0, max(1, minutes)))


def emit_benign_day(rec: Recorder, u: User, day: date, rng: random.Random) -> None:
    if rng.random() < 0.04:            # occasional absence
        return
    start = datetime.combine(day, datetime.min.time()) + timedelta(
        minutes=u.start_min + rng.randint(-25, 25))
    end = start + timedelta(minutes=u.day_len + rng.randint(-40, 40))
    rec.add_logon(start, u.user_id, u.pc, "Logon")
    rec.add_logon(end, u.user_id, u.pc, "Logoff")

    span = max(1, int((end - start).total_seconds() // 60))

    for _ in range(max(0, int(rng.gauss(u.file_rate, u.file_rate * 0.3)))):
        ext = rng.choice(EXTS_COMMON + EXTS_SENSITIVE[:3])
        rec.add_file(jitter(start, span, rng), u.user_id, u.pc,
                     f"{rng.randrange(16**8):08X}.{ext}")

    for _ in range(max(0, int(rng.gauss(u.http_rate, u.http_rate * 0.3)))):
        dom = rng.choice(NEUTRAL_DOMAINS)
        rec.add_http(jitter(start, span, rng), u.user_id, u.pc,
                     f"http://{dom}/page{rng.randint(1, 400)}")

    for _ in range(max(0, int(rng.gauss(u.email_rate, 1.5)))):
        n_to = rng.randint(1, 4)
        to = ";".join(f"U{rng.randint(1000, 9999)}@dtaa.com" for _ in range(n_to))
        atts = rng.choice([0, 0, 0, 1])
        rec.add_email(jitter(start, span, rng), u.user_id, u.pc, to, "", "",
                      u.email, rng.randint(20_000, 400_000), atts)

    if u.usb_user and rng.random() < u.usb_rate:
        c = jitter(start, span // 2, rng)
        rec.add_device(c, u.user_id, u.pc, "Connect")
        rec.add_device(c + timedelta(minutes=rng.randint(10, 90)), u.user_id, u.pc,
                       "Disconnect")


# --------------------------------------------------------------------------
# Scenarios. These mirror the three CERT r4.2 insider patterns.
# --------------------------------------------------------------------------

def scenario_1(rec: Recorder, u: User, days: list[date], rng: random.Random) -> None:
    """Ramps over weeks, then exfiltrates to a leak site and departs.

    Deliberately slow: no single early day should clear the alert threshold.
    This is the case campaign linking exists to catch.
    """
    end_idx = len(days) - rng.randint(3, 8)
    u.departure = days[end_idx]
    ramp = days[max(0, end_idx - 25):end_idx + 1]

    for i, day in enumerate(ramp):
        frac = i / max(1, len(ramp) - 1)
        base = datetime.combine(day, datetime.min.time())

        if rng.random() < 0.25 + 0.45 * frac:              # job search, growing
            t = base + timedelta(minutes=u.start_min + rng.randint(30, 400))
            for _ in range(rng.randint(2, 9)):
                rec.add_http(jitter(t, 90, rng), u.user_id, u.pc,
                             f"http://{rng.choice(JOB_DOMAINS)}/search?q=engineer")
            u.malicious_days.add(day)

        if frac > 0.45 and rng.random() < 0.55:            # off-hours work appears
            t = base + timedelta(minutes=u.start_min + u.day_len + rng.randint(120, 260))
            rec.add_logon(t, u.user_id, u.pc, "Logon")
            for _ in range(rng.randint(8, 22)):
                rec.add_file(jitter(t, 100, rng), u.user_id, u.pc,
                             f"{rng.randrange(16**8):08X}.{rng.choice(EXTS_SENSITIVE)}")
            rec.add_logon(t + timedelta(minutes=rng.randint(70, 140)), u.user_id,
                          u.pc, "Logoff")
            u.malicious_days.add(day)

    # The terminal act.
    final = days[end_idx]
    t = datetime.combine(final, datetime.min.time()) + timedelta(
        minutes=u.start_min + u.day_len + rng.randint(150, 220))
    rec.add_logon(t, u.user_id, u.pc, "Logon")
    rec.add_device(t + timedelta(minutes=12), u.user_id, u.pc, "Connect")
    for k in range(rng.randint(30, 60)):
        rec.add_file(t + timedelta(minutes=17 + k // 4), u.user_id, u.pc,
                     f"{rng.randrange(16**8):08X}.{rng.choice(EXTS_SENSITIVE)}",
                     to_removable=True)
    for _ in range(rng.randint(2, 5)):
        rec.add_http(t + timedelta(minutes=rng.randint(44, 60)), u.user_id, u.pc,
                     f"http://{rng.choice(LEAK_DOMAINS)}/upload")
    rec.add_device(t + timedelta(minutes=62), u.user_id, u.pc, "Disconnect")
    rec.add_logon(t + timedelta(minutes=70), u.user_id, u.pc, "Logoff")
    u.malicious_days.add(final)


def scenario_2(rec: Recorder, u: User, days: list[date], rng: random.Random) -> None:
    """Job-hunts, then steals data to a thumb drive shortly before leaving."""
    end_idx = len(days) - rng.randint(3, 10)
    u.departure = days[end_idx]
    window = days[max(0, end_idx - 18):end_idx + 1]

    for day in window:
        if rng.random() < 0.6:
            t = datetime.combine(day, datetime.min.time()) + timedelta(
                minutes=u.start_min + rng.randint(60, 420))
            for _ in range(rng.randint(3, 11)):
                rec.add_http(jitter(t, 120, rng), u.user_id, u.pc,
                             f"http://{rng.choice(JOB_DOMAINS)}/jobs/{rng.randint(1, 900)}")
            u.malicious_days.add(day)

    for day in window[-rng.randint(2, 4):]:
        t = datetime.combine(day, datetime.min.time()) + timedelta(
            minutes=u.start_min + u.day_len - rng.randint(20, 90))
        rec.add_device(t, u.user_id, u.pc, "Connect")
        for k in range(rng.randint(20, 45)):
            rec.add_file(t + timedelta(minutes=3 + k // 5), u.user_id, u.pc,
                         f"{rng.randrange(16**8):08X}.{rng.choice(EXTS_SENSITIVE)}",
                         to_removable=True)
        rec.add_device(t + timedelta(minutes=rng.randint(25, 55)), u.user_id, u.pc,
                       "Disconnect")
        u.malicious_days.add(day)


def scenario_3(rec: Recorder, u: User, days: list[date], rng: random.Random,
               all_pcs: list[str]) -> None:
    """Disgruntled admin: keylogger to USB, used on another machine, mass email."""
    idx = rng.randint(len(days) // 2, len(days) - 6)
    window = days[idx:idx + 4]
    foreign = rng.choice([p for p in all_pcs if p != u.pc])

    d0 = window[0]
    t = datetime.combine(d0, datetime.min.time()) + timedelta(
        minutes=u.start_min + rng.randint(120, 380))
    for _ in range(rng.randint(3, 8)):
        rec.add_http(jitter(t, 90, rng), u.user_id, u.pc,
                     f"http://{rng.choice(HACK_DOMAINS)}/download/keylogger")
    rec.add_device(t + timedelta(minutes=40), u.user_id, u.pc, "Connect")
    rec.add_file(t + timedelta(minutes=45), u.user_id, u.pc, "KEYLOG01.exe",
                 to_removable=True)
    rec.add_device(t + timedelta(minutes=52), u.user_id, u.pc, "Disconnect")
    u.malicious_days.add(d0)

    d1 = window[min(1, len(window) - 1)]
    t2 = datetime.combine(d1, datetime.min.time()) + timedelta(
        minutes=u.start_min + u.day_len + rng.randint(90, 200))
    rec.add_logon(t2, u.user_id, foreign, "Logon")
    rec.add_device(t2 + timedelta(minutes=6), u.user_id, foreign, "Connect")
    for k in range(rng.randint(10, 25)):
        rec.add_file(t2 + timedelta(minutes=10 + k // 3), u.user_id, foreign,
                     f"{rng.randrange(16**8):08X}.{rng.choice(EXTS_SENSITIVE)}")
    rec.add_device(t2 + timedelta(minutes=34), u.user_id, foreign, "Disconnect")
    rec.add_logon(t2 + timedelta(minutes=40), u.user_id, foreign, "Logoff")
    u.malicious_days.add(d1)

    d2 = window[-1]
    t3 = datetime.combine(d2, datetime.min.time()) + timedelta(
        minutes=u.start_min + rng.randint(30, 200))
    recips = ";".join(f"U{rng.randint(1000, 9999)}@dtaa.com" for _ in range(rng.randint(90, 260)))
    rec.add_email(t3, u.user_id, u.pc, recips, "", "", u.email, 90_000, 0)
    rec.add_email(t3 + timedelta(minutes=5), u.user_id, u.pc,
                  f"{u.user_id.lower()}@gmail.com", "", "", u.email, 4_500_000, 3)
    u.malicious_days.add(d2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--users", type=int, default=120)
    ap.add_argument("--days", type=int, default=150)
    ap.add_argument("--insiders", type=int, default=9)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("data/raw"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = args.out
    (out / "LDAP").mkdir(parents=True, exist_ok=True)

    days = business_days(date(2010, 1, 4), args.days)
    users = [User(i, rng) for i in range(args.users)]
    all_pcs = [u.pc for u in users]

    picks = rng.sample(users, min(args.insiders, len(users)))
    for i, u in enumerate(picks):
        u.scenario = (i % 3) + 1

    rec = Recorder()
    for u in users:
        cutoff = len(days)
        for day in days[:cutoff]:
            emit_benign_day(rec, u, day, rng)

    for u in picks:
        if u.scenario == 1:
            scenario_1(rec, u, days, rng)
        elif u.scenario == 2:
            scenario_2(rec, u, days, rng)
        else:
            scenario_3(rec, u, days, rng, all_pcs)

    # Departures truncate activity, which is itself a strong contextual signal.
    for u in users:
        if u.departure:
            rec.logon = [r for r in rec.logon
                         if not (r["user"] == u.user_id and
                                 datetime.strptime(r["date"], "%m/%d/%Y %H:%M:%S").date()
                                 > u.departure)]

    counts = rec.write(out)

    # LDAP monthly snapshots. These continue past the activity window, because a
    # departure is only observable as absence from a *later* snapshot - if the
    # directory stops when the logs stop, nobody ever appears to have left.
    months = sorted({(d.year, d.month) for d in days})
    y_last, m_last = months[-1]
    for _ in range(3):
        m_last += 1
        if m_last > 12:
            m_last, y_last = 1, y_last + 1
        months.append((y_last, m_last))
    for y, m in months:
        path = out / "LDAP" / f"{y}-{m:02d}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["employee_name", "user_id", "email", "role", "business_unit",
                        "functional_unit", "department", "team", "supervisor"])
            for u in users:
                if u.departure and date(y, m, 1) > u.departure:
                    continue
                w.writerow([u.name, u.user_id, u.email, u.role, "BU1", u.department,
                            u.department, "Team-1", ""])

    answers = {
        "insiders": [
            {"user_id": u.user_id, "scenario": u.scenario,
             "departure": u.departure.isoformat() if u.departure else None,
             "malicious_days": sorted(d.isoformat() for d in u.malicious_days)}
            for u in sorted(picks, key=lambda x: x.user_id)
        ],
        "generator": {"seed": args.seed, "users": args.users, "days": args.days},
    }
    (out / "answers.json").write_text(json.dumps(answers, indent=2), encoding="utf-8")

    total_mal_days = sum(len(u.malicious_days) for u in picks)
    print(f"Wrote synthetic CERT-schema dataset to {out}")
    for k, v in counts.items():
        print(f"  {k:<12} {v:>9,} rows")
    print(f"  LDAP/        {len(months):>9} monthly snapshots")
    print(f"\n  {len(users)} users, {len(days)} business days")
    print(f"  {len(picks)} insiders, {total_mal_days} malicious user-days "
          f"(base rate {total_mal_days / (len(users) * len(days)):.4%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
