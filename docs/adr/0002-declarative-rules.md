# ADR 0002 — Rules as declarative YAML, not Python predicates

**Status:** Accepted · **Date:** 2026-09-24

## Context

The rule catalogue is the part of the system most likely to change, and the part most likely to be changed by someone who is not the person who wrote the engine. Detection engineers tune thresholds weekly. Analysts propose rules from incidents they have worked.

If a rule is a Python function, every tuning change is a code change: a branch, a review, a deploy, and a test suite the proposer may not know how to run. That friction is the reason detection rules go stale in practice.

There is also an auditability requirement. `01-PRD` section 9.3 commits to showing a flagged person the exact signals, weights, and thresholds behind their score. That is straightforward when a rule is data and awkward when it is code.

## Decision

Rules live in `config/rules.yaml` and are evaluated by a small interpreter over a closed operator set (`gte`, `lt`, `in`, `is_true`, `z_self_gte`, `z_peer_gte`, `and`, `or`, `not`) and four strength scales (`linear`, `log`, `step`, `binary`).

Rule configuration is hashed into `config_version`, which is stored on every signal and score. Any historical score is reproducible from its configuration.

There is **no expression language and no `eval`**. An operator that does not exist is a feature request against the interpreter, not an escape hatch.

## Alternatives considered

**Python predicate functions in a registry.** Maximum expressiveness, and the easiest thing to build. Rejected: it puts tuning behind a deploy, makes the "show the subject their thresholds" commitment awkward, and lets arbitrary code into the hot path of a system that processes untrusted log content.

**A full expression DSL (CEL, JSONLogic, a small parser).** Tempting, and would cover the cases the closed operator set does not. Rejected for v1 on two grounds: it re-opens the code-injection surface, and it makes rules unreviewable by non-programmers, which defeats the purpose. Revisit if the operator set proves genuinely insufficient — the current 27 rules did not need it.

**Sigma rule format.** Real standard, real ecosystem. Rejected because Sigma is built for log-line pattern matching, and our rules operate over *aggregated per-user-day features with baselines*. Forcing our semantics into Sigma would be a worse fit than a purpose-built 40-line schema.

## Consequences

**Good.** Tuning needs no Python. Rules are diffable, reviewable, and directly renderable in the UI and in an evidence pack. Test fixtures are generated from the catalogue, so a rule added without tests fails CI. The interpreter is small enough to be obviously correct.

**Costs.** Expressiveness is capped; a genuinely novel rule shape requires an interpreter change. YAML has no type checking, so the loader must validate hard and fail loudly at startup. Errors surface at load time rather than at author time, which is mitigated by a `--validate-rules` command.

**Follow-on.** The same pattern extends to `adapters/*.yaml` (`08-ADAPTER-LAYER`), which uses an identical closed-transform approach for the same reasons.
