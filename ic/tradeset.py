"""
Generate a trade set for months StockMock never ran (e.g. 2019-2020), following the same pattern as
the reference trades: one condor per monthly expiry, entered on the Monday six weeks before it.

- expiry  = last EXPIRY weekday of the month (Thursday until Aug-2025, then Tuesday), moved to the
            previous trading day if that day is a holiday;
- entry   = that weekday minus 3 (Thursday) or 1 (Tuesday) days minus 6 weeks = a Monday, moved to the
            next trading day if it is a holiday;
- strikes = rough ~30-delta starting strikes from the previous NIFTY close and India VIX (Black-Scholes).
            They are only the centre of the search: `select_strikes.py --trade-set NAME --around 3`
            picks the real ~30-delta strikes from option prices at 11:16.

Needs NIFTY and India VIX daily data for the period (fetch_index_nse.py or download.py --index).

Run:  python make_trades.py --from 2019-01 --to 2020-12 --name 2019_2020     (months = entry months)
"""
import argparse
import math
from datetime import date, timedelta

import pandas as pd

from ic import config as C
from ic.strikes import bs

TUESDAY_EXPIRY_FROM = date(2025, 9, 1)      # monthly expiries on Tuesday from Sep-2025, Thursday before
CE_VOL_FACTOR, PE_VOL_FACTOR = 0.85, 1.15   # skew: OTM calls trade below India VIX, OTM puts above
START_DELTA = 0.30


def last_weekday(year, month, weekday):
    d = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def monthly_expiry(year, month, days):
    """(expiry, nominal day) - the nominal last Thursday/Tuesday and the trading day actually used."""
    nominal = last_weekday(year, month, 1 if date(year, month, 1) >= TUESDAY_EXPIRY_FROM else 3)
    d = nominal
    while d not in days:
        d -= timedelta(days=1)
    return d, nominal


def start_strike(spot, vol, T, opt):
    grid = range(int(spot * 0.7) // C.STRIKE_STEP * C.STRIKE_STEP, int(spot * 1.3), C.STRIKE_STEP)
    return min(grid, key=lambda k: abs(abs(bs(spot, k, T, vol, opt)[1]) - START_DELTA))


def main():
    ap = argparse.ArgumentParser(description="Generate monthly iron-condor trades for a period")
    ap.add_argument("--from", dest="first", required=True, help="first entry month, YYYY-MM")
    ap.add_argument("--to", dest="last", required=True, help="last entry month, YYYY-MM")
    ap.add_argument("--name", required=True, help="trade set name -> ic_trades_<name>.csv / ic_legs_<name>.csv")
    a = ap.parse_args()

    nifty = pd.read_csv(C.INDEX_DAILY["NIFTY"], parse_dates=["date"]).set_index("date").close.sort_index()
    vix = pd.read_csv(C.INDEX_DAILY["INDVIX"], parse_dates=["date"]).set_index("date").close.sort_index()
    hol = {date.fromisoformat(h) for h in C.MUHURAT_DAYS}
    days = {d.date() for d in nifty.index if d.weekday() < 5} - hol
    first, last = (date(int(s[:4]), int(s[5:7]), 1) for s in (a.first, a.last))

    trades, legs = [], []
    y, m = first.year, first.month
    while True:
        m += 1                                   # the expiry is in the month after the entry month ...
        if m > 12:
            y, m = y + 1, 1
        expiry, nominal = monthly_expiry(y, m, days)
        entry = nominal - timedelta(days=nominal.weekday()) - timedelta(weeks=6)   # ... Monday, 6 weeks before
        while entry not in days:
            entry += timedelta(days=1)
        if entry.replace(day=1) > last:
            break
        if entry.replace(day=1) >= first:
            prev = nifty[nifty.index < pd.Timestamp(entry)]
            if len(prev) <= C.TREND_LOOKBACK_DAYS or expiry > max(days):
                raise SystemExit(f"No NIFTY daily data around {entry} .. {expiry} - run fetch_index_nse.py first.")
            spot, v = prev.iloc[-1], vix[vix.index < pd.Timestamp(entry)].iloc[-1] / 100
            T = (expiry - entry).days / 365
            sc = start_strike(spot, v * CE_VOL_FACTOR, T, "CE")
            sp = start_strike(spot, v * PE_VOL_FACTOR, T, "PE")
            w, tid, exp = C.HEDGE_WIDTH, entry.year % 100 * 100 + entry.month, expiry.isoformat()
            trades.append(dict(trade_id=tid, entry_date=entry.isoformat(), entry_time=C.ENTRY_TIME, expiry=exp,
                               sell_ce=sc, buy_ce=sc + w, sell_pe=sp, buy_pe=sp - w, qty_stockmock="",
                               ref_exit_date="", ref_exit_reason="", ref_pnl_pts="", ref_pnl_rs="",
                               ref_note=f"generated; start strikes from NIFTY {spot:.0f}, VIX {v * 100:.1f}"))
            for side, opt, k in (("BUY", "PE", sp - w), ("SELL", "CE", sc), ("BUY", "CE", sc + w), ("SELL", "PE", sp)):
                legs.append(dict(trade_id=tid, side=side, opt_type=opt, strike=k, expiry=exp,
                                 entry_dt=f"{entry} {C.ENTRY_TIME}", exit_dt="", entry_px="", exit_px=""))
    ft, fl = C.REF_DIR / f"ic_trades_{a.name}.csv", C.REF_DIR / f"ic_legs_{a.name}.csv"
    pd.DataFrame(trades).to_csv(ft, index=False)
    pd.DataFrame(legs).to_csv(fl, index=False)
    t = pd.DataFrame(trades)
    dte = (pd.to_datetime(t.expiry) - pd.to_datetime(t.entry_date)).dt.days
    print(t[["trade_id", "entry_date", "expiry", "sell_pe", "sell_ce"]].assign(dte=dte).to_string(index=False))
    print(f"\n{len(t)} trades -> {ft.name}, {fl.name}. Trade id = YYMM of the entry month.")
    print(f"Next: python select_strikes.py --trade-set {a.name} --ce-delta 0.30 --pe-delta 0.30 --around 4 "
          f"--name d30_{a.name} --dry-run")
