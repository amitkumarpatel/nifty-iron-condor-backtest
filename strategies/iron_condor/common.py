"""Iron condor helpers: trade and leg lists (strike sets, hedge widths, entry shift), time exit, trend filter.
Contract, calendar, lot-size and cache helpers come from shared/calendar.py and are re-exported here."""
from datetime import date
from pathlib import Path

import pandas as pd

from strategies.iron_condor import config as C
from shared import calendar as _cal
from shared.calendar import (contract_key, cache_file, lot_size, load_calendar,   # noqa: F401 (re-exported)
                             shift_entry, iso, index_move_pct)


def load_inputs(trade_ids=None):
    trades = pd.read_csv(C.TRADES_CSV, parse_dates=["entry_date", "expiry", "ref_exit_date"])
    trades["ref_exit_date"] = pd.to_datetime(trades.ref_exit_date)   # all-empty in a generated trade set
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


def apply_strike_set(legs: pd.DataFrame) -> pd.DataFrame:
    """Replace sold strikes with those in strike_sets/strikes_<STRIKE_SET>.csv (from select_strikes.py).
    A moved leg has no StockMock prices."""
    if not C.STRIKE_SET:
        return legs
    f = Path(C.STRIKE_SETS_DIR) / f"strikes_{C.STRIKE_SET}.csv"
    if not f.exists():
        raise SystemExit(f"Strike set '{C.STRIKE_SET}' not found ({f}). Run strategies/iron_condor/scripts/select_strikes.py first.")
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


def time_exit_day(expiry: date, calendar: list) -> date:
    """Last trading day on/before expiry - EXIT_DTE calendar days (C.EXIT_DTE, read at call time)."""
    return _cal.time_exit_day(expiry, calendar, C.EXIT_DTE)


def trend_moves(entry_dates) -> pd.Series:
    """% move of the index over TREND_LOOKBACK_DAYS trading days, at the last close before each entry date."""
    if not Path(C.INDEX_DAILY_CSV).exists():
        raise SystemExit(f"{C.INDEX_DAILY_CSV} not found - run `python shared/scripts/fetch_index_nse.py` (needed by the "
                         "trend filter), or set IC_TREND_FILTER=off.")
    return index_move_pct(entry_dates, C.TREND_LOOKBACK_DAYS)
