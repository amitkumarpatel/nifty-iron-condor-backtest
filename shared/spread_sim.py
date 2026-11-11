"""Simulator for 2-4 leg option structures (put credit spread, condor, ratio spreads, ...) on cached Breeze candles.

Same timing, price rule and costs as the condor engine: entry at `entry_time`, one check a day at `check_time`
(stop-loss first, then target; the entry day is checked too), time exit on the last trading day on/before
expiry - `exit_dte`. Any strategy can use it; the strategy passes its own rules.
"""
import pandas as pd

from shared import config as C
from shared.calendar import contract_key, load_calendar, time_exit_day
from shared.pricing import price_at, order_costs


def run(entry, expiry, legs, qty, tp_pts=None, sl_pts=None, exit_if=None, exit_dte=18, entry_time=None, check_time=None,
        detail=False):
    """legs: list of (pos, opt, strike), pos = +n long / -n short.
    tp_pts / sl_pts: exit when P&L >= tp_pts or <= -sl_pts (points, checked at check_time).
    exit_if(day, pnl_pts) -> True exits that day (reason RULE).
    entry_time / check_time default to shared/config.py (11:16 / 15:16).
    detail=True adds entry/exit price and quality of every leg and the daily path (every check).
    Returns dict(entry_val (>0 = debit), exit_day, reason, pnl_pts, gross, net, cost, n_fills) or None if not priceable."""
    entry_time = entry_time or C.ENTRY_TIME
    check_time = check_time or C.CHECK_TIME
    entry = pd.Timestamp(entry).date()
    expiry = pd.Timestamp(expiry).date()
    exp = expiry.strftime("%Y-%m-%d")
    keys = [(p, contract_key(exp, k, o)) for p, o, k in legs]
    e, eq = {}, {}
    for p, key in keys:
        px, q, m = price_at(key, entry, entry_time)
        if px is None or (q == "AFTER" and abs(m) > C.MAX_AFTER_MIN_AT_ENTRY):
            return None
        e[key], eq[key] = px, q
    val0 = sum(p * e[k] for p, k in keys)
    cal = load_calendar(entry, expiry)
    tx = time_exit_day(expiry, cal, exit_dte)
    exit_day, reason, val, last, path = tx, "TIME", None, None, []
    for d in [x for x in cal if entry <= x <= tx]:   # entry day included (15:16 check), as in the condor engine
        now = {}
        for p, key in keys:
            px, q, _ = price_at(key, d, check_time)
            if px is None:
                break
            now[key] = (px, q)
        else:
            v = sum(p * now[k][0] for p, k in keys)
            pnl = v - val0
            last = now
            if detail:
                path.append(dict(date=d, value=round(v, 2), pnl_pts=round(pnl, 2), pnl_rs=round(pnl * qty, 2),
                                 **{f"{k}": now[k][0] for _, k in keys}))
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
    cost = order_costs(fills, qty, True) + order_costs(fills, qty, False)   # exit costs approximated at entry prices
    out = dict(entry_val=val0, exit_day=exit_day, reason=reason, pnl_pts=pnl, gross=pnl * qty, net=pnl * qty - cost,
               cost=cost, n_fills=2 * len(fills))
    if detail:
        out.update(legs_entry={k: (e[k], eq[k]) for _, k in keys}, legs_exit=dict(last), path=path)
    return out
