# ADR 0006 — Peer-group baselines alongside self-baselines

**Status:** Accepted · **Date:** 2026-09-24

## Context

The standard approach to behavioural detection is a self-baseline: compare a person to their own recent history and flag the deviation. It is intuitive and it works for the classic case — a person who never used a USB stick suddenly uses one.

It has two failure modes that generate most of the false positives in deployed systems.

**The always-unusual user.** A sysadmin touches many machines at odd hours every week. Their self-baseline absorbs that, so genuinely abnormal behaviour has to be extreme before it registers. Meanwhile a 9-to-5 analyst touching a second machine trips the same rule at a far lower bar. The system is simultaneously blind to one group and noisy about another.

**Organisation-wide shifts.** A quarter-end deadline, a holiday week, a company-wide migration. Everyone's behaviour moves at once, every self-baseline is violated at once, and the queue fills with false positives on the day when analyst attention is scarcest.

There is also a slower failure: an insider who ramps gradually trains their own baseline as they go. The self-baseline learns the attack.

## Decision

Compute and store **both** baselines for every baselined feature, and emit both z-scores.

```
z_self(f) = (f − median₃₀d(f))       / (1.4826 · MAD₃₀d(f) + ε)
z_peer(f) = (f − median_cohort(f))   / (1.4826 · MAD_cohort(f) + ε)
```

- **Cohort** is `(role, department)` on the event date, from the LDAP interval table — so a mid-period transfer moves the person into the right cohort rather than comparing them to a team they left.
- Cohorts below 30 members fall back to department, then to global.
- Rules may require either, or both: `access.file_breadth` requires `z_self ≥ 3.5` **and** `z_peer ≥ 2`, which is precisely the conjunction that kills the always-unusual-user false positive.
- **Median and MAD, not mean and standard deviation.** A single large insider day inside a trailing 30-day window inflates a standard deviation enough to hide the next one. MAD resists that — it is a small change with a large effect on exactly the attack pattern we care about.
- Cohort membership uses **role and department only**. Never a demographic or protected attribute (`01-PRD` section 9.5).

## Alternatives considered

**Self-baseline only.** Standard, cheaper, one fewer join. Rejected on the two failure modes above — they are not edge cases, they are the bulk of real false positives.

**Peer-baseline only.** Fails the classic case entirely: a person whose behaviour changes dramatically but stays within their cohort's range is invisible, and that is the core insider pattern.

**Clustered behavioural cohorts** (k-means over feature vectors instead of org structure). More adaptive, and it would group people by what they actually do rather than what their job title says. Rejected for v1: cluster membership is unstable across refits, which makes explanations unstable — "you were flagged relative to cluster 7" is not something you can put in front of a person, where "relative to Engineers in Research" is. Worth revisiting as a supplementary signal, not a replacement.

## Consequences

**Good.** Rules can require both conditions, which is the cleanest available false-positive control. Organisation-wide shifts cancel out — everyone's peer baseline moves together. Cold-start users get a usable comparison from day one, before a self-baseline exists. The explanation improves materially: "6.2× this user's own norm and 4.1× the norm for their role" is a far stronger sentence than either half alone, and it is what an investigator needs to answer "is this person actually unusual, or is this just how their job looks".

**Costs.** Doubles baseline computation and storage. Requires accurate, time-aware org data — a stale LDAP snapshot produces wrong cohorts silently, so cohort size is surfaced in the UI and in the API response. Small cohorts are statistically weak; the fallback chain handles it but the resulting baseline is weaker, and `07-EVALUATION` section 9.7 lists this as a known limitation rather than hiding it.
