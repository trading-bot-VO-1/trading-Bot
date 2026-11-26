"""
High-impact news calendar for the news filter.

Sources (merged):
  1. Built-in (NEWS_BUILTIN): US Non-Farm Payrolls and FOMC rate decisions 2021-2026.
     These are the two biggest scheduled movers in forex and hit every USD pair.
  2. NEWS_FILE (data/news_events.csv): any full calendar you add yourself.
     Columns: time_utc, currency, impact, title
       time_utc  e.g. 2024-03-08 13:30   (UTC)
       currency  e.g. USD, EUR, GBP, JPY ...
       impact    only rows with "High" are used
  3. `python news.py --update` downloads THIS WEEK's calendar from Forex Factory
     and appends it to NEWS_FILE. Run it weekly (the live bot will do this
     automatically) and your history grows over time.

All times are converted to broker SERVER time to match MT5 candles.
"""
import argparse
import json
import os
import urllib.request
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import config

NY = "America/New_York"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
COLUMNS = ["time_utc", "currency", "impact", "title"]

# FOMC statement days (statement at 14:00 New York time)
FOMC_DATES = [
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


# ---------- time conversion ----------
def ny_to_server(ny_naive):
    """New York local wall time (naive) -> broker server time (naive)."""
    ny_naive = pd.Series(pd.to_datetime(ny_naive))
    if config.SERVER_TZ == "NY_CLOSE":
        return ny_naive + pd.Timedelta(hours=7)
    utc = ny_naive.dt.tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return utc.dt.tz_localize(None) + pd.Timedelta(hours=int(config.SERVER_TZ))


def utc_to_server(utc_naive):
    """UTC (naive) -> broker server time (naive)."""
    utc_naive = pd.Series(pd.to_datetime(utc_naive))
    if config.SERVER_TZ == "NY_CLOSE":
        ny = utc_naive.dt.tz_localize("UTC").dt.tz_convert(NY).dt.tz_localize(None)
        return ny + pd.Timedelta(hours=7)
    return utc_naive + pd.Timedelta(hours=int(config.SERVER_TZ))


def server_to_utc(ts):
    """Broker server time (naive Timestamp) -> UTC (naive)."""
    ts = pd.Timestamp(ts)
    if config.SERVER_TZ == "NY_CLOSE":
        ny = ts - pd.Timedelta(hours=7)
        return ny.tz_localize(NY, ambiguous=False, nonexistent="shift_forward") \
                 .tz_convert("UTC").tz_localize(None)
    return ts - pd.Timedelta(hours=int(config.SERVER_TZ))


def upcoming(events, currencies, now_server, hours=24):
    """High-impact events for these currencies in the next `hours` (server time)."""
    if events is None or events.empty:
        return events
    end = now_server + pd.Timedelta(hours=hours)
    m = events.currency.isin(set(currencies)) & (events.server_time >= now_server) & \
        (events.server_time <= end)
    return events[m].sort_values("server_time")


# ---------- built-in events ----------
def _nfp_days(start_year, end_year):
    """NFP = first Friday of the month at 08:30 NY. When the first Friday falls on
    the 1st-3rd, BLS sometimes releases a week later, so both Fridays are blocked."""
    days = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            d = date(y, m, 1)
            first_fri = d + timedelta(days=(4 - d.weekday()) % 7)
            days.append(first_fri)
            if first_fri.day <= 3:
                days.append(first_fri + timedelta(days=7))
    return days


def builtin_events(start_year=2021, end_year=2026):
    nfp = pd.DataFrame({
        "ny_time": [datetime.combine(d, datetime.min.time()) + timedelta(hours=8, minutes=30)
                    for d in _nfp_days(start_year, end_year)],
        "title": "Non-Farm Payrolls",
    })
    fomc = pd.DataFrame({
        "ny_time": pd.to_datetime(FOMC_DATES) + pd.Timedelta(hours=14),
        "title": "FOMC Rate Decision",
    })
    ev = pd.concat([nfp, fomc], ignore_index=True)
    ev["server_time"] = ny_to_server(ev["ny_time"]).values
    ev["currency"] = "USD"
    return ev[["server_time", "currency", "title"]]


# ---------- user / Forex Factory file ----------
def file_events(path=None):
    path = path or config.NEWS_FILE
    if not os.path.exists(path):
        return pd.DataFrame(columns=["server_time", "currency", "title"])
    df = pd.read_csv(path)
    df = df[df["impact"].astype(str).str.lower() == "high"].copy()
    df["server_time"] = utc_to_server(pd.to_datetime(df["time_utc"])).values
    df["currency"] = df["currency"].str.upper().str.strip()
    return df[["server_time", "currency", "title"]]


def load_events():
    parts = []
    if config.NEWS_BUILTIN:
        parts.append(builtin_events())
    parts.append(file_events())
    ev = pd.concat(parts, ignore_index=True).dropna(subset=["server_time"])
    return ev.drop_duplicates(["server_time", "currency"]).sort_values("server_time")


def block_mask(symbol, bar_times, events=None):
    """True for each bar whose OPEN time is inside a news window for either currency
    of the pair (from NEWS_BLOCK_BEFORE_MIN before to NEWS_BLOCK_AFTER_MIN after)."""
    events = load_events() if events is None else events
    currencies = {symbol[:3], symbol[3:6]}
    ev = np.sort(events.loc[events.currency.isin(currencies), "server_time"]
                 .values.astype("datetime64[ns]").astype(np.int64))
    t = np.asarray(bar_times).astype("datetime64[ns]").astype(np.int64)
    if len(ev) == 0:
        return np.zeros(len(t), dtype=bool)
    before = config.NEWS_BLOCK_BEFORE_MIN * 60 * 1_000_000_000
    after = config.NEWS_BLOCK_AFTER_MIN * 60 * 1_000_000_000
    # blocked if an event e exists with  t - after <= e <= t + before
    idx = np.searchsorted(ev, t - after, side="left")
    idx_ok = idx < len(ev)
    nxt = np.where(idx_ok, ev[np.minimum(idx, len(ev) - 1)], np.iinfo(np.int64).max)
    return idx_ok & (nxt <= t + before)


# ---------- Forex Factory weekly update ----------
def update_from_forexfactory(path=None):
    path = path or config.NEWS_FILE
    req = urllib.request.Request(FF_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        items = json.loads(r.read().decode("utf-8"))

    rows = []
    for it in items:
        ts = pd.Timestamp(it["date"]).tz_convert("UTC").tz_localize(None)
        rows.append({"time_utc": ts.strftime("%Y-%m-%d %H:%M"), "currency": it.get("country", ""),
                     "impact": it.get("impact", ""), "title": it.get("title", "")})
    new = pd.DataFrame(rows, columns=COLUMNS)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        new = pd.concat([pd.read_csv(path), new], ignore_index=True)
    new = new.drop_duplicates(["time_utc", "currency", "title"]).sort_values("time_utc")
    new.to_csv(path, index=False)
    high = (new.impact.astype(str).str.lower() == "high").sum()
    print(f"Saved {len(new)} events ({high} high-impact) to {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="News calendar tools")
    ap.add_argument("--update", action="store_true", help="append this week's Forex Factory calendar")
    ap.add_argument("--show", action="store_true", help="print upcoming / loaded high-impact events")
    a = ap.parse_args()
    if a.update:
        update_from_forexfactory()
    if a.show or not a.update:
        ev = load_events()
        print(f"{len(ev)} high-impact events loaded (server time):")
        print(ev.tail(20).to_string(index=False))
