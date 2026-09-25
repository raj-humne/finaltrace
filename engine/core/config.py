"""Configuration loading and versioning.

Every score the engine produces carries the hash of the configuration that
produced it, so any historical score is reproducible (NFR-8).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILES = [
    "detection.yaml",
    "features.yaml",
    "correlation.yaml",
    "triage.yaml",
    "rules.yaml",
    "domain_categories.yaml",
]

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@dataclass(frozen=True)
class Config:
    """Merged, hashed configuration. Treated as immutable once loaded."""

    detection: dict[str, Any]
    features: dict[str, Any]
    correlation: dict[str, Any]
    triage: dict[str, Any]
    rules: list[dict[str, Any]]
    domains: dict[str, Any]
    version: str
    source_dir: Path = field(compare=False, default=DEFAULT_CONFIG_DIR)

    # -- convenience accessors -------------------------------------------------
    @property
    def scoring(self) -> dict[str, Any]:
        return self.detection["scoring"]

    @property
    def corr_bonus(self) -> dict[str, Any]:
        return self.detection["correlation_bonus"]

    @property
    def confidence(self) -> dict[str, Any]:
        return self.detection["confidence"]

    @property
    def anomaly(self) -> dict[str, Any]:
        return self.detection["anomaly"]

    @property
    def baseline(self) -> dict[str, Any]:
        return self.features["baseline"]

    @property
    def working_window(self) -> dict[str, Any]:
        return self.features["working_window"]

    def pair_window_min(self, source_a: str, source_b: str) -> float:
        """Per-pair correlation window; order-insensitive."""
        pairs = self.correlation.get("pair_windows", {})
        a, b = sorted((source_a, source_b))
        return float(pairs.get(f"{a}__{b}", self.correlation["default_window_min"]))


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def load_config(config_dir: str | Path | None = None) -> Config:
    """Load and merge every config file, then hash the result into a version."""
    cfg_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    if not cfg_dir.is_dir():
        raise FileNotFoundError(f"config directory not found: {cfg_dir}")

    raw: dict[str, Any] = {}
    for name in CONFIG_FILES:
        path = cfg_dir / name
        if not path.exists():
            raise FileNotFoundError(f"missing config file: {path}")
        with path.open("r", encoding="utf-8") as fh:
            raw[name] = yaml.safe_load(fh) or {}

    version = "sha256:" + hashlib.sha256(
        _canonical_json(raw).encode("utf-8")
    ).hexdigest()[:16]

    cfg = Config(
        detection=raw["detection.yaml"],
        features=raw["features.yaml"],
        correlation=raw["correlation.yaml"],
        triage=raw["triage.yaml"],
        rules=raw["rules.yaml"]["rules"],
        domains=raw["domain_categories.yaml"],
        version=version,
        source_dir=cfg_dir,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    """Fail loudly at load time rather than silently at detection time (ADR 0002)."""
    seen: set[str] = set()
    valid_ops = {
        "gte", "gt", "lte", "lt", "eq", "neq", "in", "is_true", "is_false",
        "z_self_gte", "z_peer_gte",
    }
    valid_scales = {"linear", "log", "step", "binary", "inverse_linear"}

    for rule in cfg.rules:
        rid = rule.get("id")
        if not rid:
            raise ValueError(f"rule without an id: {rule}")
        if rid in seen:
            raise ValueError(f"duplicate rule id: {rid}")
        seen.add(rid)

        for required in ("category", "stage", "weight", "when", "phrase"):
            if required not in rule:
                raise ValueError(f"rule {rid} is missing required field '{required}'")

        if not 0 <= int(rule["stage"]) <= 5:
            raise ValueError(f"rule {rid} has stage outside 0..5")
        if float(rule["weight"]) <= 0:
            raise ValueError(f"rule {rid} has a non-positive weight")

        for clause in rule["when"]:
            op = clause.get("op")
            if op not in valid_ops:
                raise ValueError(f"rule {rid} uses unknown operator '{op}'")
            if "feature" not in clause:
                raise ValueError(f"rule {rid} has a clause without a feature")

        scale = (rule.get("strength") or {}).get("scale", "binary")
        if scale not in valid_scales:
            raise ValueError(f"rule {rid} uses unknown strength scale '{scale}'")

    matrix = cfg.triage["matrix"]
    if matrix["high"]["low"] == "AUTO_FLAG":
        raise ValueError(
            "triage matrix violates FR-6.2: high risk with low confidence must "
            "never route to AUTO_FLAG"
        )
