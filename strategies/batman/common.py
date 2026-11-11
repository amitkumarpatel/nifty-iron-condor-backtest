"""Batman helpers: the monthly cycles (entry dates, expiries, lot sizes) and the chosen strikes."""
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from strategies.batman import config as C
from shared.calendar import lot_size


def load_cycles(trade_ids=None) -> pd.DataFrame:
    """The 2021-26 monthly cycles: entry Monday 11:16 at 43 DTE = the condor's reference months + the Apr-2026 expiry.
    Columns: trade_id, entry_date, expiry, lot, ref_sell_ce, ref_sell_pe (the condor's ~30-delta strikes, used only
    to estimate implied volatility when searching for the Batman strikes)."""
    t = pd.concat([pd.read_csv(f, parse_dates=["entry_date", "expiry"]) for f in C.CYCLE_FILES], ignore_index=True)
    t = t.rename(columns={"sell_ce": "ref_sell_ce", "sell_pe": "ref_sell_pe"})
    t["lot"] = [lot_size(e.date()) for e in t.expiry]
    t = t[["trade_id", "entry_date", "expiry", "lot", "ref_sell_ce", "ref_sell_pe"]].sort_values("entry_date")
    if trade_ids:
        t = t[t.trade_id.isin(trade_ids)]
    return t.reset_index(drop=True)


def years(day, expiry) -> float:
    """Time to expiry in years from ENTRY_TIME on `day` to 15:30 on the expiry day (same as the condor's picker)."""
    return (datetime.combine(pd.Timestamp(expiry).date(), datetime.strptime("15:30", "%H:%M").time())
            - datetime.combine(day, datetime.strptime(C.ENTRY_TIME, "%H:%M").time())) / timedelta(days=365)


def strike_file(name=None) -> Path:
    return Path(C.STRIKE_SETS_DIR) / f"strikes_{name or C.STRIKE_SET}.csv"


def load_strikes(name=None) -> pd.DataFrame:
    f = strike_file(name)
    if not f.exists():
        raise SystemExit(f"{f} not found - run `python strategies/batman/scripts/select_strikes.py` first.")
    return pd.read_csv(f, parse_dates=["entry_date", "expiry"])


def legs_of(strikes: pd.DataFrame, trade_id) -> list:
    """[(pos, opt, strike)] of one Batman: +BUY_LOTS at the bought strike, -SELL_LOTS at the sold strike, both sides.
    Empty if any of the four strikes is missing."""
    s = strikes[strikes.trade_id == trade_id].set_index(["opt_type", "role"]).strike
    try:
        return [(C.BUY_LOTS, "CE", int(s["CE", "BUY"])), (-C.SELL_LOTS, "CE", int(s["CE", "SELL"])),
                (C.BUY_LOTS, "PE", int(s["PE", "BUY"])), (-C.SELL_LOTS, "PE", int(s["PE", "SELL"]))]
    except KeyError:
        return []
