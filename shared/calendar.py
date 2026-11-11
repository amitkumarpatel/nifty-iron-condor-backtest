"""Contracts, trading calendar, lot sizes and cache paths - shared by every strategy."""
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from shared import config as C


def contract_key(expiry: str, strike: int, opt_type: str) -> str:
    return f"{C.INDEX}_{expiry}_{int(strike)}{opt_type}"


def cache_file(key: str, day: date) -> Path:
    return Path(C.CACHE_DIR) / key / f"{day.isoformat()}.csv"


def lot_size(expiry: date) -> int:
    """Lot size of the index for a contract expiring on `expiry` (config.LOT_SIZES)."""
    return next(q for last, q in C.LOT_SIZES if expiry <= date.fromisoformat(last))


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


def shift_entry(day: date, days: int) -> date:
    """`day` + `days` calendar days; a non-trading day moves forward (days > 0) or back (days < 0)."""
    target = day + timedelta(days=days)
    if days < 0:
        cal = load_calendar(target - timedelta(days=10), target)
        return cal[-1] if cal else target
    cal = load_calendar(target, target + timedelta(days=10))
    return cal[0] if cal else target


def time_exit_day(expiry: date, calendar: list, exit_dte: int) -> date:
    """Last trading day on/before expiry - exit_dte calendar days."""
    target = expiry - timedelta(days=exit_dte)
    return max(d for d in calendar if d <= target)


def iso(dt: datetime) -> str:
    # Breeze reads these as IST wall-clock despite the trailing Z
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def index_closes() -> pd.Series:
    """Official daily closes of the traded index (config.INDEX_DAILY_CSV), indexed by date."""
    f = Path(C.INDEX_DAILY_CSV)
    if not f.exists():
        raise SystemExit(f"{f} not found - run `python shared/scripts/fetch_index_nse.py`.")
    return pd.read_csv(f, parse_dates=["date"]).set_index("date").close.sort_index()


def index_move_pct(entry_dates, lookback: int) -> pd.Series:
    """% move of the index over `lookback` trading days, at the last close before each entry date."""
    c = index_closes()
    out = {}
    for d in entry_dates:
        s = c[c.index < pd.Timestamp(d)]
        out[pd.Timestamp(d)] = (s.iloc[-1] / s.iloc[-1 - lookback] - 1) * 100 if len(s) > lookback else float("nan")
    return pd.Series(out)
