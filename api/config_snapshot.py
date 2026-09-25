"""Read-only view of config/*.yaml for the API layer.

Track A's engine/core/config.py is the canonical merger + validator + hash for
the detection engine; Track B does not import engine/ (architecture P1), so
this is an independent, much smaller reader used only to answer `GET /rules`
and to report a config_version on `GET /health` before any pipeline run has
written one to config_versions. Once a real ingest run exists, config_version
on /health switches to the value stamped on the latest run.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=1)
def load_rules() -> list[dict[str, Any]]:
    path = CONFIG_DIR / "rules.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc["rules"]


@lru_cache(maxsize=1)
def config_version() -> str:
    """sha256 over the sorted bytes of every config/*.yaml file, matching the
    "sha256:<hex>" shape used throughout docs/05-API-SPEC.md."""
    digest = hashlib.sha256()
    for path in sorted(CONFIG_DIR.glob("*.yaml")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def get_rule(rule_id: str) -> dict[str, Any] | None:
    for rule in load_rules():
        if rule["id"] == rule_id:
            return rule
    return None


@lru_cache(maxsize=1)
def load_detection_config() -> dict[str, Any]:
    path = CONFIG_DIR / "detection.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))
