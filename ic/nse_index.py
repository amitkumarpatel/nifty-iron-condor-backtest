"""
NIFTY 50 and India VIX daily OHLC from NSE's public daily index files (one small CSV per trading day,
no login). Merged into data/nifty_daily.csv, data/india_vix_daily.csv and the trading calendar - for
history before the Breeze index download, or to fill days Breeze leaves out.

Run:  python fetch_index_nse.py --from 2018-11-01 --to 2020-08-14
"""
import argparse
import csv
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ic import config as C

URL = "https://archives.nseindia.com/content/indices/ind_close_all_{:%d%m%Y}.csv"
NAMES = {"nifty 50": "NIFTY", "india vix": "INDVIX"}
TRIES, PAUSE_SEC = 3, 0.2


def fetch_day(day):
    """{code: (open, high, low, close)} for one day; {} if NSE has no file (weekend, holiday)."""
    req = urllib.request.Request(URL.format(day), headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(TRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return {}
            raise
        except OSError:
            if attempt == TRIES - 1:
                raise
            time.sleep(2)
    if not text.lstrip().lower().startswith("index name"):
        return {}
    out = {}
    for row in csv.DictReader(text.splitlines()):
        code = NAMES.get((row.get("Index Name") or "").strip().lower())
        if code:
            try:
                out[code] = tuple(float(row[k]) for k in ("Open Index Value", "High Index Value",
                                                           "Low Index Value", "Closing Index Value"))
            except ValueError:
                pass
    return out


def merge(path, rows, replace=False):
    """Add `rows` (date, open, high, low, close) to a daily CSV; existing days are kept unless `replace`."""
    new = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])
    p = Path(path)
    if p.exists():
        old = pd.read_csv(p)
        new = pd.concat([new, old[~old.date.isin(new.date)]]) if replace else pd.concat([old, new[~new.date.isin(old.date)]])
    p.parent.mkdir(parents=True, exist_ok=True)
    new.sort_values("date").to_csv(p, index=False)
    return len(new)


def main():
    ap = argparse.ArgumentParser(description="NIFTY and India VIX daily OHLC from NSE's daily index files")
    ap.add_argument("--from", dest="first", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="last", required=True, help="YYYY-MM-DD")
    ap.add_argument("--replace", action="store_true", help="overwrite days already in the files (default: only add)")
    a = ap.parse_args()
    day, last, rows = date.fromisoformat(a.first), date.fromisoformat(a.last), {"NIFTY": [], "INDVIX": []}
    n = 0
    while day <= last:
        if day.weekday() < 5:          # special weekend sessions are not fetched
            for code, v in fetch_day(day).items():
                rows[code].append((day.isoformat(), *v))
            n += 1
            if n % 50 == 0:
                print(f"  {day}  ({len(rows['NIFTY'])} trading days so far)")
            time.sleep(PAUSE_SEC)
        day += timedelta(days=1)
    for code, r in rows.items():
        print(f"{code}: {len(r)} days fetched, file now has {merge(C.INDEX_DAILY[code], r, a.replace)} days")
    cal = Path(C.CALENDAR_CSV)
    days = (set(pd.read_csv(cal).date) if cal.exists() else set()) | {r[0] for r in rows["NIFTY"]}
    pd.DataFrame({"date": sorted(days)}).to_csv(cal, index=False)
    print(f"Calendar: {len(days)} trading days")
