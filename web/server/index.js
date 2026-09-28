// Fixture API server standing in for Track B until it lands.
// Serves /api/v1/* with the exact shapes documented in docs/05-API-SPEC.md,
// backed by server/data.js, plus /api/v1/openapi.json so the frontend build
// can generate real response types instead of hand-writing them.
import express from "express";
import cookieParser from "cookie-parser";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  ALL_USERS,
  ALL_INCIDENTS,
  INCIDENTS_BY_ID,
  CAMPAIGNS,
  CAMPAIGNS_BY_ID,
  RULE_CATALOGUE,
  userListItem,
  userProfile,
  userRiskSeries,
  userTimeline,
  incidentListItem,
  incidentDetail,
  incidentGraph,
  ruleStats,
  detectionHealth,
  evalReport,
} from "./data.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 8787;

const app = express();
app.use(express.json());
app.use(cookieParser());

// ---- CORS for the Vite dev server ----
app.use((req, res, next) => {
  res.header("Access-Control-Allow-Origin", req.headers.origin || "http://localhost:5173");
  res.header("Access-Control-Allow-Credentials", "true");
  res.header("Access-Control-Allow-Headers", "Content-Type");
  res.header("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

function problem(res, status, title, detail) {
  res.status(status).type("application/problem+json").json({
    type: `https://sentineltrace.dev/errors/${title.toLowerCase().replace(/\s+/g, "-")}`,
    title,
    status,
    detail,
    instance: res.req.originalUrl,
    trace_id: Math.random().toString(36).slice(2, 12),
  });
}

// ---- Auth (fixture only — Track B replaces this with real Argon2id + sessions) ----
const DEMO_USERS = {
  "priya.s": { password: "analyst-demo", analyst_id: "priya.s", name: "Priya Sharma", role: "analyst" },
  "anjali.m": { password: "engineer-demo", analyst_id: "anjali.m", name: "Anjali Mehta", role: "detection_engineer" },
  "riya": { password: "123456", analyst_id: "riya", name: "Riya", role: "analyst" },
};
const SESSIONS = new Map();

function sessionFromReq(req) {
  const token = req.cookies?.st_session;
  return token ? SESSIONS.get(token) : null;
}

app.post("/api/v1/auth/login", (req, res) => {
  const { username, password } = req.body ?? {};
  const record = DEMO_USERS[username];
  if (!record || record.password !== password) {
    return problem(res, 401, "Invalid credentials", "Username or password is incorrect.");
  }
  const token = `sess_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
  const user = { analyst_id: record.analyst_id, name: record.name, role: record.role };
  SESSIONS.set(token, user);
  res.cookie("st_session", token, { httpOnly: true, sameSite: "strict", maxAge: 1000 * 60 * 60 * 8 });
  res.json({ user });
});

app.post("/api/v1/auth/logout", (req, res) => {
  const token = req.cookies?.st_session;
  if (token) SESSIONS.delete(token);
  res.clearCookie("st_session");
  res.status(204).end();
});

app.get("/api/v1/auth/me", (req, res) => {
  const user = sessionFromReq(req);
  if (!user) return problem(res, 401, "Not authenticated", "No active session.");
  res.json(user);
});

function requireAuth(req, res, next) {
  const user = sessionFromReq(req);
  if (!user) return problem(res, 401, "Not authenticated", "No active session.");
  req.user = user;
  next();
}

function requireEngineer(req, res, next) {
  if (req.user.role !== "detection_engineer") {
    return problem(res, 403, "Insufficient role", "Only a detection engineer may activate a suppression.");
  }
  next();
}

// ---- OpenAPI ----
app.get("/api/v1/openapi.json", (req, res) => {
  const spec = JSON.parse(readFileSync(join(__dirname, "..", "fixtures", "openapi.json"), "utf-8"));
  res.json(spec);
});

// ---- Health ----
app.get("/api/v1/health", requireAuth, (req, res) => {
  res.json({
    status: "ok",
    config_version: "sha256:9f2c1a7e4b3d5f608a1c2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a41",
    data: {
      ts_min: "2010-01-02T00:00:00Z",
      ts_max: "2011-05-31T23:59:00Z",
      users: 1000,
      events: 32770227,
      last_pipeline_run: "2026-09-24T08:12:00Z",
    },
    engine: { rules_loaded: RULE_CATALOGUE.length, cohort_models: 41, mode: "batch" },
  });
});

// ---- Users ----
app.get("/api/v1/users", requireAuth, (req, res) => {
  const { q, department, role, min_risk, departing_within, sort = "-current_risk", limit = 50 } = req.query;
  let items = [...ALL_USERS];
  if (q) items = items.filter((u) => u.name.toLowerCase().includes(String(q).toLowerCase()) || u.user_id.toLowerCase().includes(String(q).toLowerCase()));
  if (department) items = items.filter((u) => u.department === department);
  if (role) items = items.filter((u) => u.role === role);
  if (min_risk) items = items.filter((u) => u.current_risk >= Number(min_risk));
  if (departing_within) items = items.filter((u) => u.departure_date != null);
  const field = String(sort).replace(/^-/, "");
  const desc = String(sort).startsWith("-");
  items.sort((a, b) => (desc ? b[field] - a[field] : a[field] - b[field]));
  const lim = Math.min(Number(limit) || 50, 500);
  res.json({ items: items.slice(0, lim).map(userListItem), next_cursor: items.length > lim ? "eyJvIjo1MH0" : null, total: items.length });
});

app.get("/api/v1/users/:user_id", requireAuth, (req, res) => {
  const u = ALL_USERS.find((x) => x.user_id === req.params.user_id);
  if (!u) return problem(res, 404, "User not found", `No user with id ${req.params.user_id}`);
  res.json(userProfile(u));
});

app.get("/api/v1/users/:user_id/risk", requireAuth, (req, res) => {
  const u = ALL_USERS.find((x) => x.user_id === req.params.user_id);
  if (!u) return problem(res, 404, "User not found", `No user with id ${req.params.user_id}`);
  res.json(userRiskSeries(req.params.user_id, req.query.date_from, req.query.date_to));
});

app.get("/api/v1/users/:user_id/timeline", requireAuth, (req, res) => {
  const u = ALL_USERS.find((x) => x.user_id === req.params.user_id);
  if (!u) return problem(res, 404, "User not found", `No user with id ${req.params.user_id}`);
  const date = req.query.date || u.last_seen;
  res.json(userTimeline(req.params.user_id, date));
});

// ---- Incidents ----
app.get("/api/v1/incidents", requireAuth, (req, res) => {
  const { lane, status, min_risk, min_confidence, user_id, stage_max, campaign_id, sort = "-risk", limit = 50 } = req.query;
  let items = [...ALL_INCIDENTS];
  if (lane) items = items.filter((i) => i.triage_lane === lane);
  if (status) items = items.filter((i) => i.status === status);
  if (min_risk) items = items.filter((i) => i.risk >= Number(min_risk));
  if (min_confidence) items = items.filter((i) => i.confidence >= Number(min_confidence));
  if (user_id) items = items.filter((i) => i.user_id === user_id);
  if (stage_max) items = items.filter((i) => i.max_stage <= Number(stage_max));
  if (campaign_id) items = items.filter((i) => i.campaign_id === campaign_id);
  const field = String(sort).replace(/^-/, "");
  const desc = String(sort).startsWith("-");
  items.sort((a, b) => (desc ? b[field] - a[field] : a[field] - b[field]));

  const laneFacets = { AUTO_FLAG: 0, ANALYST_REVIEW: 0, MONITOR: 0, SUPPRESSED: 0 };
  const stageFacets = {};
  for (const i of ALL_INCIDENTS) {
    laneFacets[i.triage_lane] = (laneFacets[i.triage_lane] || 0) + 1;
    stageFacets[i.max_stage] = (stageFacets[i.max_stage] || 0) + 1;
  }

  const lim = Math.min(Number(limit) || 50, 500);
  res.json({
    items: items.slice(0, lim).map(incidentListItem),
    next_cursor: items.length > lim ? "eyJvIjo1MH0" : null,
    total: items.length,
    facets: { lane: laneFacets, max_stage: stageFacets },
  });
});

app.get("/api/v1/incidents/:id", requireAuth, (req, res) => {
  const inc = INCIDENTS_BY_ID[req.params.id];
  if (!inc) return problem(res, 404, "Incident not found", `No incident with id ${req.params.id}`);
  res.json(incidentDetail(inc));
});

app.get("/api/v1/incidents/:id/graph", requireAuth, (req, res) => {
  const inc = INCIDENTS_BY_ID[req.params.id];
  if (!inc) return problem(res, 404, "Incident not found", `No incident with id ${req.params.id}`);
  res.json(incidentGraph(inc));
});

app.get("/api/v1/incidents/:id/export", requireAuth, (req, res) => {
  const inc = INCIDENTS_BY_ID[req.params.id];
  if (!inc) return problem(res, 404, "Incident not found", `No incident with id ${req.params.id}`);
  res.json({
    incident: incidentDetail(inc),
    raw_events: incidentGraph(inc).nodes.map((n) => ({ event_id: n.id, ts: n.ts, source: n.source, action: n.action, pc_id: n.pc_id })),
    config_snapshot: { config_version: "sha256:9f2c1a7e4b3d5f608a1c2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a41" },
    watermark: { exported_by: req.user.analyst_id, exported_at: new Date().toISOString() },
  });
});

app.post("/api/v1/incidents/:id/review", requireAuth, (req, res) => {
  const inc = INCIDENTS_BY_ID[req.params.id];
  if (!inc) return problem(res, 404, "Incident not found", `No incident with id ${req.params.id}`);
  if (inc.status === "closed" && req.query.force !== "true") {
    return problem(res, 409, "Incident already closed", "Pass ?force=true with an elevated token to override.");
  }
  const { verdict, note, analyst_id, propose_suppression } = req.body ?? {};
  if (!verdict || !analyst_id) return problem(res, 400, "Malformed request", "verdict and analyst_id are required.");

  inc._review = { verdict, note, analyst_id, reviewed_at: new Date().toISOString() };
  inc.status = "closed";

  let suppression = null;
  if (verdict === "benign" && propose_suppression) {
    suppression = { ...propose_suppression, status: "proposed" };
  }

  res.status(201).json({
    review_id: Math.floor(Math.random() * 900000) + 1000,
    incident_id: inc.incident_id,
    verdict,
    reviewed_at: inc._review.reviewed_at,
    incident_status: inc.status,
    suppression,
    effects: {
      rule_stats_updated: inc._signals.map((s) => s.rule_id),
      user_risk_ewma_adjusted: false,
    },
  });
});

// requireEngineer stands ready for a future POST /suppressions/{id}/activate
void requireEngineer;

// ---- Campaigns ----
app.get("/api/v1/campaigns", requireAuth, (req, res) => {
  const { user_id, min_stage, limit = 50 } = req.query;
  let items = CAMPAIGNS.map((c) => ({
    campaign_id: c.campaign_id,
    user_id: c.user_id,
    user_name: INCIDENTS_BY_ID[c.stage_progression[0].incident_id]?.user_name ?? c.user_id,
    first_seen: c.first_seen,
    last_seen: c.last_seen,
    incident_count: c.incident_count,
    peak_risk: c.peak_risk,
    max_stage: c.max_stage,
  }));
  if (user_id) items = items.filter((c) => c.user_id === user_id);
  if (min_stage) items = items.filter((c) => c.max_stage >= Number(min_stage));
  res.json({ items: items.slice(0, Number(limit) || 50), total: items.length });
});

app.get("/api/v1/campaigns/:id", requireAuth, (req, res) => {
  const c = CAMPAIGNS_BY_ID[req.params.id];
  if (!c) return problem(res, 404, "Campaign not found", `No campaign with id ${req.params.id}`);
  res.json(c);
});

// ---- Rules ----
app.get("/api/v1/rules", requireAuth, (req, res) => {
  res.json({ config_version: "sha256:9f2c1a7e4b3d5f608a1c2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a41", items: RULE_CATALOGUE });
});

app.get("/api/v1/rules/:rule_id/stats", requireAuth, (req, res) => {
  const rule = RULE_CATALOGUE.find((r) => r.rule_id === req.params.rule_id);
  if (!rule) return problem(res, 404, "Rule not found", `No rule with id ${req.params.rule_id}`);
  res.json(ruleStats(req.params.rule_id, req.query.date_from, req.query.date_to));
});

// ---- Detection health / eval ----
app.get("/api/v1/detection/health", requireAuth, (req, res) => res.json(detectionHealth()));
app.get("/api/v1/eval/report", requireAuth, (req, res) => res.json(evalReport()));

// ---- Ad-hoc analyze ----
app.post("/api/v1/analyze", requireAuth, (req, res) => {
  const { user_id, date_from, date_to } = req.body ?? {};
  const u = ALL_USERS.find((x) => x.user_id === user_id);
  if (!u) return problem(res, 404, "User not found", `No user with id ${user_id}`);
  const series = userRiskSeries(user_id, date_from, date_to);
  const incidentIds = series.series.flatMap((s) => s.incident_ids);
  res.json({
    user_id,
    window: { from: date_from, to: date_to },
    computed_in_ms: 280 + Math.floor(Math.random() * 120),
    from_cache: !(req.body?.options?.force_recompute),
    peak_risk: series.summary.peak_risk,
    incidents: [...new Set(incidentIds)],
    campaigns: [...new Set(CAMPAIGNS.filter((c) => c.user_id === user_id).map((c) => c.campaign_id))],
    daily: series.series.filter((s) => s.signal_count > 0).map((s) => ({ date: s.date, risk: s.risk, confidence: s.confidence, signal_count: s.signal_count })),
    narrative: CAMPAIGNS.find((c) => c.user_id === user_id)?.narrative ?? `No campaign-level progression detected for ${user_id} in this window.`,
  });
});

app.listen(PORT, () => {
  console.log(`SentinelTrace fixture API listening on http://localhost:${PORT}`);
});
