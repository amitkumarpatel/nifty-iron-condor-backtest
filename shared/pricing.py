"""Prices from the 1-minute cache and trading costs - shared by every strategy."""
from datetime import date, datetime
from functools import lru_cache

import pandas as pd

from shared import config as C
from shared.calendar import cache_file


@lru_cache(maxsize=None)
def candles(key: str, day: date) -> pd.Series:
    f = cache_file(key, day)
    if not f.exists():
        return None
    df = pd.read_csv(f)
    if not len(df):
        return pd.Series(dtype=float)
    s = pd.Series(df.close.astype(float).values,
                  index=pd.to_datetime(df.datetime.str[:16])).sort_index()
    return s[~s.index.duplicated(keep="last")]


def price_at(key, day, hhmm):
    """Close of candle labelled hh:mm; else last candle before it that day; else first after.
    Returns (price, quality, minutes_off)."""
    s = candles(key, day)
    if s is None:
        return None, "NOT_DOWNLOADED", None
    target = datetime.combine(day, datetime.strptime(hhmm, "%H:%M").time())
    if target in s.index:
        return float(s[target]), "EXACT", 0
    before = s[s.index < target]
    if len(before):
        m = int((target - before.index[-1]).total_seconds() // 60)
        return float(before.iloc[-1]), ("STALE" if m > C.STALE_WARN_MIN else "FFILL"), m
    after = s[s.index > target]
    if len(after):
        m = int((after.index[0] - target).total_seconds() // 60)
        return float(after.iloc[0]), "AFTER", -m
    return None, "NO_TRADES", None


def order_costs(legs_px, qty, entry: bool):
    """legs_px: list of (side, price). entry=True -> SELL legs sold, BUY legs bought."""
    k = C.COSTS
    sell_turn = buy_turn = 0.0
    for side, px in legs_px:
        turn = px * qty
        is_sell = (side == "SELL") == entry
        if is_sell:
            sell_turn += turn
        else:
            buy_turn += turn
    tot = sell_turn + buy_turn
    brk = k["brokerage_per_order"] * len(legs_px)
    exch = tot * k["exch_txn_pct"] / 100
    sebi = tot * k["sebi_per_crore"] / 1e7
    stt = sell_turn * k["stt_sell_pct"] / 100
    stamp = buy_turn * k["stamp_buy_pct"] / 100
    gst = (brk + exch + sebi) * k["gst_pct"] / 100
    slip = k["slippage_pts_per_leg"] * qty * len(legs_px)
    return brk + exch + sebi + stt + stamp + gst + slip
