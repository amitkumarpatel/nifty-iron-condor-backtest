"""Shared helpers: contracts, calendar, cache paths."""
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from ic import config as C


def contract_key(expiry: str, strike: int, opt_type: str) -> str:
    return f"NIFTY_{expiry}_{int(strike)}{opt_type}"


def cache_file(key: str, day: date) -> Path:
    return Path(C.CACHE_DIR) / key / f"{day.isoformat()}.csv"


def load_inputs(trade_ids=None):
    trades = pd.read_csv(C.TRADES_CSV, parse_dates=["entry_date", "expiry", "ref_exit_date"])
    trades["qty"] = [lot_size(e.date()) for e in trades.expiry]
    legs = pd.read_csv(C.LEGS_CSV)
    if C.ENTRY_SHIFT_DAYS:
        trades["entry_date"] = [pd.Timestamp(shift_entry(d.date(), C.ENTRY_SHIFT_DAYS)) for d in trades.entry_date]
        legs[["entry_px", "exit_px"]] = float("nan")          # StockMock prices are for the original day
    legs = apply_strike_set(legs)
    legs = apply_hedge_width(legs)
    legs["key"] = [contract_key(e, k, t) for e, k, t in zip(legs.expiry, legs.strike, legs.opt_type)]
    if trade_ids:
        trades = trades[trades.trade_id.isin(trade_ids)]
        legs = legs[legs.trade_id.isin(trade_ids)]
    return trades, legs


def shift_entry(day: date, days: int) -> date:
    """`day` + `days` calendar days; a non-trading day moves forward (days > 0) or back (days < 0)."""
    target = day + timedelta(days=days)
    if days < 0:
        cal = load_calendar(target - timedelta(days=10), target)
        return cal[-1] if cal else target
    cal = load_calendar(target, target + timedelta(days=10))
    return cal[0] if cal else target


def lot_size(expiry: date) -> int:
    """NIFTY lot size for a contract expiring on `expiry` (config.LOT_SIZES)."""
    return next(q for last, q in C.LOT_SIZES if expiry <= date.fromisoformat(last))


def apply_strike_set(legs: pd.DataFrame) -> pd.DataFrame:
    """Replace sold strikes with those in strike_sets/strikes_<STRIKE_SET>.csv (from select_strikes.py).
    A moved leg has no StockMock prices."""
    if not C.STRIKE_SET:
        return legs
    f = Path(C.STRIKE_SETS_DIR) / f"strikes_{C.STRIKE_SET}.csv"
    if not f.exists():
        raise SystemExit(f"Strike set '{C.STRIKE_SET}' not found ({f}). Run select_strikes.py first.")
    legs = legs.copy()
    for r in pd.read_csv(f).dropna(subset=["strike"]).itertuples():
        m = (legs.trade_id == r.trade_id) & (legs.side == "SELL") & (legs.opt_type == r.opt_type)
        if m.any() and legs.loc[m, "strike"].iloc[0] != r.strike:
            legs.loc[m, ["strike", "entry_px", "exit_px"]] = [int(r.strike), float("nan"), float("nan")]
    return legs


def apply_hedge_width(legs: pd.DataFrame) -> pd.DataFrame:
    """Move each bought leg to sold strike +/- HEDGE_WIDTH_CE / HEDGE_WIDTH_PE. A moved leg has no StockMock prices."""
    legs = legs.copy()
    sold = legs[legs.side == "SELL"].set_index(["trade_id", "opt_type"]).strike
    for i, r in legs[legs.side == "BUY"].iterrows():
        k = sold[(r.trade_id, r.opt_type)] + (C.HEDGE_WIDTH_CE if r.opt_type == "CE" else -C.HEDGE_WIDTH_PE)
        if k != r.strike:
            legs.loc[i, ["strike", "entry_px", "exit_px"]] = [k, float("nan"), float("nan")]
    return legs


def load_calendar(first: date, last: date) -> list:
    """Trading days from the NIFTY calendar file; beyond its range (or if missing), weekdays.
    EXTRA_HOLIDAYS and MUHURAT_DAYS are always removed."""
    hol = {date.fromisoformat(h) for h in C.EXTRA_HOLIDAYS + C.MUHURAT_DAYS}
    known, cal_end = set(), None
    p = Path(C.CALENDAR_CSV)
    if p.exists():
        df = pd.read_csv(p)
        if len(df):
            known = {date.fromisoformat(d) for d in df.date}
            cal_end = max(known)
    out, d = [], first
    while d <= last:
        ok = (d in known) if (cal_end and d <= cal_end) else d.weekday() < 5
        if ok and d not in hol:
            out.append(d)
        d += timedelta(days=1)
    return out


def time_exit_day(expiry: date, calendar: list) -> date:
    target = expiry - timedelta(days=C.EXIT_DTE)
    return max(d for d in calendar if d <= target)


def iso(dt: datetime) -> str:
    # Breeze reads these as IST wall-clock despite the trailing Z
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def trend_moves(entry_dates) -> pd.Series:
    """NIFTY % move over TREND_LOOKBACK_DAYS trading days, at the last close before each entry date."""
    f = Path(C.INDEX_DAILY["NIFTY"])
    if not f.exists():
        raise SystemExit(f"{f} not found - run `python download.py --index` (needed by the trend filter), "
                         "or set IC_TREND_FILTER=off.")
    c = pd.read_csv(f, parse_dates=["date"]).set_index("date").close.sort_index()
    out = {}
    for d in entry_dates:
        s = c[c.index < pd.Timestamp(d)]
        n = C.TREND_LOOKBACK_DAYS
        out[pd.Timestamp(d)] = (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if len(s) > n else float("nan")
    return pd.Series(out)
