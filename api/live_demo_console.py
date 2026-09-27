"""A self-contained, zero-install control panel for the two-laptop live demo
(docs/10-LIVE-DEMO.md). Served as one static HTML page with inline JS -
whoever's playing "the insider" opens a URL in any browser, on any device,
logs in on the page itself, and clicks buttons. No Python, no pip install,
no terminal on their machine at all - tools/live_demo_inject.py remains the
scriptable alternative for a rehearsed, timed run; this is the walk-up-and-
click alternative for someone who isn't comfortable with a terminal.

Every button calls the exact same real endpoints
(POST /auth/login, POST /live-demo/inject, POST /live-demo/reset) that the
CLI script and any other client use - this page contains no detection logic
of its own, only fetch() calls with credentials: 'include' so the session
cookie set by /auth/login is sent on every follow-up request.
"""
from __future__ import annotations

CONSOLE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SentinelTrace — Live Demo Console</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #05080a; --surface: #232d32; --raised: #2f3c42;
    --ink: #ffffff; --ink-2: #c7d2d6; --muted: #8b9aa0;
    --hairline: rgba(255,255,255,0.35);
    --accent: #ff9838; --good: #2ed996; --warn: #ffc233; --bad: #ff5c5b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; background: var(--bg); color: var(--ink);
    font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
    display: flex; align-items: flex-start; justify-content: center; padding: 32px 16px;
  }
  main { width: 100%; max-width: 560px; }
  h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: var(--ink-2); font-size: 14px; margin: 0 0 28px; }
  .card {
    background: var(--surface); border: 1px solid var(--hairline);
    border-radius: 10px; padding: 20px; margin-bottom: 16px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.45);
  }
  .card h2 { font-size: 14px; text-transform: none; color: var(--ink-2); margin: 0 0 14px; font-weight: 500; }
  label { display: block; font-size: 13px; color: var(--ink-2); margin: 10px 0 4px; }
  input {
    width: 100%; background: var(--raised); border: 1px solid var(--hairline);
    border-radius: 6px; padding: 10px 12px; color: var(--ink); font-size: 15px;
  }
  input:focus { outline: none; border-color: var(--accent); }
  button {
    cursor: pointer; border: none; border-radius: 6px; padding: 12px 16px;
    font-size: 15px; font-weight: 500; font-family: inherit;
  }
  button:disabled { opacity: 0.5; cursor: default; }
  .btn-primary { background: var(--accent); color: #1a0f04; width: 100%; margin-top: 14px; }
  .btn-secondary {
    background: var(--raised); color: var(--ink); border: 1px solid var(--hairline);
    width: 100%; text-align: left; margin-bottom: 8px;
  }
  .btn-secondary:hover:not(:disabled) { border-color: var(--accent); }
  .btn-ghost { background: transparent; color: var(--muted); border: 1px solid var(--hairline); width: 100%; }
  #login-panel.hidden, .steps.hidden-panel { display: none; }
  .status { font-size: 13px; color: var(--ink-2); margin-top: 10px; min-height: 18px; }
  .status.err { color: var(--bad); }
  .result {
    margin-top: 14px; padding: 14px; border-radius: 8px; border: 1px solid var(--hairline);
    background: var(--raised); font-size: 14px; display: none;
  }
  .result.visible { display: block; }
  .lane { display: inline-block; font-weight: 600; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
  .lane-AUTO_FLAG { background: rgba(227,73,72,0.18); color: var(--bad); }
  .lane-ANALYST_REVIEW { background: rgba(237,161,0,0.18); color: var(--warn); }
  .lane-MONITOR, .lane-SUPPRESSED { background: rgba(111,125,130,0.18); color: var(--ink-2); }
  .metric { color: var(--ink-2); margin-top: 4px; }
  .metric b { color: var(--ink); font-weight: 600; }
  .whoami { font-size: 13px; color: var(--ink-2); }
  .whoami b { color: var(--good); }
</style>
</head>
<body>
<main>
  <h1>SentinelTrace — Live Demo Console</h1>
  <p class="sub">Act like the insider. Every button below is a real event, really scored by the real detection engine.</p>

  <div class="card" id="login-panel">
    <h2>1. Sign in</h2>
    <label for="u">Username</label>
    <input id="u" autocomplete="username" placeholder="demo2">
    <label for="p">Password</label>
    <input id="p" type="password" autocomplete="current-password">
    <button class="btn-primary" id="login-btn">Sign in</button>
    <p class="status" id="login-status"></p>
  </div>

  <div class="steps hidden-panel" id="steps-panel">
    <div class="card">
      <h2><span class="whoami">Signed in as <b id="who"></b></span></h2>
      <button class="btn-secondary" data-action="offhours_logon">1 · Off-hours logon</button>
      <button class="btn-secondary" data-action="usb_connect_foreign">2 · Plug in USB (on someone else's PC)</button>
      <button class="btn-secondary" data-action="file_copy_burst">3 · Copy 45 files to the USB drive</button>
      <button class="btn-secondary" data-action="usb_disconnect">4 · Unplug the USB drive</button>
      <button class="btn-secondary" data-action="leak_upload">5 · Upload files to a leak site</button>
    </div>
    <div class="card">
      <button class="btn-primary" id="scenario-btn">Run the full attack, start to finish</button>
      <button class="btn-ghost" id="reset-btn" style="margin-top:8px;">Reset demo (clear everything injected)</button>
      <p class="status" id="action-status"></p>
      <div class="result" id="result"></div>
    </div>
  </div>
</main>

<script>
const API = "/api/v1";

function setStatus(el, msg, isErr) {
  el.textContent = msg;
  el.className = "status" + (isErr ? " err" : "");
}

async function api(path, body) {
  const r = await fetch(API + path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((data && (data.detail || data.title)) || ("HTTP " + r.status));
  return data;
}

document.getElementById("login-btn").addEventListener("click", async () => {
  const btn = document.getElementById("login-btn");
  const status = document.getElementById("login-status");
  const username = document.getElementById("u").value.trim();
  const password = document.getElementById("p").value;
  if (!username || !password) { setStatus(status, "enter a username and password", true); return; }
  btn.disabled = true;
  setStatus(status, "signing in…", false);
  try {
    const data = await api("/auth/login", { username, password });
    document.getElementById("who").textContent =
      data.account.display_name + " (" + data.account.role + ")";
    document.getElementById("login-panel").classList.add("hidden");
    document.getElementById("steps-panel").classList.remove("hidden-panel");
  } catch (e) {
    setStatus(status, "sign-in failed: " + e.message, true);
  } finally {
    btn.disabled = false;
  }
});

function renderResult(data) {
  const box = document.getElementById("result");
  box.classList.add("visible");
  if (!data.incidents_today || data.incidents_today.length === 0) {
    box.innerHTML = "<div class='metric'>Rescored — no correlated incident yet. Keep going.</div>";
    return;
  }
  box.innerHTML = data.incidents_today.map(inc => `
    <div style="margin-bottom:8px;">
      <span class="lane lane-${inc.triage_lane}">${inc.triage_lane.replace("_"," ")}</span>
      <div class="metric">Risk <b>${inc.risk.toFixed(1)}</b> · Confidence <b>${inc.confidence.toFixed(2)}</b>
        · ${inc.signal_count} signals across stages [${inc.stages.join(", ")}]</div>
      <div class="metric" style="color:var(--muted);font-size:12px;">${inc.incident_id}</div>
    </div>`).join("");
}

async function runAction(payload, btn) {
  const status = document.getElementById("action-status");
  const allButtons = document.querySelectorAll("#steps-panel button");
  allButtons.forEach(b => b.disabled = true);
  setStatus(status, "sending to the engine, rescoring…", false);
  try {
    const data = await api("/live-demo/inject", payload);
    setStatus(status, "done.", false);
    renderResult(data);
  } catch (e) {
    setStatus(status, "failed: " + e.message, true);
  } finally {
    allButtons.forEach(b => b.disabled = false);
  }
}

document.querySelectorAll("button[data-action]").forEach(btn => {
  btn.addEventListener("click", () => runAction({ actions: [btn.dataset.action] }, btn));
});
document.getElementById("scenario-btn").addEventListener("click", (e) =>
  runAction({ scenario: true }, e.target));
document.getElementById("reset-btn").addEventListener("click", async () => {
  const status = document.getElementById("action-status");
  setStatus(status, "resetting…", false);
  try {
    await fetch(API + "/live-demo/reset", { method: "POST", credentials: "include" });
    document.getElementById("result").classList.remove("visible");
    setStatus(status, "reset. clean baseline restored.", false);
  } catch (e) {
    setStatus(status, "reset failed: " + e.message, true);
  }
});
</script>
</body>
</html>
"""
