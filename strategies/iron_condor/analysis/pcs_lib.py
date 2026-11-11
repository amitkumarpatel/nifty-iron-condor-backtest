"""Put credit spread study helpers (moved into the repo 11-Nov-2026)."""
import os, pandas as pd, numpy as np
from strategies.iron_condor import config as C, engine as E
from strategies.iron_condor.common import contract_key, lot_size, load_calendar, time_exit_day
from shared import spread_sim as _spread_sim
class S:   # shared simulator with the condor's exit DTE (C.EXIT_DTE, read at call time)
    run = staticmethod(lambda *a, **k: _spread_sim.run(*a, **{"exit_dte": C.EXIT_DTE, **k}))

REF = pd.concat([pd.read_csv("data/iron_condor/reference/ic_reference_trades.csv"),
                 pd.read_csv("data/iron_condor/reference/ic_trades_2019_2020.csv")]).set_index("trade_id")

def ok_entry(exp, k, e):
    px, q, m = E.price_at(contract_key(exp, k, "PE"), e, C.ENTRY_TIME)
    return (px is not None and not (q == "AFTER" and abs(m) > C.MAX_AFTER_MIN_AT_ENTRY)), px

def coverage(exp, k, e, expd):
    cal = load_calendar(e, expd); tx = time_exit_day(expd, cal); need = [d for d in cal if e <= d <= tx]
    f = os.path.join(str(C.CACHE_DIR), contract_key(exp, k, "PE"))
    have = set(x[:-4] for x in os.listdir(f)) if os.path.isdir(f) else set()
    return sum(str(d) in have for d in need) / len(need)

def pcs(tid, K, w, tp=0.5, sl=1.0):
    """Put credit spread with the fallback rule. Returns dict or None."""
    e = pd.Timestamp(REF.entry_date[tid]).date(); expd = pd.Timestamp(REF.expiry[tid]).date(); exp = str(expd)
    qty = 75 if tid > 1000 else lot_size(expd)
    tries = [(K, K - w, "")] + [(K - s, K - s - w, f"spread {s:+d}") for s in C.FALLBACK_SHIFTS] + \
            [(K, K - w - x, f"hedge {w + x}") for x in C.FALLBACK_HEDGE_EXTRA]
    for ks, kb, why in tries:
        a, pa = ok_entry(exp, ks, e); b, pb = ok_entry(exp, kb, e)
        if a and b and pb < pa and min(coverage(exp, ks, e, expd), coverage(exp, kb, e, expd)) >= 0.9:
            legs = [(-1, "PE", ks), (1, "PE", kb)]
            cr = -S.run(e, exp, legs, qty)["entry_val"]
            x = S.run(e, exp, legs, qty, tp_pts=tp * cr, sl_pts=sl * cr)
            return dict(ks=ks, kb=kb, fb=why, cr=round(cr, 1), net=x["net"], reason=x["reason"], exit=str(x["exit_day"]), qty=qty)
    return None

def moves(tid):
    cl = pd.read_csv("data/shared/nifty_daily.csv", parse_dates=["date"]).set_index("date").close.sort_index()
    p = cl[cl.index < pd.Timestamp(REF.entry_date[tid])]
    return (p.iloc[-1] / p.iloc[-11] - 1) * 100, (p.iloc[-1] / p.iloc[-6] - 1) * 100

def stats(s, entry=None):
    s = s.dropna()
    if entry is not None: s = s.loc[entry.loc[s.index].sort_values().index]
    eq = s.cumsum(); dd = (eq - eq.cummax().clip(lower=0)).min(); l = s[s <= 0]
    return dict(n=len(s), net=round(s.sum()), W=int((s > 0).sum()), L=len(l), dd=round(dd), worst=round(s.min()) if len(s) else 0,
                PF=round(s[s > 0].sum() / -l.sum(), 2) if len(l) else None)
