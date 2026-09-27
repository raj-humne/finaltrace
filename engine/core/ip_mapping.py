"""Synthetic pc_id -> IP address mapping.

The CERT insider-threat dataset this engine scores has no network telemetry
at all - events carry a workstation hostname (`pc_id`, e.g. "PC-4821"), never
an IP address. A mitigation/remediation pipeline still needs something that
looks like a flagged IP to put in an isolation payload, so this module
deterministically derives one from the hostname: the same `pc_id` always
maps to the same address, both within one run and across re-runs, without
inventing a new identity space or touching ingestion.

This is explicitly a stand-in, not real telemetry - callers/consumers of the
mapped value must not treat it as ground truth about actual network
activity.
"""
from __future__ import annotations

import hashlib


def pc_to_ip(pc_id: str | None) -> str | None:
    """Hash `pc_id` into a stable-looking private (10.x.x.x) address, or
    None if there is no workstation to map."""
    if not pc_id:
        return None
    digest = hashlib.sha256(pc_id.encode("utf-8")).digest()
    return f"10.{digest[0]}.{digest[1]}.{digest[2]}"
