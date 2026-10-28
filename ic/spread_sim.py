"""Simulator for 2-4 leg option structures (put credit spread etc.) on cached Breeze candles.

Same timing, price rule and costs as the condor engine: entry at ENTRY_TIME, one check a day at CHECK_TIME
(stop-loss first, then target), time exit on the last trading day on/before expiry - EXIT_DTE.
Used for the forward-test put credit spread studies (README section 7); backtest.py does not use it.
"""
import pandas as pd

from . import config as C
from . import engine as E
from .common import contract_key, load_calendar, time_exit_day


def run(entry, expiry, legs, qty, tp_pts=None, sl_pts=None, exit_if=None):
    """legs: list of (pos, opt, strike), pos = +n long / -n short.
    tp_pts / sl_pts: exit when P&L >= tp_pts or <= -sl_pts (points, checked at CHECK_TIME).
    exit_if(day, pnl_pts) -> True exits that day (reason RULE).
    Returns dict(entry_val (>0 = debit), exit_day, reason, pnl_pts, gross, net) or None if not priceable."""
    entry = pd.Timestamp(entry).date()
    expiry = pd.Timestamp(expiry).date()
    exp = expiry.strftime("%Y-%m-%d")
    keys = [(p, contract_key(exp, k, o)) for p, o, k in legs]
    e = {}
    for p, key in keys:
        px, q, m = E.price_at(key, entry, C.ENTRY_TIME)
        if px is None or (q == "AFTER" and abs(m) > C.MAX_AFTER_MIN_AT_ENTRY):
            return None
        e[key] = px
    val0 = sum(p * e[k] for p, k in keys)
    cal = load_calendar(entry, expiry)
    tx = time_exit_day(expiry, cal)
    exit_day, reason, val = tx, "TIME", None
    for d in [x for x in cal if entry < x <= tx]:
        now = {}
        for p, key in keys:
            px = E.price_at(key, d, C.CHECK_TIME)[0]
            if px is None:
                break
            now[key] = px
        else:
            v = sum(p * now[k] for p, k in keys)
            pnl = v - val0
            if sl_pts is not None and pnl <= -sl_pts:
                exit_day, reason, val = d, "STOPLOSS", v
                break
            if tp_pts is not None and pnl >= tp_pts:
                exit_day, reason, val = d, "TARGET", v
                break
            if exit_if is not None and exit_if(d, pnl):
                exit_day, reason, val = d, "RULE", v
                break
            val = v
    if val is None:
        return None
    pnl = val - val0
    fills = [("BUY" if p > 0 else "SELL", e[k]) for p, k in keys for _ in range(abs(p))]
    cost = E.order_costs(fills, qty, True) + E.order_costs(fills, qty, False)   # exit costs approximated at entry prices
    return dict(entry_val=val0, exit_day=exit_day, reason=reason, pnl_pts=pnl, gross=pnl * qty, net=pnl * qty - cost,
                cost=cost, n_fills=2 * len(fills))
