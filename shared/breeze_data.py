"""Breeze data plumbing shared by every strategy: rate-limited API wrapper, trading calendar, index daily OHLC,
and the 1-minute candle fetch for one option contract (up to 2 days per call, one cache file per day)."""
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from shared import config as C
from shared.calendar import cache_file, iso


class Api:
    def __init__(self, breeze):
        self.b, self.calls = breeze, 0

    def hist(self, **p):
        last_err = None
        for attempt in range(3):
            if self.calls >= C.DAILY_CALL_LIMIT:
                raise RuntimeError("DAILY_LIMIT")
            try:
                r = self.b.get_historical_data_v2(**p)
                self.calls += 1
                time.sleep(C.PAUSE_SEC)
                return r or {}
            except Exception as e:  # network / SDK error -> back off and retry
                self.calls += 1
                last_err = str(e)
                time.sleep(3 * (attempt + 1))
        return {"Success": None, "Error": f"EXCEPTION: {last_err}"}


def build_calendar(api, first: date, last: date):
    p = Path(C.CALENDAR_CSV)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        df = pd.read_csv(p)
        if len(df) and date.fromisoformat(df.date.max()) >= min(last, date.today() - timedelta(days=1)):
            print(f"Calendar: {len(df)} trading days (cached)")
            return
    # Keep every day already known: a run for a few trades must never shrink the calendar (load_calendar
    # treats a day inside the file's range but not in it as a holiday). Start a few days early because
    # Breeze can leave out the first day of the range.
    days = set(pd.read_csv(p).date) if p.exists() else set()
    s = first - timedelta(days=5)
    while s <= last:
        e = min(s + timedelta(days=900), last)
        r = api.hist(interval="1day", from_date=iso(datetime(s.year, s.month, s.day, 9, 15)),
                     to_date=iso(datetime(e.year, e.month, e.day, 15, 30)),
                     stock_code="NIFTY", exchange_code="NSE", product_type="cash")
        for c in r.get("Success") or []:
            days.add(str(c["datetime"])[:10])
        s = e + timedelta(days=1)
    if days:
        pd.DataFrame({"date": sorted(days)}).to_csv(p, index=False)
        print(f"Calendar: {len(days)} NIFTY trading days saved to {p}")
    else:
        print("WARNING: could not fetch NIFTY daily candles; using weekdays minus EXTRA_HOLIDAYS. "
              "Holidays will just return empty days.")


def fetch_index_daily(api, first: date, last: date):
    """Daily OHLC of NIFTY, India VIX and the traded index (config.INDEX_DAILY), for trend/VIX filter studies."""
    for name in dict.fromkeys(["NIFTY", "INDVIX", C.INDEX]):
        code, path = C.DAILY_BREEZE_CODES[name], C.INDEX_DAILY[name]
        rows, s = [], first
        while s <= last:
            e = min(s + timedelta(days=900), last)
            r = api.hist(interval="1day", from_date=iso(datetime(s.year, s.month, s.day, 9, 15)),
                         to_date=iso(datetime(e.year, e.month, e.day, 15, 30)),
                         stock_code=code, exchange_code="NSE", product_type="cash")
            rows += r.get("Success") or []
            if not r.get("Success"):
                print(f"  {code} {s}..{e}: {r.get('Error')}")
            s = e + timedelta(days=1)
        if not rows:
            print(f"{code}: no data returned")
            continue
        df = pd.DataFrame(rows)
        df["date"] = df["datetime"].astype(str).str[:10]
        df = df[["date"] + [c for c in ["open", "high", "low", "close"] if c in df.columns]]
        if Path(path).exists():    # days already in the file win: they hold NSE's official closes
            old = pd.read_csv(path)   # (fetch_index_nse.py); Breeze's daily close is the last traded value,
            df = pd.concat([old, df[~df.date.isin(old.date)]])   # so it only fills days the file lacks
        df = df.drop_duplicates("date").sort_values("date")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        print(f"{code}: {len(df)} days saved to {path}")


def fetch_chunk(api, leg, days):
    """Fetch 1-minute candles for up to 2 trading days in one call; save one file per day."""
    d1, d2 = days[0], days[-1]
    exp = date.fromisoformat(leg.expiry)
    r = api.hist(interval="1minute",
                 from_date=iso(datetime(d1.year, d1.month, d1.day, 9, 15)),
                 to_date=iso(datetime(d2.year, d2.month, d2.day, 15, 30)),
                 stock_code=C.BREEZE_CODE, exchange_code="NFO", product_type="options",
                 expiry_date=iso(datetime(exp.year, exp.month, exp.day, 6, 0)),
                 right="call" if leg.opt_type == "CE" else "put", strike_price=str(int(leg.strike)))
    err = str(r.get("Error") or "")
    rows = r.get("Success")
    if rows is None and err and "no data" not in err.lower():
        return "ERROR", err                       # do not cache; will retry next run
    df = pd.DataFrame(rows or [])
    cols = ["datetime", "open", "high", "low", "close", "volume", "open_interest"]
    if len(df):
        df = df[[c for c in cols if c in df.columns]]
        df["datetime"] = df["datetime"].astype(str).str[:19]
    for d in days:
        f = cache_file(leg.key, d)
        f.parent.mkdir(parents=True, exist_ok=True)
        part = df[df.datetime.str[:10] == d.isoformat()] if len(df) else pd.DataFrame(columns=cols)
        part.to_csv(f, index=False)               # empty file = fetched, no trades that day
    return "OK", err
