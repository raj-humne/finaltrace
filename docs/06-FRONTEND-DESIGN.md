# 06 — Frontend Design

---

## 1. Who this is for, and what it has to do

One user, one moment: **an analyst at 02:00, seven hours into a shift, deciding whether this item deserves ten minutes.** Everything below is judged against that.

The second user, less often but with higher stakes, is the investigation lead assembling something they will hand to HR. For them the screen has to behave like a document, because that is what it becomes.

That gives the interface two jobs, in order:

1. **Make the finding readable in ten seconds.**
2. **Make the evidence behind it inspectable without leaving the page.**

---

## 2. Design concept: the case file, not the dashboard

The default for this product category is a grid of tiles: sparkline card, donut card, top-10 card, a red number. That layout is wrong here, because it answers "how are things overall" — and nobody opens this tool to ask that. They open it holding one question about one person.

So the organising metaphor is a **case file**: a written finding at the top, an evidence chain beneath it, and the raw record available but not in the way. The page reads as a document with instruments in it, not as a wall of instruments.

**The one bold element is the kill-chain spine.** A six-stage horizontal rail that carries the whole product thesis — *individually harmless actions become a progression*. It appears at three scales and is the thing that makes a SentinelTrace screen recognisable at a glance:

```
 CONTEXT   RECON   STAGING   COLLECTION   EXFILTRATION   EVASION
    ·———————·———————●═══════════●════════════●—————————————○
                    ▲           ▲            ▲
                 21:47       22:04        22:31
```

Filled and joined where the chain advanced, hollow where it did not. In a queue row it is 96px wide and unlabelled; in incident detail it is full width with events hung beneath it; in campaign view its horizontal axis becomes days instead of hours.

Everything else on the page is deliberately quiet so the spine carries.

### What was rejected, and why

| Default for this genre | Why not | Instead |
|---|---|---|
| Slate-navy ground with red alert accents | It is the stock SOC look, and pervasive red produces alarm blindness — the thing this product exists to reduce | Petrol ink ground; red reserved strictly for one status role |
| Green/amber/red traffic light for risk | Fails for deutan viewers (~6% of men), and hue-only encoding breaks rule 6 of the viz method | Single-hue ember ramp for magnitude + reserved status colors with icon and label. See section 9 |
| Big KPI number as the hero | The hero should be the most characteristic thing in this subject, and the characteristic thing here is a *sequence*, not a total | Kill-chain spine as the hero |
| Identical rounded cards in a grid | Uniform containers flatten hierarchy — the finding and the raw log would look equally important | Document flow: one reading column, hairline-separated sections, containers only where content is genuinely a set |
| Inter / system sans throughout | Correct and invisible; carries no point of view | Archivo for interface, Source Serif for the finding, JetBrains Mono for tabular values — three faces, three non-overlapping jobs |

---

## 3. Type

Three families, each with a job it does not share.

| Role | Face | Why |
|---|---|---|
| Interface — headings, labels, controls, tables | **Archivo** (400/500/600) | A grotesque drawn for dense screen data; holds up at 12px in a table row, has enough character at 28px to head a page |
| The finding — narrative prose only | **Source Serif 4** (400, 400 italic) | The narrative is the only *written argument* in the product. Setting it in a serif at a comfortable measure marks it as a conclusion rather than another data field. This is the typographic signal that "a human should read this sentence" |
| Values that must align — timestamps, ids, scores, deltas | **JetBrains Mono** (400/500) | Strictly tabular use: event ids, clock times, point deltas in the attribution table. Never used for labels or headings |

**Scale** (1.25 ratio, 16px base):

```
44 / 1.05 / -0.02em   page title            Archivo 600
28 / 1.15 / -0.01em   incident headline     Archivo 600
22 / 1.30             section heading       Archivo 500
18 / 1.55 / 68ch      narrative             Source Serif 4 400
16 / 1.50             body                  Archivo 400
14 / 1.45             table, controls       Archivo 400
13 / 1.40             axis ticks, captions  Archivo 400
13 / 1.40             values, ids, times    JetBrains Mono 400
```

Narrative measure is capped at **68 characters**; serif body gets the extra line-height it needs (1.55).

**Not doing:** no tracked-out capitals as section labels, no single accented word in a headline, no label stacked above content that already names itself.

---

## 4. Color

Validated with the viz method's checker against both surfaces. Every result below is computed, not judged by eye.

### 4.1 Surfaces and ink

| Role | Dark (default) | Light |
|---|---|---|
| Page plane | `#0E1315` | `#F1F3F4` |
| Surface (chart, panel) | `#151B1E` | `#FAFBFB` |
| Raised surface | `#1C2428` | `#FFFFFF` |
| Primary ink | `#F2F5F6` | `#0B0F10` |
| Secondary ink | `#A9B6BA` | `#4C585C` |
| Muted (axis, meta) | `#6F7D82` | `#77858A` |
| Hairline | `rgba(242,245,246,0.10)` | `rgba(11,15,16,0.10)` |
| Gridline | `#232C30` | `#E3E7E8` |

The ground is a **petrol ink** — cool and slightly green-blue, not a tinted black standing in for black. It reads as an instrument surface and it lets the ember risk ramp sit warm against it without either fighting.

### 4.2 Categorical — the five log sources

Fixed slot order. Assigned once, never cycled, never reassigned when a filter changes the series count.

| Slot | Source | Dark | Light |
|---|---|---|---|
| 1 | `file` | `#199e70` | `#1baf7a` |
| 2 | `logon` | `#3987e5` | `#2a78d6` |
| 3 | `email` | `#c98500` | `#eda100` |
| 4 | `device` | `#9085e9` | `#4a3aa7` |
| 5 | `http` | `#d55181` | `#e87ba4` |

**Validator results.** Dark on `#151B1E`: lightness band PASS, chroma PASS, worst adjacent CVD ΔE 16.0 (deutan) PASS, normal-vision floor 19.7 PASS, contrast all ≥ 3:1 PASS. Light on `#FAFBFB`: worst adjacent CVD ΔE 23.1 PASS, normal-vision 24.0 PASS, contrast **WARN** — aqua 2.72, yellow 2.09, magenta 2.60 sit below 3:1.

> **Binding consequence of that WARN:** in light mode, every chart using source colors ships visible direct labels or a table view. This is not optional and not dismissable. It is why the source legend in light mode is always direct-labelled rather than a color key.

The ordering is the safety mechanism. Aqua and magenta must never be adjacent slots — that pair collapses to ΔE 1.6 under deutan simulation, which is the single worst collision available in this hue set. It was found by running candidate orderings through the validator, not by inspection.

### 4.3 Sequential — risk magnitude

One hue, light to dark. Ember, chosen to read warm against the petrol ground and to be unmistakably *not* a category.

| step | 100 | 200 | 300 | 400 | 500 | 600 | 700 |
|---|---|---|---|---|---|---|---|
| hex | `#FDE4C8` | `#F9C68B` | `#F0A24E` | `#DE7F1C` | `#B9640F` | `#8F4B0C` | `#6A360A` |

Ordinal use (discrete bands, graph node fills) uses steps 300–600: validated PASS — monotone lightness, adjacent ΔL ≥ 0.06, dark-end contrast 2.63:1, hue spread 10°.

**Kill-chain stage** is a second sequential context, so by the method's rule it takes the next categorical hue as its own one-hue ramp: the blue ramp, `#cde2fb → #184f95`. Stage is structure; risk is heat. They never share a scale.

### 4.4 Status — reserved, never reused as a series

| Lane | Role | Hex | Glyph |
|---|---|---|---|
| `AUTO_FLAG` | critical | `#d03b3b` | filled square |
| `ANALYST_REVIEW` | serious | `#ec835a` | half square |
| `MONITOR` | warning | `#fab219` | hollow square |
| `SUPPRESSED` | neutral | muted ink | dash |

Always shipped as **glyph + word + color**. Never color alone. An analyst who cannot distinguish `#d03b3b` from `#ec835a` reads "Auto-flag" and "Review" and loses nothing.

---

## 5. Screens

### 5.1 Queue — `/incidents`

The default landing screen. Scannable rows, not cards. Sorted by risk descending.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  SentinelTrace              Queue   Users   Detection health          [theme]   │
├────────────────────────────────────────────────────────────────────────────────┤
│  Triage queue                                                                   │
│  34 auto-flagged · 118 awaiting review · 902 monitored          17 Aug 2010     │
│                                                                                 │
│  [ Lane ▾ ] [ Stage ▾ ] [ Department ▾ ] [ Date range ▾ ]    Sort: Risk ▾      │
├────────────────────────────────────────────────────────────────────────────────┤
│ ■ Auto-flag │ 73 │ conf ▓▓▓▓▓▓▓▓░░ 0.88                                        │
│   Aaron A. Fields · Engineer, Research             ·———●═══●═══●———○            │
│   First removable-media use in 8 months — 5 correlated signals, 3 categories    │
│   14 Aug 2010, 21:47–22:31     Departing in 11 days        3 in this campaign   │
├────────────────────────────────────────────────────────────────────────────────┤
│ ◨ Review    │ 61 │ conf ▓▓▓▓▓░░░░░ 0.52                                        │
│   Marcus Reed · Sysadmin, IT                       ·———●═══●———○———○            │
│   Hacking-tool download followed by use of a supervisor workstation             │
│   12 Aug 2010, 19:02–19:44     Baseline 22 days            first incident       │
└────────────────────────────────────────────────────────────────────────────────┘
```

Row anatomy, in reading order: **lane glyph + word**, **risk** (mono, ember-tinted), **confidence meter**, then the person, then the mini spine, then the headline sentence, then context. Risk and confidence sit side by side at the same visual weight — a person scanning cannot take one without the other, which is the point.

The context line carries whatever is most load-bearing for *this* row: an imminent departure, an immature baseline, a campaign membership. It is a different fact per row, chosen by the same precedence the engine uses, not a fixed field.

### 5.2 Incident detail — `/incidents/{id}`

The main working surface. One reading column at 72ch for prose, full width for instruments.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  ← Queue                                            INC-20100814-AAF0535-01     │
│                                                                                 │
│  First removable-media use in 8 months                                          │
│  5 correlated signals across 3 categories                                       │
│                                                                                 │
│  ■ Auto-flag        Risk 73        Confidence 0.88                              │
│                     ▓▓▓▓▓▓▓░░░     ▓▓▓▓▓▓▓▓░░                                  │
│                     alert at 40    auto-flag at 0.65                            │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   Aaron A. Fields (Engineer, Research) acted between 21:47 and 22:31 on         │
│   14 August 2010, progressing from off-hours access through removable-media     │
│   staging to file collection and an external upload. File activity was 6.2×     │
│   this user's 30-day norm and 4.1× the norm for their role. The user's          │
│   departure is recorded 11 days later.                        ← Source Serif    │
│                                                                                 │
├────────────────────────────────────────────────────────────────────────────────┤
│  The chain                                                                      │
│                                                                                 │
│  CONTEXT   RECON   STAGING      COLLECTION     EXFILTRATION    EVASION          │
│     ·————————·———————●═════════════●══════════════●———————————————○             │
│                      │             │              │                             │
│                   21:47         22:04          22:31                            │
│                   ▲ logon       ▲ file ×47      ▲ http upload                   │
│                   ▲ 21:59 usb                                                   │
│                                                                                 │
│  [ ▶ Replay the day ]                                    ●——●  12 min gap       │
├────────────────────────────────────────────────────────────────────────────────┤
│  Correlation graph                        [ time ] [ force ]   61 nodes          │
│                                                                                 │
│      ◆logon ──12m── ⬟usb ──5m── ●file ●file ●file ──27m── ▲upload               │
│       ░░              ▓▓          ▓▓▓  ▓▓▓  ▓▓▓             ███                  │
│                                                                                 │
│   shape = source · fill = risk contribution · edge = elapsed time               │
├────────────────────────────────────────────────────────────────────────────────┤
│  Evidence                                          contributions overlap;       │
│                                                    they do not sum to 73        │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ EXFIL   copied 47 files while removable media was connected      +18.4 ▓ │  │
│  │         file_events_during_usb  observed 47 · threshold 10 · z 5.8       │  │
│  │         without this signal, risk would be 54.8            ✓ minimal set  │  │
│  ├──────────────────────────────────────────────────────────────────────────┤  │
│  │ STAGE   first removable-media connection in 243 days             +14.1 ▓ │  │
│  │         without this signal, risk would be 59.1            ✓ minimal set  │  │
│  ├──────────────────────────────────────────────────────────────────────────┤  │
│  │ ML      99.1st percentile within Engineer/Research (n=46)         +9.6 ▒ │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  Two of these five signals are enough on their own to clear the threshold.      │
├────────────────────────────────────────────────────────────────────────────────┤
│  Record a verdict                                                               │
│  ( ) Confirmed threat   ( ) Benign   ( ) Inconclusive                           │
│  [ note                                                            ]            │
│                                                       [ Save verdict ]          │
└────────────────────────────────────────────────────────────────────────────────┘
```

Four decisions worth naming:

- **The narrative sits above the instruments.** The finding is read first; the evidence is there to check it, not to be assembled by the reader.
- **Thresholds are drawn on the meters**, not stated elsewhere. "73 against an alert threshold of 40" is a different fact from "73".
- **Counterfactuals are written as sentences** — "without this signal, risk would be 54.8" — because a number in a column labelled Δ gets skipped.
- **The overlap caveat is placed where the numbers are**, not in a footnote. Contributions genuinely do not sum, and hiding that would be the kind of small dishonesty that costs an analyst's trust the first time they add them up.

### 5.3 User profile — `/users/{id}`

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  Aaron A. Fields            AAF0535                                             │
│  Engineer, Research · reports to BKL0022 · 46 in cohort · departing 25 Aug      │
│                                                                                 │
│  Risk over time                                    [ 30d ] [ 90d ] [ all ]      │
│  100 ┤                                                                          │
│      │                                                    ╱╲                    │
│   50 ┤                                            ╱╲    ╱   ╲                   │
│      │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░╱░░╲░░╱░░░░░╲░  ← cohort p90   │
│    0 ┼────────────────────────────────────────────────────────────              │
│       15 Jul            1 Aug              14 Aug                               │
│                                                                                 │
│  Working window, learned: 08:18 – 18:06     ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░               │
│                                                                                 │
│  Incidents (3)          Campaign CMP-AAF0535-001 spans 13 days                  │
└────────────────────────────────────────────────────────────────────────────────┘
```

The shaded band is the cohort's p50–p90 for the same dates. A line without it is unreadable — 40 means nothing until you know the peers sat at 8. The learned working window is shown explicitly, because "off-hours" being personalised rather than hard-coded is a claim the interface should let an analyst verify rather than take on faith.

### 5.4 Detection health — `/detection/health`

For Anjali. Alert volume over time, lane mix, the calibration plot (stated confidence against observed precision, with the diagonal drawn), and the rule table sorted by weight drift. The rule table is the screen's real content: `rule_id · fires · reviewed · observed precision · configured weight · measured log-odds · drift`, with drift outside tolerance marked by glyph and value.

---

## 6. Component tree

```
App
├── AppShell                       nav, theme toggle, command palette (⌘K)
├── QueuePage
│   ├── QueueHeader                lane counts as text, not tiles
│   ├── FilterBar                  one row, above content
│   └── IncidentRow[]
│       ├── LaneChip               glyph + word + color
│       ├── RiskValue              mono, ember-tinted
│       ├── ConfidenceMeter        bar + threshold tick
│       └── ChainSpine  size=sm
├── IncidentPage
│   ├── IncidentHeader
│   │   ├── LaneChip
│   │   └── ScoreMeter ×2          risk, confidence — with thresholds drawn
│   ├── NarrativePanel             Source Serif, 68ch
│   ├── ChainSpine      size=lg    + event pins + ReplayControl
│   ├── CorrelationGraph           react-force-graph, two layout modes
│   ├── EvidenceList
│   │   └── SignalCard[]           phrase, detail, counterfactual, minimal-set mark
│   └── VerdictForm                + SuppressionProposal (conditional)
├── UserPage
│   ├── UserHeader
│   ├── RiskTrendChart             line + cohort band
│   ├── WorkingWindowBar
│   └── IncidentList
├── DetectionHealthPage
│   ├── AlertVolumeChart
│   ├── LaneMixBar
│   ├── CalibrationPlot
│   └── RuleTable
└── shared/
    ├── ChainSpine   sm | lg | campaign
    ├── ScoreMeter
    ├── DataTable        sortable, keyboard-navigable, CSV export
    ├── Tooltip
    ├── EmptyState
    └── ErrorState
```

`ChainSpine` at three scales is the reuse that makes the product cohere. It is one component with one data contract: an array of stages, each present or absent, each with an optional timestamp and event list.

---

## 7. Charts

Each follows the viz method: form chosen by the data's job, color assigned by role, palette validated, hover shipped by default.

| Chart | Form | Why that form | Color job |
|---|---|---|---|
| Risk over time | Line, one series + cohort band | Change over time for one entity | None — single series needs no key; the ember tint carries magnitude at the peak only |
| Cohort band | Shaded area p50–p90 | Comparison context, recessive by construction | Muted ink at 12% |
| Alert volume | Bar, one series | Magnitude per day | Sequential ember |
| Lane mix | Single stacked bar | Parts of one whole, four parts | Status palette, 2px surface gap between segments |
| Calibration | Scatter + reference diagonal | Two continuous measures, agreement is the question | Sequential by bin count |
| Kill-chain spine | Custom SVG rail | Ordered stages with presence/absence — no standard form fits, and inventing one here is justified because it is the product thesis | Blue ordinal ramp |
| Correlation graph | Force / temporal graph | Relationships are the data | **Fill = ember risk; shape = source; edge dash = type** |
| Confidence | Horizontal meter with threshold tick | One value against one threshold | Neutral fill, status-colored tick |

### 7.1 The graph encodes source by shape, not hue

A force graph puts every pair of nodes potentially adjacent, so it needs all-pairs colour separation. Five source hues cannot clear the all-pairs floors — only the first three slots do (validated: worst all-pairs CVD ΔE 8.4, normal-vision 19.8).

Rather than cut to three sources or accept an unsafe palette, source moves to **shape**: circle `file`, diamond `logon`, hexagon `device`, triangle `http`, square `email`. Colour is then freed for the thing an analyst actually scans a graph for — **where the risk is** — on the ember sequential ramp.

This is a better chart for having been forced: the first question at a graph is never "which log file produced this node".

### 7.2 Why the gauge became a meter

The pitch deck specifies a traffic-light gauge for confidence. Built as specified it would have two problems: a radial gauge spends a large area to show one number and reads imprecisely near the ends, and a green/amber/red scale encodes by hue alone.

The replacement keeps the intent — *see at a glance whether this is sure enough to act on* — as a **horizontal meter with the auto-flag threshold drawn on it as a tick**. The threshold is the actual question, and a linear meter against a marked threshold answers it faster and more precisely than an arc. The lane chip beside it carries the categorical judgement with a glyph and a word.

Flagged explicitly here because it is a visible departure from slide 6 of the deck, and it should be a decision, not a surprise.

### 7.3 Interaction rules

- Crosshair and tooltip on every line and area chart; per-mark tooltip on bars, dots, cells, and graph nodes. Hit targets exceed the mark.
- Filters in one row above the content, never in a sidebar.
- Graph: hovering a node highlights its edges and the matching row in the evidence list; clicking pins it. Selection is shared state across spine, graph, and evidence list — the three views are one object seen three ways.
- Timeline replay is the one piece of non-user-triggered motion in the product, and it is explicitly user-started. Events appear in sequence with the risk meter climbing; scrubbable; `prefers-reduced-motion` renders the final state with a step-through control instead of animating.

---

## 8. Motion

One orchestrated moment: the replay. Everything else responds to an action and shows what changed.

| Interaction | Motion |
|---|---|
| Route change | None. Content replaces content |
| Expanding a signal card | Height transition, 160 ms, `ease-out` |
| Graph node selection | Edge highlight 120 ms; no layout reflow |
| Verdict saved | Row state changes in place with a 200 ms tint, then settles. No toast that slides in from a corner |
| Replay | User-started, scrubbable, reduced-motion honoured |

No fade-and-slide-up on section entry. No hover lift on rows. A row that moves when the pointer passes over it costs attention and returns nothing.

---

## 9. Accessibility

| Requirement | How |
|---|---|
| Colour never carries meaning alone | Lane = glyph + word + colour; source = shape + label; risk = number + fill |
| CVD safety | Palette validated under protan and deutan simulation; ordering chosen from passing candidates |
| Contrast | All dark-mode marks ≥ 3:1 on `#151B1E`. Light-mode aqua, yellow and magenta fall below 3:1, so those charts ship direct labels or a table view — mandatory, per the validator's relief rule |
| Table view | Every chart has a "View as table" affordance producing a keyboard-navigable, screen-reader-legible table |
| Keyboard | Full traversal. `j`/`k` move through the queue, `Enter` opens, `c`/`b`/`i` record a verdict, `⌘K` opens the command palette. Focus is visibly ringed everywhere |
| Motion | `prefers-reduced-motion` disables replay animation and all transitions |
| Screen readers | The narrative is real prose in the DOM, not an image or a canvas label — the single most valuable accessibility property of a template-generated explanation |
| Texture channel | 45°/135° line fills available for print and `forced-colors` |

---

## 10. Words

The interface's vocabulary is fixed and shared with the API, so a term means one thing everywhere.

| Use | Not |
|---|---|
| Auto-flag, Review, Monitor, Suppressed | High / Medium / Low |
| Risk, Confidence | Score, Certainty, Severity |
| Signal | Alert, Indicator, Hit |
| Incident, Campaign | Case, Cluster, Group |
| Record a verdict | Submit, Triage this |
| Confirmed threat / Benign / Inconclusive | True positive / False positive |

"Confirmed threat" rather than "true positive" is deliberate: an analyst is judging a person's behaviour, not scoring a model. The model's accounting is a consequence of their judgement, not its purpose.

**Empty and error states point somewhere.**

- Empty queue: "No open incidents in this window. 902 user-days were scored and stayed below the alert threshold." — then a link to widen the range. The count matters; a blank screen in a detection tool is ambiguous between "nothing happened" and "nothing ran".
- Immature baseline: "This user has 9 days of history. Self-baseline rules are suppressed until 14; peer comparison is active and confidence is capped at 0.60."
- Pipeline running: "Detection is running. Scores shown are from the previous run, finished 2 hours ago." — never a spinner over stale data with no explanation.
- Failed load: "Could not load the correlation graph. The incident and its evidence are shown above." — name what still works.

---

## 11. Implementation notes

- **Types are generated** from the OpenAPI schema (`05-API-SPEC` section 10). No hand-written response interfaces.
- **Tokens live in CSS custom properties** on a `.viz-root` scope, with dark values declared under both `@media (prefers-color-scheme: dark)` and `[data-theme="dark"]`, so the toggle wins in both directions.
- **Data fetching:** TanStack Query. The queue prefetches the top 10 incident details on idle, which is what makes the 90-second triage target reachable.
- **The graph is computed server-side.** The client receives nodes and edges and renders; it never runs component detection. A graph of 400 nodes renders in under 2s because there is no computation in the render path.
- **Virtualised queue rows** — 1,000+ incidents scroll without pagination.
- **No chart library for the spine.** It is ~120 lines of SVG and needs to be exact.
