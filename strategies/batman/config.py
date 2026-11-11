"""Batman settings. Shared settings (index table, folders, calendar, holidays, lot sizes, price rules, Breeze limits,
costs, ENTRY_TIME / ENTRY_DTE / CHECK_TIME) come from shared/config.py and are re-exported here.

STATUS (11-Nov-2026): rules agreed with the user (below); only MARGIN_K is still open (calibrate from one live Kite
basket margin). No backtest yet - next: strike selection and downloads (Breeze), then the backtest scripts.
"""
import os
from pathlib import Path

from shared.config import *            # noqa: F401,F403  (shared settings, re-exported)
from shared.config import ROOT, OUTPUT_ROOT

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
TP_PCT_OF_MARGIN = 4.0           # target: P&L >= 4% of the margin blocked at entry
SL_PCT_OF_MARGIN = 4.0           # stop:   P&L <= -4% of the margin blocked at entry
EXIT_DTE       = 18              # time exit: last trading day on/before expiry - 18 days (same as the condor; to be tested)
# Margin blocked at entry (historical margin is not in the Breeze data): MARGIN_K x NIFTY spot at entry x lot size.
# MARGIN_K is calibrated from one live Batman margin read from Kite's basket (margin / (NIFTY x lot)).
MARGIN_K       = None            # TO DO: calibrate with the user
ENTRY_FILTER   = None            # every month first; the condor's 10-day move filter is a later variant
PERIODS        = ["2021-26 (68 cycles)", "2019-20 (24 cycles, out of sample)"]
