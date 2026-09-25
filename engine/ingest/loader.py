"""Ingestion: raw CERT-schema CSV -> canonical event frame.

The bulk path is vectorised (column operations over whole chunks) because the
target corpus is ~32M rows and NFR-1 caps a full run at 15 minutes. A row-wise
Python loop costs roughly 70us/row, which alone would blow that budget.

The adapter still exposes a row-wise `iter_events()` yielding `Event` objects,
derived from the same vectorised transform, so the streaming path and the batch
path cannot diverge.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from engine.core.config import Config
from engine.core.models import Event

CERT_TS = "%m/%d/%Y %H:%M:%S"
INTERNAL_DOMAIN = "dtaa.com"


@dataclass
class IngestReport:
    rows_read: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    duplicates_skipped: int = 0
    per_source: dict[str, int] = field(default_factory=dict)
    reject_samples: list[dict[str, Any]] = field(default_factory=list)
    ts_min: datetime | None = None
    ts_max: datetime | None = None

    def note_reject(self, reason: str, count: int, sample: Any = None) -> None:
        self.rows_rejected += count
        if count and len(self.reject_samples) < 20:
            self.reject_samples.append(
                {"reason": reason, "count": int(count), "raw": str(sample)[:200]}
            )

    def summary(self) -> str:
        lines = [
            f"  read      {self.rows_read:>9,}",
            f"  accepted  {self.rows_accepted:>9,}",
            f"  rejected  {self.rows_rejected:>9,}",
            f"  duplicate {self.duplicates_skipped:>9,}",
        ]
        for src, n in sorted(self.per_source.items()):
            lines.append(f"    {src:<8} {n:>9,}")
        if self.ts_min and self.ts_max:
            lines.append(f"  range     {self.ts_min.date()} .. {self.ts_max.date()}")
        for s in self.reject_samples:
            lines.append(f"  reject    {s['reason']} x{s['count']}")
        return "\n".join(lines)


def _hash_ids(payload: pd.Series) -> pd.Series:
    """Content-addressed event ids (FR-1.4)."""
    return payload.map(
        lambda s: hashlib.blake2b(s.encode("utf-8"), digest_size=8).hexdigest()
    )


class DomainClassifier:
    """URL -> host -> category. Data-driven, from config."""

    def __init__(self, cfg: Config) -> None:
        self._exact: dict[str, str] = {}
        self._suffix: list[tuple[str, str]] = []
        for category, entries in (cfg.domains.get("categories") or {}).items():
            for entry in entries:
                host = entry.split("/")[0].lower()
                self._exact[host] = category
                self._suffix.append((host, category))
        self._upload_markers = [
            m.lower() for m in cfg.domains.get("upload_path_markers", [])
        ]

    def categorise(self, hosts: pd.Series) -> pd.Series:
        out = hosts.map(self._exact).fillna("")
        unresolved = out == ""
        if unresolved.any() and self._suffix:
            def by_suffix(host: str) -> str:
                for suffix, category in self._suffix:
                    if host.endswith("." + suffix):
                        return category
                return "neutral"
            out.loc[unresolved] = hosts[unresolved].map(by_suffix)
        return out.replace("", "neutral")

    def upload_flag(self, urls: pd.Series) -> pd.Series:
        low = urls.str.lower()
        flag = pd.Series(False, index=urls.index)
        for marker in self._upload_markers:
            flag |= low.str.contains(marker, regex=False, na=False)
        return flag


class CertAdapter:
    """Adapter for the CERT r4.2 schema (and the synthetic stand-in)."""

    id = "cert_r42"
    FILES = {
        "logon": "logon.csv", "device": "device.csv", "file": "file.csv",
        "http": "http.csv", "email": "email.csv",
    }

    # Boolean/numeric attrs that only one source populates. Left sparse, these
    # come back NaN for every other source's rows once every chunk is
    # concatenated into one frame - and pandas cannot hold NaN in a bool or
    # int64 column, so it silently upcasts the whole 32M-row column to
    # `object` (a ~28x memory blowup per column) to make room for it. That is
    # exactly what exhausted memory on the full corpus (NFR-4, 4 GB): the
    # union-of-sparse-columns concat needed one more allocation than the
    # machine had headroom for. `_densify` gives every chunk the full,
    # correctly-typed attr schema *before* concat so no column is ever forced
    # to widen.
    ATTR_DEFAULTS: dict[str, tuple[str, Any]] = {
        "a_removable": ("bool", False),
        "a_sensitive": ("bool", False),
        "a_on_removable": ("bool", False),
        "a_upload_shaped": ("bool", False),
        "a_self_send": ("bool", False),
        "a_recipient_count": ("int32", 0),
        "a_external_count": ("int32", 0),
        "a_bcc_external_count": ("int32", 0),
        "a_size": ("int64", 0),
        "a_attachments": ("int32", 0),
        "a_attachment_bytes_external": ("int64", 0),
    }

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.domains = DomainClassifier(cfg)
        self._personal = set(cfg.domains.get("personal_email_domains", []))
        self._sensitive = set(cfg.features.get("sensitive_extensions", []))

    # -- vectorised per-source transforms ---------------------------------
    def _base(self, chunk: pd.DataFrame, source: str,
              report: IngestReport) -> pd.DataFrame:
        report.rows_read += len(chunk)
        ts = pd.to_datetime(chunk["date"], format=CERT_TS, errors="coerce")
        bad = ts.isna()
        if bad.any():
            report.note_reject("unparseable_date", int(bad.sum()),
                               chunk.loc[bad, "date"].iloc[0])
        user = chunk.get("user", pd.Series("", index=chunk.index)).astype(str).str.strip()
        missing = user.eq("") | user.eq("nan")
        if missing.any():
            report.note_reject("missing_user", int(missing.sum()))
        keep = ~bad & ~missing

        out = pd.DataFrame(index=chunk.index[keep])
        out["user_id"] = user[keep]
        out["ts"] = ts[keep]
        out["source"] = source
        out["pc_id"] = chunk.get("pc", pd.Series("", index=chunk.index))[keep].astype(str)
        raw_id = chunk.get("id", pd.Series("", index=chunk.index))[keep].astype(str)
        # Epoch nanoseconds rather than a formatted string: strftime over a
        # column costs ~20x more and this payload is never read back.
        out["event_id"] = _hash_ids(
            source + "|" + raw_id + "|" + out["user_id"] + "|"
            + out["ts"].astype("int64").astype(str)
        )
        return out

    def transform(self, chunk: pd.DataFrame, source: str,
                  report: IngestReport) -> pd.DataFrame:
        out = self._base(chunk, source, report)
        if out.empty:
            return out
        keep = out.index
        sub = chunk.loc[keep]

        if source in ("logon", "device"):
            out["action"] = sub["activity"].astype(str).str.lower()
            if source == "device":
                out["a_removable"] = True

        elif source == "file":
            name = sub["filename"].astype(str)
            ext = name.str.rsplit(".", n=1).str[-1].str.lower()
            ext = ext.where(name.str.contains(".", regex=False), "")
            out["action"] = "open"
            out["a_extension"] = ext
            out["a_sensitive"] = ext.isin(self._sensitive)
            if "to_removable_media" in sub.columns:
                out["a_on_removable"] = (
                    sub["to_removable_media"].astype(str).str.strip().str.lower()
                    .isin({"true", "1", "yes"})
                )
            else:
                # Real CERT r4.2 file.csv carries no such column: per its
                # readme, every row it records already IS a copy to
                # removable media, so the flag is unconditionally true
                # rather than silently absent (docs/08 FR: on_removable is
                # required_for exfil.file_copy_to_usb).
                out["a_on_removable"] = True

        elif source == "http":
            url = sub["url"].astype(str)
            host = (url.str.replace(r"^\w+://", "", regex=True)
                       .str.split("/").str[0].str.split(":").str[0].str.lower())
            upload = self.domains.upload_flag(url)
            out["a_domain"] = host
            out["a_category"] = self.domains.categorise(host)
            out["a_upload_shaped"] = upload
            out["action"] = upload.map({True: "upload", False: "visit"})

        elif source == "email":
            def addr_count(col: str) -> pd.Series:
                s = sub.get(col, pd.Series("", index=keep)).astype(str).fillna("")
                s = s.replace("nan", "")
                return s.str.count(";").add(1).where(s.str.len() > 0, 0)

            def external_count(col: str) -> pd.Series:
                s = sub.get(col, pd.Series("", index=keep)).astype(str).replace("nan", "")
                total = s.str.count(";").add(1).where(s.str.len() > 0, 0)
                internal = s.str.lower().str.count("@" + INTERNAL_DOMAIN.replace(".", r"\."))
                return (total - internal).clip(lower=0)

            recips = addr_count("to") + addr_count("cc") + addr_count("bcc")
            ext = external_count("to") + external_count("cc") + external_count("bcc")
            size = pd.to_numeric(sub.get("size"), errors="coerce").fillna(0).astype("int64")
            atts = pd.to_numeric(sub.get("attachments"), errors="coerce").fillna(0).astype("int64")

            joined = (sub.get("to", "").astype(str) + ";"
                      + sub.get("cc", "").astype(str) + ";"
                      + sub.get("bcc", "").astype(str)).str.lower()
            personal = pd.Series(False, index=keep)
            for dom in self._personal:
                personal |= joined.str.contains("@" + dom, regex=False, na=False)
            # A self-send is a personal-domain recipient whose local part carries
            # the user's own id.
            local = out["user_id"].str.lower()
            names_itself = pd.Series(
                [loc in j for loc, j in zip(local, joined)], index=keep
            )
            self_send = personal & names_itself

            out["action"] = "send"
            out["a_recipient_count"] = recips
            out["a_external_count"] = ext
            out["a_bcc_external_count"] = external_count("bcc")
            out["a_self_send"] = self_send
            out["a_size"] = size
            out["a_attachments"] = atts
            out["a_attachment_bytes_external"] = size.where((ext > 0) & (atts > 0), 0)

        return out

    def read_frames(self, raw_dir: Path, report: IngestReport,
                    chunk_size: int = 500_000) -> Iterator[pd.DataFrame]:
        for source, filename in self.FILES.items():
            path = raw_dir / filename
            if not path.exists():
                continue
            for chunk in pd.read_csv(path, chunksize=chunk_size, dtype=str,
                                     keep_default_na=False):
                frame = self.transform(chunk, source, report)
                if not frame.empty:
                    report.rows_accepted += len(frame)
                    report.per_source[source] = (
                        report.per_source.get(source, 0) + len(frame))
                    lo, hi = frame["ts"].min(), frame["ts"].max()
                    report.ts_min = lo if report.ts_min is None else min(report.ts_min, lo)
                    report.ts_max = hi if report.ts_max is None else max(report.ts_max, hi)
                    yield frame

    def iter_events(self, raw_dir: Path, report: IngestReport) -> Iterator[Event]:
        """Row-wise view over the same transform, for the streaming path."""
        for frame in self.read_frames(raw_dir, report):
            attr_cols = [c for c in frame.columns if c.startswith("a_")]
            for row in frame.to_dict("records"):
                yield Event(
                    event_id=row["event_id"], user_id=row["user_id"], ts=row["ts"],
                    source=row["source"], action=row["action"],
                    pc_id=row["pc_id"] or None,
                    attrs={c[2:]: row[c] for c in attr_cols
                           if row.get(c) is not None and row.get(c) == row.get(c)},
                )


def _densify(frame: pd.DataFrame) -> pd.DataFrame:
    """Fill in every source-sparse attr column so concat never upcasts one.

    Only used on the bulk (`load_events`) path - `iter_events` shares the same
    per-chunk `transform()` output but must keep it sparse, since `Event.attrs`
    is documented as schemaless-per-source, not a dense union of every
    source's fields.
    """
    for col, (dtype, default) in CertAdapter.ATTR_DEFAULTS.items():
        if col in frame.columns:
            frame[col] = frame[col].fillna(default).astype(dtype)
        else:
            frame[col] = pd.Series(default, index=frame.index, dtype=dtype)
    return frame


def load_events(raw_dir: Path, cfg: Config) -> tuple[pd.DataFrame, IngestReport]:
    """Read every source into one tidy events frame."""
    report = IngestReport()
    adapter = CertAdapter(cfg)
    frames = [_densify(f) for f in adapter.read_frames(raw_dir, report)]
    if not frames:
        return pd.DataFrame(), report

    df = pd.concat(frames, ignore_index=True)
    del frames

    before = len(df)
    df = df.drop_duplicates(subset="event_id", keep="first")
    report.duplicates_skipped += before - len(df)
    report.rows_accepted -= before - len(df)

    df["date"] = df["ts"].dt.normalize()
    df = df.sort_values(["user_id", "ts"], kind="stable").reset_index(drop=True)

    # Small-cardinality string columns: safe to compact now that concat has
    # already succeeded (no forced-upcast risk left at this point).
    for col in ("source", "action", "pc_id", "user_id", "a_domain", "a_category",
                "a_extension"):
        if col in df.columns:
            df[col] = df[col].astype("category")

    return df, report


def load_org(raw_dir: Path) -> pd.DataFrame:
    """Build the user org table from LDAP snapshots, with departure dates.

    A user present in one snapshot and absent from a later one has departed.
    That requires snapshots to continue past the activity window - if the
    directory stops when the logs stop, departures are unobservable.
    """
    ldap_dir = raw_dir / "LDAP"
    cols = ["user_id", "employee_name", "email", "role", "department",
            "cohort_key", "departure_date"]
    if not ldap_dir.is_dir():
        return pd.DataFrame(columns=cols)

    frames = []
    for path in sorted(ldap_dir.glob("*.csv")):
        frame = pd.read_csv(path, dtype=str)
        frame["snapshot"] = pd.to_datetime(path.stem + "-01")
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=cols)

    everything = pd.concat(frames, ignore_index=True)
    final_snapshot = everything["snapshot"].max()

    latest = (everything.sort_values("snapshot")
              .groupby("user_id", as_index=False).last())
    last_seen = everything.groupby("user_id")["snapshot"].max()
    latest["last_snapshot"] = latest["user_id"].map(last_seen)

    departed = latest["last_snapshot"] < final_snapshot
    latest["departure_date"] = (
        latest["last_snapshot"] + pd.offsets.MonthEnd(1)).where(departed)
    latest["cohort_key"] = (latest["role"].fillna("?") + "|"
                            + latest["department"].fillna("?"))
    return latest[cols]
