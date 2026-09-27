# 10 — Two-Laptop Live Demo

A live, real demonstration of detection actually happening: Laptop A plays
"the insider's machine" and sends a real suspicious sequence of events over
the LAN; Laptop B runs the real API and dashboard (what's shown to judges),
scores it with the real engine, and the incident appears on screen within
seconds — with a real narrative, real risk/confidence, real correlation
graph.

This is not a separate demo mode or a scripted animation. `POST /live-demo/inject`
calls `engine.run.Pipeline` — the exact same detection code every other
incident in the system goes through. The only thing special about it is the
dataset: a small, dedicated, clearly-synthetic corpus (`data/demo_live/`,
18 users, 45 days, zero injected insider scenarios) built specifically so one
employee (`AA0000`, Engineer/Research) has a real, engine-computed mature
baseline to be anomalous against. See `api/live_demo.py`'s module docstring
for the full mechanism.

**Do not confuse this with a reported evaluation result.** `engine/eval/harness.py`'s
real-CERT guard has nothing to do with this dataset and never will — this is
a demo mechanism, not a detection-quality claim. `data/demo_live/` will never
produce a number that belongs in `docs/07-EVALUATION.md`.

---

## 1. Laptop B — the machine judges watch

### 1.1 Start the API, reachable on the LAN

By default `uvicorn` binds to `127.0.0.1` only — invisible to Laptop A. Bind
to all interfaces instead:

```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 1.2 Find this laptop's LAN IP

```bash
ipconfig          # Windows — look for "IPv4 Address" under your Wi-Fi adapter
# or
ifconfig          # macOS/Linux
```

Both laptops must be on the **same network** (same Wi-Fi/hotspot). A venue's
guest Wi-Fi often isolates clients from each other — if Laptop A can't reach
Laptop B, that's the first thing to check; a personal mobile hotspot is a
reliable fallback.

### 1.3 Allow the port through the firewall

Windows will prompt for this automatically on first inbound connection —
allow it for the current network profile. If it doesn't prompt:

```powershell
New-NetFirewallRule -DisplayName "SentinelTrace demo" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### 1.4 Create the demo account (once)

No default credentials exist anywhere in this repo, by design:

```bash
python -m api.cli create-user --username demo --display-name "Demo Operator" --role detection_engineer
```

### 1.5 Start the dashboard

```bash
cd web && npm run dev
```

Open it on Laptop B's screen — this is what's projected. Log in with the
`demo` account.

### 1.6 Sanity check, before anyone is watching

From Laptop B itself:

```bash
curl http://localhost:8000/api/v1/health
```

Then from Laptop A (or a phone on the same network), confirm the LAN path
actually works — see 2.1 below — **before** the live demo starts, not during
it.

---

## 2. Laptop A — "the insider's machine"

### 2.1 Install the one dependency

```bash
pip install requests
```

No engine code, no database, no local copy of the repo's Python packages
needed — `tools/live_demo_inject.py` only makes HTTP calls. Copy just that
one file to Laptop A if it doesn't have the repo checked out.

### 2.2 List the available actions (confirms connectivity + login)

```bash
python -m tools.live_demo_inject --host <laptop-B-lan-ip> --username demo --list-actions
```

Enter the account's password when prompted (never pass it as an argument —
it would land in shell history and any screen-share).

### 2.3 The full staged scenario, in one call

```bash
python -m tools.live_demo_inject --host <laptop-B-lan-ip> --username demo --scenario
```

Sends, in order, ~5–6 seconds apart in wall-clock terms but staged with
realistic in-data timing offsets: an off-hours logon → a USB connect on a
workstation that isn't the employee's own → a 45-file copy burst onto that
removable media → disconnect → three uploads to a leak-platform domain. The
real engine rescores the whole demo dataset (~5s) and returns the result —
on a clean run, this reliably lands as **AUTO_FLAG, risk ≈ 73–78, confidence
≈ 0.87**, all four kill-chain stages present.

### 2.4 Or stage it step by step, for a slower narrated demo

```bash
python -m tools.live_demo_inject --host <ip> --username demo \
  --actions offhours_logon --step-delay 3
python -m tools.live_demo_inject --host <ip> --username demo \
  --actions usb_connect_foreign --step-delay 3
python -m tools.live_demo_inject --host <ip> --username demo \
  --actions file_copy_burst --step-delay 3
python -m tools.live_demo_inject --host <ip> --username demo \
  --actions usb_disconnect leak_upload
```

Each call rescores and reports the incident's state *so far* — useful for
narrating "watch the risk climb as each piece of evidence arrives" rather
than dropping the whole scenario at once. `risk` and `triage_lane` visibly
change between calls as correlation strengthens.

### 2.5 Reset between rehearsals or between back-to-back demos

```bash
python -m tools.live_demo_inject --host <ip> --username demo --reset
```

Wipes every injected event back to the clean baseline (both the CSVs and the
persisted incident) — the next injection starts fresh, as if `AA0000` had
never done anything unusual.

---

## 3. What to say while it runs

Matches `docs/09-DELIVERY-PLAN.md`'s demo script in spirit — this is the
live version of that 2:30–3:30 "validation" beat:

> "Everything so far has been precomputed CERT data from 2010. Here's the
> same engine, live, right now. My colleague on that laptop is about to act
> like an employee: log on after hours, plug in a USB drive on someone
> else's desk, copy forty-five files, and upload them to a paste site.
> Watch the screen — no refresh, no re-run, this is the same pipeline
> scoring in real time over the network."

Then let Laptop A's `--scenario` call run. The incident appears via the
dashboard's normal query invalidation within the ~5-second rescore window —
open it and read the real generated narrative aloud.

---

## 4. If something goes wrong

| Symptom | Likely cause |
|---|---|
| Laptop A's script hangs or times out on login | Firewall blocking port 8000, or the two laptops aren't on the same network — try a mobile hotspot |
| `401` on every call | Wrong password, or the session cookie didn't round-trip — confirm Laptop B's `SENTINEL_COOKIE_SECURE` isn't forcing HTTPS-only cookies over a plain-HTTP LAN connection |
| Incident never appears / low risk | Someone ran `--reset` recently and the baseline history itself is gone — check `data/demo_live/logon.csv`'s date range still ends `2010-03-05`; restore from `data/demo_live/_original/` if not |
| A second `--scenario` run right after the first shows nothing new | Expected and correct — `_next_anchor()` advances to a new day each call, so a second identical scenario produces a **second**, separate incident the next day, not a duplicate of the first |
| Script crashes on a Windows console | Should not happen — `tools/live_demo_inject.py` and `api/live_demo.py` are verified to contain zero non-ASCII characters, specifically because an earlier version crashed a plain `cp1252` console on an emoji status marker. If it happens again, that constraint was violated by a later edit |

---

## 5. Fallback if the network truly won't cooperate

Everything above also works with both processes on **one** laptop
(`--host 127.0.0.1`) — the mechanism is identical, only the LAN hop is
removed. If the venue's network is unworkable, fall back to a single-laptop
run and narrate "Laptop A" as a second terminal window instead of a second
physical device. The engine result is exactly the same either way.
