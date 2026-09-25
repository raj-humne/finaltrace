// Fixture data for the SentinelTrace dashboard, built against the example
// payloads in docs/05-API-SPEC.md. This stands in for Track B's real API
// until it lands — same shapes, same field names, deterministic content.

const SOURCES = ["file", "logon", "email", "device", "http"];
const DEPARTMENTS = ["Research", "IT", "Sales", "Legal", "Finance", "Production"];
const ROLES = ["Engineer", "Sysadmin", "Salesman", "Lawyer", "Accountant", "Technician"];

function seededRandom(seed) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

const rand = seededRandom(20100814);

function pick(arr) {
  return arr[Math.floor(rand() * arr.length)];
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function isoDate(y, m, d) {
  return `${y}-${pad(m)}-${pad(d)}`;
}

// ---- Named, hand-authored "flagship" scenarios (mirror the API spec's own examples) ----

const FLAGSHIP_USERS = [
  {
    user_id: "AAF0535",
    name: "Aaron A. Fields",
    email: "AAF0535@dtaa.com",
    role: "Engineer",
    department: "Research",
    team: "Team-07",
    supervisor: "BKL0022",
    cohort_key: "eng|research",
    cohort_size: 46,
    tenure_days: 812,
    departure_date: "2010-08-25",
    first_seen: "2010-01-04",
    last_seen: "2010-08-24",
    baseline: { days_available: 217, maturity: 1.0, working_window: { start_min: 498, end_min: 1086 } },
    current_risk: 73.2,
    risk_ewma: 41.8,
    trend: "rising",
  },
  {
    user_id: "MRE0221",
    name: "Marcus Reed",
    email: "MRE0221@dtaa.com",
    role: "Sysadmin",
    department: "IT",
    team: "Team-02",
    supervisor: "PTL0091",
    cohort_key: "sysadmin|it",
    cohort_size: 18,
    tenure_days: 1490,
    departure_date: null,
    first_seen: "2010-01-02",
    last_seen: "2010-08-20",
    baseline: { days_available: 231, maturity: 1.0, working_window: { start_min: 480, end_min: 1050 } },
    current_risk: 61.0,
    risk_ewma: 22.4,
    trend: "rising",
  },
  {
    user_id: "BKR0912",
    name: "Bianca Kruse",
    email: "BKR0912@dtaa.com",
    role: "Technician",
    department: "Production",
    team: "Team-11",
    supervisor: "OLW0403",
    cohort_key: "technician|production",
    cohort_size: 62,
    tenure_days: 2100,
    departure_date: null,
    first_seen: "2010-01-02",
    last_seen: "2010-08-19",
    baseline: { days_available: 231, maturity: 1.0, working_window: { start_min: 0, end_min: 1439 } },
    current_risk: 24.6,
    risk_ewma: 21.1,
    trend: "flat",
  },
];

// Procedurally-named additional users to fill out the queue (department/role
// cohorts, mostly quiet — this is what "902 monitored" looks like).
const FIRST_NAMES = ["Wei", "Sofia", "Liam", "Amara", "Noah", "Priya", "Kenji", "Elena", "Omar", "Grace", "Ivan", "Lena", "Marco", "Nadia", "Tariq", "Yuki"];
const LAST_NAMES = ["Chen", "Alvarez", "Osei", "Novak", "Singh", "Petrov", "Diallo", "Fischer", "Kowalski", "Reyes", "Haddad", "Larsen", "Moreau", "Tanaka"];

function makeFillerUser(i) {
  const dept = pick(DEPARTMENTS);
  const role = pick(ROLES);
  const first = pick(FIRST_NAMES);
  const last = pick(LAST_NAMES);
  const id = `${first[0]}${last[0]}${last[1] ?? "X"}${String(1000 + i)}`.toUpperCase();
  const risk = Math.round((rand() * (rand() < 0.08 ? 90 : 30)) * 10) / 10;
  return {
    user_id: id,
    name: `${first} ${last}`,
    email: `${id}@dtaa.com`,
    role,
    department: dept,
    team: `Team-${String(1 + Math.floor(rand() * 14)).padStart(2, "0")}`,
    supervisor: `SUP${String(1 + Math.floor(rand() * 90)).padStart(4, "0")}`,
    cohort_key: `${role.toLowerCase()}|${dept.toLowerCase()}`,
    cohort_size: 15 + Math.floor(rand() * 60),
    tenure_days: 60 + Math.floor(rand() * 3000),
    departure_date: rand() < 0.03 ? isoDate(2010, 8, 15 + Math.floor(rand() * 14)) : null,
    first_seen: "2010-01-02",
    last_seen: "2010-08-22",
    baseline: {
      days_available: 8 + Math.floor(rand() * 223),
      maturity: rand() < 0.1 ? Math.round(rand() * 100) / 100 : 1.0,
      working_window: { start_min: 420 + Math.floor(rand() * 120), end_min: 990 + Math.floor(rand() * 120) },
    },
    current_risk: risk,
    risk_ewma: Math.max(0, Math.round((risk * (0.4 + rand() * 0.5)) * 10) / 10),
    trend: pick(["rising", "falling", "flat"]),
  };
}

const FILLER_USERS = Array.from({ length: 240 }, (_, i) => makeFillerUser(i));
const ALL_USERS = [...FLAGSHIP_USERS, ...FILLER_USERS];
const USERS_BY_ID = Object.fromEntries(ALL_USERS.map((u) => [u.user_id, u]));

function userListItem(u) {
  return {
    user_id: u.user_id,
    name: u.name,
    role: u.role,
    department: u.department,
    cohort_key: u.cohort_key,
    current_risk: u.current_risk,
    risk_ewma: u.risk_ewma,
    trend: u.trend,
    open_incidents: incidentsByUser(u.user_id).filter((i) => i.status === "open").length,
    departing_in_days: u.departure_date ? daysBetween("2010-08-14", u.departure_date) : null,
  };
}

function userProfile(u) {
  const counts = { AUTO_FLAG: 0, ANALYST_REVIEW: 0, MONITOR: 0 };
  for (const inc of incidentsByUser(u.user_id)) {
    if (counts[inc.triage_lane] !== undefined) counts[inc.triage_lane] += 1;
  }
  return {
    user_id: u.user_id,
    name: u.name,
    email: u.email,
    org: { role: u.role, department: u.department, team: u.team, supervisor: u.supervisor, cohort_size: u.cohort_size },
    tenure_days: u.tenure_days,
    departure_date: u.departure_date,
    first_seen: u.first_seen,
    last_seen: u.last_seen,
    baseline: u.baseline,
    current_risk: u.current_risk,
    risk_ewma: u.risk_ewma,
    incident_counts: counts,
  };
}

function daysBetween(a, b) {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000);
}

// ---- Signals, incidents ----

const AAF_SIGNALS = [
  {
    signal_id: 88231,
    rule_id: "ctx.offhours_own_pc",
    name: "Off-hours logon on own workstation",
    category: "context",
    stage: 2,
    strength: 0.35,
    weight: 0.6,
    contribution: 0.21,
    phrase: "logged on to their own workstation 3h after their normal last-activity time",
    detail: { feature: "offhours_event_ratio", observed: 0.62, threshold: 0.3, z_self: 2.4, z_peer: 1.8 },
    evidence_event_ids: ["a1f2c3d4e5f60001"],
    references: [],
  },
  {
    signal_id: 88232,
    rule_id: "stage.first_ever_usb",
    name: "First removable-media connection",
    category: "staging",
    stage: 2,
    strength: 0.82,
    weight: 1.6,
    contribution: 0.7,
    phrase: "connected removable media for the first time in 243 days",
    detail: { feature: "is_first_ever_usb", observed: 1, threshold: 0, z_self: null, z_peer: null },
    evidence_event_ids: ["b7c3d4e5f6070002"],
    references: ["MITRE T1052.001"],
  },
  {
    signal_id: 88234,
    rule_id: "exfil.file_copy_to_usb",
    name: "Bulk file activity during removable-media session",
    category: "exfil",
    stage: 4,
    strength: 0.7,
    weight: 1.3,
    contribution: 0.91,
    phrase: "copied 47 files while removable media was connected",
    detail: { feature: "file_events_during_usb", observed: 47, threshold: 10, z_self: 5.8, z_peer: 4.1 },
    evidence_event_ids: ["c9d1000000000001", "c9d1000000000002", "c9d1000000000003"],
    references: ["MITRE T1052.001"],
  },
  {
    signal_id: 88235,
    rule_id: "exfil.leak_platform_upload",
    name: "Upload to a personal cloud-storage domain",
    category: "exfil",
    stage: 5,
    strength: 0.75,
    weight: 1.1,
    contribution: 0.52,
    phrase: "uploaded data to a personal cloud-storage domain never visited before",
    detail: { feature: "leak_platform_visits", observed: 1, threshold: 0, z_self: null, z_peer: null },
    evidence_event_ids: ["d1e2000000000009"],
    references: ["MITRE T1567.002"],
  },
  {
    signal_id: 88236,
    rule_id: "ml.isoforest",
    name: "Cohort anomaly score",
    category: "ml",
    stage: 4,
    strength: 0.55,
    weight: 1.0,
    contribution: 0.51,
    phrase: "behaviour in the 99.1st percentile of the Engineer/Research cohort",
    detail: { feature: "isoforest_percentile", observed: 99.1, threshold: 95, z_self: null, z_peer: null },
    evidence_event_ids: [],
    references: [],
  },
];

const MRE_SIGNALS = [
  {
    signal_id: 91001,
    rule_id: "recon.hacking_tool_download",
    name: "Hacking-tool download",
    category: "recon",
    stage: 1,
    strength: 0.66,
    weight: 1.2,
    contribution: 0.58,
    phrase: "downloaded a file from a known hacking-tool distribution domain",
    detail: { feature: "hacktool_domain_visits", observed: 1, threshold: 0, z_self: null, z_peer: null },
    evidence_event_ids: ["e1f2000000000001"],
    references: ["MITRE T1588.002"],
  },
  {
    signal_id: 91002,
    rule_id: "stage.supervisor_pc_access",
    name: "Logon to a supervisor's workstation",
    category: "staging",
    stage: 3,
    strength: 0.6,
    weight: 1.4,
    contribution: 0.63,
    phrase: "logged on to their supervisor's workstation, never used before",
    detail: { feature: "is_first_ever_pc", observed: 1, threshold: 0, z_self: null, z_peer: null },
    evidence_event_ids: ["e1f2000000000002"],
    references: ["MITRE T1078"],
  },
  {
    signal_id: 91003,
    rule_id: "ml.isoforest",
    name: "Cohort anomaly score",
    category: "ml",
    stage: 3,
    strength: 0.4,
    weight: 1.0,
    contribution: 0.34,
    phrase: "behaviour in the 94.0th percentile of the Sysadmin/IT cohort",
    detail: { feature: "isoforest_percentile", observed: 94.0, threshold: 90, z_self: null, z_peer: null },
    evidence_event_ids: [],
    references: [],
  },
];

function buildIncident({ id, user, date, startTime, endTime, risk, confidence, lane, headline, stages, signals, campaign, status, review }) {
  const window = { start: `${date}T${startTime}Z`, end: `${date}T${endTime}Z` };
  const durationMin = (new Date(window.end).getTime() - new Date(window.start).getTime()) / 60000;
  const total = signals.reduce((s, sig) => s + sig.contribution, 0);
  const priorLogit = -4.6;
  const rulePoints = signals.filter((s) => s.category !== "ml").reduce((s, sig) => s + sig.contribution, 0);
  const mlPoints = signals.filter((s) => s.category === "ml").reduce((s, sig) => s + sig.contribution, 0);
  const correlationPoints = signals.length >= 3 ? 0.3 * (new Set(signals.map((s) => s.category)).size - 1) : 0;
  const totalLogit = priorLogit + rulePoints + mlPoints + correlationPoints + 4.6;
  const attributionItems = signals
    .map((sig, idx) => ({
      signal_id: sig.signal_id,
      rule_id: sig.rule_id,
      risk_without: Math.max(0, Math.round((risk - sig.contribution * 20) * 10) / 10),
      delta: Math.round(sig.contribution * 20 * 10) / 10,
      rank: idx + 1,
      in_minimal_set: false,
    }))
    .sort((a, b) => b.delta - a.delta)
    .map((a, idx) => ({ ...a, rank: idx + 1 }));

  let running = 0;
  const alertThreshold = 40.0;
  const minimalSet = [];
  for (const item of attributionItems) {
    if (running >= risk - alertThreshold) break;
    minimalSet.push(item.rule_id);
    running += item.delta;
  }
  for (const item of attributionItems) item.in_minimal_set = minimalSet.includes(item.rule_id);

  const u = USERS_BY_ID[user];

  return {
    incident_id: id,
    user_id: user,
    user_name: u.name,
    department: u.department,
    window,
    duration_min: Math.round(durationMin * 10) / 10,
    risk,
    confidence,
    triage_lane: lane,
    status,
    headline,
    killchain_stages: stages,
    max_stage: Math.max(...stages),
    signal_count: signals.length,
    event_count: 20 + signals.length * 8,
    campaign_id: campaign ?? null,
    top_signal: {
      rule_id: [...signals].sort((a, b) => b.contribution - a.contribution)[0].rule_id,
      delta: attributionItems[0]?.delta ?? 0,
    },
    baseline_days: u.baseline.days_available < 14 ? u.baseline.days_available : null,
    departing_in_days: u.departure_date ? daysBetween(date, u.departure_date) : null,
    campaign_incident_count: campaign ? 3 : null,
    _signals: signals,
    _breakdown: {
      prior_logit: priorLogit,
      rule_points: Math.round(rulePoints * 100) / 100,
      ml_points: Math.round(mlPoints * 100) / 100,
      correlation_points: Math.round(correlationPoints * 100) / 100,
      total_logit: Math.round(totalLogit * 100) / 100,
      tau: 1.8,
    },
    _attribution: attributionItems,
    _minimalSet: minimalSet,
    _alertThreshold: alertThreshold,
    _review: review ?? null,
    _cohortSize: u.cohort_size,
    _cohortRole: u.role,
    _cohortDept: u.department,
  };
}

const FLAGSHIP_INCIDENTS = [
  buildIncident({
    id: "INC-20100814-AAF0535-01",
    user: "AAF0535",
    date: "2010-08-14",
    startTime: "21:47:03",
    endTime: "22:31:40",
    risk: 73.2,
    confidence: 0.88,
    lane: "AUTO_FLAG",
    headline: "First removable-media use in 8 months — 5 correlated signals across 3 categories",
    stages: [2, 3, 4],
    signals: AAF_SIGNALS,
    campaign: "CMP-AAF0535-001",
    status: "open",
  }),
  buildIncident({
    id: "INC-20100809-AAF0535-01",
    user: "AAF0535",
    date: "2010-08-09",
    startTime: "20:10:00",
    endTime: "20:44:00",
    risk: 44.6,
    confidence: 0.63,
    lane: "ANALYST_REVIEW",
    headline: "Off-hours logon on an unfamiliar workstation",
    stages: [1, 2],
    signals: AAF_SIGNALS.slice(0, 2),
    campaign: "CMP-AAF0535-001",
    status: "closed",
    review: { verdict: "inconclusive", note: "Flagged during initial triage; deferred pending the 8/14 incident.", analyst_id: "priya.s", reviewed_at: "2010-08-10T09:04:00Z" },
  }),
  buildIncident({
    id: "INC-20100802-AAF0535-01",
    user: "AAF0535",
    date: "2010-08-02",
    startTime: "13:02:00",
    endTime: "13:40:00",
    risk: 28.1,
    confidence: 0.41,
    lane: "MONITOR",
    headline: "Sustained job-search browsing",
    stages: [0],
    signals: [
      { ...AAF_SIGNALS[0], signal_id: 88001, rule_id: "ctx.job_search_browsing", name: "Job-search site visits", category: "context", stage: 0, strength: 0.3, weight: 0.5, contribution: 0.28, phrase: "visited job-search sites on 6 of the last 10 working days" },
    ],
    campaign: "CMP-AAF0535-001",
    status: "open",
  }),
  buildIncident({
    id: "INC-20100812-MRE0221-01",
    user: "MRE0221",
    date: "2010-08-12",
    startTime: "19:02:00",
    endTime: "19:44:00",
    risk: 61.0,
    confidence: 0.52,
    lane: "ANALYST_REVIEW",
    headline: "Hacking-tool download followed by use of a supervisor workstation",
    stages: [1, 3],
    signals: MRE_SIGNALS,
    status: "open",
  }),
  buildIncident({
    id: "INC-20100710-BKR0912-01",
    user: "BKR0912",
    date: "2010-07-10",
    startTime: "02:15:00",
    endTime: "02:40:00",
    risk: 19.4,
    confidence: 0.35,
    lane: "SUPPRESSED",
    headline: "Nightly USB rotation — suppressed (CHG-4471)",
    stages: [2],
    signals: [
      { ...AAF_SIGNALS[1], signal_id: 77001, rule_id: "stage.usb_after_dormancy", contribution: 0.19 },
    ],
    status: "closed",
    review: { verdict: "benign", note: "Backup operator; nightly USB rotation is documented in CHG-4471.", analyst_id: "priya.s", reviewed_at: "2010-07-11T08:00:00Z" },
  }),
];

function makeFillerIncident(i) {
  const u = pick(FILLER_USERS);
  const day = 1 + Math.floor(rand() * 28);
  const month = 6 + Math.floor(rand() * 3);
  const date = isoDate(2010, month, day);
  const hour = Math.floor(rand() * 24);
  const startTime = `${pad(hour)}:${pad(Math.floor(rand() * 60))}:00`;
  const endMinuteOffset = 10 + Math.floor(rand() * 60);
  const endDate = new Date(`${date}T${startTime}Z`);
  endDate.setMinutes(endDate.getMinutes() + endMinuteOffset);
  const endTime = `${pad(endDate.getUTCHours())}:${pad(endDate.getUTCMinutes())}:00`;
  const laneRoll = rand();
  const lane = laneRoll < 0.03 ? "AUTO_FLAG" : laneRoll < 0.15 ? "ANALYST_REVIEW" : laneRoll < 0.2 ? "SUPPRESSED" : "MONITOR";
  const risk = lane === "AUTO_FLAG" ? 65 + rand() * 30 : lane === "ANALYST_REVIEW" ? 40 + rand() * 25 : lane === "SUPPRESSED" ? 10 + rand() * 20 : 5 + rand() * 35;
  const confidence = lane === "AUTO_FLAG" ? 0.65 + rand() * 0.33 : lane === "ANALYST_REVIEW" ? 0.2 + rand() * 0.5 : 0.2 + rand() * 0.6;
  const headlines = [
    "Elevated off-hours file access versus peer norm",
    "First access to an unfamiliar file share",
    "Sustained after-hours logon pattern",
    "Elevated email traffic to an external domain",
    "Print volume spike outside normal working hours",
    "First-ever access to a departing colleague's shared drive",
    "Browsing pattern consistent with disgruntlement indicators",
    "Repeated failed logons followed by a successful one",
  ];
  const stagesPool = [[0], [1], [1, 2], [2, 3], [0, 1, 2], [3, 4]];
  const stages = pick(stagesPool);
  const category = pick(["context", "recon", "staging", "exfil"]);
  const sig = {
    signal_id: 100000 + i,
    rule_id: `${category}.filler_${i % 9}`,
    name: "Behavioural deviation",
    category,
    stage: stages[stages.length - 1],
    strength: Math.round(rand() * 100) / 100,
    weight: Math.round((0.4 + rand() * 1.2) * 100) / 100,
    contribution: Math.round(rand() * 0.6 * 100) / 100,
    phrase: pick(headlines).toLowerCase(),
    detail: { feature: "generic_feature", observed: Math.round(rand() * 50 * 10) / 10, threshold: 10, z_self: Math.round(rand() * 5 * 10) / 10, z_peer: Math.round(rand() * 4 * 10) / 10 },
    evidence_event_ids: [`f${i.toString(16).padStart(15, "0")}`],
    references: [],
  };
  const signalCount = 1 + Math.floor(rand() * 3);
  const signals = Array.from({ length: signalCount }, (_, k) => ({ ...sig, signal_id: sig.signal_id + k * 7, contribution: Math.round(rand() * 0.5 * 100) / 100 }));
  return buildIncident({
    id: `INC-${date.replace(/-/g, "")}-${u.user_id}-${String(i).padStart(2, "0")}`,
    user: u.user_id,
    date,
    startTime,
    endTime,
    risk: Math.round(risk * 10) / 10,
    confidence: Math.round(confidence * 100) / 100,
    lane,
    headline: pick(headlines),
    stages,
    signals,
    status: rand() < 0.3 ? "closed" : "open",
    review: rand() < 0.3 ? { verdict: pick(["confirmed_threat", "benign", "inconclusive"]), note: "Reviewed during routine triage.", analyst_id: pick(["priya.s", "rohit.k", "anjali.m"]), reviewed_at: `${date}T10:00:00Z` } : null,
  });
}

const FILLER_INCIDENTS = Array.from({ length: 180 }, (_, i) => makeFillerIncident(i + 1));
const ALL_INCIDENTS = [...FLAGSHIP_INCIDENTS, ...FILLER_INCIDENTS].sort((a, b) => b.risk - a.risk);
const INCIDENTS_BY_ID = Object.fromEntries(ALL_INCIDENTS.map((inc) => [inc.incident_id, inc]));

function incidentsByUser(userId) {
  return ALL_INCIDENTS.filter((i) => i.user_id === userId);
}

function incidentListItem(inc) {
  return {
    incident_id: inc.incident_id,
    user_id: inc.user_id,
    user_name: inc.user_name,
    department: inc.department,
    window: inc.window,
    risk: inc.risk,
    confidence: inc.confidence,
    triage_lane: inc.triage_lane,
    status: inc.status,
    headline: inc.headline,
    killchain_stages: inc.killchain_stages,
    max_stage: inc.max_stage,
    signal_count: inc.signal_count,
    event_count: inc.event_count,
    campaign_id: inc.campaign_id,
    top_signal: inc.top_signal,
    baseline_days: inc.baseline_days,
    departing_in_days: inc.departing_in_days,
    campaign_incident_count: inc.campaign_incident_count,
  };
}

function incidentDetail(inc) {
  const bulletFor = (s) => {
    const tag = s.category.toUpperCase().slice(0, 6);
    const pts = Math.round(s.contribution * 20 * 10) / 10;
    let extra = "";
    if (s.detail.observed != null && s.detail.threshold != null) {
      extra = ` (threshold ${s.detail.threshold}; observed ${s.detail.observed}${s.detail.z_self != null ? `; z_self ${s.detail.z_self}` : ""})`;
    }
    return `[${tag} · +${pts} pts] ${s.phrase}${extra}`;
  };
  return {
    incident_id: inc.incident_id,
    user: { user_id: inc.user_id, name: inc.user_name, role: inc._cohortRole, department: inc._cohortDept, cohort_size: inc._cohortSize },
    window: { start: inc.window.start, end: inc.window.end, duration_min: inc.duration_min },
    score: {
      risk: inc.risk,
      confidence: inc.confidence,
      triage_lane: inc.triage_lane,
      breakdown: inc._breakdown,
      confidence_terms: {
        agreement: Math.min(1, Math.round((0.6 + inc.confidence * 0.4) * 100) / 100),
        diversity: Math.min(1, Math.round((new Set(inc._signals.map((s) => s.category)).size / 4) * 100) / 100),
        completeness: inc.baseline_days ? 0.6 : 0.9,
        maturity: inc.baseline_days ? Math.min(1, inc.baseline_days / 14) : 1.0,
        caps_applied: inc.baseline_days ? ["baseline_immature_cap_0.60"] : [],
      },
    },
    narrative: {
      headline: inc.headline,
      summary: narrativeSummary(inc),
      detail_bullets: [...inc._signals].sort((a, b) => b.contribution - a.contribution).slice(0, 4).map(bulletFor),
      template_ids: ["head.top_signal_v1", "sum.stage_progression_v2", "det.signal_bullet_v1"],
    },
    signals: inc._signals,
    attribution: {
      note: "Contributions overlap due to category saturation and the correlation bonus; they do not sum to the total.",
      items: inc._attribution,
      minimal_sufficient_set: inc._minimalSet,
      alert_threshold: inc._alertThreshold,
    },
    campaign: inc.campaign_id ? campaignSummaryRef(inc.campaign_id) : null,
    status: inc.status,
    review: inc._review,
    config_version: "sha256:9f2c1a7e4b3d5f608a1c2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a41",
    links: {
      graph: `/api/v1/incidents/${inc.incident_id}/graph`,
      export: `/api/v1/incidents/${inc.incident_id}/export`,
    },
  };
}

function narrativeSummary(inc) {
  const u = USERS_BY_ID[inc.user_id];
  const start = new Date(inc.window.start);
  const end = new Date(inc.window.end);
  const fmtTime = (d) => `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  const dateStr = inc.window.start.slice(0, 10);
  const depClause = u.departure_date ? ` The user's departure is recorded ${daysBetween(dateStr, u.departure_date)} days later.` : "";
  const topCat = [...inc._signals].sort((a, b) => b.contribution - a.contribution)[0]?.category ?? "behavioural";
  return `${inc.user_id} (${u.role}, ${u.department}) acted between ${fmtTime(start)} and ${fmtTime(end)} on ${dateStr}, generating ${inc._signals.length} correlated signal${inc._signals.length === 1 ? "" : "s"} with a ${topCat} emphasis. Behaviour diverged from both this user's own 30-day norm and their role/department cohort.${depClause}`;
}

function campaignSummaryRef(campaignId) {
  const c = CAMPAIGNS_BY_ID[campaignId];
  if (!c) return null;
  return {
    campaign_id: c.campaign_id,
    incident_count: c.incident_count,
    first_seen: c.first_seen,
    last_seen: c.last_seen,
    stage_progression: c.stage_progression.map((s) => s.stage),
  };
}

// ---- Graph payload ----

function incidentGraph(inc) {
  const baseTs = new Date(inc.window.start).getTime();
  const nodes = [];
  const edges = [];
  let cursor = baseTs;
  const sortedSignals = [...inc._signals].sort((a, b) => a.stage - b.stage);
  sortedSignals.forEach((s, idx) => {
    cursor += (5 + Math.floor(rand() * 20)) * 60000;
    const id = s.evidence_event_ids[0] ?? `${inc.incident_id}-ev-${idx}`;
    nodes.push({
      id,
      ts: new Date(cursor).toISOString(),
      source: s.category === "ml" ? pick(SOURCES) : pick(SOURCES),
      action: s.name,
      label: s.name,
      stage: s.stage,
      risk_contribution: Math.round(s.contribution * 20 * 10) / 10,
      has_signal: true,
      pc_id: `PC-${1000 + (idx % 7)}`,
      user_id: inc.user_id,
    });
    if (idx > 0) {
      const prev = nodes[idx - 1];
      const gapSec = Math.round((cursor - new Date(prev.ts).getTime()) / 1000);
      edges.push({
        source: prev.id,
        target: id,
        gap_seconds: gapSec,
        gap_label: gapSec >= 60 ? `${Math.round(gapSec / 60)} min` : `${gapSec}s`,
        type: s.stage > prev.stage ? "stage_advance" : "temporal",
        weight: s.stage > prev.stage ? 1.0 : 0.6 + rand() * 0.3,
      });
    }
  });
  // context nodes without their own signal, to fill out the picture
  const extra = Math.max(0, inc.event_count - nodes.length);
  for (let i = 0; i < Math.min(extra, 40); i++) {
    cursor += (2 + Math.floor(rand() * 15)) * 60000;
    const id = `${inc.incident_id}-ctx-${i}`;
    nodes.push({
      id,
      ts: new Date(cursor).toISOString(),
      source: pick(SOURCES),
      action: "context event",
      label: "context event",
      stage: nodes[nodes.length - 1]?.stage ?? 0,
      risk_contribution: 0,
      has_signal: false,
      pc_id: `PC-${1000 + (i % 7)}`,
      user_id: inc.user_id,
    });
    const prev = nodes[nodes.length - 2];
    const gapSec = Math.round((cursor - new Date(prev.ts).getTime()) / 1000);
    edges.push({ source: prev.id, target: id, gap_seconds: gapSec, gap_label: gapSec >= 60 ? `${Math.round(gapSec / 60)} min` : `${gapSec}s`, type: "temporal", weight: 0.3 + rand() * 0.3 });
  }
  return {
    incident_id: inc.incident_id,
    over_dense: nodes.length > 60,
    nodes,
    edges,
    layout_hint: "temporal_left_to_right",
    stats: { node_count: nodes.length, edge_count: edges.length, component_diameter: Math.max(1, Math.round(Math.sqrt(nodes.length))) },
  };
}

// ---- Timeline (replay) ----

function userTimeline(userId, date) {
  const incs = incidentsByUser(userId).filter((i) => i.window.start.startsWith(date));
  const events = [];
  let running = 0;
  for (const inc of incs) {
    const g = incidentGraph(inc);
    for (const n of g.nodes.filter((n) => n.has_signal)) {
      running += n.risk_contribution;
      events.push({
        event_id: n.id,
        ts: n.ts,
        source: n.source,
        action: n.action,
        pc_id: n.pc_id,
        attrs: { own_pc: rand() > 0.3, offhours: rand() > 0.5 },
        signal_ids: [],
        risk_after: Math.round(Math.min(running, inc.risk) * 10) / 10,
        stage: n.stage,
      });
    }
  }
  events.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  const u = USERS_BY_ID[userId];
  return {
    date,
    events,
    working_window: u.baseline.working_window,
    final_risk: events.length ? events[events.length - 1].risk_after : 0,
  };
}

// ---- Risk series ----

function userRiskSeries(userId, dateFrom, dateTo) {
  const u = USERS_BY_ID[userId];
  const from = new Date(dateFrom ?? "2010-07-15");
  const to = new Date(dateTo ?? "2010-08-24");
  const series = [];
  const peerBand = [];
  const incs = incidentsByUser(userId);
  let peak = 0;
  let peakDate = null;
  let daysAbove = 0;
  for (let d = new Date(from); d <= to; d.setDate(d.getDate() + 1)) {
    const dateStr = d.toISOString().slice(0, 10);
    const dayIncidents = incs.filter((i) => i.window.start.startsWith(dateStr));
    const risk = dayIncidents.length ? Math.max(...dayIncidents.map((i) => i.risk)) : Math.round(rand() * 15 * 10) / 10;
    const confidence = dayIncidents.length ? Math.max(...dayIncidents.map((i) => i.confidence)) : Math.round((0.2 + rand() * 0.3) * 100) / 100;
    if (risk > peak) {
      peak = risk;
      peakDate = dateStr;
    }
    if (risk >= 40) daysAbove += 1;
    series.push({
      date: dateStr,
      risk,
      confidence,
      risk_ewma: Math.round(risk * 0.6 * 10) / 10,
      signal_count: dayIncidents.reduce((s, i) => s + i.signal_count, 0),
      incident_ids: dayIncidents.map((i) => i.incident_id),
    });
    peerBand.push({
      date: dateStr,
      p50: Math.round((5 + rand() * 6) * 10) / 10,
      p90: Math.round((15 + rand() * 10) * 10) / 10,
      p99: Math.round((30 + rand() * 15) * 10) / 10,
    });
  }
  return {
    user_id: userId,
    window: { from: dateFrom ?? series[0]?.date, to: dateTo ?? series[series.length - 1]?.date },
    series,
    peer_band: peerBand,
    summary: { peak_risk: peak, peak_date: peakDate, days_above_threshold: daysAbove, trend: u.trend },
  };
}

// ---- Campaigns ----

const CAMPAIGNS = [
  {
    campaign_id: "CMP-AAF0535-001",
    user_id: "AAF0535",
    first_seen: "2010-08-02",
    last_seen: "2010-08-14",
    incident_count: 3,
    peak_risk: 73.2,
    campaign_risk: 81.4,
    max_stage: 4,
    stage_progression: [
      { date: "2010-08-02", stage: 0, incident_id: "INC-20100802-AAF0535-01", risk: 28.1, headline: "Sustained job-search browsing" },
      { date: "2010-08-09", stage: 2, incident_id: "INC-20100809-AAF0535-01", risk: 44.6, headline: "Off-hours logon on an unfamiliar workstation" },
      { date: "2010-08-14", stage: 4, incident_id: "INC-20100814-AAF0535-01", risk: 73.2, headline: "First removable-media use in 8 months" },
    ],
    narrative: "Over 13 days this user progressed from job-search activity, through off-hours access on an unfamiliar workstation, to removable-media collection and an external upload. No single day exceeded the alert threshold before 2010-08-14; the progression did.",
  },
];
const CAMPAIGNS_BY_ID = Object.fromEntries(CAMPAIGNS.map((c) => [c.campaign_id, c]));

// ---- Rules ----

const RULE_CATALOGUE = [
  { rule_id: "ctx.offhours_own_pc", name: "Off-hours logon, own workstation", category: "context", stage: 2, weight: 0.6, requires_baseline: true, description: "Logon falls outside the user's learned working window." },
  { rule_id: "ctx.job_search_browsing", name: "Job-search site visits", category: "context", stage: 0, weight: 0.5, requires_baseline: false, description: "Repeated visits to job-search domains." },
  { rule_id: "ctx.departure_imminent", name: "Departure recorded within 30 days", category: "context", stage: 0, weight: 0.4, requires_baseline: false, description: "HR record shows an imminent departure." },
  { rule_id: "recon.hacking_tool_download", name: "Hacking-tool download", category: "recon", stage: 1, weight: 1.2, requires_baseline: false, description: "Download from a known hacking-tool distribution domain." },
  { rule_id: "stage.first_ever_usb", name: "First-ever removable media", category: "staging", stage: 2, weight: 1.6, requires_baseline: true, description: "First removable-media connection in the user's history." },
  { rule_id: "stage.usb_after_dormancy", name: "Removable media after long dormancy", category: "staging", stage: 2, weight: 1.1, requires_baseline: true, description: "Removable media reconnected after 60+ days of no use." },
  { rule_id: "stage.supervisor_pc_access", name: "Supervisor workstation access", category: "staging", stage: 3, weight: 1.4, requires_baseline: true, description: "First-ever logon to a supervisor's workstation." },
  { rule_id: "exfil.file_copy_to_usb", name: "Bulk file copy to removable media", category: "exfil", stage: 4, weight: 1.3, requires_baseline: true, description: "File event count during a USB session exceeds the cohort threshold." },
  { rule_id: "exfil.leak_platform_upload", name: "Personal cloud-storage upload", category: "exfil", stage: 5, weight: 1.1, requires_baseline: false, description: "Upload to a personal cloud-storage domain." },
  { rule_id: "ml.isoforest", name: "Cohort anomaly (IsolationForest)", category: "ml", stage: 4, weight: 1.0, requires_baseline: true, description: "Within-cohort percentile from the anomaly model." },
];

function ruleStats(ruleId, dateFrom, dateTo) {
  const fires = ALL_INCIDENTS.flatMap((i) => i._signals).filter((s) => s.rule_id === ruleId || s.rule_id.startsWith(ruleId.split(".")[0]));
  const configured = RULE_CATALOGUE.find((r) => r.rule_id === ruleId);
  const fireCount = 200 + Math.floor(rand() * 400);
  const reviewed = Math.floor(fireCount * (0.15 + rand() * 0.15));
  const confirmed = Math.floor(reviewed * (0.4 + rand() * 0.4));
  const benign = Math.floor((reviewed - confirmed) * 0.8);
  const inconclusive = reviewed - confirmed - benign;
  const precision = reviewed ? Math.round((confirmed / reviewed) * 100) / 100 : 0;
  const measuredLogOdds = Math.round((Math.log((precision + 0.01) / (1 - precision + 0.01))) * 100) / 100;
  const configuredWeight = configured?.weight ?? 1.0;
  const drift = Math.round((configuredWeight - measuredLogOdds) * 100) / 100;
  return {
    rule_id: ruleId,
    configured_weight: configuredWeight,
    fire_count: fireCount,
    fire_rate_per_user_day: Math.round((fireCount / 250000) * 10000) / 10000,
    reviewed,
    confirmed,
    benign,
    inconclusive,
    observed_precision: precision,
    measured_log_odds: measuredLogOdds,
    weight_drift: drift,
    recommendation: Math.abs(drift) > 0.3 ? "reduce_weight" : Math.abs(drift) > 0.15 ? "review" : "within_tolerance",
  };
}

// ---- Detection health / eval ----

function detectionHealth() {
  const laneCounts = { AUTO_FLAG: 0, ANALYST_REVIEW: 0, MONITOR: 0, SUPPRESSED: 0 };
  for (const inc of ALL_INCIDENTS) laneCounts[inc.triage_lane] += 1;
  const bins = [
    [0.0, 0.1], [0.1, 0.2], [0.2, 0.3], [0.3, 0.4], [0.4, 0.5],
    [0.5, 0.6], [0.6, 0.7], [0.7, 0.8], [0.8, 0.9], [0.9, 1.0],
  ].map(([lo, hi]) => {
    const inBin = ALL_INCIDENTS.filter((i) => i.confidence >= lo && i.confidence < hi + (hi === 1.0 ? 0.001 : 0));
    const n = inBin.length || Math.floor(rand() * 40) + 5;
    const observed = Math.max(0, Math.min(1, Math.round(((lo + hi) / 2 + (rand() - 0.5) * 0.08) * 100) / 100));
    return { confidence_range: [lo, hi], n, observed_precision: observed };
  });
  const ece = Math.round((bins.reduce((s, b) => s + Math.abs((b.confidence_range[0] + b.confidence_range[1]) / 2 - b.observed_precision) * b.n, 0) / bins.reduce((s, b) => s + b.n, 0)) * 1000) / 1000;
  return {
    window: { from: "2010-01-01", to: "2011-05-31" },
    alert_volume: { incidents_per_day: 0.41, per_1k_users_per_day: 0.41 },
    lane_mix: laneCounts,
    compression: { signals_per_incident_mean: Math.round((ALL_INCIDENTS.reduce((s, i) => s + i.signal_count, 0) / ALL_INCIDENTS.length) * 10) / 10, events_per_incident_mean: Math.round((ALL_INCIDENTS.reduce((s, i) => s + i.event_count, 0) / ALL_INCIDENTS.length) * 10) / 10 },
    calibration: { bins, ece },
    top_firing_rules: RULE_CATALOGUE.slice(0, 6).map((r) => ({ rule_id: r.rule_id, count: 200 + Math.floor(rand() * 3000), observed_precision: Math.round(rand() * 100) / 100 })),
    warnings: ["ctx.departure_imminent has low standalone precision — intended as a supporting signal only"],
  };
}

function evalReport() {
  return {
    config_version: "sha256:9f2c1a7e4b3d5f608a1c2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a41",
    data_source: "cert_r4.2_real",
    generated_at: "2026-09-24T08:12:00Z",
    primary_metrics: {
      insider_recall: [0.87, 0.78, 0.93],
      incident_precision: [0.58, 0.49, 0.66],
      auto_flag_precision: [0.81, 0.71, 0.89],
      pr_auc: [0.41, 0.34, 0.48],
      median_time_to_detect_days: 1.5,
    },
    pr_curve: Array.from({ length: 20 }, (_, i) => ({ recall: Math.round((i / 19) * 100) / 100, precision: Math.round(Math.max(0.05, 1 - (i / 19) * 0.85) * 100) / 100 })),
    per_scenario_recall: { scenario_1: 0.91, scenario_2: 0.83, scenario_3: 0.79 },
    time_to_detect_distribution: [0, 0, 1, 1, 1, 2, 2, 3, 5, 8],
  };
}

export {
  ALL_USERS,
  USERS_BY_ID,
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
  incidentsByUser,
  ruleStats,
  detectionHealth,
  evalReport,
  daysBetween,
};
