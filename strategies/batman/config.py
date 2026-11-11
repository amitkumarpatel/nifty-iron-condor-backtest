"""Batman settings. Shared settings (index table, folders, calendar, holidays, lot sizes, price rules, Breeze limits,
costs, ENTRY_TIME / ENTRY_DTE / CHECK_TIME) come from shared/config.py and are re-exported here.

STATUS (11-Nov-2026): rules agreed with the user (below). 2021-26 only, static capital Rs 2.5L, nearest-delta strikes.
"""
import os
from pathlib import Path

from shared.config import *            # noqa: F401,F403  (shared settings, re-exported)
from shared.config import ROOT, OUTPUT_ROOT, DATA_DIR

STRATEGY   = "batman"
OUTPUT_DIR = OUTPUT_ROOT / STRATEGY                              # output/batman/
REF_DIR    = Path(os.environ.get("BATMAN_REF_DIR", ROOT / "data" / STRATEGY / "reference"))

# ---- rules agreed 11-Nov-2026 ----
# Unhedged Batman = call ratio spread + put ratio spread, every month (no entry filter in the first run).
# Per side: BUY BUY_LOTS lot(s) at ~BUY_DELTA, SELL SELL_LOTS lots at ~SELL_DELTA (further out). One sold lot per side is
# therefore uncovered -> unlimited risk beyond the sold strikes; a hedged version (far wing per side) is the next test.
ENTRY_SOURCE   = "iron_condor"   # entry Monday 11:16 at ENTRY_DTE (43) - same dates/expiries as the condor trade lists
BUY_DELTA      = 0.20            # call and put: bought leg (closer to the money)
SELL_DELTA     = 0.16            # call and put: sold legs (further out); must be a different strike from the bought one
BUY_LOTS       = 1
SELL_LOTS      = 2
WING_WIDTH     = None            # None = unhedged (first test). Hedged variant later: buy 1 lot this many pts beyond the sold strike
STRIKE_METHOD  = "black_scholes_11:16"   # delta from option and spot prices at 11:16, as strategies/iron_condor/strikes.py
# Exits, checked once a day at CHECK_TIME (15:16) on the whole position, entry day included; stop before target.
# Capital per Batman: STATIC Rs 2.5 lakh for the tests (user, 11-Nov-2026) -> target = stop = Rs 10,000 in every month.
# (A margin estimate scaled by NIFTY x lot, k = 0.159 from the StockMock sample, was considered and set aside for now.)
CAPITAL        = 250_000
TP_PCT_OF_CAPITAL = 4.0           # target: P&L >= 4% of CAPITAL
SL_PCT_OF_CAPITAL = 4.0           # stop:   P&L <= -4% of CAPITAL
TP_RS          = CAPITAL * TP_PCT_OF_CAPITAL / 100     # Rs 10,000
SL_RS          = CAPITAL * SL_PCT_OF_CAPITAL / 100     # Rs 10,000
EXIT_DTE       = int(os.environ.get("BATMAN_EXIT_DTE", 18))   # time exit: last trading day on/before expiry - 18 days
                                                             # (same as the condor; to be tested; --exit-dte per run)
ENTRY_FILTER   = None            # every month first; the condor's 10-day move filter is a later variant
PERIODS        = ["2021-26 (68 cycles)"]   # 2019-20 not tested yet (user, 11-Nov-2026)

# ---- files ----
# The 68 monthly cycles of 2021-26 = the condor's StockMock reference months + the Apr-2026 expiry (entry 16-Mar-2026).
CYCLE_FILES    = [ROOT / "data" / "iron_condor" / "reference" / "ic_reference_trades.csv",
                  ROOT / "data" / "iron_condor" / "reference" / "ic_trades_apr26.csv"]
STRIKE_SETS_DIR = DATA_DIR / STRATEGY / "strike_sets"          # strikes_<name>.csv from select_strikes.py
STRIKE_SET     = os.environ.get("BATMAN_STRIKE_SET", "b20_16")  # 20-delta bought / 16-delta sold
SEARCH_AROUND  = 3               # candidate strikes each side of the Black-Scholes estimate of each target strike
MAX_EXTEND_ROUNDS = 4            # widen the search while a target delta is not bracketed
