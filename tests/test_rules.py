"""Generated positive/negative fixtures for every rule in config/rules.yaml.

ADR 0002: "test fixtures are generated from the catalogue, so a rule added
without tests fails CI." This module builds one satisfying and one
unsatisfying feature row per rule directly from its `when` clauses - nobody
has to hand-write a fixture when a 28th rule is added; it is covered the
moment it lands in the YAML.
"""
from __future__ import annotations

import pytest

from engine.core.config import load_config
from engine.detect.rules import rule_fires

CFG = load_config()


def _all_feature_keys() -> set[str]:
    keys = {"baseline_mature"}
    for rule in CFG.rules:
        for clause in rule["when"]:
            feature = clause.get("feature")
            if not feature:
                continue
            if clause["op"] == "z_self_gte":
                keys.add(f"{feature}__z_self")
            elif clause["op"] == "z_peer_gte":
                keys.add(f"{feature}__z_peer")
            else:
                keys.add(feature)
        strength = rule.get("strength") or {}
        if "feature" in strength:
            keys.add(strength["feature"])
    return keys


def _default_row() -> dict:
    row = {k: 0.0 for k in _all_feature_keys()}
    row["baseline_mature"] = True
    return row


def _satisfying_value(clause: dict) -> object:
    op, value = clause["op"], clause.get("value")
    if op in ("gte", "z_self_gte", "z_peer_gte"):
        return value
    if op == "gt":
        return value + 1
    if op == "lte":
        return value
    if op == "lt":
        return value - 1
    if op == "eq":
        return value
    if op == "neq":
        return value + 1 if isinstance(value, (int, float)) else "__other__"
    if op == "in":
        return value[0]
    if op == "is_true":
        return True
    if op == "is_false":
        return False
    raise AssertionError(f"no satisfying-value rule for op {op!r}")


def _failing_value(clause: dict) -> object:
    op, value = clause["op"], clause.get("value")
    if op in ("gte", "z_self_gte", "z_peer_gte"):
        return value - 1
    if op == "gt":
        return value
    if op == "lte":
        return value + 1
    if op == "lt":
        return value
    if op == "eq":
        return value + 1 if isinstance(value, (int, float)) else "__other__"
    if op == "neq":
        return value
    if op == "in":
        return "__not_in_list__"
    if op == "is_true":
        return False
    if op == "is_false":
        return True
    raise AssertionError(f"no failing-value rule for op {op!r}")


def _row_key(clause: dict) -> str:
    op, feature = clause["op"], clause["feature"]
    if op == "z_self_gte":
        return f"{feature}__z_self"
    if op == "z_peer_gte":
        return f"{feature}__z_peer"
    return feature


def _positive_fixture(rule: dict) -> dict:
    row = _default_row()
    for clause in rule["when"]:
        row[_row_key(clause)] = _satisfying_value(clause)
    return row


def _negative_fixture(rule: dict) -> dict:
    """Satisfy every clause except the last, which is forced to fail - proves
    the rule's clauses are genuinely AND'd rather than vacuously true."""
    row = _positive_fixture(rule)
    last = rule["when"][-1]
    row[_row_key(last)] = _failing_value(last)
    return row


RULE_IDS = [rule["id"] for rule in CFG.rules]


@pytest.mark.parametrize("rule", CFG.rules, ids=RULE_IDS)
def test_rule_fires_on_positive_fixture(rule):
    row = _positive_fixture(rule)
    assert rule_fires(row, rule) is True, (
        f"{rule['id']} did not fire on a fixture built to satisfy every clause: {row}")


@pytest.mark.parametrize("rule", CFG.rules, ids=RULE_IDS)
def test_rule_does_not_fire_on_negative_fixture(rule):
    row = _negative_fixture(rule)
    assert rule_fires(row, rule) is False, (
        f"{rule['id']} fired even though its last clause was forced to fail: {row}")


def test_requires_baseline_rule_suppressed_during_warmup():
    """A rule flagged requires_baseline must not fire while baseline_mature is
    False, even if every clause is otherwise satisfied (docs/04-DETECTION-
    ENGINE.md section 9 / docs/02-ARCHITECTURE.md section 9)."""
    rule = next(r for r in CFG.rules if r.get("requires_baseline"))
    row = _positive_fixture(rule)
    assert rule_fires(row, rule) is True   # sanity: fires when mature

    row["baseline_mature"] = False
    assert rule_fires(row, rule) is False


def test_rule_without_requires_baseline_still_fires_during_warmup():
    """The converse: a rule that does not require baseline maturity keeps
    firing during warm-up - peer-baseline and hard-evidence rules must not be
    silently suppressed too."""
    rule = next(r for r in CFG.rules if not r.get("requires_baseline"))
    row = _positive_fixture(rule)
    row["baseline_mature"] = False
    assert rule_fires(row, rule) is True


def test_every_rule_id_covered():
    assert len(RULE_IDS) == 27, (
        "docs/04-DETECTION-ENGINE.md section 3.2 promises a 27-rule catalogue; "
        f"config/rules.yaml has {len(RULE_IDS)}. Update this count if the "
        "catalogue is deliberately changed, not silently.")
