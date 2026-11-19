"""Covered call with ROLL: monthly call (16 or 20 delta) on the condor's dates, TP 50%, and when NIFTY's NSE close >= the sold strike
-> at 15:16 that day buy it back AND sell a next-month call at the same delta (managed by the same rules, may roll again). The next
cycle's regular entry is skipped while a rolled call covers its expiry. Downloads only the data the rolls need (iteratively).
Run: python cc_roll.py [--dry-run] [--download]"""
import os, sys, pickle, argparse
sys.path.insert(0, '.'); os.environ['BATMAN_VARIANT'] = 'hedged'
from types import SimpleNamespace
from datetime import datetime, timedelta
import pandas as pd, numpy as np
from shared import config as SC
from shared.calendar import contract_key, cache_file, load_calendar, time_exit_day
from shared.pricing import price_at, candles, order_costs
from shared.options_math import bs, implied_vol

S = 'output/iron_condor/'
nd = pd.read_csv('data/shared/nifty_daily.csv', parse_dates=['date']).set_index('date').close
b20 = pd.read_csv('data/batman/strike_sets/strikes_b20_16.csv', parse_dates=['entry_date', 'expiry'])
SETS = {16: b20[(b20.opt_type == 'CE') & (b20.role == 'SELL')], 20: b20[(b20.opt_type == 'CE') & (b20.role == 'BUY')]}
LOT, TP, EXIT_DTE, STEP, AROUND = 65, 0.5, 18, 50, 4
NEED = set()          # (expiry, strike, day) contract-days to download


def T(day, t, expiry):
    return (datetime.combine(expiry, datetime.strptime('15:30', '%H:%M').time())
            - datetime.combine(day, datetime.strptime(t, '%H:%M').time())) / timedelta(days=365)


def px(exp, k, day, t):
    key = contract_key(exp.strftime('%Y-%m-%d'), int(k), 'CE')
    if not cache_file(key, day).exists():
        NEED.add((exp, int(k), day)); return None, 'MISSING'
    p, q, m = price_at(key, day, t)
    return p, q


def mv10(e):
    c = nd[nd.index < pd.Timestamp(e)]; return (c.iloc[-1] / c.iloc[-11] - 1) * 100


def manage(start, t0, exp, k, roll_ok):
    """Short 1 call from start@t0. Returns dict(exit, why, net, credit, path) or None if data missing."""
    p0, q0 = px(exp, k, start, t0)
    if p0 is None: return None
    cal = load_calendar(start, exp); tx = time_exit_day(exp, cal, EXIT_DTE); path = []
    first = start if t0 <= SC.CHECK_TIME and t0 != SC.CHECK_TIME else start + timedelta(days=1)
    key = contract_key(exp.strftime('%Y-%m-%d'), int(k), 'CE')
    miss = [d for d in cal if start <= d <= tx and not cache_file(key, d).exists()]
    if miss:
        NEED.update((exp, int(k), d) for d in miss); return None
    for d in [x for x in cal if first <= x <= tx]:
        p, q = px(exp, k, d, SC.CHECK_TIME)
        if p is None:
            if q == 'MISSING': return None
            continue
        pnl = p0 - p; path.append((d, pnl * LOT))
        c = nd.get(pd.Timestamp(d))
        if c is not None and c >= k:
            return dict(exit=d, why='STRIKE', pnl=pnl, credit=p0, path=path, px_exit=p)
        if pnl >= TP * p0:
            return dict(exit=d, why='TARGET', pnl=pnl, credit=p0, path=path, px_exit=p)
    if not path: return None
    return dict(exit=path[-1][0], why='TIME', pnl=path[-1][1] / LOT, credit=p0, path=path, px_exit=None)


def pick_roll(day, exp_old, k_old, exp_new, delta):
    """Strike of the next-month call nearest `delta` at 15:16 on `day` (IV from the old call). None if data missing."""
    spot = nd.get(pd.Timestamp(day))
    pold, _ = px(exp_old, k_old, day, SC.CHECK_TIME)
    if pold is None or spot is None: return None
    iv = implied_vol(pold, spot, k_old, T(day, SC.CHECK_TIME, exp_old), 'CE') or 0.15
    tt = T(day, SC.CHECK_TIME, exp_new)
    grid = range(int(spot) // STEP * STEP, int(spot * 1.2), STEP)
    c = min(grid, key=lambda k: abs(bs(spot, k, tt, iv, 'CE')[1] - delta))
    cands, missing = [], False
    for k in range(c - AROUND * STEP, c + AROUND * STEP + 1, STEP):
        p, q = px(exp_new, k, day, SC.CHECK_TIME)
        if q == 'MISSING': missing = True; continue
        if p and q in ('EXACT', 'FFILL'):
            v = implied_vol(p, spot, k, tt, 'CE')
            if v: cands.append((abs(bs(spot, k, tt, v, 'CE')[1] - delta), k))
    if missing: return None
    return min(cands)[1] if cands else 'NONE'


def run(delta, filt=None):
    cyc = SETS[delta].sort_values('entry_date').reset_index(drop=True)
    exps = list(cyc.expiry.dt.date)
    rows, covered_until, incomplete = [], None, False
    for i, r in cyc.iterrows():
        e, x = r.entry_date.date(), r.expiry.date()
        if covered_until and x <= covered_until: continue          # a rolled call already covers this expiry
        if filt is not None and mv10(e) > filt: continue
        res = manage(e, SC.ENTRY_TIME, x, int(r.strike), True)
        if res is None: incomplete = True; continue
        chain = [dict(tid=r.trade_id, leg=0, expiry=x, strike=int(r.strike), start=e, **res)]
        j = i
        while chain[-1]['why'] == 'STRIKE' and j + 1 < len(cyc):
            j += 1; d = chain[-1]['exit']; xn = exps[j]
            k = pick_roll(d, chain[-1]['expiry'], chain[-1]['strike'], xn, delta / 100)
            if k is None: incomplete = True; break
            if k == 'NONE': break
            nr = manage(d, SC.CHECK_TIME, xn, k, True)
            if nr is None: incomplete = True; break
            chain.append(dict(tid=r.trade_id, leg=len(chain), expiry=xn, strike=k, start=d, **nr)); covered_until = xn
        for c in chain:
            fills = [('SELL', c['credit'])]
            c['net'] = c['pnl'] * LOT - order_costs(fills, LOT, True) - order_costs(fills, LOT, False)
        rows += chain
    return rows, incomplete


def download():
    from shared.breeze_client import connect
    from shared.breeze_data import Api, fetch_chunk
    api = Api(connect()); n = 0
    by = {}
    for exp, k, d in NEED: by.setdefault((exp, k), []).append(d)
    for (exp, k), ds in by.items():
        ds = sorted(ds)
        leg = SimpleNamespace(expiry=exp.strftime('%Y-%m-%d'), opt_type='CE', strike=k, key=contract_key(exp.strftime('%Y-%m-%d'), k, 'CE'))
        for i in range(0, len(ds), 2):
            st, msg = fetch_chunk(api, leg, ds[i:i + 2]); n += 1
            if st == 'ERROR': print('  error', leg.key, ds[i], msg)
    candles.cache_clear(); print('API calls', api.calls); return api.calls


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
    total = 0
    for it in range(12):
        NEED.clear(); inc = False
        for delta in (16, 20):
            for f in (None, 2.0):
                _, i = run(delta, f); inc |= i
        # a held call needs every day to its time exit: add the remaining days of chosen strikes lazily (manage stops at the first gap)
        if not NEED:
            print('all data present'); break
        calls = len({(e, k, d) for e, k, d in NEED})
        print(f'round {it}: {len(NEED)} contract-days missing (~{(calls + 1) // 2}+ calls)')
        if a.dry_run: break
        total += download()
    print('total API calls', total)
