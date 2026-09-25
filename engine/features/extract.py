"""Per-user-per-day behavioural feature extraction.

Turns the canonical event frame into one row per (user, date) carrying the
features the rule catalogue reads. Cross-source interaction features - the
gaps between a logon, a USB insert, a file burst and an upload - are computed
here, and they are the ones a single-source detector cannot produce.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.core.config import Config

MINUTES_PER_DAY = 1440


# ---------------------------------------------------------------- sessions
def _pair_sessions(frame: pd.DataFrame, open_action: str,
                   close_action: str) -> pd.DataFrame:
    """Pair open/close events per (user, pc) into sessions.

    An unmatched open is closed at end-of-day and flagged `inferred_end`
    rather than dropped - a missing logoff is a data-quality fact, not a
    reason to lose the session (docs/03-DATA-MODEL.md section 7).
    """
    if frame.empty:
        return pd.DataFrame(columns=["user_id", "pc_id", "start", "end",
                                     "date", "inferred_end"])
    rows = []
    frame = frame.sort_values(["user_id", "pc_id", "ts"], kind="stable")
    for (user, pc), grp in frame.groupby(["user_id", "pc_id"], sort=False, observed=True):
        start = None
        for ts, action in zip(grp["ts"].to_numpy(), grp["action"].to_numpy()):
            if action == open_action:
                if start is not None:
                    rows.append((user, pc, start, _eod(start), True))
                start = ts
            elif action == close_action and start is not None:
                rows.append((user, pc, start, ts, False))
                start = None
        if start is not None:
            rows.append((user, pc, start, _eod(start), True))

    out = pd.DataFrame(rows, columns=["user_id", "pc_id", "start", "end",
                                      "inferred_end"])
    if out.empty:
        out["date"] = pd.Series(dtype="datetime64[ns]")
        return out
    out["date"] = pd.to_datetime(out["start"]).dt.normalize()
    out["duration_min"] = (
        (pd.to_datetime(out["end"]) - pd.to_datetime(out["start"]))
        .dt.total_seconds() / 60.0
    )
    return out


def _eod(ts) -> pd.Timestamp:
    return pd.Timestamp(ts).normalize() + pd.Timedelta(minutes=MINUTES_PER_DAY - 1)


def _interval_membership(event_ts: np.ndarray, starts: np.ndarray,
                         ends: np.ndarray) -> np.ndarray:
    """Vectorised 'is each timestamp inside any [start, end] interval'."""
    if len(event_ts) == 0 or len(starts) == 0:
        return np.zeros(len(event_ts), dtype=bool)
    order = np.argsort(starts)
    s, e = starts[order], ends[order]
    # Merge overlapping intervals so searchsorted logic stays valid.
    merged_s, merged_e = [s[0]], [e[0]]
    for i in range(1, len(s)):
        if s[i] <= merged_e[-1]:
            merged_e[-1] = max(merged_e[-1], e[i])
        else:
            merged_s.append(s[i])
            merged_e.append(e[i])
    ms, me = np.array(merged_s), np.array(merged_e)
    idx = np.searchsorted(ms, event_ts, side="right") - 1
    inside = np.zeros(len(event_ts), dtype=bool)
    valid = idx >= 0
    inside[valid] = event_ts[valid] <= me[idx[valid]]
    return inside


# ---------------------------------------------------------- working window
def learn_working_windows(events: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Per-user, per-week learned working window.

    Off-hours is the 5th-95th percentile of the user's own activity over a
    trailing window, not a hard-coded 18:00-06:00. A night-shift admin is not
    off-hours at 02:00; a 9-to-5 analyst is. Refreshed weekly because a
    behavioural rhythm does not move day to day.
    """
    ww = cfg.working_window
    lo_p, hi_p = ww["low_percentile"], ww["high_percentile"]
    lookback = pd.Timedelta(days=ww["lookback_days"])

    rows = []
    for user, grp in events.groupby("user_id", sort=False, observed=True):
        ts = grp["ts"].to_numpy()
        minutes = (grp["ts"].dt.hour * 60 + grp["ts"].dt.minute).to_numpy()
        order = np.argsort(ts)
        ts, minutes = ts[order], minutes[order]

        days = pd.to_datetime(grp["date"]).dt.normalize().unique()
        days = np.sort(days)
        if len(days) == 0:
            continue
        weeks = pd.to_datetime(pd.Series(days)).dt.to_period("W").unique()
        for week in weeks:
            anchor = week.start_time
            lo_bound = np.datetime64(anchor - lookback)
            hi_bound = np.datetime64(anchor)
            left = np.searchsorted(ts, lo_bound, side="left")
            right = np.searchsorted(ts, hi_bound, side="right")
            window = minutes[left:right]
            n_days = max(1, int((right - left) > 0) * len(
                np.unique(ts[left:right].astype("datetime64[D]"))))
            if len(window) < 30:
                start_min, end_min = ww["default_start_min"], ww["default_end_min"]
                mature = False
            else:
                start_min = float(np.percentile(window, lo_p))
                end_min = float(np.percentile(window, hi_p))
                mature = True
            rows.append((user, anchor, start_min, end_min, n_days, mature))

    out = pd.DataFrame(rows, columns=["user_id", "week_start", "ww_start_min",
                                      "ww_end_min", "baseline_days", "ww_mature"])
    return out


# --------------------------------------------------------------- features
def build_features(events: pd.DataFrame, org: pd.DataFrame,
                   cfg: Config) -> pd.DataFrame:
    """One row per (user, date) with the behavioural feature set."""
    if events.empty:
        return pd.DataFrame()

    ev = events.copy()
    ev["minute"] = ev["ts"].dt.hour * 60 + ev["ts"].dt.minute

    # -- learned working window, joined per user-week ---------------------
    windows = learn_working_windows(ev, cfg)
    ev["week_start"] = ev["ts"].dt.to_period("W").dt.start_time
    ev = ev.merge(windows, on=["user_id", "week_start"], how="left")
    ev["ww_start_min"] = ev["ww_start_min"].fillna(cfg.working_window["default_start_min"])
    ev["ww_end_min"] = ev["ww_end_min"].fillna(cfg.working_window["default_end_min"])
    ev["offhours"] = (ev["minute"] < ev["ww_start_min"]) | (ev["minute"] > ev["ww_end_min"])

    keys = ["user_id", "date"]

    # -- base per-day aggregates ------------------------------------------
    base = ev.groupby(keys, observed=True).agg(
        total_event_count=("event_id", "size"),
        first_activity_min=("minute", "min"),
        last_activity_min=("minute", "max"),
        offhours_event_count=("offhours", "sum"),
        distinct_pc_count=("pc_id", "nunique"),
    ).reset_index()
    base["active_span_min"] = base["last_activity_min"] - base["first_activity_min"]
    base["offhours_event_ratio"] = (
        base["offhours_event_count"] / base["total_event_count"].clip(lower=1))
    base["offhours_pct"] = base["offhours_event_ratio"] * 100
    base["is_weekend"] = pd.to_datetime(base["date"]).dt.weekday >= 5
    base["weekend_activity_count"] = np.where(
        base["is_weekend"], base["total_event_count"], 0)

    feats = base

    # -- per-source counts -------------------------------------------------
    for source, col in [("logon", "logon_count"), ("device", "device_connect_count"),
                        ("file", "file_event_count"), ("http", "http_event_count"),
                        ("email", "email_sent_count")]:
        sub = ev[ev["source"] == source]
        if source == "device":
            sub = sub[sub["action"] == "connect"]
        if source == "logon":
            sub = sub[sub["action"] == "logon"]
        agg = sub.groupby(keys, observed=True).size().rename(col).reset_index()
        feats = feats.merge(agg, on=keys, how="left")

    # -- device off-hours connects ------------------------------------------
    device_connects = ev[(ev["source"] == "device") & (ev["action"] == "connect")]
    if not device_connects.empty:
        agg = (device_connects.groupby(keys, observed=True)["offhours"].sum()
               .rename("usb_offhours_connect_count").reset_index())
        feats = feats.merge(agg, on=keys, how="left")

    # -- http off-hours ratio ------------------------------------------------
    http_all = ev[ev["source"] == "http"]
    if not http_all.empty:
        agg = (http_all.groupby(keys, observed=True)["offhours"].sum()
               .rename("offhours_http_count").reset_index())
        feats = feats.merge(agg, on=keys, how="left")

    # -- logon features ----------------------------------------------------
    logons = ev[(ev["source"] == "logon") & (ev["action"] == "logon")]
    if not logons.empty:
        agg = logons.groupby(keys, observed=True).agg(
            after_hours_logon_count=("offhours", "sum"),
        ).reset_index()
        feats = feats.merge(agg, on=keys, how="left")

        # A user's "own" PC is the one they use most over the whole period.
        modal = (logons.groupby(["user_id", "pc_id"], observed=True).size()
                 .reset_index(name="n")
                 .sort_values("n", ascending=False)
                 .drop_duplicates("user_id")
                 .rename(columns={"pc_id": "own_pc"})[["user_id", "own_pc"]])
        logons = logons.merge(modal, on="user_id", how="left")
        logons["is_own"] = logons["pc_id"] == logons["own_pc"]
        agg = logons.groupby(keys, observed=True)["is_own"].mean().rename("own_pc_ratio").reset_index()
        feats = feats.merge(agg, on=keys, how="left")

        # First-ever workstation use, per user, in time order.
        lg = logons.sort_values(["user_id", "ts"], kind="stable")
        first_use = lg.groupby(["user_id", "pc_id"], observed=True)["date"].transform("min")
        lg = lg.assign(is_new_pc=lg["date"] == first_use)
        new_pc = (lg[lg["is_new_pc"]].drop_duplicates(["user_id", "pc_id"])
                  .groupby(keys, observed=True).size().rename("new_pc_count").reset_index())
        feats = feats.merge(new_pc, on=keys, how="left")
    else:
        modal = pd.DataFrame(columns=["user_id", "own_pc"])

    # -- sessions ----------------------------------------------------------
    sessions = _pair_sessions(
        ev[(ev["source"] == "logon") & ev["action"].isin(["logon", "logoff"])],
        "logon", "logoff")
    usb = _pair_sessions(
        ev[(ev["source"] == "device") & ev["action"].isin(["connect", "disconnect"])],
        "connect", "disconnect")

    if not sessions.empty:
        agg = sessions.groupby(["user_id", "date"], observed=True).agg(
            max_session_duration_min=("duration_min", "max")).reset_index()
        feats = feats.merge(agg, on=["user_id", "date"], how="left")

    if not usb.empty:
        agg = usb.groupby(["user_id", "date"], observed=True).agg(
            usb_session_total_min=("duration_min", "sum")).reset_index()
        feats = feats.merge(agg, on=["user_id", "date"], how="left")

        # USB on a workstation that is not the user's own.
        if not modal.empty:
            u = usb.merge(modal, on="user_id", how="left")
            u["foreign"] = u["pc_id"] != u["own_pc"]
            agg = (u.groupby(["user_id", "date"], observed=True)["foreign"].any()
                   .rename("usb_on_foreign_pc").reset_index())
            feats = feats.merge(agg, on=["user_id", "date"], how="left")

        # First-ever USB use, and dormancy since the last one.
        usb_days = (usb.groupby("user_id", observed=True)["date"].apply(lambda s: sorted(set(s)))
                    .to_dict())
        first_rows, dormancy_rows = [], []
        for user, days in usb_days.items():
            for i, day in enumerate(days):
                first_rows.append((user, day, i == 0))
                gap = (day - days[i - 1]).days if i > 0 else np.nan
                dormancy_rows.append((user, day, gap))
        feats = feats.merge(
            pd.DataFrame(first_rows, columns=["user_id", "date", "is_first_ever_usb"]),
            on=["user_id", "date"], how="left")
        feats = feats.merge(
            pd.DataFrame(dormancy_rows, columns=["user_id", "date", "days_since_last_usb"]),
            on=["user_id", "date"], how="left")

    # -- file features -----------------------------------------------------
    files = ev[ev["source"] == "file"].copy()
    if not files.empty:
        # a_sensitive is boolean but object-dtype after the cross-source concat
        # (NaN on every row from another source forces it). Object-dtype
        # groupby.sum() then hits a pandas edge case: a single-row group sums
        # to the raw bool instead of casting to int, leaving a mixed
        # bool/int object column that breaks any typed sink (Parquet, the
        # DB). Cast to int on the filtered (NaN-free) subset first.
        files["a_sensitive"] = files["a_sensitive"].astype(bool).astype(int)
        agg = files.groupby(keys, observed=True).agg(
            distinct_file_count=("a_filename", "nunique")
            if "a_filename" in files.columns else ("event_id", "nunique"),
            distinct_extension_count=("a_extension", "nunique"),
            sensitive_ext_count=("a_sensitive", "sum"),
        ).reset_index()
        feats = feats.merge(agg, on=keys, how="left")

        # Files touched while removable media was connected - the single
        # strongest exfiltration primitive in the whole feature set.
        if not usb.empty:
            during = []
            usb_by_user = {u: g for u, g in usb.groupby("user_id", sort=False, observed=True)}
            for (user, day), grp in files.groupby(keys, sort=False, observed=True):
                sess = usb_by_user.get(user)
                if sess is None:
                    continue
                same_day = sess[sess["date"] == day]
                if same_day.empty:
                    continue
                inside = _interval_membership(
                    grp["ts"].to_numpy(),
                    same_day["start"].to_numpy(), same_day["end"].to_numpy())
                during.append((user, day, int(inside.sum())))
            if during:
                feats = feats.merge(
                    pd.DataFrame(during, columns=["user_id", "date",
                                                  "file_events_during_usb"]),
                    on=["user_id", "date"], how="left")

        # Largest burst of file activity inside any ten-minute span.
        bursts = []
        for (user, day), grp in files.groupby(keys, sort=False, observed=True):
            t = np.sort(grp["ts"].to_numpy())
            if len(t) < 2:
                bursts.append((user, day, len(t)))
                continue
            window = np.timedelta64(10, "m")
            right = np.searchsorted(t, t + window, side="right")
            bursts.append((user, day, int((right - np.arange(len(t))).max())))
        feats = feats.merge(
            pd.DataFrame(bursts, columns=["user_id", "date", "file_burst_max_per_10min"]),
            on=["user_id", "date"], how="left")

        # File extensions never previously used by this user.
        fl = files.sort_values(["user_id", "ts"], kind="stable")
        first_ext = fl.groupby(["user_id", "a_extension"], observed=True)["date"].transform("min")
        fl = fl.assign(is_new=fl["date"] == first_ext)
        new_ext = (fl[fl["is_new"]].drop_duplicates(["user_id", "a_extension"])
                   .groupby(keys, observed=True).size().rename("new_extension_count").reset_index())
        feats = feats.merge(new_ext, on=keys, how="left")

    # -- http features -----------------------------------------------------
    http = ev[ev["source"] == "http"].copy()
    if not http.empty:
        http["a_upload_shaped"] = http["a_upload_shaped"].astype(bool).astype(int)
        agg = http.groupby(keys, observed=True).agg(
            distinct_domain_count=("a_domain", "nunique"),
            upload_shaped_count=("a_upload_shaped", "sum"),
        ).reset_index()
        feats = feats.merge(agg, on=keys, how="left")

        cats = (http.pivot_table(index=keys, columns="a_category",
                                 values="event_id", aggfunc="size", observed=True)
                .reset_index())
        rename = {"job_search": "job_search_visits",
                  "cloud_storage": "cloud_storage_visits",
                  "leak_platform": "leak_platform_visits",
                  "hacking_tools": "hacking_tool_visits",
                  "webmail": "webmail_visits"}
        cats = cats.rename(columns=rename)
        wanted = keys + [c for c in rename.values() if c in cats.columns]
        feats = feats.merge(cats[wanted], on=keys, how="left")

        hl = http.sort_values(["user_id", "ts"], kind="stable")
        first_dom = hl.groupby(["user_id", "a_domain"], observed=True)["date"].transform("min")
        hl = hl.assign(is_new=hl["date"] == first_dom)
        new_dom = (hl[hl["is_new"]].drop_duplicates(["user_id", "a_domain"])
                   .groupby(keys, observed=True).size().rename("new_domain_count").reset_index())
        feats = feats.merge(new_dom, on=keys, how="left")

    # -- email features ----------------------------------------------------
    email = ev[ev["source"] == "email"].copy()
    if not email.empty:
        email["a_self_send"] = email["a_self_send"].astype(bool).astype(int)
        agg = email.groupby(keys, observed=True).agg(
            external_recipient_count=("a_external_count", "sum"),
            self_send_count=("a_self_send", "sum"),
            attachment_count=("a_attachments", "sum"),
            attachment_bytes_external=("a_attachment_bytes_external", "sum"),
            bcc_external_count=("a_bcc_external_count", "sum"),
            max_recipients_single_email=("a_recipient_count", "max"),
        ).reset_index()
        feats = feats.merge(agg, on=keys, how="left")

    # -- events with no open logon session ---------------------------------
    if not sessions.empty:
        non_logon = ev[ev["source"] != "logon"]
        outside = []
        sess_by_user = {u: g for u, g in sessions.groupby("user_id", sort=False, observed=True)}
        for (user, day), grp in non_logon.groupby(keys, sort=False, observed=True):
            s = sess_by_user.get(user)
            if s is None:
                outside.append((user, day, len(grp)))
                continue
            same_day = s[s["date"] == day]
            if same_day.empty:
                outside.append((user, day, len(grp)))
                continue
            inside = _interval_membership(
                grp["ts"].to_numpy(),
                same_day["start"].to_numpy(), same_day["end"].to_numpy())
            outside.append((user, day, int((~inside).sum())))
        feats = feats.merge(
            pd.DataFrame(outside, columns=["user_id", "date", "events_outside_session"]),
            on=["user_id", "date"], how="left")

    # -- cross-source interaction features ----------------------------------
    # The gaps between an off-hours logon, a USB connect, a file touch, and an
    # upload. A single-source detector cannot compute these (docs/03-DATA-MODEL
    # section 4.8) - they are where correlation-aware detection earns itself.
    offhours_logons = ev[(ev["source"] == "logon") & (ev["action"] == "logon")
                         & ev["offhours"]]
    connects = ev[(ev["source"] == "device") & (ev["action"] == "connect")]
    uploads = ev[(ev["source"] == "http") & ev["a_upload_shaped"]] if (
        "a_upload_shaped" in ev.columns) else ev.iloc[0:0]

    def _first_ts_by_day(frame: pd.DataFrame) -> dict:
        if frame.empty:
            return {}
        g = frame.groupby(keys, observed=True)["ts"].min()
        return g.to_dict()

    def _gap_after(from_map: dict, to_frame: pd.DataFrame, out_name: str) -> pd.DataFrame:
        """Minutes from each (user, date) anchor to the next event of `to_frame`
        on the same day at or after the anchor. NaN when either side is absent."""
        rows = []
        if not from_map or to_frame.empty:
            return pd.DataFrame(columns=["user_id", "date", out_name])
        to_by_key = {k: g["ts"].to_numpy() for k, g in to_frame.groupby(keys, sort=False, observed=True)}
        for key, anchor in from_map.items():
            candidates = to_by_key.get(key)
            if candidates is None:
                continue
            after = candidates[candidates >= np.datetime64(anchor)]
            if len(after) == 0:
                continue
            gap_min = (after.min() - np.datetime64(anchor)) / np.timedelta64(1, "m")
            rows.append((key[0], key[1], float(gap_min)))
        return pd.DataFrame(rows, columns=["user_id", "date", out_name])

    logon_map = _first_ts_by_day(offhours_logons)
    connect_map = _first_ts_by_day(connects)
    file_map = _first_ts_by_day(files) if not files.empty else {}

    feats = feats.merge(_gap_after(logon_map, connects, "min_gap_logon_to_usb_min"),
                        on=keys, how="left")
    feats = feats.merge(_gap_after(connect_map, files, "min_gap_usb_to_file_min"),
                        on=keys, how="left")
    feats = feats.merge(_gap_after(file_map, uploads, "min_gap_file_to_upload_min"),
                        on=keys, how="left")

    feats["chain_completeness"] = (
        (feats["logon_count"] > 0).astype(int)
        + (feats["file_event_count"] > 0).astype(int)
        + (feats["device_connect_count"] > 0).astype(int)
        + (feats["http_event_count"] > 0).astype(int))

    # Ordinal proxy for "furthest stage reached", from raw counts only (feature
    # extraction runs before baselines and before the rule engine, so this
    # cannot see z-scores or fired signals - it is a coarse heuristic for
    # reporting, not the authoritative kill-chain stage the detect stage
    # assigns per fired rule).
    def _stage_proxy(row) -> int:
        if (row.get("file_events_during_usb", 0) > 0 or row.get("leak_platform_visits", 0) > 0
                or row.get("cloud_storage_visits", 0) > 0 or row.get("self_send_count", 0) > 0
                or row.get("bcc_external_count", 0) > 0):
            return 4
        if row.get("file_burst_max_per_10min", 0) >= 10 or row.get("sensitive_ext_count", 0) > 0:
            return 3
        if (row.get("is_first_ever_usb", False) or row.get("device_connect_count", 0) > 0
                or row.get("hacking_tool_visits", 0) > 0 or row.get("after_hours_logon_count", 0) > 0):
            return 2
        if (row.get("new_pc_count", 0) > 0 or row.get("distinct_file_count", 0) > 0
                or row.get("distinct_domain_count", 0) > 0):
            return 1
        if row.get("job_search_visits", 0) > 0:
            return 0
        return 0

    for col in ("file_events_during_usb", "leak_platform_visits", "cloud_storage_visits",
               "self_send_count", "bcc_external_count", "file_burst_max_per_10min",
               "sensitive_ext_count", "device_connect_count", "hacking_tool_visits",
               "after_hours_logon_count", "new_pc_count", "distinct_file_count",
               "distinct_domain_count", "job_search_visits"):
        if col not in feats.columns:
            feats[col] = 0
    feats["killchain_max_stage"] = feats.apply(_stage_proxy, axis=1)

    # -- organisational context -------------------------------------------
    if not org.empty:
        feats = feats.merge(
            org[["user_id", "role", "department", "cohort_key", "departure_date"]],
            on="user_id", how="left")
        feats["days_to_departure"] = (
            (pd.to_datetime(feats["departure_date"]) - pd.to_datetime(feats["date"]))
            .dt.days)
        feats["is_departing_within_30d"] = feats["days_to_departure"].between(0, 30)
    else:
        feats["cohort_key"] = "unknown"
        feats["days_to_departure"] = np.nan

    # Tenure: days since this user's first observed event (no hire-date source
    # exists in CERT). Peer cohort size: how many members of this user's
    # cohort were active on this same date - a small cohort weakens the
    # peer baseline, and this is what lets confidence reflect that.
    first_seen = ev.groupby("user_id", observed=True)["date"].min().rename("first_seen")
    feats = feats.merge(first_seen, on="user_id", how="left")
    feats["tenure_days"] = (pd.to_datetime(feats["date"])
                            - pd.to_datetime(feats["first_seen"])).dt.days
    feats = feats.drop(columns=["first_seen"])

    feats["peer_cohort_size"] = (
        feats.groupby(["cohort_key", "date"], observed=True)["user_id"].transform("nunique"))

    # Mass-email flag: recipients above this cohort's p99 on this date, cross-
    # sectional over cohort members with at least peer_min_cohort data points.
    peer_min = cfg.baseline["peer_min_cohort"]
    p99 = (feats.groupby(["cohort_key", "date"], observed=True)["max_recipients_single_email"]
           .transform(lambda s: s.quantile(0.99) if len(s) >= peer_min else np.inf))
    feats["mass_email_flag"] = feats["max_recipients_single_email"] > p99

    # -- derived and defaults ---------------------------------------------
    counts = [
        "logon_count", "device_connect_count", "file_event_count", "http_event_count",
        "email_sent_count", "after_hours_logon_count", "new_pc_count",
        "distinct_file_count", "distinct_extension_count", "sensitive_ext_count",
        "file_events_during_usb", "file_burst_max_per_10min", "new_extension_count",
        "distinct_domain_count", "upload_shaped_count", "new_domain_count",
        "job_search_visits", "cloud_storage_visits", "leak_platform_visits",
        "hacking_tool_visits", "webmail_visits", "external_recipient_count",
        "self_send_count", "attachment_count", "attachment_bytes_external",
        "bcc_external_count", "max_recipients_single_email",
        "events_outside_session", "usb_session_total_min",
        "max_session_duration_min", "usb_offhours_connect_count",
        "offhours_http_count", "chain_completeness", "killchain_max_stage",
        "tenure_days", "peer_cohort_size",
    ]
    for col in counts:
        if col not in feats.columns:
            feats[col] = 0
        feats[col] = feats[col].fillna(0)

    for col, default in [("is_first_ever_usb", False), ("usb_on_foreign_pc", False),
                         ("mass_email_flag", False)]:
        if col not in feats.columns:
            feats[col] = default
        feats[col] = np.where(feats[col].isna(), False, feats[col]).astype(bool)

    if "days_since_last_usb" not in feats.columns:
        feats["days_since_last_usb"] = np.nan
    if "own_pc_ratio" not in feats.columns:
        feats["own_pc_ratio"] = 1.0
    feats["own_pc_ratio"] = feats["own_pc_ratio"].fillna(1.0)

    feats["sensitive_ext_ratio"] = (
        feats["sensitive_ext_count"] / feats["file_event_count"].clip(lower=1))
    feats["attachment_mb_external"] = feats["attachment_bytes_external"] / 1e6
    feats["file_to_usb_ratio"] = (
        feats["file_events_during_usb"] / feats["file_event_count"].clip(lower=1))
    feats["usb_connect_after_hours_ratio"] = (
        feats["usb_offhours_connect_count"] / feats["device_connect_count"].clip(lower=1))
    feats["offhours_http_ratio"] = (
        feats["offhours_http_count"] / feats["http_event_count"].clip(lower=1))

    # Trailing-14-day job-search persistence: a sustained pattern, not a spike.
    feats = feats.sort_values(["user_id", "date"], kind="stable")
    feats["_js_day"] = (feats["job_search_visits"] > 0).astype(int)
    feats["job_search_days_trailing14"] = (
        feats.groupby("user_id", observed=True)["_js_day"]
        .transform(lambda s: s.rolling(14, min_periods=1).sum()))
    feats = feats.drop(columns=["_js_day"])

    # Data completeness feeds confidence: missing sources lower certainty,
    # they never silently lower risk.
    present = ev.groupby(keys, observed=True)["source"].nunique().rename("sources_present").reset_index()
    feats = feats.merge(present, on=keys, how="left")
    feats["data_completeness"] = feats["sources_present"].fillna(0) / len(
        cfg.features["sources"])

    return feats.reset_index(drop=True)
