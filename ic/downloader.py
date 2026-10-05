"""
Downloader: download 1-minute candles from ICICI Breeze for every leg of every trade,
for every trading day from entry to the latest possible exit. Restart-safe: already
downloaded contract-days are skipped, so if you hit the daily API limit just run it again
tomorrow with a fresh session token.

Run:  python download.py              (all trades)
      python download.py --trades 1 2 3
      python download.py --index      (only NIFTY and India VIX daily OHLC, a few calls)
"""
import argparse
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from ic import config as C
from ic.breeze_client import connect
from ic.common import load_inputs, load_calendar, time_exit_day, cache_file, iso


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
    days, s = set(), first
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
    """Daily OHLC of NIFTY and India VIX (config.INDEX_DAILY), for trend/VIX filter studies."""
    for code, path in C.INDEX_DAILY.items():
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
        df = df.drop_duplicates("date").sort_values("date")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        print(f"{code}: {len(df)} days saved to {path}")


def fetch_fallback(api, trades, legs, cal, errors):
    """For trades with a leg that has no usable entry price: fetch the entry day of the fallback
    candidates (ic/fallback.py), then the full price history of the strikes chosen."""
    from types import SimpleNamespace
    from ic.engine import candles
    from ic.fallback import choose
    need_entry = []
    for t in trades.itertuples():
        _, note, checked = choose(t, legs[legs.trade_id == t.trade_id])
        if note:
            day = t.entry_date.date()
            need_entry += [(t, k) for k in dict.fromkeys(checked) if not cache_file(k, day).exists()]
    print(f"Fallback strikes: {len(need_entry)} API calls needed for entry-day prices")
    for t, k in need_entry:
        leg = SimpleNamespace(expiry=t.expiry.strftime("%Y-%m-%d"), opt_type=k[-2:], strike=int(k.split("_")[2][:-2]), key=k)
        status, msg = fetch_chunk(api, leg, [t.entry_date.date()])
        if status == "ERROR":
            errors.append((t.trade_id, k, t.entry_date.date().isoformat(), msg))
    candles.cache_clear()
    todo = []
    for t in trades.itertuples():
        chosen, note, _ = choose(t, legs[legs.trade_id == t.trade_id])
        if not note:
            continue
        tx = time_exit_day(t.expiry.date(), cal)
        end = max(tx, t.ref_exit_date.date()) if pd.notna(t.ref_exit_date) else tx
        days = sorted({t.entry_date.date()} | {d for d in cal if t.entry_date.date() <= d <= end})
        for leg in chosen.itertuples():
            need = [d for d in days if not cache_file(leg.key, d).exists()]
            todo += [(t.trade_id, leg, need[i:i + 2]) for i in range(0, len(need), 2)]
    print(f"Fallback strikes: {len(todo)} API calls needed for the chosen strikes")
    for tid, leg, chunk in todo:
        status, msg = fetch_chunk(api, leg, chunk)
        if status == "ERROR":
            errors.append((tid, leg.key, chunk[0].isoformat(), msg))
    return True


def fetch_chunk(api, leg, days):
    """Fetch 1-minute candles for up to 2 trading days in one call; save one file per day."""
    d1, d2 = days[0], days[-1]
    exp = date.fromisoformat(leg.expiry)
    r = api.hist(interval="1minute",
                 from_date=iso(datetime(d1.year, d1.month, d1.day, 9, 15)),
                 to_date=iso(datetime(d2.year, d2.month, d2.day, 15, 30)),
                 stock_code="NIFTY", exchange_code="NFO", product_type="options",
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


def chunks(t, leg, cal):
    """Day pairs of one leg (entry -> time exit / StockMock exit) that are not cached yet - one API call each."""
    tx = time_exit_day(t.expiry.date(), cal)
    end = max(tx, t.ref_exit_date.date()) if pd.notna(t.ref_exit_date) else tx
    days = sorted({t.entry_date.date()} | {d for d in cal if t.entry_date.date() <= d <= end})
    need = [d for d in days if not cache_file(leg.key, d).exists()]
    return [need[i:i + 2] for i in range(0, len(need), 2)]


def main():
    ap = argparse.ArgumentParser(description="Download Breeze 1-minute candles for all trade legs")
    ap.add_argument("--trades", type=int, nargs="*", help="only these trade ids")
    ap.add_argument("--index", action="store_true", help="only NIFTY + India VIX daily OHLC")
    ap.add_argument("--dry-run", action="store_true", help="only count the API calls needed (no login, no calls)")
    a = ap.parse_args()
    trades, legs = load_inputs(a.trades)

    if a.dry_run:
        cal = load_calendar(trades.entry_date.min().date(), trades.expiry.max().date())
        n = sum(len(chunks(t, leg, cal)) for t in trades.itertuples()
                for leg in legs[legs.trade_id == t.trade_id].itertuples())
        print(f"{n} API calls needed for {len(trades)} trades (strike set '{C.STRIKE_SET or 'StockMock'}', hedges "
              f"{C.HEDGE_WIDTH_CE}/{C.HEDGE_WIDTH_PE} pts); fallback strikes may add a few. "
              f"Limit per day {C.DAILY_CALL_LIMIT}.")
        return
    api = Api(connect())
    if a.index:   # ~100 trading days before the first entry, for moving averages
        fetch_index_daily(api, trades.entry_date.min().date() - timedelta(days=150), date.today())
        print(f"API calls this run: {api.calls}")
        return
    errors, complete = [], False
    first = trades.entry_date.min().date()
    last = max(trades.expiry.max().date(), date.today())
    try:
        build_calendar(api, first, min(last, date.today()))
        cal = load_calendar(first, trades.expiry.max().date())

        # work list: (leg, [day1, day2]) chunks not yet cached
        todo = [(t.trade_id, leg, chunk) for t in trades.itertuples()
                for leg in legs[legs.trade_id == t.trade_id].itertuples() for chunk in chunks(t, leg, cal)]
        print(f"{len(todo)} API calls needed (limit per run {C.DAILY_CALL_LIMIT}, already used {api.calls})")

        for n, (tid, leg, chunk) in enumerate(todo, 1):
            status, msg = fetch_chunk(api, leg, chunk)
            if status == "ERROR":
                errors.append((tid, leg.key, chunk[0].isoformat(), msg))
                if "session" in msg.lower() or "unauthor" in msg.lower():
                    print(f"\nSession problem: {msg}\nGenerate a new session token and run again.")
                    break
            if n % 50 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} calls  (errors so far: {len(errors)})")
        else:
            complete = fetch_fallback(api, trades, legs, cal, errors) if C.FALLBACK_STRIKES else True
    except RuntimeError as e:
        if str(e) != "DAILY_LIMIT":
            raise
        print(f"\nStopped at the daily call limit ({C.DAILY_CALL_LIMIT}). Progress is saved - "
              "run again tomorrow with a new session token.")

    print(f"\nAPI calls this run: {api.calls}")
    if errors:
        C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ef = C.OUTPUT_DIR / "download_errors.csv"
        pd.DataFrame(errors, columns=["trade_id", "contract", "from_day", "error"]).to_csv(ef, index=False)
        print(f"{len(errors)} chunks failed -> {ef} (they will be retried next run)")
    elif complete:
        print("All requested data downloaded. Next: python backtest.py")


if __name__ == "__main__":
    main()
