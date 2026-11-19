"""Covered-call research: pick a CE strike nearest a target delta at 11:16 on every condor cycle (2021-26) and download its candles
from entry to the time exit. Black-Scholes as in the condor picker (IV of each candidate's own 11:16 price; first guess from the
reference 30-delta call's IV). Writes data/iron_condor/strike_sets/strikes_cc<delta>.csv.

Run from the repo root:
  python strategies/iron_condor/analysis/covered_call_delta_download.py --delta 0.12 --dry-run
  python strategies/iron_condor/analysis/covered_call_delta_download.py --delta 0.12          (needs today's Breeze session)
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.getcwd())
import pandas as pd

from shared import config as SC
from shared.calendar import cache_file, contract_key, load_calendar, time_exit_day
from shared.options_math import bs, implied_vol
from shared.pricing import candles, price_at

REF = 'data/iron_condor/reference/ic_reference_trades.csv'
STEP, AROUND = 50, 3
_ND = pd.read_csv('data/shared/nifty_daily.csv', parse_dates=['date']).set_index('date')


def SPOT_FALLBACK(day):
    '''1-minute spot is not cached every day: use the midpoint of that day's NSE open and close.'''
    r = _ND.loc[pd.Timestamp(day)] if pd.Timestamp(day) in _ND.index else None
    return None if r is None else (r.open + r.close) / 2


def years(day, expiry):
    return (datetime.combine(expiry, datetime.strptime('15:30', '%H:%M').time())
            - datetime.combine(day, datetime.strptime(SC.ENTRY_TIME, '%H:%M').time())) / timedelta(days=365)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--delta', type=float, default=0.12)
    ap.add_argument('--exit-dte', type=int, default=18)
    ap.add_argument('--month', action='store_true',
                    help="enter the trading day after the previous monthly expiry (current-month call, ~28-30 DTE) instead of the condor's 43-DTE Monday")
    ap.add_argument('--ref', default=REF, help='trade list (default the 2021-26 reference; e.g. data/iron_condor/reference/ic_trades_2019_2020.csv)')
    ap.add_argument('--ref-strikes', help="strike set whose CE strike replaces sell_ce as the IV first guess (e.g. strikes_d30_2019_2020.csv)")
    ap.add_argument('--suffix', default='', help='strike set name suffix, e.g. _2019_2020')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    name = f"cc{int(round(a.delta * 100))}" + ('_m' if a.month else '') + a.suffix
    ref = pd.read_csv(a.ref, parse_dates=['entry_date', 'expiry']).sort_values('expiry').reset_index(drop=True)
    if a.ref_strikes:
        rs = pd.read_csv(a.ref_strikes)
        ce = rs[rs.opt_type == 'CE'].drop_duplicates('trade_id').set_index('trade_id').strike
        ref['sell_ce'] = [int(ce.get(t, s0)) for t, s0 in zip(ref.trade_id, ref.sell_ce)]
    if a.month:     # entry = first trading day after the previous monthly expiry
        prev = [pd.Timestamp('2021-01-28')] + list(ref.expiry[:-1])
        ent = []
        for pe, ex in zip(prev, ref.expiry):
            cal = load_calendar(pe.date() + timedelta(days=1), ex.date())
            ent.append(pd.Timestamp(cal[0]))
        ref['entry_date'] = ent
    api = None

    def fetch(legs):
        nonlocal api
        if not legs or a.dry_run:
            return
        from shared.breeze_client import connect
        from shared.breeze_data import Api, fetch_chunk
        api = api or Api(connect())
        for n, (leg, days) in enumerate(legs, 1):
            st, msg = fetch_chunk(api, leg, days)
            if st == 'ERROR':
                print('  error', leg.key, days[0], msg)
            if n % 100 == 0:
                print(f'  {n}/{len(legs)}', flush=True)
        candles.cache_clear()

    def leg(exp, k):
        e = exp.strftime('%Y-%m-%d')
        return SimpleNamespace(expiry=e, opt_type='CE', strike=int(k), key=contract_key(e, int(k), 'CE'))

    # 1) candidate strikes on the entry day
    plan, todo = {}, []
    for t in ref.itertuples():
        day, exp = t.entry_date.date(), t.expiry.date()
        spot = price_at(SC.SPOT_KEY, day, SC.ENTRY_TIME)[0] or SPOT_FALLBACK(day)
        rp = price_at(contract_key(exp.strftime('%Y-%m-%d'), int(t.sell_ce), 'CE'), day, SC.ENTRY_TIME)[0]
        if not rp:      # month mode: reference strike may not be cached that day -> generic 13% IV first guess
            rp = bs(spot, int(t.sell_ce), years(day, exp), 0.13, 'CE')[0] if spot else None
        T = years(day, exp)
        iv = implied_vol(rp, spot, int(t.sell_ce), T, 'CE') if (rp and spot) else None
        if not iv:
            print('no IV estimate', t.trade_id); continue
        grid = range(int(spot) // STEP * STEP, int(spot * 1.3), STEP)
        c = min(grid, key=lambda k: abs(bs(spot, k, T, iv * 0.95, 'CE')[1] - a.delta))   # OTM calls trade at a lower IV (skew)
        ks = list(range(c - AROUND * STEP, c + AROUND * STEP + 1, STEP))
        plan[t.trade_id] = (day, exp, spot, T, ks)
        todo += [(leg(exp, k), [day]) for k in ks if not cache_file(leg(exp, k).key, day).exists()]
    print(f'{len(plan)} cycles; {len(todo)} entry-day calls for candidates')
    fetch(todo)

    # 2) pick and download entry -> time exit
    picks, todo2 = [], []
    for tid, (day, exp, spot, T, ks) in plan.items():
        rows = []
        for k in ks:
            p, q, _ = price_at(contract_key(exp.strftime('%Y-%m-%d'), k, 'CE'), day, SC.ENTRY_TIME)
            if p and q in ('EXACT', 'FFILL'):
                v = implied_vol(p, spot, k, T, 'CE')
                if v:
                    rows.append((abs(bs(spot, k, T, v, 'CE')[1] - a.delta), k, bs(spot, k, T, v, 'CE')[1], p, q))
        if not rows:
            continue
        _, k, dl, p, q = min(rows)
        picks.append(dict(trade_id=tid, entry_date=day, expiry=exp, opt_type='CE', role='SELL', strike=k, delta=round(dl, 4),
                          price=p, quality=q, spot=spot))
        cal = load_calendar(day, exp)
        tx = time_exit_day(exp, cal, a.exit_dte)
        need = [d for d in cal if day <= d <= tx and not cache_file(leg(exp, k).key, d).exists()]
        todo2 += [(leg(exp, k), need[i:i + 2]) for i in range(0, len(need), 2)]
    print(f'{len(picks)} strikes picked; {len(todo2)} calls for candles to {a.exit_dte} DTE '
          f'(estimate before the candidates are downloaded)' if a.dry_run else f'{len(todo2)} candle calls')
    fetch(todo2)
    if not a.dry_run:
        out = pd.DataFrame(picks)
        f = f'data/iron_condor/strike_sets/strikes_{name}.csv'
        out.to_csv(f, index=False)
        print(f'saved {f}: delta avg {out.delta.mean():.3f} ({out.delta.min():.3f}-{out.delta.max():.3f})')
        if api:
            print('API calls', api.calls)


if __name__ == '__main__':
    main()
